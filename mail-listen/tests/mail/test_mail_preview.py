import unittest

from mail_preview import build_mail_preview


class MailPreviewTest(unittest.TestCase):
    def test_keeps_full_table_content_and_presentation(self):
        html = '<style>td { padding: 8px }</style><p>第一行<br>第二行</p>' + '<p>内容</p>' * 200 + '<table border="1"><tr><td rowspan="2">LINE-9021 &amp; A</td></tr></table>'
        preview = build_mail_preview(html)
        self.assertIn('<style>td { padding: 8px }</style>', preview)
        self.assertIn('<p>第一行<br>第二行</p>', preview)
        self.assertIn('<table border="1"><tr><td rowspan="2">LINE-9021 &amp; A</td></tr></table>', preview)
        self.assertEqual(preview.count('<p>内容</p>'), 200)

    def test_removes_active_content_but_keeps_local_images_and_link_text(self):
        html = '''<meta http-equiv="refresh" content="0;url=https://external.invalid">
            <base href="https://external.invalid"><script>alert(1)</script>
            <iframe src="https://external.invalid">hidden</iframe><svg onload="alert(1)"></svg>
            <a href="javascript:alert(1)" onclick="alert(1)">Contact NOC</a>
            <img src="https://external.invalid/tracker"><img src="data:image/png;base64,iVBORw0KGgo=" onerror="alert(1)">'''
        preview = build_mail_preview(html)
        self.assertNotIn('external.invalid', preview)
        self.assertNotIn('alert(1)', preview)
        self.assertNotIn('hidden', preview)
        self.assertIn('<a>Contact NOC</a>', preview)
        self.assertIn('src="data:image/png;base64,iVBORw0KGgo="', preview)
        self.assertIn("default-src 'none'", preview)

    def test_empty_html_uses_plain_text_fallback(self):
        self.assertIsNone(build_mail_preview(None))
        self.assertIsNone(build_mail_preview(''))
