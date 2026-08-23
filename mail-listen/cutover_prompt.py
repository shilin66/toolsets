"""通用割接提取提示词生成模块。

后台内置固定字段（carrier_ticket_no、cutover_time、cutover_backup_time、
cutover_timezone、cutover_reason、location）及其提取规则，
以及 line_array 的固定子字段（ImpactType、ImpactDateTime、ImpactDuration、
InteruptionsCounts）。供应商只需要配置 line_array 的自定义字段，
并勾选用于线路查询的关键字字段（line_query_keywords），
本模块负责渲染出完整的 LLM 提取提示词。

除 line_array 自定义字段外，供应商还可配置顶层自定义字段（custom_fields），
输出在提取结果 JSON 的顶层，用于特殊规则判断等场景。
"""

import json

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LineCustomField(BaseModel):
    """line_array 元素中的自定义字段。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, description="line_array 元素中的字段名")
    description: str = Field(default="", description="字段提取规则描述")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not value.replace("_", "").isalnum():
            raise ValueError("字段名只能包含字母、数字和下划线")
        return value


FIXED_FIELDS = [
    {
        "name": "carrier_ticket_no",
        "required": True,
        "description": (
            "从邮件中提取运营商单号。\n\n"
            "对应邮件内容中：\n\n"
            "* No:"
        ),
    },
    {
        "name": "cutover_time",
        "required": True,
        "description": (
            "从邮件正文中提取割接时间，并转换为 UTC 时间。\n\n"
            "对应邮件内容中：Start Time 和 End Time\n\n"
            "* 包括开始时间和结束时间，输出格式固定为 `YYYY-MM-DD HH:mm:ss/YYYY-MM-DD HH:mm:ss`。\n"
            "* 如果正文中只有一个时间点，保留该时间点对应的原文含义，并格式化为 `YYYY-MM-DD HH:mm:ss`。\n"
            "* 如果原文包含时间范围，必须同时提取开始时间和结束时间。\n"
            "* 如果原文时间跨天，需要正确保留跨天后的日期。\n"
            "* 如果原文未提供年份，但邮件正文或标题中存在可用年份，可以使用该年份。\n"
            "* 如果无法确定日期或时间，返回空字符串。\n"
            "* 识别原文中的时区，例如 UTC、GMT、CST、BJT、HKT、SGT、PST、EST、CET、JST、KST 等，"
            "按\"时间格式与转换规则\"转换为 UTC。\n"
            "* 若原文明确为北京时间、中国标准时间、BJT、CST、GMT+8、UTC+8、HKT、SGT，则按 UTC+8 转换为 UTC。\n"
            "* 若原文未明确时区，不要自行推断，返回原文可识别的时间表达，并将 cutover_timezone 置为空字符串。"
        ),
    },
    {
        "name": "cutover_backup_time",
        "required": False,
        "description": (
            "从邮件正文中提取备用割接时间（如 Backup Time、Reserve Time、备用窗口等）。\n\n"
            "* 时间格式与时区转换规则与 cutover_time 一致。\n"
            "* 如果邮件未提供备用割接时间，返回空字符串。"
        ),
    },
    {
        "name": "cutover_timezone",
        "required": True,
        "description": (
            "割接时间转换后的时区。\n\n"
            "* 若 cutover_time 已成功转换为 UTC，则输出 `UTC`。\n"
            "* 若原文没有明确时区，无法进行 UTC 转换，则输出空字符串。\n"
            "* 不要输出原始时区。"
        ),
    },
    {
        "name": "cutover_reason",
        "required": True,
        "description": (
            "从邮件正文中提取割接原因。\n\n"
            "常见关键词包括但不限于：割接原因、变更原因、维护原因、Maintenance Reason、"
            "Change Reason、Reason、升级、扩容、优化、故障修复、设备替换、线路调整、网络调整、"
            "版本升级、设备维护。\n\n"
            "* 优先提取关键词后的完整原因描述。\n"
            "* 如果正文中存在专门的\"原因/Reason\"字段，优先使用该字段。\n"
            "* 如果没有明确原因字段，但正文中有清晰说明本次割接目的，可以提取原文描述。\n"
            "* 不要根据常识补充或改写正文中不存在的原因。\n"
            "* 如果无法识别割接原因，返回空字符串。"
        ),
    },
    {
        "name": "location",
        "required": True,
        "description": (
            "从邮件正文中提取割接地点、影响地点或涉及资源位置。\n\n"
            "可能包含：城市、国家/地区、站点、机房、局点、线路、节点、POP、DC、区域、"
            "起止端点、A/Z End、Site、Location、POP Name、Data Center。\n\n"
            "* 优先提取正文中明确标注为\"割接地点 / 维护地点 / Location / Site / POP / DC / A End / Z End\""
            "等字段的内容。\n"
            "* 如果正文表格中包含线路两端、站点或节点信息，也可以提取与本次割接最相关的位置描述。\n"
            "* 保留原文中的地点名称和缩写，不要自行补全城市、国家或机房名称。\n"
            "* 如果无法识别地点，返回空字符串。"
        ),
    },
]

FIXED_LINE_FIELDS = [
    {
        "name": "ImpactType",
        "description": "影响类型，例如中断、闪断、丢包、抖动、降级、无影响、Service interruption 等，根据 Downtime 判断",
    },
    {
        "name": "ImpactDateTime",
        "description": "与 cutover_time 保持一致",
    },
    {
        "name": "ImpactDuration",
        "description": "影响时长，单位 h，例如 30 m、2 h、more than 60 minutes 等，从 Downtime 中获取；如果无影响则为 0",
    },
    {
        "name": "InteruptionsCounts",
        "description": "默认值 1",
    },
]

PROMPT_HEADER = """你是一个"运营商割接邮件解析助手"。
供应商可能把割接信息放在附件中。
你的任务是根据附件和邮件内容，准确提取运营商割接信息，并输出结构化 JSON。

