import importlib
import os
import sys
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

api_server = importlib.import_module("api_server")


class AdminFrontendApiTest(unittest.TestCase):
    def test_admin_page_is_served(self):
        response = api_server.app.test_client().get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("NOC 工作台", html)
        # Vue 3 + Element Plus 架构：挂载点与脚本（含版本号注入）
        self.assertIn('<div id="app"></div>', html)
        self.assertIn('/static/vendor/vue.global.prod.js', html)
        self.assertIn('/static/vendor/element-plus.js', html)
        self.assertIn('/static/admin-shared.js?v=', html)
        self.assertIn('/static/admin-views.js?v=', html)
        self.assertIn('/static/admin.js?v=', html)

    def test_dispatch_session_page_is_served(self):
        response = api_server.app.test_client().get(
            "/admin/dispatch-session"
        )

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<div id="app"></div>', html)

    def test_admin_page_exposes_runtime_rpa_environment_and_global_badge(self):
        with patch.dict(
            os.environ,
            {"RPA_DEFAULT_ENVIRONMENT": "production"},
        ):
            response = api_server.app.test_client().get("/admin")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('data-rpa-default-environment="production"', html)

        source = (
            Path(__file__).resolve().parent / "static" / "admin.js"
        ).read_text(encoding="utf-8")
        self.assertIn('class="rpa-environment-badge"', source)
        self.assertIn("portalEnvironmentTone", source)
        self.assertIn("common.rpaProductionEnvironment", source)

        translations = (
            Path(__file__).resolve().parent / "static" / "admin-i18n.js"
        ).read_text(encoding="utf-8")
        self.assertNotIn('production: "生产环境"', translations)

        styles = (
            Path(__file__).resolve().parent / "static" / "admin.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".rpa-environment-badge.is-test", styles)
        self.assertIn(".rpa-environment-badge.is-production", styles)

    def test_auth_check_passes_with_valid_api_key(self):
        client = api_server.app.test_client()

        response = client.get(
            "/api/auth/check",
            headers={"Authorization": "Bearer test-key"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

    def test_auth_check_rejects_missing_or_invalid_key(self):
        client = api_server.app.test_client()

        missing = client.get("/api/auth/check")
        invalid = client.get(
            "/api/auth/check",
            headers={"Authorization": "Bearer wrong-key"},
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)

    def test_customer_cutover_enum_controls_are_declared(self):
        source = (Path(__file__).resolve().parent / "static" / "admin-views.js").read_text()

        self.assertIn('"客户电路在割接段是否有保护": ["无保护", "有保护"]', source)
        self.assertIn('"预计影响客户业务时长": ["不中断", "瞬断"]', source)
        self.assertIn('customerEnumOptions(column, row)', source)
        self.assertIn(':class="customerColumnClass(column)"', source)
        self.assertIn('const backboneInterruptionMinutes = ref([])', source)
        self.assertIn(
            'handleBackboneEnumChange(card, cardIndex, sectionName, fieldName, value)',
            source,
        )
        self.assertIn(
            'card[sectionName]["中断时间 (分钟)"] = backboneInterruptionMinutes.value[cardIndex] ?? "";',
            source,
        )
        self.assertIn(
            'basicInfo["中断时间 (分钟)"] = backboneInterruptionMinutes.value[cardIndex] ?? "";',
            source,
        )

        styles = (Path(__file__).resolve().parent / "static" / "admin.css").read_text()
        self.assertIn(".sheet-table th.customer-protection-column", styles)
        self.assertIn(".sheet-table th.customer-impact-duration-column", styles)

    def test_supplier_form_uses_reply_email_without_direct_reply_toggle(self):
        source = (
            Path(__file__).resolve().parent / "static" / "admin-views.js"
        ).read_text(encoding="utf-8")

        self.assertIn('reply_email: ""', source)
        self.assertIn('reply_email: form.reply_email.trim()', source)
        self.assertIn("supplierForm.replyEmailLabel", source)
        self.assertNotIn("can_reply_directly", source)
        self.assertNotIn("supplierForm.canReplyDirectly", source)

    def test_reply_task_exposes_editable_cc_recipients(self):
        source = (
            Path(__file__).resolve().parent / "static" / "admin-views.js"
        ).read_text(encoding="utf-8")

        self.assertIn('v-model="replyCcRecipients"', source)
        self.assertIn('v-model="replyCcRecipients" multiple filterable allow-create clearable', source)
        self.assertIn("cc_recipients: ccRecipients", source)
        self.assertIn("cutover.detail.replyCcPlaceholder", source)

    def test_cutover_list_tags_use_pending_scene_before_reply_is_sent(self):
        source = (
            Path(__file__).resolve().parent / "static" / "admin-shared.js"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "const scene = row.pending_reply_scene || row.cutover_scene;",
            source,
        )
        self.assertIn("if (isRejectedScene(scene))", source)

    def test_backbone_interruption_duration_uses_inline_minutes_control(self):
        source = (
            Path(__file__).resolve().parent / "static" / "admin-views.js"
        ).read_text(encoding="utf-8")
        styles = (
            Path(__file__).resolve().parent / "static" / "admin.css"
        ).read_text(encoding="utf-8")
        self.assertIn('class="backbone-interruption-control"', source)
        self.assertIn('aria-label="中断时间 (分钟)"', source)
        self.assertIn(
            'v-if="card[sectionName][\'中断类型\'] === \'中断\'"',
            source,
        )
        self.assertIn(
            '].filter((name) => name !== "中断时间 (分钟)");',
            source,
        )
        self.assertIn(".backbone-interruption-duration", styles)
        self.assertIn(".backbone-interruption-unit", styles)

    def test_system_settings_declares_backbone_personnel_fields(self):
        source = (
            Path(__file__).resolve().parent / "static" / "admin-views.js"
        ).read_text(encoding="utf-8")

        self.assertIn('backbone_noc_phone: nocPhone.value.trim()', source)
        self.assertIn(
            'backbone_province_reviewer_name: provinceReviewerName.value.trim()',
            source,
        )
        self.assertIn(
            'backbone_province_reviewer_phone: provinceReviewerPhone.value.trim()',
            source,
        )
        self.assertIn("settings.backbonePersonnelTitle", source)

    def test_cutover_task_declares_non_blocking_actions_and_live_report_progress(self):
        source = (
            Path(__file__).resolve().parent / "static" / "admin-views.js"
        ).read_text(encoding="utf-8")

        self.assertIn('const reportProgressVisible = ref(false)', source)
        self.assertIn('requestJson(`/api/cutover/reports/${reportId}`)', source)
        self.assertIn('<el-drawer v-model="reportProgressVisible"', source)
        self.assertIn('const payload = await runAction(', source)
        self.assertIn('applyResult(payload, tt("cutover.task.savedFallback"))', source)

    def test_cutover_email_detail_declares_api_forward_status_and_retry(self):
        source = (
            Path(__file__).resolve().parent / "static" / "admin-views.js"
        ).read_text(encoding="utf-8")
        styles = (
            Path(__file__).resolve().parent / "static" / "admin.css"
        ).read_text(encoding="utf-8")
        translations = (
            Path(__file__).resolve().parent / "static" / "admin-i18n.js"
        ).read_text(encoding="utf-8")

        self.assertIn('const apiForwardBusy = ref(false)', source)
        self.assertIn(
            '`/api/cutover/emails/${props.emailRecordId}/forward-attempts`',
            source,
        )
        self.assertIn('class="api-forward-card"', source)
        self.assertIn(':loading="apiForwardBusy"', source)
        self.assertIn("email.api_forward.error && !apiForwardBusy", source)
        self.assertIn("apiForwardBusy ? 'forwarding'", source)
        self.assertIn(':aria-busy="apiForwardBusy"', source)
        self.assertIn(".api-forward-card", styles)
        self.assertIn('apiForwardTitle: "邮件解析"', translations)
        self.assertIn('apiForwardRetry: "重新解析"', translations)

    def test_cutover_email_line_match_table_uses_circuit_columns_and_block_state(self):
        # Given
        source = (
            Path(__file__).resolve().parent / "static" / "admin-views.js"
        ).read_text(encoding="utf-8")

        # When / Then
        self.assertIn("line.task_generation_blocked", source)
        self.assertIn("row.line_status", source)
        self.assertIn("$t('circuits.lineType')", source)
        self.assertIn("$t('circuits.lineStatus')", source)


if __name__ == "__main__":
    unittest.main()
