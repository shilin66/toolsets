"""Task editor fits its desktop container; only sheet contents may scroll sideways."""
from pathlib import Path
import unittest
from unittest.mock import patch

from playwright.sync_api import expect

from tests.ui import test_cutover_add_defaults_ui as defaults


class TaskDetailLayoutUiTest(unittest.TestCase):
    setUp = defaults.CutoverAddDefaultsUiTest.setUp
    open_task = defaults.CutoverAddDefaultsUiTest.open_task
    assert_clean = defaults.CutoverAddDefaultsUiTest.assert_clean

    def check_desktop_layout(self, backbone):
        self.open_task(backbone=backbone)
        for width in (1280, 1440, 1920):
            self.page.set_viewport_size({'width': width, 'height': 1000})
            for collapsed in (False, True):
                if collapsed:
                    self.page.get_by_role('button', name='收起菜单', exact=True).click()
                else:
                    expand = self.page.get_by_role('button', name='展开菜单', exact=True)
                    if expand.count():
                        expand.click()
                self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
                with self.subTest(width=width, collapsed=collapsed, backbone=backbone):
                    metrics = self.panel.evaluate('''el => {
                        const viewport = el.closest('.cw-selected-task').getBoundingClientRect();
                        const panel = el.getBoundingClientRect();
                        // The editor is now a standalone panel. Hidden accordion actions have no layout box.
                        const controls = [...el.querySelectorAll('.panel-heading-tools button, .block-head button, .backbone-card-tools button, .task-type-switch, .backbone-field-grid > label, .task-meta-item')].filter(e => e.getClientRects().length);
                        return {panelRight:panel.right, panelLeft:panel.left,
                            viewportRight:viewport.right, viewportLeft:viewport.left,
                            overflow:el.scrollWidth-el.clientWidth,
                            controls:controls.map(e=>({right:e.getBoundingClientRect().right,left:e.getBoundingClientRect().left}))};
                    }''')
                    self.assertLessEqual(metrics['panelRight'], metrics['viewportRight'] + 1)
                    self.assertGreaterEqual(metrics['panelLeft'], metrics['viewportLeft'] - 1)
                    self.assertLessEqual(metrics['overflow'], 1)
                    for control in metrics['controls']:
                        self.assertLessEqual(control['right'], metrics['viewportRight'] + 1)
                        self.assertGreaterEqual(control['left'], metrics['viewportLeft'] - 1)
                    if not backbone and width == 1280:
                        sheet = self.panel.locator('.sheet-table-wrap').first
                        self.assertTrue(sheet.evaluate('el => el.scrollWidth > el.clientWidth'))
                    self.panel.locator('.task-type-switch').scroll_into_view_if_needed()
                    evidence = Path(__file__).resolve().parents[2] / '.qa' / 'task-detail-layout'
                    evidence.mkdir(parents=True, exist_ok=True)
                    self.page.screenshot(path=str(evidence / f'{"backbone" if backbone else "customer"}-{width}-{"collapsed" if collapsed else "expanded"}.png'))
                    self.assert_clean()

    def test_backbone_editor_fits_desktop_with_both_sidebar_states(self):
        self.check_desktop_layout(backbone=True)

    def test_customer_editor_fits_desktop_with_both_sidebar_states(self):
        self.check_desktop_layout(backbone=False)

    def test_type_selection_style_and_keyboard_switch_preserve_behavior(self):
        self.open_task(backbone=True)
        group = self.panel.get_by_role('radiogroup')
        customer = group.get_by_role('radio', name='客户线路填报', exact=True)
        backbone = group.get_by_role('radio', name='骨干线路填报', exact=True)
        expect(backbone).to_be_checked()
        expect(customer).not_to_be_checked()
        selected = group.locator('.n-radio-button--checked')
        unselected = group.locator('.n-radio-button:not(.n-radio-button--checked)')
        expect(selected.locator('.noc-icon')).to_have_css('opacity', '1')
        expect(unselected.locator('.noc-icon')).to_have_css('opacity', '0')
        self.assertNotEqual(selected.evaluate('el => getComputedStyle(el).backgroundColor'),
                            unselected.evaluate('el => getComputedStyle(el).backgroundColor'))
        with patch.object(defaults.fixture.api_server, 'save_workbook_output',
                          return_value=Path(self.api.tmpdir.name) / 'test.xlsx'):
            customer.focus()
            customer.press('Space')
            expect(customer).to_be_checked()
            expect(backbone).not_to_be_checked()
            expect(self.panel.locator('.sheet-table')).to_have_count(2)
            self.assertEqual(self.api.db.get_cutover_task(self.task_id)['line_type'], 'customer')
        group.locator('label').filter(has_text='骨干线路填报').click()
        expect(backbone).to_be_checked()
        expect(self.panel.locator('.backbone-card')).to_have_count(1)
        self.assertEqual(self.api.db.get_cutover_task(self.task_id)['line_type'], 'backbone')
        self.assert_clean()
