import json
import re
import threading
import unittest
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

import api_server
from models import EmailMessage
from tests.api import test_supplier_drafts_api as fixture
from tests.ui.test_cutover_regeneration_ui import QuietRequestHandler


class SupplierDiscoveryUiTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.SupplierDraftApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.draft_id = self.fixture.make_draft()
        self.job = self.fixture.repo.claim()
        self.email_id = self.job['email_records_id']
        self.fixture.complete(self.job, {
            'analysis_status': 'ready', 'scene': 'major_event',
            'cutover_start': '2026-10-14T02:00:00+08:00', 'cutover_end': '2026-10-14T04:00:00+08:00',
            'assessed_at': '2026-10-13T10:00:00+08:00', 'source_timezone': 'Asia/Shanghai',
            'source_time_text': '北京时间 14 日 02:00—04:00', 'hours_until_start': 16,
            'security_window': {'start': '2026-10-14T00:00:00+08:00', 'end': '2026-10-15T00:00:00+08:00'},
            'reason': '割接窗口与重保窗口相交', 'reply': {'content': '重保期间请调整维护窗口。'},
        })
        self.server = make_server('127.0.0.1', 0, api_server.app, threaded=True, request_handler=QuietRequestHandler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1000}, locale='zh-CN')
        self.page.set_default_timeout(10000)
        self.errors = []
        self.console_errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.on('console', lambda message: self.console_errors.append(message.text) if message.type == 'error' else None)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.page.goto(self.base + '/admin/settings')
        self.page.get_by_role('textbox', name='API Key').fill('test-key')
        self.page.get_by_role('button', name='登录', exact=True).click()
        expect(self.page.locator('.discovery-settings')).to_be_visible()
        self.evidence = Path(__file__).resolve().parents[2] / '.qa' / 'supplier-discovery'
        self.evidence.mkdir(parents=True, exist_ok=True)

    def add_list_drafts(self, count):
        statuses = ('collecting', 'generating', 'review', 'generation_failed', 'published')
        created = []
        for index in range(count):
            sender = f'supplier-{index:02d}-' + 'regional.' * 4 + 'maintenance@network-operations.example.com'
            status = statuses[index % len(statuses)]
            name = f'跨区域网络维护服务供应商与备用线路管理团队 {index:02d}'
            config = {'name':name, 'email':sender, 'prompt_mode':'auto',
                'email_type_samples':{'割接通知':{'subject':'维护通知','content':'维护正文'}}}
            supplier_id = None
            if status == 'published':
                response = self.fixture.client.post('/api/suppliers', headers=self.fixture.headers, json=config)
                self.assertEqual(response.status_code, 201)
                supplier_id = response.get_json()['data']['id']
            draft = {'config':config, 'evidence':['来自邮件样本'], 'unresolved_questions':[]} if status in ('review','published') else None
            with self.fixture.db.get_connection() as conn:
                row = conn.execute('''INSERT INTO supplier_drafts
                    (candidate_key,sender,display_name,status,draft_json,revision,published_supplier_id,last_error,create_time,update_time)
                    VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (sender,sender,name,status,json.dumps(draft, ensure_ascii=False) if draft else None,
                     1 if draft else 0,supplier_id,'模型返回格式错误，等待人工重试' if status == 'generation_failed' else '',
                     '2030-01-01 00:00:00',f'2030-01-01 00:00:{index:02d}'))
                created.append({'id':row.lastrowid, 'sender':sender, 'status':status})
                conn.commit()
        return created

    def open_drafts_list(self):
        self.page.goto(self.base + '/admin/suppliers')
        self.page.get_by_role('tab', name='配置草稿', exact=True).click()
        panel = self.page.locator('.drafts-list-panel')
        expect(panel).to_be_visible()
        return panel

    def assert_clean_browser(self, expected_http_errors=()):
        unexpected = [message for message in self.console_errors if not any(
            re.search(rf'Failed to load resource:.*status of {status}\b', message)
            for status in expected_http_errors)]
        self.assertEqual(unexpected, [])
        self.assertEqual(self.errors, [])

    def test_original_sample_keeps_tables_full_body_and_plain_text_line_breaks(self):
        text = 'Dear NOC,\n\n' + 'Maintenance notice details. ' * 25 + '\nCircuit ID: ORIGINAL-4821\nEnd of notice.'
        html = '''<!doctype html><html><head><style>td,th { padding: 12px; border: 1px solid #ddd; }</style>
            <meta http-equiv="refresh" content="0;url=https://mail-preview.invalid/refresh"></head><body>
            <p>Dear NOC,<br>Scheduled network maintenance</p><p>Full original mail body.</p>
            <table><tr><th>Circuit ID</th><th>Location</th></tr><tr><td>ORIGINAL-4821</td><td>Hong Kong</td></tr></table>
            <p>End of notice.</p><script>parent.document.body.dataset.mailScriptRan = 'yes'</script>
            <img src="https://mail-preview.invalid/tracker" onerror="parent.document.body.dataset.mailScriptRan = 'yes'">
            </body></html>'''
        with self.fixture.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET content=?, html_content=? WHERE id=?', (text, html, self.email_id))
            conn.commit()
        external = []
        self.page.route('https://mail-preview.invalid/**', lambda route: (external.append(route.request.url), route.abort()))
        panel = self.open_drafts_list()
        panel.get_by_role('button', name='邮件样本', exact=True).click()
        self.page.locator('.draft-review-panel').get_by_role('button', name='维护', exact=True).click()
        dialog = self.page.get_by_role('dialog', name='维护', exact=True)
        expect(dialog).to_be_visible()
        frame = dialog.frame_locator('iframe')
        expect(frame.locator('table')).to_be_visible()
        expect(frame.locator('td').first).to_have_text('ORIGINAL-4821')
        expect(frame.locator('body')).to_contain_text('End of notice.')
        expect(frame.locator('script, meta[http-equiv="refresh"], img[src^="https:"]')).to_have_count(0)
        self.assertEqual(self.page.locator('body').get_attribute('data-mail-script-ran'), None)
        self.assertEqual(external, [])
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.page.mouse.move(0, 0)
            self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
            self.assertLessEqual(dialog.bounding_box()['x'] + dialog.bounding_box()['width'], width)
            self.page.screenshot(path=str(self.evidence / f'original-sample-html-{width}.png'))
        dialog.get_by_role('button', name='关闭', exact=True).click()
        expect(dialog).not_to_be_visible()
        with self.fixture.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET html_content=NULL WHERE id=?', (self.email_id,))
            conn.commit()
        self.page.locator('.draft-review-panel').get_by_role('button', name='维护', exact=True).click()
        expect(dialog.locator('pre')).to_have_text(text)
        expect(dialog.locator('pre')).to_have_css('white-space', 'pre-wrap')
        expect(dialog.locator('iframe')).to_have_count(0)
        self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
        self.page.screenshot(path=str(self.evidence / 'original-sample-plain-1920.png'))
        self.assert_clean_browser()

    def test_full_sample_editor_and_original_restore_preserve_classification_input(self):
        body = '样本首行\n\n' + '\n'.join(f'线路 {i}: HKG-{i:04d}' for i in range(80)) + '\n样本最后一行'
        response = self.fixture.client.post('/api/suppliers', headers=self.fixture.headers, json={
            'name': 'Full sample supplier', 'email': 'full@example.com', 'prompt_mode': 'auto',
            'line_custom_fields': [{'name': 'CircuitId', 'description': '提取原邮件线路编号'}],
            'line_query_keywords': ['CircuitId'],
            'email_type_samples': {'割接通知': {'subject': '完整样本', 'content': body}}})
        self.assertEqual(response.status_code, 201)
        supplier_id = response.get_json()['data']['id']
        self.page.goto(self.base + f'/admin/suppliers/{supplier_id}')
        category = self.page.locator('.mail-type-item').filter(has=self.page.locator('.mail-type-name').filter(has_text='割接通知'))
        expect(category.locator('textarea')).to_have_value(body)
        category.get_by_role('button', name='展开编辑', exact=True).click()
        dialog = self.page.get_by_role('dialog', name='割接通知样本全文', exact=True)
        expect(dialog.get_by_role('textbox', name='割接通知正文样本', exact=True)).to_have_value(body)
        revised = body + '\n人工编辑尾行'
        dialog.get_by_role('textbox', name='割接通知正文样本', exact=True).fill(revised)
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width': width, 'height': 800})
            self.page.mouse.move(0, 0)
            self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
            footer = dialog.get_by_role('button', name='关闭', exact=True).bounding_box()
            self.assertLessEqual(footer['y'] + footer['height'], 800)
            self.page.screenshot(path=str(self.evidence / f'classification-sample-editor-{width}.png'))
        dialog.get_by_role('button', name='关闭', exact=True).click()
        expect(category.locator('textarea')).to_have_value(revised)
        self.page.get_by_role('button', name='保存配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        supplier = self.fixture.client.get(f'/api/suppliers/{supplier_id}', headers=self.fixture.headers).get_json()['data']
        self.assertEqual(supplier['email_type_samples']['割接通知']['content'], revised)
        self.assertIn(revised, supplier['supplier_mail_classify_prompt'])

        html = '<p>原始正文<br>第二行</p><table><tr><td>RESTORED-LINE-9821</td></tr></table>'
        with self.fixture.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET html_content=? WHERE id=?', (html, self.email_id))
            conn.commit()
        url = f'/api/supplier-drafts/{self.draft_id}'
        before = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        category.get_by_role('button', name='载入原邮件', exact=True).click()
        expect(category.locator('textarea')).to_have_value(html)
        unchanged = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        self.assertEqual(unchanged['draft'], before['draft'])
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        saved = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        self.assertEqual(saved['draft']['config']['email_type_samples']['割接通知']['content'], html)
        self.assert_clean_browser()

    def test_draft_list_review_and_delete_cancel_then_confirm(self):
        panel = self.open_drafts_list()
        row = panel.locator('.n-data-table-tbody tr').filter(has_text='noc@example.com')
        expect(row).to_have_count(1)
        expect(self.page.locator('.draft-review-panel')).to_have_count(0)
        expect(row.locator('.draft-status-badge')).to_have_css('opacity', '1')
        self.page.screenshot(path=str(self.evidence / 'drafts-list-single-1440.png'), full_page=True)
        panel.screenshot(path=str(self.evidence / 'drafts-panel-single-1440.png'))
        row.get_by_role('button', name='审核配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_be_visible()
        self.page.locator('.supplier-section-actions').get_by_role('button', name='取消', exact=True).click()
        expect(self.page.locator('.draft-review-panel')).to_be_visible()
        url = f'/api/supplier-drafts/{self.draft_id}'
        original = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        mail_before = self.fixture.db.get_email_record_by_id(self.email_id)
        deletes = []
        self.page.on('request', lambda request: deletes.append(request)
            if request.method == 'DELETE' and request.url.endswith(url) else None)
        row.get_by_role('button', name='删除', exact=True).click()
        confirm = self.page.locator('.n-dialog')
        expect(confirm).to_contain_text('删除配置草稿')
        confirm.get_by_role('button', name='取消', exact=True).click()
        expect(confirm).not_to_be_visible()
        expect(row).to_be_visible()
        self.assertEqual(deletes, [])
        current = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        self.assertEqual(current['revision'], original['revision'])
        self.assertEqual(current['draft'], original['draft'])
        row.get_by_role('button', name='删除', exact=True).click()
        expect(confirm).to_be_visible()
        expect(confirm).to_have_css('opacity', '1')
        expect(self.page.locator('.n-modal-container').filter(has=confirm)).to_have_css('opacity', '1')
        self.page.screenshot(path=str(self.evidence / 'draft-delete-confirm-1440.png'), full_page=True)
        confirm.get_by_role('button', name='确认删除', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='配置草稿已删除')).to_be_visible()
        expect(row).to_have_count(0)
        expect(self.page.locator('.drafts-empty-state')).to_be_visible()
        expect(self.page.locator('.draft-review-panel')).to_have_count(0)
        expect(confirm).not_to_be_visible()
        expect(self.page.locator('.n-modal-container').filter(has=confirm)).not_to_be_visible()
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0].post_data_json, {'revision':original['revision']})
        self.assertEqual(self.fixture.client.get(url, headers=self.fixture.headers).status_code, 404)
        mail_after = self.fixture.db.get_email_record_by_id(self.email_id)
        for key in ('subject','content','unconfigured_analysis_json','reply_status','pending_reply_content'):
            self.assertEqual(mail_after[key], mail_before[key])
        self.page.screenshot(path=str(self.evidence / 'draft-delete-empty-1440.png'), full_page=True)
        self.assert_clean_browser()

    def test_draft_delete_failures_keep_list_row_and_selected_detail(self):
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
        panel = self.page.locator('.drafts-list-panel')
        row = panel.locator('.n-data-table-tbody tr').filter(has_text='noc@example.com')
        expect(self.page.locator('.draft-review-panel')).to_be_visible()
        url = f'/api/supplier-drafts/{self.draft_id}'
        original = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        response = {'status':409, 'message':'草稿版本已变化，请刷新后重试'}
        calls = []
        def reject_delete(route):
            if route.request.method != 'DELETE':
                route.continue_()
                return
            calls.append(route.request.post_data_json)
            route.fulfill(status=response['status'], content_type='application/json',
                body=json.dumps({'success':False,'message':response['message']}, ensure_ascii=False))
        pattern = '**/api/supplier-drafts/*'
        self.page.route(pattern, reject_delete)
        try:
            for status, message in ((409,'草稿版本已变化，请刷新后重试'), (500,'删除暂时失败，请稍后重试')):
                with self.subTest(status=status):
                    response.update(status=status, message=message)
                    row.get_by_role('button', name='删除', exact=True).click()
                    self.page.locator('.n-dialog').get_by_role('button', name='确认删除', exact=True).click()
                    expect(self.page.locator('.n-message').filter(has_text=message)).to_be_visible()
                    expect(self.page.locator('.n-dialog')).not_to_be_visible()
                    expect(row).to_be_visible()
                    expect(self.page.locator('.draft-review-panel')).to_be_visible()
                    expect(self.page.locator('.drafts-empty-state')).to_have_count(0)
                    saved = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
                    self.assertEqual(saved['revision'], original['revision'])
                    self.assertEqual(saved['draft'], original['draft'])
            self.page.screenshot(path=str(self.evidence / 'draft-delete-error-1440.png'), full_page=True)
        finally:
            self.page.unroute(pattern, reject_delete)
        self.assertEqual(calls, [{'revision':original['revision']}] * 2)
        self.assert_clean_browser(expected_http_errors=(409,500))

    def test_draft_list_desktop_layout_and_last_page_delete(self):
        added = self.add_list_drafts(25)
        panel = self.open_drafts_list()
        rows = panel.locator('.n-data-table-tbody tr')
        expect(rows).to_have_count(20)
        for status in ('收集样本中','生成中','待审核','生成失败'):
            expect(panel).to_contain_text(status)
            expect(panel.locator('.draft-status-badge').filter(has_text=status).first).to_have_css('opacity', '1')
        expect(panel).to_contain_text(added[-2]['sender'])
        expect(panel.locator('.draft-status-badge').filter(has_text='已启用')).to_have_count(0)
        for width, height in ((1280,900),(1440,1000),(1920,1080)):
            with self.subTest(width=width):
                self.page.set_viewport_size({'width':width,'height':height})
                self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                self.assertTrue(panel.evaluate('(element) => element.scrollWidth <= element.clientWidth + 1'))
                body_scroll = panel.locator('.n-data-table-base-table-body .n-scrollbar-container')
                self.assertTrue(body_scroll.evaluate('(element) => element.scrollWidth <= element.clientWidth + 1'))
                self.page.screenshot(path=str(self.evidence / f'drafts-list-{width}.png'), full_page=True)
        panel.get_by_role('button', name='下一页', exact=True).click()
        expect(rows).to_have_count(1)
        expect(rows.first).to_contain_text('noc@example.com')
        expect(panel.locator('.n-pagination-item--active')).to_have_text('2')
        rows.first.get_by_role('button', name='删除', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='确认删除', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='配置草稿已删除')).to_be_visible()
        expect(rows).to_have_count(20)
        expect(panel.locator('.n-pagination-item--active')).to_have_text('1')
        expect(panel.get_by_role('button', name='上一页', exact=True)).to_be_disabled()
        expect(self.page.locator('.n-dialog')).not_to_be_visible()
        self.assertEqual(self.fixture.client.get('/api/supplier-drafts', headers=self.fixture.headers).get_json()['data']['total'], 20)
        self.assertIsNotNone(self.fixture.db.get_email_record_by_id(self.email_id))
        self.page.set_viewport_size({'width':1280,'height':900})
        self.page.screenshot(path=str(self.evidence / 'drafts-last-page-deleted-1280.png'), full_page=True)
        self.assert_clean_browser()

    def test_settings_validate_and_persist(self):
        panel = self.page.locator('.discovery-settings')
        panel.get_by_text('仅处理指定发件人', exact=True).click()
        panel.get_by_role('button', name='保存设置', exact=True).click()
        expect(panel.get_by_role('alert')).to_contain_text('名单不能为空')
        panel.get_by_role('textbox', name='发件人范围').fill('*@example.com')
        panel.get_by_role('button', name='保存设置', exact=True).click()
        expect(panel.get_by_role('alert')).to_have_count(0)
        self.page.reload()
        expect(panel.get_by_role('textbox', name='发件人范围')).to_have_value('*@example.com')
        self.page.screenshot(path=str(self.evidence / 'settings-1440.png'), full_page=True)
        self.page.set_viewport_size({'width': 1280, 'height': 900})
        self.page.screenshot(path=str(self.evidence / 'settings-1280.png'), full_page=True)
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.set_viewport_size({'width': 1920, 'height': 1080})
        self.page.screenshot(path=str(self.evidence / 'settings-1920.png'), full_page=True)
        self.assertEqual(self.errors, [])

    def test_pending_reply_shows_time_and_original_without_sending(self):
        self.page.goto(self.base + f'/admin/cutover-emails/{self.email_id}')
        expect(self.page.locator('.reply-pending-card')).to_be_visible()
        expect(self.page.locator('.mail-analysis-panel')).to_contain_text('重保期割接')
        expect(self.page.locator('.mail-analysis-heading .n-tag')).to_have_css('opacity', '1')
        self.page.set_viewport_size({'width':1280, 'height':900})
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.screenshot(path=str(self.evidence / 'pending-reply-1280.png'), full_page=True)
        actions = self.page.locator('.reply-pending-actions')
        actions.scroll_into_view_if_needed()
        expect(actions.locator('button')).to_have_count(2)
        expect(actions.locator('button').last).to_be_enabled()
        self.page.screenshot(path=str(self.evidence / 'pending-reply-actions-1280.png'), full_page=True)
        self.assertEqual(self.fixture.db.get_email_record_by_id(self.email_id)['reply_status'], 'pending')
        self.assertEqual(self.errors, [])

    def test_review_save_and_publish(self):
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_be_visible()
        name = self.page.locator('.supplier-form input').first
        name.fill('经人工确认的供应商')
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        self.assertEqual(self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data'], [])
        self.page.screenshot(path=str(self.evidence / 'draft-review-1440.png'), full_page=True)
        self.page.get_by_role('button', name='确认启用', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='确认启用', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        expect(self.page.locator('.drafts-list-panel')).to_be_visible()
        self.assertEqual(len(self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data']), 1)
        panel = self.page.locator('.drafts-list-panel')
        expect(panel.locator('.drafts-total-count')).to_have_text('0')
        self.assertNotIn('draft=', self.page.url)
        panel.locator('.drafts-header-actions').get_by_text('已启用', exact=True).click()
        expect(panel.locator('.n-data-table-tbody tr')).to_have_count(1)
        expect(panel).to_contain_text('经人工确认的供应商')
        panel.get_by_role('button', name='邮件样本', exact=True).click()
        expect(self.page.locator('.draft-review-panel')).to_contain_text('邮件正文')
        expect(self.page.locator('.draft-review-panel .draft-sample-subject')).to_have_text('维护')
        expect(self.page.get_by_role('button', name='审核配置', exact=True)).to_have_count(0)
        self.page.reload()
        expect(panel.get_by_role('radio', name='已启用', exact=True)).to_be_checked()
        expect(self.page.locator('.draft-review-panel')).to_be_visible()
        self.page.screenshot(path=str(self.evidence / 'published-history-1440.png'), full_page=True)
        panel.locator('.drafts-header-actions').get_by_text('未启用', exact=True).click()
        expect(self.page.locator('.draft-review-panel')).to_have_count(0)
        expect(panel.locator('.drafts-empty-state')).to_be_visible()
        self.assert_clean_browser()

    def test_switch_draft_status_resets_pagination_and_detail(self):
        self.add_list_drafts(25)
        panel = self.open_drafts_list()
        expect(panel.locator('.drafts-total-count')).to_have_text('21')
        panel.get_by_role('button', name='下一页', exact=True).click()
        expect(panel.locator('.n-pagination-item--active')).to_have_text('2')
        expect(panel.locator('.n-data-table-tbody tr')).to_have_count(1)
        panel.get_by_role('button', name='邮件样本', exact=True).click()
        expect(self.page.locator('.draft-review-panel')).to_be_visible()
        panel.locator('.drafts-header-actions').get_by_text('已启用', exact=True).click()
        expect(self.page.locator('.draft-review-panel')).to_have_count(0)
        expect(panel.locator('.drafts-total-count')).to_have_text('5')
        expect(panel.locator('.n-data-table-tbody tr')).to_have_count(5)
        expect(panel.locator('.n-pagination-item--active')).to_have_text('1')
        expect(panel.locator('.draft-status-badge')).to_have_text(['已启用'] * 5)
        for width in (1280, 1920):
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            self.page.screenshot(path=str(self.evidence / f'published-history-{width}.png'), full_page=True)
        panel.locator('.drafts-header-actions').get_by_text('未启用', exact=True).click()
        expect(panel.locator('.drafts-total-count')).to_have_text('21')
        expect(panel.locator('.n-data-table-tbody tr')).to_have_count(20)
        expect(panel.locator('.n-pagination-item--active')).to_have_text('1')
        self.assert_clean_browser()

    def test_blank_draft_name_is_blocked_before_save_or_publish(self):
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        name = self.page.locator('.supplier-form input').first
        expect(name).to_have_value('')
        url = f'/api/supplier-drafts/{self.draft_id}'
        mutations = []
        self.page.on('request', lambda request: mutations.append(request.method)
            if url in request.url and request.method in ('PUT', 'POST') else None)
        for value in ('', '   '):
            name.fill(value)
            self.page.get_by_role('button', name='确认启用', exact=True).click()
            expect(self.page.locator('.n-message').filter(has_text='启用前请填写供应商名称').last).to_be_visible()
            expect(name).to_be_focused()
            expect(self.page.locator('.n-dialog')).to_have_count(0)
            self.assertEqual(mutations, [])
        self.page.screenshot(path=str(self.evidence / 'draft-name-required-1440.png'))
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        draft = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        self.assertEqual(draft['draft']['config']['name'], '')
        self.assertEqual(draft['status'], 'review')
        name.fill('人工填写名称后启用')
        self.page.get_by_role('button', name='确认启用', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='确认启用', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        expect(self.page.locator('.drafts-list-panel')).to_be_visible()
        suppliers = self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data']
        self.assertEqual([supplier['name'] for supplier in suppliers], ['人工填写名称后启用'])
        self.assert_clean_browser()

    def test_incomplete_notice_samples_block_publish_but_allow_draft_save(self):
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        self.page.locator('.supplier-form input').first.fill('人工确认供应商')
        notice = self.page.locator('.mail-type-item').filter(
            has=self.page.locator('.mail-type-name').filter(has_text='割接通知'))
        url = f'/api/supplier-drafts/{self.draft_id}'
        mutations = []
        self.page.on('request', lambda request: mutations.append(request.method)
            if url in request.url and request.method in ('PUT', 'POST') else None)
        for selector, message in [('input', '主题样本'), ('textarea', '正文样本')]:
            control = notice.locator(selector)
            original = control.input_value()
            control.fill('   ')
            self.page.get_by_role('button', name='确认启用', exact=True).click()
            expect(self.page.locator('.n-message').filter(has_text=message).last).to_be_visible()
            expect(self.page.locator('.n-dialog')).to_have_count(0)
            self.assertEqual(mutations, [])
            control.fill(original)
        notice.locator('textarea').fill('')
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        saved = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        self.assertEqual(saved['draft']['config']['email_type_samples']['割接通知']['content'], '')
        self.assertEqual(saved['status'], 'review')
        self.assert_clean_browser()

    def test_guard_visible_after_cancel_without_line_tasks(self):
        self.fixture.db.cancel_pending_reply(self.email_id)
        self.page.goto(self.base + f'/admin/cutover-emails/{self.email_id}')
        panel = self.page.locator('.mail-analysis-panel')
        expect(panel).to_contain_text('重保期割接')
        expect(panel.locator('.mail-analysis-heading .n-tag')).to_have_css('opacity', '1')
        expect(panel).to_contain_text('回复已取消')
        expect(panel).to_contain_text('2026-10-14 02:00:00')
        expect(self.page.locator('.api-forward-card')).to_have_count(0)
        expect(self.page.locator('.extraction-panel')).to_have_count(0)
        self.page.screenshot(path=str(self.evidence / 'guard-detail-1440.png'), full_page=True)
        self.page.set_viewport_size({'width': 1280, 'height': 900})
        self.page.screenshot(path=str(self.evidence / 'guard-detail-1280.png'), full_page=True)
        self.page.goto(self.base + '/admin/cutover-tasks')
        expect(self.page.locator('.n-data-table-tbody')).to_contain_text('重保期割接')
        expect(self.page.locator('.n-data-table-tbody')).to_contain_text('回复已取消')
        self.assertEqual(self.errors, [])

    def test_custom_categories_survive_draft_publish_and_formal_edit(self):
        url = f'/api/supplier-drafts/{self.draft_id}'
        draft = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        config = draft['draft']['config']
        config['name'] = '人工确认分类测试供应商'
        config['line_custom_fields'] = [{'name':'circuit_id', 'description':'线路编号'}]
        config['line_query_keywords'] = ['circuit_id']
        self.fixture.client.put(url, headers=self.fixture.headers, json={'revision':draft['revision'], 'config':config})
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        expect(self.page.locator('.mail-type-item')).to_have_count(4)
        expect(self.page.locator('.mail-type-list')).not_to_contain_text('故障邮件')
        self.page.locator('.supplier-section--mail-types').get_by_role('button', name='添加分类', exact=True).click()
        dialog = self.page.get_by_role('dialog', name='添加邮件分类')
        submit = dialog.get_by_role('button', name='添加分类', exact=True)
        submit.click()
        expect(dialog.get_by_role('alert')).to_contain_text('分类名称')
        for name in ('割接通知', '其它', '类' * 33):
            dialog.get_by_role('textbox', name='分类名称', exact=True).fill(name)
            submit.click()
            expect(dialog.get_by_role('alert')).to_be_visible()
        dialog.get_by_role('textbox', name='分类名称', exact=True).fill('  账单通知  ')
        expect(dialog.get_by_role('alert')).to_have_count(0)
        self.page.screenshot(path=str(self.evidence / 'add-category-dialog-1440.png'), full_page=True)
        submit.click()
        expect(dialog).not_to_be_visible()
        category = self.page.locator('.mail-type-item').filter(has_text='账单通知')
        expect(category).to_be_visible()
        category.locator('input').fill('月度账单')
        category.locator('textarea').fill('请核对本月费用。')
        self.page.locator('.supplier-section--mail-types').get_by_role('button', name='添加分类', exact=True).click()
        dialog.get_by_role('textbox', name='分类名称', exact=True).fill('业务公告')
        dialog.get_by_role('textbox', name='分类名称', exact=True).press('Enter')
        expect(dialog).not_to_be_visible()
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        saved = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        self.assertIn('业务公告', saved['draft']['config']['email_type_samples'])
        self.page.reload()
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        expect(self.page.locator('.mail-type-item').filter(has_text='账单通知').locator('textarea')).to_have_value('请核对本月费用。')
        self.page.set_viewport_size({'width':1280,'height':900})
        self.page.locator('.mail-type-item').filter(has_text='业务公告').scroll_into_view_if_needed()
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.screenshot(path=str(self.evidence / 'custom-categories-1280.png'), full_page=True)
        self.page.get_by_role('button', name='确认启用', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='确认启用', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        expect(self.page.locator('.drafts-list-panel')).to_be_visible()
        supplier = self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data'][0]
        self.assertIn('账单通知', supplier['supplier_mail_classify_prompt'])
        self.page.goto(self.base + f'/admin/suppliers/{supplier["id"]}')
        category = self.page.locator('.mail-type-item').filter(has_text='账单通知')
        expect(category.locator('textarea')).to_have_value('请核对本月费用。')
        category.get_by_role('button', name='移除分类', exact=True).click()
        self.page.get_by_role('button', name='保存配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        saved = self.fixture.client.get(f'/api/suppliers/{supplier["id"]}', headers=self.fixture.headers).get_json()['data']
        self.assertNotIn('账单通知', saved['email_type_samples'])
        self.assertIn('业务公告', saved['email_type_samples'])
        self.assertEqual(self.errors, [])

    def test_legacy_fault_sample_is_visible_as_removable_custom_category(self):
        url = f'/api/supplier-drafts/{self.draft_id}'
        draft = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']
        draft['draft']['config']['email_type_samples']['故障邮件'] = {'subject':'故障', 'content':'原有故障样本'}
        self.fixture.client.put(url, headers=self.fixture.headers,
            json={'revision':draft['revision'], 'config':draft['draft']['config']})
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        category = self.page.locator('.mail-type-item').filter(has_text='故障邮件')
        expect(category.locator('textarea')).to_have_value('原有故障样本')
        expect(category.get_by_role('button', name='移除分类', exact=True)).to_be_visible()
        self.assertEqual(self.errors, [])

    def test_generated_complete_fixed_field_rules_survive_review_edit_save_and_publish(self):
        subject = 'Maintenance Reference 维护通知'
        content = ('Maintenance Reference: MR-123\nCircuit Title: LINK-A\n'
                   'Start Time: 2026-11-01 02:00 UTC\nEnd Time: 2026-11-01 04:00 UTC\n'
                   'Expected Outage duration: 4 minutes\n'
                   'Reason: 光传输设备升级\nLocation: Shanghai POP')
        self.fixture.repo.ingest(EmailMessage(
            uid=2, sender='fixed-rules@example.com', recipients=['inbox@example.com'],
            subject=subject, content=content, received_date=datetime.now(),
        ), 'inbox@example.com')
        self.fixture.classify()
        job = self.fixture.repo.claim()
        self.assertEqual(job['task_type'], 'supplier_config_draft')
        complete_rules = {
            'carrier_ticket_no': (
                '从邮件正文 Maintenance Reference 或 CarrierRef 标签后提取运营商维护单号。\n'
                '保留原文编号，不将 Circuit Title 对应的线路标识当作维护单号；无法识别时返回空字符串。'),
            'ImpactDuration': (
                '原文明示线路有保护且不会中断时返回 0m。\n'
                '否则优先读取 Expected Outage duration 表示的单次实际中断时长，按单位换算为分钟，输出整数加 m。\n'
                '没有明确时长但存在实际中断起止时间时，用结束减去开始并正确处理跨天。\n'
                '不要将 Start Time 与 End Time 的整个维护窗口当作中断时长。\n'
                '多次等长中断填写单次时长，次数写入 InteruptionsCounts；明确时长和实际中断起止均缺失时返回空字符串。'),
            'ImpactType': (
                '原文明示线路有保护或不会中断时输出 protected。\n'
                '否则根据 Expected Outage duration 的明确单次时长乘以中断次数计算总中断分钟数；'
                '无明确时长时才使用实际中断起止时间计算。\n'
                '总中断小于 5 分钟输出 momentary_interrupted，大于或等于 5 分钟输出 interrupted；'
                '无法确定时返回空字符串。'),
        }
        self.fixture.complete(job, {
            'config': {
                'name': '固定字段规则测试供应商', 'prompt_mode': 'auto', 'fixed_field_rules': complete_rules,
                'line_custom_fields': [{'name': 'CircuitTitle', 'description': '提取 Circuit Title 标签后的线路标识'}],
                'line_query_keywords': ['CircuitTitle'],
                'email_type_samples': {'割接通知': {'subject': subject, 'content': content}},
            },
            'evidence': [
                'carrier_ticket_no：邮件使用 Maintenance Reference 表示维护单号，覆盖默认 No 标签。',
                'ImpactDuration：Expected Outage duration 明确给出单次中断时长，未给出实际中断起止。',
                'ImpactType：依据明确单次时长与次数判断影响类型，沿用受保护与 5 分钟分界。',
                '其余 7 项沿用默认：Start Time / End Time 与 UTC 可用于时间转换；Reason 和 Location 标签适用；'
                '未提供备用时间、独立线路影响窗口和多次中断证据，使用对应默认规则。',
            ],
            'unresolved_questions': [],
        })
        url = f"/api/supplier-drafts/{job['draft_id']}"
        generated = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']['draft']
        self.assertNotIn('fixed_field_supplements', generated)
        rules = generated['config']['fixed_field_rules']
        self.assertEqual(rules, complete_rules)
        definitions = self.fixture.client.get('/api/suppliers/field-defaults', headers=self.fixture.headers).get_json()['data']
        defaults = {field['name']: field['description']
                    for field in definitions['top_fields'] + definitions['line_fields']}
        for name in complete_rules:
            self.assertNotIn(defaults[name], rules[name])
        self.assertNotIn('* No:', rules['carrier_ticket_no'])
        self.assertNotIn('缺少可计算的中断起止时间时返回空字符串', rules['ImpactDuration'])

        self.page.goto(self.base + f"/admin/suppliers?draft={job['draft_id']}")
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        self.page.locator('.supplier-form input').first.fill('人工确认固定字段供应商')
        workbench = self.page.locator('.fixed-field-workbench')
        expect(workbench.get_by_role('tab')).to_have_count(10)
        expect(self.page.locator('.fixed-field-summary')).to_contain_text('已配置 3')
        expect(self.page.locator('.fixed-field-summary')).to_contain_text('默认 7')
        for name in complete_rules:
            self.page.locator(f'#fixed-field-tab-{name}').click()
            expect(self.page.locator(f'#fixed-field-panel-{name} textarea')).to_have_value(rules[name])
            expect(self.page.locator(f'#fixed-field-tab-{name}')).to_contain_text('已配置')
        for name in ('carrier_ticket_no', 'ImpactDuration'):
            self.page.locator(f'#fixed-field-tab-{name}').click()
            width = 1440 if name == 'carrier_ticket_no' else 1280
            self.page.set_viewport_size({'width': width, 'height': 1000})
            for tag in self.page.locator(f'#fixed-field-panel-{name} .n-tag').all():
                expect(tag).to_have_css('opacity', '1')
            self.page.wait_for_function(
                "element => element.getAnimations({subtree:true}).every(animation => animation.playState !== 'running' && !animation.pending)",
                arg=workbench.element_handle(),
            )
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            self.assertTrue(workbench.evaluate('element => element.scrollWidth <= element.clientWidth + 1'))
            workbench.screenshot(path=str(self.evidence / f'generated-fixed-{name}-{width}.png'))
        impact_editor = self.page.locator('#fixed-field-panel-ImpactDuration textarea')
        edited_rules = {**rules, 'ImpactDuration':rules['ImpactDuration'] + '\n人工确认：时长仅给出上限或范围时返回空字符串，不将上限当作确定时长。'}
        impact_editor.fill(edited_rules['ImpactDuration'])
        expect(impact_editor).to_have_value(edited_rules['ImpactDuration'])
        for name in ('cutover_reason', 'cutover_timezone'):
            self.page.locator(f'#fixed-field-tab-{name}').click()
            expect(self.page.locator(f'#fixed-field-panel-{name} textarea')).to_have_value(defaults[name])
            expect(self.page.locator(f'#fixed-field-tab-{name}')).to_contain_text('使用默认')
            expect(self.page.locator('.fixed-field-editor').get_by_role('button', name='恢复默认', exact=True)).to_be_disabled()
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        saved = self.fixture.client.get(url, headers=self.fixture.headers).get_json()['data']['draft']['config']
        self.assertEqual(saved['fixed_field_rules'], edited_rules)
        self.page.reload()
        self.page.locator('.draft-review-panel').get_by_role('button', name='审核配置', exact=True).click()
        self.page.locator('#fixed-field-tab-ImpactDuration').click()
        expect(self.page.locator('#fixed-field-panel-ImpactDuration textarea')).to_have_value(edited_rules['ImpactDuration'])
        self.page.get_by_role('button', name='确认启用', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='确认启用', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        expect(self.page.locator('.drafts-list-panel')).to_be_visible()
        supplier = self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data'][0]
        self.assertEqual(supplier['fixed_field_rules'], edited_rules)
        prompt = supplier['cutover_extract_prompt']
        for name, rule in edited_rules.items():
            self.assertIn(rule, prompt)
            self.assertNotIn(defaults[name], prompt)
        for name in set(defaults) - set(edited_rules):
            self.assertNotIn(name, supplier['fixed_field_rules'])
            self.assertIn(defaults[name], prompt)
        self.assertNotIn('* No:', prompt)
        self.assertNotIn('缺少可计算的中断起止时间时返回空字符串', prompt)
        self.assert_clean_browser()
