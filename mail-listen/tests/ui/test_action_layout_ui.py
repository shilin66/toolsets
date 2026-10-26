"""Shared icon actions, spacing and desktop list geometry using isolated data."""
import unittest
import re
from pathlib import Path
from playwright.sync_api import expect
from tests.ui import test_naive_migration_ui as migration


class ActionLayoutUiTest(unittest.TestCase):
    setUp = migration.NaiveMigrationUiTest.setUp
    assert_clean = migration.NaiveMigrationUiTest.assert_clean

    def test_sidebar_icons_remain_legible_when_collapsed(self):
        evidence = Path(__file__).resolve().parents[2] / '.qa' / 'sidebar-contrast'
        evidence.mkdir(parents=True, exist_ok=True)
        icons = self.page.locator('.side-menu .n-menu-item-content__icon svg')
        contrast = '''els => {
            const luminance = color => {
                const rgb = color.match(/[\\d.]+/g).slice(0, 3).map(Number).map(v => {
                    v /= 255;
                    return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
                });
                return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
            };
            const bg = luminance(getComputedStyle(document.querySelector('.sidebar')).backgroundColor);
            return els.map(el => {
                const fg = luminance(getComputedStyle(el).color);
                return (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05);
            });
        }'''
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width': width, 'height': 1000})
            for collapsed in (True, False):
                self.page.get_by_role('button', name='收起菜单' if collapsed else '展开菜单', exact=True).click()
                self.page.mouse.move(500, 20)
                self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
                expect(icons).to_have_count(6)
                for ratio in icons.evaluate_all(contrast):
                    self.assertGreaterEqual(ratio, 3, (width, collapsed, ratio))
                icons.nth(1).hover()
                self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
                for ratio in icons.evaluate_all(contrast):
                    self.assertGreaterEqual(ratio, 3, (width, collapsed, 'hover', ratio))
                self.page.mouse.move(500, 20)
                self.page.screenshot(path=str(evidence / f'{width}-{"collapsed" if collapsed else "expanded"}.png'))
        self.assert_clean()

    def test_task_summary_loads_after_navigation_and_sign_in(self):
        expect(self.page.locator('.operations-summary')).to_have_count(0)
        self.page.locator('.side-menu').get_by_text('割接任务', exact=True).click()
        value = self.page.locator('.operations-metric strong').first
        expect(value).to_have_text('0')
        self.page.get_by_role('button', name='退出登录', exact=True).click()
        self.page.get_by_role('textbox', name='API Key').fill('test-key')
        self.page.get_by_role('button', name='登录', exact=True).click()
        expect(value).to_have_text('0')
        with self.page.expect_response(lambda response: '/api/dashboard/summary' in response.url):
            self.page.get_by_role('button', name='刷新运营摘要', exact=True).click()
        expect(value).to_have_text('0')
        self.page.locator('.side-menu').get_by_text('线路管理', exact=True).click()
        expect(self.page.locator('.operations-summary')).to_have_count(0)
        self.assert_clean()

    def test_page_actions_follow_navigation_and_keep_their_handlers(self):
        actions = self.page.get_by_role('button', name=re.compile(r'^(新增供应商|新增线路|新增邮箱|导入|导出)$'))
        expect(self.page.locator('.card-header').get_by_role('button', name='新增供应商', exact=True)).to_be_visible()
        self.page.get_by_role('button', name='新增供应商', exact=True).click()
        expect(self.page.locator('.supplier-form')).to_be_visible()
        expect(actions).to_have_count(0)

        self.page.locator('.topbar-breadcrumb').get_by_role('button', name='供应商配置', exact=True).click()
        expect(actions).to_have_count(1)
        self.page.get_by_role('tab', name='配置草稿', exact=True).click()
        expect(actions).to_have_count(0)
        self.page.get_by_role('tab', name='正式配置', exact=True).click()
        expect(self.page.get_by_role('button', name='新增供应商', exact=True)).to_be_visible()

        for menu, label, title, count in (
            ('线路管理', '新增线路', '新增线路', 3),
            ('邮箱配置', '新增邮箱', '新增邮箱', 1),
        ):
            self.page.locator('.side-menu').get_by_text(menu, exact=True).click()
            expect(actions).to_have_count(count)
            self.page.locator('.list-heading, .mail-accounts-panel > .block-head').get_by_role('button', name=label, exact=True).click()
            dialog = self.page.get_by_role('dialog', name=title, exact=True)
            expect(dialog).to_be_visible()
            dialog.get_by_role('button', name='取消', exact=True).click()
            expect(dialog).not_to_be_visible()
        self.page.locator('.side-menu').get_by_text('割接任务', exact=True).click()
        expect(actions).to_have_count(0)
        self.page.locator('.side-menu').get_by_text('供应商配置', exact=True).click()
        expect(self.page.get_by_role('button', name='新增供应商', exact=True)).to_be_visible()
        self.page.get_by_role('button', name='退出登录', exact=True).click()
        expect(self.page.locator('.login-screen')).to_be_visible()
        self.assert_clean()

    def test_list_actions_spacing_tooltips_and_dialog_footer(self):
        result = self.api.client.post('/api/system/mail-accounts', headers=self.api.headers, json={
            'name': 'NOC test mailbox', 'email_address': 'noc@example.com',
            'email_password': 'test-only', 'imap_server': 'imap.example.com',
            'imap_port': 993, 'imap_use_ssl': True, 'enabled': False,
        })
        self.assertEqual(result.status_code, 201)
        evidence = Path(__file__).resolve().parents[2] / '.qa' / 'ui-polish'
        evidence.mkdir(parents=True, exist_ok=True)
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width': width, 'height': 1000})
            for route in ('suppliers', 'cutover-tasks', 'circuits', 'mail-accounts'):
                with self.subTest(width=width, route=route):
                    self.page.goto(self.base + '/admin/' + route)
                    table = self.page.locator('.noc-data-table').first
                    expect(table.locator('.n-data-table-tbody .noc-action').first).to_be_visible()
                    actions = table.locator('.noc-action')
                    metrics = actions.evaluate_all('''els => els.map(el => ({
                        label: el.getAttribute('aria-label'), text: el.textContent.trim(),
                        width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height,
                        icons: el.querySelectorAll('svg').length
                    }))''')
                    for metric in metrics:
                        self.assertTrue(metric['label'])
                        self.assertEqual(metric['text'], '')
                        self.assertEqual(metric['icons'], 1)
                        self.assertEqual(metric['width'], 32)
                        self.assertEqual(metric['height'], 32)
                    for selector, side in (('.n-data-table-th:first-child', 'paddingLeft'),
                                           ('.n-data-table-td:first-child', 'paddingLeft'),
                                           ('.n-data-table-th:last-child', 'paddingRight'),
                                           ('.n-data-table-td:last-child', 'paddingRight')):
                        padding = table.locator(selector).first.evaluate('(el, side) => parseFloat(getComputedStyle(el)[side])', side)
                        self.assertGreaterEqual(padding, 20)
                    groups = table.locator('.row-actions, .cutover-row-actions')
                    for group in groups.all():
                        positions = group.locator('button').evaluate_all('els => els.map(el => el.getBoundingClientRect().toJSON())')
                        for left, right in zip(positions, positions[1:]):
                            self.assertGreaterEqual(right['left'] - left['right'], 7.9)
                    self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                    if route == 'mail-accounts':
                        scroll = table.locator('.n-data-table-base-table-body .n-scrollbar-container')
                        self.assertTrue(scroll.evaluate('el => el.scrollWidth <= el.clientWidth + 1'))
                        switch = table.get_by_role('switch').first.bounding_box()
                        action_group = table.locator('.row-actions').first.bounding_box()
                        self.assertLessEqual(switch['x'] + switch['width'], action_group['x'])
                    self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
                    self.page.screenshot(path=str(evidence / f'{route}-{width}.png'))
                    self.assert_clean()
        self.page.set_viewport_size({'width': 1280, 'height': 800})
        self.page.goto(self.base + '/admin/circuits')
        edit = self.page.get_by_role('button', name='编辑', exact=True)
        edit.focus()
        expect(self.page.get_by_role('tooltip')).to_contain_text('编辑')
        edit.press('Escape')
        expect(self.page.get_by_role('tooltip')).not_to_be_visible()
        edit.press('Enter')
        dialog = self.page.get_by_role('dialog', name='编辑线路', exact=True)
        expect(dialog).to_be_visible()
        self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
        expect(self.page.get_by_role('tooltip')).not_to_be_visible()
        footer = dialog.locator('.dialog-actions')
        rect = footer.bounding_box()
        self.assertLessEqual(rect['y'] + rect['height'], 800)
        self.assertGreaterEqual(rect['y'], 0)
        buttons = footer.locator('button').evaluate_all('els => els.map(el => el.getBoundingClientRect().toJSON())')
        self.assertGreaterEqual(buttons[1]['left'] - buttons[0]['right'], 7.9)
        suggestions = self.page.locator('.n-auto-complete-menu:visible')
        expect(suggestions).to_have_count(0)
        self.page.screenshot(path=str(evidence / 'circuit-edit-dialog.png'))
        supplier = dialog.locator('.n-auto-complete input').first
        supplier.press('ArrowDown')
        expect(suggestions).to_be_visible()
        self.assertGreaterEqual(suggestions.bounding_box()['y'], supplier.bounding_box()['y'] + supplier.bounding_box()['height'])
        supplier.press('Tab')
        expect(suggestions).to_have_count(0)
        supplier.click()
        expect(suggestions).to_be_visible()
        supplier.fill('R')
        suggestions.get_by_text('RT', exact=True).click()
        expect(supplier).to_have_value('RT')
        dialog.get_by_role('button', name='取消', exact=True).click()
        expect(dialog).not_to_be_visible()
        self.assert_clean()

    def test_dense_desktop_lists_keep_pagination_and_full_text_reachable(self):
        remarks = [
            '运营商邮件直接转发给以下邮箱即可：voice@carrier.example.com',
            '运营商邮件直接转发给以下邮箱即可：noc-east@carrier.example.com; noc-west@carrier.example.com; backbone-operations@carrier.example.com; support@carrier.example.com',
            '',
        ]
        self.api.db.replace_all_supplier_circuits([{
            'supplier': ('RT', 'TTK', 'COLT')[i % 3],
            'supplier_circuit_id': str(751630 + i),
            'circuit_id': f'HKG/CT-Kiev/RT NP{i:03d}' if i % 3 else '',
            'line_type': ('语音电路', '骨干', '客户')[i % 3],
            'line_status': '正常', 'remark': remarks[i % 3],
        } for i in range(45)])
        for i in range(23):
            self.api.db.add_email_record(
                email_id=2000 + i, sender='noc@supplier.example.com', receiver='noc@example.com',
                subject=f'Scheduled maintenance 00/260{i:05d} for China Telecommunications Corporation',
                content=f'Dear China Telecommunications Corporation, please be informed that maintenance NO. 00/260{i:05d} has been scheduled. The main transmission route will be affected during the maintenance window.',
                is_read=i % 3 == 0,
            )
        evidence = Path(__file__).resolve().parents[2] / '.qa' / 'workbench-refinement'
        evidence.mkdir(parents=True, exist_ok=True)
        for width, height in ((1280, 800), (1440, 1000), (1920, 1080)):
            self.page.set_viewport_size({'width': width, 'height': height})
            for route in ('circuits', 'cutover-tasks'):
                self.page.goto(self.base + '/admin/' + route)
                table = self.page.locator('.noc-data-table').first
                expect(table.locator('.n-data-table-tbody > tr')).to_have_count(20)
                for collapsed in (False, True):
                    toggle = self.page.get_by_role('button', name='收起菜单' if collapsed else '展开菜单', exact=True)
                    if toggle.count():
                        toggle.click()
                    self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
                    footer = self.page.locator('.pagination-bar' if route == 'circuits' else '.cutover-pagination')
                    rect = footer.bounding_box()
                    self.assertLessEqual(rect['y'] + rect['height'], height)
                    self.assertGreaterEqual(rect['y'], 0)
                    scroll = table.locator('.n-data-table-base-table-body .n-scrollbar-container')
                    self.assertTrue(scroll.evaluate('el => el.scrollHeight > el.clientHeight'))
                    self.assertTrue(scroll.evaluate('el => el.scrollWidth <= el.clientWidth + 1'))
                    self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
                    if route == 'cutover-tasks':
                        self.assertLessEqual(self.page.locator('.operations-summary').bounding_box()['height'], 74)
                        expect(self.page.locator('.page-heading')).not_to_be_visible()
                        refresh = self.page.locator('.operations-summary-refresh')
                        expect(refresh).to_be_visible()
                        expect(refresh.locator('svg')).to_have_count(1)
                        visible_rows = table.locator('.n-data-table-tbody > tr').evaluate_all('''rows => {
                            const body = rows[0].closest('.n-scrollbar-container').getBoundingClientRect();
                            return rows.filter(row => { const box = row.getBoundingClientRect();
                                return box.top >= body.top && box.bottom <= body.bottom; }).length;
                        }''')
                        self.assertGreaterEqual(visible_rows, 5 if height == 800 else 7)
                    else:
                        expect(self.page.locator('.operations-summary')).to_have_count(0)
                    if route == 'circuits':
                        for row in table.locator('.n-data-table-tbody > tr').all():
                            self.assertLessEqual(row.bounding_box()['height'], 76)
                    self.page.screenshot(path=str(evidence / f'{route}-{width}-{"collapsed" if collapsed else "expanded"}.png'))
            # Supplement the table checks with the settings surface at each desktop width.
            self.page.goto(self.base + '/admin/settings')
            expect(self.page.locator('.settings-view')).to_be_visible()
            self.page.get_by_role('button', name='展开菜单', exact=True).click()
            expect(self.page.locator('.settings-field').first).to_be_visible()
            self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
            self.assertFalse(self.page.evaluate('document.documentElement.scrollWidth > innerWidth'))
            self.page.screenshot(path=str(evidence / f'settings-{width}.png'))
        self.page.goto(self.base + '/admin/circuits')
        preview = self.page.locator('.cell-preview.muted').first
        preview.focus()
        expect(self.page.locator('.cell-preview-tooltip')).to_contain_text(remarks[0])
        preview.press('Escape')
        expect(self.page.locator('.cell-preview-tooltip')).not_to_be_visible()
        self.page.get_by_placeholder('关键字（编号/Circuit ID/备注）').fill('751630')
        self.page.get_by_placeholder('关键字（编号/Circuit ID/备注）').press('Enter')
        expect(self.page.locator('.circuits-table .n-data-table-tbody > tr')).to_have_count(1)
        expect(self.page.locator('.circuits-table')).to_contain_text('751630')
        self.page.get_by_role('button', name='重置', exact=True).click()
        expect(self.page.locator('.circuits-table .n-data-table-tbody > tr')).to_have_count(20)
        self.page.get_by_role('button', name='下一页', exact=True).click()
        expect(self.page.locator('.n-pagination-item--active')).to_have_text('2')
        expect(self.page.locator('.circuits-table')).to_contain_text('751650')
        self.assert_clean()
