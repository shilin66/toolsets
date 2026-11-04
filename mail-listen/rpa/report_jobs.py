"""Durable report claims with immutable identity and payload."""
import json
import os
import signal
import shutil
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path

from loguru import logger

from user_access import UserAccessRepository
from .isolation import session_lock
from .session_models import PortalSessionError


def identity(binding):
    return {key: binding[key] for key in (
        'principal_key', 'username', 'environment', 'session_version', 'workbench_username')}


def report_result_with_username(conn, result):
    """Resolve old principal IDs for display without rewriting historical records."""
    if not isinstance(result, dict) or not isinstance(result.get('execution_identity'), dict):
        return result
    public = dict(result['execution_identity'])
    if not public.get('workbench_username'):
        key = public.get('principal_key', '')
        row = conn.execute("SELECT username FROM app_users WHERE 'user-' || id = ?", (key,)).fetchone()
        public['workbench_username'] = 'admin' if key == 'admin' else row['username'] if row else None
    return {**result, 'execution_identity': public}


def claim_report(db, principal, service, task_id, environment, data_dir, expected_version=None):
    if principal.is_admin:
        raise PortalSessionError('ADMIN_RPA_FORBIDDEN', '综调上报仅限普通用户账号使用')
    with session_lock(service.binding_lock_path, blocking=True):
        binding = service.report_binding(environment)
        if expected_version is not None and binding['version'] != expected_version:
            raise PortalSessionError('SESSION_CHANGED', '综调登录账号已变更，请刷新并确认后重新提交')
        scope, params = UserAccessRepository.email_scope(principal, 'e', operate=True)
        with db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            task = conn.execute(f'''SELECT t.* FROM cutover_tasks t JOIN email_records e
                ON e.id=t.email_records_id WHERE t.id=? AND {scope}
                AND NOT EXISTS (SELECT 1 FROM mail_deletions d WHERE d.email_records_id=e.id)''', [task_id, *params]).fetchone()
            if not task:
                raise PortalSessionError('ACCESS_DENIED', '任务不存在或邮箱操作授权已撤销')
            if task['status'] not in ('confirmed', 'report_failed'):
                raise PortalSessionError('TASK_BUSY', '任务状态已变更或已经提交，请刷新后重试')
            # Login binding cannot change while the principal binding lock is held.
            public = {'principal_key': principal.key, 'workbench_username': principal.username,
                      'username': binding['username'],
                      'environment': str(environment), 'session_version': binding['version']}
            result = {'phase': 'queued', 'current_step': 'queued', 'current_step_label': '已进入上报队列',
                      'note': '已进入上报队列', 'operation_log': [], 'execution_identity': public}
            cursor = conn.execute('INSERT INTO cutover_reports(task_id,report_type,status,result) VALUES (?,?,?,?)',
                (task_id, task['line_type'], 'pending', json.dumps(result, ensure_ascii=False)))
            report_id = cursor.lastrowid
            snapshot = dict(task)
            if task['line_type'] == 'customer':
                from access_artifacts import legacy_excel_unambiguous
                from mail_artifacts import customer_excel_path, message_storage_directory
                email = conn.execute('SELECT receiver,email_id FROM email_records WHERE id=?', (task['email_records_id'],)).fetchone()
                source = customer_excel_path(Path(data_dir), mailbox_address=email['receiver'],
                    email_uid=email['email_id'], filename=task['customer_excel_filename'])
                if not source.is_file():
                    if not legacy_excel_unambiguous(db, snapshot):
                        raise PortalSessionError('EXCEL_AMBIGUOUS', '历史 Excel 文件归属不明确，请重新生成后确认任务')
                    source = Path(data_dir) / Path(task['customer_excel_filename']).name
                if not source.is_file():
                    raise PortalSessionError('EXCEL_MISSING', '上报 Excel 不存在，请重新生成后确认任务')
                target = message_storage_directory(Path(data_dir).resolve(), mailbox_address=email['receiver'],
                    email_uid=email['email_id']) / 'cutover' / 'report-inputs' / str(report_id) / 'customer.xlsx'
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                shutil.copyfile(source, target)
                os.chmod(target, 0o600)
                snapshot['_report_excel_path'] = str(target)
            # Store the raw DB row so JSON fields are decoded exactly once in the worker.
            conn.execute('''INSERT INTO rpa_report_jobs(report_id,principal_key,user_id,username,environment,
                session_version,state_path,task_snapshot,settings_json) VALUES (?,?,?,?,?,?,?,?,?)''',
                (report_id, principal.key, principal.user_id, binding['username'], str(environment),
                 binding['version'], binding['state_path'], json.dumps(snapshot, default=str), binding['settings_json']))
            conn.execute("UPDATE cutover_tasks SET status='reporting' WHERE id=?", (task_id,))
            conn.commit()
            return report_id, result