## 输入内容

输入通常包含：

* 邮件标题
* 邮件正文
* 正文中的表格内容

## 输出要求

只输出一个 JSON 对象，不要输出解释、分析过程或多余文本。

JSON 字段如下：

```json
{schema_json}
```
"""

LINE_ARRAY_RULES = """### {index}. line_array（必填，数组）

从邮件正文中的表格或明显的列表型线路信息中提取线路影响信息，输出 JSON 数组。
如果每条线路没有单独的 ImpactType、ImpactDateTime、ImpactDuration，则从整体的割接信息中获取，保持一致。

数组中每个元素包含以下字段：

{line_field_bullets}

提取规则：

* 仅从邮件正文中的表格或明显的列表型线路信息中提取。
* 表格中有多行线路信息时，每一行输出为数组中的一个对象。
* 字段不存在时填空字符串。
* 不要编造任何表格中不存在的线路信息。
* 表头名称可能不完全一致，需要根据语义映射到上述字段。
* `ImpactDateTime` 若表格中存在明确时区，需要转换为北京时间。
* 若表格影响时间未写时区，但正文割接时间已明确时区，则可使用正文割接时间时区进行转换。
* 若无法确定时区，不要转换，保留可识别的原文时间表达。
* 若表格没有任何线路影响信息，返回空数组 `[]`。
"""

TIME_CONVERSION_RULES = """## 时间格式与转换规则

### 标准输出格式

时间范围统一格式为：

```text
YYYY-MM-DD HH:mm:ss/YYYY-MM-DD HH:mm:ss
```

单个时间点统一格式为：

```text
YYYY-MM-DD HH:mm:ss
```

### 时区转换规则

* UTC：不转换
* GMT：按 UTC 处理
* BJT / 北京时间 / 中国标准时间 / CST（中国语境）/ GMT+8 / UTC+8 / HKT / SGT：减 8 小时得到 UTC
* JST / KST：减 9 小时得到 UTC
* CET：减 1 小时得到 UTC
* CEST：减 2 小时得到 UTC
* PST：加 8 小时得到 UTC
* PDT：加 7 小时得到 UTC
* EST：加 5 小时得到 UTC
* EDT：加 4 小时得到 UTC

