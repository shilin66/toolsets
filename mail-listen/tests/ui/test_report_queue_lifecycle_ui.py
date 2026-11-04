import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect
from rpa.report_queue import recover_report_jobs
from rpa.report_jobs import finish_job
from tests.api.test_cutover_task_api import api_server
from tests.ui import test_report_start_ui as fixtures


class ReportQueueLifecycleUiTest(unittest.TestCase):
    use_user_login = True
    setUp = fixtures.ReportStartUiTest.setUp
    open_task = fixtures.ReportStartUiTest.open_task
    prepare_report = fixtures.ReportStartUiTest.prepare_report
    assert_clean = fixtures.ReportStartUiTest.assert_clean

    def enqueue(self):
        del self.api.session_service.status
        self.prepare_report()
        self.scheduled = []
        scheduling = patch.object(api_server, 'submit_cutover_report_job', side_effect=self.scheduled.append)
        scheduling.start()
        self.addCleanup(scheduling.stop)
        self.button.click()
        self.drawer = self.page.locator('.report-progress-drawer')
        expect(self.drawer).to_contain_text('排队中')
        self.report_id = self.api.db.get_cutover_reports(self.task_id)[0]['id']

    def test_pause_survives_reload_and_resume_runs_task(self):
        self.enqueue()
        self.drawer.get_by_role('button', name='暂停任务', exact=True).click()
        expect(self.drawer).to_contain_text('已暂停')
        self.page.reload()
        expect(self.drawer).to_contain_text('已暂停')
        self.assertEqual(self.api.db.get_cutover_report(self.report_id)['status'], 'paused')
        evidence = Path('.qa/report-queue')
        evidence.mkdir(parents=True, exist_ok=True)
        self.page.set_viewport_size({'width':1280,'height':1000})
        self.page.screenshot(path=str(evidence / 'paused-1280.png'), animations='disabled')
        self.drawer.get_by_role('button', name='继续上报', exact=True).click()
        expect(self.drawer).to_contain_text('排队中')
        with patch.object(api_server, 'report_cutover_task', return_value={'status':'success'}), \
                patch.object(api_server, 'ensure_source_email_archived'):
            self.scheduled[-1]()
        expect(self.drawer).to_contain_text('上报成功')
        self.assert_clean()

    def test_login_pause_offers_relogin_without_failure_toast(self):
        self.enqueue()
        with patch.object(api_server, 'report_cutover_task',
                side_effect=api_server.PortalSessionError('RPA_SESSION_REQUIRED', '登录失效')), \
                patch.object(api_server, 'ensure_source_email_archived'):
            self.scheduled[0]()
        expect(self.drawer).to_contain_text('等待重新登录')
        expect(self.page.locator('.n-message--error')).to_have_count(0)
        self.drawer.get_by_role('button', name='前往登录', exact=True).click()
        expect(self.page.locator('.dispatch-status-panel')).to_contain_text('队列已暂停')
        self.page.get_by_placeholder('请输入用户名', exact=True).fill('portal-admin')
        self.page.get_by_placeholder('请输入密码', exact=True).fill('password')
        self.page.get_by_placeholder('请输入图形验证码结果', exact=True).fill('42')
        self.page.locator('.dispatch-form-actions button[type="submit"]').click()
        expect(self.page.locator('.dispatch-status-panel')).to_contain_text('会话有效')
        self.assertEqual(self.api.db.get_cutover_report(self.report_id)['status'], 'pending')
        with patch.object(api_server, 'report_cutover_task', return_value={'status':'success'}), \
                patch.object(api_server, 'ensure_source_email_archived'):
            self.scheduled[-1]()
        self.assertEqual(self.api.db.get_cutover_report(self.report_id)['status'], 'success')
        self.assert_clean()

    def test_recovered_interrupted_report_displays_reconciliation_state(self):
        self.enqueue()
        finish_job(self.api.db, self.report_id, 'running')
        self.api.db.update_cutover_report(self.report_id, status='running')
        recover_report_jobs(self.api.db, self.api.data_dir, lambda rid: None)
        self.page.reload()
        expect(self.drawer).to_contain_text('结果待核对')
        expect(self.drawer.get_by_role('button', name='暂停任务', exact=True)).to_have_count(0)
        expect(self.page.locator('.n-message--error')).to_have_count(0)
        self.assert_clean()
