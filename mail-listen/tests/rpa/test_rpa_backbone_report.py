import importlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic


cutover_report_module = importlib.import_module("rpa.cutover_report")
session_config_module = importlib.import_module("rpa.session_config")
session_models_module = importlib.import_module("rpa.session_models")

PortalCutoverReportRpa = cutover_report_module.PortalCutoverReportRpa
build_backbone_report_url = cutover_report_module.build_backbone_report_url
CutoverReportManualInterventionError = (
    cutover_report_module.CutoverReportManualInterventionError
)
PortalSessionSettings = session_config_module.PortalSessionSettings
PortalEnvironment = session_models_module.PortalEnvironment


BACKBONE_PAGE = """<!doctype html>
<html lang="zh-CN">
<style>
  .el-checkbox__input { display: inline-block; width: 16px; height: 16px; }
  .el-checkbox__inner { display: block; width: 14px; height: 14px; border: 1px solid blue; }
  .el-checkbox__original { position: absolute; opacity: 0; pointer-events: none; }
  .el-radio__input { display: inline-block; width: 16px; height: 16px; }
  .el-radio__inner { display: block; width: 14px; height: 14px; border: 1px solid blue; }
  .el-radio__original { position: absolute; opacity: 0; pointer-events: none; }
</style>
<body>
  <h1>传输一干</h1>
  <section id="backbone-form">
    <div class="el-form-item"><label class="el-form-item__label">标题：</label><input id="title"></div>
    <div class="el-form-item"><label class="el-form-item__label">割接分类：</label>
      <select id="category"><option></option><option>线路割接</option></select>
    </div>
    <div class="el-row">
      <div class="el-col el-col-6">
        <div class="el-form-item" id="interrupt-item"><label class="el-form-item__label">中断类型：</label>
          <label class="el-radio"><input type="radio" name="interrupt" value="不中断">不中断</label>
          <label class="el-radio"><input type="radio" name="interrupt" value="瞬断">瞬断</label>
          <label class="el-radio"><input type="radio" name="interrupt" value="中断">中断</label>
        </div>
      </div>
      <div class="el-col el-col-2" id="duration-control" hidden>
        <div class="el-input"><input id="duration" maxlength="10" class="el-input__inner"></div>
        <span>分钟</span>
      </div>
    </div>
    <div class="el-form-item" id="reason-item" hidden><label class="el-form-item__label">中断原因：</label><input id="interrupt-reason"></div>
    <div class="el-form-item"><label class="el-form-item__label">是否涉及集团维护设备或业务影响超出本省范围：</label>
      <label class="el-radio"><input type="radio" name="cross-province" value="是">是</label>
      <label class="el-radio"><input type="radio" name="cross-province" value="否">否</label>
    </div>
    <div class="el-form-item"><label class="el-form-item__label">系统名称：</label>
      <textarea id="systems" readonly></textarea>
    </div>
    <div class="el-form-item"><label class="el-form-item__label">割接开始(北京时间)：</label>
      <div class="el-date-editor"><input id="cutover-start" placeholder="选择开始时间"></div>
    </div>
    <div class="el-form-item"><label class="el-form-item__label">割接结束(北京时间)：</label>
      <div class="el-date-editor"><input id="cutover-end" placeholder="选择结束时间"></div>
    </div>
    <div class="el-form-item"><label class="el-form-item__label">现场指挥人姓名：</label><input data-personnel="现场指挥人员名称"></div>
    <div class="el-form-item"><label class="el-form-item__label">现场指挥人手机：</label><input data-personnel="现场指挥人电话"></div>
    <div class="el-form-item"><label class="el-form-item__label">现场指挥人单位：</label><input data-personnel="现场指挥人单位" data-personnel-unit readonly></div>
    <div class="el-form-item"><label class="el-form-item__label">支撑人员姓名：</label><input data-personnel="支撑人员"></div>
    <div class="el-form-item"><label class="el-form-item__label">支撑人员手机：</label><input data-personnel="支撑人电话"></div>
    <div class="el-form-item"><label class="el-form-item__label">支撑人员单位：</label><input data-personnel="支撑人单位" data-personnel-unit readonly></div>
    <div class="el-form-item"><label class="el-form-item__label">省公司审核人姓名：</label><input data-personnel="省公司审核人姓名"></div>
    <div class="el-form-item"><label class="el-form-item__label">省公司审核人手机：</label><input data-personnel="省公司审核人电话"></div>
    <div class="el-form-item"><label class="el-form-item__label">省公司审核人单位：</label><input data-personnel="省公司审核人单位" data-personnel-unit readonly></div>
    <div class="el-form-item"><label class="el-form-item__label">业务测试人姓名：</label><input data-personnel="业务测试人员"></div>
    <div class="el-form-item"><label class="el-form-item__label">业务测试人手机：</label><input data-personnel="业务测试人员电话"></div>
    <div class="el-form-item"><label class="el-form-item__label">业务测试人员单位：</label><input data-personnel="业务测试人单位" data-personnel-unit readonly></div>
    <div class="el-form-item"><label class="el-form-item__label">操作审核人姓名：</label><input data-personnel="操作审核人姓名"></div>
    <div class="el-form-item"><label class="el-form-item__label">操作审核人手机：</label><input data-personnel="操作审核人电话"></div>
    <div class="el-form-item"><label class="el-form-item__label">操作审核人单位：</label><input data-personnel="操作审核人单位" data-personnel-unit readonly></div>
    <div class="el-form-item"><label class="el-form-item__label">业务复核人姓名：</label><input data-personnel="业务复核人姓名"></div>
    <div class="el-form-item"><label class="el-form-item__label">业务复核人手机：</label><input data-personnel="业务复核人电话"></div>
    <div class="el-form-item"><label class="el-form-item__label">业务复核人单位：</label><input data-personnel="业务复核人单位" data-personnel-unit readonly></div>
    <div id="personnel-unit-options" hidden>
      <div class="el-select-dropdown__item">国际公司</div>
    </div>
    <div class="el-form-item"><label class="el-form-item__label">风险操作影响范围：</label><textarea id="risk"></textarea></div>
    <div class="el-form-item"><label class="el-form-item__label">是否为境外运营商割接或联通割接(跳过变更操作方案校验)：</label>
      <label class="el-radio"><span class="el-radio__input"><span class="el-radio__inner"></span><input class="el-radio__original" type="radio" tabindex="-1" aria-hidden="true" name="overseas-cutover" value="1"></span><span class="el-radio__label">是</span></label>
      <label class="el-radio"><span class="el-radio__input"><span class="el-radio__inner"></span><input class="el-radio__original" type="radio" tabindex="-1" aria-hidden="true" name="overseas-cutover" value="0"></span><span class="el-radio__label">否</span></label>
    </div>
    <label class="el-checkbox">
      <span class="el-checkbox__input"><span class="el-checkbox__inner"></span><input id="confirmed" class="el-checkbox__original" type="checkbox"></span>
      <span class="el-checkbox__label">该割接已按照集团相关文件要求经过省公司领导审批。</span>
    </label>
    <div class="el-form-item"><label class="el-form-item__label">割接方案附件：</label><input id="attachment" type="file" multiple></div>
    <button id="submit" type="button">提交</button>
  </section>
  <section class="el-dialog" role="dialog" id="system-dialog" hidden>
    <h2>选择系统名称</h2>
    <input id="system-search" placeholder="请输入电路名">
    <button id="system-query" type="button">查询</button>
    <table><tbody id="system-results"></tbody></table>
    <button id="system-confirm" type="button">确定</button>
  </section>
  <section class="el-dialog" role="dialog" id="unknown-dialog" hidden>
    <p>需要人工确认未知参数</p><button>确定</button>
  </section>
  <section id="success" hidden>提交成功，任务号：QT2026GJJJ009999</section>
  <script>
    const systemCatalog = ["系统甲", "系统乙"];
    const systemDialog = document.querySelector("#system-dialog");
    const renderSystems = () => {
      const query = document.querySelector("#system-search").value.trim();
      const matches = systemCatalog.filter((name) => !query || name === query);
      document.querySelector("#system-results").innerHTML = matches.map((name) =>
        `<tr><td><label><input type="checkbox" value="${name}">${name}</label></td></tr>`
      ).join("");
    };
    document.querySelector("#systems").addEventListener("click", () => {
      document.querySelector("#system-search").value = "";
      renderSystems();
      systemDialog.hidden = false;
    });
    document.querySelector("#system-query").addEventListener("click", renderSystems);
    document.querySelector("#system-confirm").addEventListener("click", () => {
      const selected = Array.from(
        document.querySelectorAll('#system-results input[type="checkbox"]:checked')
      ).map((input) => input.value);
      document.querySelector("#systems").value = selected.join(",");
      systemDialog.hidden = true;
    });
    document.querySelectorAll('input[name="interrupt"]').forEach((input) => {
      input.addEventListener("change", () => {
        document.querySelector("#reason-item").hidden = input.value !== "中断";
        document.querySelector("#duration-control").hidden = input.value !== "中断";
      });
    });
    let activePersonnelUnit = null;
    let personnelUnitOpenedAt = 0;
    const personnelUnitOptions = document.querySelector("#personnel-unit-options");
    document.querySelectorAll("input[data-personnel-unit]").forEach((input) => {
      input.addEventListener("click", () => {
        activePersonnelUnit = input;
        personnelUnitOpenedAt = performance.now();
        personnelUnitOptions.hidden = false;
      });
    });
    personnelUnitOptions.querySelector(".el-select-dropdown__item").addEventListener("click", (event) => {
      if (event.isTrusted && performance.now() - personnelUnitOpenedAt < 80) return;
      activePersonnelUnit.value = event.target.textContent;
      activePersonnelUnit.dispatchEvent(new Event("input", { bubbles: true }));
      activePersonnelUnit.dispatchEvent(new Event("change", { bubbles: true }));
      personnelUnitOptions.hidden = true;
    });
    ["cutover-start", "cutover-end"].forEach((id) => {
      const input = document.querySelector(`#${id}`);
      input.parentElement.__vue__ = {
        $vnode: { data: { model: { callback: (value) => {
          if (!/^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$/.test(value)) return;
          input.dataset.modelValue = value;
          input.dataset.committed = value.slice(0, 16);
          input.value = value.slice(0, 16);
        } } } },
        userInput: null,
        pickerVisible: false,
      };
      input.addEventListener("blur", () => {
        if (input.dataset.committed !== input.value) input.value = "";
      });
    });
    const confirmationWrapper = document.querySelector("#confirmed").closest(".el-checkbox__input");
    confirmationWrapper.addEventListener("click", (event) => {
      if (event.target === document.querySelector("#confirmed")) return;
      event.preventDefault();
      document.querySelector("#confirmed").checked = true;
    });
    document.querySelector("#confirmed").addEventListener("click", (event) => {
      event.preventDefault();
    });
    document.querySelectorAll('input[name="overseas-cutover"]').forEach((input) => {
      input.addEventListener("click", (event) => event.preventDefault());
      input.closest("label.el-radio").addEventListener("click", (event) => {
        if (event.target === input) return;
        event.preventDefault();
        document.querySelectorAll('input[name="overseas-cutover"]').forEach(
          (candidate) => { candidate.checked = candidate === input; }
        );
      });
    });
    document.querySelector("#submit").addEventListener("click", () => {
      if (document.cookie.includes("backbone_unknown=1")) {
        document.querySelector("#unknown-dialog").hidden = false;
        return;
      }
      if (document.cookie.includes("backbone_personnel_only=1")) {
        const expected = {
          "现场指挥人员名称": "RT",
          "现场指挥人电话": "NA",
          "现场指挥人单位": "国际公司",
          "支撑人员": "NOC",
          "支撑人电话": "+85231000000",
          "支撑人单位": "国际公司",
          "省公司审核人姓名": "Andrew",
          "省公司审核人电话": "+85291089855",
          "省公司审核人单位": "国际公司",
          "业务测试人员": "NOC",
          "业务测试人员电话": "+85231000000",
          "业务测试人单位": "国际公司",
          "操作审核人姓名": "RT NOC",
          "操作审核人电话": "+85231000000",
          "操作审核人单位": "国际公司",
          "业务复核人姓名": "NOC",
          "业务复核人电话": "+85231000000",
          "业务复核人单位": "国际公司"
        };
        const valid = Array.from(document.querySelectorAll("[data-personnel]")).every(
          (input) => input.value === expected[input.dataset.personnel]
        );
        if (valid) document.querySelector("#success").hidden = false;
        return;
      }
      const valid = document.querySelector("#title").value === "骨干割接测试"
        && document.querySelector("#category").value === "线路割接"
        && document.querySelector('input[name="interrupt"]:checked').value === "中断"
        && document.querySelector("#interrupt-reason").value === "Location: Romania Reason: measurement"
        && document.querySelector("#duration").value === "40"
        && document.querySelector('input[name="cross-province"]:checked').value === "是"
        && document.querySelector("#systems").value === "系统甲,系统乙"
        && document.querySelector("#cutover-start").value === "2026-11-11 05:00"
        && document.querySelector("#cutover-end").value === "2026-12-10 12:00"
        && document.querySelector("#risk").value === "割接影响传输通道及其承载的客户电路，IP中继等"
        && document.querySelector('input[name="overseas-cutover"]:checked').value === (
          document.cookie.includes("backbone_overseas_yes=1") ? "1" : "0"
        )
        && document.querySelector("#confirmed").checked
        && document.querySelector("#attachment").files[0].name === "方案.pdf";
      if (valid) document.querySelector("#success").hidden = false;
    });
  </script>
</body>
</html>""".encode()


class FakeBackbonePortalHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = BACKBONE_PAGE
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class PortalBackboneReportRpaTest(unittest.TestCase):
    def test_batches_independent_personnel_text_inputs(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakeBackbonePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    state_path = temp_path / "auth-state.json"
                    state_path.write_text(json.dumps({
                        "cookies": [{
                            "name": "backbone_personnel_only",
                            "value": "1",
                            "domain": "127.0.0.1",
                            "path": "/",
                            "expires": -1,
                            "httpOnly": False,
                            "secure": False,
                            "sameSite": "Lax",
                        }],
                        "origins": [],
                    }), encoding="utf-8")
                    settings = PortalSessionSettings(**{
                        "_env_file": None,
                        "test_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/pLogin",
                        "test_mobile_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/login",
                        "test_session_check_url": f"http://127.0.0.1:{server.server_port}/portal/#/",
                        "test_state_path": state_path,
                        "artifact_dir": temp_path,
                        "headless": True,
                        "timeout_ms": 5_000,
                        "report_action_delay_ms": 200,
                    })
                    personnel = {
                        "现场指挥人员名称": "RT",
                        "现场指挥人电话": "NA",
                        "现场指挥人单位": "国际公司",
                        "支撑人员": "NOC",
                        "支撑人电话": "+85231000000",
                        "支撑人单位": "国际公司",
                        "省公司审核人姓名": "Andrew",
                        "省公司审核人电话": "+85291089855",
                        "省公司审核人单位": "国际公司",
                        "业务测试人员": "NOC",
                        "业务测试人员电话": "+85231000000",
                        "业务测试人单位": "国际公司",
                        "操作审核人姓名": "RT NOC",
                        "操作审核人电话": "+85231000000",
                        "操作审核人单位": "国际公司",
                        "业务复核人姓名": "NOC",
                        "业务复核人电话": "+85231000000",
                        "业务复核人单位": "国际公司",
                    }

                    started_at = monotonic()
                    result = PortalCutoverReportRpa(settings).fill_backbone_form(
                        {"人员信息": personnel},
                        attachment_paths=(),
                        environment=PortalEnvironment.TEST,
                        screenshot_path=temp_path / "backbone-success.png",
                    )
                    elapsed_seconds = monotonic() - started_at

                    self.assertTrue(result.submitted)
                    self.assertIn(
                        "backbone_people_filled",
                        [step.step for step in result.operation_log],
                    )
                    self.assertLess(elapsed_seconds, 18)
            finally:
                server.shutdown()
                server_thread.join()

    def test_builds_direct_backbone_report_url_with_anti_devtools_flag(self):
        url = build_backbone_report_url(
            "https://ofm.crm.189.cn:23122/portal/#/",
            timestamp_ms=1_788_615_452_370,
        )

        self.assertEqual(
            url,
            "https://ofm.crm.189.cn:23122/portal/"
            "?ignoreDisableDevtool=true#/iframe/"
            "https%3A%2F%2Fofm.crm.189.cn%3A23122%2ForderHandle%2F"
            "index.html%23%2FemOrderCreate%2FeeOrderTransNetworkCreate_iframePath/"
            "%E4%BC%A0%E8%BE%93%E4%B8%80%E5%B9%B2/"
            "?t=1788615452370",
        )

    def test_orders_backbone_sections_like_the_portal(self):
        self.assertEqual(
            tuple(PortalCutoverReportRpa._BACKBONE_SECTION_STEPS),
            (
                "基本信息",
                "割接对象",
                "人员信息",
                "其他",
                "确认项",
                "关联网络资源变更单",
            ),
        )

    def test_orders_backbone_fields_and_skips_portal_linked_fields(self):
        cases = {
            "基本信息": (
                {
                    "中断时间 (分钟)": 40,
                    "中断原因": "Location: Romania Reason: measurement",
                    "变更操作等级": "四级",
                    "中断类型": "中断",
                    "设备名称": "无",
                    "涉及系统（网络）": "涉及系统（网络）",
                    "割接分类": "线路割接",
                    "操作厂家": "无",
                    "标题": "骨干割接测试",
                },
                [
                    "标题",
                    "割接分类",
                    "中断类型",
                    "中断原因",
                    "中断时间 (分钟)",
                ],
            ),
            "人员信息": (
                {
                    "业务复核人单位": "国际公司",
                    "业务复核人电话": "+85231000000",
                    "业务复核人姓名": "NOC",
                    "操作审核人单位": "国际公司",
                    "操作审核人电话": "+85231000000",
                    "操作审核人姓名": "RT NOC",
                    "业务测试人单位": "国际公司",
                    "业务测试人员电话": "+85231000000",
                    "业务测试人员": "NOC",
                    "省公司审核人单位": "国际公司",
                    "省公司审核人电话": "+85291089855",
                    "省公司审核人姓名": "Andrew",
                    "支撑人单位": "国际公司",
                    "现场指挥人电话": "NA",
                    "支撑人员": "NOC",
                    "现场指挥人单位": "国际公司",
                    "支撑人电话": "+85231000000",
                    "现场指挥人员名称": "RT",
                },
                [
                    "现场指挥人员名称",
                    "现场指挥人电话",
                    "现场指挥人单位",
                    "支撑人员",
                    "支撑人电话",
                    "支撑人单位",
                    "省公司审核人姓名",
                    "省公司审核人电话",
                    "省公司审核人单位",
                    "业务测试人员",
                    "业务测试人员电话",
                    "业务测试人单位",
                    "操作审核人姓名",
                    "操作审核人电话",
                    "操作审核人单位",
                    "业务复核人姓名",
                    "业务复核人电话",
                    "业务复核人单位",
                ],
            ),
            "其他": (
                {
                    "影响军队": "否",
                    "是否需要集团网管配置操作": "否",
                    "是否增加、删除或更改光开关(OLP)": "否",
                    "是否影响联通": "否",
                    "是否变更网管中网元管理对象配置": "否",
                    "是否为境外运营商割接或联通割接(跳过变更操作方案校验)": "否",
                },
                [
                    "是否增加、删除或更改光开关(OLP)",
                    "是否变更网管中网元管理对象配置",
                    "是否需要集团网管配置操作",
                    "是否影响联通",
                    "影响军队",
                    "是否为境外运营商割接或联通割接(跳过变更操作方案校验)",
                ],
            ),
        }

        for section, (fields, expected_names) in cases.items():
            with self.subTest(section=section):
                ordered = PortalCutoverReportRpa._ordered_backbone_field_items(
                    section,
                    fields,
                )
                self.assertEqual(
                    [field_name for field_name, _value in ordered],
                    expected_names,
                )

    def test_normalizes_fullwidth_parentheses_in_portal_labels(self):
        self.assertEqual(
            PortalCutoverReportRpa._normalize_label("涉及系统（网络）："),
            PortalCutoverReportRpa._normalize_label("涉及系统(网络):"),
        )

    def test_maps_workbench_field_names_to_live_portal_labels(self):
        expected_live_aliases = {
            "割接开始时间": "割接开始(北京时间)",
            "割接结束时间": "割接结束(北京时间)",
            "现场指挥人员名称": "现场指挥人姓名",
            "现场指挥人电话": "现场指挥人手机",
            "支撑人员": "支撑人员姓名",
            "支撑人电话": "支撑人员手机",
            "支撑人单位": "支撑人员单位",
            "省公司审核人电话": "省公司审核人手机",
            "业务测试人员": "业务测试人姓名",
            "业务测试人员电话": "业务测试人手机",
            "操作审核人电话": "操作审核人手机",
            "业务复核人电话": "业务复核人手机",
        }

        for field_name, live_label in expected_live_aliases.items():
            with self.subTest(field_name=field_name):
                self.assertIn(
                    live_label,
                    PortalCutoverReportRpa._BACKBONE_LABEL_ALIASES.get(
                        field_name,
                        (),
                    ),
                )

    def test_fills_sibling_backbone_duration_without_standalone_label(self):
        self._assert_fills_backbone_form("否")

    def test_report_service_preserves_yes_in_backbone_radio_selection(self):
        self._assert_fills_backbone_form("是")

    def _assert_fills_backbone_form(self, overseas_value):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakeBackbonePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    state_path = temp_path / "auth-state.json"
                    state_path.write_text(
                        json.dumps({"cookies": [{
                            "name": "backbone_overseas_yes",
                            "value": "1" if overseas_value == "是" else "0",
                            "domain": "127.0.0.1",
                            "path": "/",
                            "expires": -1,
                            "httpOnly": False,
                            "secure": False,
                            "sameSite": "Lax",
                        }], "origins": []}),
                        encoding="utf-8",
                    )
                    attachment_path = temp_path / "方案.pdf"
                    attachment_path.write_bytes(b"fake-pdf")
                    settings = PortalSessionSettings(**{
                        "_env_file": None,
                        "test_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/pLogin",
                        "test_mobile_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/login",
                        "test_session_check_url": f"http://127.0.0.1:{server.server_port}/portal/#/",
                        "test_state_path": state_path,
                        "artifact_dir": temp_path,
                        "headless": True,
                        "timeout_ms": 5_000,
                        "report_action_delay_ms": 0,
                    })
                    form_data = {
                        "基本信息": {
                            "标题": "骨干割接测试",
                            "割接分类": "线路割接",
                            "中断类型": "中断",
                            "中断原因": "Location: Romania Reason: measurement",
                            "中断时间 (分钟)": 40,
                            "是否涉及集团维护设备或业务影响超出本省范围": "是",
                            "割接地点": "",
                        },
                        "割接对象": {
                            "系统名称": ["系统甲", "系统乙"],
                            "割接开始时间": "2026-11-11 05:00",
                            "割接结束时间": "2026-12-10 12:00:00",
                        },
                        "其他": {
                            "风险操作影响范围": "割接影响传输通道及其承载的客户电路，IP中继等",
                            "是否为境外运营商割接或联通割接(跳过变更操作方案校验)": overseas_value,
                        },
                        "确认项": {
                            "该割接已按照集团相关文件要求经过省公司领导审批。": "是",
                        },
                    }

                    service = importlib.import_module("cutover_report")
                    forms = service._resolve_backbone_forms({
                        "fill_result": {"backbone_circuits": [form_data]},
                    })
                    result = PortalCutoverReportRpa(settings).fill_backbone_form(
                        forms[0],
                        attachment_paths=(attachment_path,),
                        environment=PortalEnvironment.TEST,
                        screenshot_path=temp_path / "backbone-success.png",
                    )

                    self.assertTrue(result.submitted)
                    self.assertEqual(result.portal_task_number, "QT2026GJJJ009999")
                    self.assertEqual(result.uploaded_filenames, ("方案.pdf",))
                    self.assertTrue(result.success_screenshot_path.is_file())
                    self.assertEqual(
                        [step.step for step in result.operation_log],
                        [
                            "backbone_form_ready",
                            "backbone_basic_info_filled",
                            "backbone_cutover_object_filled",
                            "backbone_other_filled",
                            "backbone_confirmations_checked",
                            "backbone_attachments_uploaded",
                            "backbone_submit_succeeded",
                        ],
                    )
            finally:
                server.shutdown()
                server_thread.join()

    def test_unknown_submit_dialog_requires_manual_intervention_with_screenshot(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakeBackbonePortalHandler) as server:
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.start()
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_path = Path(temp_dir)
                    state_path = temp_path / "auth-state.json"
                    state_path.write_text(json.dumps({
                        "cookies": [{
                            "name": "backbone_unknown",
                            "value": "1",
                            "domain": "127.0.0.1",
                            "path": "/",
                            "expires": -1,
                            "httpOnly": False,
                            "secure": False,
                            "sameSite": "Lax",
                        }],
                        "origins": [],
                    }), encoding="utf-8")
                    settings = PortalSessionSettings(**{
                        "_env_file": None,
                        "test_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/pLogin",
                        "test_mobile_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/login",
                        "test_session_check_url": f"http://127.0.0.1:{server.server_port}/portal/#/",
                        "test_state_path": state_path,
                        "artifact_dir": temp_path,
                        "headless": True,
                        "timeout_ms": 5_000,
                        "report_action_delay_ms": 0,
                    })
                    form_data = {
                        "基本信息": {
                            "标题": "骨干割接测试",
                            "割接分类": "线路割接",
                            "中断类型": "中断",
                            "中断时间 (分钟)": 40,
                            "是否涉及集团维护设备或业务影响超出本省范围": "是",
                        },
                        "割接对象": {"系统名称": ["系统甲", "系统乙"]},
                        "其他": {
                            "风险操作影响范围": "割接影响传输通道及其承载的客户电路，IP中继等",
                        },
                        "确认项": {
                            "该割接已按照集团相关文件要求经过省公司领导审批。": "是",
                        },
                    }

                    with self.assertRaises(
                        CutoverReportManualInterventionError
                    ) as caught:
                        PortalCutoverReportRpa(settings).fill_backbone_form(
                            form_data,
                            attachment_paths=(),
                            environment=PortalEnvironment.TEST,
                            screenshot_path=temp_path / "backbone-success.png",
                        )

                    self.assertTrue(caught.exception.screenshot_path.is_file())
                    self.assertEqual(
                        caught.exception.operation_log[-1].step,
                        "manual_intervention_required",
                    )
            finally:
                server.shutdown()
                server_thread.join()

    def test_missing_backbone_system_name_requires_manual_intervention(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), FakeBackbonePortalHandler) as server:
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
                    settings = PortalSessionSettings(**{
                        "_env_file": None,
                        "test_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/pLogin",
                        "test_mobile_login_url": f"http://127.0.0.1:{server.server_port}/portal/#/login",
                        "test_session_check_url": f"http://127.0.0.1:{server.server_port}/portal/#/",
                        "test_state_path": state_path,
                        "artifact_dir": temp_path,
                        "headless": True,
                        "timeout_ms": 5_000,
                        "report_action_delay_ms": 0,
                    })

                    with self.assertRaises(
                        CutoverReportManualInterventionError
                    ) as caught:
                        PortalCutoverReportRpa(settings).fill_backbone_form(
                            {
                                "基本信息": {
                                    "标题": "骨干割接测试",
                                    "割接分类": "线路割接",
                                },
                                "割接对象": {"系统名称": ["不存在的系统"]},
                            },
                            attachment_paths=(),
                            environment=PortalEnvironment.TEST,
                            screenshot_path=temp_path / "backbone-success.png",
                            submit=False,
                        )

                    self.assertIn("系统名称不存在", str(caught.exception))
                    self.assertTrue(caught.exception.screenshot_path.is_file())
            finally:
                server.shutdown()
                server_thread.join()


if __name__ == "__main__":
    unittest.main()
