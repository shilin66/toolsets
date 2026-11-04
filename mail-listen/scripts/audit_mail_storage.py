#!/usr/bin/env python3
"""Standalone, standard-library-only storage inventory (Python 3.8+, Unix).

Reads metadata by default. --hash-attachments additionally reads stable attachment
contents. Never imports the application, opens SQLite, or writes scanned files.
All output goes to stdout/stderr; redirect reports outside the scanned directory.
"""

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import stat
import sys
import time


def empty_stat():
    return {'files': 0, 'logical_bytes': 0, 'allocated_bytes': 0}


def add_stat(bucket, info):
    bucket['files'] += 1
    bucket['logical_bytes'] += info.st_size
    bucket['allocated_bytes'] += info.st_blocks * 512


def layout(root, relative):
    parts = relative.parts
    if root.name in ('mail_store', 'email_attachments', 'rpa'):
        parts = (root.name,) + parts
    extension = relative.suffix.lower() or '(no extension)'
    mailbox, message, owner = '(unmapped)', None, None
    category = 'other'
    if (len(parts) >= 6 and parts[:2] == ('mail_store', 'mailboxes')
            and parts[3] == 'messages' and parts[4].isdigit()):
        mailbox = parts[2]
        message = '/'.join(parts[:5])
        tail = parts[5:]
        if tail[0] == 'attachments':
            category, owner = 'attachments', '/'.join(parts[:-1])
        elif len(tail) == 1 and tail[0] == 'source-email-{}.eml'.format(parts[4]):
            category = 'source_eml'
        elif tail[:2] == ('cutover', 'report-inputs'):
            category = 'report_inputs'
        elif tail[:2] == ('cutover', 'customer'):
            category = 'customer_excel'
        elif tail[:2] == ('cutover', 'reports'):
            category = 'report_screenshots' if extension in ('.png', '.jpg', '.jpeg', '.webp') else 'report_other'
        else:
            category = 'message_other'
    elif parts and parts[0] == 'email_attachments':
        category = 'preview_attachments' if len(parts) > 1 and parts[1] == 'preview-extract' else 'legacy_attachments'
        if category == 'legacy_attachments':
            owner = '/'.join(parts[:-1])
    elif parts[:2] == ('rpa', 'backbone-attachments') and extension == '.eml':
        category = 'legacy_source_eml'
    elif parts[:2] == ('rpa', 'artifacts'):
        category = 'legacy_rpa_artifacts'
    return category, extension, mailbox, message, owner


def age_bucket(modified, now):
    days = (now - modified) / 86400
    if days < 0:
        return 'future_mtime'
    for limit, label in ((7, '0-7d'), (30, '7-30d'), (90, '30-90d'), (180, '90-180d')):
        if days < limit:
            return label
    return '180d+'


