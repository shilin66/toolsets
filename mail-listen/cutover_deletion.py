"""Delete one local cutover email and its children, with retryable file cleanup."""

import json
import os
import re
from collections import defaultdict
from pathlib import Path

from loguru import logger

from html_image import IMAGE_DIR
from mail_artifacts import MailArtifactError, legacy_mailbox_storage_key, message_storage_directory


class DeletionConflict(ValueError):
    pass


class DeletionCleanupError(RuntimeError):
    pass


class DeletionNotFound(LookupError):
    pass


def _safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or not relative.parts or '..' in relative.parts:
        raise DeletionCleanupError('删除文件路径无效')
    allowed = (relative.parts[0] in ('mail_store', 'email_attachments')
        or relative.parts[:2] in (('rpa', 'artifacts'), ('rpa', 'backbone-attachments'))
        or len(relative.parts) == 1 and relative.suffix.lower() == '.xlsx')
    if not allowed:
        raise DeletionCleanupError('删除文件不在邮件数据目录内')
    path = root
    for part in relative.parts:
        path /= part
        if path.is_symlink():
            raise DeletionCleanupError('邮件文件包含符号链接，无法安全删除')
    if not path.resolve().is_relative_to(root):
        raise DeletionCleanupError('邮件文件路径越出数据目录')
    return path


def _message_roots(root, record):
    try:
        current = message_storage_directory(root, mailbox_address=record['receiver'], email_uid=record['email_id'])
        legacy = root / 'mail_store' / 'mailboxes' / legacy_mailbox_storage_key(record['receiver']) / 'messages' / str(record['email_id'])
    except MailArtifactError:
        logger.warning('删除清理跳过缺少邮箱或 UID 的邮件目录: email_records_id={}', record['id'])
        return set()
    return {current.relative_to(root).as_posix(), legacy.relative_to(root).as_posix()}


def _optional_json(value, field):
    if isinstance(value, str):
        if not value.strip():
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning('删除清理跳过无法解析的可选字段: field={}', field)
            return None
    return value


def _report_references(result):
    result = _optional_json(result, 'cutover_reports.result')
    if not isinstance(result, dict):
        return []
    references = [result.get('screenshot_path')]
    operation_log = result.get('operation_log')
    if isinstance(operation_log, list):
        references.extend(step.get('screenshot_filename') for step in operation_log if isinstance(step, dict))
    references.extend(re.findall(r'(?:data/rpa/artifacts/|mail_store/mailboxes/)[^\s；，。]+\.png',
        str(result.get('error') or '')))
    return [value for value in references if isinstance(value, str) and value]


def _file_reference(root, value, *, report=False, shared=False):
    """Resolve stored paths against this deployment, never delete on an old host."""
    if not isinstance(value, str) or not value.strip():
        return None
    if '\x00' in value:
        logger.warning('删除清理跳过无效的文件引用')
        return None
    path = Path(value.strip())
    if '..' in path.parts:
        if shared:
            logger.warning('共享文件检查跳过路径越界引用')
            return None
        raise DeletionCleanupError('删除文件路径无效')
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            # Older container/host deployments stored /app/data/... absolute paths.
            # Only map recognized application layouts, not arbitrary external paths.
            relocated = None
            for index, part in enumerate(path.parts):
                tail = path.parts[index + 1:]
                if part == 'data' and tail and (
                    tail[0] in ('mail_store', 'email_attachments')
                    or tail[:2] in (('rpa', 'artifacts'), ('rpa', 'backbone-attachments'))
                    or len(tail) == 1 and Path(tail[0]).suffix.lower() == '.xlsx'
                ):
                    relocated = Path(*tail)
                    break
            if relocated is not None:
                path = relocated
            elif shared or not os.path.lexists(path):
                logger.warning('删除清理跳过外部历史文件引用: reason={}',
                    'other_mail_reference' if shared else 'file_missing')
                return None
            else:
                raise DeletionCleanupError('文件不在数据目录内，无法安全删除')
    elif path.parts and path.parts[0] == 'data':
        path = Path(*path.parts[1:])
    elif report and path.parts and path.parts[0] not in ('mail_store', 'rpa'):
        path = Path('rpa/artifacts') / path
    if not path.parts:
        return None
    return path.as_posix()


