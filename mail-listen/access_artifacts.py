"""Authorize file references against records, never against a caller's path alone."""

from pathlib import Path

from user_access import UserAccessRepository


def _reference_matches(reference, requested: str, data_dir: Path) -> bool:
    if not isinstance(reference, str):
        return False
    candidate = Path(reference)
    if candidate.is_absolute():
        try:
            reference = candidate.resolve().relative_to(data_dir.resolve()).as_posix()
        except ValueError:
            return False
    return reference == requested


def _screenshot_references(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {'screenshot_filename', 'screenshot_path', 'success_screenshot_path'} and isinstance(child, str):
                yield child
            elif isinstance(child, (list, dict)):
                yield from _screenshot_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from _screenshot_references(child)


def can_access_artifact(db, principal, endpoint, arguments, data_dir: Path) -> bool:
    requested = arguments.get('relative_path') or arguments.get('filename') or ''
    path = Path(requested)
    if not requested or path.is_absolute() or '..' in path.parts:
        return False
    if endpoint == 'download_email_attachment' and len(path.parts) == 4 and path.parts[:3] == (
            'email_attachments', 'preview-extract', principal.key):
        return True
    if endpoint == 'download_template_xlsx':
        return (len(path.parts) == 4 and path.parts[:3] == ('users', principal.key, 'templates')
                and path.name == path.name.strip() and path.name.endswith('.xlsx'))
    scope, params = UserAccessRepository.email_scope(principal)
    with db.get_connection() as conn:
        if endpoint == 'download_email_attachment':
            for row in conn.execute(f'SELECT attachments FROM email_records WHERE {scope}', params):
                if any(_reference_matches(value, requested, data_dir)
                       for value in db.deserialize_attachments(row['attachments'])):
                    return True
        elif endpoint == 'get_rpa_report_artifact':
            rows = conn.execute(f'''SELECT r.result FROM cutover_reports r
                JOIN cutover_tasks t ON t.id=r.task_id
                JOIN email_records ON email_records.id=t.email_records_id WHERE {scope}''', params)
            for row in rows:
                if any(_reference_matches(value, requested, data_dir)
                       for value in _screenshot_references(db._deserialize_json(row['result']))):
                    return True
        # Legacy HTML images have no persisted mailbox owner; never infer it from a UID.
    return False


def legacy_excel_unambiguous(db, task):
    with db.get_connection() as conn:
        rows = conn.execute('''SELECT DISTINCT lower(trim(e.receiver)) AS receiver FROM cutover_tasks t
            JOIN email_records e ON e.id=t.email_records_id WHERE t.customer_excel_filename=?''',
            (task.get('customer_excel_filename'),)).fetchall()
    return len(rows) == 1
