"""Role-specific desktop sign-in and administrator RPA restrictions."""
from pathlib import Path
import unittest
from unittest.mock import patch

from playwright.sync_api import expect

from tests.ui import test_multiuser_ui as fixture


class LoginUiTest(unittest.TestCase):
    def setUp(self):
        fixture.MultiuserUiTest.setUp(self)
        task_db = patch('cutover_task.email_db', self.fixture.db)
        task_db.start()
        self.addCleanup(task_db.stop)
    close_server = fixture.MultiuserUiTest.close_server
    page = fixture.MultiuserUiTest.page

    def test_password_and_api_key_visibility_toggle_preserves_value(self):
        page = self.page()
        for mode, field_id in (('user', 'login-password'), ('admin', 'login-key')):
            with self.subTest(mode=mode):
                if mode == 'admin':
                    page.get_by_role('button', name='管理员登录', exact=True).click()
                field = page.locator(f'#{field_id}')
                expect(field).to_have_attribute('type', 'password')
                field.fill('visibility-test-secret')
                toggle = field.locator('xpath=ancestor::div[contains(@class, "login-field")]').locator('.n-input__eye')
                toggle.click()
                expect(field).to_have_attribute('type', 'text')
                expect(field).to_have_value('visibility-test-secret')
                toggle.click()
                expect(field).to_have_attribute('type', 'password')
                expect(field).to_have_value('visibility-test-secret')
        page.get_by_role('button', name='返回普通用户登录', exact=True).click()
        expect(page.locator('#login-password')).to_have_attribute('type', 'password')
        expect(page.locator('#login-password')).to_have_value('')
        self.assertEqual(self.errors, [])

    def test_autofill_keeps_login_field_surface_and_readable_text(self):
        page = self.page()
        cdp = page.context.new_cdp_session(page)
        cdp.send('DOM.enable')
        cdp.send('CSS.enable')
        for selector in ('#login-username', '#login-password', '#login-key'):
            if selector == '#login-key':
                page.get_by_role('button', name='管理员登录', exact=True).click()
            field = page.locator(selector)
            field.fill('autofill-test')
            root = cdp.send('DOM.getDocument')['root']['nodeId']
            node = cdp.send('DOM.querySelector', {'nodeId': root, 'selector': selector})['nodeId']
            # Exercise Chromium's autofill pseudo-state, without storing credentials.
            cdp.send('CSS.forcePseudoState', {'nodeId': node, 'forcedPseudoClasses': ['autofill']})
            for focused in (False, True):
                if focused:
                    field.focus()
                else:
                    page.locator('.login-title').click()
                styles = field.evaluate('''el => {
                    const style = getComputedStyle(el);
                    return {autofilled: el.matches(':autofill'), shadow: style.boxShadow,
                        text: style.webkitTextFillColor, caret: style.caretColor,
                        surface: getComputedStyle(el.closest('.n-input')).backgroundColor};
                }''')
                self.assertTrue(styles['autofilled'])
                self.assertIn(styles['surface'], styles['shadow'])
                self.assertIn('inset', styles['shadow'])
                self.assertNotEqual(styles['caret'], styles['surface'])
                self.assertNotEqual(styles['text'], styles['surface'])
            cdp.send('CSS.forcePseudoState', {'nodeId': node, 'forcedPseudoClasses': []})
        self.assertEqual(self.errors, [])

    def test_user_default_validation_role_switch_and_desktop_layout(self):
        page = self.page(1280)
        username = page.get_by_role('textbox', name='用户名', exact=True)
        password = page.get_by_role('textbox', name='密码', exact=True)
        expect(username).to_be_focused()
        expect(password).to_be_visible()
        expect(page.get_by_role('textbox', name='API Key')).to_have_count(0)
        expect(page.get_by_role('tablist')).to_have_count(0)
        requests = []
        page.on('request', lambda request: requests.append(request) if request.url.endswith('/api/auth/login') else None)
        username.press('Enter')
        expect(page.get_by_role('alert')).to_have_text('请输入用户名')
        expect(username).to_be_focused()
        username.fill('alice')
        username.press('Enter')
        expect(page.get_by_role('alert')).to_have_text('请输入密码')
        expect(password).to_be_focused()
        self.assertEqual(len(requests), 0)
        password.fill('temporary-secret')
        page.get_by_role('button', name='管理员登录', exact=True).click()
        key = page.get_by_role('textbox', name='API Key')
        expect(key).to_be_focused()
        expect(page.get_by_role('alert')).to_have_count(0)
        expect(page.locator('.login-admin-note')).to_contain_text('不提供综调登录与上报')
        key.fill('temporary-api-key')
        page.get_by_role('button', name='返回普通用户登录', exact=True).click()
        expect(username).to_be_focused()
        expect(username).to_have_value('alice')
        expect(password).to_have_value('')
        target = Path('.qa/login-redesign')
        target.mkdir(parents=True, exist_ok=True)
        for width in (1280, 1440, 1920):
            page.set_viewport_size({'width': width, 'height': 900})
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
            switch = page.get_by_role('button', name='管理员登录', exact=True)
            expect(switch.locator('svg')).to_be_visible()
            switch_box = switch.bounding_box()
            card = page.locator('.login-card').bounding_box()
            self.assertLess(card['x'] + card['width'] - switch_box['x'] - switch_box['width'], 60)
            self.assertLess(card['y'] + card['height'] - switch_box['y'] - switch_box['height'], 48)
            self.assertGreater(switch_box['y'], page.locator('.login-submit').bounding_box()['y'])
            page.screenshot(path=str(target / f'user-{width}.png'))
        switch.focus()
        switch.press('Enter')
        expect(page.get_by_role('heading', name='管理员登录', exact=True)).to_be_visible()
        expect(key).to_be_focused()
        expect(key).to_have_value('')
        page.screenshot(path=str(target / 'admin-1920.png'))
        self.assertEqual(self.errors, [])

    def test_enter_submits_once_and_locks_role_while_pending(self):
        page = self.page()
        pending = []
        page.route('**/api/auth/login', lambda route: pending.append(route))
        page.get_by_role('textbox', name='用户名', exact=True).fill('alice')
        password = page.get_by_role('textbox', name='密码', exact=True)
        password.fill('a-secure-password')
        password.press('Enter')
        expect(page.get_by_role('button', name='登录', exact=True)).to_be_disabled()
        expect(page.get_by_role('button', name='管理员登录', exact=True)).to_be_disabled()
        page.keyboard.press('Enter')
        self.assertEqual(len(pending), 1)
        pending[0].continue_()
        expect(page.locator('.workbench-identity')).to_contain_text('张三')
        expect(page.locator('.side-menu')).to_contain_text('综调会话')
        expect(page.locator('.rpa-environment-badge')).to_contain_text('portal-alice')
        self.assertEqual(self.errors, [])

    def test_admin_has_no_portal_requests_route_or_report_action(self):
        page = self.page()
        portal_requests = []
        page.on('request', lambda request: portal_requests.append(request.url) if '/api/rpa/session' in request.url else None)
        page.get_by_role('button', name='管理员登录', exact=True).click()
        page.get_by_role('textbox', name='API Key').fill('test-key')
        page.get_by_role('textbox', name='API Key').press('Enter')
        expect(page.locator('.workbench-identity')).to_contain_text('管理员')
        expect(page.locator('.side-menu')).not_to_contain_text('综调会话')
        expect(page.locator('.side-menu')).to_contain_text('用户与邮箱授权')
        expect(page.locator('.side-menu')).to_contain_text('邮箱配置')
        expect(page.locator('.rpa-environment-badge')).to_have_count(0)
        page.goto(self.base + '/admin/dispatch-session')
        expect(page).to_have_url(self.base + '/admin/cutover-tasks')
        task = self.fixture.tasks[0]
        self.fixture.db.update_cutover_task(task, status='confirmed', fill_result={
            'circuits': [{'电路代号': 'TEST-001'}], 'reasons': [{'割接原因': '测试'}]})
        page.goto(f'{self.base}/admin/cutover-emails/{self.fixture.emails[0]}?taskId={task}')
        panel = page.locator('.task-detail-panel')
        expect(panel).to_be_visible()
        expect(panel.get_by_role('button', name='上报综调系统', exact=True)).to_be_disabled()
        expect(panel).to_contain_text('综调上报请使用普通用户账号')
        self.assertEqual(portal_requests, [])
        self.assertEqual(self.errors, [])

    def test_failed_login_has_inline_error_and_can_retry(self):
        page = self.page()
        page.get_by_role('textbox', name='用户名', exact=True).fill('alice')
        password = page.get_by_role('textbox', name='密码', exact=True)
        password.fill('incorrect-password')
        password.press('Enter')
        expect(page.get_by_role('alert')).to_contain_text('用户名或密码不正确')
        expect(page.get_by_role('button', name='登录', exact=True)).to_be_enabled()
        password.fill('a-secure-password')
        password.press('Enter')
        expect(page.locator('.workbench-identity')).to_contain_text('张三')
        self.assertEqual(self.errors, [])