注意：

* `cutover_time` 与 `cutover_backup_time` 必须转换为 UTC。
* `line_array[].ImpactDateTime` 必须转换为北京时间，即 UTC+8。
* 如果原文没有明确时区，也无法从正文其他割接时间字段确定时区，则不要自行推断。
* 如果日期跨天，转换后必须正确调整日期。
* 如果原文只有日期没有时间，或只有时间没有日期，且无法从上下文补全，则保留原文可识别内容，不能编造完整时间。
"""

STRICT_LIMITS = """## 严格限制

* 不要编造信息。
* 不要根据常识推断正文中不存在的内容。
* 不要输出解释。
* 不要输出 Markdown。
* 不要输出解析过程。
* 所有字段必须存在。
* 无法提取的字段使用空字符串。
* 无法提取线路表格时，`line_array` 使用空数组。
* JSON 必须合法，可直接被程序解析。
"""


def build_cutover_extract_prompt(
    line_custom_fields: list[LineCustomField] | list[dict] | None = None,
    line_query_keywords: list[str] | None = None,
    extra_instructions: str | None = None,
    fixed_field_rules: dict[str, str] | None = None,
    custom_fields: list[LineCustomField] | list[dict] | None = None,
) -> str:
    """根据固定字段与自定义字段生成完整的割接提取提示词。

    fixed_field_rules 可按字段名覆盖固定字段的内置提取规则；
    custom_fields 为顶层自定义字段，输出在提取结果 JSON 顶层。
    """
    custom_fields_models = _normalize_custom_fields(line_custom_fields)
    top_custom_fields = _normalize_custom_fields(custom_fields)
    check_custom_extract_fields(top_custom_fields)
    keywords = list(line_query_keywords or [])
    custom_names = {field.name for field in custom_fields_models}
    for keyword in keywords:
        if keyword not in custom_names:
            raise ValueError(
                f"线路查询关键字 {keyword} 必须是 line_array 中的自定义字段"
            )
    overrides = _normalize_fixed_field_rules(fixed_field_rules)

    schema = _build_schema(keywords, custom_fields_models, top_custom_fields)
    sections = [PROMPT_HEADER.format(schema_json=json.dumps(schema, ensure_ascii=False, indent=2))]

    sections.append("## 字段提取规则\n")
    index = 1
    for fixed in FIXED_FIELDS:
        sections.append(_render_fixed_field_section(index, fixed, overrides))
        index += 1
    for field in top_custom_fields:
        sections.append(_render_custom_field_section(index, field))
        index += 1
    sections.append(_render_keywords_section(index, keywords))
    index += 1
    sections.append(_render_line_array_section(index, custom_fields_models, overrides))

    sections.append(TIME_CONVERSION_RULES)
    sections.append(STRICT_LIMITS)

    extra = (extra_instructions or "").strip()
    if extra:
        sections.append(f"## 补充说明\n\n{extra}\n")

    return "\n".join(sections).strip() + "\n"


def get_fixed_field_definitions() -> dict[str, list[dict]]:
    """导出固定字段的内置默认提取规则，供前端预填。"""
    return {
        "top_fields": [
            {
                "name": fixed["name"],
                "required": fixed["required"],
                "description": fixed["description"],
            }
            for fixed in FIXED_FIELDS
        ],
        "line_fields": [
            {"name": fixed["name"], "description": fixed["description"]}
            for fixed in FIXED_LINE_FIELDS
        ],
    }


def check_fixed_field_rules(fixed_field_rules: dict[str, str] | None) -> None:
    """校验规则覆盖的字段名必须是已知的固定字段。"""
    _normalize_fixed_field_rules(fixed_field_rules)


# 提取结果 JSON 的保留键，顶层自定义字段不得占用
RESERVED_OUTPUT_KEYS = {
    fixed["name"] for fixed in FIXED_FIELDS
} | {
    fixed["name"] for fixed in FIXED_LINE_FIELDS
} | {"line_query_keywords", "line_array"}


def check_custom_extract_fields(
    custom_fields: list[LineCustomField] | list[dict] | None,
) -> None:
    """校验顶层自定义字段：不得与保留键冲突，且自身不重复。"""
    fields = _normalize_custom_fields(custom_fields)
    seen: set[str] = set()
    for field in fields:
        if field.name in RESERVED_OUTPUT_KEYS:
            raise ValueError(f"自定义字段 {field.name} 与内置字段或保留键冲突")
        if field.name in seen:
            raise ValueError(f"自定义字段 {field.name} 重复")
        seen.add(field.name)


def _normalize_fixed_field_rules(
    fixed_field_rules: dict[str, str] | None,
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    known_names = {fixed["name"] for fixed in FIXED_FIELDS} | {
        fixed["name"] for fixed in FIXED_LINE_FIELDS
    }
    for name, description in (fixed_field_rules or {}).items():
        if name not in known_names:
            raise ValueError(f"未知的固定字段：{name}")
        text = (description or "").strip()
        if text:
            overrides[name] = text
    return overrides


def _normalize_custom_fields(
    line_custom_fields: list[LineCustomField] | list[dict] | None,
) -> list[LineCustomField]:
    fields: list[LineCustomField] = []
    for item in line_custom_fields or []:
        if isinstance(item, LineCustomField):
            field = item
        else:
            field = LineCustomField.model_validate(item)
        fields.append(field)
    return fields


def _build_schema(
    keywords: list[str],
    custom_fields: list[LineCustomField],
    top_custom_fields: list[LineCustomField] | None = None,
) -> dict:
    line_item: dict = {}
    for fixed in FIXED_LINE_FIELDS:
        line_item[fixed["name"]] = "1" if fixed["name"] == "InteruptionsCounts" else ""
    for field in custom_fields:
        line_item[field.name] = ""
    schema = {
        "carrier_ticket_no": "",
        "cutover_time": "",
        "cutover_backup_time": "",
        "cutover_timezone": "UTC",
        "cutover_reason": "",
        "location": "",
    }
    for field in top_custom_fields or []:
        schema[field.name] = ""
    schema["line_query_keywords"] = keywords
    schema["line_array"] = [line_item]
    return schema


def _render_fixed_field_section(index: int, fixed: dict, overrides: dict[str, str]) -> str:
    required_text = "必填" if fixed["required"] else "非必填"
    description = overrides.get(fixed["name"], fixed["description"])
    return (
        f"### {index}. {fixed['name']}（{required_text}）\n\n"
        f"{description}\n"
    )


def _render_custom_field_section(index: int, field: LineCustomField) -> str:
    description = field.description.strip() or "从邮件主题或正文中提取该字段的内容"
    return (
        f"### {index}. {field.name}（非必填）\n\n"
        f"{description}\n\n"
        f"* 如果无法提取，返回空字符串。\n"
    )


def _render_keywords_section(index: int, keywords: list[str]) -> str:
    keywords_json = json.dumps(keywords, ensure_ascii=False)
    return (
        f"### {index}. line_query_keywords（必填）\n\n"
        f"需要进行线路查询的字段名称，固定输出 `{keywords_json}`，不需要从正文中提取。\n"
    )


def _render_line_array_section(
    index: int,
    custom_fields: list[LineCustomField],
    overrides: dict[str, str],
) -> str:
    bullets = [
        f"* `{fixed['name']}`：{overrides.get(fixed['name'], fixed['description'])}"
        for fixed in FIXED_LINE_FIELDS
    ]
    for field in custom_fields:
        description = field.description.strip() or "从线路表格中提取对应列的内容"
        bullets.append(f"* `{field.name}`：{description}")
    return LINE_ARRAY_RULES.format(
        index=index,
        line_field_bullets="\n".join(bullets),
    )
