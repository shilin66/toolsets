"""Capture the real desktop UI with isolated demonstration fixtures.

Run from the repository root with API_KEY=test-key and a temporary
MAIL_DATABASE_PATH. No production mailbox, AI provider or portal is contacted.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import expect
from tests.ui.test_supplier_discovery_ui import SupplierDiscoveryUiTest
from tests.ui.test_multiuser_ui import MultiuserUiTest
from tests.ui.test_cutover_workbench_ui import CutoverWorkbenchUiTest
from tests.ui.test_cutover_add_defaults_ui import CutoverAddDefaultsUiTest
from tests.ui.test_operations_ui import OperationsUiTest
from tests.ui.test_report_queue_lifecycle_ui import ReportQueueLifecycleUiTest
from tests.ui.test_cutover_attachment_preview_ui import CutoverAttachmentPreviewUiTest
from tests.ui.test_report_gallery_ui import ReportGalleryUiTest

OUTPUT = Path(__file__).resolve().parents[1] / 'manual' / 'images'


def capture(page, name, locator=None):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    page.set_viewport_size({'width': 2560, 'height': 1440})
    if locator is not None:
        locator.scroll_into_view_if_needed()
        locator.evaluate("el => el.scrollIntoView({block: 'start'})")
    page.wait_for_function("document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)")
    page.screenshot(path=str(OUTPUT / (name + '.png')), animations='disabled')
    print('Captured', name, flush=True)


def suppliers(case):
    page = case.page
    capture(page, 'system-settings')
    page.goto(case.base + '/admin/suppliers/new')
    expect(page.locator('.supplier-start')).to_be_visible()
    capture(page, 'supplier-new')
    url = f'/api/supplier-drafts/{case.draft_id}'
    draft = case.fixture.client.get(url, headers=case.fixture.headers).get_json()['data']
    config = {**draft['draft']['config'], 'name': '示例国际网络', 'reply_email': 'maintenance@example.com',
        'line_custom_fields': [{'name': 'ServiceId', 'description': '读取线路表的 Service ID 列，完整保留前导零。'}],
        'line_query_keywords': ['ServiceId'],
        'custom_fields': [{'name': 'carrier', 'description': '读取邮件落款中的运营商名称。'}],
        'email_type_samples': {'割接通知': {'subject': '计划维护通知 · DEMO-2026-001',
            'content': '<h3>Planned Maintenance · 示例通知</h3><p>Ticket: DEMO-2026-001</p>'
            '<p>Window: 12 November 2026 02:00 – 04:00 UTC</p>'
            '<p>Reason: Replace a degraded network card.</p><p>Location: Frankfurt</p>'
            '<table border="1" cellpadding="10"><tr><th>Service ID</th><th>Duration</th></tr>'
            '<tr><td>001234</td><td>10 minutes</td></tr><tr><td>005678</td><td>10 minutes</td></tr></table>'}}}
    result = case.fixture.client.put(url, headers=case.fixture.headers,
                                    json={'revision': draft['revision'], 'config': config})
    assert result.status_code == 200, result.get_json()
    case.open_drafts_list()
    capture(page, 'supplier-drafts')
    case.open_draft_editor()
    def preview(route):
        route.fulfill(json={'success': True, 'data': {'extract_result': json.dumps({
            'carrier_ticket_no': 'DEMO-2026-001', 'cutover_time': '2026-11-12 02:00:00/2026-11-12 04:00:00',
            'cutover_timezone': 'UTC', 'cutover_reason': 'Replace a degraded network card.',
            'location': 'Frankfurt', 'line_query_keywords': ['ServiceId'], 'carrier': '示例国际网络',
            'line_array': [{'ServiceId': '001234', 'ImpactType': 'interrupted', 'ImpactDuration': '10m'},
                           {'ServiceId': '005678', 'ImpactType': 'interrupted', 'ImpactDuration': '10m'}]}, ensure_ascii=False)}})
    page.route('**/api/suppliers/preview-extract', preview)
    page.get_by_role('button', name='识别这封邮件', exact=True).click()
    expect(page.locator('.review-result-status')).to_contain_text('待人工核对')
    capture(page, 'supplier-compare')
    page.get_by_role('button', name='查看 / 编辑规则：ServiceId', exact=True).click()
    capture(page, 'supplier-rule-editor', page.locator('.review-query-options'))
    page.get_by_role('button', name='高级配置', exact=True).click()
    for section, name in [('mailTypes', 'supplier-classification'), ('fixed', 'supplier-fixed-fields'),
                          ('custom', 'supplier-line-fields')]:
        capture(page, name, page.locator('#draft-section-' + section))
    other = page.locator('.supplier-section').filter(has=page.get_by_text('其他信息（可选）', exact=True))
    capture(page, 'supplier-top-fields', other)
    page.get_by_role('button', name='预览提示词', exact=True).click()
    expect(page.get_by_role('button', name='高级设置：完整提示词', exact=True)).to_have_attribute('aria-expanded', 'true')
    capture(page, 'supplier-prompt', page.locator('#draft-section-prompt'))
    page.get_by_text('高级：手工提示词（兼容旧配置，配置了提取字段时不会生效）', exact=True).click()
    capture(page, 'supplier-legacy-prompt', page.locator('.legacy-prompt-collapse'))
    page.get_by_role('button', name='添加分类', exact=True).click()
    capture(page, 'supplier-add-classification', page.locator('.n-modal').last)
    page.get_by_role('button', name='取消', exact=True).last.click()
    page.get_by_role('button', name='返回邮件核对', exact=True).click()
    page.get_by_role('button', name='添加一种线路编号', exact=True).click()
    capture(page, 'supplier-add-identifier', page.locator('.review-identifier-dialog'))
    page.get_by_role('button', name='取消', exact=True).last.click()
    page.get_by_role('button', name='编辑样本', exact=True).click()
    capture(page, 'supplier-edit-sample', page.locator('.mail-sample-editor-dialog'))
    page.get_by_role('button', name='关闭', exact=True).last.click()
    page.goto(case.base + f'/admin/cutover-emails/{case.email_id}')
    expect(page.locator('.cutover-workbench')).to_be_visible()
    capture(page, 'unconfigured-analysis')
    response = case.fixture.client.post('/api/suppliers', headers=case.fixture.headers,
                                         json={**config, 'email': 'formal@example.com'})
    assert response.status_code == 201, response.get_json()
    page.goto(case.base + '/admin/suppliers')
    expect(page.locator('.supplier-config-tabs')).to_be_visible()
    capture(page, 'supplier-list')
    page.goto(case.base + '/admin/circuits')
    page.get_by_role('button', name='新增线路', exact=True).click()
    capture(page, 'circuit-edit', page.locator('.n-modal').last)
    page.get_by_role('button', name='取消', exact=True).last.click()
    page.get_by_role('button', name='增量导入', exact=True).click()
    capture(page, 'circuit-import', page.locator('.n-modal').last)
    assert not case.errors, case.errors


def accounts(case):
    page = case.page()
    capture(page, 'login-user')
    page.get_by_role('button', name='管理员登录', exact=True).click()
    capture(page, 'login-admin')
    page.get_by_role('textbox', name='API Key').fill('test-key')
    page.get_by_role('button', name='登录', exact=True).click()
    expect(page.locator('.workbench-identity')).to_be_visible()
    capture(page, 'cutover-list')
    page.get_by_role('button', name='更多筛选', exact=False).click()
    capture(page, 'cutover-filters')
    page.goto(case.base + '/admin/mail-accounts')
    expect(page.locator('.mail-accounts-panel')).to_be_visible()
    capture(page, 'mail-accounts')
    page.get_by_role('button', name='新增邮箱', exact=True).click()
    capture(page, 'mail-account-edit', page.locator('.n-modal').last)
    page.goto(case.base + '/admin/users')
    page.get_by_role('button', name='张三 alice · 已启用').click()
    expect(page.get_by_role('heading', name='张三 · 邮箱授权')).to_be_visible()
    capture(page, 'user-permissions')
    page.goto(case.base + '/admin/emails')
    expect(page.get_by_role('heading', name='邮件记录', exact=True)).to_be_visible()
    capture(page, 'email-records')
    page.context.close()
    page = case.page()
    case.login_user(page, 'alice', 'a-secure-password')
    page.goto(case.base + '/admin/dispatch-session')
    expect(page.get_by_role('button', name='立即检测', exact=True)).to_be_visible()
    capture(page, 'portal-session')
    assert not case.errors, case.errors


def cutover(case):
    page = case.page
    case.api.db.save_pending_reply(case.api.email_records_id, '维护窗口与重要保障时段冲突，请调整维护时间并再次确认。', 'major_event')
    page.reload()
    expect(page.locator('.cw-compare')).to_be_visible()
    capture(page, 'email-review')
    page.get_by_role('button', name='编辑识别结果', exact=True).click()
    capture(page, 'email-correction', page.locator('.cw-result-dialog'))
    page.get_by_role('button', name='取消', exact=True).last.click()
    case.select_tab('线路确认')
    capture(page, 'line-matching')
    case.select_tab('回复审核')
    capture(page, 'reply-review')
    case.select_tab('上报处理')
    capture(page, 'task-summary')
    case.select_tab('处理记录')
    capture(page, 'processing-history')
    page.get_by_role('button', name='高级信息', exact=True).click()
    capture(page, 'email-advanced', page.locator('#cw-advanced'))
    page.get_by_role('button', name='删除', exact=True).first.click()
    capture(page, 'email-delete-confirm', page.locator('.n-dialog'))
    page.locator('.n-dialog').get_by_role('button', name='取消', exact=True).click()
    assert not case.errors, case.errors


def forms(case):
    case.open_task()
    capture(case.page, 'customer-form', case.panel.locator('.cw-full-form'))
    case.open_task(backbone=True)
    capture(case.page, 'backbone-form', case.panel.locator('.cw-full-form'))
    case.page.goto(case.base + '/admin/circuits')
    expect(case.page.get_by_role('button', name='新增线路', exact=True)).to_be_visible()
    capture(case.page, 'circuits')
    assert not case.errors, case.errors


def operations(case):
    page = case.page(admin=True)
    capture(page, 'operations-overview')
    page.get_by_role('tab', name='运营商明细', exact=True).click()
    expect(page.get_by_role('button', name='导出筛选结果 CSV')).to_be_visible()
    capture(page, 'operations-suppliers')
    page.locator('.stats-name-link').first.click()
    expect(page.get_by_role('tab', name='业务明细', exact=True)).to_be_visible()
    capture(page, 'operations-details')
    assert not case.errors, case.errors


def queue(case):
    case.enqueue()  # Fixture intercepts execution: nothing is submitted to a portal.
    capture(case.page, 'report-queue')
    case.drawer.get_by_role('button', name='暂停任务', exact=True).click()
    expect(case.drawer).to_contain_text('已暂停')
    capture(case.page, 'report-paused')


def attachments(case):
    case.preview('Affected_Services.csv')
    expect(case.page.locator('.cw-source .cw-attachment-table')).to_contain_text('00123')
    capture(case.page, 'attachment-preview')


def history(case):
    case.prepare_report()
    case.panel.locator('.n-data-table-expand-trigger').click()
    expect(case.panel.locator('.report-gallery')).to_be_visible()
    case.page.wait_for_function("[...document.querySelectorAll('.report-thumbnail img')].every(img => img.complete && img.naturalWidth > 0)")
    capture(case.page, 'report-history', case.panel.locator('.report-gallery'))


SCENARIOS = {'suppliers': (SupplierDiscoveryUiTest, suppliers), 'accounts': (MultiuserUiTest, accounts),
             'cutover': (CutoverWorkbenchUiTest, cutover), 'forms': (CutoverAddDefaultsUiTest, forms),
             'operations': (OperationsUiTest, operations), 'queue': (ReportQueueLifecycleUiTest, queue),
             'attachments': (CutoverAttachmentPreviewUiTest, attachments),
             'history': (ReportGalleryUiTest, history)}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenarios', nargs='*', metavar='SCENARIO',
                        help='Scenes to capture (default: all): ' + ', '.join(SCENARIOS))
    args = parser.parse_args()
    for name in args.scenarios:
        if name not in SCENARIOS:
            parser.error('Unknown scenario: ' + name)
    for name in args.scenarios or SCENARIOS:
        cls, run = SCENARIOS[name]
        case = cls()
        try:
            case.setUp()
            run(case)
        finally:
            case.doCleanups()
