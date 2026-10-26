"""List/detail navigation must retain the user's query and pagination."""
import re
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect

from tests.ui import test_naive_migration_ui as migration


class CutoverListStateUiTest(unittest.TestCase):
    setUp = migration.NaiveMigrationUiTest.setUp
    assert_clean = migration.NaiveMigrationUiTest.assert_clean

    def list_response(self, action):
        with self.page.expect_response(
            lambda response: urlsplit(response.url).path == '/api/cutover/emails'
        ) as response:
            action()
        self.assertEqual(response.value.status, 200)
        return parse_qs(urlsplit(response.value.url).query)

    def open_detail(self):
        self.page.locator('.cutover-mail-heading').first.click()
        expect(self.page.locator('.topbar-title')).to_have_text('割接任务详情')

    def test_filters_survive_breadcrumb_browser_back_and_sidebar_return(self):
        self.page.set_viewport_size({'width': 1280, 'height': 1000})
        self.list_response(lambda: self.page.goto(self.base + '/admin/cutover-tasks?status=no_task'))
        keyword = self.page.locator('.cutover-main-filters input').first
        keyword.fill('割接通知')
        self.page.get_by_role('button', name=re.compile('更多筛选')).click()
        sender = self.page.locator('.cutover-advanced-filters input[aria-label="发件人"]')
        sender.fill('noc@supplier.example.com')
        dates = self.page.locator('.cutover-advanced-filters .n-date-picker input')
        for index, value in enumerate(('2020-01-01', '2099-12-31')):
            dates.nth(index).fill(value)
            dates.nth(index).press('Tab')
        expected = self.list_response(
            lambda: self.page.get_by_role('button', name='查询', exact=True).click()
        )
        self.assertEqual(expected['keyword'], ['割接通知'])
        for return_method in ('breadcrumb', 'browser', 'sidebar'):
            with self.subTest(return_method=return_method):
                self.open_detail()
                if return_method == 'browser':
                    action = self.page.go_back
                elif return_method == 'breadcrumb':
                    action = lambda: self.page.locator('.topbar-parent-link').click()
                else:
                    action = lambda: self.page.locator('.side-menu').get_by_text('割接任务', exact=True).click()
                self.assertEqual(self.list_response(action), expected)
                expect(keyword).to_have_value('割接通知')
                expect(sender).to_have_value('noc@supplier.example.com')
                expect(dates.nth(0)).to_have_value('2020-01-01')
                expect(dates.nth(1)).to_have_value('2099-12-31')
                expect(self.page.locator('.cutover-main-filters')).to_contain_text('无任务')
        evidence = Path(__file__).resolve().parents[2] / '.qa' / 'cutover-list-state'
        evidence.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(evidence / 'returned-filters-1280.png'))
        reset = self.list_response(lambda: self.page.get_by_role('button', name='重置', exact=True).click())
        self.assertEqual(reset, {'page': ['1'], 'pageSize': ['20']})
        self.open_detail()
        self.assertEqual(self.list_response(lambda: self.page.locator('.topbar-parent-link').click()), reset)
        expect(keyword).to_have_value('')
        expect(sender).to_have_value('')
        self.assert_clean()

    def test_pagination_and_unsubmitted_edits_survive_return(self):
        for index in range(55):
            self.api.insert_email_record(subject=f'分页保留 {index}')
        self.list_response(lambda: self.page.goto(self.base + '/admin/cutover-tasks'))
        keyword = self.page.locator('.cutover-main-filters input').first
        keyword.fill('分页保留')
        self.list_response(lambda: self.page.get_by_role('button', name='查询', exact=True).click())
        self.page.locator('.cutover-pagination .n-base-selection').click()
        self.list_response(lambda: self.page.get_by_text('50 / 页', exact=True).click())
        expected = self.list_response(lambda: self.page.get_by_role('button', name='下一页', exact=True).click())
        self.assertEqual(expected, {'page': ['2'], 'pageSize': ['50'], 'keyword': ['分页保留']})
        keyword.fill('尚未提交的查询')
        self.open_detail()
        self.assertEqual(self.list_response(lambda: self.page.locator('.topbar-parent-link').click()), expected)
        expect(keyword).to_have_value('尚未提交的查询')
        expect(self.page.locator('.cutover-pagination')).to_contain_text('51')
        expect(self.page.locator('.cutover-mail-heading')).to_have_count(5)
        self.assert_clean()

    def test_return_refreshes_results_and_summary_starts_a_new_query(self):
        self.list_response(lambda: self.page.goto(self.base + '/admin/cutover-tasks'))
        keyword = self.page.locator('.cutover-main-filters input').first
        keyword.fill('割接通知')
        expected = self.list_response(lambda: self.page.get_by_role('button', name='查询', exact=True).click())
        self.open_detail()
        self.api.insert_email_record(subject='割接通知：新增邮件')
        self.assertEqual(self.list_response(lambda: self.page.locator('.topbar-parent-link').click()), expected)
        expect(self.page.locator('.cutover-mail-heading')).to_have_count(2)
        params = self.list_response(lambda: self.page.locator('.operations-metric').first.click())
        self.assertEqual(params, {'page': ['1'], 'pageSize': ['20'], 'status': ['draft']})
        expect(keyword).to_have_value('')
        # A directly opened detail has no originating list state.
        self.page.goto(self.base + f'/admin/cutover-emails/{self.api.email_records_id}')
        params = self.list_response(lambda: self.page.locator('.topbar-parent-link').click())
        self.assertEqual(params, {'page': ['1'], 'pageSize': ['20']})
        self.assert_clean()

    def test_detail_deletion_preserves_query_on_automatic_return(self):
        self.api.insert_email_record(subject='割接通知：保留邮件')
        self.list_response(lambda: self.page.goto(self.base + '/admin/cutover-tasks'))
        keyword = self.page.locator('.cutover-main-filters input').first
        keyword.fill('割接通知')
        expected = self.list_response(lambda: self.page.get_by_role('button', name='查询', exact=True).click())
        self.open_detail()
        self.page.locator('.cutover-email-delete-action').click()
        returned = self.list_response(
            lambda: self.page.locator('.n-dialog').get_by_role('button', name='确认删除', exact=True).click()
        )
        self.assertEqual(returned, expected)
        expect(keyword).to_have_value('割接通知')
        expect(self.page.locator('.cutover-mail-heading')).to_have_count(1)
        self.assert_clean()
