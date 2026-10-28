import json
import re
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from mail_artifacts import customer_excel_path, message_storage_directory
from tests.api import test_cutover_task_api as fixture
from tests.ui.test_cutover_regeneration_ui import QuietRequestHandler


class CutoverDeletionUiTest(unittest.TestCase):
    def setUp(self):
        self.api = fixture.CutoverTaskApiTest()
        self.api.setUp()
        self.addCleanup(self.api.tearDown)
        self.data_dir = Path(self.api.tmpdir.name) / "data"
        self.data_dir.mkdir()
        for patcher in (
            patch.object(fixture.api_server, "DATA_DIR", self.data_dir),
            patch("cutover_deletion.IMAGE_DIR", Path(self.api.tmpdir.name) / "images"),
            patch.object(fixture.api_server, "ensure_source_email_archived"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.api.db.replace_all_supplier_circuits([
            fixture.CUSTOMER_CIRCUIT, fixture.BACKBONE_CIRCUIT,
        ])
        self.email_id = self.api.email_records_id
        self.subject = "跨区域骨干与客户线路割接通知 — Copenhagen / Hamburg 长距离传输维护"
        with self.api.db.get_connection() as connection:
            connection.execute("UPDATE email_records SET subject = ? WHERE id = ?", (self.subject, self.email_id))
            connection.commit()
        self.mail_directory = self.create_mail_files(self.email_id)
        excel = customer_excel_path(
            self.data_dir, mailbox_address="noc@example.com", email_uid=1000,
            filename="RT00_26012495.xlsx",
        )
        excel.parent.mkdir(parents=True, exist_ok=True)
        excel.write_bytes(b"isolated UI deletion fixture")
        # Generate real task records while keeping the fixture export inside its temporary directory.
        with patch.object(fixture.api_server, "build_template_workbook", return_value=object()), \
                patch.object(fixture.api_server, "save_workbook_output", return_value=excel):
            response = self.api.client.post(
                "/api/cutover/tasks/generate", headers=self.api.headers,
                json=self.api.mixed_fill_payload(),
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.tasks_before = self.api.db.list_cutover_tasks_by_email(self.email_id)
        self.assertEqual(len(self.tasks_before), 2)
        self.other_id = self.api.insert_email_record(subject="保留的另一封割接通知")
        self.other_directory = self.create_mail_files(self.other_id)
        payload = self.api.fill_payload(email_records_id=self.other_id, carrier_ticket_no="KEEP-001")
        payload["line_array_info"]["data"][0]["CircuitIDRT"] = "1940953"
        response = self.api.client.post("/api/cutover/tasks/generate", headers=self.api.headers, json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.other_before = self.api.db.get_email_record_by_id(self.other_id)
        self.other_tasks_before = self.api.db.list_cutover_tasks_by_email(self.other_id)
        self.circuits_before = self.api.db.get_all_supplier_circuits()
        self.suppliers_before = self.api.client.get("/api/suppliers", headers=self.api.headers).get_json()["data"]
        self.server = make_server(
            "127.0.0.1", 0, fixture.api_server.app, threaded=True,
            request_handler=QuietRequestHandler,
        )
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
        self.console_errors = []
        self.deletes = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("console", lambda message: self.console_errors.append(message.text)
                     if message.type == "error" else None)
        self.page.on("request", lambda request: self.deletes.append(request.url)
                     if request.method == "DELETE" and "/api/cutover/emails/" in request.url else None)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.page.goto(self.base + "/admin/cutover-tasks")
        self.page.get_by_role('button', name='管理员登录', exact=True).click()
        self.page.get_by_role("textbox", name="API Key").fill("test-key")
        self.page.get_by_role("button", name="登录", exact=True).click()
        expect(self.list_panel()).to_be_visible()
        expect(self.list_rows()).to_have_count(2)
        with self.page.expect_response(lambda response: response.url.endswith("/api/dashboard/summary") and response.status == 200):
            self.page.get_by_role("button", name="刷新运营摘要", exact=True).click()
        expect(self.page.locator(".operations-metric strong").first).to_have_text("3")
        expect(self.page.locator(".n-message").filter(has_text="登录成功")).not_to_be_visible()
        self.evidence = Path(__file__).resolve().parents[2] / ".qa" / "cutover-deletion"
        self.evidence.mkdir(parents=True, exist_ok=True)

    def close_server(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def create_mail_files(self, email_id):
        record = self.api.db.get_email_record_by_id(email_id)
        directory = message_storage_directory(
            self.data_dir, mailbox_address=record["receiver"], email_uid=record["email_id"],
        )
        (directory / "attachments").mkdir(parents=True)
        (directory / f"source-email-{record['email_id']}.eml").write_bytes(b"Subject: isolated fixture\r\n\r\nBody")
        (directory / "attachments" / "notice.txt").write_text("隔离测试附件", encoding="utf-8")
        return directory

    def list_panel(self):
        return self.page.locator(".cutover-list-view")

    def list_rows(self):
        return self.list_panel().locator(".n-data-table-tbody tr.n-data-table-tr")

    def target_row(self):
        return self.list_rows().filter(has_text=self.subject)

    def confirm_box(self):
        return self.page.locator(".n-dialog.cutover-delete-confirm")

    def open_confirmation(self, source):
        source.click()
        box = self.confirm_box()
        expect(box).to_be_visible()
        expect(box).to_contain_text("删除割接邮件及关联数据")
        return box

    def stable_screenshot(self, filename, confirmation=False):
        if confirmation:
            box = self.confirm_box()
            expect(box).to_have_css("opacity", "1")
            expect(self.page.locator(".n-modal-container").filter(has=box)).to_have_css("opacity", "1")
        else:
            expect(self.confirm_box()).not_to_be_visible()
            expect(self.page.locator(".n-modal-container").filter(has=self.confirm_box())).not_to_be_visible()
        self.page.wait_for_function("""() => document.getAnimations().every(animation =>
            animation.playState !== 'running' || animation.effect.getTiming().iterations === Infinity)
        """)
        self.assertFalse(self.page.evaluate("document.documentElement.scrollWidth > innerWidth"))
        if self.list_panel().is_visible():
            scroll = self.list_panel().locator(".cutover-six-table .n-data-table-base-table-body .n-scrollbar-container")
            self.assertTrue(scroll.evaluate("element => element.scrollWidth <= element.clientWidth + 1"))
        self.page.screenshot(path=str(self.evidence / filename), full_page=True)

    def assert_preserved_records(self):
        self.assertEqual(self.api.db.get_email_record_by_id(self.other_id), self.other_before)
        self.assertEqual(self.api.db.list_cutover_tasks_by_email(self.other_id), self.other_tasks_before)
        self.assertEqual(self.api.db.get_all_supplier_circuits(), self.circuits_before)
        self.assertEqual(self.api.client.get("/api/suppliers", headers=self.api.headers).get_json()["data"], self.suppliers_before)
        self.assertTrue((self.other_directory / "attachments" / "notice.txt").exists())

    def assert_clean_browser(self, expected_http_errors=()):
        unexpected = [message for message in self.console_errors if not any(
            re.search(rf"Failed to load resource:.*status of {status}\b", message)
            for status in expected_http_errors
        )]
        self.assertEqual(unexpected, [])
        self.assertEqual(self.errors, [])

    def test_list_cancel_then_real_delete_with_loading_and_preserved_other_data(self):
        record_before = self.api.db.get_email_record_by_id(self.email_id)
        delete = self.target_row().get_by_role("button", name="删除此邮件及关联数据", exact=True)
        self.stable_screenshot("list-1440.png")
        box = self.open_confirmation(delete)
        for text in ("EML", "附件", "Excel", "截图", "原始邮箱", "综调"):
            expect(box).to_contain_text(text)
        self.stable_screenshot("confirm-1440.png", confirmation=True)
        box.get_by_role("button", name="取消", exact=True).click()
        expect(box).not_to_be_visible()
        expect(delete).to_be_enabled()
        self.assertEqual(self.deletes, [])
        self.assertEqual(self.api.db.get_email_record_by_id(self.email_id), record_before)
        self.assertEqual(self.api.db.list_cutover_tasks_by_email(self.email_id), self.tasks_before)
        self.assertTrue(self.mail_directory.exists())

        held = []
        pattern = f"**/api/cutover/emails/{self.email_id}"
        def hold_delete(route):
            if route.request.method == "DELETE":
                held.append(route)
            else:
                route.continue_()
        self.page.route(pattern, hold_delete)
        try:
            self.open_confirmation(delete).get_by_role("button", name="确认删除", exact=True).click()
            expect(box).not_to_be_visible()
            expect(delete).to_be_disabled()
            expect(delete).to_have_class(re.compile(r"\bn-button--loading\b"))
            expect(self.target_row().locator(".cutover-read-action")).to_be_disabled()
            self.assertEqual(len(held), 1)
            bounds = delete.bounding_box()
            self.page.mouse.dblclick(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
            self.target_row().locator(".cutover-subject").click()
            expect(self.page).to_have_url(self.base + "/admin/cutover-tasks")
            with self.page.expect_response(lambda response: response.url.endswith("/api/dashboard/summary") and response.status == 200):
                held[0].continue_()
            expect(self.page.locator(".n-message").filter(has_text="割接邮件及关联数据已删除")).to_be_visible()
            expect(self.target_row()).to_have_count(0)
            expect(self.list_rows()).to_have_count(1)
            expect(self.page.locator(".operations-metric strong").first).to_have_text("1")
        finally:
            self.page.unroute(pattern, hold_delete)
        self.assertEqual(len(self.deletes), 1)
        self.assertEqual(len(held), 1)
        self.assertIsNone(self.api.db.get_email_record_by_id(self.email_id))
        self.assertEqual(self.api.db.list_cutover_tasks_by_email(self.email_id), [])
        self.assertFalse(self.mail_directory.exists())
        self.assert_preserved_records()
        self.stable_screenshot("list-deleted-1440.png")
        self.assert_clean_browser()

    def test_detail_real_delete_replaces_history_and_returns_to_list(self):
        self.page.set_viewport_size({"width": 1280, "height": 900})
        self.target_row().locator(".cutover-subject").click()
        expect(self.page).to_have_url(self.base + f"/admin/cutover-emails/{self.email_id}")
        delete = self.page.locator(".cutover-email-delete-action")
        expect(delete).to_be_visible()
        history_length = self.page.evaluate("history.length")
        self.stable_screenshot("detail-1280.png")
        box = self.open_confirmation(delete)
        self.stable_screenshot("confirm-1280.png", confirmation=True)
        with self.page.expect_response(lambda response: response.url.endswith("/api/dashboard/summary") and response.status == 200):
            box.get_by_role("button", name="确认删除", exact=True).click()
        expect(self.page.locator(".n-message").filter(has_text="割接邮件及关联数据已删除")).to_be_visible()
        expect(self.page).to_have_url(self.base + "/admin/cutover-tasks")
        expect(self.list_rows()).to_have_count(1)
        expect(self.page.locator(".operations-metric strong").first).to_have_text("1")
        self.assertEqual(self.page.evaluate("history.length"), history_length)
        self.page.go_back()
        expect(self.page).to_have_url(self.base + "/admin/cutover-tasks")
        expect(self.list_rows()).to_have_count(1)
        self.assertIsNone(self.api.db.get_email_record_by_id(self.email_id))
        self.assertEqual(self.api.db.list_cutover_tasks_by_email(self.email_id), [])
        self.assertEqual(len(self.deletes), 1)
        self.assert_preserved_records()
        self.stable_screenshot("detail-deleted-list-1280.png")
        self.assert_clean_browser()

    def test_failed_deletes_keep_rows_details_and_data(self):
        failure = {"status": 409, "message": "邮件正在处理，请稍后删除"}
        pattern = f"**/api/cutover/emails/{self.email_id}"
        def reject_delete(route):
            if route.request.method != "DELETE":
                route.continue_()
                return
            route.fulfill(status=failure["status"], content_type="application/json",
                          body=json.dumps({"success": False, "message": failure["message"]}, ensure_ascii=False))
        self.page.route(pattern, reject_delete)
        try:
            for surface in ("list", "detail"):
                if surface == "detail":
                    self.target_row().locator(".cutover-subject").click()
                    expect(self.page.locator(".cutover-email-delete-action")).to_be_visible()
                before = self.api.db.get_email_record_by_id(self.email_id)
                for status, message in ((409, "邮件正在处理，请稍后删除"), (404, "邮件记录已不存在，请刷新"), (500, "删除暂时失败，请稍后重试")):
                    with self.subTest(surface=surface, status=status):
                        failure.update(status=status, message=message)
                        source = self.target_row().get_by_role("button", name="删除此邮件及关联数据", exact=True) if surface == "list" else self.page.locator(".cutover-email-delete-action")
                        self.open_confirmation(source).get_by_role("button", name="确认删除", exact=True).click()
                        expect(self.page.locator(".n-message").filter(has_text=message)).to_be_visible()
                        expect(self.confirm_box()).not_to_be_visible()
                        expect(source).to_be_visible()
                        expect(source).to_be_enabled()
                        if surface == "list":
                            expect(self.list_rows()).to_have_count(2)
                        else:
                            expect(self.page).to_have_url(self.base + f"/admin/cutover-emails/{self.email_id}")
                            expect(self.page.locator(".topbar-breadcrumb")).to_contain_text("割接任务详情")
                            expect(self.page.locator(".view-body .supplier-back-link")).to_have_count(0)
                        self.assertEqual(self.api.db.get_email_record_by_id(self.email_id), before)
                        self.assertEqual(self.api.db.list_cutover_tasks_by_email(self.email_id), self.tasks_before)
                        self.assertTrue(self.mail_directory.exists())
                        if status != 500:
                            expect(self.page.locator(".n-message").filter(has_text=message)).not_to_be_visible()
                self.stable_screenshot(f"{surface}-delete-failed-1440.png")
                expect(self.page.locator(".n-message").filter(has_text=failure["message"])).not_to_be_visible()
        finally:
            self.page.unroute(pattern, reject_delete)
        self.assertEqual(len(self.deletes), 6)
        self.assert_preserved_records()
        self.assert_clean_browser(expected_http_errors=(404, 409, 500))

    def test_pagination_stays_inside_desktop_viewport_with_both_menu_states(self):
        for width, height in ((1280, 800), (1440, 1000)):
            self.page.set_viewport_size({'width': width, 'height': height})
            for collapsed in (False, True):
                with self.subTest(width=width, height=height, collapsed=collapsed):
                    toggle_name = '收起菜单' if collapsed else '展开菜单'
                    toggle = self.page.get_by_role('button', name=toggle_name, exact=True)
                    if toggle.count():
                        toggle.click()
                    self.page.wait_for_function("""() => document.getAnimations().every(animation =>
                        animation.playState !== 'running' || animation.effect.getTiming().iterations === Infinity)
                    """)
                    pagination = self.page.locator('.cutover-pagination')
                    expect(pagination).to_be_visible()
                    box = pagination.bounding_box()
                    self.assertIsNotNone(box)
                    self.assertGreaterEqual(box['y'], 0)
                    self.assertLessEqual(box['y'] + box['height'], height,
                                         f'Pagination must be reachable without clipping: {box}')
                    self.assertGreaterEqual(box['x'], 0)
                    self.assertLessEqual(box['x'] + box['width'], width)
                    expect(pagination.get_by_role('button', name='上一页', exact=True)).to_be_disabled()
                    self.page.screenshot(path=str(self.evidence / f'pagination-{width}-{height}-{"collapsed" if collapsed else "expanded"}.png'))
        self.assert_clean_browser()

    def test_last_page_delete_returns_to_previous_page(self):
        for index in range(19):
            self.api.insert_email_record(subject=f"后续割接通知 {index:02d}")
        with self.api.db.get_connection() as connection:
            connection.execute("UPDATE email_records SET create_time = '2020-01-01 00:00:00' WHERE id = ?", (self.email_id,))
            connection.commit()
        self.page.reload()
        expect(self.list_rows()).to_have_count(20)
        self.page.set_viewport_size({"width": 1280, "height": 900})
        self.stable_screenshot("list-21-emails-1280.png")
        self.list_panel().get_by_role('button', name='下一页', exact=True).click()
        expect(self.list_rows()).to_have_count(1)
        expect(self.target_row()).to_be_visible()
        expect(self.list_panel().locator(".n-pagination-item--active")).to_have_text("2")
        source = self.target_row().get_by_role("button", name="删除此邮件及关联数据", exact=True)
        self.open_confirmation(source).get_by_role("button", name="确认删除", exact=True).click()
        expect(self.page.locator(".n-message").filter(has_text="割接邮件及关联数据已删除")).to_be_visible()
        expect(self.list_rows()).to_have_count(20)
        expect(self.list_panel().locator(".n-pagination-item--active")).to_have_text("1")
        expect(self.list_panel().get_by_role('button', name='上一页', exact=True)).to_be_disabled()
        expect(self.page.locator(".operations-metric strong").first).to_have_text("1")
        records = self.api.client.get("/api/cutover/emails", headers=self.api.headers).get_json()["data"]
        self.assertEqual(records["total"], 20)
        self.assertIsNone(self.api.db.get_email_record_by_id(self.email_id))
        self.assertEqual(self.api.db.list_cutover_tasks_by_email(self.email_id), [])
        self.assertEqual(len(self.deletes), 1)
        self.assert_preserved_records()
        self.stable_screenshot("last-page-deleted-1280.png")
        self.assert_clean_browser()


if __name__ == "__main__":
    unittest.main()
