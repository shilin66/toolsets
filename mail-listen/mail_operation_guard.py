"""Coordinate synchronous mail mutations with local deletion in the API process."""

from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from weakref import WeakValueDictionary


class MailOperationConflict(ValueError):
    pass


_registry_lock = Lock()
_mail_locks = WeakValueDictionary()


def request_email_record_id(db, request):
    """Resolve only existing mail API identifiers; validation stays with each route."""
    if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
        return None
    if not request.path.startswith(('/api/cutover/', '/api/email/', '/api/tickets')):
        return None
    arguments = request.view_args or {}
    if 'email_records_id' in arguments:
        return arguments['email_records_id']
    if 'task_id' in arguments:
        task = db.get_cutover_task(arguments['task_id'])
        return task['email_records_id'] if task else None
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None
    try:
        if payload.get('email_records_id') is not None:
            return int(payload['email_records_id'])
        if payload.get('email_id') is not None:
            record = db.get_email_record(int(payload['email_id']))
            return record['id'] if record else None
    except (TypeError, ValueError):
        pass
    return None


@contextmanager
def guard_mail_operation(db, record_id, *, deleting=False, forwarding=False, reporting=False, allow_completed=False):
    if record_id is None:
        yield
        return
    # Forwarding can call this API back synchronously. Its database claim prevents
    # deletion; holding an API lock across the network call would block callbacks.
    if forwarding:
        if db.get_mail_deletion(record_id):
            raise MailOperationConflict('该邮件正在删除或已删除，无法继续处理')
        if (db.get_email_record_by_id(record_id) or {}).get('manual_completion'):
            raise MailOperationConflict('该割接任务已人工完成，不能继续修改或上报')
        yield
        return
    key = (str(Path(db.db_path).resolve()), record_id)
    with _registry_lock:
        lock = _mail_locks.get(key)
        if lock is None:
            lock = Lock()
            _mail_locks[key] = lock
    if not lock.acquire(blocking=reporting):
        raise MailOperationConflict('该邮件正在处理，请稍后重试')
    try:
        from rpa.isolation import session_lock
        from rpa.session_models import PortalSessionError
        lock_path = Path(db.db_path).resolve().parent / (Path(db.db_path).name + '.locks') / f'mail-{record_id}.lock'
        try:
            with session_lock(lock_path, blocking=reporting):
                if not deleting and db.get_mail_deletion(record_id):
                    raise MailOperationConflict('该邮件正在删除或已删除，无法继续处理')
                with db.get_connection() as conn:
                    if not deleting and not allow_completed and conn.execute(
                            'SELECT 1 FROM email_records WHERE id=? AND manual_completion IS NOT NULL', (record_id,)).fetchone():
                        raise MailOperationConflict('该割接任务已人工完成，不能继续修改或上报')
                    busy = conn.execute("SELECT 1 FROM cutover_tasks WHERE email_records_id=? AND status='reporting'", (record_id,)).fetchone()
                if busy and not deleting and not reporting:
                    raise MailOperationConflict('该邮件存在正在上报或待核对的任务，暂时不能修改')
                yield
        except PortalSessionError as error:
            raise MailOperationConflict('该邮件正在处理，请稍后重试') from error
    finally:
        lock.release()
