"""Persistent controls and recovery for personal report queues."""
import json
from contextlib import ExitStack
from pathlib import Path

from user_access import UserAccessRepository
from .isolation import session_lock
from .session_models import PortalSessionError


LOGIN_ERRORS = frozenset({'RPA_SESSION_REQUIRED', 'LOGIN_REQUIRED', 'SESSION_CHANGED',
                          'RPA_SESSION_REQUIRED_AFTER_SUBMIT'})
WAITING_NOTE = '登录失效，当前用户的队列已暂停，重新登录后自动继续'


def login_required(conn, principal_key):
    return bool(conn.execute('SELECT 1 FROM rpa_report_queues WHERE principal_key=? AND login_required=1',
                             (principal_key,)).fetchone())


def _set_state(conn, row, status, note):
    result = json.loads(row['result'] or '{}')
    result.update(phase=status, current_step=status, current_step_label=note, note=note)
    if status == 'pending':
        result.pop('error', None)
        result.pop('error_code', None)
    conn.execute('UPDATE cutover_reports SET status=?,result=? WHERE id=?',
                 (status, json.dumps(result, ensure_ascii=False), row['report_id']))
    conn.execute('UPDATE rpa_report_jobs SET status=? WHERE report_id=?', (status, row['report_id']))
    task_status = {'success': 'reported', 'failed': 'report_failed'}.get(status, 'reporting')
    conn.execute('UPDATE cutover_tasks SET status=? WHERE id=?', (task_status, row['task_id']))


def pause_for_login(db, report_id, error_code, message):
    with db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        job = conn.execute('SELECT * FROM rpa_report_jobs WHERE report_id=?', (report_id,)).fetchone()
        if not job or job['status'] not in ('pending', 'running'):
            return False
        conn.execute('INSERT INTO rpa_report_queues VALUES (?,1) ON CONFLICT(principal_key) '
                     'DO UPDATE SET login_required=1', (job['principal_key'],))
        rows = conn.execute('''SELECT j.report_id,r.task_id,r.result FROM rpa_report_jobs j
            JOIN cutover_reports r ON r.id=j.report_id
            WHERE j.principal_key=? AND (j.status='pending' OR j.report_id=?)''',
            (job['principal_key'], report_id)).fetchall()
        for row in rows:
            uncertain = row['report_id'] == report_id and error_code == 'RPA_SESSION_REQUIRED_AFTER_SUBMIT'
            if row['report_id'] == report_id:
                result = {**json.loads(row['result'] or '{}'), 'error_code': error_code,
                          'last_error_code': error_code, 'last_error': message}
                row = {**dict(row), 'result': json.dumps(result, ensure_ascii=False)}
            _set_state(conn, row, 'interrupted' if uncertain else 'waiting_login',
                       '结果待核对' if uncertain else WAITING_NOTE)
        conn.commit()
        return True


def rebind_waiting_jobs(conn, principal_key, username, environment, version, state_path, settings_json):
    """Called inside the successful login transaction while binding/activity locks are held."""
    rows = conn.execute('''SELECT j.report_id,j.status,r.task_id,r.result FROM rpa_report_jobs j
        JOIN cutover_reports r ON r.id=j.report_id WHERE j.principal_key=?
        AND j.status IN ('pending','paused','waiting_login')''', (principal_key,)).fetchall()
    if conn.execute('''SELECT 1 FROM rpa_report_jobs WHERE principal_key=?
        AND status IN ('pending','paused','waiting_login') AND (LOWER(username)<>LOWER(?) OR environment<>?)''',
        (principal_key, username, environment)).fetchone():
        raise PortalSessionError('QUEUE_IDENTITY_MISMATCH', '请使用队列原有的综调账号和环境重新登录')
    for row in rows:
        result = json.loads(row['result'] or '{}')
        result['execution_identity'] = {**result.get('execution_identity', {}), 'session_version': version}
        conn.execute('UPDATE cutover_reports SET result=? WHERE id=?',
                     (json.dumps(result, ensure_ascii=False), row['report_id']))
        conn.execute('''UPDATE rpa_report_jobs SET session_version=?,state_path=?,settings_json=?
            WHERE report_id=?''', (version, str(state_path), settings_json, row['report_id']))
        if row['status'] == 'waiting_login':
            _set_state(conn, {**dict(row), 'result': json.dumps(result)}, 'pending', '已重新登录，等待自动上报')
    conn.execute('DELETE FROM rpa_report_queues WHERE principal_key=?', (principal_key,))


