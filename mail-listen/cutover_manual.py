"""Audited local reconciliation; never submits to the external portal."""
import json
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

from mail_operation_guard import guard_mail_operation
from rpa.isolation import session_lock
from rpa.report_jobs import get_job, identity
from rpa.session_config import PortalSessionSettings


def _event(action, principal, note, **extra):
    return {'action': action, 'by': principal.username, 'at': datetime.now().astimezone().isoformat(),
            'note': note, **extra}


def _report_state(conn, report_id):
    report = dict(conn.execute('SELECT * FROM cutover_reports WHERE id=?', (report_id,)).fetchone())
    report.pop('manual_history', None)
    task = dict(conn.execute('SELECT * FROM cutover_tasks WHERE id=?', (report['task_id'],)).fetchone())
    job = conn.execute('SELECT status FROM rpa_report_jobs WHERE report_id=?', (report_id,)).fetchone()
    return {'report': report, 'task': task, 'job_status': job['status'] if job else None}


def _email_state(conn, email_id):
    tasks = [dict(row) for row in conn.execute('SELECT * FROM cutover_tasks WHERE email_records_id=? ORDER BY id', (email_id,))]
    reports = [_report_state(conn, row['id']) for row in conn.execute(
        'SELECT r.id FROM cutover_reports r JOIN cutover_tasks t ON t.id=r.task_id WHERE t.email_records_id=? ORDER BY r.id', (email_id,))]
    return {'tasks': tasks, 'reports': reports}


def _report_locks(locks, job):
    if job:
        root = Path(PortalSessionSettings.model_validate_json(job['settings_json']).session_lock_path).parent
        locks.enter_context(session_lock(root / 'binding.lock'))
        locks.enter_context(session_lock(root / 'activity.lock'))


def resolve_report(db, principal, report_id, resolution, note):
    report = db.get_cutover_report(report_id)
    task = db.get_cutover_task(report['task_id']) if report else None
    if not task:
        raise LookupError('上报记录不存在')
    job = get_job(db, report_id)
    with guard_mail_operation(db, task['email_records_id'], reporting=True, allow_completed=True), ExitStack() as locks:
        _report_locks(locks, job)
        with db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM cutover_reports WHERE id=?', (report_id,)).fetchone()
            if row['status'] not in ('pending', 'running', 'interrupted', 'failed') or (row['status'] == 'failed' and resolution != 'success'):
                raise ValueError('仅未结束、中断或失败的记录可以人工核对；失败记录只能标记已上报')
            if conn.execute('SELECT 1 FROM cutover_reports WHERE task_id=? AND id>?', (row['task_id'], report_id)).fetchone():
                raise ValueError('已有更新的上报记录，请处理最新记录，避免覆盖后续上报结果')
            before = _report_state(conn, report_id)
            original = json.loads(row['result'] or '{}')
            result = {**original, 'original_status': row['status'], 'original_result': original,
                      'phase': resolution, 'current_step': resolution,
                      'current_step_label': '人工核对：' + note, 'note': '人工核对：' + note,
                      'resolved_by': principal.username, 'resolved_at': datetime.now().astimezone().isoformat()}
            if job:
                result['execution_identity'] = identity(job)
            conn.execute('UPDATE cutover_reports SET status=?,result=? WHERE id=?',
                         (resolution, json.dumps(result, ensure_ascii=False), report_id))
            conn.execute("UPDATE cutover_tasks SET status=?,update_time=CURRENT_TIMESTAMP WHERE id=? AND status<>'completed'",
                         ('reported' if resolution == 'success' else 'report_failed', row['task_id']))
            conn.execute('UPDATE rpa_report_jobs SET status=? WHERE report_id=?', (resolution, report_id))
            event = _event('resolve', principal, note, before=before, after=_report_state(conn, report_id))
            event['at'] = result['resolved_at']
            history = json.loads(row['manual_history'] or '[]') + [event]
            conn.execute('UPDATE cutover_reports SET manual_history=? WHERE id=?', (json.dumps(history, ensure_ascii=False), report_id))
            conn.commit()
    return db.get_cutover_report(report_id)