def signature(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def content_hash(directory_fd, name, expected):
    # O_NOFOLLOW rejects a final-component symlink introduced after the stat.
    # O_NONBLOCK avoids blocking if a file is replaced by a FIFO mid-scan.
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or signature(before) != signature(expected):
            return None
        digest = hashlib.sha256()
        remaining = expected.st_size
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                return None
            digest.update(chunk)
            remaining -= len(chunk)
        after = os.fstat(stream.fileno())
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if signature(before) != signature(after) or signature(before) != signature(current):
            return None
        return digest.hexdigest()


def top_rows(mapping, limit, key='allocated_bytes'):
    return [dict(name=name, **values) for name, values in
            heapq.nlargest(limit, mapping.items(), key=lambda item: item[1][key])]


def summarize_hashes(groups, audit, limit):
    top = []
    for (size, digest), group in groups.items():
        count = sum(value[0] for value in group['owners'].values())
        if count < 2:
            continue
        owners = group['owners']
        allocated = sum(value[1] for value in owners.values())
        max_allocated = max(value[2] for value in owners.values())
        within = count - len(owners)
        across = len(owners) - 1
        audit['duplicate_groups'] += 1
        audit['within_directory_extra_copies'] += within
        audit['across_directory_extra_copies'] += across
        audit['extra_copy_logical_bytes'] += (count - 1) * size
        audit['extra_copy_allocated_upper_bound_bytes'] += allocated - max_allocated
        row = {'sha256': digest, 'file_bytes': size, 'copies': count,
               'attachment_directories': len(owners), 'within_directory_extra_copies': within,
               'across_directory_extra_copies': across,
               'extra_copy_logical_bytes': (count - 1) * size,
               'extra_copy_allocated_upper_bound_bytes': allocated - max_allocated,
               'sample_paths': group['examples']}
        item = (allocated - max_allocated, digest, row)
        if len(top) < limit:
            heapq.heappush(top, item)
        elif item[:2] > top[0][:2]:
            heapq.heapreplace(top, item)
    audit['top_groups'] = [item[2] for item in sorted(top, reverse=True)]


def inventory(root, *, hash_attachments=False, settle_hours=24, top=20):
    started = time.time()
    started_iso = datetime.fromtimestamp(started, timezone.utc).isoformat()
    root_info = root.stat()
    fs = os.statvfs(root)
    totals = {'regular_file_paths': 0, 'unique_regular_files': 0, 'hardlink_aliases': 0,
              'logical_bytes': 0, 'allocated_bytes': 0, 'directories': 0,
              'directory_allocated_bytes': 0, 'symlinks': 0, 'symlink_allocated_bytes': 0,
              'special_files': 0, 'cross_device_directories_skipped': 0}
    extensions, categories, category_extensions, mailboxes, messages, months, ages = (
        defaultdict(empty_stat) for _ in range(7))
    hash_audit = {'enabled': hash_attachments, 'settle_hours': settle_hours,
                  'hashed_files': 0, 'hashed_bytes': 0, 'recent_files_skipped': 0,
                  'changed_files_skipped': 0, 'duplicate_groups': 0,
                  'within_directory_extra_copies': 0, 'across_directory_extra_copies': 0,
                  'extra_copy_logical_bytes': 0, 'extra_copy_allocated_upper_bound_bytes': 0,
                  'top_groups': []}
    groups, seen_links, largest = {}, set(), []
    errors = {'count': 0, 'examples': []}
    last_progress = started

    def record_error(error):
        errors['count'] += 1
        if len(errors['examples']) < 20:
            errors['examples'].append(str(error))

    def add_symlink(info):
        totals['symlinks'] += 1
        totals['symlink_allocated_bytes'] += info.st_blocks * 512

    for directory, dirs, files, directory_fd in os.fwalk(root, follow_symlinks=False, onerror=record_error):
        info = os.fstat(directory_fd)
        totals['directories'] += 1
        totals['directory_allocated_bytes'] += info.st_blocks * 512
        for name in list(dirs):
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    add_symlink(info)
                    dirs.remove(name)
                elif info.st_dev != root_info.st_dev:
                    totals['cross_device_directories_skipped'] += 1
                    dirs.remove(name)
            except OSError as error:
                record_error(error)
                dirs.remove(name)
        for name in files:
            try:
                info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode):
                    add_symlink(info)
                    continue
                if not stat.S_ISREG(info.st_mode):
                    totals['special_files'] += 1
                    continue
                totals['regular_file_paths'] += 1
                if info.st_nlink > 1:
                    identity = info.st_dev, info.st_ino
                    if identity in seen_links:
                        totals['hardlink_aliases'] += 1
                        continue
                    seen_links.add(identity)
                relative = (Path(directory) / name).relative_to(root)
                category, extension, mailbox, message, owner = layout(root, relative)
                totals['unique_regular_files'] += 1
                totals['logical_bytes'] += info.st_size
                totals['allocated_bytes'] += info.st_blocks * 512
                try:
                    month = datetime.fromtimestamp(info.st_mtime, timezone.utc).strftime('%Y-%m')
                except (ValueError, OverflowError, OSError):
                    month = '(invalid mtime)'
                for bucket in (extensions[extension], categories[category],
                               category_extensions[category + ' / ' + extension],
                               mailboxes[mailbox], months[month], ages[age_bucket(info.st_mtime, started)]):
                    add_stat(bucket, info)
                if message:
                    add_stat(messages[message], info)
                path_text = relative.as_posix()
                item = (info.st_blocks * 512, info.st_size, path_text)
                if len(largest) < top:
                    heapq.heappush(largest, item)
                elif item > largest[0]:
                    heapq.heapreplace(largest, item)
                if hash_attachments and owner:
                    if max(info.st_mtime, info.st_ctime) > started - settle_hours * 3600:
                        hash_audit['recent_files_skipped'] += 1
                    else:
                        digest = content_hash(directory_fd, name, info)
                        if digest is None:
                            hash_audit['changed_files_skipped'] += 1
                        else:
                            hash_audit['hashed_files'] += 1
                            hash_audit['hashed_bytes'] += info.st_size
                            group = groups.setdefault((info.st_size, digest), {'owners': {}, 'examples': []})
                            value = group['owners'].setdefault(owner, [0, 0, 0])
                            value[0] += 1
                            value[1] += info.st_blocks * 512
                            value[2] = max(value[2], info.st_blocks * 512)
                            if len(group['examples']) < 3:
                                group['examples'].append(path_text)
            except OSError as error:
                record_error(error)
            now = time.time()
            if now - last_progress >= 10:
                print('Scanned {} files; hashed {} files'.format(
                    totals['unique_regular_files'], hash_audit['hashed_files']), file=sys.stderr, flush=True)
                last_progress = now
    summarize_hashes(groups, hash_audit, top)
    totals['tree_allocated_bytes'] = (totals['allocated_bytes'] + totals['directory_allocated_bytes']
                                     + totals['symlink_allocated_bytes'])
    return {
        'schema_version': 1, 'root': str(root), 'started_at_utc': started_iso,
        'finished_at_utc': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': round(time.time() - started, 2),
        'complete': errors['count'] == 0,
        'filesystem': {'total_bytes': fs.f_blocks * fs.f_frsize,
                       'available_bytes': fs.f_bavail * fs.f_frsize,
                       'total_inodes': fs.f_files, 'free_inodes': fs.f_ffree},
        'totals': totals, 'extensions': dict(extensions), 'categories': dict(categories),
        'category_extensions': dict(category_extensions), 'mailboxes': dict(mailboxes),
        'message_directories': len(messages),
        'top_messages_by_allocated_bytes': top_rows(messages, top),
        'top_messages_by_file_count': top_rows(messages, top, 'files'),
        'mtime_months_utc': dict(sorted(months.items())), 'mtime_age_buckets': dict(ages),
        'top_files': [{'path': path, 'logical_bytes': size, 'allocated_bytes': allocated}
                      for allocated, size, path in sorted(largest, reverse=True)],
        'hash_audit': hash_audit, 'errors': errors,
        'notes': [
            'Metadata scan is not an atomic filesystem snapshot. No database/reference/thread audit was performed.',
            'Allocated bytes = st_blocks * 512; hardlinked files counted once, attributed to first encountered path.',
            'Directory and symlink blocks are separate from regular-file extension totals. Symlinks are not followed.',
            'Traversal stays on the root device. Filesystem capacity/inodes describe the whole filesystem, not this tree.',
            'mtime is modification time, NOT receipt time, discussion activity or net growth. Migration can change it.',
            'Hash scope: canonical and legacy attachment directories only, excluding preview uploads, EML and reports.',
            'Hash eligibility uses both mtime and ctime. Files changed during reading are excluded.',
            'Directory identity does not identify a conversation. Equal content may be legitimate across replies or MIME parts.',
            'Duplicate allocation is a theoretical upper bound, NOT reclaimable space. References, reflinks and external links are not audited.',
            'Reads may update atime according to filesystem mount policy. No source contents, names or permissions are written.',
        ],
    }


