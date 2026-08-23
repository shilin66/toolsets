import unittest

from pydantic import ValidationError

from cutover_prompt import (
    LineCustomField,
    build_cutover_extract_prompt,
    check_fixed_field_rules,
    get_fixed_field_definitions,
)


class CutoverPromptTest(unittest.TestCase):
    def test_build_prompt_contains_fixed_fields_and_rules(self):
        prompt = build_cutover_extract_prompt()

        for name in [
            "carrier_ticket_no",
            "cutover_time",
            "cutover_backup_time",
            "cutover_timezone",
            "cutover_reason",
            "location",
            "line_query_keywords",
            "line_array",
        ]:
            self.assertIn(f'"{name}"', prompt)
        for line_field in ["ImpactType", "ImpactDateTime", "ImpactDuration", "InteruptionsCounts"]:
            self.assertIn(f'"{line_field}"', prompt)
        self.assertIn("cutover_backup_time（非必填）", prompt)
        self.assertIn("carrier_ticket_no（必填）", prompt)
        self.assertIn("时间格式与转换规则", prompt)
        self.assertIn("严格限制", prompt)

    def test_custom_field_and_query_keywords_rendered(self):
        prompt = build_cutover_extract_prompt(
            line_custom_fields=[
                {"name": "CircuitTitle", "description": "对应表格中的 Circuit Title 列"},
            ],
            line_query_keywords=["CircuitTitle"],
        )

        self.assertIn('"CircuitTitle": ""', prompt)
        self.assertIn('"line_query_keywords": [\n    "CircuitTitle"\n  ]', prompt)
        self.assertIn('固定输出 `["CircuitTitle"]`', prompt)
        self.assertIn("对应表格中的 Circuit Title 列", prompt)

    def test_keyword_must_be_custom_field(self):
        with self.assertRaises(ValueError):
            build_cutover_extract_prompt(
                line_custom_fields=[{"name": "CircuitTitle"}],
                line_query_keywords=["NotConfigured"],
            )

    def test_extra_instructions_appended(self):
        prompt = build_cutover_extract_prompt(extra_instructions="该供应商时间均为曼谷时间。")
        self.assertIn("补充说明", prompt)
        self.assertIn("该供应商时间均为曼谷时间。", prompt)

    def test_invalid_field_name_rejected(self):
        with self.assertRaises(ValidationError):
            LineCustomField.model_validate({"name": "bad name!"})

    def test_fixed_field_rules_override_defaults(self):
        prompt = build_cutover_extract_prompt(
            fixed_field_rules={
                "carrier_ticket_no": "从邮件标题中提取单号，格式为 CR 开头。",
                "ImpactType": "仅识别 Service interruption 和 No impact 两种取值",
            },
        )

        self.assertIn("从邮件标题中提取单号，格式为 CR 开头。", prompt)
        self.assertNotIn("* No:", prompt)
        self.assertIn("仅识别 Service interruption 和 No impact 两种取值", prompt)

    def test_unknown_fixed_field_rule_rejected(self):
        with self.assertRaises(ValueError):
            build_cutover_extract_prompt(fixed_field_rules={"not_a_field": "规则"})
        with self.assertRaises(ValueError):
            check_fixed_field_rules({"not_a_field": "规则"})

    def test_fixed_field_definitions_exported(self):
        definitions = get_fixed_field_definitions()
        top_names = [field["name"] for field in definitions["top_fields"]]
        line_names = [field["name"] for field in definitions["line_fields"]]
        self.assertIn("carrier_ticket_no", top_names)
        self.assertIn("cutover_backup_time", top_names)
        self.assertIn("ImpactType", line_names)
        backup = next(
            field for field in definitions["top_fields"]
            if field["name"] == "cutover_backup_time"
        )
        self.assertFalse(backup["required"])


if __name__ == "__main__":
    unittest.main()
