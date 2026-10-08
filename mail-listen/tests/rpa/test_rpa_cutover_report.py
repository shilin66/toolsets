import importlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic

from PIL import Image

cutover_report_module = importlib.import_module("rpa.cutover_report")
session_config_module = importlib.import_module("rpa.session_config")
session_models_module = importlib.import_module("rpa.session_models")

PortalCutoverReportRpa = cutover_report_module.PortalCutoverReportRpa
build_cutover_report_url = cutover_report_module.build_cutover_report_url
CutoverReportManualInterventionError = (
    cutover_report_module.CutoverReportManualInterventionError
)
PortalSessionSettings = session_config_module.PortalSessionSettings
PortalEnvironment = session_models_module.PortalEnvironment
PortalSessionError = session_models_module.PortalSessionError


REPORT_PAGE = """<!doctype html>
<html lang="zh-CN">
<style>
  .el-checkbox__input { display: inline-block; width: 16px; height: 16px; }
  .el-checkbox__inner { display: block; width: 14px; height: 14px; border: 1px solid blue; }
  .el-checkbox__original { position: absolute; left: -9999px; }
</style>
<body>
  <button id="excel-import">EXCEL导入</button>
  <section id="import-dialog" hidden>
    <h2>传输任务及影响电路导入</h2>
    <input id="excel-file" type="file" accept=".xlsx">
    <button id="submit">提交</button>
  </section>
  <section id="existing-task" class="el-message-box" role="dialog" hidden>
    <h2>提示</h2>
    <p>发现任务在数据库中已存在，点击以下任务号链接查看详细信息</p>
    <a href="#existing-task-details">QT2026GJJJ000293</a>
    <p>点击"继续"将向该任务追加影响电路</p>
    <p>点击"停止"将停止本次导入</p>
    <button class="stop">停止</button>
    <button class="continue">继续</button>
  </section>
  <section id="customer-warning" class="el-dialog" role="dialog" hidden>
    <h2>提示</h2>
    <p>发现有电路没有填写客户名称，电路对应的客户名称将以系统中的为准，是否继续？</p>
    <button class="continue">继续</button>
  </section>
  <section id="temporary-confirm" class="el-dialog" role="dialog" hidden>
    <h2>临时电路确认</h2>
    <div class="el-table__header-wrapper" hidden>
      <span class="el-checkbox__input" role="checkbox">
        <span class="el-checkbox__inner"></span>
        <input class="el-checkbox__original" type="checkbox">
      </span><span>全选</span>
    </div>
    <div class="el-table__header-wrapper">
      <span id="select-all-control" class="el-checkbox__input" role="checkbox">
        <span class="el-checkbox__inner"></span>
        <input id="select-all" class="el-checkbox__original" type="checkbox">
      </span><span>全选</span>
    </div>
    <button class="continue">继续</button>
  </section>
  <section id="missing-circuit" class="el-dialog" role="dialog" hidden>
    <h2>临时电路确认</h2>
    <p>以下电路编号系统中不存在！系统无法解析，请填写空白项，确认是否存入你填写的客户信息下(打勾)!</p>
    <div class="el-table__header-wrapper">
      <span id="missing-circuit-select-all-control" class="el-checkbox__input" role="checkbox">
        <span class="el-checkbox__inner"></span>
        <input id="missing-circuit-select-all" class="el-checkbox__original" type="checkbox">
      </span><span>全选</span>
    </div>
    <button class="continue">继续</button>
  </section>
  <section id="unknown-dialog" class="el-dialog" role="dialog" hidden>
    <h2>需要补充未知参数</h2>
    <button>确定</button>
  </section>
  <section id="import-log" class="el-dialog" role="dialog" hidden>
    <h2>导入日志</h2>
    <p>导入成功的任务 1 条，导入失败的任务 0 条；</p>
    <p>导入成功的电路 1 条，导入失败的电路 0 条；</p>
    <p>导入涉及的任务号: QT2026GJJJ000293</p>
  </section>
  <section id="inline-import-log" hidden>
    <h2>导入日志</h2>
    <p>导入成功的任务 1 条，导入失败的任务 0 条；</p>
    <p>导入成功的电路 1 条，导入失败的电路 0 条；</p>
    <p>导入涉及的任务号: QT2026GJJJ000293</p>
  </section>
  <script>
    const dialog = document.querySelector("#import-dialog");
    const fileInput = document.querySelector("#excel-file");
    const warning = document.querySelector("#customer-warning");
    const existingTask = document.querySelector("#existing-task");
    const temporaryConfirm = document.querySelector("#temporary-confirm");
    const missingCircuit = document.querySelector("#missing-circuit");
    const importLog = document.querySelector("#import-log");
    const scenario = document.cookie.includes("portal_auth=existing-task")
      ? "existing-task"
      : document.cookie.includes("portal_auth=no-temp")
      ? "no-temp"
      : document.cookie.includes("portal_auth=unknown")
        ? "unknown"
        : document.cookie.includes("portal_auth=transition")
          ? "transition"
        : document.cookie.includes("portal_auth=missing-circuit")
          ? "missing-circuit"
        : document.cookie.includes("portal_auth=stale-temporary")
          ? "stale-temporary"
        : document.cookie.includes("portal_auth=reused-warning")
            ? "reused-warning"
          : document.cookie.includes("portal_auth=inline-log")
            ? "inline-log"
          : "temporary";
    let warningCount = 0;
    document.querySelector("#excel-import").addEventListener("click", () => {
      dialog.hidden = false;
    });
    document.querySelector("#submit").addEventListener("click", () => {
      const filename = fileInput.files.length ? fileInput.files[0].name : "";
      if (filename.endsWith(".xlsx")) {
        if (scenario === "unknown") {
          document.querySelector("#unknown-dialog").hidden = false;
        } else if (scenario === "existing-task") {
          existingTask.hidden = false;
        } else {
          warning.hidden = false;
        }
      }
    });
    existingTask.querySelector(".continue").addEventListener("click", () => {
      existingTask.hidden = true;
      warning.hidden = false;
    });
    warning.querySelector(".continue").addEventListener("click", () => {
      warningCount += 1;
      if (scenario === "existing-task") {
        warning.hidden = true;
        importLog.querySelector("p").textContent = "导入成功的任务 0 条，导入失败的任务 0 条；";
        importLog.hidden = false;
        return;
      }
      if (scenario === "reused-warning") {
        if (warningCount >= 2) {
          warning.hidden = true;
          temporaryConfirm.hidden = false;
        }
        return;
      }
      if (scenario === "transition") {
        warning.style.opacity = "0";
        setTimeout(() => { temporaryConfirm.hidden = false; }, 300);
        return;
      }
      warning.hidden = true;
      if (warningCount < 2) {
        setTimeout(() => { warning.hidden = false; }, 0);
      } else if (scenario === "missing-circuit") {
        missingCircuit.hidden = false;
      } else if (
        scenario === "temporary"
        || scenario === "inline-log"
        || scenario === "stale-temporary"
      ) {
        temporaryConfirm.hidden = false;
      } else {
        importLog.hidden = false;
      }
    });
    temporaryConfirm.querySelector(".continue").addEventListener("click", () => {
      if (document.querySelector("#select-all").checked) {
        if (scenario === "stale-temporary") {
          document.querySelector("#select-all-control").remove();
          setTimeout(() => {
            temporaryConfirm.hidden = true;
            importLog.hidden = false;
          }, 500);
          return;
        }
        if (scenario === "inline-log") {
          temporaryConfirm.style.opacity = "0";
          temporaryConfirm.style.pointerEvents = "none";
          document.querySelector("#inline-import-log").hidden = false;
          return;
        }
        temporaryConfirm.hidden = true;
        importLog.hidden = false;
      }
    });
    document.querySelector("#select-all-control").addEventListener("click", () => {
      document.querySelector("#select-all").checked = true;
    });
    document.querySelector("#missing-circuit-select-all-control").addEventListener("click", () => {
      document.querySelector("#missing-circuit-select-all").checked = true;
    });
    missingCircuit.querySelector(".continue").addEventListener("click", () => {
      if (document.querySelector("#missing-circuit-select-all").checked) {
        missingCircuit.hidden = true;
        importLog.hidden = false;
      }
    });
  </script>
</body>
</html>""".encode()

