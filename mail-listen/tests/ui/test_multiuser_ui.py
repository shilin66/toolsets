import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import g
from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

import api_server
from rpa.session_config import PortalSessionSettings
from rpa.session_models import LoginMode, PortalEnvironment
from rpa.user_sessions import PortalSessionRegistry
from tests.api import test_user_access_api as access_fixture
from tests.rpa.test_user_sessions import FakeSessionService
from tests.ui.test_cutover_regeneration_ui import QuietRequestHandler


class MultiuserUiTest(unittest.TestCase):
    def setUp(self):
        self.fixture = access_fixture.UserAccessApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        db, repo = self.fixture.db, self.fixture.repo
        self.bob = repo.create_user('bob', 'another-password', '李四')
        repo.set_grants(self.bob['id'], [{'account_id': self.fixture.accounts[1], 'can_operate': False}])
        settings = PortalSessionSettings.model_construct(
            test_login_url='http://localhost/login', test_mobile_login_url='http://localhost/mobile',
            test_session_check_url='http://localhost/home', production_login_url='http://localhost/login',
            production_mobile_login_url='http://localhost/mobile', production_session_check_url='http://localhost/home',
            session_keepalive_enabled=False)
        self.registry = PortalSessionRegistry(db, Path(self.fixture.temp.name), settings, service_factory=FakeSessionService)
        self.addCleanup(self.registry.close)
        for user, name, env in [(self.fixture.user, 'portal-alice', PortalEnvironment.TEST), (self.bob, 'portal-bob', PortalEnvironment.PRODUCTION)]:
            service = self.registry.for_principal(repo.get_principal(user['id']))
            attempt = service.begin(LoginMode.PASSWORD, env)
            service.login_with_password(attempt.attempt_id, name, 'secret', '42')
        service_patch = patch.object(api_server, 'get_portal_session_service', side_effect=lambda: self.registry.for_principal(g.principal))
        service_patch.start()
        self.addCleanup(service_patch.stop)
        self.server = make_server('127.0.0.1', 0, api_server.app, threaded=True, request_handler=QuietRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.errors = []

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def page(self, width=1440, production=False):
        context = self.browser.new_context(viewport={'width': width, 'height': 1000}, locale='zh-CN')
        if production:
            context.add_init_script("localStorage.setItem('mailListenPortalEnvironment', 'production')")
        page = context.new_page()
        page.set_default_timeout(10000)
        page.on('pageerror', lambda error: self.errors.append(str(error)))
        page.goto(self.base + '/admin/cutover-tasks')
        return page

    def login_user(self, page, username, password):
        page.get_by_role('textbox', name='用户名', exact=True).fill(username)
        page.get_by_role('textbox', name='密码', exact=True).fill(password)
        page.get_by_role('button', name='登录', exact=True).click()
        expect(page.locator('.workbench-identity')).to_be_visible()

    def test_two_browser_sessions_show_only_their_mail_and_portal_identity(self):
        alice = self.page(1280)
        self.login_user(alice, 'alice', 'a-secure-password')
        bob = self.page(1440, production=True)
        self.login_user(bob, 'bob', 'another-password')
        expect(alice.locator('.cutover-list-view')).to_contain_text('one@example.com')
        expect(alice.locator('.cutover-list-view')).not_to_contain_text('two@example.com')
        expect(bob.locator('.cutover-list-view')).to_contain_text('two@example.com')
        expect(bob.locator('.cutover-list-view')).not_to_contain_text('one@example.com')
        expect(alice.locator('.rpa-environment-badge')).to_contain_text('portal-alice')
        expect(bob.locator('.rpa-environment-badge.is-production')).to_contain_text('portal-bob')
        expect(bob.locator('.rpa-environment-badge')).to_contain_text('PRODUCTION')
        expect(alice.locator('.side-menu .n-menu-item')).to_have_count(6)
        expect(alice.locator('.side-menu')).not_to_contain_text('用户与邮箱授权')
        expect(alice.locator('.side-menu')).not_to_contain_text('邮箱配置')
        for page, name in [(alice, 'alice-1280'), (bob, 'bob-production-1440')]:
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
            target = Path('.qa/multiuser')
            target.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(target / f'{name}.png'), full_page=True)
        alice.goto(self.base + '/admin/users')
        expect(alice).to_have_url(self.base + '/admin/cutover-tasks')
        alice.get_by_role('button', name='退出登录').click()
        expect(alice.get_by_role('textbox', name='用户名', exact=True)).to_be_visible()
        bob.reload()
        expect(bob.locator('.workbench-identity')).to_contain_text('李四')
        self.assertEqual(self.errors, [])

    def test_regular_user_business_pages_exclude_user_and_mailbox_management(self):
        page = self.page(1280)
        failures = []
        page.on('response', lambda response: failures.append((response.url, response.status))
                if '/api/' in response.url and response.status >= 400 else None)
        self.login_user(page, 'alice', 'a-secure-password')
        for route, selector in (
            ('suppliers', '.supplier-config-tabs'), ('suppliers/new', '.supplier-form'),
            ('circuits', '.view-body'),
            ('settings', '.discovery-settings'), ('dispatch-session', '.view-body'),
        ):
            page.goto(self.base + '/admin/' + route)
            expect(page).to_have_url(self.base + '/admin/' + route)
            expect(page.locator(selector)).to_be_visible()
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
        page.goto(self.base + '/admin/suppliers')
        page.get_by_role('tab', name='配置草稿', exact=True).click()
        expect(page.locator('.drafts-list-panel')).to_be_visible()
        for restricted in ('users', 'mail-accounts'):
            page.goto(self.base + '/admin/' + restricted)
            expect(page).to_have_url(self.base + '/admin/cutover-tasks')
            expect(page.locator('.mail-accounts-panel')).to_have_count(0)
        self.assertEqual(failures, [])
        self.assertEqual(self.errors, [])

    def test_admin_can_create_user_and_grant_existing_mailbox_from_page(self):
        page = self.page()
        page.get_by_role('button', name='管理员登录', exact=True).click()
        page.get_by_role('textbox', name='API Key').fill('test-key')
        page.get_by_role('button', name='登录', exact=True).click()
        page.get_by_role('menuitem', name='用户与邮箱授权').click()
        page.get_by_role('textbox', name='新用户用户名').fill('charlie')
        page.get_by_role('textbox', name='新用户显示名称').fill('王五')
        page.get_by_role('textbox', name='新用户初始密码').fill('charlie-password')
        page.get_by_role('button', name='创建账号', exact=True).click()
        expect(page.get_by_role('heading', name='王五 · 邮箱授权')).to_be_visible()
        page.get_by_label('one@example.com 权限', exact=True).click()
        page.locator('.n-base-select-option').filter(has_text='查看并操作').click()
        page.get_by_role('button', name='保存邮箱授权', exact=True).click()
        expect(page.get_by_text('已保存', exact=True).last).to_be_visible()
        page.reload()
        page.get_by_role('button', name='王五 charlie · 已启用').click()
        expect(page.get_by_label('one@example.com 权限', exact=True)).to_contain_text('查看并操作')
        target = Path('.qa/multiuser')
        target.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target / 'admin-grants-1440.png'), full_page=True)
        self.assertEqual(self.errors, [])

    def test_regular_user_can_save_shared_fields_without_reading_hidden_samples(self):
        secret = '禁止跨邮箱查看的样本正文'
        result = self.fixture.client.post('/api/suppliers', headers=self.fixture.admin_headers, json={
            'name': '共享配置', 'email': 'sample@example.com', 'prompt_mode': 'auto',
            'line_custom_fields': [{'name': 'CircuitTitle', 'description': '线路名称'}],
            'line_query_keywords': ['CircuitTitle'],
            'email_type_samples': {'割接通知': {'subject': '维护', 'content': secret}}})
        self.assertEqual(result.status_code, 201, result.get_json())
        supplier_id = result.get_json()['data']['id']
        page = self.page(1280)
        self.login_user(page, 'alice', 'a-secure-password')
        page.goto(self.base + f'/admin/suppliers/{supplier_id}')
        expect(page.locator('.supplier-mail-pane')).to_contain_text('邮件样本受来源邮箱权限保护')
        expect(page.locator('.mail-type-list')).to_have_count(0)
        expect(page.locator('body')).not_to_contain_text(secret)
        expect(page.get_by_role('button', name='识别这封邮件', exact=True)).to_be_disabled()
        page.get_by_placeholder('例如 RT', exact=True).fill('普通用户更新共享配置')
        with page.expect_response(lambda response: response.url.endswith(f'/api/suppliers/{supplier_id}')
                                  and response.request.method == 'PATCH') as saved:
            page.get_by_role('button', name='保存配置', exact=True).click()
        self.assertEqual(saved.value.status, 200)
        from supplier_config import SupplierConfigRepository
        stored = SupplierConfigRepository(self.fixture.db).get(supplier_id)
        self.assertEqual(stored['name'], '普通用户更新共享配置')
        self.assertEqual(stored['email_type_samples']['割接通知']['content'], secret)
        self.assertEqual(self.errors, [])