def get_job(db, report_id):
    with db.get_connection() as conn:
        row = conn.execute('''SELECT j.*, r.result AS report_result FROM rpa_report_jobs j
            JOIN cutover_reports r ON r.id=j.report_id WHERE j.report_id=?''', (report_id,)).fetchone()
        if not row:
            return None
        job = dict(row)
        result = json.loads(job.pop('report_result') or '{}')
        result = report_result_with_username(conn, {
            'execution_identity': {**(result.get('execution_identity') or {}), 'principal_key': job['principal_key']}})
        job['workbench_username'] = result['execution_identity']['workbench_username']
        return job


def finish_job(db, report_id, status):
    with db.get_connection() as conn:
        conn.execute('UPDATE rpa_report_jobs SET status=? WHERE report_id=?', (status, report_id))
        conn.commit()


def _finish_process_failure(db, report_id, *, outcome_unknown, pending_only=False):
    """Do not overwrite a manual resolution or a newer attempt during cleanup."""
    with db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('''SELECT r.*, j.status AS job_status FROM cutover_reports r
            JOIN rpa_report_jobs j ON j.report_id=r.id WHERE r.id=?''', (report_id,)).fetchone()
        if not row or row['job_status'] not in ('pending', 'running') or row['status'] not in ('pending', 'running'):
            return False
        if pending_only and (row['job_status'] != 'pending' or row['status'] != 'pending'):
            return False
        status = 'interrupted' if outcome_unknown else 'failed'
        note = ('执行进程中断，提交结果未知。请核对综调系统后处理，禁止直接重试。'
                if outcome_unknown else '执行进程未能启动，请检查服务日志后重试')
        result = {**(json.loads(row['result']) if row['result'] else {}), 'phase': status, 'note': note,
                  'current_step': status, 'current_step_label': '结果待核对' if outcome_unknown else note}
        conn.execute('UPDATE cutover_reports SET status=?,result=? WHERE id=?',
                     (status, json.dumps(result, ensure_ascii=False), report_id))
        conn.execute('UPDATE rpa_report_jobs SET status=? WHERE report_id=?', (status, report_id))
        if not outcome_unknown:
            conn.execute("""UPDATE cutover_tasks SET status='report_failed' WHERE id=? AND status='reporting'
                AND NOT EXISTS (SELECT 1 FROM cutover_reports WHERE task_id=? AND id>?)""",
                (row['task_id'], row['task_id'], report_id))
        conn.commit()
        return True


def run_report_queue(db, data_dir, report_id):
    """One runner per user drains durable jobs in submission order on this host."""
    from .report_queue import login_required
    job = get_job(db, report_id)
    if not job:
        return
    root = Path(data_dir) / 'rpa' / 'users' / job['principal_key']
    with ExitStack() as queue_lock:
        with session_lock(root / 'binding.lock', blocking=True):
            try:
                queue_lock.enter_context(session_lock(root / 'report-queue.lock'))
            except PortalSessionError as error:
                if error.code != 'RPA_BUSY':
                    raise
                # The current runner will pick up this user's newly committed jobs.
                return
        while True:
            with session_lock(root / 'binding.lock', blocking=True):
                with db.get_connection() as conn:
                    pending = None if login_required(conn, job['principal_key']) else conn.execute('''SELECT report_id FROM rpa_report_jobs
                        WHERE principal_key=? AND status='pending' ORDER BY report_id LIMIT 1''',
                        (job['principal_key'],)).fetchone()
                if not pending:
                    # Release before allowing a new claim/wakeup, so no job is stranded
                    # between our final empty check and releasing the runner lock.
                    queue_lock.close()
                    return
            next_id = pending['report_id']
            try:
                run_report_process(db, data_dir, next_id)
            except Exception:
                logger.exception('上报执行进程异常: report_id={}', next_id)
                _finish_process_failure(db, next_id, outcome_unknown=True)


def run_report_process(db, data_dir, report_id):
    """Each report has its own Python/Playwright/browser process tree."""
    if (get_job(db, report_id) or {}).get('status') != 'pending':
        return
    env = {**os.environ, 'MAIL_DATABASE_PATH': str(Path(db.db_path).resolve())}
    try:
        process = subprocess.Popen([sys.executable, '-m', 'rpa.report_worker', str(report_id), str(Path(data_dir).resolve())],
                                   cwd=Path(__file__).resolve().parent.parent, env=env, start_new_session=True)
    except OSError:
        _finish_process_failure(db, report_id, outcome_unknown=False)
        return
    try:
        code = process.wait(timeout=30 * 60)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        code = -1
    report = db.get_cutover_report(report_id)
    if report and (code != 0 or report['status'] == 'running'):
        # Unknown remote outcome must not be automatically retried.
        # A clean worker can leave a pending job after pause/resume or reauthentication.
        _finish_process_failure(db, report_id, outcome_unknown=True)

