"""Native Naive UI smoke checks against one Flask server and a temporary database."""
import threading
from datetime import datetime
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

from tests.api import test_cutover_task_api as fixture
from tests.ui.test_cutover_regeneration_ui import QuietRequestHandler


class NaiveMigrationUiTest(unittest.TestCase):
    def setUp(self):
        self.api = fixture.CutoverTaskApiTest()
        self.api.setUp()
        self.addCleanup(self.api.tearDown)
        self.api.session_service.status = lambda environment=None: SimpleNamespace(state='authenticated', authenticated=True, message='测试会话', checked_at=datetime.now(), environment=environment or 'test', configured=True, password_login_url='https://example.invalid/login', mobile_login_url='https://example.invalid/mobile', state_path=Path(self.api.tmpdir.name)/'session', keepalive=None)
        manager = patch.object(fixture.api_server, 'listener_manager', MagicMock())
        manager.start()
        self.addCleanup(manager.stop)
        self.api.db.replace_all_supplier_circuits([fixture.BACKBONE_CIRCUIT])
        self.server = make_server('127.0.0.1', 0, fixture.api_server.app,
                                 threaded=True, request_handler=QuietRequestHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        runtime = sync_playwright().start()
        self.addCleanup(runtime.stop)
        self.browser = runtime.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={'width':1440, 'height':1000}, locale='zh-CN')
        self.page.set_default_timeout(10000)
        self.errors = []
        self.external_requests = []
        self.console_errors = []
        self.page.on('console', lambda message:self.console_errors.append(message.text) if message.type == 'error' else None)
        self.page.on('pageerror', lambda error:self.errors.append(str(error)))
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        def local_only(route):
            if urlsplit(route.request.url).netloc != urlsplit(self.base).netloc:
                self.external_requests.append(route.request.url)
                route.abort()
            else:
                route.continue_()
        self.page.route('**/*', local_only)
        self.page.goto(self.base + '/admin/suppliers')
        if getattr(self, 'use_user_login', False):
            self.page.get_by_role('textbox', name='用户名', exact=True).fill('operator')
            self.page.get_by_role('textbox', name='密码', exact=True).fill('operator-password')
        else:
            self.page.get_by_role('button', name='管理员登录', exact=True).click()
            self.page.get_by_role('textbox', name='API Key').fill('test-key')
        self.page.get_by_role('button', name='登录', exact=True).click()
        expect(self.page.locator('.view-body')).to_be_visible()
        self.evidence = Path(__file__).resolve().parents[2] / '.qa' / 'naive-migration'
        self.evidence.mkdir(parents=True, exist_ok=True)

    def assert_clean(self):
        self.assertEqual(self.errors, [])
        self.assertEqual(self.console_errors, [])
        self.assertEqual(self.external_requests, [], 'All frontend assets must use the same Flask service')

    def test_all_desktop_routes_use_native_naive_and_same_service(self):
        routes = ['suppliers', 'emails', 'cutover-tasks', 'circuits', 'mail-accounts',
                  'settings', 'suppliers/new', f'suppliers/{self.api.supplier_config["id"]}',
                  f'cutover-emails/{self.api.email_records_id}']
        for route in routes:
            with self.subTest(route=route):
                self.page.goto(self.base + '/admin/' + route)
                expect(self.page.locator('.view-body')).to_be_visible()
                expect(self.page.locator('.n-button').first).to_be_visible()
                expect(self.page.get_by_role('heading', level=1)).to_have_count(1)
                expect(self.page.locator('.topbar-title')).to_be_visible()
                expect(self.page.locator('.page-heading, .dispatch-session-intro')).to_have_count(0)
                self.assertLessEqual(self.page.locator('.topbar').bounding_box()['height'], 56)
                if route == 'cutover-tasks':
                    expect(self.page.locator('.operations-summary')).to_be_visible()
                else:
                    expect(self.page.locator('.operations-summary')).to_have_count(0)
                self.assertFalse(self.page.locator('script[src*="/element-plus.js"]').count())
                self.page.screenshot(path=str(self.evidence / (route.replace('/', '-') + '-1440.png')), full_page=True)
                self.assert_clean()
        for width in (1280, 1920):
            self.page.set_viewport_size({'width':width, 'height':1000})
            self.page.goto(self.base + '/admin/suppliers')
            expect(self.page.locator('.view-body')).to_be_visible()
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))

    def test_language_and_keyboard_login_survive_reload(self):
        self.page.get_by_role('button', name='退出登录', exact=True).click()
        expect(self.page.locator('.login-screen')).to_be_visible()
        self.page.locator('.login-lang').click()
        self.page.get_by_text('English', exact=True).click()
        expect(self.page.locator('html')).to_have_attribute('lang', 'en')
        self.page.reload()
        expect(self.page.locator('html')).to_have_attribute('lang', 'en')
        self.page.get_by_role('button', name='Administrator sign-in', exact=True).click()
        self.page.get_by_role('textbox', name='API Key').fill('test-key')
        self.page.get_by_role('textbox', name='API Key').press('Enter')
        expect(self.page.locator('.app-shell')).to_be_visible()
        self.page.get_by_role('button', name='Sign out', exact=True).click()
        self.page.locator('.login-lang').click()
        self.page.get_by_text('繁體中文（香港）', exact=True).click()
        expect(self.page.locator('html')).to_have_attribute('lang', 'zh-HK')
        self.page.get_by_role('button', name='管理員登入', exact=True).click()
        self.page.get_by_role('textbox', name='API Key').fill('test-key')
        self.page.get_by_role('textbox', name='API Key').press('Enter')
        expect(self.page.locator('.app-shell')).to_be_visible()
        expect(self.page.get_by_role('button', name='登出', exact=True)).to_be_visible()
        self.assert_clean()

    def test_supplier_create_edit_persists_to_database(self):
        self.page.goto(self.base + '/admin/suppliers/new')
        self.page.get_by_placeholder('例如 RT', exact=True).fill('Naive smoke supplier')
        self.page.get_by_role('textbox', name='来信发件地址', exact=True).fill('naive@example.com')
        self.page.get_by_role('textbox', name='割接通知主题样本', exact=True).fill('维护通知')
        self.page.get_by_role('textbox', name='割接通知正文样本', exact=True).fill('线路维护，2026 年 10 月 25 日 02:00 至 04:00。')
        self.page.get_by_role('button', name='进入邮件核对', exact=True).click()
        self.page.get_by_role('button', name='高级配置', exact=True).click()
        attachment = self.page.locator('.mail-type-attachment-flag')
        expect(attachment).not_to_be_checked()
        attachment.click()
        expect(attachment).to_be_checked()
        self.page.get_by_placeholder('字段名，例如 CircuitTitle', exact=True).fill('CircuitTitle')
        self.page.get_by_placeholder('描述该字段在线路表格中的对应列和提取方式，例如：对应表格中的 Circuit Title 列', exact=True).fill('线路编号')
        self.page.get_by_role('button', name='保存配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        suppliers = self.api.client.get('/api/suppliers', headers=self.api.headers).get_json()['data']
        supplier = next(row for row in suppliers if row['name'] == 'Naive smoke supplier')
        self.assertEqual(supplier['email'], 'naive@example.com')
        self.page.goto(self.base + f'/admin/suppliers/{supplier["id"]}')
        expect(self.page.get_by_placeholder('例如 RT', exact=True)).to_have_value('Naive smoke supplier')
        self.page.get_by_role('button', name='高级配置', exact=True).click()
        expect(attachment).to_be_checked()
        attachment.click()
        expect(attachment).not_to_be_checked()
        self.page.get_by_placeholder('例如 RT', exact=True).fill('Naive edited supplier')
        self.page.get_by_role('button', name='保存配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        saved = self.api.client.get(f'/api/suppliers/{supplier["id"]}', headers=self.api.headers).get_json()['data']
        self.assertEqual(saved['name'], 'Naive edited supplier')
        self.assertIs(saved['email_type_samples']['割接通知']['content_in_attachment'], False)
        self.assert_clean()

    def test_mail_form_validation_and_save_uses_native_dialog(self):
        original = self.api.db.list_mail_accounts()
        self.page.goto(self.base + '/admin/mail-accounts')
        self.page.get_by_role('button', name='新增邮箱', exact=True).click()
        dialog = self.page.get_by_role('dialog')
        expect(dialog).to_be_visible()
        dialog.get_by_role('button', name='保存', exact=True).click()
        expect(dialog).to_contain_text('请填写名称')
        self.assertEqual(self.api.db.list_mail_accounts(), original)
        dialog.get_by_placeholder('如：NOC 值班邮箱', exact=True).fill('Naive mailbox')
        dialog.locator('.n-form-item').filter(has=self.page.get_by_text('邮箱地址', exact=True)).locator('input').fill('naive@example.com')
        dialog.get_by_placeholder('请输入密码或授权码', exact=True).fill('test-only-password')
        dialog.get_by_placeholder('如：imap.qq.com', exact=True).fill('imap.example.com')
        dialog.get_by_role('button', name='保存', exact=True).click()
        expect(dialog).not_to_be_visible()
        rows = self.api.db.list_mail_accounts()
        self.assertEqual(len(rows), len(original) + 1)
        self.assertIn('naive@example.com', [row['email_address'] for row in rows])
        self.assert_clean()

    def test_circuit_upload_preview_cancel_and_confirm_replace(self):
        from tests.api.test_supplier_circuits_api import build_import_workbook_bytes
        imported = dict(fixture.CUSTOMER_CIRCUIT, circuit_id='NAIVE-IMPORT-001')
        content = build_import_workbook_bytes([imported])
        original = self.api.db.get_all_supplier_circuits()
        self.page.goto(self.base + '/admin/circuits')
        self.page.get_by_role('button', name='导入', exact=True).click()
        dialog = self.page.get_by_role('dialog', name='导入线路表', exact=True)
        dialog.locator('input[type=file]').set_input_files({
            'name':'circuits.xlsx',
            'mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'buffer':content,
        })
        dialog.get_by_role('button', name='解析预览', exact=True).click()
        expect(dialog.locator('.n-data-table')).to_contain_text('NAIVE-IMPORT-001')
        self.assertEqual(self.api.db.get_all_supplier_circuits(), original)
        dialog.get_by_role('button', name='确认导入', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='取消', exact=True).click()
        self.assertEqual(self.api.db.get_all_supplier_circuits(), original)
        dialog.get_by_role('button', name='确认导入', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='确认导入', exact=True).click()
        expect(dialog).not_to_be_visible()
        rows = self.api.db.get_all_supplier_circuits()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['circuit_id'], 'NAIVE-IMPORT-001')
        self.assert_clean()
