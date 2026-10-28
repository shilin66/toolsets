import json
import re
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server

import api_server
from models import EmailMessage
from rpa.session_config import PortalSessionSettings
from rpa.user_sessions import PortalSessionRegistry
from tests.api import test_supplier_drafts_api as fixture
from tests.ui.test_cutover_regeneration_ui import QuietRequestHandler


class SupplierDiscoveryUiTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.SupplierDraftApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        registry = PortalSessionRegistry(self.fixture.db, self.fixture.tmp.name,
                                        PortalSessionSettings.model_construct())
        self.addCleanup(registry.close)
        sessions = patch.object(api_server, '_portal_session_service', registry)
        sessions.start()
        self.addCleanup(sessions.stop)
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
        self.page.get_by_role('button', name='管理员登录', exact=True).click()
        self.page.get_by_role('textbox', name='API Key').fill('test-key')
        self.page.get_by_role('button', name='登录', exact=True).click()
        expect(self.page.locator('.discovery-settings')).to_be_visible()
        self.evidence = Path(__file__).resolve().parents[2] / '.qa' / 'supplier-discovery'
        self.evidence.mkdir(parents=True, exist_ok=True)

    def select_collected_mail(self, email_id):
        mail = self.fixture.db.get_email_record_by_id(email_id)
        self.page.get_by_label('选择邮件样本', exact=True).click()
        self.page.locator('.n-base-select-option').filter(has_text=' · ' + mail['subject'] + ' · ').click()

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

    def open_draft_editor(self):
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
        expect(self.page.locator('.supplier-compare')).to_be_visible()

    def test_draft_review_integrates_samples_questions_and_advanced_evidence(self):
        second_id = self.fixture.mail(2)
        self.fixture.classify()
        with self.fixture.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET subject=?, content=?, html_content=? WHERE id=?',
                ('第二封维护通知', 'Second notice ServiceId 00022', '<p>Second notice</p><table><tr><td>00022</td></tr></table>', second_id))
            draft = json.loads(conn.execute('SELECT draft_json FROM supplier_drafts WHERE id=?', (self.draft_id,)).fetchone()[0])
            draft['unresolved_questions'] = ['reply_email | 正文未明确指定回复邮箱，请人工确认。',
                'cutover_backup_time | 当前样本未提供备用窗口，请确认是否需要。',
                'ImpactDuration | 请确认 Duration 是否为单次中断时长。',
                '请核对附件是否覆盖全部线路。']
            draft['evidence'] = ['仅在高级配置展示的生成依据']
            conn.execute('UPDATE supplier_drafts SET draft_json=? WHERE id=?', (json.dumps(draft), self.draft_id))
            conn.commit()
        panel = self.open_drafts_list()
        expect(panel.get_by_role('button', name='邮件样本', exact=True)).to_have_count(0)
        panel.get_by_role('button', name='审核配置', exact=True).click()
        expect(self.page.locator('.draft-review-panel')).to_have_count(0)
        expect(self.page.locator('.supplier-identity')).to_contain_text('正文未明确指定回复邮箱')
        expect(self.page.locator('[data-field=cutover_backup_time]')).to_contain_text('当前样本未提供备用窗口')
        expect(self.page.locator('.review-line-rule[data-field=ImpactDuration]')).to_contain_text('请确认 Duration 是否为单次中断时长')
        expect(self.page.locator('.review-general-questions')).to_contain_text('请核对附件是否覆盖全部线路')
        expect(self.page.get_by_text('仅在高级配置展示的生成依据', exact=True)).to_have_count(0)
        self.page.get_by_role('button', name='已收集的邮件（2）', exact=True).click()
        expect(self.page.frame_locator('.review-mail-frame').get_by_role('cell', name='00022')).to_be_visible()
        calls = self.mock_review()
        self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        expect(self.page.locator('.review-result-status')).to_be_visible()
        self.assertIn('00022', calls[-1]['content'])
        # Viewing/testing another message must not replace stored classification samples.
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        stored = self.fixture.client.get(f'/api/supplier-drafts/{self.draft_id}', headers=self.fixture.headers).get_json()['data']
        self.assertEqual(stored['draft']['config']['email_type_samples']['割接通知']['content'], '维护正文')
        self.select_collected_mail(self.email_id)
        expect(self.page.locator('.review-mail-body')).to_contain_text('维护正文')
        expect(self.page.locator('.review-result-status')).to_contain_text('样本或规则已修改')
        self.select_collected_mail(second_id)
        expect(self.page.frame_locator('.review-mail-frame').get_by_role('cell', name='00022')).to_be_visible()
        self.page.get_by_role('button', name='设为此分类样本', exact=True).click()
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存').last).to_be_visible()
        self.open_advanced()
        evidence = self.page.locator('.review-generation-evidence')
        evidence.locator('summary').click()
        expect(evidence).to_contain_text('仅在高级配置展示的生成依据')
        self.page.screenshot(path=str(self.evidence / 'consolidated-advanced-evidence-1440.png'))
        self.page.get_by_role('button', name='返回邮件核对', exact=True).click()
        self.page.set_viewport_size({'width':1920, 'height':1250})
        expect(self.page.frame_locator('.review-mail-frame').get_by_role('cell', name='00022')).to_be_visible()
        expect(self.page.locator('.n-message')).to_have_count(0, timeout=10000)
        self.page.locator('.workspace').evaluate('(e)=>e.scrollTo({top:0,behavior:"instant"})')
        self.page.screenshot(path=str(self.evidence / 'consolidated-review-1920.png'))
        self.assert_clean_browser()

    def test_draft_failure_retry_and_collecting_states_share_review_page(self):
        from unconfigured_mail import ANALYSIS
        self.fixture.db.set_system_settings({}, {ANALYSIS:False})
        self.fixture.mail(90, sender='failed@example.com')
        self.fixture.classify()
        failed_job = self.fixture.repo.claim()
        self.fixture.repo.fail(failed_job, 'AI 返回格式不完整，请重试生成')
        failed_id = failed_job['draft_id']
        self.fixture.mail(91, sender='collecting@example.com')
        self.fixture.classify('割接取消')
        panel = self.open_drafts_list()
        failed_row = panel.locator('.n-data-table-tbody tr').filter(has_text='failed@example.com')
        expect(failed_row).to_contain_text('AI 返回格式不完整')
        expect(panel.get_by_role('button', name='邮件样本', exact=True)).to_have_count(0)
        self.page.screenshot(path=str(self.evidence / 'consolidated-list-states-1440.png'))
        failed_row.get_by_role('button', name='查看邮件', exact=True).click()
        state = self.page.locator('.review-draft-state')
        expect(state).to_contain_text('AI 返回格式不完整')
        expect(self.page.locator('.review-mail-body')).to_contain_text('维护正文')
        expect(self.page.get_by_role('button', name='保存草稿', exact=True)).to_have_count(0)
        expect(self.page.get_by_role('button', name='识别这封邮件', exact=True)).to_have_count(0)
        self.page.screenshot(path=str(self.evidence / 'consolidated-failure-1440.png'))
        retry_url = f'**/api/supplier-drafts/{failed_id}/retry'
        self.page.route(retry_url, lambda route: route.fulfill(status=409, content_type='application/json',
            body=json.dumps({'success':False, 'message':'当前任务暂不能重试'})))
        state.get_by_role('button', name='重试失败任务', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='当前任务暂不能重试')).to_be_visible()
        expect(state).to_contain_text('AI 返回格式不完整')
        self.page.unroute(retry_url)
        state.get_by_role('button', name='重试失败任务', exact=True).click()
        expect(state).to_contain_text('生成中')
        expect(state.get_by_role('button', name='重试失败任务', exact=True)).to_have_count(0)
        self.page.get_by_role('button', name='返回列表', exact=True).click()
        expect(failed_row).to_contain_text('生成中')
        job = self.fixture.repo.claim()
        self.fixture.repo.fail(job, '生成再次失败')
        panel.get_by_role('button', name='刷新', exact=True).click()
        expect(failed_row).to_contain_text('生成再次失败')
        failed_row.get_by_role('button', name='重试失败任务', exact=True).click()
        expect(failed_row).to_contain_text('生成中')
        collecting = panel.locator('.n-data-table-tbody tr').filter(has_text='collecting@example.com')
        collecting.get_by_role('button', name='查看邮件', exact=True).click()
        expect(state).to_contain_text('等待收到割接通知后生成配置')
        expect(self.page.locator('.review-mail-body')).to_contain_text('维护正文')
        self.fixture.db.add_email_record(92, sender='collecting@example.com', receiver='inbox@example.com',
            subject='新增收集邮件', content='追加样本正文')
        with self.fixture.db.get_connection() as conn:
            new_id = conn.execute('SELECT id FROM email_records WHERE email_id=92').fetchone()[0]
            candidate = conn.execute("SELECT id FROM supplier_drafts WHERE sender='collecting@example.com'").fetchone()[0]
            conn.execute("UPDATE email_records SET mail_type='割接提醒' WHERE id=?", (new_id,))
            conn.execute('INSERT INTO supplier_draft_samples(draft_id,email_records_id) VALUES (?,?)', (candidate, new_id))
            conn.commit()
        state.get_by_role('button', name='刷新状态', exact=True).click()
        expect(self.page.get_by_role('button', name='已收集的邮件（2）', exact=True)).to_be_visible()
        self.select_collected_mail(new_id)
        expect(self.page.locator('.review-mail-body')).to_contain_text('追加样本正文')
        self.assert_clean_browser(expected_http_errors=(409,))

    def test_collected_mail_pagination_failure_retry_and_unmount(self):
        for uid in range(100, 121):
            self.fixture.db.add_email_record(uid, sender='noc@example.com', receiver='inbox@example.com',
                subject=f'通知 {uid}', content=f'线路编号 SAMPLE-{uid}')
            with self.fixture.db.get_connection() as conn:
                record_id = conn.execute('SELECT id FROM email_records WHERE email_id=?', (uid,)).fetchone()[0]
                conn.execute("UPDATE email_records SET mail_type='割接通知' WHERE id=?", (record_id,))
                conn.execute('INSERT INTO supplier_draft_samples(draft_id,email_records_id) VALUES (?,?)', (self.draft_id, record_id))
                conn.commit()
        self.open_draft_editor()
        self.page.get_by_role('button', name='已收集的邮件（22）', exact=True).click()
        expect(self.page.locator('.review-mail-body')).to_contain_text('SAMPLE-120')
        picker = self.page.locator('.review-collected-picker')
        picker.get_by_role('button', name='下一页', exact=True).click()
        expect(picker.locator('.n-pagination-item--active')).to_have_text('2')
        expect(self.page.locator('.review-mail-body')).to_contain_text('SAMPLE-100')
        failed_url = f'**/api/emails/{self.email_id}/source'
        self.page.route(failed_url, lambda route: route.fulfill(status=500, content_type='application/json',
            body=json.dumps({'success':False,'message':'邮件暂时不可读取'})))
        self.select_collected_mail(self.email_id)
        expect(self.page.locator('.review-mail-body')).to_contain_text('邮件暂时不可读取')
        expect(self.page.locator('.review-mail-body')).not_to_contain_text('SAMPLE-100')
        expect(self.page.get_by_role('button', name='识别这封邮件', exact=True)).to_be_disabled()
        self.page.unroute(failed_url)
        self.page.locator('.review-mail-body').get_by_role('button', name='重试读取', exact=True).click()
        expect(self.page.locator('.review-mail-body')).to_contain_text('维护正文')
        self.page.get_by_role('button', name='返回列表', exact=True).click()
        expect(self.page.locator('.draft-review-panel')).to_have_count(0)
        self.assert_clean_browser(expected_http_errors=(500,))

    def open_advanced(self):
        self.page.get_by_role('button', name='高级配置', exact=True).click()
        expect(self.page.locator('.supplier-advanced-config')).to_be_visible()

    def mock_review(self):
        calls = []
        def preview(route):
            calls.append(route.request.post_data_json)
            reason = '更换故障板卡' if 'Reason 段落' in calls[-1]['cutover_extract_prompt'] else '网络维护'
            route.fulfill(content_type='application/json', body=json.dumps({'success': True, 'data': {
                'extract_result': json.dumps({'carrier_ticket_no':'CRQ1-85090548414',
                    'cutover_time':'2026-04-12 06:00:00/2026-04-12 12:00:00', 'cutover_timezone':'Asia/Shanghai',
                    'cutover_reason':reason, 'location':'Frankfurt', 'line_query_keywords':['ServiceId'],
                    'line_array':[{'ServiceId':'001234','ImpactDuration':'300m'},
                                  {'ServiceId':'005678','OrderNumber':'009870','ImpactDuration':'300m'}]}, ensure_ascii=False)}}))
        self.page.route('**/api/suppliers/preview-extract', preview)
        return calls

    def add_identifier(self, name='ServiceId', rule='读取每行的 Service ID，保留前导零。', query=True):
        self.page.get_by_role('button', name='添加一种线路编号', exact=True).click()
        dialog = self.page.locator('.review-identifier-dialog')
        dialog.get_by_role('textbox', name='字段 key', exact=True).fill(name)
        dialog.get_by_role('textbox', name='从哪里提取', exact=True).fill(rule)
        if not query:
            dialog.get_by_role('checkbox').uncheck()
        dialog.get_by_role('button', name='添加', exact=True).click()
        return dialog

    def test_operator_draft_guide_source_and_custom_identifiers(self):
        self.open_draft_editor()
        expect(self.page.locator('.draft-operator-guide')).to_have_count(0)
        expect(self.page.locator('.supplier-advanced-config')).to_have_count(0)
        expect(self.page.get_by_role('textbox', name='字段 key', exact=True)).to_have_count(0)
        name = self.page.get_by_role('textbox', name='供应商名称', exact=True)
        name.fill('运营审核供应商')
        self.page.get_by_role('button', name='已收集的邮件（1）', exact=True).click()
        expect(self.page.locator('.review-mail-body')).to_contain_text('维护正文')
        self.page.get_by_role('button', name='配置中的样本', exact=True).click()
        expect(name).to_have_value('运营审核供应商')
        expect(self.page.get_by_role('button', name='添加服务编号', exact=True)).to_have_count(0)
        self.add_identifier()
        duplicate = self.add_identifier('ServiceId', '此重复要求不能覆盖已有规则。')
        expect(duplicate).to_contain_text('已存在')
        duplicate.get_by_role('button', name='取消', exact=True).click()
        expect(self.page.locator('.review-query-row')).to_have_count(1)
        expect(self.page.locator('.review-query-row').get_by_role('checkbox', name='ServiceId', exact=True)).to_be_checked()
        self.page.get_by_role('button', name='修正识别方式：ServiceId', exact=True).click()
        correction = self.page.locator('.review-correction-dialog')
        correction.get_by_role('textbox').fill('读取每行的 Service ID，保留前导零。')
        correction.get_by_role('button', name='应用修正', exact=True).click()
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        saved = self.fixture.client.get(f'/api/supplier-drafts/{self.draft_id}', headers=self.fixture.headers).get_json()['data']
        self.assertEqual(saved['draft']['config']['line_query_keywords'], ['ServiceId'])
        self.assertEqual(saved['draft']['config']['name'], '运营审核供应商')
        self.assertEqual(saved['draft']['config']['line_custom_fields'][0]['description'], '读取每行的 Service ID，保留前导零。')
        self.assertEqual(saved['status'], 'review')
        self.open_advanced()
        expect(self.page.get_by_role('textbox', name='字段 key', exact=True)).to_have_value('ServiceId')
        self.page.get_by_role('button', name='返回邮件核对', exact=True).click()
        expect(self.page.locator('.supplier-compare')).to_be_visible()
        self.assert_clean_browser()

    def test_draft_test_is_explicit_and_displays_business_labels(self):
        self.open_draft_editor()
        self.page.get_by_role('textbox', name='供应商名称', exact=True).fill('Colt')
        self.page.get_by_role('button', name='编辑样本', exact=True).click()
        sample_dialog = self.page.locator('.mail-sample-editor-dialog')
        sample_dialog.get_by_role('textbox', name='割接通知主题样本', exact=True).fill('Colt Planned Maintenance — CRQ1-85090548414')
        body = """<h3>Planned Outage Notification</h3><p>Dear Customer,</p>
            <p><b>Maintenance window:</b> 11 April 2026 22:00 – 12 April 2026 04:00 GMT</p>
            <p><b>Reason:</b> Replace a degraded card on the long-distance network in Frankfurt.</p>
            <table border="1" cellpadding="8"><tr><th>Service ID</th><th>Order Number</th></tr>
            <tr><td>001234</td><td>009870</td></tr><tr><td>005678</td><td>009871</td></tr></table>
            <p>Please reply to maintenance@example.com.</p><script>parent.document.body.dataset.unsafe='yes'</script>
            <img src="https://mail-preview.invalid/tracker">"""
        sample_dialog.get_by_role('textbox', name='割接通知正文样本', exact=True).fill(body)
        sample_dialog.get_by_role('button', name='关闭', exact=True).click()
        frame = self.page.frame_locator('.review-mail-frame')
        expect(frame.get_by_role('cell', name='001234', exact=True)).to_be_visible()
        self.assertIsNone(self.page.locator('body').get_attribute('data-unsafe'))
        self.assertEqual(self.page.locator('.review-mail-frame').get_attribute('sandbox'), '')
        self.add_identifier()
        calls = self.mock_review()
        self.assertEqual(calls, [])
        self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        result = self.page.locator('.supplier-results-pane')
        expect(result).to_contain_text('待人工核对')
        expect(result).to_contain_text('001234')
        expect(result).to_contain_text('OrderNumber')  # Custom keys are not translated; includes later-row columns.
        expect(result).to_contain_text('单次中断时长')
        expect(self.page.locator('.extract-result-dialog')).to_have_count(0)
        self.assertEqual(calls[0]['content'], body)
        self.assertEqual(calls[0]['attachments'], [])
        for width in (1280, 1440, 1920, 2560):
            self.page.set_viewport_size({'width':width, 'height':1100})
            self.page.locator('.workspace').evaluate('(e)=>e.scrollTo({top:0,behavior:"instant"})')
            self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
            left = self.page.locator('.supplier-mail-pane').bounding_box()
            right = result.bounding_box()
            self.assertLessEqual(left['x'] + left['width'], right['x'])
            workspace = self.page.locator('.workspace').bounding_box()
            editor = self.page.locator('.supplier-form-view').bounding_box()
            self.assertLessEqual(editor['x'] - workspace['x'], 40)
            self.assertLessEqual(workspace['x'] + workspace['width'] - editor['x'] - editor['width'], 40)
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            self.page.screenshot(path=str(self.evidence / f'compare-draft-{width}.png'))
            if width == 1280:
                self.page.locator('.review-query-options').evaluate('(e)=>e.scrollIntoView({block:"center",behavior:"instant"})')
                button = self.page.get_by_role('button', name='重新识别', exact=True).bounding_box()
                self.assertGreaterEqual(button['y'], 0)
                self.assertLessEqual(button['y'] + button['height'], 1100)
                self.page.screenshot(path=str(self.evidence / 'compare-lines-1280.png'))
        self.assertEqual(self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data'], [])
        self.assert_clean_browser()

    def test_configured_sample_keeps_source_attachments_and_equal_panes(self):
        root = Path(self.fixture.tmp.name)
        path = root / 'email_attachments' / 'sample' / 'services.csv'
        path.parent.mkdir(parents=True)
        path.write_text('CircuitId,OrderNumber\n001234,000456\n')
        with self.fixture.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET attachments=? WHERE id=?', (json.dumps([path.relative_to(root).as_posix()]), self.email_id))
            # Simulate a legacy draft without the new source reference in its sample.
            row = conn.execute('SELECT draft_json FROM supplier_drafts WHERE id=?', (self.draft_id,)).fetchone()
            value = json.loads(row[0])
            value['config']['email_type_samples']['割接通知'].pop('source_email_records_id', None)
            conn.execute('UPDATE supplier_drafts SET draft_json=? WHERE id=?', (json.dumps(value), self.draft_id))
            conn.commit()
        with patch.object(api_server, 'DATA_DIR', root):
            self.open_draft_editor()
            listing = self.page.locator('.cw-attachment-list')
            expect(listing).to_contain_text('services.csv')
            expect(self.page.locator('.supplier-compare').get_by_role('button', name='选择附件', exact=True)).to_have_count(0)
            listing.get_by_role('button', name='预览 services.csv', exact=True).click()
            expect(self.page.locator('.cw-attachment-table')).to_contain_text('001234')
            for width in (1280, 1920):
                self.page.set_viewport_size({'width':width,'height':1000})
                left = self.page.locator('.supplier-mail-pane').bounding_box()
                right = self.page.locator('.supplier-results-pane').bounding_box()
                self.assertAlmostEqual(left['y'], right['y'], delta=1)
                self.assertAlmostEqual(left['height'], right['height'], delta=1)
                self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                self.page.screenshot(path=str(self.evidence / f'configured-attachments-equal-{width}.png'))
            self.page.get_by_role('button', name='已收集的邮件（1）', exact=True).click()
            expect(listing).to_contain_text('services.csv')
            expect(self.page.locator('.supplier-compare').get_by_role('button', name='选择附件', exact=True)).to_have_count(0)
            self.page.get_by_role('button', name='设为此分类样本', exact=True).click()
            self.page.get_by_role('button', name='配置中的样本', exact=True).click()
            expect(listing).to_contain_text('services.csv')
            self.page.get_by_role('button', name='保存草稿', exact=True).click()
            expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
            self.page.reload()
            expect(listing).to_contain_text('services.csv')
            self.page.get_by_role('textbox', name='供应商名称', exact=True).fill('Source Supplier')
            self.page.get_by_role('button', name='确认启用', exact=True).click()
            self.page.locator('.n-dialog').get_by_role('button', name='确认启用', exact=True).click()
            expect(self.page).to_have_url(re.compile(r'/admin/suppliers$'))
            with self.fixture.db.get_connection() as conn:
                supplier_id = conn.execute('SELECT published_supplier_id FROM supplier_drafts WHERE id=?', (self.draft_id,)).fetchone()[0]
            self.page.goto(self.base + f'/admin/suppliers/{supplier_id}')
            expect(listing).to_contain_text('services.csv')
            listing.get_by_role('button', name='预览 services.csv', exact=True).click()
            expect(self.page.locator('.cw-attachment-table')).to_contain_text('000456')
            self.assert_clean_browser()

    def test_sample_attachments_share_task_preview_for_collected_and_local_files(self):
        root = Path(self.fixture.tmp.name)
        path = root / 'email_attachments' / 'sample' / ('a'*32+'-services.csv')
        path.parent.mkdir(parents=True)
        path.write_text('CircuitId,OrderNumber\n001234,000456\n')
        with self.fixture.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET attachments=? WHERE id=?', (json.dumps([path.relative_to(root).as_posix()]), self.email_id))
            conn.commit()
        with patch.object(api_server, 'DATA_DIR', root):
            self.open_draft_editor()
            calls = self.mock_review()
            self.page.get_by_role('button', name='已收集的邮件（1）', exact=True).click()
            listing = self.page.locator('.cw-attachment-list')
            expect(listing).to_contain_text('services.csv')
            expect(listing).not_to_contain_text('a'*32)
            listing.get_by_role('button', name='预览 services.csv', exact=True).click()
            expect(self.page.locator('.cw-attachment-table')).to_contain_text('001234')
            expect(self.page.locator('.cw-attachment-table')).to_contain_text('000456')
            self.page.set_viewport_size({'width':1440,'height':1100})
            self.page.screenshot(path=str(self.evidence / 'sample-attachment-csv.png'))
            self.page.get_by_role('button', name='← 返回邮件正文', exact=True).click()
            expect(self.page.locator('.review-mail-body')).to_be_visible()
            self.open_advanced()
            self.page.locator('.n-upload input[type=file]').set_input_files({
                'name':'details.txt','mimeType':'text/plain','buffer':'Circuit 000123\n上海'.encode()})
            self.page.get_by_role('button', name='返回邮件核对', exact=True).click()
            expect(listing.locator('.cw-attachment-row')).to_have_count(2)
            listing.get_by_role('button', name='预览 details.txt', exact=True).click()
            expect(self.page.locator('.cw-preview-text')).to_contain_text('Circuit 000123')
            expect(self.page.locator('.cw-preview-text')).to_contain_text('上海')
            self.assertEqual(calls, [])
            for width in (1280, 1920):
                self.page.set_viewport_size({'width':width,'height':1100})
                self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            self.page.screenshot(path=str(self.evidence / 'sample-attachment-text.png'))
            listing.get_by_role('button', name='删除 details.txt', exact=True).click()
            expect(self.page.locator('.cw-attachment-preview')).to_have_count(0)
            expect(listing.locator('.cw-attachment-row')).to_have_count(1)
            expect(self.page.locator('.review-mail-body')).to_be_visible()
            self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
            expect(self.page.locator('.review-result-status')).to_be_visible()
            self.assertEqual(calls[0]['attachments'], [path.relative_to(root).as_posix()])
            self.assert_clean_browser()

    def test_manual_supplier_eml_import_populates_sample_and_test_attachments(self):
        from tests.mail.test_supplier_eml import sample_eml
        self.page.goto(self.base + '/admin/suppliers/new')
        source = self.page.locator('.supplier-start input[type=file]')
        with self.page.expect_file_chooser() as chooser:
            self.page.get_by_role('button', name='导入 EML 邮件', exact=True).click()
        chooser.value.set_files({'name':'notice.eml', 'mimeType':'message/rfc822', 'buffer':sample_eml()})
        expect(self.page.get_by_role('textbox', name='割接通知主题样本', exact=True)).to_have_value('割接通知 CRQ-001')
        expect(self.page.get_by_role('textbox', name='来信发件地址', exact=True)).to_have_value('notice@example.com')
        expect(self.page.get_by_role('textbox', name='供应商名称', exact=True)).to_have_value('')
        expect(self.page.locator('.supplier-start')).to_contain_text('已带入 1 个附件')
        # A failed second import must retain the successful first sample.
        source.set_input_files({'name':'bad.eml', 'mimeType':'message/rfc822', 'buffer':b'invalid'})
        expect(self.page.locator('.supplier-start [role=alert]')).to_be_visible()
        expect(self.page.get_by_role('textbox', name='割接通知主题样本', exact=True)).to_have_value('割接通知 CRQ-001')
        self.page.get_by_role('textbox', name='供应商名称', exact=True).fill('手动供应商')
        self.page.get_by_role('button', name='进入邮件核对', exact=True).click()
        expect(self.page.locator('.cw-attachment-list')).to_contain_text('线路.csv')
        expect(self.page.locator('.cw-attachment-list')).not_to_contain_text('notice.ICS')
        expect(self.page.frame_locator('.review-mail-frame').locator('td')).to_have_text('001234')
        uploads = []
        def upload(route):
            uploads.append(route.request.post_data_buffer)
            route.fulfill(json={'success':True, 'data':{'relative_path':'preview/imported.csv'}})
        self.page.route('**/api/suppliers/preview-attachments', upload)
        calls = self.mock_review()
        self.assertEqual(calls, [])
        self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        expect(self.page.locator('.review-result-row[data-field=cutover_reason]')).to_contain_text('网络维护')
        self.assertEqual(len(uploads), 1)
        self.assertIn('001234,上海'.encode(), uploads[0])
        self.assertEqual(calls[0]['attachments'], ['preview/imported.csv'])
        self.page.screenshot(path=str(self.evidence / 'eml-import-review.png'))
        self.assertEqual(self.errors, [])

    def test_formal_supplier_operator_create_edit_and_preview(self):
        self.page.goto(self.base + '/admin/suppliers/new')
        expect(self.page.locator('.supplier-start')).to_contain_text('从一封割接通知开始')
        expect(self.page.locator('.supplier-compare')).to_have_count(0)
        self.page.get_by_role('button', name='进入邮件核对', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='请先填写供应商名称')).to_be_visible()
        self.page.get_by_role('textbox', name='供应商名称', exact=True).fill('运营配置 Colt')
        self.page.get_by_role('textbox', name='来信发件地址', exact=True).fill('notice@operator.example')
        self.page.get_by_role('textbox', name='回复邮箱地址', exact=True).fill('reply@operator.example')
        self.page.get_by_role('textbox', name='割接通知主题样本', exact=True).fill('Planned maintenance')
        self.page.get_by_role('textbox', name='割接通知正文样本', exact=True).fill('Reason: Replace card. Service ID: 001234')
        self.page.screenshot(path=str(self.evidence / 'compare-create-guide-1440.png'))
        self.page.get_by_role('button', name='进入邮件核对', exact=True).click()
        self.add_identifier()
        calls = self.mock_review()
        self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        reason = self.page.locator('.review-result-row[data-field=cutover_reason]')
        expect(reason).to_contain_text('网络维护')
        reason.get_by_role('button').click()
        correction = self.page.locator('.review-correction-dialog')
        correction.get_by_role('textbox').fill('读取 Reason 段落中的设备更换原因。')
        self.page.screenshot(path=str(self.evidence / 'compare-correction-1440.png'))
        correction.get_by_role('button', name='应用修正', exact=True).click()
        expect(self.page.locator('.review-result-status')).to_contain_text('样本或规则已修改')
        expect(reason).to_contain_text('网络维护')  # Editing a rule must not fabricate a result.
        self.page.get_by_role('button', name='重新识别', exact=True).click()
        expect(reason).to_contain_text('更换故障板卡')
        expect(self.page.locator('.review-result-status')).not_to_contain_text('样本或规则已修改')
        self.assertEqual(len(calls), 2)
        self.assertIn('读取 Reason 段落', calls[-1]['cutover_extract_prompt'])
        self.assertEqual(self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data'], [])
        self.page.get_by_role('button', name='保存配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        supplier_id = self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data'][0]['id']
        self.page.goto(self.base + f'/admin/suppliers/{supplier_id}')
        expect(self.page.locator('.supplier-start')).to_have_count(0)
        expect(self.page.locator('.supplier-compare')).to_be_visible()
        expect(self.page.get_by_role('textbox', name='回复邮箱地址', exact=True)).to_have_value('reply@operator.example')
        self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        expect(reason).to_contain_text('更换故障板卡')
        self.page.locator('.workspace').evaluate('(e)=>e.scrollTo({top:0,behavior:"instant"})')
        self.page.screenshot(path=str(self.evidence / 'compare-formal-1440.png'))
        self.page.get_by_role('textbox', name='供应商名称', exact=True).fill('运营配置 Colt 更新')
        self.page.get_by_role('button', name='保存配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        saved = self.fixture.client.get(f'/api/suppliers/{supplier_id}', headers=self.fixture.headers).get_json()['data']
        self.assertEqual(saved['name'], '运营配置 Colt 更新')
        self.assertEqual(saved['line_query_keywords'], ['ServiceId'])
        self.assertEqual(saved['fixed_field_rules']['cutover_reason'], '读取 Reason 段落中的设备更换原因。')
        self.assert_clean_browser()

    def test_preview_falls_back_when_running_backend_lacks_endpoint(self):
        self.page.route('**/api/suppliers/sample-preview', lambda route: route.fulfill(
            status=404, content_type='text/html', body='<html><h1>Not Found</h1></html>'))
        external_requests = []
        self.page.route('https://preview-unsafe.invalid/**', lambda route: (
            external_requests.append(route.request.url), route.abort()))
        self.open_draft_editor()
        self.page.get_by_role('button', name='编辑样本', exact=True).click()
        dialog = self.page.locator('.mail-sample-editor-dialog')
        html = '''<html><head><style>td {color: rgb(0, 80, 0)}
            @import url(https://preview-unsafe.invalid/style);</style></head><body>
            <h3>Maintenance Info 155864162</h3><p>Configuration changes</p>
            <table border="1"><tr><th>TGN_NMS_ID</th><th>TSAM_VNR</th></tr>
            <tr><td>001234</td><td>00/ABC-98</td></tr></table>
            <script>parent.document.body.dataset.unsafe='yes'</script>
            <img src="https://preview-unsafe.invalid/tracker" onerror="parent.hacked=true">
            <div style="background-image:url(https://preview-unsafe.invalid/bg)">Safe text</div>
            <iframe src="https://preview-unsafe.invalid/frame"></iframe>
            <form action="https://preview-unsafe.invalid/form"><input value="hidden"></form>
            <a href="javascript:alert(1)" onclick="parent.hacked=true">link</a>
            <svg onload="parent.hacked=true"><script>alert(1)</script></svg>
            </body></html>'''
        dialog.get_by_role('textbox', name='割接通知正文样本', exact=True).fill(html)
        dialog.get_by_role('button', name='关闭', exact=True).click()
        frame = self.page.frame_locator('.review-mail-frame')
        expect(frame.get_by_role('cell', name='001234', exact=True)).to_be_visible()
        expect(frame.get_by_role('cell', name='00/ABC-98', exact=True)).to_be_visible()
        self.assertEqual(external_requests, [])
        self.assertIsNone(self.page.locator('body').get_attribute('data-unsafe'))
        self.assertEqual(self.page.locator('.review-mail-frame').get_attribute('sandbox'), '')
        markup = self.page.locator('.review-mail-frame').get_attribute('srcdoc')
        for unsafe in ('<script', '<iframe', '<form', '<svg', '<img', 'onclick=', 'onerror=', 'javascript:'):
            self.assertNotIn(unsafe, markup)
        self.assertIn("default-src 'none'", markup)
        self.page.locator('.workspace').evaluate('(e)=>e.scrollTo({top:0,behavior:"instant"})')
        self.page.screenshot(path=str(self.evidence / 'mail-preview-fallback-1440.png'))
        # Current edits, not the stored source, must be displayed after falling back.
        self.page.get_by_role('button', name='编辑样本', exact=True).click()
        dialog.get_by_role('textbox', name='割接通知正文样本', exact=True).fill('<p>Updated sample</p>')
        dialog.get_by_role('button', name='关闭', exact=True).click()
        expect(frame.get_by_text('Updated sample', exact=True)).to_be_visible()
        self.assertEqual(self.errors, [])

    def test_supplier_specific_identifiers_validate_and_persist(self):
        self.open_draft_editor()
        dialog = self.add_identifier('TGN_NMS_ID', '附件表格中 TGN NMS ID 列，每条线路各取一个值。')
        expect(dialog).not_to_be_visible()
        self.add_identifier('TSAM_VNR', '邮件表格中的 TSAM_VNR 列。', query=False)
        self.add_identifier('客户资源号', '正文中对应线路的客户资源号。')
        for name in ('!!!', 'ImpactType', 'TGN NMS ID', 'TSAM-VNR', '___', '__proto__'):
            dialog = self.add_identifier(name, '验证名称')
            expect(dialog.locator('[role=alert]')).to_be_visible()
            dialog.get_by_role('button', name='取消', exact=True).click()
        self.page.get_by_role('button', name='添加一种线路编号', exact=True).click()
        dialog = self.page.locator('.review-identifier-dialog')
        expect(dialog.get_by_role('button', name='添加', exact=True)).to_be_disabled()
        dialog.get_by_role('textbox', name='字段 key', exact=True).fill('未保存的编号')
        expect(dialog.get_by_role('button', name='添加', exact=True)).to_be_disabled()
        dialog.get_by_role('button', name='取消', exact=True).click()
        expect(self.page.locator('.review-query-row')).to_have_count(3)
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        config = self.fixture.client.get(f'/api/supplier-drafts/{self.draft_id}', headers=self.fixture.headers).get_json()['data']['draft']['config']
        self.assertEqual([row['name'] for row in config['line_custom_fields']], ['TGN_NMS_ID', 'TSAM_VNR', '客户资源号'])
        self.assertEqual(config['line_query_keywords'], ['TGN_NMS_ID', '客户资源号'])
        self.assertIn('TGN NMS ID', config['line_custom_fields'][0]['description'])
        self.open_draft_editor()
        expect(self.page.locator('.review-query-row').get_by_role('checkbox', name='TGN_NMS_ID', exact=True)).to_be_checked()
        expect(self.page.locator('.review-query-row').get_by_role('checkbox', name='TSAM_VNR', exact=True)).not_to_be_checked()
        self.page.get_by_role('button', name='添加一种线路编号', exact=True).click()
        expect(dialog).to_be_visible()
        dialog.get_by_role('textbox', name='字段 key', exact=True).fill('SupplierResourceId')
        dialog.get_by_role('textbox', name='从哪里提取', exact=True).fill('从附件的资源明细表中读取对应列，每条线路分别提取，保留完整编号。')
        self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
        self.page.screenshot(path=str(self.evidence / 'custom-identifier-dialog-1440.png'))
        dialog.get_by_role('button', name='取消', exact=True).click()
        self.assert_clean_browser()

    def test_line_fixed_rules_can_be_edited_tested_saved_and_published_from_review(self):
        self.open_draft_editor()
        self.add_identifier()
        self.page.get_by_role('textbox', name='供应商名称', exact=True).fill('线路规则供应商')
        defaults = self.fixture.client.get('/api/suppliers/field-defaults', headers=self.fixture.headers).get_json()['data']
        defaults = {field['name']:field['description'] for field in defaults['line_fields']}
        rules = {
            'ImpactType': '按附件每行 Status 和实际中断分钟数判断影响类型。',
            'ImpactDateTime': '读取每行 Begin 和 End，按该行时区转为 UTC。',
            'ImpactDuration': '读取每行 Duration，02:30 h 转换为 150m。',
            'InteruptionsCounts': '读取每行 Number of interruptions，未提供则返回 1。',
        }
        expect(self.page.locator('.review-line-rule')).to_have_count(4)
        calls = self.mock_review()
        self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        expect(self.page.locator('.review-result-status')).to_be_visible()
        dialog = self.page.locator('.review-correction-dialog')
        for key, rule in rules.items():
            row = self.page.locator(f'.review-line-rule[data-field={key}]')
            row.get_by_role('button').click()
            expect(dialog.get_by_role('textbox')).to_have_value(defaults[key])
            dialog.get_by_role('textbox').fill(rule)
            dialog.get_by_role('button', name='应用修正', exact=True).click()
            expect(row).to_contain_text(rule)
        expect(self.page.locator('.review-result-status')).to_contain_text('样本或规则已修改')
        self.assertEqual(len(calls), 1)
        self.page.get_by_role('button', name='重新识别', exact=True).click()
        expect(self.page.locator('.review-result-status')).not_to_contain_text('样本或规则已修改')
        for rule in rules.values():
            self.assertIn(rule, calls[-1]['cutover_extract_prompt'])
        for width in (1280, 1920):
            self.page.set_viewport_size({'width':width,'height':1000})
            self.page.locator('.review-line-rules').screenshot(path=str(self.evidence / f'line-rules-{width}.png'))
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth-innerWidth'), 1)
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        self.page.reload()
        self.page.locator('.review-line-rule[data-field=ImpactDuration]').get_by_role('button').click()
        expect(dialog.get_by_role('textbox')).to_have_value(rules['ImpactDuration'])
        dialog.get_by_role('button', name='取消', exact=True).click()
        self.page.get_by_role('button', name='确认启用', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='确认启用', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        supplier = self.fixture.client.get('/api/suppliers', headers=self.fixture.headers).get_json()['data'][0]
        for key, rule in rules.items():
            self.assertEqual(supplier['fixed_field_rules'][key], rule)
        self.page.goto(self.base + f"/admin/suppliers/{supplier['id']}")
        self.page.locator('.review-line-rule[data-field=ImpactDuration]').get_by_role('button').click()
        expect(dialog.get_by_role('textbox')).to_have_value(rules['ImpactDuration'])
        dialog.get_by_role('textbox').fill('读取 Duration 列，按分钟输出，保留每条线路对应关系。')
        dialog.get_by_role('button', name='应用修正', exact=True).click()
        self.page.get_by_role('button', name='保存配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        saved = self.fixture.client.get(f"/api/suppliers/{supplier['id']}", headers=self.fixture.headers).get_json()['data']
        self.assertIn('保留每条线路对应关系', saved['fixed_field_rules']['ImpactDuration'])
        self.assertEqual(saved['fixed_field_rules']['ImpactType'], rules['ImpactType'])
        self.assert_clean_browser()

    def test_formal_manual_prompt_is_explained_and_preserved(self):
        legacy = '保留旧版维护规则，线路编号使用 CircuitTitle。'
        response = self.fixture.client.post('/api/suppliers', headers=self.fixture.headers, json={
            'name':'旧版供应商','email':'legacy@operator.example','prompt_mode':'manual',
            'cutover_extract_prompt':legacy,'email_type_samples':{'割接通知':{'subject':'维护','content':'线路维护通知'}}})
        self.assertEqual(response.status_code, 201)
        supplier_id = response.get_json()['data']['id']
        self.page.goto(self.base + f'/admin/suppliers/{supplier_id}')
        expect(self.page.locator('.supplier-results-pane')).to_contain_text('当前使用已有手写规则')
        self.page.get_by_role('button', name='修正识别方式：割接原因', exact=True).click()
        dialog = self.page.locator('.review-correction-dialog')
        dialog.get_by_role('textbox').fill('读取 Reason 段落。')
        dialog.get_by_role('button', name='应用修正', exact=True).click()
        self.page.locator('.review-line-rule[data-field=ImpactDuration]').get_by_role('button').click()
        dialog.get_by_text('查看当前完整规则', exact=True).click()
        expect(dialog.locator('.review-manual-line-rule')).to_contain_text(legacy)
        dialog.get_by_role('textbox').fill('从 Duration 列提取每条线路的单次中断时长。')
        dialog.get_by_role('button', name='应用修正', exact=True).click()
        calls = self.mock_review()
        self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        expect(self.page.locator('.review-result-status')).to_contain_text('待人工核对')
        self.assertIn(legacy, calls[0]['cutover_extract_prompt'])
        self.assertIn('读取 Reason 段落。', calls[0]['cutover_extract_prompt'])
        self.assertIn('从 Duration 列提取每条线路的单次中断时长。', calls[0]['cutover_extract_prompt'])
        self.page.get_by_role('button', name='保存配置', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_have_count(0)
        saved = self.fixture.client.get(f'/api/suppliers/{supplier_id}', headers=self.fixture.headers).get_json()['data']
        self.assertEqual(saved['prompt_mode'], 'manual')
        self.assertIn(legacy, saved['cutover_extract_prompt'])
        self.assertIn('读取 Reason 段落。', saved['cutover_extract_prompt'])
        self.assert_clean_browser()

    def test_custom_circuit_keys_are_literal_across_review_advanced_and_persistence(self):
        self.open_draft_editor()
        keys = ['CircuitId', 'CircuitTitle', 'TGN_NMS_ID', 'TSAM_VNR', '_Service_Id_']
        for key in keys:
            self.add_identifier(key, '读取附件中对应的列，保留完整编号。')
        rows = self.page.locator('.review-query-row')
        expect(rows.locator('.n-checkbox')).to_have_text(keys)
        expect(self.page.locator('.review-identifier-dialog')).not_to_be_visible()
        self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
        self.page.locator('.review-query-options').screenshot(path=str(self.evidence / 'literal-field-keys-review.png'))
        self.open_advanced()
        expect(self.page.locator('.draft-line-field-label')).to_have_text(keys)
        expect(self.page.get_by_role('textbox', name='字段 key', exact=True)).to_have_count(len(keys))
        self.page.get_by_role('textbox', name='字段 key', exact=True).first.fill('Circuit_ID')
        expect(self.page.locator('.draft-line-field-label').first).to_have_text('Circuit_ID')
        self.page.get_by_role('button', name='返回邮件核对', exact=True).click()
        expect(rows.get_by_role('checkbox', name='Circuit_ID', exact=True)).to_be_checked()
        self.page.get_by_role('button', name='保存草稿', exact=True).click()
        expect(self.page.locator('.n-message').filter(has_text='草稿已保存')).to_be_visible()
        data = self.fixture.client.get(f'/api/supplier-drafts/{self.draft_id}', headers=self.fixture.headers).get_json()['data']['draft']['config']
        expected = ['Circuit_ID', *keys[1:]]
        self.assertEqual([field['name'] for field in data['line_custom_fields']], expected)
        self.assertEqual(data['line_query_keywords'], expected)
        self.assertEqual(data['line_custom_fields'][0]['description'], '读取附件中对应的列，保留完整编号。')
        self.open_draft_editor()
        expect(rows.locator('.n-checkbox')).to_have_text(expected)
        self.open_advanced()
        field = self.page.locator('#draft-section-custom .extract-field-row').first
        field.scroll_into_view_if_needed()
        self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
        field.screenshot(path=str(self.evidence / 'literal-field-keys-advanced.png'))
        self.assert_clean_browser()

    def test_compare_handles_attachments_stale_results_failure_and_empty_reply(self):
        self.open_draft_editor()
        calls = self.mock_review()
        self.page.route('**/api/suppliers/preview-attachments', lambda route: route.fulfill(
            status=201, content_type='application/json', body=json.dumps({'success':True,'data':{'relative_path':'email_attachments/preview-extract/test.txt'}})))
        self.open_advanced()
        self.page.locator('.n-upload input[type=file]').set_input_files({
            'name':'circuits.txt','mimeType':'text/plain','buffer':b'Service ID: 001234'})
        self.page.get_by_role('button', name='返回邮件核对', exact=True).click()
        self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        expect(self.page.locator('.review-lines-table')).to_contain_text('001234')
        self.assertEqual(calls[0]['attachments'], ['email_attachments/preview-extract/test.txt'])
        self.page.get_by_role('button', name='编辑样本', exact=True).click()
        dialog = self.page.locator('.mail-sample-editor-dialog')
        dialog.get_by_role('textbox', name='割接通知正文样本', exact=True).fill('更新后的割接通知')
        dialog.get_by_role('button', name='关闭', exact=True).click()
        expect(self.page.locator('.review-result-status')).to_contain_text('上次结果')
        self.page.locator('.review-sample-tabs').get_by_role('tab', name='割接取消', exact=True).click()
        expect(self.page.get_by_role('button', name='重新识别', exact=True)).to_be_disabled()
        expect(self.page.locator('.supplier-results-pane')).to_contain_text('请选择“割接通知”')
        self.page.locator('.review-sample-tabs').get_by_role('tab', name='割接通知', exact=True).click()
        self.page.route('**/api/suppliers/preview-extract', lambda route: route.fulfill(
            status=503, content_type='application/json', body=json.dumps({'success':False,'message':'模拟服务暂时不可用'})))
        self.page.get_by_role('button', name='重新识别', exact=True).click()
        expect(self.page.locator('.supplier-results-pane [role=alert]')).to_contain_text('本次识别未完成')
        expect(self.page.locator('.review-lines-table')).to_contain_text('001234')
        self.page.route('**/api/suppliers/preview-extract', lambda route: route.fulfill(
            content_type='application/json', body=json.dumps({'success':True,'data':{'extract_result':'{}'}})))
        self.page.get_by_role('button', name='重新识别', exact=True).click()
        expect(self.page.locator('.supplier-results-pane')).to_contain_text('本次没有返回可核对的割接字段')
        expect(self.page.locator('.review-lines-table')).to_have_count(0)
        self.mock_review()
        self.page.get_by_role('button', name='重新识别', exact=True).click()
        expect(self.page.locator('.review-lines-table')).to_contain_text('001234')
        expect(self.page.locator('.supplier-results-pane [role=alert]')).to_have_count(0)
        self.assert_clean_browser(expected_http_errors=(503,))

    def test_compare_marks_inflight_results_stale_after_editing(self):
        self.open_draft_editor()
        pending = []
        self.page.route('**/api/suppliers/preview-extract', lambda route: pending.append(route))
        with self.page.expect_request('**/api/suppliers/preview-extract'):
            self.page.get_by_role('button', name='识别这封邮件', exact=True).click()
        self.page.get_by_role('textbox', name='供应商名称', exact=True).fill('请求期间修改名称')
        pending[0].fulfill(content_type='application/json', body=json.dumps({'success':True,'data':{'extract_result':'{"cutover_reason":"原请求结果"}'}}))
        expect(self.page.locator('.review-result-status')).to_contain_text('样本或规则已修改')
        expect(self.page.locator('.review-result-row[data-field=cutover_reason]')).to_contain_text('原请求结果')
        self.assertEqual(pending[0].request.post_data_json['supplier_name'], '')
        self.assert_clean_browser()

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
        self.open_draft_editor()
        self.page.get_by_role('button', name='已收集的邮件（1）', exact=True).click()
        frame = self.page.frame_locator('.review-mail-frame')
        expect(frame.locator('table')).to_be_visible()
        expect(frame.locator('td').first).to_have_text('ORIGINAL-4821')
        expect(frame.locator('body')).to_contain_text('End of notice.')
        expect(frame.locator('script, meta[http-equiv="refresh"], img[src^="https:"]')).to_have_count(0)
        self.assertEqual(self.page.locator('body').get_attribute('data-mail-script-ran'), None)
        self.assertEqual(external, [])
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            self.page.screenshot(path=str(self.evidence / f'original-sample-html-{width}.png'))
        with self.fixture.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET html_content=NULL WHERE id=?', (self.email_id,))
            conn.commit()
        self.page.reload()
        self.page.get_by_role('button', name='已收集的邮件（1）', exact=True).click()
        body = self.page.locator('.review-mail-body')
        expect(body.locator('pre')).to_have_text(text)
        expect(body.locator('pre')).to_have_css('white-space', 'pre-wrap')
        expect(body.locator('iframe')).to_have_count(0)
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
        self.open_advanced()
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
        self.open_advanced()
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
        self.page.locator('.supplier-section-actions').get_by_role('button', name='返回列表', exact=True).click()
        expect(self.page.locator('.draft-review-panel')).to_have_count(0)
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

    def test_draft_delete_failures_keep_list_row(self):
        panel = self.open_drafts_list()
        row = panel.locator('.n-data-table-tbody tr').filter(has_text='noc@example.com')
        expect(self.page.locator('.draft-review-panel')).to_have_count(0)
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
                    expect(self.page.locator('.draft-review-panel')).to_have_count(0)
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

        expect(self.page.locator('.mail-analysis-panel')).to_contain_text('重保期割接')
        expect(self.page.locator('.mail-analysis-heading .n-tag')).to_have_css('opacity', '1')
        self.page.set_viewport_size({'width':1280, 'height':900})
        self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
        self.page.screenshot(path=str(self.evidence / 'pending-reply-1280.png'), full_page=True)
        self.page.get_by_role('tab', name='回复审核', exact=False).click()
        expect(self.page.locator('.reply-pending-card')).to_be_visible()
        actions = self.page.locator('.reply-pending-actions')
        actions.scroll_into_view_if_needed()
        expect(actions.locator('button')).to_have_count(2)
        expect(actions.locator('button').last).to_be_enabled()
        self.page.screenshot(path=str(self.evidence / 'pending-reply-actions-1280.png'), full_page=True)
        self.assertEqual(self.fixture.db.get_email_record_by_id(self.email_id)['reply_status'], 'pending')
        self.assertEqual(self.errors, [])

    def test_review_save_and_publish(self):
        self.page.goto(self.base + f'/admin/suppliers?draft={self.draft_id}')
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
        panel.get_by_role('button', name='查看记录', exact=True).click()
        expect(self.page.locator('.review-mail-body')).to_contain_text('维护正文')
        expect(self.page.get_by_role('button', name='确认启用', exact=True)).to_have_count(0)
        expect(self.page.get_by_role('textbox', name='供应商名称', exact=True)).to_be_disabled()
        expect(self.page.get_by_role('button', name='编辑正式配置', exact=True)).to_be_visible()
        self.page.reload()
        expect(self.page.locator('.review-draft-state')).to_contain_text('这是启用时保留的记录')
        self.page.screenshot(path=str(self.evidence / 'published-history-1440.png'), full_page=True)
        self.page.get_by_role('button', name='返回列表', exact=True).click()
        expect(panel.get_by_role('radio', name='已启用', exact=True)).to_be_checked()
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
        panel.get_by_role('button', name='审核配置', exact=True).click()
        expect(self.page.locator('.supplier-compare')).to_be_visible()
        self.page.get_by_role('button', name='返回列表', exact=True).click()
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
        self.open_advanced()
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
        self.open_advanced()
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
        self.open_advanced()
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
        self.open_advanced()
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
        self.open_advanced()
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
        self.page.locator('.supplier-form input').first.fill('人工确认固定字段供应商')
        self.open_advanced()
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
        self.open_advanced()
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