def change_report_pause(db, data_dir, principal, report_id, paused):
    from .report_jobs import get_job
    job = get_job(db, report_id)
    if not job:
        raise PortalSessionError('TASK_BUSY', '上报任务不存在')
    if not principal.is_admin and job['principal_key'] != principal.key:
        raise PortalSessionError('ACCESS_DENIED', '只能暂停或继续自己提交的上报任务')
    root = Path(data_dir) / 'rpa' / 'users' / job['principal_key']
    with session_lock(root / 'binding.lock', blocking=True), db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('''SELECT j.report_id,j.status,r.task_id,r.result,t.email_records_id
            FROM rpa_report_jobs j JOIN cutover_reports r ON r.id=j.report_id
            JOIN cutover_tasks t ON t.id=r.task_id WHERE j.report_id=?''', (report_id,)).fetchone()
        if not row or not UserAccessRepository(db).can_access_email(principal, row['email_records_id'], operate=True):
            raise PortalSessionError('ACCESS_DENIED', '任务不存在或邮箱操作权限已撤销')
        if row['status'] not in ('pending', 'paused', 'waiting_login'):
            raise PortalSessionError('TASK_BUSY', '只能暂停尚未开始的任务；执行中的任务请等待结果')
        status = 'paused' if paused else 'waiting_login' if login_required(conn, job['principal_key']) else 'pending'
        note = {'paused': '任务已暂停，点击继续上报后恢复', 'waiting_login': WAITING_NOTE,
                'pending': '已进入上报队列，等待自动上报'}[status]
        _set_state(conn, row, status, note)
        conn.commit()
    return db.get_cutover_report(report_id)


def recover_report_jobs(db, data_dir, schedule, *, principals=None):
    """Reconcile only abandoned workers. Return users whose live orphan worker must finish first."""
    if principals is None:
        with db.get_connection() as conn:
            principals = [r[0] for r in conn.execute("SELECT DISTINCT principal_key FROM rpa_report_jobs WHERE status IN ('pending','running')")]
    deferred = []
    for principal_key in principals:
        root = Path(data_dir) / 'rpa' / 'users' / principal_key
        with ExitStack() as locks:
            try:
                locks.enter_context(session_lock(root / 'binding.lock'))
            except PortalSessionError:
                deferred.append(principal_key)
                continue
            try:
                locks.enter_context(session_lock(root / 'report-queue.lock'))
            except PortalSessionError:
                # A newly started queue may be waiting on an old orphan worker.
                # Recheck after it finishes so abandoned running records aren't missed.
                deferred.append(principal_key)
                continue
            try:
                locks.enter_context(session_lock(root / 'activity.lock'))
            except PortalSessionError:
                deferred.append(principal_key)
                continue
            with db.get_connection() as conn:
                conn.execute('BEGIN IMMEDIATE')
                rows = conn.execute('''SELECT j.report_id,r.task_id,r.status,r.result FROM rpa_report_jobs j
                    JOIN cutover_reports r ON r.id=j.report_id WHERE j.principal_key=? AND j.status='running' ''',
                    (principal_key,)).fetchall()
                for row in rows:
                    status = row['status'] if row['status'] in ('success','failed','waiting_login','paused','interrupted') else 'interrupted'
                    if status == 'interrupted':
                        _set_state(conn, row, status, '结果待核对')
                    else:
                        conn.execute('UPDATE rpa_report_jobs SET status=? WHERE report_id=?', (status, row['report_id']))
                        conn.execute('UPDATE cutover_tasks SET status=? WHERE id=?',
                            ({'success':'reported','failed':'report_failed'}.get(status, 'reporting'), row['task_id']))
                pending = None if login_required(conn, principal_key) else conn.execute(
                    "SELECT report_id FROM rpa_report_jobs WHERE principal_key=? AND status='pending' ORDER BY report_id LIMIT 1",
                    (principal_key,)).fetchone()
                conn.commit()
        if pending:
            try:
                schedule(pending['report_id'])
            except RuntimeError:
                deferred.append(principal_key)
    return deferred