def _references(root, record, tasks, reports, *, shared=False):
    """Include legacy aliases so a file shared by another email is never removed."""
    roots = _message_roots(root, record)
    attachments = _optional_json(record['attachments'], 'email_records.attachments')
    files = set()
    if isinstance(attachments, list):
        files.update(relative for value in attachments
            if (relative := _file_reference(root, value, shared=shared)) is not None)
    for task in tasks:
        filename = task['customer_excel_filename']
        if isinstance(filename, str) and filename.strip():
            relative = _file_reference(root, filename, shared=shared)
            if relative and Path(relative).suffix.lower() == '.xlsx':
                files.add(relative)
                if Path(relative).name == relative:
                    files.update(f'{directory}/cutover/customer/{relative}' for directory in roots)
            else:
                logger.warning('删除清理跳过无效的可选 Excel 引用: email_records_id={}', record['id'])
    for report in reports:
        files.update(relative for value in _report_references(report['result'])
            if (relative := _file_reference(root, value, report=True, shared=shared)) is not None)
    files.add(f"rpa/backbone-attachments/UID-{record['email_id']}.eml")
    roots.add(f"email_attachments/{record['email_id']}")
    return roots, files


def _shared_references(conn, root, excluded_id):
    roots, files = set(), set()
    tasks_by_email, reports_by_email = defaultdict(list), defaultdict(list)
    for task in conn.execute('SELECT id,email_records_id,customer_excel_filename FROM cutover_tasks WHERE email_records_id!=?', (excluded_id,)):
        tasks_by_email[task['email_records_id']].append(task)
    for report in conn.execute('''SELECT t.email_records_id,r.result FROM cutover_reports r
        JOIN cutover_tasks t ON t.id=r.task_id WHERE t.email_records_id!=?''', (excluded_id,)):
        reports_by_email[report['email_records_id']].append(report)
    for row in conn.execute('SELECT id, receiver, email_id, attachments FROM email_records WHERE id != ?', (excluded_id,)):
        other_roots, other_files = _references(root, row, tasks_by_email[row['id']], reports_by_email[row['id']], shared=True)
        roots.update(other_roots)
        files.update(other_files)
    return roots, files


def _is_shared(relative, roots, files):
    return relative in files or any(relative == directory or relative.startswith(directory + '/') for directory in roots)


def _remaining_is_shared(root, path, shared_roots, shared_files):
    relative = path.relative_to(root).as_posix()
    _safe_path(root, relative)
    if _is_shared(relative, shared_roots, shared_files):
        return True
    if path.is_dir():
        children = list(path.iterdir())
        return bool(children) and all(_remaining_is_shared(root, child, shared_roots, shared_files) for child in children)
    return False


def _image_path(image_root, filename, uid):
    # The historical renderer used one fixed temporary directory and UUID hex names.
    # Never interpret these names as arbitrary manifest paths outside DATA_DIR.
    if not re.fullmatch(rf'email-{uid}-[a-f0-9]{{32}}\.png', filename):
        raise DeletionCleanupError('邮件正文图片名称无效')
    path = image_root / filename
    if image_root.is_symlink() or path.is_symlink():
        raise DeletionCleanupError('邮件正文图片包含符号链接，无法安全删除')
    return path


def _collect_images(conn, image_root, record):
    if conn.execute('SELECT 1 FROM email_records WHERE email_id=? AND id!=?', (record['email_id'], record['id'])).fetchone():
        return []  # The legacy format lacks mailbox identity; same-UID files are shared.
    if image_root.is_symlink():
        raise DeletionCleanupError('邮件正文图片目录包含符号链接，无法安全删除')
    images = []
    try:
        candidates = list(image_root.iterdir())
    except FileNotFoundError:
        return []
    for path in candidates:
        if re.fullmatch(rf"email-{record['email_id']}-[a-f0-9]{{32}}\.png", path.name):
            path = _image_path(image_root, path.name, record['email_id'])
            if not path.is_file():
                raise DeletionCleanupError('邮件正文图片不是普通文件')
            images.append(path.name)
    return images


