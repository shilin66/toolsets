import json
import threading
import unittest
from unittest.mock import patch

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server, WSGIRequestHandler

from tests.api import test_cutover_task_api as fixture


class QuietRequestHandler(WSGIRequestHandler):
    def log(self, type, message, *args):
        pass


class CutoverRegenerationUiTest(unittest.TestCase):
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
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
        self.page.set_default_timeout(10000)
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.requests = []
        self.page.on("request", lambda request: self.requests.append(request.url) if request.method == "POST" and request.url.endswith("/tasks/generate") else None)
        self.page.goto(f"http://127.0.0.1:{self.server.server_port}/admin/cutover-emails/{self.api.email_records_id}")
        self.page.get_by_role("textbox", name="API Key").fill("test-key")
        self.page.get_by_role("button", name="登录", exact=True).click()
        self.page.locator(".email-content-collapse .el-collapse-item__header").filter(has_text="提取解析结果").click()
        self.editor = self.page.locator(".extraction-editor textarea")
        expect(self.editor).to_be_visible()

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def test_editor_uses_saved_parameters_and_excludes_generation_context(self):
        payload = json.loads(self.editor.input_value())
        self.assertEqual(payload["cutover_timezone"], "Asia/Shanghai")
        self.assertEqual(payload["line_query_keywords"], ["OrderNumber"])
        self.assertEqual(fixture.api_server.extraction_lines(payload)[0]["ImpactType"], "interrupted")
        self.assertNotIn("supplier", payload)
        self.assertNotIn("email_records_id", payload)
        self.assertNotIn("bound_circuit_id", fixture.api_server.extraction_lines(payload)[0])
        expect(self.page.locator(".extraction-toolbar")).to_contain_text("RT")
        self.assertEqual(self.errors, [])

    def test_unsaved_extraction_cannot_regenerate_from_matching_area(self):
        before = self.api.db.get_cutover_task(self.task_id)
        payload = json.loads(self.editor.input_value())
        payload["cutover_reason"] = "尚未保存的原因"
        self.editor.fill(json.dumps(payload, ensure_ascii=False))
        self.page.get_by_role("button", name="重新生成割接任务", exact=True).click()
        expect(self.page.locator(".el-message").filter(has_text="未保存")).to_be_visible()
        self.assertEqual(self.requests, [])
        self.assertEqual(self.api.db.get_cutover_task(self.task_id), before)
        self.assertEqual(self.errors, [])

    def test_matching_regeneration_keeps_binding_and_config_personnel(self):
        self.page.get_by_role("button", name="重新生成割接任务", exact=True).click()
        self.page.locator(".el-message-box").get_by_role("button", name="重新生成", exact=True).click()
        expect(self.page.locator(".el-message").filter(has_text="割接任务已生成")).to_be_visible()
        task = self.api.db.get_cutover_task(self.task_id)
        self.assertEqual(fixture.api_server.extraction_lines(task["fill_payload"])[0]["bound_circuit_id"], fixture.BACKBONE_CIRCUIT["circuit_id"])
        self.assertEqual(task["fill_result"]["backbone_circuits"][0]["人员信息"]["操作审核人姓名"], "RT NOC")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.errors, [])

    def test_unsaved_manual_binding_cannot_regenerate(self):
        before = self.api.db.get_cutover_task(self.task_id)
        self.page.locator('.line-binding-controls input[aria-label="Circuit ID"]').fill("unsaved-circuit")
        self.page.get_by_role("button", name="重新生成割接任务", exact=True).click()
        expect(self.page.locator(".el-message").filter(has_text="未保存")).to_be_visible()
        expect(self.page.locator(".el-message-box")).not_to_be_visible()
        self.assertEqual(self.requests, [])
        self.assertEqual(self.api.db.get_cutover_task(self.task_id), before)
        self.assertEqual(self.errors, [])

    def test_extraction_generation_saves_edit_and_clears_manual_binding(self):
        payload = json.loads(self.editor.input_value())
        payload["cutover_reason"] = "用户修改后的原因"
        payload["location"] = ""
        self.editor.fill(json.dumps(payload, ensure_ascii=False))
        with patch.object(fixture.api_server, "ensure_source_email_archived"):
            self.page.get_by_role("button", name="生成割接任务", exact=True).click()
            self.page.locator(".el-message-box").get_by_role("button", name="重新生成", exact=True).click()
            expect(self.page.locator(".el-message").filter(has_text="割接任务已生成")).to_be_visible()
        task = self.api.db.get_cutover_task(self.task_id)
        self.assertEqual(task["fill_payload"]["supplier"], "RT")
        self.assertEqual(task["fill_payload"]["cutover_reason"], "用户修改后的原因")
        self.assertEqual(task["fill_payload"]["location"], "")
        self.assertNotIn("bound_circuit_id", fixture.api_server.extraction_lines(task["fill_payload"])[0])
        self.assertEqual(self.errors, [])

    def test_cancel_generation_does_not_save_extraction_or_replace_task(self):
        before = self.api.db.get_cutover_task(self.task_id)
        record = self.api.db.get_email_record_by_id(self.api.email_records_id)
        payload = json.loads(self.editor.input_value())
        payload["cutover_reason"] = "取消保存"
        self.editor.fill(json.dumps(payload, ensure_ascii=False))
        self.page.get_by_role("button", name="生成割接任务", exact=True).click()
        self.page.locator(".el-message-box").get_by_role("button", name="取消", exact=True).click()
        expect(self.page.locator(".el-message-box")).not_to_be_visible()
        self.assertEqual(self.api.db.get_cutover_task(self.task_id), before)
        self.assertEqual(self.api.db.get_email_record_by_id(self.api.email_records_id)["line_match_payload"], record["line_match_payload"])
        self.assertEqual(self.requests, [])
        self.assertEqual(self.errors, [])
