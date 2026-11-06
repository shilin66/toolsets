"""The illustrated user guide is readable on the workbench's origin."""
from pathlib import Path
import re
import struct
import unittest

from playwright.sync_api import expect

from tests.ui import test_multiuser_ui as fixture
import api_server


class UserManualApiTest(unittest.TestCase):
    def test_manual_renders_markdown_without_requiring_login(self):
        response = api_server.app.test_client().get('/manual')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/html')
        html = response.get_data(as_text=True)
        self.assertIn('NOC 工作台用户操作手册', html)
        self.assertIn('<table>', html)
        self.assertIn('aria-label="手册目录"', html)
        self.assertNotIn('<div id="app">', html)

    def test_screenshots_match_the_document_and_downloads_are_absent(self):
        client = api_server.app.test_client()
        source = (api_server.MANUAL_DIR / 'README.md').read_text(encoding='utf-8')
        pictures = re.findall(r'!\[[^\]]*\]\((images/[^)]+)\)', source)
        self.assertGreaterEqual(len(pictures), 20)
        html = client.get('/manual').get_data(as_text=True)
        for path in pictures:
            self.assertIn('src="/manual/' + path + '"', html)
            with client.get('/manual/' + path) as image:
                self.assertEqual(image.status_code, 200)
                self.assertEqual(image.mimetype, 'image/png')
                self.assertEqual(struct.unpack('>II', image.data[16:24]), (2560, 1440), path)
        self.assertNotIn(' download', html)
        self.assertEqual(client.get('/manual.zip').status_code, 404)
        self.assertEqual(client.get('/manual.md').status_code, 404)
        self.assertEqual(client.get('/manual/images/../../api_server.py').status_code, 404)