def _collect_manifest(conn, root, record):
    tasks = conn.execute('SELECT id,customer_excel_filename FROM cutover_tasks WHERE email_records_id=?', (record['id'],)).fetchall()
    reports = conn.execute('''SELECT r.result FROM cutover_reports r JOIN cutover_tasks t ON t.id=r.task_id
        WHERE t.email_records_id=?''', (record['id'],)).fetchall()
    roots, files = _references(root, record, tasks, reports)
    shared_roots, shared_files = _shared_references(conn, root, record['id'])
    directories = set()
    # Old report layouts also contain intermediate/failure screenshots omitted from result JSON.
    artifact_root = _safe_path(root, 'rpa/artifacts')
    if artifact_root.is_dir():
        task_ids = {str(task['id']) for task in tasks}
        for date_dir in artifact_root.iterdir():
            if not date_dir.is_dir():
                continue
            record_dir = _safe_path(root, (date_dir / str(record['id'])).relative_to(root))
            try:
                report_dirs = list(record_dir.iterdir())
            except FileNotFoundError:
                continue
            for path in report_dirs:
                match = re.fullmatch(r'([0-9]+)_(?:adhoc|[0-9]+)', path.name)
                if match and match.group(1) in task_ids:
                    roots.add(path.relative_to(root).as_posix())
    for relative in sorted(roots):
        if _is_shared(relative, shared_roots, shared_files):
            continue
        directory = _safe_path(root, relative)
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise DeletionCleanupError('邮件存储目录不是目录')
        def walk_error(error):
            raise error
        for current, child_dirs, child_files in os.walk(directory, followlinks=False, onerror=walk_error):
            current_relative = Path(current).relative_to(root).as_posix()
            _safe_path(root, current_relative)
            directories.add(current_relative)
            for name in child_dirs:
                _safe_path(root, (Path(current) / name).relative_to(root))
            for name in child_files:
                files.add((Path(current) / name).relative_to(root).as_posix())
    exclusive = []
    for relative in sorted(files):
        if _is_shared(relative, shared_roots, shared_files):
            continue
        # A legacy attachment may contain only a filename from a removed layout.
        # Missing references need no deletion; existing files still pass all checks.
        if not os.path.lexists(root / relative):
            continue
        path = _safe_path(root, relative)
        if path.exists():
            if not path.is_file():
                raise DeletionCleanupError('邮件文件引用不是普通文件')
            exclusive.append(relative)
    return {'root':str(root), 'files':exclusive,
        'directories':sorted(directories, key=lambda item: len(Path(item).parts), reverse=True)}


def _reject_active(conn, record):
    if record['reply_status'] == 'sending' or record['api_forward_status'] == 'forwarding':
        raise DeletionConflict('邮件正在解析或发送回复，请处理完成后删除')
    if conn.execute("SELECT 1 FROM cutover_tasks WHERE email_records_id=? AND status='reporting'", (record['id'],)).fetchone():
        raise DeletionConflict('割接任务正在上报，请上报结束后删除')
    if conn.execute('''SELECT 1 FROM cutover_reports r JOIN cutover_tasks t ON t.id=r.task_id
        WHERE t.email_records_id=? AND r.status IN ('pending','running')''', (record['id'],)).fetchone():
        raise DeletionConflict('割接上报已进入队列或正在运行，请处理完成后删除')
    if conn.execute("SELECT 1 FROM mail_ai_jobs WHERE email_records_id=? AND status='running'", (record['id'],)).fetchone():
        raise DeletionConflict('邮件 AI 任务正在运行，请处理完成后删除')


