import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault('IMAP_SERVER', 'imap.example.com')
os.environ.setdefault('EMAIL_ADDRESS', 'test@example.com')
os.environ.setdefault('EMAIL_PASSWORD', 'password')
os.environ.setdefault('API_URL', 'https://api.example.com')
os.environ.setdefault('API_TOKEN', 'token')
os.environ.setdefault('API_KEY', 'test-key')

sys.path.insert(0, str(Path(__file__).resolve().parent))

import api_server
import cutover_task
from database import EmailDatabase
from supplier_config import SupplierConfigCreate, SupplierConfigRepository


CUSTOMER_CIRCUIT = {
    'supplier': 'RT',
    'supplier_circuit_id': '1940952',
    'circuit_id': 'EU202510000941',
    'line_type': '客户',
    'remark': '',
}

BACKBONE_CIRCUIT = {
    'supplier': 'RT',
    'supplier_circuit_id': '1940953',
    'circuit_id': 'BB202510000941',
    'line_type': '骨干',
    'remark': '',
}


class CutoverTaskApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = EmailDatabase(os.path.join(self.tmpdir.name, "mail_listener.db"))
        self.api_db_patch = patch.object(api_server, "email_db", self.db)
        self.api_db_patch.start()
        self.task_db_patch = patch.object(cutover_task, "email_db", self.db)
        self.task_db_patch.start()
        self.client = api_server.app.test_client()
        self.headers = {"Authorization": "Bearer test-key"}
        self.email_records_id = self.insert_email_record()

    def tearDown(self):
        self.task_db_patch.stop()
        self.api_db_patch.stop()
        self.tmpdir.cleanup()

    def insert_email_record(self, email_id=None, subject="割接通知", content="割接邮件正文"):
        if email_id is None:
            email_id = 1000 + self.db.get_statistics()['email_records']['total']
        self.db.add_email_record(
            email_id=email_id,
            sender="noc@supplier.example.com",
            receiver="noc@example.com",
            subject=subject,
            content=content,
        )
        return self.db.get_email_record(email_id)["id"]

    def fill_payload(self, **overrides):
        payload = {
            "email_records_id": self.email_records_id,
            "supplier": "RT",
            "carrier_ticket_no": "00/26012495",
            "cutover_time": "2026-06-12 14:00:00/2026-06-12 20:00:00",
            "cutover_timezone": "UTC",
            "cutover_reason": "Scheduled maintenance.",
            "location": "Odense - Aabenraa (Denmark)",
            "line_array_info": {"data": [{
                "CircuitID": "Customer circuit",
                "OrderNumber": "24-162081",
                "InternationalId": "International customer",
                "CircuitIDRT": "1940952",
                "ImpactDateTime": "2026-06-12 14:00:00/2026-06-12 20:00:00",
                "ImpactDuration": "4h",
                "InteruptionsCounts": "1",
            }]},
        }
        payload.update(overrides)
        return payload

    def mixed_fill_payload(self):
        payload = self.fill_payload()
        payload["line_array_info"] = {
            "data": [
                dict(payload["line_array_info"]["data"][0]),
                dict(payload["line_array_info"]["data"][0], CircuitIDRT="1940953"),
            ],
        }
        return payload

    def post_fill(self, payload, circuits=None):
        matched = circuits if circuits is not None else [CUSTOMER_CIRCUIT]
        with patch.object(api_server, "query_supplier_circuits", return_value=matched), \
                patch.object(api_server, "build_template_workbook", return_value=object()), \
                patch.object(api_server, "save_workbook_output", return_value=Path("/tmp/RT00_26012495.xlsx")):
            return self.client.post("/api/cutover/tasks/generate", headers=self.headers, json=payload)

    def post_fill_mixed(self, payload):
        with patch.object(api_server, "query_supplier_circuits",
                          side_effect=[[CUSTOMER_CIRCUIT], [BACKBONE_CIRCUIT]]), \
                patch.object(api_server, "build_template_workbook", return_value=object()), \
                patch.object(api_server, "save_workbook_output", return_value=Path("/tmp/RT00_26012495.xlsx")):
            return self.client.post("/api/cutover/tasks/generate", headers=self.headers, json=payload)

    def fill_tasks(self, response):
        return response.get_json()["data"]["tasks"]

    def first_task_id(self, response):
        return self.fill_tasks(response)[0]["id"]

    def test_fill_requires_email_records_id(self):
        payload = self.fill_payload()
        del payload["email_records_id"]

        response = self.client.post("/api/cutover/tasks/generate", headers=self.headers, json=payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("email_records_id", response.get_json()["message"])

    def test_fill_rejects_missing_email_record(self):
        response = self.post_fill(self.fill_payload(email_records_id=999999))

        self.assertEqual(response.status_code, 404)
        self.assertIn("邮件记录不存在", response.get_json()["message"])

    def test_fill_creates_task_and_repeat_fill_overwrites(self):
        response = self.post_fill(self.fill_payload())
        self.assertEqual(response.status_code, 200)
        tasks = self.fill_tasks(response)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["line_type"], "customer")
        self.assertEqual(tasks[0]["status"], "draft")
        task_id = tasks[0]["id"]

        task = self.db.get_cutover_task(task_id)
        self.assertEqual(task["email_records_id"], self.email_records_id)
        self.assertEqual(task["line_type"], "customer")
        self.assertEqual(task["supplier"], "RT")
        self.assertEqual(task["customer_excel_filename"], "RT00_26012495.xlsx")
        self.assertEqual(len(task["fill_result"]["circuits"]), 1)

        repeat = self.post_fill(self.fill_payload(cutover_reason="Updated reason."))
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(self.first_task_id(repeat), task_id)

        updated = self.db.get_cutover_task(task_id)
        self.assertEqual(updated["fill_payload"]["cutover_reason"], "Updated reason.")
        self.assertEqual(updated["status"], "draft")

    def test_fill_splits_tasks_by_line_type(self):
        response = self.post_fill_mixed(self.mixed_fill_payload())
        self.assertEqual(response.status_code, 200)
        tasks = self.fill_tasks(response)
        self.assertEqual([task["line_type"] for task in tasks], ["customer", "backbone"])
        self.assertEqual(tasks[0]["line_type_label"], "客户线路")
        self.assertEqual(tasks[1]["line_type_label"], "骨干线路")

        customer_task = self.db.get_cutover_task(tasks[0]["id"])
        backbone_task = self.db.get_cutover_task(tasks[1]["id"])
        self.assertEqual(len(customer_task["fill_result"]["circuits"]), 1)
        self.assertNotIn("backbone_circuits", customer_task["fill_result"])
        self.assertEqual(len(backbone_task["fill_result"]["backbone_circuits"]), 1)
        self.assertNotIn("circuits", backbone_task["fill_result"])
        self.assertIsNone(backbone_task["customer_excel_filename"])

        # 重新 fill 只包含客户线路时，骨干任务被删除
        refill = self.post_fill(self.fill_payload())
        self.assertEqual(refill.status_code, 200)
        self.assertIsNone(self.db.get_cutover_task(tasks[1]["id"]))
        self.assertEqual(len(self.db.list_cutover_tasks_by_email(self.email_records_id)), 1)

    def test_list_and_detail_endpoints(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))

        listing = self.client.get("/api/cutover/tasks", headers=self.headers)
        self.assertEqual(listing.status_code, 200)
        data = listing.get_json()["data"]
        self.assertEqual(data["total"], 1)
        item = data["items"][0]
        self.assertEqual(item["id"], task_id)
        self.assertEqual(item["status_label"], "待确认")
        self.assertEqual(item["line_type"], "customer")
        self.assertEqual(item["line_type_label"], "客户线路")
        self.assertEqual(item["line_count"], 1)
        self.assertEqual(item["subject"], "割接通知")

        filtered = self.client.get("/api/cutover/tasks?status=confirmed", headers=self.headers)
        self.assertEqual(filtered.get_json()["data"]["total"], 0)

        detail = self.client.get(f"/api/cutover/tasks/{task_id}", headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        detail_data = detail.get_json()["data"]
        self.assertEqual(detail_data["email"]["subject"], "割接通知")
        self.assertEqual(detail_data["reports"], [])
        self.assertEqual(detail_data["line_type_label"], "客户线路")
        self.assertIn("excel_download_url", detail_data)
        self.assertEqual(detail_data["fill_result"]["cutStartTime"], "2026-06-12 22:00:00")

        missing = self.client.get("/api/cutover/tasks/999999", headers=self.headers)
        self.assertEqual(missing.status_code, 404)

    def test_patch_backbone_task_fields(self):
        tasks = self.fill_tasks(self.post_fill_mixed(self.mixed_fill_payload()))
        backbone_task_id = tasks[1]["id"]

        response = self.client.patch(
            f"/api/cutover/tasks/{backbone_task_id}",
            headers=self.headers,
            json={"backbone_circuits": [{"基本信息": {"标题": "手工补录"}}]},
        )

        self.assertEqual(response.status_code, 200)
        task = self.db.get_cutover_task(backbone_task_id)
        self.assertEqual(task["status"], "draft")
        self.assertEqual(task["fill_result"]["backbone_circuits"][0]["基本信息"]["标题"], "手工补录")

        # 骨干任务不允许编辑客户侧字段
        rejected = self.client.patch(
            f"/api/cutover/tasks/{backbone_task_id}",
            headers=self.headers,
            json={"circuits": []},
        )
        self.assertEqual(rejected.status_code, 400)

        empty_patch = self.client.patch(f"/api/cutover/tasks/{backbone_task_id}", headers=self.headers, json={})
        self.assertEqual(empty_patch.status_code, 400)

    def test_patch_rejects_cross_type_field(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))

        response = self.client.patch(
            f"/api/cutover/tasks/{task_id}",
            headers=self.headers,
            json={"backbone_circuits": [{"基本信息": {"标题": "手工补录"}}]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("不支持编辑字段", response.get_json()["message"])

    def test_patch_customer_rows_regenerates_excel(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))
        task = self.db.get_cutover_task(task_id)
        edited_circuits = [dict(task["fill_result"]["circuits"][0], **{'客户名称': '手工客户'})]

        with patch.object(api_server, "build_template_workbook", return_value=object()) as build_workbook, \
                patch.object(api_server, "save_workbook_output", return_value=Path("/tmp/RT00_26012495.xlsx")) as save_workbook:
            response = self.client.patch(
                f"/api/cutover/tasks/{task_id}",
                headers=self.headers,
                json={"circuits": edited_circuits},
            )

        self.assertEqual(response.status_code, 200)
        build_workbook.assert_called_once()
        save_workbook.assert_called_once()
        updated = self.db.get_cutover_task(task_id)
        self.assertEqual(updated["fill_result"]["circuits"][0]["客户名称"], "手工客户")
        self.assertEqual(updated["status"], "draft")

    def test_confirm_and_report_flow(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))

        blocked_report = self.client.post(
            f"/api/cutover/tasks/{task_id}/report", headers=self.headers, json={},
        )
        self.assertEqual(blocked_report.status_code, 400)

        confirmed = self.client.post(f"/api/cutover/tasks/{task_id}/confirm", headers=self.headers)
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(confirmed.get_json()["data"]["status"], "confirmed")
        self.assertIsNotNone(self.db.get_cutover_task(task_id)["confirmed_at"])

        repeat_confirm = self.client.post(f"/api/cutover/tasks/{task_id}/confirm", headers=self.headers)
        self.assertEqual(repeat_confirm.status_code, 400)

        report = self.client.post(f"/api/cutover/tasks/{task_id}/report", headers=self.headers, json={})
        self.assertEqual(report.status_code, 202)
        report_payload = report.get_json()
        self.assertIn("尚未对接", report_payload["message"])
        self.assertEqual(report_payload["data"]["report_status"], "pending")

        reports = self.db.get_cutover_reports(task_id)
        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0]["status"], "pending")
        self.assertEqual(reports[0]["report_type"], "customer")

        # 任务保持已确认状态，可重复触发上报
        self.assertEqual(self.db.get_cutover_task(task_id)["status"], "confirmed")

    def test_edit_after_confirm_reverts_to_draft(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))
        self.client.post(f"/api/cutover/tasks/{task_id}/confirm", headers=self.headers)
        task = self.db.get_cutover_task(task_id)
        edited_circuits = [dict(task["fill_result"]["circuits"][0], **{'客户名称': '确认后补录'})]

        with patch.object(api_server, "build_template_workbook", return_value=object()), \
                patch.object(api_server, "save_workbook_output", return_value=Path("/tmp/RT00_26012495.xlsx")):
            response = self.client.patch(
                f"/api/cutover/tasks/{task_id}",
                headers=self.headers,
                json={"circuits": edited_circuits},
            )

        self.assertEqual(response.status_code, 200)
        task = self.db.get_cutover_task(task_id)
        self.assertEqual(task["status"], "draft")
        self.assertIsNone(task["confirmed_at"])

    def test_email_grouped_listing_with_nested_tasks(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))
        other_email_id = self.insert_email_record()
        self.post_fill(self.fill_payload(email_records_id=other_email_id, carrier_ticket_no="00/26012496"))

        listing = self.client.get("/api/cutover/emails", headers=self.headers)
        self.assertEqual(listing.status_code, 200)
        data = listing.get_json()["data"]
        self.assertEqual(data["total"], 2)

        first = data["items"][0]
        self.assertEqual(first["subject"], "割接通知")
        self.assertEqual(first["task_count"], 1)
        self.assertEqual(first["suppliers"], "RT")
        self.assertEqual(first["carrier_ticket_nos"], "00/26012496")
        self.assertIsNotNone(first["latest_update_time"])
        self.assertEqual(len(first["tasks"]), 1)
        task = first["tasks"][0]
        self.assertIn(task["id"], (task_id, task_id + 1))
        self.assertEqual(task["status_label"], "待确认")
        self.assertEqual(task["line_type"], "customer")
        self.assertEqual(task["line_type_label"], "客户线路")
        self.assertEqual(task["line_count"], 1)
        self.assertNotIn("fill_payload", task)
        self.assertNotIn("fill_result", task)

        filtered = self.client.get("/api/cutover/emails?status=confirmed", headers=self.headers)
        self.assertEqual(filtered.get_json()["data"]["total"], 0)

        self.client.post(f"/api/cutover/tasks/{task_id}/confirm", headers=self.headers)
        filtered = self.client.get("/api/cutover/emails?status=confirmed", headers=self.headers)
        filtered_data = filtered.get_json()["data"]
        self.assertEqual(filtered_data["total"], 1)
        self.assertEqual(len(filtered_data["items"][0]["tasks"]), 1)
        self.assertEqual(filtered_data["items"][0]["tasks"][0]["id"], task_id)

    def test_email_listing_supplier_sender_time_filters(self):
        # 供应商过滤与列表显示口径一致：按发件人所属供应商匹配，而非任务上的供应商
        SupplierConfigRepository(self.db).create(SupplierConfigCreate(
            name="RT",
            email="noc@supplier.example.com",
            can_reply_directly=True,
            cutover_extract_prompt="提取割接字段。",
        ))
        self.post_fill(self.fill_payload())

        matched_sender = self.client.get("/api/cutover/emails?sender=supplier.example", headers=self.headers)
        sender_data = matched_sender.get_json()["data"]
        self.assertEqual(sender_data["total"], 1)
        self.assertEqual(len(sender_data["items"][0]["tasks"]), 1)
        missed_sender = self.client.get("/api/cutover/emails?sender=no-such-sender", headers=self.headers)
        self.assertEqual(missed_sender.get_json()["data"]["total"], 0)

        matched_supplier = self.client.get("/api/cutover/emails?supplier=RT", headers=self.headers)
        self.assertEqual(matched_supplier.get_json()["data"]["total"], 1)
        missed_supplier = self.client.get("/api/cutover/emails?supplier=NOPE", headers=self.headers)
        self.assertEqual(missed_supplier.get_json()["data"]["total"], 0)
        # 任务上的供应商改为 OTHER 后，按发件人所属供应商 RT 仍能命中，按 OTHER 不命中
        listing = self.client.get("/api/cutover/emails?supplier=RT", headers=self.headers)
        task_pk = listing.get_json()["data"]["items"][0]["tasks"][0]["id"]
        self.db.update_cutover_task(task_pk, supplier="OTHER")
        self.assertEqual(
            self.client.get("/api/cutover/emails?supplier=RT", headers=self.headers).get_json()["data"]["total"], 1)
        self.assertEqual(
            self.client.get("/api/cutover/emails?supplier=OTHER", headers=self.headers).get_json()["data"]["total"], 0)

        from datetime import datetime, timedelta
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        wide_range = self.client.get(f"/api/cutover/emails?start={yesterday}&end={today}", headers=self.headers)
        self.assertEqual(wide_range.get_json()["data"]["total"], 1)
        future_start = self.client.get("/api/cutover/emails?start=2100-01-01", headers=self.headers)
        self.assertEqual(future_start.get_json()["data"]["total"], 0)
        past_end = self.client.get("/api/cutover/emails?end=2000-01-01", headers=self.headers)
        self.assertEqual(past_end.get_json()["data"]["total"], 0)

    def test_email_listing_and_detail_carry_scene_fields(self):
        self.post_fill(self.fill_payload())

        listing = self.client.get("/api/cutover/emails", headers=self.headers)
        item = listing.get_json()["data"]["items"][0]
        self.assertEqual(item["cutover_scene"], "normal")
        self.assertEqual(item["cutover_scene_label"], "正常割接")
        self.assertEqual(item["mail_type"], "")

        detail = self.client.get(f"/api/cutover/emails/{self.email_records_id}", headers=self.headers)
        data = detail.get_json()["data"]
        self.assertEqual(data["cutover_scene"], "normal")
        self.assertEqual(data["cutover_scene_label"], "正常割接")
        self.assertEqual(data["mail_type"], "")
        self.assertEqual(data["extract_result"], "")

        # 转发解析回写邮件类型与提取解析结果后，列表与详情同步展示
        self.assertTrue(self.db.update_email_record_mail_type(self.email_records_id, "割接通知"))
        self.assertTrue(self.db.update_email_record_extract_result(
            self.email_records_id, '{"mail_type": "割接通知"}'
        ))
        listing = self.client.get("/api/cutover/emails", headers=self.headers)
        self.assertEqual(listing.get_json()["data"]["items"][0]["mail_type"], "割接通知")
        detail = self.client.get(f"/api/cutover/emails/{self.email_records_id}", headers=self.headers)
        detail_data = detail.get_json()["data"]
        self.assertEqual(detail_data["mail_type"], "割接通知")
        self.assertEqual(detail_data["extract_result"], '{"mail_type": "割接通知"}')

    def test_rejected_scene_email_shows_in_listing_without_tasks(self):
        self.assertTrue(self.db.update_email_record_cutover_scene(self.email_records_id, "major_event"))
        # 列表范围 = 全部供应商邮件：无场景且无任务的普通邮件也会出现
        plain_email_id = self.insert_email_record(content="另一封无关正文")

        listing = self.client.get("/api/cutover/emails", headers=self.headers)
        data = listing.get_json()["data"]
        self.assertEqual(data["total"], 2)
        items_by_id = {item["id"]: item for item in data["items"]}
        rejected = items_by_id[self.email_records_id]
        self.assertEqual(rejected["cutover_scene"], "major_event")
        self.assertEqual(rejected["cutover_scene_label"], "重保期割接")
        self.assertEqual(rejected["task_count"], 0)
        self.assertEqual(rejected["tasks"], [])
        plain = items_by_id[plain_email_id]
        self.assertEqual(plain["cutover_scene"], "normal")
        self.assertEqual(plain["task_count"], 0)
        self.assertFalse(plain["is_duplicate"])

        # 任务级筛选不应命中无任务的邮件
        draft = self.client.get("/api/cutover/emails?status=draft", headers=self.headers)
        self.assertEqual(draft.get_json()["data"]["total"], 0)

    def test_duplicate_email_flagged_in_listing_and_detail(self):
        # 与 setUp 邮件同主题同正文、UID 不同 -> 判定为重复邮件
        duplicate_id = self.insert_email_record()

        listing = self.client.get("/api/cutover/emails", headers=self.headers)
        data = listing.get_json()["data"]
        self.assertEqual(data["total"], 2)
        items_by_id = {item["id"]: item for item in data["items"]}
        self.assertTrue(items_by_id[duplicate_id]["is_duplicate"])
        self.assertFalse(items_by_id[self.email_records_id]["is_duplicate"])

        detail = self.client.get(f"/api/cutover/emails/{duplicate_id}", headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.get_json()["data"]["is_duplicate"])
        original_detail = self.client.get(
            f"/api/cutover/emails/{self.email_records_id}", headers=self.headers)
        self.assertFalse(original_detail.get_json()["data"]["is_duplicate"])

    def test_listing_tag_filter(self):
        self.assertTrue(self.db.update_email_record_cutover_scene(self.email_records_id, "major_event"))
        duplicate_id = self.insert_email_record()  # 与 setUp 邮件内容相同 -> 重复邮件
        self.insert_email_record(content="普通非割接邮件正文")  # normal 场景且无任务

        major = self.client.get("/api/cutover/emails?tag=major_event", headers=self.headers)
        major_data = major.get_json()["data"]
        self.assertEqual(major_data["total"], 1)
        self.assertEqual(major_data["items"][0]["id"], self.email_records_id)

        duplicate = self.client.get("/api/cutover/emails?tag=duplicate", headers=self.headers)
        duplicate_data = duplicate.get_json()["data"]
        self.assertEqual(duplicate_data["total"], 1)
        self.assertEqual(duplicate_data["items"][0]["id"], duplicate_id)

        # 标签与邮件级条件组合过滤
        combined = self.client.get(
            "/api/cutover/emails?tag=duplicate&sender=supplier.example", headers=self.headers)
        self.assertEqual(combined.get_json()["data"]["total"], 1)
        missed = self.client.get(
            "/api/cutover/emails?tag=duplicate&sender=no-such-sender", headers=self.headers)
        self.assertEqual(missed.get_json()["data"]["total"], 0)

        # 任务级筛选与标签组合：重复邮件无任务，status 筛选不命中
        with_status = self.client.get(
            "/api/cutover/emails?tag=duplicate&status=draft", headers=self.headers)
        self.assertEqual(with_status.get_json()["data"]["total"], 0)

        invalid = self.client.get("/api/cutover/emails?tag=bogus", headers=self.headers)
        self.assertEqual(invalid.status_code, 400)
        self.assertIn("tag 取值非法", invalid.get_json()["message"])

    def test_email_listing_mail_type_filter_and_options(self):
        """邮件类型可筛选，且下拉选项接口返回已解析类型去重列表。"""
        other_id = self.insert_email_record(content="另一封邮件正文")
        self.assertTrue(self.db.update_email_record_mail_type(self.email_records_id, "割接通知"))
        self.assertTrue(self.db.update_email_record_mail_type(other_id, "故障通知"))

        options = self.client.get("/api/cutover/emails/mail-types", headers=self.headers)
        self.assertEqual(options.status_code, 200)
        self.assertEqual(sorted(options.get_json()["data"]), ["割接通知", "故障通知"])

        hit = self.client.get("/api/cutover/emails?mail_type=割接通知", headers=self.headers)
        hit_data = hit.get_json()["data"]
        self.assertEqual(hit_data["total"], 1)
        self.assertEqual(hit_data["items"][0]["id"], self.email_records_id)

        missed = self.client.get("/api/cutover/emails?mail_type=不存在类型", headers=self.headers)
        self.assertEqual(missed.get_json()["data"]["total"], 0)

    def test_listing_suppliers_follow_sender_config_for_all_emails(self):
        # 供应商列统一按发件人所属供应商显示，不取任务聚合值；发件人未配置时才退回任务聚合值
        SupplierConfigRepository(self.db).create(SupplierConfigCreate(
            name="RT",
            email="noc@supplier.example.com",
            can_reply_directly=True,
            cutover_extract_prompt="提取割接字段。",
        ))
        rejected_email_id = self.insert_email_record(content="拒绝场景邮件正文")
        self.assertTrue(self.db.update_email_record_cutover_scene(rejected_email_id, "major_event"))
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))
        self.db.update_cutover_task(task_id, supplier="OTHER")

        listing = self.client.get("/api/cutover/emails", headers=self.headers)
        items_by_id = {item["id"]: item for item in listing.get_json()["data"]["items"]}
        # 有任务邮件也按发件人配置显示，而非任务聚合值 OTHER
        self.assertEqual(items_by_id[self.email_records_id]["suppliers"], "RT")
        # 拒绝场景无任务邮件同样按发件人配置显示
        rejected = items_by_id[rejected_email_id]
        self.assertEqual(rejected["task_count"], 0)
        self.assertEqual(rejected["suppliers"], "RT")

        # 发件人未配置供应商时退回任务聚合值
        email_record = self.db.get_email_record_by_id(self.email_records_id)
        self.db.update_email_record(
            email_record["email_id"], sender="unknown@not-configured.example.com")
        listing = self.client.get("/api/cutover/emails", headers=self.headers)
        items_by_id = {item["id"]: item for item in listing.get_json()["data"]["items"]}
        self.assertEqual(items_by_id[self.email_records_id]["suppliers"], "OTHER")

    def test_task_detail_carries_email_scene(self):
        self.assertTrue(self.db.update_email_record_cutover_scene(self.email_records_id, "emergency"))
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))

        detail = self.client.get(f"/api/cutover/tasks/{task_id}", headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        data = detail.get_json()["data"]
        self.assertEqual(data["cutover_scene"], "emergency")
        self.assertEqual(data["cutover_scene_label"], "紧急割接")

    def test_cutover_email_detail_endpoint(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))

        with patch.object(api_server, "query_supplier_circuits", return_value=[CUSTOMER_CIRCUIT]):
            detail = self.client.get(f"/api/cutover/emails/{self.email_records_id}", headers=self.headers)
        self.assertEqual(detail.status_code, 200)
        data = detail.get_json()["data"]
        self.assertEqual(data["id"], self.email_records_id)
        self.assertEqual(data["subject"], "割接通知")
        self.assertEqual(data["content"], "割接邮件正文")
        self.assertIsNone(data["html_content"])
        self.assertEqual(data["sender"], "noc@supplier.example.com")
        self.assertEqual(len(data["tasks"]), 1)
        task = data["tasks"][0]
        self.assertEqual(task["id"], task_id)
        self.assertEqual(task["line_type"], "customer")
        self.assertEqual(task["line_type_label"], "客户线路")
        self.assertEqual(task["status_label"], "待确认")
        self.assertEqual(task["line_count"], 1)
        self.assertNotIn("fill_payload", task)
        self.assertNotIn("fill_result", task)

        line_table = data["line_table"]
        self.assertEqual(line_table["supplier"], "RT")
        self.assertEqual(len(line_table["lines"]), 1)
        first_line = line_table["lines"][0]
        self.assertIn("1940952", first_line["keywords"])
        self.assertEqual(first_line["circuits"], [CUSTOMER_CIRCUIT])

        missing = self.client.get("/api/cutover/emails/999999", headers=self.headers)
        self.assertEqual(missing.status_code, 404)

    def test_template_columns_endpoint(self):
        response = self.client.get("/api/cutover/template-columns", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        self.assertEqual(data["circuit"][0], "客户名称")
        self.assertEqual(data["circuit"][-1], "客户编码")
        self.assertEqual(data["reason"][0], "割接线路/设备名称")
        self.assertIn("割接原因", data["reason"])

    def test_download_task_excel(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))

        with tempfile.TemporaryDirectory() as data_dir:
            excel_path = Path(data_dir) / "RT00_26012495.xlsx"
            excel_path.write_bytes(b"fake-xlsx-content")
            with patch.object(api_server, "DATA_DIR", Path(data_dir)):
                response = self.client.get(f"/api/cutover/tasks/{task_id}/excel")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b"fake-xlsx-content")

        missing_task = self.client.get("/api/cutover/tasks/999999/excel")
        self.assertEqual(missing_task.status_code, 404)

    def test_switch_customer_task_to_backbone(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))
        original = self.db.get_cutover_task(task_id)
        circuit_code = original["fill_result"]["circuits"][0]["电路代号"]

        response = self.client.post(
            f"/api/cutover/tasks/{task_id}/switch-type",
            headers=self.headers,
            json={"line_type": "backbone"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"]["line_type"], "backbone")
        task = self.db.get_cutover_task(task_id)
        self.assertEqual(task["line_type"], "backbone")
        self.assertEqual(task["status"], "draft")
        self.assertIsNone(task["customer_excel_filename"])
        self.assertNotIn("circuits", task["fill_result"])
        backbone_circuit = task["fill_result"]["backbone_circuits"][0]
        self.assertEqual(backbone_circuit["割接对象"]["系统名称"], circuit_code)
        self.assertEqual(backbone_circuit["基本信息"]["标题"], task["fill_result"]["title"])
        self.assertIn("人员信息", backbone_circuit)
        self.assertIn("Scheduled maintenance.", backbone_circuit["基本信息"]["中断原因"])

    def test_switch_backbone_task_to_customer(self):
        backbone_task_id = self.first_task_id(
            self.post_fill(self.fill_payload(), circuits=[BACKBONE_CIRCUIT])
        )

        with patch.object(api_server, "build_template_workbook", return_value=object()) as build_workbook, \
                patch.object(api_server, "save_workbook_output", return_value=Path("/tmp/RT00_26012495.xlsx")):
            response = self.client.post(
                f"/api/cutover/tasks/{backbone_task_id}/switch-type",
                headers=self.headers,
                json={"line_type": "customer"},
            )

        self.assertEqual(response.status_code, 200)
        build_workbook.assert_called_once()
        task = self.db.get_cutover_task(backbone_task_id)
        self.assertEqual(task["line_type"], "customer")
        self.assertEqual(task["customer_excel_filename"], "RT00_26012495.xlsx")
        self.assertNotIn("backbone_circuits", task["fill_result"])
        circuit = task["fill_result"]["circuits"][0]
        self.assertEqual(circuit["电路代号"], "BB202510000941")
        self.assertEqual(len(task["fill_result"]["reasons"]), 1)

    def test_switch_rejects_conflict_with_existing_task(self):
        tasks = self.fill_tasks(self.post_fill_mixed(self.mixed_fill_payload()))
        customer_task_id = tasks[0]["id"]

        response = self.client.post(
            f"/api/cutover/tasks/{customer_task_id}/switch-type",
            headers=self.headers,
            json={"line_type": "backbone"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("已存在骨干线路任务", response.get_json()["message"])

    def test_switch_rejects_invalid_type(self):
        task_id = self.first_task_id(self.post_fill(self.fill_payload()))

        response = self.client.post(
            f"/api/cutover/tasks/{task_id}/switch-type",
            headers=self.headers,
            json={"line_type": "unknown"},
        )

        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