def complete_email(db, principal, email_id, note):
    """Caller holds the mail mutation lock; completion and child statuses commit together."""
    with db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        email = conn.execute('SELECT * FROM email_records WHERE id=?', (email_id,)).fetchone()
        if not email:
            raise LookupError('邮件不存在')
        if email['manual_completion']:
            return json.loads(email['manual_completion'])
        busy = conn.execute("""SELECT 1 FROM cutover_reports r JOIN cutover_tasks t ON t.id=r.task_id
            WHERE t.email_records_id=? AND (r.status IN ('pending','running','paused','waiting_login','interrupted')
                OR EXISTS (SELECT 1 FROM rpa_report_jobs j WHERE j.report_id=r.id
                    AND j.status IN ('pending','running','paused','waiting_login','interrupted')))""", (email_id,)).fetchone()
        if busy:
            raise ValueError('存在排队、执行中或待核对的上报，请先处理这些记录后再标记完成')
        if email['reply_status'] in ('sending', 'send_uncertain') or email['api_forward_status'] == 'forwarding':
            raise ValueError('邮件正在处理或发送结果待核对，请处理结束后再标记完成')
        if conn.execute("SELECT 1 FROM mail_ai_jobs WHERE email_records_id=? AND status IN ('pending','running')", (email_id,)).fetchone():
            raise ValueError('邮件仍有后台处理任务，请处理结束后再标记完成')
        before = _email_state(conn, email_id)
        tasks = conn.execute('SELECT id,status,update_time FROM cutover_tasks WHERE email_records_id=?', (email_id,)).fetchall()
        audit = {'by': principal.username, 'at': datetime.now().astimezone().isoformat(), 'note': note,
                 'previous_task_statuses': {str(row['id']): row['status'] for row in tasks},
                 'previous_task_updated_at': {str(row['id']): row['update_time'] for row in tasks}}
        conn.execute('UPDATE email_records SET manual_completion=?,update_time=CURRENT_TIMESTAMP WHERE id=?',
                     (json.dumps(audit, ensure_ascii=False), email_id))
        conn.execute("UPDATE cutover_tasks SET status='completed',update_time=CURRENT_TIMESTAMP WHERE email_records_id=?", (email_id,))
        event = _event('complete', principal, note, before=before, after=_email_state(conn, email_id))
        event['at'] = audit['at']
        history = json.loads(email['manual_completion_history'] or '[]') + [event]
        conn.execute('UPDATE email_records SET manual_completion_history=? WHERE id=?', (json.dumps(history, ensure_ascii=False), email_id))
        conn.commit()
    return audit