def _remove_database_records(conn, email_id):
    record = conn.execute('SELECT subject,content FROM email_records WHERE id=?', (email_id,)).fetchone()
    conn.execute('''DELETE FROM rpa_report_jobs WHERE report_id IN (
        SELECT r.id FROM cutover_reports r JOIN cutover_tasks t ON t.id=r.task_id WHERE t.email_records_id=?)''', (email_id,))
    conn.execute('DELETE FROM cutover_reports WHERE task_id IN (SELECT id FROM cutover_tasks WHERE email_records_id=?)', (email_id,))
    conn.execute('DELETE FROM cutover_tasks WHERE email_records_id=?', (email_id,))
    conn.execute('DELETE FROM ticket_records WHERE email_records_id=?', (email_id,))
    conn.execute('DELETE FROM unconfigured_sample_cleanup WHERE email_records_id=?', (email_id,))
    conn.execute('DELETE FROM mail_ai_jobs WHERE email_records_id=?', (email_id,))
    conn.execute('DELETE FROM supplier_draft_samples WHERE email_records_id=?', (email_id,))
    for draft in conn.execute('SELECT id,draft_json FROM supplier_drafts WHERE source_email_records_id=?', (email_id,)).fetchall():
        value = _optional_json(draft['draft_json'], 'supplier_drafts.draft_json')
        if isinstance(value, dict):
            config = value.get('config')
            samples = config.get('email_type_samples') if isinstance(config, dict) else None
            if record:
                source = ((record['subject'] or '').strip(), (record['content'] or '').strip())
                if isinstance(samples, dict):
                    config['email_type_samples'] = {kind: sample for kind, sample in samples.items()
                        if not isinstance(sample, dict) or not any(source)
                        or (str(sample.get('subject') or '').strip(), str(sample.get('content') or '').strip()) != source}
            value['evidence'] = []
            questions = value.get('unresolved_questions') or []
            if not isinstance(questions, list):
                questions = [questions] if isinstance(questions, str) else []
            if record:
                # Remove provable copies of the deleted source, not unrelated review notes.
                questions = [question for question in questions
                    if not isinstance(question, str)
                    or not (source[1] and source[1] in question or source[0] and question.strip() == source[0])]
            notice = '来源邮件已删除，启用前请补充并审核新的割接通知样本。'
            value['unresolved_questions'] = questions if notice in questions else [*questions, notice]
            conn.execute('UPDATE supplier_drafts SET draft_json=? WHERE id=?',
                (json.dumps(value, ensure_ascii=False), draft['id']))
        else:
            # Invalid generated content cannot retain source text after its mail
            # is deleted. Keep the candidate and other samples for regeneration.
            conn.execute('UPDATE supplier_drafts SET draft_json=NULL WHERE id=?', (draft['id'],))
    conn.execute('''UPDATE supplier_drafts SET source_email_records_id=NULL,
        status=CASE WHEN draft_json IS NULL THEN 'collecting' ELSE status END,
        last_error='', revision=revision+1, update_time=CURRENT_TIMESTAMP WHERE source_email_records_id=?''', (email_id,))
    conn.execute('DELETE FROM email_records WHERE id=?', (email_id,))


