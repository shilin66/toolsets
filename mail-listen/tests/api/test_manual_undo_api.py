import json
import unittest
from tests.api import test_cutover_manual_completion_api as fixtures


class ManualUndoApiTest(unittest.TestCase):
    setUp = fixtures.ManualCompletionApiTest.setUp
    post = fixtures.ManualCompletionApiTest.post

    def mark_report(self):
        self.assertEqual(self.post(self.resolve, {'resolution':'success','note':'已核对'}).status_code, 200)
        return self.api.db.get_cutover_report(self.rid)['result']['resolved_at']

    def mark_complete(self):
        response = self.post(self.complete, {'note':'人工完成'})
        self.assertEqual(response.status_code, 200)
        return response.get_json()['data']['at']

    def undo_report(self, token):
        return self.post(self.resolve + '/undo', {'expected_at':token, 'note':'误操作，撤销'})

    def undo_complete(self, token):
        return self.post(self.complete + '/undo', {'expected_at':token, 'note':'误操作，恢复处理'})

    def test_report_undo_restores_result_task_and_statistics_and_keeps_audit(self):
        before = self.api.db.get_cutover_report(self.rid)
        task = self.api.db.get_cutover_task(self.tasks[0]['id'])
        token = self.mark_report()
        self.assertEqual(self.undo_report(token).status_code, 200)
        after = self.api.db.get_cutover_report(self.rid)
        for key in ('status','result','completed_at'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.api.db.get_cutover_task(task['id']), task)
        self.assertEqual([event['action'] for event in after['manual_history']], ['resolve','undo_resolve'])
        self.assertEqual(after['manual_history'][-1]['by'], 'operator')
        self.assertEqual(self.undo_report(token).status_code, 409)
        token2 = self.mark_report()
        self.assertEqual(self.undo_report(token).status_code, 409)
        self.assertEqual(self.undo_report(token2).status_code, 200)

    def test_completion_undo_restores_each_child_and_allows_editing(self):
        before = [self.api.db.get_cutover_task(t['id']) for t in self.tasks]
        token = self.mark_complete()
        self.assertEqual(self.undo_complete(token).status_code, 200)
        self.assertEqual([self.api.db.get_cutover_task(t['id']) for t in self.tasks], before)
        detail = self.api.report_client.get(f'/api/cutover/emails/{self.api.email_records_id}').get_json()['data']
        self.assertIsNone(detail['manual_completion'])
        self.assertEqual([e['action'] for e in detail['manual_completion_history']], ['complete','undo_complete'])
        self.assertEqual(self.post(f'/api/cutover/tasks/{self.tasks[1]["id"]}/confirm', {}).status_code, 200)
        self.assertEqual(self.undo_complete(token).status_code, 409)

    def test_later_report_or_edit_prevents_undo(self):
        token = self.mark_report()
        self.api.db.update_cutover_task(self.tasks[0]['id'], status='draft')
        self.assertEqual(self.undo_report(token).status_code, 409)
        self.api.db.add_cutover_report(self.tasks[0]['id'], 'customer', 'pending', {})
        self.assertEqual(self.undo_report(token).status_code, 409)

    def test_nested_marks_must_be_undone_in_reverse_order(self):
        report_token = self.mark_report()
        completion_token = self.mark_complete()
        self.assertEqual(self.undo_report(report_token).status_code, 409)
        self.assertEqual(self.undo_complete(completion_token).status_code, 200)
        self.assertEqual(self.undo_report(report_token).status_code, 200)
        completion_token = self.mark_complete()
        report_token = self.mark_report()
        self.assertEqual(self.undo_complete(completion_token).status_code, 409)
        self.assertEqual(self.undo_report(report_token).status_code, 200)
        self.assertEqual(self.undo_complete(completion_token).status_code, 200)

    def test_existing_marks_without_new_history_can_be_undone(self):
        original = {'original_status':'failed','original_result':self.original,'resolved_by':'operator',
                    'resolved_at':'2026-11-05T10:00:00+08:00','phase':'success'}
        self.api.db.update_cutover_report(self.rid, status='success', result=original)
        self.api.db.update_cutover_task(self.tasks[0]['id'], status='reported')
        self.assertEqual(self.undo_report(original['resolved_at']).status_code, 200)
        token = self.mark_complete()
        with self.api.db.get_connection() as conn:
            conn.execute("UPDATE email_records SET manual_completion_history='[]' WHERE id=?", (self.api.email_records_id,))
            conn.commit()
        self.assertEqual(self.undo_complete(token).status_code, 200)
        self.assertEqual(self.api.db.get_cutover_task(self.tasks[0]['id'])['status'], 'report_failed')

    def test_undo_requires_note_token_and_operation_permission(self):
        token = self.mark_report()
        self.assertEqual(self.post(self.resolve+'/undo', {'note':'撤销'}).status_code, 400)
        completion = self.mark_complete()
        account = self.api.db.list_mail_accounts()[0]['id']
        self.api.access_repo.set_grants(self.api.operator['id'], [{'account_id':account,'can_operate':False}])
        self.assertEqual(self.undo_report(token).status_code, 403)
        self.assertEqual(self.undo_complete(completion).status_code, 403)

    def test_queue_undo_restores_failed_job_and_is_blocked_by_live_worker(self):
        from unittest.mock import patch
        from rpa.report_jobs import finish_job, get_job
        from rpa.isolation import session_lock
        task = self.tasks[1]
        self.api.db.update_cutover_task(task['id'], status='confirmed')
        with patch.object(fixtures.fixtures.api_server, 'submit_cutover_report_job'):
            rid = self.post(f'/api/cutover/tasks/{task["id"]}/report', {}).get_json()['data']['report_id']
        self.api.db.update_cutover_report(rid, status='failed', result=self.original)
        self.api.db.update_cutover_task(task['id'], status='report_failed')
        finish_job(self.api.db, rid, 'failed')
        self.assertEqual(self.post(f'/api/cutover/reports/{rid}/resolve', {'resolution':'success','note':'已核对'}).status_code, 200)
        token = self.api.db.get_cutover_report(rid)['result']['resolved_at']
        path = f'/api/cutover/reports/{rid}/resolve/undo'
        with session_lock(self.api.session_service.lock_path):
            self.assertEqual(self.post(path, {'expected_at':token,'note':'误操作'}).status_code, 409)
            self.assertEqual(get_job(self.api.db, rid)['status'], 'success')
        with patch.object(fixtures.fixtures.api_server, 'submit_cutover_report_job') as schedule:
            self.assertEqual(self.post(path, {'expected_at':token,'note':'误操作'}).status_code, 200)
            schedule.assert_not_called()
        self.assertEqual(get_job(self.api.db, rid)['status'], 'failed')

    def test_restart_preserves_undo_snapshots(self):
        from database import EmailDatabase
        token = self.mark_report()
        EmailDatabase(self.api.db.db_path)
        self.assertEqual(self.undo_report(token).status_code, 200)
        token = self.mark_complete()
        EmailDatabase(self.api.db.db_path)
        self.assertEqual(self.undo_complete(token).status_code, 200)