def print_text(report):
    def mib(value):
        return value / 1048576

    def table(title, mapping):
        print('\n' + title)
        print('  allocated MiB    content MiB       files  item')
        for name, row in sorted(mapping.items(), key=lambda item: item[1]['allocated_bytes'], reverse=True):
            print('{:15.2f}{:15.2f}{:12d}  {}'.format(mib(row['allocated_bytes']),
                  mib(row['logical_bytes']), row['files'], json.dumps(name, ensure_ascii=False)))

    print('Root:', json.dumps(report['root'], ensure_ascii=False))
    print('Scan UTC:', report['started_at_utc'], '->', report['finished_at_utc'])
    print('Complete:', report['complete'], '| seconds:', report['duration_seconds'])
    print('Totals:', json.dumps(report['totals'], ensure_ascii=False))
    print('Filesystem (whole volume):', json.dumps(report['filesystem']))
    for title, key in [('File extensions', 'extensions'), ('Storage purpose', 'categories'),
                       ('Purpose / extension', 'category_extensions'), ('Mailboxes', 'mailboxes'),
                       ('Modification month UTC (not growth)', 'mtime_months_utc'),
                       ('Modification age (not retention eligibility)', 'mtime_age_buckets')]:
        table(title, report[key])
    for title, key in [('Top message directories by disk', 'top_messages_by_allocated_bytes'),
                       ('Top message directories by file count', 'top_messages_by_file_count')]:
        print('\n' + title)
        for row in report[key]:
            print('{:.2f} MiB | {} files | {}'.format(mib(row['allocated_bytes']), row['files'],
                  json.dumps(row['name'], ensure_ascii=False)))
    print('\nTop files')
    for row in report['top_files']:
        print('{:.2f} MiB allocated | {:.2f} MiB content | {}'.format(
            mib(row['allocated_bytes']), mib(row['logical_bytes']), json.dumps(row['path'], ensure_ascii=False)))
    print('\nHash audit:', json.dumps(report['hash_audit'], ensure_ascii=False, indent=2))
    print('\nErrors:', json.dumps(report['errors'], ensure_ascii=False))
    for note in report['notes']:
        print('-', note)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='mail_store directory, or data to include legacy files')
    parser.add_argument('--format', choices=('text', 'json'), default='text')
    parser.add_argument('--top', type=int, default=20)
    parser.add_argument('--hash-attachments', action='store_true', help='also read stable attachments for SHA-256 equality')
    parser.add_argument('--settle-hours', type=float, default=24, help='minimum mtime AND ctime age for hashing (default 24)')
    args = parser.parse_args(argv)
    if not 1 <= args.top <= 100 or not math.isfinite(args.settle_hours) or args.settle_hours < 0:
        parser.error('--top must be 1..100; --settle-hours must be finite and nonnegative')
    if args.root.is_symlink() or not args.root.is_dir():
        parser.error('--root must be an existing directory, not a symlink')
    root = args.root.resolve()
    if not hasattr(os, 'fwalk') or not hasattr(os, 'O_NOFOLLOW'):
        parser.error('This script requires Unix (Linux/macOS)')
    try:
        report = inventory(root, hash_attachments=args.hash_attachments, settle_hours=args.settle_hours, top=args.top)
    except OSError as error:
        print('Audit failed: {}'.format(error), file=sys.stderr)
        return 2
    if args.format == 'json':
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text(report)
    return 0 if report['complete'] else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('Interrupted; no complete report produced.', file=sys.stderr)
        sys.exit(130)