LOGIN_PAGE = """<!doctype html>
<html lang="zh-CN"><body>
  <input id="username" placeholder="请输入用户名">
  <input id="mobile" placeholder="手机号">
</body></html>""".encode()


class FakePortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        authenticated = "portal_auth=" in self.headers.get("Cookie", "")
        body = REPORT_PAGE if authenticated else LOGIN_PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class PortalCutoverReportRpaTest(unittest.TestCase):
    def test_builds_direct_cutover_report_url_with_dynamic_timestamp(self):
        url = build_cutover_report_url(
            "https://ofm.crm.189.cn:23122/portal/"
            "?ignoreDisableDevtool=true#/",
            timestamp_ms=1_788_417_784_416,
        )

        self.assertEqual(
            url,
            "https://ofm.crm.189.cn:23122/portal/"
            "?ignoreDisableDevtool=true#/iframe/"
            "https%3A%2F%2Fofm.crm.189.cn%3A23122%2ForderHandle%2F"
            "index.html%23%2FemOrderCreate%2FeeOrderCoEffect_iframePath/"
            "%E5%89%B2%E6%8E%A5%E5%BD%B1%E5%93%8D/"
            "?t=1788417784416",
        )

    def test_uploads_customer_excel_from_saved_session_on_direct_page(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                self._assert_excel_upload(server.server_port)
            finally:
                server.shutdown()
                server_thread.join()

    def test_waits_for_fading_warning_before_temporary_circuit_confirmation(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                self._assert_excel_upload(
                    server.server_port,
                    cookie_value="transition",
                )
            finally:
                server.shutdown()
                server_thread.join()

    def test_continues_existing_task_before_single_customer_confirmation(self) -> None:
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                self._assert_excel_upload(server.server_port, "existing-task")
            finally:
                server.shutdown()
                server_thread.join()

    def test_handles_reused_customer_warning_after_each_settled_click(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                self._assert_excel_upload(
                    server.server_port,
                    cookie_value="reused-warning",
                )
            finally:
                server.shutdown()
                server_thread.join()

    def test_accepts_success_log_outside_dialog_while_old_dialog_remains(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                self._assert_excel_upload(
                    server.server_port,
                    cookie_value="inline-log",
                )
            finally:
                server.shutdown()
                server_thread.join()

    def test_success_log_requires_zero_failed_tasks_and_circuits(self):
        parse = PortalCutoverReportRpa._extract_successful_portal_task_number
        successful_log = (
            "导入成功的任务 1 条，导入失败的任务 0 条；\n"
            "导入成功的电路 1 条，导入失败的电路 0 条；\n"
            "导入涉及的任务号: QT2026GJJJ000311"
        )

        self.assertEqual(parse(successful_log), "QT2026GJJJ000311")
        self.assertIsNone(parse(successful_log.replace("失败的任务 0", "失败的任务 1")))
        self.assertIsNone(parse(successful_log.replace("失败的电路 0", "失败的电路 1")))

    def test_success_log_accepts_circuit_append_without_new_task(self) -> None:
        log = (
            "导入成功的任务 0 条，导入失败的任务 0 条；\n"
            "导入成功的电路 1 条，导入失败的电路 0 条；\n"
            "导入涉及的任务号: QT2026GJJJ000371\n"
            "电路未填写客户名称,使用系统内客户名称"
        )

        task_number = PortalCutoverReportRpa._extract_successful_portal_task_number(log)

        self.assertEqual(task_number, "QT2026GJJJ000371")

    def test_success_log_rejects_empty_failed_or_incomplete_appends(self) -> None:
        log = (
            "导入成功的任务 0 条，导入失败的任务 0 条；\n"
            "导入成功的电路 1 条，导入失败的电路 0 条；\n"
            "导入涉及的任务号: QT2026GJJJ000371"
        )
        invalid_logs = (
            log.replace("成功的电路 1", "成功的电路 0"),
            log.replace("失败的任务 0", "失败的任务 1"),
            log.replace("失败的电路 0", "失败的电路 1"),
            log.replace("导入成功的电路 1 条，", ""),
            log.replace("导入失败的任务 0 条", ""),
            log.replace("导入失败的电路 0 条", ""),
            log.replace("QT2026GJJJ000371", ""),
        )
        for invalid_log in invalid_logs:
            with self.subTest(log=invalid_log):
                task_number = PortalCutoverReportRpa._extract_successful_portal_task_number(invalid_log)
                self.assertIsNone(task_number)

    def test_waits_for_loading_overlay_before_operation_screenshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            settings = PortalSessionSettings(**{
                "_env_file": None,
                "artifact_dir": temp_path,
                "timeout_ms": 2_000,
                "report_action_delay_ms": 0,
            })
            operation_log = []
            with cutover_report_module.sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content("""
                  <style>
                    .el-loading-mask {
                      position: fixed; inset: 0; z-index: 99;
                      background: rgb(255, 0, 0);
                    }
                  </style>
                  <main>页面已加载</main>
                  <div id="loader" class="el-loading-mask"></div>
                  <script>setTimeout(() => loader.remove(), 300);</script>
                """)
                PortalCutoverReportRpa(settings)._capture_operation_step(
                    page,
                    temp_path / "result.png",
                    operation_log,
                    "settled",
                    "页面稳定后截图",
                )
                browser.close()

            with Image.open(operation_log[0].screenshot_path) as screenshot:
                self.assertNotEqual(screenshot.convert("RGB").getpixel((5, 5)), (255, 0, 0))

    def test_spaces_report_clicks_by_configured_delay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = PortalSessionSettings(**{
                "_env_file": None,
                "artifact_dir": Path(temp_dir),
                "timeout_ms": 2_000,
                "report_action_delay_ms": 150,
            })
            with cutover_report_module.sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content('<button id="next">继续</button>')
                started_at = monotonic()
                PortalCutoverReportRpa(settings)._click_with_pacing(
                    page,
                    page.locator("#next"),
                )
                elapsed = monotonic() - started_at
                browser.close()

            self.assertGreaterEqual(elapsed, 0.14)

    def test_selects_most_specific_visible_dialog_when_dialogs_are_nested(self):
        settings = PortalSessionSettings(**{
            "_env_file": None,
            "report_action_delay_ms": 0,
        })
        with cutover_report_module.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content("""
              <section id="outer" class="el-dialog">
                <h2>传输任务及影响电路导入</h2>
                <section id="customer-warning" class="el-dialog" role="dialog">
                  <p>发现有电路没有填写客户名称，是否继续？</p>
                  <button>继续</button>
                </section>
                <button id="outer-continue">继续</button>
              </section>
            """)

            dialog = PortalCutoverReportRpa(settings)._visible_dialog_containing(
                page,
                "发现有电路没有填写客户名称",
            )

            self.assertIsNotNone(dialog)
            self.assertEqual(dialog.get_attribute("id"), "customer-warning")
            browser.close()

    def _assert_excel_upload(self, port: int, cookie_value: str = "1") -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            state_path = temp_path / "auth-state.json"
            state_path.write_text(
                json.dumps({
                    "cookies": [{
                        "name": "portal_auth",
                        "value": cookie_value,
                        "domain": "127.0.0.1",
                        "path": "/",
                        "expires": -1,
                        "httpOnly": False,
                        "secure": False,
                        "sameSite": "Lax",
                    }],
                    "origins": [],
                }),
                encoding="utf-8",
            )
            excel_path = temp_path / "RT00_26012495.xlsx"
            excel_path.write_bytes(b"fake-xlsx-content")
            screenshot_path = temp_path / "report-success.png"
            settings = PortalSessionSettings(**{
                "_env_file": None,
                "test_login_url": f"http://127.0.0.1:{port}/portal/#/pLogin",
                "test_mobile_login_url": f"http://127.0.0.1:{port}/portal/#/login",
                "test_session_check_url": f"http://127.0.0.1:{port}/portal/#/",
                "headless": True,
                "test_state_path": state_path,
                "artifact_dir": temp_path,
                "timeout_ms": 5_000,
                "report_action_delay_ms": 0,
            })

            result = PortalCutoverReportRpa(settings).upload_customer_excel(
                excel_path,
                environment=PortalEnvironment.TEST,
                screenshot_path=screenshot_path,
            )

            self.assertEqual(result.uploaded_filename, excel_path.name)
            self.assertIn(
                f"http://127.0.0.1:{port}/portal/"
                "?ignoreDisableDevtool=true#/iframe/",
                result.final_url,
            )
            self.assertIn("_iframePath/%E5%89%B2%E6%8E%A5%E5%BD%B1%E5%93%8D/", result.final_url)
            self.assertEqual(result.success_screenshot_path, screenshot_path)
            self.assertTrue(screenshot_path.is_file())
            self.assertEqual(result.portal_task_number, "QT2026GJJJ000293")
            expected_steps = [
                "excel_selected",
                "submit_clicked",
            ]
            if cookie_value == "existing-task":
                expected_steps.append("existing_task_confirmation")
            expected_steps.append("customer_name_warning_1")
            if cookie_value not in ("transition", "existing-task"):
                expected_steps.append("customer_name_warning_2")
            if cookie_value not in ("no-temp", "existing-task"):
                expected_steps.extend([
                    "temporary_circuits_detected",
                    "temporary_circuits_selected",
                ])
            expected_steps.append("import_log")
            self.assertEqual(
                [step.step for step in result.operation_log],
                expected_steps,
            )
            self.assertTrue(all(
                step.screenshot_path.is_file() for step in result.operation_log
            ))

    def test_import_without_temporary_circuit_skips_confirmation(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                self._assert_excel_upload(server.server_port, "no-temp")
            finally:
                server.shutdown()
                server_thread.join()

    def test_does_not_reprocess_temporary_dialog_while_it_is_closing(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                self._assert_excel_upload(
                    server.server_port,
                    "stale-temporary",
                )
            finally:
                server.shutdown()
                server_thread.join()

    def test_unknown_dialog_requires_manual_intervention_with_screenshot(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    state_path = temp_path / "auth-state.json"
                    state_path.write_text(json.dumps({
                        "cookies": [{
                            "name": "portal_auth", "value": "unknown",
                            "domain": "127.0.0.1", "path": "/", "expires": -1,
                            "httpOnly": False, "secure": False, "sameSite": "Lax",
                        }],
                        "origins": [],
                    }), encoding="utf-8")
                    excel_path = temp_path / "RT00.xlsx"
                    excel_path.write_bytes(b"fake")
                    settings = PortalSessionSettings(**{
                        "_env_file": None,
                        "test_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/pLogin",
                        "test_mobile_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/login",
                        "test_session_check_url": f"http://127.0.0.1:{server.server_port}/portal/#/",
                        "headless": True,
                        "test_state_path": state_path,
                        "artifact_dir": temp_path,
                        "timeout_ms": 5_000,
                    })
                    report_dir = temp_path / "2026-09-04" / "135" / "10_19"

                    with self.assertRaises(CutoverReportManualInterventionError) as caught:
                        PortalCutoverReportRpa(settings).upload_customer_excel(
                            excel_path,
                            environment=PortalEnvironment.TEST,
                            screenshot_path=report_dir / "report-success.png",
                        )

                    self.assertTrue(caught.exception.screenshot_path.is_file())
                    self.assertEqual(
                        caught.exception.screenshot_path.parent,
                        report_dir,
                    )
                    self.assertEqual(
                        caught.exception.operation_log[-1].step,
                        "manual_intervention_required",
                    )
            finally:
                server.shutdown()
                server_thread.join()

    def test_missing_circuit_number_requires_manual_intervention(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    state_path = temp_path / "auth-state.json"
                    state_path.write_text(json.dumps({
                        "cookies": [{
                            "name": "portal_auth", "value": "missing-circuit",
                            "domain": "127.0.0.1", "path": "/", "expires": -1,
                            "httpOnly": False, "secure": False, "sameSite": "Lax",
                        }],
                        "origins": [],
                    }), encoding="utf-8")
                    excel_path = temp_path / "RT00.xlsx"
                    excel_path.write_bytes(b"fake")
                    settings = PortalSessionSettings(**{
                        "_env_file": None,
                        "test_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/pLogin",
                        "test_mobile_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/login",
                        "test_session_check_url": f"http://127.0.0.1:{server.server_port}/portal/#/",
                        "headless": True,
                        "test_state_path": state_path,
                        "artifact_dir": temp_path,
                        "timeout_ms": 5_000,
                        "report_action_delay_ms": 0,
                    })

                    with self.assertRaises(CutoverReportManualInterventionError) as caught:
                        PortalCutoverReportRpa(settings).upload_customer_excel(
                            excel_path,
                            environment=PortalEnvironment.TEST,
                            screenshot_path=temp_path / "report-success.png",
                        )

                    self.assertIn("电路编号不存在", caught.exception.reason)
                    self.assertTrue(caught.exception.screenshot_path.is_file())
                    self.assertEqual(
                        caught.exception.operation_log[-1].step,
                        "manual_intervention_required",
                    )
                    self.assertEqual(
                        caught.exception.operation_log[-1].label,
                        "电路编号不存在，等待人工处理",
                    )
            finally:
                server.shutdown()
                server_thread.join()

    def test_reports_expired_session_when_direct_page_returns_login_form(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    state_path = temp_path / "auth-state.json"
                    state_path.write_text(
                        json.dumps({"cookies": [], "origins": []}),
                        encoding="utf-8",
                    )
                    excel_path = temp_path / "RT00_26012495.xlsx"
                    excel_path.write_bytes(b"fake-xlsx-content")
                    settings = PortalSessionSettings(**{
                        "_env_file": None,
                        "test_login_url": (
                            f"http://127.0.0.1:{server.server_port}/portal/#/pLogin"
                        ),
                        "test_mobile_login_url": (
                            f"http://127.0.0.1:{server.server_port}/portal/#/login"
                        ),
                        "test_session_check_url": (
                            f"http://127.0.0.1:{server.server_port}/portal/#/"
                        ),
                        "headless": True,
                        "test_state_path": state_path,
                        "artifact_dir": temp_path,
                        "username_selector": "#username",
                        "mobile_phone_selector": "#mobile",
                        "timeout_ms": 5_000,
                    })

                    with self.assertRaises(PortalSessionError) as caught:
                        PortalCutoverReportRpa(settings).upload_customer_excel(
                            excel_path,
                            environment=PortalEnvironment.TEST,
                            screenshot_path=temp_path / "should-not-exist.png",
                        )

                    self.assertEqual(caught.exception.code, "RPA_SESSION_REQUIRED")
            finally:
                server.shutdown()
                server_thread.join()


if __name__ == "__main__":
    unittest.main()
