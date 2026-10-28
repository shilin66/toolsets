import json
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server, WSGIRequestHandler

from tests.api import test_cutover_task_api as fixture


class QuietRequestHandler(WSGIRequestHandler):
    def log(self, type, message, *args):
        pass


class CutoverWorkbenchUiTest(unittest.TestCase):
    def setUp(self):
        self.api = fixture.CutoverTaskApiTest()
        self.api.setUp()
        self.addCleanup(self.api.tearDown)
        archive_patch = patch.object(fixture.api_server, "ensure_source_email_archived")
        archive_patch.start()
        self.addCleanup(archive_patch.stop)
        self.api.db.replace_all_supplier_circuits([fixture.BACKBONE_CIRCUIT])
        payload = self.api.fill_payload(cutover_timezone="Asia/Shanghai", line_query_keywords=["OrderNumber"])
        payload["line_array_info"]["data"][0].update(
            CircuitIDRT="1940953", OrderNumber="1940953", ImpactType="interrupted",
            bound_circuit_id=fixture.BACKBONE_CIRCUIT["circuit_id"], bound_line_type="骨干",
        )
        response = self.api.post_fill(payload, circuits=[fixture.BACKBONE_CIRCUIT])
        self.task_id = self.api.first_task_id(response)
        raw = dict(payload, line_array=[dict(payload["line_array_info"]["data"][0], ImpactType="protected")])
        raw.pop("supplier")
        raw.pop("line_array_info")
        self.api.db.update_email_record_extract_result(self.api.email_records_id, json.dumps(raw))
        self.server = make_server("127.0.0.1", 0, fixture.api_server.app, threaded=True, request_handler=QuietRequestHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True, channel=getattr(self, 'browser_channel', None))
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
        self.page.set_default_timeout(10000)
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.requests = []
        self.page.on("request", lambda request: self.requests.append(request.url) if request.method == "POST" and request.url.endswith("/tasks/generate") else None)
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/admin/cutover-emails/{self.api.email_records_id}")
        self.page.get_by_role('button', name='管理员登录', exact=True).click()
        self.page.get_by_role("textbox", name="API Key").fill("test-key")
        self.page.get_by_role("button", name="登录", exact=True).click()
        expect(self.page.locator(".cutover-workbench")).to_be_visible()

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def test_review_is_business_form_and_list_remains_separate(self):
        expect(self.page.get_by_role('tab', name='邮件核对', exact=True)).to_be_visible()
        expect(self.page.locator('.cw-compare')).to_be_visible()
        expect(self.page.locator('.extraction-editor')).not_to_be_visible()
        expect(self.page.locator('.cw-fields')).to_contain_text('Scheduled maintenance')
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width':width, 'height':1000})
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
        self.evidence = Path('.qa/cutover-workbench')
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.page.set_viewport_size({'width':1440, 'height':1000})
        self.page.screenshot(path=str(self.evidence / 'review-1440.png'), full_page=True)
        self.assertEqual(self.errors, [])

    def test_business_correction_preserves_structure_and_regenerates_only_explicitly(self):
        before = self.api.db.get_cutover_task(self.task_id)
        self.page.get_by_role('button', name='编辑识别结果', exact=True).click()
        dialog = self.page.locator('.cw-result-dialog')
        expect(dialog).to_contain_text('清除已有手动绑定')
        dialog.get_by_role('textbox', name='割接原因', exact=True).fill('运营人员修正的原因')
        dialog.get_by_role('textbox', name='OrderNumber · 线路 1', exact=True).fill('001940953')
        dialog.get_by_role('button', name='保存并重新匹配', exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(self.page.locator('.cw-fields')).to_contain_text('运营人员修正的原因')
        saved = fixture.api_server.saved_email_fill_payload(self.api.db.get_email_record_by_id(self.api.email_records_id))
        self.assertEqual(saved['cutover_reason'], '运营人员修正的原因')
        self.assertEqual(saved['cutover_timezone'], 'Asia/Shanghai')
        self.assertEqual(saved['line_query_keywords'], ['OrderNumber'])
        self.assertEqual(fixture.api_server.extraction_lines(saved)[0]['OrderNumber'], '001940953')
        self.assertEqual(self.api.db.get_cutover_task(self.task_id), before)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.errors, [])

    def select_tab(self, name):
        self.page.get_by_role('tab', name=name, exact=False).click()

    def test_result_editor_supports_keyboard_edits_across_multiple_lines(self):
        payload = self.api.fill_payload()
        payload['line_array_info']['data'] = [
            {'CircuitId': '22-184435', 'CircuitIDRT': 1661552, 'OrderNumber': '00123',
             'ImpactType': 'protected', 'ImpactDuration': '0m'},
            {'CircuitId': '16-146899', 'CircuitIDRT': 1484026, 'OrderNumber': '00456',
             'ImpactType': 'interrupted', 'ImpactDuration': '365m'},
            {'CircuitId': '', 'CircuitIDRT': 1692110, 'OrderNumber': '00789',
             'ImpactType': 'protected', 'ImpactDuration': '0m'},
        ]
        self.api.db.update_email_line_match_payload(self.api.email_records_id, payload)
        self.page.reload()
        self.page.get_by_role('button', name='编辑识别结果', exact=True).click()
        dialog = self.page.locator('.cw-result-dialog')
        for name, value in [('CircuitIDRT · 线路 1', '001661553'),
                            ('OrderNumber · 线路 2', '00045678'),
                            ('CircuitId · 线路 3', 'NEW-00123')]:
            field = dialog.get_by_role('textbox', name=name, exact=True)
            field.click()
            field.press('ControlOrMeta+A')
            field.press('Backspace')
            for character in value:
                self.page.keyboard.type(character)
                expect(field).to_be_focused()
            expect(field).to_have_value(value)
        dialog.get_by_role('button', name='保存并重新匹配', exact=True).click()
        expect(dialog).not_to_be_visible()
        self.page.reload()
        self.page.get_by_role('button', name='编辑识别结果', exact=True).click()
        expect(dialog.get_by_role('textbox', name='CircuitIDRT · 线路 1', exact=True)).to_have_value('001661553')
        expect(dialog.get_by_role('textbox', name='OrderNumber · 线路 2', exact=True)).to_have_value('00045678')
        expect(dialog.get_by_role('textbox', name='CircuitId · 线路 3', exact=True)).to_have_value('NEW-00123')
        self.assertEqual(self.errors, [])

    def test_reply_edits_survive_tabs_and_send_keeps_reporting_tasks(self):
        self.api.db.save_pending_reply(self.api.email_records_id, 'Original reply draft', 'emergency')
        self.page.reload()
        self.select_tab('回复审核')
        reply = self.page.locator('.reply-pending-card textarea')
        reply.fill('Reviewed reply content')
        self.select_tab('邮件核对')
        self.select_tab('回复审核')
        expect(reply).to_have_value('Reviewed reply content')
        calls = []
        def send(route):
            calls.append(route.request.post_data_json)
            self.api.db.mark_reply_sent(self.api.email_records_id, '2026-10-28 10:00:00', snapshot={
                'content': calls[-1]['reply_content'],
                'recipients': ['actual-recipient@example.com'],
                'cc_recipients': ['actual-cc@example.com'],
            })
            route.fulfill(content_type='application/json', body=json.dumps({'success': True, 'data':{}}))
        self.page.route('**/api/cutover/reply/confirm', send)
        self.page.locator('.reply-pending-card').get_by_role('button', name='确认发送', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='取消', exact=True).click()
        self.assertEqual(calls, [])
        self.page.locator('.reply-pending-card').get_by_role('button', name='确认发送', exact=True).click()
        self.page.locator('.n-dialog').get_by_role('button', name='确认发送', exact=True).click()
        expect(self.page.locator('#cw-panel-reply')).to_contain_text('回复已发送')
        history = self.page.locator('.cw-reply-history')
        expect(history).to_contain_text('Reviewed reply content')
        expect(history).to_contain_text('actual-recipient@example.com')
        expect(history).to_contain_text('actual-cc@example.com')
        expect(history).to_contain_text('2026-10-28 10:00:00')
        self.assertEqual(calls[0]['reply_content'], 'Reviewed reply content')
        self.select_tab('上报处理')
        expect(self.page.locator('.cw-task-card')).to_have_count(1)
        expect(self.page.locator('.cw-task-card')).to_contain_text('待确认')
        self.assertEqual(self.errors, [])

    def test_sent_reply_history_survives_new_drafts_and_renders_plain_text(self):
        record_id = self.api.email_records_id
        self.api.db.save_pending_reply(record_id, 'Old reply', 'major_event')
        self.api.db.mark_reply_sent(record_id, '2026-10-28 09:00:00', snapshot={
            'content': 'Old reply\n<script>window.replyExecuted=true</script>',
            'recipients': ['old@example.com'], 'cc_recipients': [],
        })
        self.api.db.save_pending_reply(record_id, 'Second reply', 'major_event')
        self.api.db.mark_reply_sent(record_id, '2026-10-28 10:00:00', snapshot={
            'content': 'Second reply', 'recipients': ['new@example.com'], 'cc_recipients': [],
        })
        self.api.db.save_pending_reply(record_id, 'New draft', 'major_event')
        self.page.reload()
        self.select_tab('回复审核')
        expect(self.page.locator('.cw-sent-reply')).to_have_count(2)
        expect(self.page.locator('.cw-sent-reply').first).to_contain_text('Second reply')
        expect(self.page.locator('.cw-sent-reply').last).to_contain_text('<script>window.replyExecuted=true</script>')
        expect(self.page.locator('.reply-pending-card textarea')).to_have_value('New draft')
        self.assertIsNone(self.page.evaluate('window.replyExecuted'))
        self.assertEqual(self.errors, [])
        evidence = Path('.qa/cutover-workbench/reply-history.png')
        evidence.parent.mkdir(parents=True, exist_ok=True)
        self.page.locator('.cw-reply-history').screenshot(path=str(evidence))

    def test_legacy_reply_shows_saved_content_without_inventing_addresses(self):
        self.api.db.save_pending_reply(self.api.email_records_id, 'Historical sent content', 'major_event')
        self.api.db.mark_reply_sent(self.api.email_records_id, '2026-10-28 08:00:00')
        self.api.db.init_database()
        self.api.db.init_database()  # Migration is idempotent.
        self.api.db.update_email_record_cutover_scene(self.api.email_records_id, 'major_event')
        self.page.reload()
        expect(self.page.locator('.scene-major_event')).to_contain_text('仍生成割接填报任务')
        self.select_tab('回复审核')
        expect(self.page.locator('.cw-sent-reply')).to_contain_text('Historical sent content')
        expect(self.page.locator('.cw-reply-addresses')).to_contain_text('未记录')
        expect(self.page.locator('.cw-sent-reply')).to_contain_text('历史记录未保存实际收件人和抄送地址')
        self.api.db.save_pending_reply(self.api.email_records_id, 'New draft after migration', 'major_event')
        self.page.reload()
        self.select_tab('回复审核')
        expect(self.page.locator('.cw-sent-reply')).to_have_count(1)
        expect(self.page.locator('.cw-sent-reply')).to_contain_text('Historical sent content')
        self.assertEqual(self.errors, [])

    def test_task_content_survives_tabs_and_unsaved_form_cannot_confirm(self):
        self.select_tab('上报处理')
        self.page.get_by_role('button', name='核对任务', exact=True).click()
        panel = self.page.locator('.task-detail-panel')
        expect(panel).to_be_visible()
        expect(panel.locator('.cw-report-summary')).to_contain_text(fixture.BACKBONE_CIRCUIT['circuit_id'])
        expect(panel.locator('.cw-report-summary')).to_contain_text('Scheduled maintenance')
        expect(panel.locator('.cw-full-form')).not_to_be_visible()
        panel.get_by_role('button', name='完整填报内容', exact=False).click()
        field = panel.locator('.backbone-input').first
        field.fill('人工修改但尚未保存')
        expect(panel.get_by_role('button', name='人工确认', exact=True)).to_be_disabled()
        self.select_tab('回复审核')
        self.select_tab('上报处理')
        expect(field).to_have_value('人工修改但尚未保存')
        self.select_tab('处理记录')
        expect(panel.get_by_role('button', name='人工确认', exact=True)).not_to_be_visible()
        expect(self.page.locator('.cw-history')).to_contain_text('邮件已接收')
        self.select_tab('上报处理')
        expect(field).to_have_value('人工修改但尚未保存')
        panel.get_by_role('button', name='收起', exact=True).click()
        expect(self.page.locator('.n-dialog')).to_contain_text('尚未保存')
        self.page.locator('.n-dialog').get_by_role('button', name='取消', exact=True).click()
        expect(field).to_have_value('人工修改但尚未保存')
        self.assertEqual(self.errors, [])

    def test_failed_correction_preserves_inputs_and_can_retry(self):
        url = f'**/api/cutover/emails/{self.api.email_records_id}/extraction'
        self.page.route(url, lambda route: route.fulfill(status=409, content_type='application/json', body=json.dumps({'success':False,'message':'暂时无法保存'})))
        self.page.get_by_role('button', name='编辑识别结果', exact=True).click()
        dialog = self.page.locator('.cw-result-dialog')
        field = dialog.get_by_role('textbox', name='割接原因', exact=True)
        field.fill('失败后仍保留的编辑')
        dialog.get_by_role('button', name='保存并重新匹配', exact=True).click()
        expect(dialog.locator('[role=alert]')).to_be_visible()
        expect(field).to_have_value('失败后仍保留的编辑')
        self.page.unroute(url)
        dialog.get_by_role('button', name='保存并重新匹配', exact=True).click()
        expect(dialog).not_to_be_visible()
        expect(self.page.locator('.cw-fields')).to_contain_text('失败后仍保留的编辑')
        self.assertEqual(self.errors, [])

    def test_invalid_time_stays_in_editor_without_saving(self):
        self.page.get_by_role('button', name='编辑识别结果', exact=True).click()
        dialog = self.page.locator('.cw-result-dialog')
        dialog.locator('.n-date-picker input').nth(1).fill('2026-06-12 10:00:00')
        dialog.locator('.n-date-picker input').nth(1).press('Tab')
        dialog.get_by_role('button', name='保存并重新匹配', exact=True).click()
        expect(dialog.locator('[role=alert]')).to_contain_text('结束时间必须晚于开始时间')
        self.assertEqual(self.requests, [])
        self.assertEqual(self.errors, [])

    def test_common_datetime_picker_preserves_timezone_seconds_and_unchanged_values(self):
        payload = self.api.fill_payload(cutover_timezone='UTC')
        original = '2026-10-27 19:00:00/2026-10-28 03:40:00'
        payload['cutover_time'] = original
        self.api.db.update_email_line_match_payload(self.api.email_records_id, payload)
        self.page.reload()
        edit = self.page.get_by_role('button', name='编辑识别结果', exact=True)
        edit.click()
        dialog = self.page.locator('.cw-result-dialog')
        dates = dialog.locator('.n-date-picker input')
        expect(dialog.locator('input[type=datetime-local]')).to_have_count(0)
        expect(dates.nth(0)).to_have_value('2026-10-27 19:00:00')
        expect(dates.nth(1)).to_have_value('2026-10-28 03:40:00')
        save = dialog.get_by_role('button', name='保存并重新匹配', exact=True)
        with self.page.expect_response(lambda response: response.url.endswith('/extraction')) as response:
            save.click()
        self.assertEqual(response.value.status, 200, response.value.text())
        expect(dialog).not_to_be_visible()
        saved = fixture.api_server.saved_email_fill_payload(self.api.db.get_email_record_by_id(self.api.email_records_id))
        self.assertEqual(saved['cutover_time'], original)
        edit.click()
        dates.nth(0).click()
        expect(self.page.locator('.n-date-panel')).to_be_visible()
        evidence = Path('.qa/cutover-workbench')
        evidence.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(evidence/'edit-date-picker.png'), animations='disabled')
        dates.nth(0).press('Escape')
        dates.nth(0).fill('2026-10-27 20:10:25')
        dates.nth(0).press('Tab')
        dates.nth(1).fill('2026-10-28 04:30:45')
        dates.nth(1).press('Tab')
        save.click()
        expect(dialog).not_to_be_visible()
        saved = fixture.api_server.saved_email_fill_payload(self.api.db.get_email_record_by_id(self.api.email_records_id))
        self.assertEqual(saved['cutover_time'], '2026-10-27 20:10:25/2026-10-28 04:30:45')
        self.assertEqual(saved['cutover_timezone'], 'UTC')
        self.page.reload()
        edit.click()
        expect(dates.nth(0)).to_have_value('2026-10-27 20:10:25')
        expect(dates.nth(1)).to_have_value('2026-10-28 04:30:45')
        dates.nth(0).fill('')
        dates.nth(0).press('Tab')
        save.click()
        expect(dialog.locator('[role=alert]')).to_contain_text('请填写有效的起止时间')
        self.assertEqual(self.errors, [])

    def test_task_load_failure_can_retry_and_tabs_work_with_keyboard(self):
        self.page.route(f'**/api/cutover/tasks/{self.task_id}', lambda route: route.fulfill(
            status=503, content_type='application/json', body=json.dumps({'success':False,'message':'暂时无法读取任务'})))
        self.page.get_by_role('tab', name='邮件核对', exact=True).focus()
        self.page.keyboard.press('End')
        expect(self.page.get_by_role('tab', name='处理记录', exact=True)).to_have_attribute('aria-selected', 'true')
        self.page.get_by_role('button', name='查看上报记录', exact=False).click()
        expect(self.page.locator('.cw-selected-task [role=alert]')).to_contain_text('暂时无法读取任务')
        self.page.unroute(f'**/api/cutover/tasks/{self.task_id}')
        self.page.locator('.cw-selected-task').get_by_role('button', name='刷新', exact=True).click()
        expect(self.page.locator('.task-detail-panel')).to_be_visible()
        self.assertEqual(self.errors, [])

    def test_html_is_sandboxed_and_no_remote_content_loaded(self):
        with self.api.db.get_connection() as conn:
            conn.execute('UPDATE email_records SET html_content=? WHERE id=?', ('<h2>Planned Maintenance</h2><table><tr><td>Start time</td><td>2026-06-12 14:00 UTC</td></tr></table><script>parent.hacked=true</script><img src="https://example.invalid/tracker">', self.api.email_records_id))
            conn.commit()
        remote = []
        self.page.on('request', lambda request: remote.append(request.url) if request.url.startswith('https://example.invalid') else None)
        self.page.reload()
        frame = self.page.frame_locator('.cw-source iframe')
        expect(frame.get_by_text('Start time', exact=True)).to_be_visible()
        self.assertIsNone(self.page.evaluate('window.hacked'))
        expect(self.page.locator('.cw-source iframe')).to_have_attribute('sandbox', '')
        evidence = Path('.qa/cutover-workbench')
        evidence.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(evidence / 'html-review-1440.png'), full_page=True)
        self.select_tab('线路确认')
        self.page.get_by_role('button', name='邮件原文', exact=False).click()
        expect(self.page.frame_locator('.cw-source-drawer iframe').get_by_text('Start time', exact=True)).to_be_visible()
        self.assertEqual(remote, [])
        self.assertEqual(self.errors, [])

    def test_view_only_mailbox_disables_mutations(self):
        with self.api.db.get_connection() as conn:
            account_id = conn.execute('SELECT id FROM mail_accounts LIMIT 1').fetchone()[0]
        self.api.access_repo.set_grants(self.api.operator['id'], [{'account_id':account_id, 'can_operate':False}])
        self.page.get_by_role('button', name='退出登录', exact=True).click()
        self.page.get_by_role('textbox', name='用户名', exact=True).fill('operator')
        self.page.get_by_role('textbox', name='密码', exact=True).fill('operator-password')
        self.page.get_by_role('button', name='登录', exact=True).click()
        expect(self.page.get_by_role('button', name='编辑识别结果', exact=True)).to_be_disabled()
        self.select_tab('线路确认')
        expect(self.page.get_by_role('button', name='绑定并重新匹配', exact=True)).to_be_disabled()
        expect(self.page.get_by_role('button', name='重新生成割接任务', exact=True)).to_be_disabled()
        self.assertEqual(self.errors, [])
