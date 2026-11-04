#!/usr/bin/env python3
"""Find same-directory PDF name/size duplicates using metadata only (Python 3.8+).

Standalone: no application imports, database access, content reads or file writes.
Results are candidates, not proof of identical content or a deletion list.
Directory birth times use native stat attributes or GNU stat on Linux; never ctime.
"""

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time


def directory_times(path):
    result = {'path': str(path), 'created_at': None, 'created_at_status': 'unavailable',
              'created_at_source': None, 'modified_at': None}

    def timestamp(value):
        return datetime.fromtimestamp(value, timezone(timedelta(hours=8))).isoformat(timespec='seconds')

    try:
        info = os.stat(path, follow_symlinks=False)
        if not stat.S_ISDIR(info.st_mode):
            result['created_at_status'] = 'not_a_directory'
            return result
        result['modified_at'] = timestamp(info.st_mtime)
        birth = getattr(info, 'st_birthtime', None)
        source = 'os.stat.st_birthtime'
        if birth is None and sys.platform.startswith('linux'):
            # GNU %W returns zero when birth time is unknown. Include identity
            # to reject a directory replaced between Python stat and GNU stat.
            command = ['stat', '--format=%d %i %W', '--', str(path)]
            completed = subprocess.run(command, capture_output=True, text=True, timeout=3)
            if completed.returncode != 0:
                result['created_at_status'] = 'query_failed'
                return result
            device, inode, birth = map(int, completed.stdout.split())
            if (device, inode) != (info.st_dev, info.st_ino):
                result['created_at_status'] = 'directory_changed'
                return result
            birth = birth or None
            source = 'GNU stat %W'
        if birth is not None:
            result['created_at'] = timestamp(birth)
            result['created_at_status'] = 'available'
            result['created_at_source'] = source
    except (OSError, ValueError, OverflowError, subprocess.TimeoutExpired):
        result['created_at_status'] = 'query_failed'
    return result


def scan(root, top=30):
    groups = defaultdict(list)
    errors = []
    error_count = 0
    seen_links = set()
    pdf_files = 0
    started = time.monotonic()
    last_progress = started

    def record_error(error):
        nonlocal error_count
        error_count += 1
        if len(errors) < 20:
            errors.append(str(error))

    for directory, dirs, files, directory_fd in os.fwalk(root, follow_symlinks=False, onerror=record_error):
        parts = Path(directory).relative_to(root).parts
        # Canonical direct attachments; retain mailbox identity as well as UID.
        if not (len(parts) == 5 and parts[0] == 'mailboxes' and parts[2] == 'messages'
                and parts[3].isdigit() and parts[4] == 'attachments'):
            continue
        for name in files:
            if not name.lower().endswith('.pdf'):
                continue
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    continue
                if info.st_nlink > 1:
                    identity = info.st_dev, info.st_ino
                    if identity in seen_links:
                        continue
                    seen_links.add(identity)
                original = re.sub(r'^[0-9a-fA-F]{32}-', '', name)
                groups[(parts[1], parts[3], original, info.st_size)].append(
                    (info.st_blocks * 512, str(Path(directory) / name)))
                pdf_files += 1
            except OSError as error:
                record_error(error)
        now = time.monotonic()
        if now - last_progress >= 10:
            print('Scanned {} PDF files'.format(pdf_files), file=sys.stderr, flush=True)
            last_progress = now

    candidates = []
    for (mailbox, uid, name, size), files in groups.items():
        if len(files) < 2:
            continue
        candidates.append({
            'mailbox': mailbox, 'uid': int(uid), 'original_filename': name,
            'copies': len(files), 'each_logical_bytes': size,
            'group_allocated_bytes': sum(item[0] for item in files),
            'group_allocated_mib': round(sum(item[0] for item in files) / 1048576, 2),
            'sample_paths': [item[1] for item in files[:2]],
        })
    candidates.sort(key=lambda row: row['group_allocated_bytes'], reverse=True)
    top_groups = candidates[:top]
    directory_cache = {}
    for row in top_groups:
        attachment_directory = Path(row['sample_paths'][0]).parent
        for key, path in (('message_directory', attachment_directory.parent),
                          ('attachment_directory', attachment_directory)):
            if path not in directory_cache:
                directory_cache[path] = directory_times(path)
            row[key] = directory_cache[path]
    return {
        'root': str(root), 'complete': error_count == 0,
        'duration_seconds': round(time.monotonic() - started, 2),
        'pdf_files_scanned': pdf_files, 'candidate_groups': len(candidates),
        'candidate_files': sum(row['copies'] for row in candidates),
        'candidate_group_allocated_bytes': sum(row['group_allocated_bytes'] for row in candidates),
        'top_groups': top_groups, 'error_count': error_count, 'error_examples': errors,
        'directory_time_zone': 'UTC+08:00',
        'notes': [
            'Same mailbox + UID + filename without UUID prefix + file size. Content was NOT hashed.',
            'Scope: mail_store/mailboxes/*/messages/<UID>/attachments/*.pdf (case-insensitive extension).',
            'Different UIDs stay separate. Hardlink aliases are counted once; symlinks are not followed.',
            'Group bytes include all copies, NOT estimated reclaimable space. No database references were checked.',
            'This is a live scan, not an atomic snapshot. Directory reads may update atime.',
            'Directory created_at is birth time, NOT ctime. Null means unavailable; see created_at_status.',
            'Directory times use UTC+08:00. Directory birth time does not date every attachment or email receipt.',
            'Directory time availability is reported per directory, independently of the metadata scan complete flag.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='mail_store directory')
    parser.add_argument('--top', type=int, default=30)
    args = parser.parse_args()
    if args.root.is_symlink() or not args.root.is_dir() or not 1 <= args.top <= 1000:
        parser.error('--root must be an existing directory (not a symlink); --top must be 1..1000')
    report = scan(args.root.resolve(), args.top)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('Interrupted; no complete report produced.', file=sys.stderr)
        sys.exit(130)