def prepare_cutover_email_deletion(conn, data_dir, email_id, *, image_dir=None):
    """Stage a deletion in the caller's transaction, before any file removal."""
    root = Path(data_dir).resolve()
    image_root = Path(image_dir) if image_dir is not None else IMAGE_DIR
    deletion = conn.execute('SELECT * FROM mail_deletions WHERE email_records_id=?', (email_id,)).fetchone()
    if deletion and deletion['status'] == 'deleted':
        return
    if not deletion:
        record = conn.execute('SELECT * FROM email_records WHERE id=?', (email_id,)).fetchone()
        if not record:
            raise DeletionNotFound('割接邮件不存在')
        _reject_active(conn, record)
        manifest = _collect_manifest(conn, root, record)
        manifest.update(image_root=str(image_root), images=_collect_images(conn, image_root, record))
        conn.execute('''INSERT INTO mail_deletions
            (email_records_id,mailbox_address,email_uid,status,cleanup_manifest,create_time,update_time)
            VALUES (?,?,?,'pending_cleanup',?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)''',
            (email_id, (record['receiver'] or '').strip().casefold(), record['email_id'], json.dumps(manifest, ensure_ascii=False)))
    else:
        manifest = json.loads(deletion['cleanup_manifest'])
        if manifest != [] and manifest.get('root') != str(root):
            raise DeletionCleanupError('待清理文件的数据根目录已变化，请恢复目录后重试')
        if manifest != [] and manifest.get('image_root', str(image_root)) != str(image_root):
            raise DeletionCleanupError('待清理正文图片目录已变化，请恢复目录后重试')
        record = conn.execute('SELECT * FROM email_records WHERE id=?', (email_id,)).fetchone()
        if record:
            manifest = _collect_manifest(conn, root, record)
            manifest.update(image_root=str(image_root), images=_collect_images(conn, image_root, record))
            conn.execute('UPDATE mail_deletions SET cleanup_manifest=?,update_time=CURRENT_TIMESTAMP WHERE email_records_id=?',
                (json.dumps(manifest, ensure_ascii=False), email_id))


def delete_cutover_email(db, data_dir, email_id, *, image_dir=None):
    root = Path(data_dir).resolve()
    image_root = Path(image_dir) if image_dir is not None else IMAGE_DIR
    result = {'email_records_id':email_id, 'deleted':True}
    with db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        prepare_cutover_email_deletion(conn, root, email_id, image_dir=image_root)
        conn.commit()

    # Keep the row and manifest until files are gone. Failure leaves a retryable list entry.
    # The second write transaction also serializes simultaneous DELETE requests.
    with db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        deletion = conn.execute('SELECT * FROM mail_deletions WHERE email_records_id=?', (email_id,)).fetchone()
        if deletion['status'] == 'deleted':
            return result
        manifest = json.loads(deletion['cleanup_manifest'])
        if manifest == []:
            manifest = {'root':str(root), 'files':[], 'directories':[]}
        if manifest.get('root') != str(root):
            raise DeletionCleanupError('待清理文件的数据根目录已变化，请恢复目录后重试')
        if manifest.get('image_root', str(image_root)) != str(image_root):
            raise DeletionCleanupError('待清理正文图片目录已变化，请恢复目录后重试')
        shared_roots, shared_files = _shared_references(conn, root, email_id)
        for relative in manifest['files']:
            if not _is_shared(relative, shared_roots, shared_files):
                _safe_path(root, relative).unlink(missing_ok=True)
        for relative in manifest['directories']:
            if _is_shared(relative, shared_roots, shared_files):
                continue
            directory = _safe_path(root, relative)
            if directory.exists():
                remaining = list(directory.iterdir())
                if not remaining:
                    directory.rmdir()
                elif not all(_remaining_is_shared(root, path, shared_roots, shared_files) for path in remaining):
                    raise DeletionCleanupError('清理期间出现新的邮件文件，请重试')
        record = conn.execute('SELECT * FROM email_records WHERE id=?', (email_id,)).fetchone()
        if record:
            current_images = set(_collect_images(conn, image_root, record))
            for filename in manifest.get('images', []):
                if filename in current_images:
                    _image_path(image_root, filename, record['email_id']).unlink(missing_ok=True)
            if _collect_images(conn, image_root, record):
                raise DeletionCleanupError('清理期间出现新的邮件正文图片，请重试')
        if record and _collect_manifest(conn, root, record)['files']:
            raise DeletionCleanupError('清理期间出现新的邮件文件，请重试')
        _remove_database_records(conn, email_id)
        conn.execute("UPDATE mail_deletions SET status='deleted', cleanup_manifest='[]', update_time=CURRENT_TIMESTAMP WHERE email_records_id=?", (email_id,))
        conn.commit()
    return result
