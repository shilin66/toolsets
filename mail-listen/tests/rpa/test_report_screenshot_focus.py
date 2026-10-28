"""Exercise real report screenshots with iframe and nested scroll clipping."""
import html
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from tests.rpa.test_rpa_backbone_report import (
    FakeBackbonePortalHandler, PortalCutoverReportRpa, PortalSessionSettings,
    PortalEnvironment,
)


def portal_page(resource_label, upload_label):
    form = '''<!doctype html><meta charset="utf-8"><style>
      body {margin:0; font:18px sans-serif; overflow:hidden;}
      header, footer {height:55px; background:#eee; position:fixed; left:0; right:0; z-index:3;}
      header {top:0} footer {bottom:0}
      #scroll {position:absolute; top:55px; bottom:55px; overflow:auto; width:100%;}
      .spacer {height:1100px}
      .el-form-item, .file-card {margin:20px; padding:24px; height:220px; box-sizing:border-box;}
      #related {background:#d8eee5} #upload {background:#e6edfa}
      .marker {height:24px; width:24px; margin-top:24px;}
      #related .marker {background:rgb(12,130,90)} #upload .marker {background:rgb(40,80,200)}
      input[type=file] {display:none}
    </style><header>传输一干</header><div id="scroll">
      <section class="spacer">其他信息</section>
      <section id="related" class="el-form-item"><h2>关联网络资源变更</h2>
        <label class="el-form-item__label">RESOURCE_LABEL：</label>
        <label><input type="radio" name="resource" value="是">是</label>
        <label><input type="radio" name="resource" value="否" checked>否</label>
        <div class="marker"></div>
      </section><div class="spacer"></div>
      <section id="upload" class="UPLOAD_CLASS"><h2>割接方案附件</h2>
        <label class="el-form-item__label">UPLOAD_LABEL：</label>
        <input type="file" id="file" multiple><ul id="files"></ul><div class="marker"></div>
      </section><div style="height:450px"></div>
    </div><footer><button onclick="window.submitted=true">提交</button></footer>
    <script>document.querySelector('#file').onchange=event=>{
      document.querySelector('#files').replaceChildren(...Array.from(event.target.files, file=>{
        const item=document.createElement('li'); item.textContent=file.name; return item;
      }));
    };</script>'''.replace('RESOURCE_LABEL', resource_label).replace('UPLOAD_LABEL', upload_label).replace(
        'UPLOAD_CLASS', 'file-card' if upload_label == '上传文件' else 'el-form-item',
    )
    return ('<!doctype html><meta charset="utf-8"><style>body{margin:0;overflow:hidden} '
            'header{height:50px;background:#087afa;color:white} '
            'iframe{border:0;width:100%;height:calc(100vh - 50px)}</style>'
            '<header>综调截图定位测试</header><iframe srcdoc="' + html.escape(form, quote=True) + '"></iframe>').encode()


class ReportScreenshotFocusTest(unittest.TestCase):
    def test_resource_and_hidden_upload_targets_are_visible_in_step_screenshots(self):
        # Cover the portal's alternate resource label and configurable upload fallback.
        for resource_label, upload_label, width in [
            ('是否设计网络资源变更', '割接方案附件', 1920),
            ('是否关联变更操作需求单', '上传文件', 1280),
        ]:
            with self.subTest(resource_label=resource_label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                state = root / 'state.json'
                state.write_text(json.dumps({'cookies':[], 'origins':[]}))
                attachment = root / 'cutover-plan.txt'
                attachment.write_text('Scheduled maintenance plan')
                captured = {}
                original_capture = PortalCutoverReportRpa._capture_screenshot

                def capture(page, path):
                    for step, target in [('backbone_related_change_filled', 'related'),
                                         ('backbone_attachments_uploaded', 'upload')]:
                        if step not in path.name:
                            continue
                        frame = next(frame for frame in page.frames if frame.locator('#'+target).count())
                        item = frame.locator('#'+target)
                        captured[step] = {
                            'box':item.bounding_box(), 'marker':item.locator('.marker').bounding_box(),
                            'checked':frame.locator('input[value="否"]').is_checked(),
                            'text':item.inner_text(), 'path':path,
                            'submitted':frame.evaluate('Boolean(window.submitted)'),
                        }
                    original_capture(page, path)

                with patch.object(FakeBackbonePortalHandler, 'page_body', portal_page(resource_label, upload_label)):
                    server = ThreadingHTTPServer(('127.0.0.1', 0), FakeBackbonePortalHandler)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    thread.start()
                    try:
                        settings = PortalSessionSettings(
                            _env_file=None, test_state_path=state, artifact_dir=root,
                            test_login_url=f'http://127.0.0.1:{server.server_port}/login',
                            test_mobile_login_url=f'http://127.0.0.1:{server.server_port}/mobile-login',
                            test_session_check_url=f'http://127.0.0.1:{server.server_port}/portal/',
                            headless=True, timeout_ms=2000, report_action_delay_ms=0,
                            viewport_width=width, viewport_height=900,
                        )
                        with patch.object(PortalCutoverReportRpa, '_capture_screenshot', staticmethod(capture)):
                            result = PortalCutoverReportRpa(settings).fill_backbone_form(
                                {'关联网络资源变更单':{'是否设计网络资源变更':'否'}},
                                attachment_paths=(attachment,), environment=PortalEnvironment.TEST,
                                screenshot_path=root/'result.png', submit=False,
                            )
                    finally:
                        server.shutdown(); thread.join(timeout=5); server.server_close()
                self.assertFalse(result.submitted)
                self.assertEqual(len(captured), 2)
                for step, color in [('backbone_related_change_filled',(12,130,90)),
                                    ('backbone_attachments_uploaded',(40,80,200))]:
                    evidence = captured[step]
                    box = evidence['box']
                    self.assertGreaterEqual(box['y'], 105, f'{step} is above the iframe viewport')
                    self.assertLessEqual(box['y']+box['height'], 845, f'{step} is clipped by the footer')
                    self.assertTrue(evidence['checked'])
                    self.assertFalse(evidence['submitted'])
                    marker = evidence['marker']
                    with Image.open(evidence['path']) as screenshot:
                        self.assertEqual(screenshot.convert('RGB').getpixel((
                            int(marker['x']+marker['width']/2), int(marker['y']+marker['height']/2))), color)
                    if 'attachments' in step:
                        self.assertIn(attachment.name, evidence['text'])
                    destination = Path('.qa/report-screenshot-focus')
                    destination.mkdir(parents=True, exist_ok=True)
                    (destination/f'{width}-{step}.png').write_bytes(evidence['path'].read_bytes())
