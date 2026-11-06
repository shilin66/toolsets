import unittest
from copy import deepcopy

from tests.api import test_cutover_task_api as fixtures


class ManualCompletionApiTest(unittest.TestCase):
    def setUp(self):
        self.api = fixtures.CutoverTaskApiTest()
        self.api.setUp()
        self.addCleanup(self.api.tearDown)
        self.tasks = self.api.fill_tasks(self.api.post_fill_mixed(self.api.mixed_fill_payload()))
        self.original = {'phase': 'failed', 'note': '原始异常说明', 'error': '提交超时',
                         'error_code': 'TIMEOUT', 'operation_log': [{'label': '提交', 'screenshot': 'original.png'}]}
        self.rid = self.api.db.add_cutover_report(self.tasks[0]['id'], 'customer', 'failed', deepcopy(self.original))
        self.api.db.update_cutover_task(self.tasks[0]['id'], status='report_failed')
        self.resolve = f'/api/cutover/reports/{self.rid}/resolve'
        self.complete = f'/api/cutover/emails/{self.api.email_records_id}/complete'

    def post(self, path, body):
        return self.api.report_client.post(path, json=body, headers=self.api.report_headers)

    def test_failed_legacy_report_can_be_marked_reported_without_losing_evidence(self):
        response = self.post(self.resolve, {'resolution': 'success', 'note': '已在综调核对单号 123'})
        self.assertEqual(response.status_code, 200, response.get_json())
        report = self.api.db.get_cutover_report(self.rid)
        self.assertEqual(report['status'], 'success')
        self.assertEqual(report['result']['original_result'], self.original)
        for key in ('error', 'error_code', 'operation_log'):
            self.assertEqual(report['result'][key], self.original[key])
        self.assertEqual(report['result']['resolved_by'], 'operator')
        self.assertTrue(report['result']['resolved_at'])
        self.assertEqual(self.api.db.get_cutover_task(self.tasks[0]['id'])['status'], 'reported')

    def test_old_failed_attempt_cannot_override_a_newer_attempt(self):
        self.api.db.add_cutover_report(self.tasks[0]['id'], 'customer', 'pending', {})
        response = self.post(self.resolve, {'resolution': 'success', 'note': '已核对'})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.api.db.get_cutover_report(self.rid)['status'], 'failed')

    def test_complete_entire_email_preserves_reports_and_records_actor_and_reason(self):
        before = self.api.db.get_cutover_report(self.rid)
        response = self.post(self.complete, {'note': '已人工处理全部线路'})
        self.assertEqual(response.status_code, 200, response.get_json())
        for task in self.tasks:
            self.assertEqual(self.api.db.get_cutover_task(task['id'])['status'], 'completed')
        self.assertEqual(self.api.db.get_cutover_report(self.rid), before)
        detail = self.api.report_client.get(f'/api/cutover/emails/{self.api.email_records_id}').get_json()['data']
        self.assertEqual(detail['manual_completion']['by'], 'operator')
        self.assertEqual(detail['manual_completion']['note'], '已人工处理全部线路')
        self.assertEqual(detail['manual_completion']['previous_task_statuses'][str(self.tasks[0]['id'])], 'report_failed')
        self.assertEqual(self.post(self.complete, {'note': '重复请求'}).status_code, 200)
        listed = self.api.report_client.get('/api/cutover/emails?status=completed').get_json()['data']
        self.assertEqual(listed['total'], 1)
        self.assertEqual(listed['items'][0]['manual_completion'], detail['manual_completion'])
        self.assertEqual(self.post(f'/api/cutover/tasks/{self.tasks[1]["id"]}/confirm', {}).status_code, 409)
        self.assertEqual(self.post(self.resolve, {'resolution': 'success', 'note': '核对已上报'}).status_code, 200)
        self.assertEqual(self.api.db.get_cutover_task(self.tasks[0]['id'])['status'], 'completed')

    def test_completion_requires_note_and_operation_permission(self):
        self.assertEqual(self.post(self.complete, {'note': '  '}).status_code, 400)
        self.api.access_repo.set_grants(self.api.operator['id'], [])
        self.assertEqual(self.post(self.complete, {'note': '完成'}).status_code, 404)
        self.assertEqual(self.post(self.resolve, {'resolution': 'success', 'note': '核对'}).status_code, 404)

    def test_active_or_uncertain_reports_block_completion_atomically(self):
        for status in ('pending', 'running', 'paused', 'waiting_login', 'interrupted'):
            with self.subTest(status=status):
                self.api.db.update_cutover_report(self.rid, status=status)
                response = self.post(self.complete, {'note': '完成'})
                self.assertEqual(response.status_code, 409, response.get_json())
                self.assertEqual(self.api.db.get_cutover_task(self.tasks[1]['id'])['status'], 'draft')

    def test_completion_without_generated_tasks_is_visible_in_completed_filter(self):
        other = self.api.insert_email_record()
        self.assertEqual(self.post(f'/api/cutover/emails/{other}/complete', {'note': '无需上报，人工办结'}).status_code, 200)
        listed = self.api.report_client.get('/api/cutover/emails?status=completed').get_json()['data']
        self.assertEqual([item['id'] for item in listed['items']], [other])

    def test_completed_email_is_excluded_from_pending_stats_and_cannot_restart_processing(self):
        self.assertEqual(self.post(self.complete, {'note': '办结'}).status_code, 200)
        self.assertFalse(self.api.db.claim_email_api_forward(self.api.email_records_id))
        stats = self.api.report_client.get('/api/operations/summary?environment=all').get_json()['data']
        self.assertEqual(stats['metrics']['pending_tasks'], 0)
        self.assertEqual(stats['metrics']['reported_orders'], 0)
        self.assertEqual(self.post(f'/api/cutover/emails/{self.api.email_records_id}/forward-attempts', {}).status_code, 409)
        self.assertEqual(self.api.client.post(f'/api/cutover/tasks/{self.tasks[0]["id"]}/confirm',
            json={}, headers=self.api.headers).status_code, 409)
        other = self.api.insert_email_record()
        self.assertEqual(self.post(f'/api/cutover/emails/{other}/complete', {'note': '无需上报'}).status_code, 200)
        pending = self.api.report_client.get('/api/cutover/emails?status=no_task').get_json()['data']
        self.assertEqual(pending['total'], 0)

    def test_readonly_grant_cannot_resolve_or_complete(self):
        account = self.api.db.list_mail_accounts()[0]['id']
        self.api.access_repo.set_grants(self.api.operator['id'], [{'account_id': account, 'can_operate': False}])
        self.assertEqual(self.post(self.complete, {'note': '办结'}).status_code, 403)
        self.assertEqual(self.post(self.resolve, {'resolution': 'success', 'note': '核对'}).status_code, 403)

    def test_failed_queue_report_resolves_job_and_keeps_evidence(self):
        from unittest.mock import patch
        from rpa.report_jobs import finish_job, get_job
        task = self.tasks[1]
        self.api.db.update_cutover_task(task['id'], status='confirmed')
        with patch.object(fixtures.api_server, 'submit_cutover_report_job'):
            rid = self.post(f'/api/cutover/tasks/{task["id"]}/report', {}).get_json()['data']['report_id']
        self.api.db.update_cutover_report(rid, status='failed', result=deepcopy(self.original))
        finish_job(self.api.db, rid, 'running')
        self.api.db.update_cutover_task(task['id'], status='report_failed')
        self.assertEqual(self.post(self.complete, {'note': '完成'}).status_code, 409)
        finish_job(self.api.db, rid, 'failed')
        self.assertEqual(self.post(f'/api/cutover/reports/{rid}/resolve', {'resolution':'success','note':'综调已确认'}).status_code, 200)
        self.assertEqual(get_job(self.api.db, rid)['status'], 'success')
        self.assertEqual(self.api.db.get_cutover_report(rid)['result']['error'], '提交超时')

    def test_completion_keeps_legacy_reported_statistics_without_report_rows(self):
        task = self.tasks[1]
        with self.api.db.get_connection() as conn:
            conn.execute("UPDATE cutover_tasks SET status='reported',update_time='2026-10-28 10:00:00' WHERE id=?", (task['id'],))
            conn.commit()
        url = '/api/operations/summary?environment=all&start=2026-10-26&end=2026-11-01'
        before = self.api.report_client.get(url).get_json()['data']['metrics']
        self.assertEqual(before['reported_orders'], 1)
        self.assertEqual(self.post(self.complete, {'note':'办结'}).status_code, 200)
        after = self.api.report_client.get(url).get_json()['data']['metrics']
        self.assertEqual(after['reported_orders'], before['reported_orders'])
        self.assertEqual(after['reported_lines'], before['reported_lines'])
