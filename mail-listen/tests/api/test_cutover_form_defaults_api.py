"""Defaults used when manually adding the first circuit to a task."""
import unittest
from unittest.mock import patch

from tests.api.test_cutover_task_api import api_server


class CutoverFormDefaultsApiTest(unittest.TestCase):
    def test_defaults_keep_constants_and_clear_variables(self):
        settings = {
            'backbone_noc_phone': '123456',
            'backbone_province_reviewer_name': 'Test Reviewer',
            'backbone_province_reviewer_phone': '654321',
        }
        with patch.object(api_server, 'get_backbone_personnel_settings', return_value=settings):
            response = api_server.app.test_client().get(
                '/api/cutover/template-columns',
                headers={'Authorization': 'Bearer test-key'},
            )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()['data']
        defaults = data['defaults']
        for kind in ('circuit', 'reason'):
            self.assertEqual(set(defaults[kind]), set(data[kind]))
            self.assertEqual(defaults[kind]['割接省'], '国际公司')
            for key in ('割接时间', '时间类型', '割接线路/设备名称'):
                self.assertFalse(defaults[kind][key])
        for key in ('电路代号', '客户电路在割接段是否有保护', '预计影响客户业务时长'):
            self.assertFalse(defaults['circuit'][key])
        self.assertEqual(defaults['reason']['割接类型'], '紧急割接')
        self.assertFalse(defaults['reason']['割接原因'])
        card = defaults['backbone']
        self.assertEqual(card['基本信息']['变更操作等级'], '四级')
        self.assertFalse(card['基本信息']['标题'])
        self.assertFalse(card['基本信息']['中断类型'])
        self.assertEqual(card['割接对象']['系统名称'], [])
        self.assertFalse(card['割接对象']['割接开始时间'])
        self.assertFalse(card['割接对象']['割接结束时间'])
        self.assertFalse(card['其他']['割接原因'])
        self.assertTrue(all(value == '是' for value in card['确认项'].values()))
        for key in ('现场指挥人员名称', '现场指挥人电话', '操作审核人姓名', '操作审核人电话'):
            self.assertFalse(card['人员信息'][key])
        self.assertEqual(card['人员信息']['支撑人电话'], '123456')
        self.assertEqual(card['人员信息']['省公司审核人姓名'], 'Test Reviewer')
        self.assertEqual(card['人员信息']['省公司审核人电话'], '654321')
