import unittest
from pathlib import Path
from playwright.sync_api import expect
from tests.ui import test_cutover_add_defaults_ui as fixtures


class ManualUndoUiTest(unittest.TestCase):
    use_user_login = True
    setUp = fixtures.CutoverAddDefaultsUiTest.setUp
    open_task = fixtures.CutoverAddDefaultsUiTest.open_task
    assert_clean = fixtures.CutoverAddDefaultsUiTest.assert_clean

    def failed_report(self):
        self.open_task(backbone=True)
        self.error = '提交后未检测到导入日志或已知确认弹窗；失败截图： /srv/private/mail-store/very-long-path/report-failure.webp'
        self.rid = self.api.db.add_cutover_report(self.task_id, 'backbone', 'failed', {
            'error':self.error, 'note':self.error, 'operation_log':[],
            'execution_identity': {'principal_key':f'user-{self.api.operator["id"]}', 'username':'portal-test', 'environment':'test'}})
        self.api.db.update_cutover_task(self.task_id, status='report_failed')
        self.page.reload()
        self.panel.locator('.n-data-table-expand-trigger').click()

    def confirm_note(self, text):
        dialog = self.page.get_by_role('dialog')
        dialog.get_by_role('textbox', name='处理说明', exact=True).fill(text)
        dialog.get_by_role('button', name='确认标记', exact=True).click()
        expect(dialog).to_have_count(0)

    def test_failed_action_is_compact_and_paths_are_in_details(self):
        self.failed_report()
        evidence = Path('.qa/manual-undo'); evidence.mkdir(parents=True, exist_ok=True)
        for width in (1280, 1920):
            self.page.set_viewport_size({'width':width,'height':1000})
            button = self.panel.get_by_role('button', name='手动标记已上报', exact=True)
            self.assertLess(button.bounding_box()['width'], 240)
            expect(self.panel.locator('.report-operation-detail .panel-actions')).to_have_count(0)
            expect(self.panel.locator('.report-result-note')).not_to_contain_text('/srv/private')
            self.panel.get_by_text('异常详情', exact=True).click()
            expect(self.panel.locator('.report-error-details')).to_contain_text(self.error)
            self.panel.get_by_text('异常详情', exact=True).click()
            self.panel.locator('.report-operation-detail').scroll_into_view_if_needed()
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
            self.page.screenshot(path=str(evidence / f'failed-{width}.png'), animations='disabled')
        self.assert_clean()

    def test_manual_badge_is_visible_collapsed_and_undo_restores_failure(self):
        self.failed_report()
        self.panel.get_by_role('button', name='手动标记已上报', exact=True).click()
        self.confirm_note('已在综调确认单号 123')
        expect(self.panel.locator('.report-manual-summary')).to_contain_text('人工标记')
        expect(self.panel.locator('.report-manual-summary')).to_contain_text('operator')
        expect(self.panel.locator('.report-manual-summary')).to_contain_text('已在综调确认单号 123')
        self.page.reload()
        expect(self.panel.locator('.report-manual-summary')).to_be_visible()
        self.panel.locator('.n-data-table-expand-trigger').click()
        evidence = Path('.qa/manual-undo'); evidence.mkdir(parents=True, exist_ok=True)
        self.panel.locator('.report-operation-detail').scroll_into_view_if_needed()
        self.page.screenshot(path=str(evidence / 'manual-mark.png'), animations='disabled')
        self.panel.get_by_role('button', name='撤销人工标记', exact=True).click()
        self.confirm_note('误操作，恢复失败状态')
        expect(self.panel.locator('.report-manual-summary')).to_have_count(0)
        self.assertEqual(self.api.db.get_cutover_report(self.rid)['status'], 'failed')
        self.page.reload()
        self.panel.locator('.n-data-table-expand-trigger').click()
        self.panel.get_by_text('人工操作记录', exact=False).click()
        expect(self.panel.locator('.manual-action-history')).to_contain_text('误操作，恢复失败状态')
        self.assertEqual(self.api.db.get_cutover_report(self.rid)['result']['error'], self.error)
        self.assert_clean()

    def test_undo_completion_restores_editing_and_keeps_both_events(self):
        self.open_task(backbone=True)
        self.page.get_by_role('button', name='标记已完成', exact=True).click()
        self.confirm_note('已办结')
        expect(self.page.locator('.manual-completion-audit')).to_be_visible()
        evidence = Path('.qa/manual-undo'); evidence.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(evidence / 'completion-undo.png'), animations='disabled')
        self.page.get_by_role('button', name='撤销已完成', exact=True).click()
        self.confirm_note('误操作，继续处理')
        expect(self.page.locator('.manual-completion-audit')).to_have_count(0)
        expect(self.page.get_by_role('button', name='标记已完成', exact=True)).to_be_enabled()
        self.assertEqual(self.api.db.get_cutover_task(self.task_id)['status'], 'draft')
        self.page.reload()
        self.page.get_by_text('人工操作记录', exact=False).click()
        expect(self.page.locator('.manual-completion-history')).to_contain_text('误操作，继续处理')
        self.assert_clean()
