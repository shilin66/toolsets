"""Desktop report identity and current-session state presentation."""
from pathlib import Path
import unittest

from playwright.sync_api import expect

from tests.ui import test_cutover_add_defaults_ui as defaults
from user_access import UserAccessRepository


class ReportIdentityUiTest(unittest.TestCase):
    use_user_login = True
    setUp = defaults.CutoverAddDefaultsUiTest.setUp
    open_task = defaults.CutoverAddDefaultsUiTest.open_task
    assert_clean = defaults.CutoverAddDefaultsUiTest.assert_clean

    def test_history_uses_usernames_chinese_types_and_desktop_layout(self):
        self.open_task(backbone=True)
        user = UserAccessRepository(self.api.db).create_user('alice', 'secure-password', '张三')
        self.api.db.add_cutover_report(self.task_id, 'backbone', 'success', {
            'note': '上报成功', 'execution_identity': {'principal_key': f'user-{user["id"]}',
                'username': 'sunting', 'environment': 'test'}})
        self.api.db.add_cutover_report(self.task_id, 'customer', 'failed', {'note': '历史失败记录'})
        self.page.reload()
        record = self.panel.locator('.report-identity')
        expect(record).to_contain_text('工作台用户')
        expect(record).to_contain_text('alice')
        expect(record).to_contain_text('综调账号')
        expect(record).to_contain_text('sunting')
        expect(record).not_to_contain_text('user-')
        table = self.panel.locator('.n-data-table').last
        expect(table).to_contain_text('骨干线路')
        expect(table).to_contain_text('客户线路')
        expect(table).not_to_contain_text('backbone')
        expect(table).to_contain_text('历史记录 · 未记录执行账号')
        expect(self.panel.get_by_role('region', name='当前综调会话')).to_have_count(0)
        expect(self.panel.locator('.current-portal-session')).to_have_count(0)
        expect(self.page.locator('.rpa-environment-badge')).to_contain_text('测试环境')
        evidence = Path('.qa/report-identity')
        evidence.mkdir(parents=True, exist_ok=True)
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width': width, 'height': 1000})
            self.panel.locator('.panel-actions').scroll_into_view_if_needed()
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
            self.assertLessEqual(record.evaluate('el => el.scrollWidth - el.clientWidth'), 1)
            self.page.screenshot(path=str(evidence / f'report-{width}.png'))
        self.assert_clean()

    def test_unchecked_running_expired_and_check_failure_are_distinct(self):
        pending = []
        self.page.route('**/api/rpa/session?*', lambda route: pending.append(route))
        self.open_task(backbone=True)
        session = self.page.locator('.rpa-environment-badge')
        expect(session).to_contain_text('未检查')
        self.assertTrue(pending)
        valid = {'state': 'authenticated', 'authenticated': True, 'portal_username': 'sunting',
                 'environment': 'test', 'session_version': 'version-one'}
        for route in pending:
            route.fulfill(json={'success': True, 'data': valid})
        self.page.unroute('**/api/rpa/session?*')
        expect(session).to_contain_text('sunting · 已登录')
        cases = [
            ({'state': 'unavailable', 'authenticated': False, 'reporting': True, 'portal_username': 'sunting'}, '执行中'),
            ({'state': 'login_required', 'authenticated': False, 'portal_username': 'sunting'}, '登录失效'),
            ({'state': 'unavailable', 'authenticated': False, 'portal_username': 'sunting'}, '检查失败'),
            ({'state': 'busy', 'authenticated': False}, '账号忙碌'),
            ({'state': 'login_required', 'authenticated': False}, '未登录'),
            ({'state': 'unavailable', 'authenticated': False, 'configured': False}, '未配置'),
        ]
        for status, label in cases:
            with self.subTest(state=label):
                self.page.route('**/api/rpa/session?*', lambda route: route.fulfill(json={'success': True, 'data': status}))
                self.page.reload()
                expect(session).to_contain_text(label)
                if label == '执行中':
                    expect(session).not_to_contain_text('登录失效')
                if label == '登录失效':
                    expect(session).to_contain_text('sunting · 登录失效')
                self.page.unroute('**/api/rpa/session?*')
        self.assert_clean()

    def test_reentering_session_page_reuses_check_before_environment_change(self):
        self.page.locator('.side-menu').get_by_text('综调会话', exact=True).click()
        expect(self.page.locator('.dispatch-status-panel')).to_contain_text('测试会话')
        pending = []
        self.page.route('**/api/rpa/session?*', lambda route: pending.append(route))
        self.page.locator('.dispatch-status-actions').get_by_role('button', name='立即检测').click()
        expect(self.page.locator('.dispatch-status-panel')).to_contain_text('正在检测')
        self.assertTrue(pending)
        self.page.unroute('**/api/rpa/session?*')
        self.page.locator('.side-menu').get_by_text('割接任务', exact=True).click()
        self.page.locator('.side-menu').get_by_text('综调会话', exact=True).click()
        expect(self.page.locator('.dispatch-status-panel')).to_contain_text('正在检测')
        self.assertEqual(len(pending), 1)
        pending[0].fulfill(json={'success': True, 'data': {'state': 'authenticated', 'authenticated': True,
            'environment': 'test', 'portal_username': 'old-test-account'}})
        expect(self.page.locator('.dispatch-status-panel')).to_contain_text('会话有效')
        self.page.locator('.dispatch-environment-select').click()
        self.page.get_by_text('正式环境', exact=True).click()
        expect(self.page.locator('.rpa-environment-badge')).to_contain_text('PRODUCTION')
        expect(self.page.locator('.dispatch-status-panel')).to_contain_text('测试会话')
        self.page.wait_for_load_state('networkidle')
        expect(self.page.locator('.rpa-environment-badge')).to_contain_text('PRODUCTION')
        expect(self.page.locator('.rpa-environment-badge')).not_to_contain_text('old-test-account')
        self.assert_clean()

    def test_report_completion_refreshes_session_without_waiting_for_header_timer(self):
        self.open_task(backbone=True)
        report_id = self.api.db.add_cutover_report(self.task_id, 'backbone', 'running', {'note': '执行中'})
        self.api.db.update_cutover_task(self.task_id, status='reporting')
        session_status = {'state': 'unavailable', 'authenticated': False, 'reporting': True,
                          'environment': 'test', 'portal_username': 'sunting'}
        checks = []
        def respond(route):
            checks.append(route.request.url)
            route.fulfill(json={'success': True, 'data': session_status})
        self.page.route('**/api/rpa/session?*', respond)
        self.page.reload()
        expect(self.page.locator('.report-progress-drawer')).to_be_visible()
        state = self.page.locator('.rpa-environment-badge')
        expect(state).to_contain_text('执行中')
        checks_before = len(checks)
        session_status.update(state='authenticated', authenticated=True, reporting=False)
        self.api.db.update_cutover_report(report_id, status='success', result={'note': '上报成功'})
        self.api.db.update_cutover_task(self.task_id, status='reported')
        expect(state).to_contain_text('已登录', timeout=5000)
        self.assertGreater(len(checks), checks_before)
        self.assert_clean()

    def test_login_cannot_be_interrupted_by_status_check(self):
        self.page.route('**/api/rpa/session/attempts', lambda route: route.fulfill(json={
            'success': True, 'data': {'attempt_id': 'pending-login', 'captcha_data_url': '', 'environment': 'test'}}))
        self.page.locator('.side-menu').get_by_text('综调会话', exact=True).click()
        self.page.locator('.dispatch-status-actions').get_by_role('button', name='重新登录').click()
        self.page.get_by_placeholder('请输入用户名', exact=True).fill('sunting')
        self.page.get_by_placeholder('请输入密码', exact=True).fill('test-password')
        self.page.get_by_placeholder('请输入图形验证码结果', exact=True).fill('42')
        pending = []
        self.page.route('**/api/rpa/session/attempts/pending-login/password', lambda route: pending.append(route))
        self.page.locator('.dispatch-form-actions button[type="submit"]').click()
        check = self.page.locator('.dispatch-status-actions').get_by_role('button', name='立即检测')
        expect(check).to_be_disabled()
        self.assertTrue(pending)
        pending[0].fulfill(json={'success': True, 'data': {'state': 'authenticated', 'authenticated': True,
            'environment': 'test', 'portal_username': 'sunting'}})
        expect(check).to_be_enabled()
        expect(self.page.locator('.rpa-environment-badge')).to_contain_text('sunting · 已登录')
        self.assert_clean()

    def test_status_check_and_captcha_creation_cannot_overlap(self):
        checks, attempts = [], []
        self.page.route('**/api/rpa/session?*', lambda route: checks.append(route))
        self.page.route('**/api/rpa/session/attempts', lambda route: attempts.append(route))
        self.page.reload()
        expect(self.page.locator('.side-menu')).to_be_visible()
        self.page.locator('.side-menu').get_by_text('综调会话', exact=True).click()
        relogin = self.page.locator('.dispatch-status-actions').get_by_role('button', name='重新登录')
        captcha = self.page.locator('.dispatch-captcha-button')
        expect(self.page.locator('.dispatch-status-panel')).to_contain_text('正在检测')
        expect(relogin).to_be_disabled()
        expect(captcha).to_be_disabled()
        self.assertEqual(attempts, [])
        for route in checks:
            route.fulfill(json={'success': True, 'data': {'state': 'login_required',
                'authenticated': False, 'configured': True, 'environment': 'test'}})
        expect(relogin).to_be_disabled()
        expect(captcha).to_be_disabled()
        expect(self.page.locator('.dispatch-status-actions').get_by_role('button', name='立即检测')).to_be_disabled()
        self.page.wait_for_function("document.querySelector('.dispatch-status-panel h4').textContent.includes('需要登录')")
        self.assertEqual(len(attempts), 1)
        self.assertEqual(len(checks), 1, 'header and session page must share the running check')
        attempts[0].fulfill(json={'success': True, 'data': {'attempt_id': 'captcha-ready',
            'captcha_data_url': '', 'environment': 'test'}})
        expect(relogin).to_be_enabled()
        expect(captcha).to_be_enabled()
        self.assert_clean()


if __name__ == '__main__':
    unittest.main()
