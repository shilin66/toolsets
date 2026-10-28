"""Add/copy/save regressions in Chromium with isolated task data."""
from pathlib import Path
import unittest
from unittest.mock import patch

from playwright.sync_api import expect

from tests.api import test_cutover_task_api as fixture
from tests.ui import test_naive_migration_ui as migration


class CutoverAddDefaultsUiTest(unittest.TestCase):
    setUp = migration.NaiveMigrationUiTest.setUp
    assert_clean = migration.NaiveMigrationUiTest.assert_clean

    def open_task(self, backbone=False, empty=False):
        circuit = fixture.BACKBONE_CIRCUIT if backbone else fixture.CUSTOMER_CIRCUIT
        payload = self.api.fill_payload()
        if backbone:
            payload['line_array_info']['data'][0]['ImpactType'] = 'interrupted'
        response = self.api.post_fill(payload, circuits=[circuit])
        self.task_id = self.api.first_task_id(response)
        task = self.api.db.get_cutover_task(self.task_id)
        if empty:
            fill = task['fill_result']
            for key in ('circuits', 'reasons', 'backbone_circuits'):
                if key in fill:
                    fill[key] = []
            self.api.db.update_cutover_task(self.task_id, fill_result=fill)
        self.page.goto(f'{self.base}/admin/cutover-emails/{self.api.email_records_id}?taskId={self.task_id}')
        self.panel = self.page.locator('.task-detail-panel')
        expect(self.panel).to_be_visible()
        self.panel.get_by_role("button", name="完整填报内容", exact=False).click()
        return task

    def save(self):
        evidence = Path(__file__).resolve().parents[2] / '.qa' / 'cutover-add-defaults'
        evidence.mkdir(parents=True, exist_ok=True)
        self.panel.screenshot(path=str(evidence / f'{self._testMethodName}.png'))
        with patch.object(fixture.api_server, 'save_workbook_output',
                          return_value=Path(self.api.tmpdir.name) / 'test.xlsx'):
            with self.page.expect_response(lambda r: r.request.method == 'PATCH' and r.url.endswith(f'/tasks/{self.task_id}')) as result:
                self.panel.get_by_role('button', name='保存修改', exact=True).click()
            self.assertEqual(result.value.status, 200)
        self.assert_clean()
        return self.api.db.get_cutover_task(self.task_id)['fill_result']

    def test_empty_customer_adds_fixed_defaults_and_can_save(self):
        self.page.set_viewport_size({'width': 1280, 'height': 1000})
        self.open_task(empty=True)
        tables = self.panel.locator('.sheet-table')
        for button in self.panel.get_by_role('button', name='添加行', exact=True).all():
            button.click()
        expect(tables.nth(0).get_by_role('textbox', name='割接省', exact=True)).to_have_value('国际公司')
        expect(tables.nth(0).get_by_role('textbox', name='电路代号', exact=True)).to_have_value('')
        fill = self.save()
        self.assertEqual(fill['circuits'][0]['割接省'], '国际公司')
        self.assertIsNone(fill['circuits'][0]['客户电路在割接段是否有保护'])
        self.assertIsNone(fill['circuits'][0]['预计影响客户业务时长'])
        self.assertIsNone(fill['circuits'][0]['时间类型'])
        self.assertEqual(fill['reasons'][0]['割接类型'], '紧急割接')
        self.assertIsNone(fill['reasons'][0]['割接原因'])

    def test_customer_copies_latest_unsaved_row_independently(self):
        self.open_task()
        tables = self.panel.locator('.sheet-table')
        for index in range(2):
            add = self.panel.get_by_role('button', name='添加行', exact=True).nth(index)
            add.click()
            rows = tables.nth(index).locator('tbody tr')
            rows.nth(1).locator('input').first.fill('最新编辑')
            add.click()
            expect(rows.nth(2).locator('input').first).to_have_value('最新编辑')
            rows.nth(2).locator('input').first.fill('副本独立修改')
            expect(rows.nth(1).locator('input').first).to_have_value('最新编辑')
        fill = self.save()
        for key in ('circuits', 'reasons'):
            self.assertEqual(len(fill[key]), 3)
            self.assertEqual(fill[key][0]['割接时间'], fill[key][2]['割接时间'])

    def test_empty_backbone_adds_defaults_even_after_removing_all(self):
        self.page.set_viewport_size({'width': 1280, 'height': 1000})
        self.open_task(backbone=True, empty=True)
        add = self.panel.get_by_role('button', name='添加骨干线路', exact=True)
        add.click()
        cards = self.panel.locator('.backbone-card')
        expect(cards).to_have_count(1)
        expect(cards.get_by_label('标题', exact=True)).to_have_value('')
        expect(cards.get_by_label('变更操作等级', exact=True)).to_have_value('四级')
        cards.get_by_role('button', name='删除', exact=True).click()
        add.click()
        expect(cards).to_have_count(1)
        fill = self.save()
        card = fill['backbone_circuits'][0]
        self.assertEqual(card['割接对象']['系统名称'], [])
        self.assertIsNone(card['基本信息']['中断类型'])
        self.assertIsNone(card['基本信息']['标题'])
        self.assertEqual(card['基本信息']['操作厂家'], '无')
        self.assertIsNone(card['其他']['割接原因'])

    def check_backbone_defaults_retry(self, first_response):
        self.open_task(backbone=True)
        cards = self.panel.locator('.backbone-card')
        cards.get_by_role('button', name='删除', exact=True).click()
        expect(cards).to_have_count(0)
        requests = []

        def template_response(route):
            requests.append(route.request.url)
            if len(requests) == 1:
                route.fulfill(json=first_response)
            else:
                route.continue_()

        self.page.route('**/api/cutover/template-columns', template_response)
        add = self.panel.get_by_role('button', name='添加骨干线路', exact=True)
        add.click()
        expect(self.page.locator('.n-message')).to_be_visible()
        expect(cards).to_have_count(0)
        # A backend upgrade or recovered request must work without reloading the editor.
        add.click()
        expect(cards).to_have_count(1, timeout=2000)
        expect(cards.get_by_label('标题', exact=True)).to_have_value('')
        expect(cards.get_by_label('变更操作等级', exact=True)).to_have_value('四级')
        self.assertEqual(len(requests), 2)
        self.assert_clean()

    def test_backbone_retries_legacy_template_response_after_removing_all(self):
        self.check_backbone_defaults_retry({
            'success': True, 'data': {'circuit': [], 'reason': []},
        })

    def test_backbone_retries_failed_template_request_after_removing_all(self):
        self.check_backbone_defaults_retry({
            'success': False, 'message': 'Temporary template failure',
        })

    def test_backbone_confirmations_display_and_save_yes_no_values(self):
        original = self.open_task(backbone=True)['fill_result']['backbone_circuits'][0]
        self.assertTrue(all(value == '是' for value in original['确认项'].values()))
        self.panel.get_by_role('button', name='展开全部', exact=True).click()
        checks = self.panel.locator('.backbone-confirmation-checkbox')
        expect(checks).to_have_count(3)
        for checkbox in checks.all():
            expect(checkbox).to_be_checked()
            expect(checkbox).to_have_text('已选中')
        checks.first.click()
        expect(checks.first).not_to_be_checked()
        expect(checks.first).to_have_text('未选中')
        saved = self.save()['backbone_circuits'][0]['确认项']
        self.assertEqual(saved, {
            **original['确认项'],
            '该割接已按照集团相关文件要求经过省公司领导审批。': '否',
        })
        self.page.reload()
        self.panel.get_by_role('button', name='完整填报内容', exact=False).click()
        self.panel.get_by_role('button', name='展开全部', exact=True).click()
        expect(checks.first).not_to_be_checked()
        expect(checks.nth(1)).to_be_checked()
        checks.first.press('Space')
        expect(checks.first).to_be_checked()
        expect(checks.first).to_have_text('已选中')
        saved = self.save()['backbone_circuits'][0]['确认项']
        self.assertTrue(all(value == '是' for value in saved.values()))
        checks.last.scroll_into_view_if_needed()
        self.page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
        self.page.screenshot(path=str(Path(__file__).resolve().parents[2] / '.qa' / 'cutover-add-defaults' / 'confirmations-checked.png'))

    def test_backbone_copies_latest_card_and_nested_systems_independently(self):
        original = self.open_task(backbone=True)['fill_result']['backbone_circuits'][0]
        add = self.panel.get_by_role('button', name='添加骨干线路', exact=True)
        cards = self.panel.locator('.backbone-card')
        add.click()
        expect(cards).to_have_count(2)
        expect(cards.nth(1).get_by_label('标题', exact=True)).to_have_value(original['基本信息']['标题'])
        cards.nth(1).get_by_label('标题', exact=True).fill('最新骨干线路')
        add.click()
        expect(cards.nth(2).get_by_label('标题', exact=True)).to_have_value('最新骨干线路')
        cards.nth(2).get_by_label('标题', exact=True).fill('独立副本')
        cards.nth(2).get_by_role('button', name='展开全部', exact=True).click()
        cards.nth(2).locator('.backbone-system-select .n-base-selection').click()
        systems = cards.nth(2).locator('.backbone-system-select input')
        systems.fill('EXTRA-SYSTEM')
        systems.press('Enter')
        fill = self.save()
        copies = fill['backbone_circuits']
        normalized = {
            section: {key: None if value == '' else value for key, value in fields.items()}
            for section, fields in original.items()
        }
        self.assertEqual(copies[0], normalized)
        self.assertEqual(copies[2]['基本信息']['中断时间 (分钟)'], 240)
        self.assertEqual(copies[1]['基本信息']['标题'], '最新骨干线路')
        self.assertEqual(copies[2]['基本信息']['标题'], '独立副本')
        self.assertEqual(copies[1]['割接对象']['系统名称'], original['割接对象']['系统名称'])
        self.assertIn('EXTRA-SYSTEM', copies[2]['割接对象']['系统名称'])
