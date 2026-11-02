import io
import json
import os
import re
from pathlib import Path
from unittest.mock import patch
import unittest
from zipfile import ZipFile

from openpyxl import Workbook
from PIL import Image, ImageDraw
from playwright.sync_api import expect

import email_attachments
from tests.ui import test_cutover_workbench_ui as workbench


class CutoverAttachmentPreviewUiTest(unittest.TestCase):
    browser_channel = os.environ.get('UI_BROWSER_CHANNEL', 'chromium')
    close_server = workbench.CutoverWorkbenchUiTest.close_server
    select_tab = workbench.CutoverWorkbenchUiTest.select_tab

    def setUp(self):
        workbench.CutoverWorkbenchUiTest.setUp(self)
        root = patch.object(email_attachments, 'DATA_DIR', self.api.data_dir)
        root.start()
        self.addCleanup(root.stop)
        self.files = []
        self.attach('Affected_Services.csv', 'CircuitId\tOrderNumber\n00123\t000456\n'.encode('utf-16'))
        self.attach('notice.txt', b'<script>window.previewInjected=true</script>\nOriginal text 000789')
        self.page.reload()
        expect(self.page.locator('.cw-source .cw-attachment-row')).to_have_count(2)
        self.evidence = Path('.qa/cutover-attachments')
        self.evidence.mkdir(parents=True, exist_ok=True)

    def attach(self, filename, content):
        relative = email_attachments.save_attachment('noc@example.com', 1000, filename, content)
        self.files.append(relative)
        with self.api.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET attachments=? WHERE id=?',
                         (json.dumps(self.files), self.api.email_records_id))
            conn.commit()

    def preview(self, name):
        self.page.locator('.cw-source').get_by_role('button', name='预览 ' + name, exact=True).click()

    def test_actions_visible_and_custom_line_columns_come_first(self):
        payload = self.api.fill_payload()
        payload.pop('line_array_info')
        payload['line_array'] = [{
            'ImpactType':'interrupted', 'ImpactDateTime':'2026-06-12 14:00:00/2026-06-12 20:00:00',
            'ImpactDuration':'60m', 'InteruptionsCounts':'1',
            'VendorCircuit':'000ABC', 'OrderNumber':'00123', 'InterruptionsCounts':'1', 'ExtensionCode':'0099',
        }]
        self.api.db.update_email_line_match_payload(self.api.email_records_id, payload)
        self.page.reload()
        bar = self.page.locator('.cw-header-actions')
        expect(bar.get_by_role('button', name='高级信息', exact=True)).to_be_visible()
        expect(bar.locator('.cutover-email-delete-action')).to_be_visible()
        expect(self.page.get_by_text('更多操作', exact=False)).to_have_count(0)
        table = self.page.locator('.cw-result-line-table')
        expect(table.locator('thead th')).to_have_text(['#', 'ExtensionCode', 'OrderNumber', 'VendorCircuit',
            'ImpactType', 'ImpactDateTime', 'ImpactDuration', 'InteruptionsCounts', 'InterruptionsCounts'])
        expect(table).to_contain_text('00123')
        self.page.get_by_role('button', name='编辑识别结果', exact=True).click()
        expect(self.page.locator('.cw-edit-lines thead th')).to_have_text(table.locator('thead th').all_text_contents())
        self.assertEqual(self.errors, [])

    def test_csv_and_text_preview_keep_recognition_visible(self):
        payload = self.api.fill_payload()
        payload.pop('line_array_info')
        payload['line_array'] = [{'ImpactType':'interrupted',
            'ImpactDateTime':'2026-06-12 14:00:00/2026-06-12 20:00:00',
            'ImpactDuration':'60m','InteruptionsCounts':'1','CircuitId':'00123','OrderNumber':'000456'}]
        self.api.db.update_email_line_match_payload(self.api.email_records_id, payload)
        self.page.reload()
        self.preview('Affected_Services.csv')
        preview = self.page.locator('.cw-source .cw-attachment-preview')
        expect(preview.locator('tbody td')).to_have_text(['00123', '000456'])
        expect(self.page.locator('.cw-results')).to_be_visible()
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width':width,'height':1000})
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
            source = self.page.locator('.cw-compare > .cw-source').bounding_box()
            result = self.page.locator('.cw-compare > .cw-results').bounding_box()
            self.assertAlmostEqual(source['height'], result['height'], delta=1)
        self.page.set_viewport_size({'width':1440,'height':1000})
        self.page.screenshot(path=str(self.evidence/'csv-1440.png'), full_page=True)
        with self.page.expect_download() as download:
            self.page.locator('.cw-source').get_by_role('link', name='下载 Affected_Services.csv', exact=True).click()
        self.assertIn('00123', Path(download.value.path()).read_text())
        self.preview('notice.txt')
        expect(preview.locator('.cw-preview-text')).to_contain_text('<script>window.previewInjected=true</script>')
        self.assertIsNone(self.page.evaluate('window.previewInjected'))
        preview.get_by_role('button', name='返回邮件正文', exact=False).click()
        expect(self.page.locator('.cw-source .email-content-block')).to_be_visible()
        expect(preview).to_have_count(0)
        self.assertEqual(self.errors, [])

    def test_preview_failure_and_late_response_do_not_replace_active_attachment(self):
        url = f'**/api/cutover/emails/{self.api.email_records_id}/attachments/0/preview'
        self.page.route(url, lambda route: route.fulfill(status=422, json={'success':False,'message':'附件暂时无法预览'}))
        self.preview('Affected_Services.csv')
        expect(self.page.locator('.cw-source [role=alert]')).to_contain_text('附件暂时无法预览')
        self.page.unroute(url)
        self.page.get_by_role('button', name='重新预览', exact=True).click()
        expect(self.page.locator('.cw-source .cw-attachment-table')).to_contain_text('00123')
        held = []
        self.page.route(url, lambda route: held.append(route))
        self.preview('Affected_Services.csv')
        expect(self.page.locator('.cw-source .cw-attachment-preview [role=status]')).to_be_visible()
        self.preview('notice.txt')
        expect(self.page.locator('.cw-preview-text')).to_contain_text('000789')
        self.assertTrue(held)
        held[0].fulfill(json={'success':True,'data':{'kind':'text','text':'STALE DATA'}})
        expect(self.page.locator('.cw-preview-text')).to_contain_text('000789')
        expect(self.page.get_by_text('STALE DATA')).to_have_count(0)
        self.assertEqual(self.errors, [])

    def test_office_image_and_pdf_previews(self):
        book = Workbook()
        book.active.append(['CircuitId','OrderNumber'])
        book.active.append(['000987','000654'])
        book.create_sheet('备用线路').append(['000321'])
        output = io.BytesIO(); book.save(output)
        self.attach('lines.xlsx', output.getvalue())
        output = io.BytesIO()
        with ZipFile(output, 'w') as archive:
            archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>维护窗口 02:00—04:00</w:t></w:r></w:p></w:body></w:document>')
        self.attach('notice.docx', output.getvalue())
        picture = Image.new('RGB', (640,240), '#e5f1eb')
        draw = ImageDraw.Draw(picture)
        draw.text((16, 20), 'CircuitId: 000987', fill='#172b2e', font_size=24)
        draw.text((350, 20), 'OrderNumber: 000654', fill='#172b2e', font_size=24)
        draw.text((16, 180), 'Start: 2026-06-12 14:00', fill='#172b2e', font_size=24)
        draw.text((350, 180), 'End: 2026-06-12 20:00', fill='#172b2e', font_size=24)
        output = io.BytesIO(); picture.save(output,format='PNG')
        self.attach('map.png', output.getvalue())
        output = io.BytesIO(); picture.save(output,format='PDF')
        self.attach('notice.pdf', output.getvalue())
        self.page.reload()
        self.preview('lines.xlsx')
        expect(self.page.locator('.cw-attachment-table')).to_contain_text('000987')
        self.page.locator('.cw-sheet-bar select').select_option(label='备用线路')
        expect(self.page.locator('.cw-attachment-table')).to_contain_text('000321')
        self.preview('notice.docx')
        expect(self.page.locator('.cw-preview-document')).to_contain_text('维护窗口 02:00—04:00')
        self.preview('map.png')
        image = self.page.locator('.cw-preview-image img')
        expect(image).to_be_visible()
        self.page.wait_for_function("document.querySelector('.cw-preview-image img')?.naturalWidth===640")
        self.preview('notice.pdf')
        expect(self.page.locator('.cw-preview-pdf')).to_be_visible()
        expect(self.page.locator('.cw-preview-pdf')).to_have_attribute('data', re.compile('^blob:'))
        self.page.wait_for_load_state('networkidle')
        self.page.locator('.cw-preview-pdf').scroll_into_view_if_needed()
        self.page.screenshot(path=str(self.evidence/'pdf-preview.png'))
        self.assertEqual(self.errors, [])
