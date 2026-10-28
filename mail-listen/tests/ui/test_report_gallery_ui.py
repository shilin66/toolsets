"""Report thumbnails fit desktop layouts and open complete, navigable screenshots."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw
from playwright.sync_api import expect

from tests.ui import test_cutover_add_defaults_ui as defaults


class ReportGalleryUiTest(unittest.TestCase):
    setUp = defaults.CutoverAddDefaultsUiTest.setUp
    open_task = defaults.CutoverAddDefaultsUiTest.open_task
    assert_clean = defaults.CutoverAddDefaultsUiTest.assert_clean

    def prepare_report(self, status='success'):
        self.open_task(backbone=True)
        root = Path(self.api.tmpdir.name) / 'report-images'
        root.mkdir()
        for name, size in (('wide.png', (2400, 1400)), ('tall.png', (1200, 3200))):
            image = Image.new('RGB', size, '#f5f7f4')
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, size[0] - 1, size[1] - 1), outline='#3f7b65', width=16)
            draw.rectangle((40, 40, size[0] - 40, 180), fill='#1c2d30')
            draw.text((70, 80), 'TEST REPORT - COMPLETE SCREENSHOT', fill='white', font_size=36)
            for y in range(240, size[1] - 120, 160):
                draw.rectangle((80, y, size[0] - 80, y + 100), fill='white', outline='#ced8d3', width=3)
                draw.text((110, y + 32), f'Form field / step {y // 160}', fill='#263638', font_size=28)
            draw.text((80, size[1] - 80), 'END OF SCREENSHOT', fill='#3f7b65', font_size=28)
            image.save(root / name)
        settings = patch.object(defaults.fixture.api_server, 'PortalSessionSettings', return_value=SimpleNamespace(artifact_dir=root, default_environment='test'))
        settings.start()
        self.addCleanup(settings.stop)
        steps = [{'step': f'step-{i}', 'label': label, 'captured_at': f'2026-10-26T09:00:{i:02d}',
                  'screenshot_filename': 'tall.png' if i % 2 else 'wide.png'}
                 for i, label in enumerate(('打开填报页面', '填写基本信息与割接对象，核对线路及操作时间', '填写人员信息', '核对确认项', '提交前检查', '上报完成'))]
        steps.append({'step': 'no-image', 'label': '仅记录日志的步骤', 'captured_at': '2026-10-26T09:00:07'})
        self.report_id = self.api.db.add_cutover_report(self.task_id, 'backbone', status, {'operation_log': steps})
        self.page.reload()
        expect(self.panel).to_be_visible()
        self.evidence = Path(__file__).resolve().parents[2] / '.qa' / 'report-gallery'
        self.evidence.mkdir(parents=True, exist_ok=True)

    def test_history_thumbnails_fit_and_keyboard_preview_switches_complete_images(self):
        self.prepare_report()
        self.panel.locator('.n-data-table-expand-trigger').click()
        gallery = self.panel.locator('.report-gallery')
        expect(gallery.locator('.report-thumbnail')).to_have_count(6)
        expect(gallery.locator('.report-image-missing')).to_have_text('截图暂不可用')
        self.page.wait_for_function("[...document.querySelectorAll('.report-thumbnail img')].every(img => img.complete && img.naturalWidth > 0)")
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width': width, 'height': 1000})
            for collapsed in (False, True):
                toggle = self.page.get_by_role('button', name='展开菜单' if not collapsed else '收起菜单', exact=True)
                if toggle.count():
                    toggle.click()
                self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
                gallery.scroll_into_view_if_needed()
                metrics = gallery.evaluate('''el => ({overflow:el.scrollWidth - el.clientWidth,
                    cards:[...el.querySelectorAll('.report-operation-card')].map(card => ({
                        width:card.getBoundingClientRect().width, height:card.getBoundingClientRect().height})),
                    images:[...el.querySelectorAll('.report-thumbnail img')].map(img=>({
                        height:img.getBoundingClientRect().height, fit:getComputedStyle(img).objectFit}))})''')
                self.assertLessEqual(metrics['overflow'], 1)
                for card in metrics['cards']:
                    self.assertLess(card['width'], 360)
                    self.assertLess(card['height'], 280)
                for image in metrics['images']:
                    self.assertLessEqual(image['height'], 160)
                    self.assertEqual(image['fit'], 'contain')
                self.page.screenshot(path=str(self.evidence / f'history-{width}-{collapsed}.png'))
        first = gallery.locator('.report-thumbnail').first
        first.focus()
        first.press('Enter')
        preview = self.page.locator('img.n-image-preview')
        expect(preview).to_be_visible()
        self.assertEqual(preview.evaluate('img => img.naturalWidth'), 2400)
        self.page.keyboard.press('ArrowRight')
        self.page.wait_for_function("document.querySelector('img.n-image-preview')?.naturalHeight === 3200")
        self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
        self.page.screenshot(path=str(self.evidence / 'full-size-preview.png'))
        self.page.keyboard.press('Escape')
        expect(preview).not_to_be_visible()
        expect(first).to_be_focused()
        self.assert_clean()

    def test_progress_drawer_uses_compact_gallery_and_missing_state(self):
        self.prepare_report(status='running')
        drawer = self.page.locator('.report-progress-drawer')
        expect(drawer).to_be_visible()
        expect(drawer.locator('.report-thumbnail')).to_have_count(6)
        expect(drawer.locator('.report-image-missing')).to_have_text('截图暂不可用')
        self.assertLessEqual(drawer.evaluate('el => el.scrollWidth - el.clientWidth'), 1)
        self.page.screenshot(path=str(self.evidence / 'progress-drawer.png'))
        self.assert_clean()

    def test_loading_images_are_released_when_leaving_detail(self):
        self.page.add_init_script('''(() => {
            const create = URL.createObjectURL.bind(URL), revoke = URL.revokeObjectURL.bind(URL);
            window.reportUrls = {created: [], active: new Set()};
            URL.createObjectURL = blob => { const url = create(blob); reportUrls.created.push(url); reportUrls.active.add(url); return url; };
            URL.revokeObjectURL = url => { reportUrls.active.delete(url); revoke(url); };
        })();''')
        held = []
        self.page.route('**/api/rpa/report-artifacts/**', lambda route: held.append(route))
        self.prepare_report()
        self.panel.locator('.n-data-table-expand-trigger').click()
        gallery = self.panel.locator('.report-gallery')
        expect(gallery.get_by_text('正在加载操作截图', exact=True)).to_have_count(6)
        self.page.locator('.side-menu').get_by_text('系统配置', exact=True).click()
        expect(self.panel).to_have_count(0)
        self.assertEqual(len(held), 6)
        for route in held:
            route.continue_()
        self.page.wait_for_function('reportUrls.created.length === 6 && reportUrls.active.size === 0')
        self.assert_clean()
