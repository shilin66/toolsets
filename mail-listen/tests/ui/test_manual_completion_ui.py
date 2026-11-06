import unittest
from pathlib import Path
from playwright.sync_api import expect
from tests.ui import test_cutover_add_defaults_ui as fixtures


class ManualCompletionUiTest(unittest.TestCase):
    use_user_login = True
    setUp = fixtures.CutoverAddDefaultsUiTest.setUp
    open_task = fixtures.CutoverAddDefaultsUiTest.open_task
    assert_clean = fixtures.CutoverAddDefaultsUiTest.assert_clean

    def test_mark_failed_report_and_keep_original_error_after_reload(self):
        self.open_task(backbone=True)
        rid = self.api.db.add_cutover_report(self.task_id, 'backbone', 'failed',
            {'error': '原始提交超时', 'note': '异常发生在提交阶段', 'operation_log': []})
        self.api.db.update_cutover_task(self.task_id, status='report_failed')
        self.page.reload()
        self.panel.locator('.n-data-table-expand-trigger').first.click()
        self.panel.get_by_role('button', name='手动标记已上报', exact=True).click()
        dialog = self.page.get_by_role('dialog')
        dialog.get_by_role('button', name='确认标记', exact=True).click()
        expect(dialog.get_by_role('alert')).to_contain_text('请填写处理说明')
        dialog.get_by_role('textbox', name='处理说明', exact=True).fill('已核对综调单号 123')
        dialog.get_by_role('button', name='确认标记', exact=True).click()
        expect(dialog).to_have_count(0)
        self.assertEqual(self.api.db.get_cutover_task(self.task_id)['status'], 'reported')
        self.page.reload()
        self.panel.locator('.n-data-table-expand-trigger').first.click()
        expect(self.panel.locator('.report-error')).to_have_text('原始提交超时')
        expect(self.panel.locator('.manual-report-audit')).to_contain_text('operator')
        expect(self.panel.locator('.manual-report-audit')).to_contain_text('已核对综调单号 123')
        self.panel.get_by_text('原始异常记录', exact=True).click()
        expect(self.panel.locator('.manual-report-audit pre')).to_contain_text('异常发生在提交阶段')
        self.assertEqual(self.api.db.get_cutover_report(rid)['status'], 'success')
        evidence = Path('.qa/manual-completion'); evidence.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(evidence / 'report-audit.png'), full_page=True)
        self.assert_clean()

    def test_complete_entire_email_and_show_completed_in_list(self):
        tasks = self.api.fill_tasks(self.api.post_fill_mixed(self.api.mixed_fill_payload()))
        rid = self.api.db.add_cutover_report(tasks[0]['id'], 'customer', 'failed', {'error': '历史异常保留'})
        self.page.goto(f'{self.base}/admin/cutover-emails/{self.api.email_records_id}')
        self.page.get_by_role('button', name='标记已完成', exact=True).click()
        dialog = self.page.get_by_role('dialog')
        dialog.get_by_role('button', name='取消', exact=True).click()
        self.assertEqual(self.api.db.get_cutover_task(tasks[0]['id'])['status'], 'draft')
        self.page.get_by_role('button', name='标记已完成', exact=True).click()
        dialog.get_by_role('textbox', name='处理说明', exact=True).fill('全部线路已人工处理')
        dialog.get_by_role('button', name='确认标记', exact=True).click()
        expect(self.page.locator('.manual-completion-audit')).to_contain_text('全部线路已人工处理')
        self.page.reload()
        expect(self.page.locator('.manual-completion-audit')).to_contain_text('operator')
        for task in tasks:
            self.assertEqual(self.api.db.get_cutover_task(task['id'])['status'], 'completed')
        self.assertEqual(self.api.db.get_cutover_report(rid)['result']['error'], '历史异常保留')
        self.page.goto(f'{self.base}/admin/cutover-emails/{self.api.email_records_id}?taskId={tasks[1]["id"]}')
        panel = self.page.locator('.task-detail-panel')
        panel.get_by_role('button', name='完整填报内容', exact=False).click()
        expect(panel.get_by_role('button', name='保存修改', exact=True)).to_be_disabled()
        expect(panel.get_by_label('标题', exact=True)).to_be_disabled()
        evidence = Path('.qa/manual-completion'); evidence.mkdir(parents=True, exist_ok=True)
        for width in (1280, 1440):
            self.page.set_viewport_size({'width': width, 'height': 1000})
            self.assertLessEqual(self.page.evaluate('document.documentElement.scrollWidth - innerWidth'), 1)
            self.page.screenshot(path=str(evidence / f'completed-{width}.png'), animations='disabled')
        self.page.goto(f'{self.base}/admin/cutover-tasks?status=completed')
        expect(self.page.locator('.cutover-processing')).to_contain_text('已完成')
        self.assert_clean()