def undo_report(db, principal, report_id, expected_at, note):
    report = db.get_cutover_report(report_id)
    task = db.get_cutover_task(report['task_id']) if report else None
    if not task:
        raise LookupError('上报记录不存在')
    with guard_mail_operation(db, task['email_records_id'], reporting=True, allow_completed=True), ExitStack() as locks:
        _report_locks(locks, get_job(db, report_id))
        with db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            current = _report_state(conn, report_id)
            result = json.loads(current['report']['result'] or '{}')
            if result.get('resolved_at') != expected_at or not result.get('resolved_by'):
                raise ValueError('人工标记已变更，请刷新后重试')
            if result.get('original_status') not in ('failed', 'interrupted'):
                raise ValueError('原任务可能已执行，不能恢复为自动排队；请人工核对结果')
            if conn.execute('SELECT 1 FROM cutover_reports WHERE task_id=? AND id>?', (task['id'], report_id)).fetchone():
                raise ValueError('已有更新的上报记录，不能撤销旧标记')
            history = json.loads(conn.execute('SELECT manual_history FROM cutover_reports WHERE id=?', (report_id,)).fetchone()[0])
            mark = next((event for event in reversed(history) if event['action']=='resolve' and event['at']==expected_at), None)
            if mark:
                if mark['after'] != current:
                    raise ValueError('标记后任务已变更，请先撤销后续人工操作，避免覆盖新结果')
                before = mark['before']
            else:
                # Compatibility with marks saved before undo snapshots were introduced.
                completion = conn.execute('SELECT manual_completion FROM email_records WHERE id=?', (task['email_records_id'],)).fetchone()[0]
                if completion and json.loads(completion)['at'] > expected_at:
                    raise ValueError('请先撤销整封邮件的已完成标记')
                if task['status'] not in ('reported', 'report_failed', 'completed') or not isinstance(result.get('original_result'), dict):
                    raise ValueError('任务状态已变更或缺少原始结果，不能撤销')
                before = json.loads(json.dumps(current))
                before['report'].update(status=result['original_status'], result=json.dumps(result['original_result'], ensure_ascii=False), completed_at=None)
                if task['status'] != 'completed':
                    before['task']['status'] = 'report_failed' if result['original_status']=='failed' else 'reporting'
                before['job_status'] = result['original_status'] if current['job_status'] is not None else None
                history.append({'action':'resolve','by':result['resolved_by'],'at':expected_at,'note':result.get('note','')})
            original = before['report']
            conn.execute('UPDATE cutover_reports SET status=?,result=?,completed_at=? WHERE id=?',
                         (original['status'], original['result'], original['completed_at'], report_id))
            conn.execute('UPDATE cutover_tasks SET status=?,update_time=? WHERE id=?',
                         (before['task']['status'], before['task']['update_time'], task['id']))
            if before['job_status'] is not None:
                conn.execute('UPDATE rpa_report_jobs SET status=? WHERE report_id=?', (before['job_status'], report_id))
            history.append(_event('undo_resolve', principal, note, target_at=expected_at))
            conn.execute('UPDATE cutover_reports SET manual_history=? WHERE id=?', (json.dumps(history, ensure_ascii=False), report_id))
            conn.commit()
    return db.get_cutover_report(report_id)


def undo_completion(db, principal, email_id, expected_at, note):
    """Caller holds the mail mutation lock. Does not wake any report queue."""
    with db.get_connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        email = conn.execute('SELECT * FROM email_records WHERE id=?', (email_id,)).fetchone()
        if not email:
            raise LookupError('邮件不存在')
        audit = json.loads(email['manual_completion'] or '{}')
        if audit.get('at') != expected_at:
            raise ValueError('完成标记已变更，请刷新后重试')
        history = json.loads(email['manual_completion_history'] or '[]')
        mark = next((event for event in reversed(history) if event['action']=='complete' and event['at']==expected_at), None)
        current = _email_state(conn, email_id)
        if mark:
            if current != mark['after']:
                raise ValueError('完成后已有其他处理，请先撤销后续人工操作，避免覆盖新结果')
            tasks = mark['before']['tasks']
        else:
            previous = audit.get('previous_task_statuses', {})
            if set(previous) != {str(row['id']) for row in current['tasks']} or any(row['status']!='completed' for row in current['tasks']):
                raise ValueError('子任务已变更，不能撤销完成标记')
            if any((json.loads(row['report']['result'] or '{}').get('resolved_at') or '') > expected_at for row in current['reports']):
                raise ValueError('请先撤销完成后的人工上报标记')
            tasks = [{**row, 'status':previous[str(row['id'])],
                      'update_time':audit.get('previous_task_updated_at', {}).get(str(row['id']), row['update_time'])} for row in current['tasks']]
            history.append({'action':'complete','by':audit['by'],'at':audit['at'],'note':audit['note']})
        for task in tasks:
            conn.execute('UPDATE cutover_tasks SET status=?,update_time=? WHERE id=?', (task['status'], task['update_time'], task['id']))
        history.append(_event('undo_complete', principal, note, target_at=expected_at))
        conn.execute('UPDATE email_records SET manual_completion=NULL,manual_completion_history=? WHERE id=?',
                     (json.dumps(history, ensure_ascii=False), email_id))
        conn.commit()
    return {'manual_completion': None, 'manual_completion_history': db.public_manual_history(json.dumps(history))}