class UserManualUiTest(unittest.TestCase):
    setUp = fixture.MultiuserUiTest.setUp
    close_server = fixture.MultiuserUiTest.close_server
    page = fixture.MultiuserUiTest.page
    login_user = fixture.MultiuserUiTest.login_user

    def test_footer_opens_readable_manual_in_new_tab_for_both_roles(self):
        output = Path('.qa/manual')
        output.mkdir(parents=True, exist_ok=True)
        for width, admin in ((1280, True), (1440, False), (2560, False)):
            with self.subTest(width=width, admin=admin):
                page = self.page(width)
                if width == 2560:
                    page.set_viewport_size({'width': 2560, 'height': 1440})
                if admin:
                    page.get_by_role('button', name='管理员登录', exact=True).click()
                    page.get_by_role('textbox', name='API Key').fill('test-key')
                    page.get_by_role('button', name='登录', exact=True).click()
                else:
                    self.login_user(page, 'alice', 'a-secure-password')
                link = page.get_by_role('link', name='用户手册（新标签页打开）', exact=True)
                expect(link).to_be_visible()
                expect(link).to_have_attribute('rel', 'noopener noreferrer')
                box = link.bounding_box()
                self.assertLess(box['x'], 88)
                self.assertGreater(box['y'], 700)
                page.screenshot(path=str(output / f'entry-{width}.png'))
                for collapsed in (False, True):
                    if collapsed:
                        page.get_by_role('button', name='收起菜单', exact=True).click()
                    link.focus()
                    with page.expect_popup() as opened:
                        link.press('Enter')
                    manual = opened.value
                    if width == 2560:
                        manual.set_viewport_size({'width': 2560, 'height': 1440})
                    manual.on('pageerror', lambda error: self.errors.append(str(error)))
                    expect(manual).to_have_url(self.base + '/manual')
                    expect(page).to_have_url(self.base + '/admin/cutover-tasks')
                    expect(manual.get_by_role('heading', level=1)).to_have_text('NOC 工作台用户操作手册')
                    manual.wait_for_function("[...document.querySelectorAll('.manual-content img')].every(img => img.complete && img.naturalWidth === 2560 && img.naturalHeight === 1440)")
                    self.assertFalse(manual.evaluate('Boolean(window.opener)'))
                    self.assertLessEqual(manual.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
                    anchors = manual.locator('.manual-toc a, .manual-chapters a')
                    self.assertGreater(anchors.count(), 8)
                    for anchor in anchors.all():
                        target = anchor.get_attribute('href')[1:]
                        self.assertEqual(manual.locator('[id="' + target + '"]').count(), 1)
                    if not collapsed:
                        manual.screenshot(path=str(output / f'manual-{width}.png'))
                        chapters = manual.get_by_role('navigation', name='手册目录', exact=True)
                        sections = manual.get_by_role('navigation', name='本章导航', exact=True)
                        supplier = chapters.get_by_role('link', name='7. 维护供应商规则与配置草稿', exact=True)
                        supplier.click()
                        expect(supplier).to_have_attribute('aria-current', 'location')
                        prompt = sections.get_by_role('link', name='7.13 高级配置：补充说明、测试附件和提示词预览', exact=True)
                        prompt.click()
                        expect(prompt).to_have_attribute('aria-current', 'location')
                        manual.screenshot(path=str(output / f'illustrated-{width}.png'))
                        picture = manual.locator('.manual-image-link').filter(has=manual.locator('img[src="/manual/images/supplier-prompt.png"]'))
                        tabs_before = len(manual.context.pages)
                        url_before = manual.url
                        picture.click()
                        preview = manual.get_by_role('dialog', name='图片预览', exact=True)
                        expect(preview).to_be_visible()
                        preview_image = preview.locator('img')
                        expect(preview_image).to_have_attribute('src', self.base + '/manual/images/supplier-prompt.png')
                        self.assertEqual(len(manual.context.pages), tabs_before)
                        expect(manual).to_have_url(url_before)
                        scroll_before = manual.evaluate('scrollY')
                        manual.screenshot(path=str(output / f'image-preview-{width}.png'))
                        preview_image.click()
                        expect(preview).to_be_visible()
                        manual.mouse.click(10, 10)
                        expect(preview).to_be_hidden()
                        expect(picture).to_be_focused()
                        self.assertEqual(manual.evaluate('scrollY'), scroll_before)
                        picture.press('Enter')
                        expect(preview).to_be_visible()
                        manual.keyboard.press('Escape')
                        expect(preview).to_be_hidden()
                        picture.press('Enter')
                        preview.get_by_role('button', name='关闭图片预览', exact=True).click()
                        expect(preview).to_be_hidden()
                        chapters.get_by_role('link', name='12. 常见问题', exact=True).click()
                        expect(manual.get_by_role('heading', name='12. 常见问题', exact=True)).to_be_in_viewport()
                        manual.reload()
                        expect(manual.get_by_role('heading', name='12. 常见问题', exact=True)).to_be_in_viewport()
                        expect(chapters.get_by_role('link', name='12. 常见问题', exact=True)).to_have_attribute('aria-current', 'location')
                        search = manual.get_by_role('searchbox', name='搜索手册')
                        manual.keyboard.press('Control+k')
                        expect(search).to_be_focused()
                        search.fill('顶层其他信息')
                        results = manual.locator('#manual-search-results')
                        expect(results.get_by_role('link')).to_have_count(1)
                        search.press('ArrowDown')
                        results.get_by_role('link').press('Enter')
                        expect(manual.get_by_role('heading', name='7.12 高级配置：顶层其他信息', exact=True)).to_be_in_viewport()
                        expect(results).to_be_hidden()
                        expect(supplier).to_have_attribute('aria-current', 'location')
                        manual.go_back()
                        expect(manual.get_by_role('heading', name='12. 常见问题', exact=True)).to_be_in_viewport()
                        search.fill('前导零')
                        expect(results.get_by_role('link').first).to_be_visible()
                        search.fill('不存在的手册词条xyz')
                        expect(results).to_contain_text('没有找到相关内容')
                        search.press('Escape')
                        expect(results).to_be_hidden()
                        expect(search).to_have_value('')
                        expect(manual.get_by_role('link', name='下载 Markdown')).to_have_count(0)
                    manual.close()
                page.context.close()
        self.assertEqual(self.errors, [])
