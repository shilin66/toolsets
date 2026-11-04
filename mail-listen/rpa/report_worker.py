"""Entry point for an isolated report process; no credentials in argv."""
import json
import sys
from pathlib import Path

from user_access import UserAccessRepository
from .isolation import session_lock
from .report_jobs import finish_job, get_job
from .report_queue import LOGIN_ERRORS, pause_for_login
from .session_config import PortalSessionSettings
from .session_models import PortalEnvironment, PortalSessionError


def execute(db, data_dir, report_id, execute_callback):
    job = get_job(db, report_id)
    if not job:
        raise ValueError('上报任务不存在')
    settings = PortalSessionSettings.model_validate_json(job['settings_json'])
    with session_lock(settings.session_lock_path, blocking=True):
        job = get_job(db, report_id)
        if not job:
            return
        settings = PortalSessionSettings.model_validate_json(job['settings_json'])
        with db.get_connection() as conn:
            cursor = conn.execute("""UPDATE rpa_report_jobs SET status='running' WHERE report_id=? AND status='pending'
                AND NOT EXISTS (SELECT 1 FROM rpa_report_queues q
                    WHERE q.principal_key=rpa_report_jobs.principal_key AND q.login_required=1)""", (report_id,))
            conn.commit()
            if cursor.rowcount != 1:
                return
        task = json.loads(job['task_snapshot'])
        try:
            if job['principal_key'] == 'admin':
                raise PortalSessionError('ADMIN_RPA_FORBIDDEN', 'API Key 管理员不能上报，请由普通用户重新确认并提交')
            repo = UserAccessRepository(db)
            principal = repo.get_principal(job['user_id'])
            if not principal or not repo.can_access_email(principal, task['email_records_id'], operate=True):
                raise PortalSessionError('ACCESS_DENIED', '执行前检查失败：邮箱操作授权已撤销')
            with db.get_connection() as conn:
                current = conn.execute('SELECT version FROM portal_sessions WHERE principal_key=? AND environment=?',
                    (job['principal_key'], job['environment'])).fetchone()
            if not current or current['version'] != job['session_version']:
                raise PortalSessionError('SESSION_CHANGED', '任务绑定的登录会话已失效，请重新登录')
            if not Path(job['state_path']).is_file():
                raise PortalSessionError('LOGIN_REQUIRED', '综调登录会话文件已失效，请重新登录')
            for key in ('fill_payload', 'fill_result'):
                if isinstance(task.get(key), str):
                    task[key] = json.loads(task[key])
            execute_callback(task['id'], report_id, task['line_type'], PortalEnvironment(job['environment']),
                             task_snapshot=task, session_settings=settings)
        except PortalSessionError as error:
            if error.code in LOGIN_ERRORS:
                pause_for_login(db, report_id, error.code, str(error))
            else:
                db.update_cutover_report(report_id, status='failed', result={'phase': 'failed', 'note': str(error), 'error_code': error.code})
                db.update_cutover_task(task['id'], status='report_failed')
        finally:
            report = db.get_cutover_report(report_id)
            finish_job(db, report_id, (report or {}).get('status', 'interrupted'))


def main():
    import api_server
    api_server.DATA_DIR = Path(sys.argv[2])
    execute(api_server.email_db, api_server.DATA_DIR, int(sys.argv[1]), api_server._execute_cutover_report_job)


if __name__ == '__main__':
    main()
