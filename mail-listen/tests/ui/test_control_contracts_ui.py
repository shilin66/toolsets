"""Exercise migrated controls against isolated, real application endpoints."""
import re
import unittest
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect

from tests.ui import test_naive_migration_ui as migration
from tests.api.test_supplier_circuits_api import build_import_workbook_bytes
from tests.api.test_cutover_task_api import CUSTOMER_CIRCUIT


class ControlContractsUiTest(unittest.TestCase):
    setUp = migration.NaiveMigrationUiTest.setUp
    assert_clean = migration.NaiveMigrationUiTest.assert_clean

    def test_escape_cancels_delete_and_releases_row_action(self):
        self.page.goto(self.base + '/admin/cutover-tasks')
        delete = self.page.get_by_role('button', name='删除此邮件及关联数据', exact=True).first
        original = self.api.db.get_email_record_by_id(self.api.email_records_id)
        delete.click()
        confirm = self.page.locator('.n-dialog')
        expect(confirm).to_be_visible()
        # This destructive confirmation deliberately ignores backdrop clicks.
        self.page.mouse.click(10, 10)
        expect(confirm).to_be_visible()
        expect(delete).to_be_disabled()
        self.page.keyboard.press('Escape')
        expect(confirm).not_to_be_visible()
        expect(delete).to_be_enabled()
        expect(delete).not_to_have_class(re.compile(r'n-button--loading'))
        delete.click()
        expect(confirm).to_be_visible()
        confirm.get_by_role('button', name='取消', exact=True).click()
        expect(confirm).not_to_be_visible()
        delete.click()
        confirm.locator('.n-dialog__close').click()
        expect(confirm).not_to_be_visible()
        expect(delete).to_be_enabled()
        self.assertNotIn('cancel', self.page.locator('.n-message').all_text_contents())
        self.assertEqual(self.api.db.get_email_record_by_id(self.api.email_records_id), original)
        self.assert_clean()

    def test_import_replacement_validates_files_and_removal_clears_preview(self):
        self.page.goto(self.base + '/admin/circuits')
        self.page.get_by_role('button', name='更多导入方式', exact=True).click()
        self.page.get_by_text('全量覆盖导入', exact=True).click()
        dialog = self.page.get_by_role('dialog', name='导入线路表', exact=True)
        file_input = dialog.locator('input[type=file]')
        preview = dialog.get_by_role('button', name='解析预览', exact=True)
        def upload(name, circuit_id):
            file_input.set_input_files({
                'name': name, 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'buffer': build_import_workbook_bytes([dict(CUSTOMER_CIRCUIT, circuit_id=circuit_id)]),
            })
        upload('first.xlsx', 'FIRST-LINE')
        preview.click()
        expect(dialog.locator('.n-data-table')).to_contain_text('FIRST-LINE')
        upload('replacement.xlsx', 'SECOND-LINE')
        expect(dialog.locator('.n-upload-file')).to_have_count(1)
        expect(dialog.locator('.n-upload-file')).to_contain_text('replacement.xlsx')
        expect(dialog.locator('.n-data-table')).to_have_count(0)
        preview.click()
        expect(dialog.locator('.n-data-table')).to_contain_text('SECOND-LINE')
        upload('invalid.txt', 'INVALID-LINE')
        expect(preview).to_be_disabled()
        expect(dialog.locator('.n-upload-file')).to_have_count(0)
        expect(dialog.locator('.n-data-table')).to_have_count(0)
        upload('last.xlsx', 'LAST-LINE')
        preview.click()
        expect(dialog.locator('.n-data-table')).to_contain_text('LAST-LINE')
        dialog.locator('.n-upload-file .n-button').click()
        expect(preview).to_be_disabled()
        expect(dialog.locator('.n-data-table')).to_have_count(0)
        self.assert_clean()

    def test_mail_switches_and_numeric_ports_round_trip(self):
        response = self.api.client.post('/api/system/mail-accounts', headers=self.api.headers, json={
            'name': 'Control test', 'email_address': 'controls@example.com',
            'email_password': 'test-only', 'imap_server': 'imap.example.com',
            'imap_port': 993, 'imap_use_ssl': True, 'smtp_port': 465,
            'smtp_use_ssl': True, 'smtp_use_tls': False, 'enabled': False,
        })
        self.assertEqual(response.status_code, 201)
        self.page.goto(self.base + '/admin/mail-accounts')
        row = self.page.get_by_role('row').filter(has_text='controls@example.com')
        row.get_by_role('button', name='编辑', exact=True).click()
        dialog = self.page.get_by_role('dialog', name='编辑邮箱', exact=True)
        switches = dialog.get_by_role('switch')
        for index, checked in enumerate((True, True, False)):
            expect(switches.nth(index)).to_be_checked(checked=checked)
            switches.nth(index).click()
        ports = dialog.locator('.n-input-number input')
        for index, value in enumerate(('143', '587')):
            ports.nth(index).fill(value)
            ports.nth(index).press('Tab')
        dialog.get_by_role('button', name='保存', exact=True).click()
        expect(dialog).not_to_be_visible()
        saved = next(item for item in self.api.db.list_mail_accounts() if item['email_address'] == 'controls@example.com')
        self.assertEqual((saved['imap_port'], saved['smtp_port']), (143, 587))
        self.assertEqual(tuple(bool(saved[key]) for key in ('imap_use_ssl', 'smtp_use_ssl', 'smtp_use_tls')), (False, False, True))
        row.get_by_role('button', name='编辑', exact=True).click()
        for index, checked in enumerate((False, False, True)):
            expect(switches.nth(index)).to_be_checked(checked=checked)
        expect(ports.nth(0)).to_have_value('143')
        expect(ports.nth(1)).to_have_value('587')
        dialog.get_by_role('button', name='取消', exact=True).click()
        expect(dialog).not_to_be_visible()
        toggle = row.get_by_role('switch')
        expect(toggle).not_to_be_checked()
        toggle.click()
        expect(toggle).to_be_checked()
        saved = next(item for item in self.api.db.list_mail_accounts() if item['email_address'] == 'controls@example.com')
        self.assertTrue(saved['enabled'])
        self.assert_clean()

    def test_date_filters_apply_and_reset_without_changing_date_format(self):
        self.page.goto(self.base + '/admin/cutover-tasks')
        self.page.get_by_role('button', name=re.compile('更多筛选')).click()
        dates = self.page.locator('.cutover-advanced-filters .n-date-picker input')
        for index, value in enumerate(('2026-10-01', '2026-10-31')):
            dates.nth(index).fill(value)
            dates.nth(index).press('Tab')
        is_list = lambda r: urlsplit(r.url).path == '/api/cutover/emails'
        with self.page.expect_response(is_list) as response:
            self.page.get_by_role('button', name='查询', exact=True).click()
        params = parse_qs(urlsplit(response.value.url).query)
        self.assertEqual(params['start'], ['2026-10-01'])
        self.assertEqual(params['end'], ['2026-10-31'])
        with self.page.expect_response(is_list) as response:
            self.page.get_by_role('button', name='重置', exact=True).click()
        params = parse_qs(urlsplit(response.value.url).query)
        self.assertNotIn('start', params)
        self.assertNotIn('end', params)
        self.assert_clean()

    def test_datetime_settings_preserve_seconds_and_clear_to_null(self):
        response = self.api.client.put('/api/system/settings', headers=self.api.headers, json={
            'guard_start_time': '2026-10-01 10:20:30', 'guard_end_time': '2026-10-31 21:30:45',
            'backbone_noc_phone': '123456', 'backbone_province_reviewer_name': 'Test reviewer',
            'backbone_province_reviewer_phone': '654321',
        })
        self.assertEqual(response.status_code, 200)
        self.page.goto(self.base + '/admin/settings')
        dates = self.page.locator('.settings-view .n-date-picker input')
        expect(dates.nth(0)).to_have_value('2026-10-01 10:20:30')
        dates.nth(0).fill('2026-10-02 11:22:33')
        dates.nth(0).press('Tab')
        dates.nth(1).fill('')
        dates.nth(1).press('Tab')
        guard = self.page.locator('.block-section').filter(has=self.page.locator('.n-date-picker'))
        with self.page.expect_response(lambda r: r.request.method == 'PUT' and urlsplit(r.url).path == '/api/system/settings') as result:
            guard.get_by_role('button', name='保存', exact=True).click()
        self.assertEqual(result.value.status, 200)
        saved = result.value.json()['data']
        self.assertEqual(saved['guard_start_time'], '2026-10-02 11:22:33')
        self.assertIsNone(saved['guard_end_time'])
        self.page.reload()
        expect(dates.nth(0)).to_have_value('2026-10-02 11:22:33')
        expect(dates.nth(1)).to_have_value('')
        self.assert_clean()
