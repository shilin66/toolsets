"""Immediate report feedback while session and submission requests are pending."""
import unittest
from pathlib import Path
from playwright.sync_api import expect
from tests.ui import test_cutover_add_defaults_ui as defaults


class ReportStartUiTest(unittest.TestCase):
    use_user_login = True
    setUp = defaults.CutoverAddDefaultsUiTest.setUp
    open_task = defaults.CutoverAddDefaultsUiTest.open_task
    assert_clean = defaults.CutoverAddDefaultsUiTest.assert_clean

    def prepare_report(self):
        self.open_task(backbone=True)
        self.api.db.update_cutover_task(self.task_id, status='confirmed')
        self.page.reload()
        self.button = self.panel.get_by_role('button', name='上报综调系统', exact=True)
        expect(self.button).to_be_enabled()
        self.page.wait_for_load_state('networkidle')

    def test_progress_opens_before_session_and_submission_finish(self):
        self.prepare_report()
        sessions, submissions = [], []
        self.page.route('**/api/rpa/session?*', lambda route: sessions.append(route))
        self.page.route(f'**/api/cutover/tasks/{self.task_id}/report', lambda route: submissions.append(route))
        self.button.click()
        drawer = self.page.locator('.report-progress-drawer')
        expect(drawer).to_be_visible(timeout=1000)
        expect(drawer).to_contain_text('正在准备上报任务')
        expect(drawer).not_to_contain_text('后台任务已启动')
        expect(drawer).not_to_contain_text('排队中')
        expect(self.button).to_be_disabled()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(submissions, [])
        evidence = Path('.qa/report-start')
        evidence.mkdir(parents=True, exist_ok=True)
        expect(drawer).to_be_in_viewport(ratio=0.95, timeout=1000)
        self.page.screenshot(path=str(evidence / 'preparing.png'), animations='disabled')
        sessions[0].fulfill(json={'success': True, 'data': {
            'authenticated': True, 'state': 'authenticated', 'session_version': 'v1'}})
        self.page.unroute('**/api/rpa/session?*')
        self.page.wait_for_timeout(100)
        self.assertEqual(len(submissions), 1)
        expect(drawer).to_be_visible()
        expect(self.button).to_be_disabled()
        report_id = self.api.db.add_cutover_report(self.task_id, 'backbone', 'running', {'note': '执行中'})
        submissions[0].fulfill(json={'success': True, 'data': {'report_id': report_id, 'report_status': 'running'}})
        expect(drawer).to_contain_text(f'#{report_id}')
        expect(drawer).to_contain_text('执行中')
        self.assert_clean()

    def test_rejected_submission_stops_spinner_and_allows_retry(self):
        self.prepare_report()
        self.page.route(f'**/api/cutover/tasks/{self.task_id}/report', lambda route: route.fulfill(
            json={'success': False, 'message': '测试：暂时无法创建上报任务'}))
        self.button.click()
        drawer = self.page.locator('.report-progress-drawer')
        expect(drawer).to_be_visible()
        expect(drawer).to_contain_text('测试：暂时无法创建上报任务')
        expect(drawer.locator('.is-loading')).to_have_count(0)
        expect(self.button).to_be_enabled()
        self.assert_clean()
