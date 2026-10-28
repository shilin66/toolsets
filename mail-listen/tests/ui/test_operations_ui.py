"""Desktop operations UI against an isolated real Flask/SQLite application."""
import threading
import unittest
from pathlib import Path

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

import api_server
from tests.api import test_operations_api as operations_fixture
from tests.ui.test_cutover_regeneration_ui import QuietRequestHandler


class OperationsUiTest(unittest.TestCase):
    def setUp(self):
        self.fixture = operations_fixture.OperationsApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.server = make_server('127.0.0.1', 0, api_server.app, threaded=True, request_handler=QuietRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.pw = sync_playwright().start()
        self.addCleanup(self.pw.stop)
        self.browser = self.pw.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.errors = []

    def stop_server(self):
        self.server.shutdown(); self.thread.join(timeout=5); self.server.server_close()

    def page(self, admin=False, width=1440):
        page = self.browser.new_page(viewport={'width': width, 'height': 1100}, locale='zh-CN')
        page.set_default_timeout(10000)
        page.on('pageerror', lambda error: self.errors.append(str(error)))
        page.route('**/api/rpa/session?*', lambda route: route.fulfill(json={'success': True, 'data': {'authenticated': False, 'state': 'login_required'}}))
        page.goto(self.base + '/admin/operations')
        if admin:
            page.get_by_role('button', name='管理员登录', exact=True).click()
            page.get_by_role('textbox', name='API Key').fill('test-key')
        else:
            page.get_by_role('textbox', name='用户名', exact=True).fill('stats')
            page.get_by_role('textbox', name='密码', exact=True).fill('stats-password-123')
        page.get_by_role('button', name='登录', exact=True).click()
        expect(page.get_by_role('heading', name='每周运营，一览全局')).to_be_visible()
        page.locator('.n-date-picker[aria-label="开始日期"] input').fill('2026-10-26')
        page.locator('.n-date-picker[aria-label="开始日期"] input').press('Tab')
        page.locator('.n-date-picker[aria-label="结束日期"] input').fill('2026-11-01')
        page.locator('.n-date-picker[aria-label="结束日期"] input').press('Tab')
        expect(page.get_by_role('button', name='查询统计')).to_be_enabled()
        with page.expect_response(lambda response: '/api/operations/summary?' in response.url):
            page.get_by_role('button', name='查询统计').click()
        expect(page.locator('.stats-cards')).to_be_visible()
        expect(page.get_by_role('button', name='查询统计')).to_be_enabled()
        return page

    def screenshot(self, page, name):
        target = Path('.qa/operations'); target.mkdir(parents=True, exist_ok=True)
        page.get_by_role('heading', name='每周运营，一览全局').click()
        expect(page.locator('.n-date-panel:visible')).to_have_count(0)
        page.screenshot(path=str(target / name), full_page=True)
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)

    def test_user_scope_empty_filter_details_and_failure(self):
        page = self.page(width=1280)
        expect(page.get_by_role('menuitem', name='运营统计', exact=True)).to_be_visible()
        expect(page.locator('.stats-card').filter(has_text='上报线路')).to_contain_text('3')
        page.get_by_label('监听邮箱', exact=True).click()
        expect(page.locator('.n-base-select-menu')).to_contain_text('one@example.com')
        expect(page.locator('.n-base-select-menu')).not_to_contain_text('two@example.com')
        page.keyboard.press('Escape')
        self.screenshot(page, 'user-overview-1280.png')
        page.locator('.stats-card').filter(has_text='上报线路').click()
        expect(page.locator('.stats-table tbody tr')).to_have_count(3)
        expect(page.locator('.stats-table')).to_contain_text('CT-1')
        page.get_by_label('监听邮箱', exact=True).click()
        page.get_by_role('button', name='清空', exact=True).click()
        page.keyboard.press('Escape')
        page.get_by_role('button', name='查询统计').click()
        expect(page.locator('.stats-card').filter(has_text='接收邮件').locator('strong')).to_have_text('0')
        expect(page.locator('.stats-table tbody tr')).to_have_count(0)
        page.route('**/api/operations/summary?*', lambda route: route.fulfill(status=500, json={'success': False, 'message': '统计服务暂不可用'}))
        page.get_by_role('button', name='查询统计').click()
        expect(page.get_by_role('alert')).to_contain_text('统计服务暂不可用')
        expect(page.locator('.stats-cards')).to_have_count(0)
        self.assertEqual(self.errors, [])

    def test_mailbox_options_failure_can_retry_without_showing_false_zero(self):
        page = self.browser.new_page(viewport={'width': 1280, 'height': 1000})
        page.context.request.post(self.base + '/api/auth/login', data={'mode': 'admin', 'api_key': 'test-key'})
        page.route('**/api/operations/options', lambda route: route.fulfill(status=503, json={'success': False, 'message': '邮箱列表暂不可用'}), times=1)
        page.goto(self.base + '/admin/operations')
        expect(page.get_by_role('alert')).to_contain_text('邮箱列表暂不可用')
        expect(page.locator('.stats-cards')).to_have_count(0)
        page.get_by_role('button', name='重试', exact=True).click()
        expect(page.locator('.stats-cards')).to_be_visible()
        expect(page.locator('.stats-mailbox-filter')).to_contain_text('含历史邮箱')
        expect(page.locator('.stats-card').filter(has_text='已接入运营商').locator('strong')).to_have_text('1')

    def test_legacy_successes_show_numbers_in_overview_and_details(self):
        with self.fixture.db.get_connection() as c:
            c.execute("UPDATE cutover_reports SET statistics_snapshot=NULL,completed_at=NULL,result=?",
                ('{"updated_at":"2026-10-27T10:00:00+08:00"}',))
            c.commit()
        page = self.page(admin=True, width=1280)
        for title, count in [('上报邮件','2'),('上报工单','1'),('上报线路','5')]:
            expect(page.locator('.stats-card').filter(has_text=title).locator('strong')).to_have_text(count)
        expect(page.locator('.stats-overview')).to_be_visible()
        self.screenshot(page, 'legacy-counts-1280.png')
        page.locator('.stats-card').filter(has_text='上报线路').click()
        expect(page.locator('.stats-table tbody tr')).to_have_count(5)
        expect(page.locator('.stats-table')).to_contain_text('CT-1')
        self.assertEqual(self.errors, [])

    def test_admin_filter_export_pagination_and_navigation(self):
        with self.fixture.db.get_connection() as c:
            c.executemany("INSERT INTO supplier_configs(name,email,create_time,update_time) VALUES (?,?,?,?)",
                [(f'其他运营商{i:02}',f'other{i}@example.com','2026-10-27','2026-10-27') for i in range(25)])
            c.commit()
        page = self.page(admin=True)
        expect(page.locator('.stats-card').filter(has_text='上报线路')).to_contain_text('5')
        self.screenshot(page, 'admin-overview-1440.png')
        page.get_by_role('tab', name='运营商明细').click()
        page.get_by_label('运营商状态', exact=True).click()
        page.locator('.n-base-select-option').filter(has_text='全部运营商').click()
        expect(page.locator('.stats-table tbody tr')).to_have_count(20)
        page.get_by_role('button', name='下一页', exact=True).click()
        expect(page.locator('.stats-table tbody tr')).to_have_count(6)
        page.get_by_label('搜索运营商').fill('运营商甲')
        page.get_by_role('button', name='搜索', exact=True).click()
        expect(page.locator('.stats-table tbody tr')).to_have_count(1)
        page.get_by_label('搜索运营商').fill('尚未提交的新搜索')
        with page.expect_download() as download:
            page.get_by_role('button', name='导出筛选结果 CSV').click()
        self.assertTrue(download.value.suggested_filename.endswith('.csv'))
        self.assertIn('运营商甲', Path(download.value.path()).read_text(encoding='utf-8-sig'))
        page.get_by_label('搜索运营商').fill('运营商甲')
        self.screenshot(page, 'admin-suppliers-1440.png')
        page.get_by_label('监听邮箱', exact=True).click()
        page.locator('.n-base-select-option').filter(has_text='two@example.com').click()
        page.keyboard.press('Escape')
        page.get_by_role('button', name='查询统计').click()
        expect(page.locator('.stats-card').filter(has_text='上报线路')).to_contain_text('3')
        page.get_by_role('menuitem', name='割接任务', exact=True).click()
        page.locator('.operations-summary-heading').get_by_role('button', name='运营统计').click()
        expect(page).to_have_url(self.base + '/admin/operations')
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
