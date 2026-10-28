"""Shared selectors must keep settings styling and desktop keyboard behavior."""
import unittest
from pathlib import Path

from playwright.sync_api import expect
from tests.ui import test_operations_ui as operations


class ControlStyleUiTest(unittest.TestCase):
    setUp = operations.OperationsUiTest.setUp
    stop_server = operations.OperationsUiTest.stop_server
    page = operations.OperationsUiTest.page

    def test_settings_reference_matches_filters_and_open_panels(self):
        page = self.page(admin=True)
        errors = []
        page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)
        page.goto(self.base + '/admin/settings')
        select = page.locator('.settings-field.n-select .n-base-selection')
        date = page.locator('.settings-field.n-date-picker .n-input').first
        expect(select).to_be_visible()
        expect(date).to_be_visible()
        styles = """el => { const s=getComputedStyle(el); return {
            height:el.getBoundingClientRect().height, radius:s.borderRadius,
            font:s.getPropertyValue('--n-font-size'), border:s.getPropertyValue('--n-border'),
            active:s.getPropertyValue('--n-border-focus'), color:s.getPropertyValue('--n-color')
        }; }"""
        select_style = select.evaluate(styles)
        date_style = date.evaluate(styles)
        target = Path('.qa/unified-controls'); target.mkdir(parents=True, exist_ok=True)
        page.goto(self.base + '/admin/operations')
        expect(page.locator('.stats-cards')).to_be_visible()
        expect(page.locator('select, input[type=date]')).to_have_count(0)
        for width in (1280, 1440, 1920):
            page.set_viewport_size({'width': width, 'height': 1000})
            for field in page.locator('.stats-filters .n-base-selection').all():
                self.assertEqual(field.evaluate(styles), select_style)
            for field in page.locator('.stats-filters .n-date-picker .n-input').all():
                self.assertEqual(field.evaluate(styles), date_style)
            self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
            page.get_by_label('统计周期', exact=True).click()
            expect(page.locator('.n-base-select-menu')).to_be_visible()
            page.wait_for_timeout(250)  # Capture after the dropdown entrance transition.
            page.screenshot(path=str(target / f'select-{width}.png'))
            page.keyboard.press('Escape')
            expect(page.locator('.n-base-select-menu')).not_to_be_visible()
            page.locator('.n-date-picker[aria-label="结束日期"] input').click()
            expect(page.locator('.n-date-panel')).to_be_visible()
            page.wait_for_timeout(250)  # Capture after the calendar entrance transition.
            page.screenshot(path=str(target / f'date-{width}.png'))
            page.keyboard.press('Escape')
            expect(page.locator('.n-date-panel')).not_to_be_visible()
        self.assertEqual(self.errors, [])
        self.assertEqual(errors, [])

    def test_date_validation_and_multi_select_keep_scope(self):
        page = self.page(admin=True, width=1280)
        page.get_by_label('统计周期', exact=True).click()
        page.locator('.n-base-select-option').filter(has_text='上周').click()
        start = page.locator('.n-date-picker[aria-label="开始日期"] input')
        end = page.locator('.n-date-picker[aria-label="结束日期"] input')
        self.assertLess(start.input_value(), end.input_value())
        requests = []
        page.on('request', lambda request: requests.append(request.url) if '/api/operations/summary?' in request.url else None)
        start.fill(''); start.press('Tab')
        page.get_by_role('button', name='查询统计').click()
        expect(page.get_by_role('alert')).to_contain_text('请选择完整的日期范围')
        self.assertEqual(requests, [])
        start.fill('2026-10-26'); start.press('Tab')
        end.fill('2026-11-01'); end.press('Tab')
        box = page.get_by_label('监听邮箱', exact=True)
        box.click()
        page.get_by_role('button', name='清空', exact=True).click()
        page.keyboard.press('Escape')
        page.get_by_role('button', name='查询统计').click()
        expect(page.locator('.stats-card').filter(has_text='接收邮件').locator('strong')).to_have_text('0')
        self.assertIn('mailboxes=', requests[-1])
        box.click()
        # A searchable multiple selector must still allow restoring the historical scope.
        page.get_by_role('button', name='全选', exact=True).click()
        page.keyboard.press('Escape')
        page.get_by_role('button', name='查询统计').click()
        expect(page.locator('.stats-context')).to_contain_text('全部邮箱（含历史）')
        self.assertNotIn('mailboxes=', requests[-1])
        self.assertEqual(self.errors, [])
