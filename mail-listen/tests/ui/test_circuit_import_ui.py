"""Desktop circuit import journeys against real endpoints and temporary data."""
import io
import re
import unittest
from pathlib import Path

from openpyxl import load_workbook
from playwright.sync_api import expect

from tests.ui import test_naive_migration_ui as migration
from tests.api.test_supplier_circuits_api import build_import_workbook_bytes


class CircuitImportUiTest(unittest.TestCase):
    setUp = migration.NaiveMigrationUiTest.setUp
    assert_clean = migration.NaiveMigrationUiTest.assert_clean

    def open_import(self):
        self.page.goto(self.base + '/admin/circuits')
        self.page.get_by_role('button', name='增量导入', exact=True).click()
        return self.page.get_by_role('dialog', name='增量导入线路', exact=True)

    def upload(self, dialog, rows):
        dialog.locator('input[type=file]').set_input_files({
            'name': '新增线路.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'buffer': build_import_workbook_bytes(rows),
        })
        dialog.get_by_role('button', name='解析预览', exact=True).click()
        expect(dialog.locator('.n-data-table')).to_be_visible()

    def test_desktop_import_preserves_data_downloads_report_and_template(self):
        output = Path('.qa/circuit-import')
        output.mkdir(parents=True, exist_ok=True)
        for width in (1280, 1440, 2560):
            with self.subTest(width=width):
                self.page.set_viewport_size({'width': width, 'height': 1440 if width == 2560 else 1000})
                original = self.api.db.get_all_supplier_circuits()
                dialog = self.open_import()
                self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
                bounds = dialog.bounding_box()
                self.assertGreaterEqual(bounds['x'], 0)
                self.assertLessEqual(bounds['x'] + bounds['width'], width)
                if width == 2560:
                    self.page.screenshot(path=str(output / 'circuit-import.png'))
                with self.page.expect_download() as downloaded:
                    dialog.get_by_role('button', name='下载模板', exact=True).click()
                self.assertEqual(downloaded.value.suggested_filename, '线路导入模板_v1.xlsx')
                wb = load_workbook(io.BytesIO(Path(downloaded.value.path()).read_bytes()))
                self.assertEqual(wb.active['B2'].number_format, '@')
                self.assertIsNone(wb.active['B2'].value)
                wb.close()
                new = dict(supplier='UI-RT', supplier_circuit_id=f'0000{width}', circuit_id='INTERNAL-01', line_status='正常')
                rows = [new, new, dict(original[0], line_status='待确认')]
                self.upload(dialog, rows)
                expect(dialog.get_by_role('button', name='确认新增 1 条', exact=True)).to_be_enabled()
                self.assertEqual(self.api.db.get_all_supplier_circuits(), original)
                self.page.screenshot(path=str(output / f'preview-{width}.png'))
                dialog.get_by_role('button', name='确认新增 1 条', exact=True).click()
                expect(dialog.get_by_role('button', name='下载结果明细', exact=True)).to_be_visible()
                self.assertEqual(self.api.db.count_supplier_circuits(), len(original) + 1)
                for row in original:
                    self.assertEqual(self.api.db.get_supplier_circuit(row['id']), row)
                with self.page.expect_download() as downloaded:
                    dialog.get_by_role('button', name='下载结果明细', exact=True).click()
                wb = load_workbook(io.BytesIO(Path(downloaded.value.path()).read_bytes()))
                self.assertEqual(wb.active['D2'].value, new['supplier_circuit_id'])
                self.assertEqual(wb.active['H2'].value, '已新增')
                self.assertEqual(wb.active['H3'].value, '已跳过')
                wb.close()
                self.page.screenshot(path=str(output / f'result-{width}.png'))
                dialog.get_by_role('button', name='关闭', exact=True).click()
                expect(dialog).not_to_be_visible()
                self.assert_clean()

    def test_invalid_rows_block_batch_and_replacement_resets_preview(self):
        original = self.api.db.get_all_supplier_circuits()
        dialog = self.open_import()
        rows = [{'supplier': '', 'supplier_circuit_id': 'ERROR'},
                {'supplier': 'RT', 'supplier_circuit_id': 'GOOD'}]
        self.upload(dialog, rows)
        expect(dialog).to_contain_text('存在校验错误，整批暂不写入')
        expect(dialog.get_by_role('button', name='确认新增 1 条', exact=True)).to_be_disabled()
        dialog.locator('.circuit-import-filters .n-select').click()
        self.page.locator('.n-base-select-option').filter(has_text='校验错误').click()
        expect(dialog.locator('.n-data-table')).to_contain_text('ERROR')
        expect(dialog.locator('.n-data-table')).not_to_contain_text('GOOD')
        dialog.locator('input[type=file]').set_input_files({
            'name': 'corrected.xlsx', 'mimeType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'buffer': build_import_workbook_bytes([rows[1]])})
        expect(dialog.locator('.n-data-table')).to_have_count(0)
        expect(dialog.get_by_role('button', name='确认新增 0 条', exact=True)).to_be_disabled()
        self.assertEqual(self.api.db.get_all_supplier_circuits(), original)
        self.assert_clean()

    def test_changed_database_refreshes_preview_without_writing(self):
        dialog = self.open_import()
        row = {'supplier': 'RT', 'supplier_circuit_id': 'CONCURRENT', 'circuit_id': 'TEST'}
        self.upload(dialog, [row])
        self.api.db.create_supplier_circuit(row)
        count = self.api.db.count_supplier_circuits()
        dialog.get_by_role('button', name='确认新增 1 条', exact=True).click()
        expect(dialog).to_contain_text('没有需要新增的线路')
        expect(dialog.get_by_role('button', name='确认新增 0 条', exact=True)).to_be_disabled()
        self.assertEqual(self.api.db.count_supplier_circuits(), count)
        self.assertEqual(self.errors, [])

    def test_template_download_from_toolbar(self):
        self.page.goto(self.base + '/admin/circuits')
        with self.page.expect_download() as download:
            self.page.get_by_role('button', name='下载模板', exact=True).click()
        self.assertEqual(download.value.suggested_filename, '线路导入模板_v1.xlsx')
        self.assert_clean()

    def test_preview_pagination_and_keyboard_entry(self):
        self.page.goto(self.base + '/admin/circuits')
        button = self.page.get_by_role('button', name='增量导入', exact=True)
        button.focus()
        button.press('Enter')
        dialog = self.page.get_by_role('dialog', name='增量导入线路', exact=True)
        self.upload(dialog, [{'supplier': 'PAGE', 'supplier_circuit_id': f'ID-{i:03d}'} for i in range(52)])
        expect(dialog.locator('.n-data-table')).to_contain_text('ID-000')
        expect(dialog.locator('.n-data-table')).not_to_contain_text('ID-051')
        dialog.get_by_role('button', name='下一页', exact=True).click()
        expect(dialog.locator('.n-data-table')).to_contain_text('ID-051')
        dialog.get_by_role('button', name='确认新增 52 条', exact=True).click()
        expect(dialog.get_by_role('button', name='下载结果明细', exact=True)).to_be_visible()
        self.assertEqual(len([row for row in self.api.db.get_all_supplier_circuits() if row['supplier'] == 'PAGE']), 52)
        self.assert_clean()
