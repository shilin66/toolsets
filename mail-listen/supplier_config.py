import json
import sqlite3
from datetime import datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from cutover_prompt import (
    LineCustomField,
    build_cutover_extract_prompt,
    check_custom_extract_fields,
    check_fixed_field_rules,
)
from database import EmailDatabase


# 内置邮件类型列表，用于 AI 邮件分类的样本配置
MAIL_TYPE_OPTIONS: tuple[str, ...] = (
    "割接通知",
    "割接改期",
    "割接取消",
    "割接提醒",
    "故障邮件",
)

# 唯一必须提供样本的邮件类型
REQUIRED_MAIL_TYPE = "割接通知"

# 分类兜底类型：不属于任何已配置类型时输出，不参与样本配置
OTHER_MAIL_TYPE = "其它"

# 各邮件类型的含义说明，用于生成分类提示词
MAIL_TYPE_DESCRIPTIONS: dict[str, str] = {
    "割接通知": "供应商告知计划内的割接/维护安排，通常包含割接时间、影响范围与影响线路",
    "割接改期": "供应商通知原定割接的时间发生变更（推迟或提前）",
    "割接取消": "供应商通知原定割接已取消，不再执行",
    "割接提醒": "供应商对即将执行的割接计划进行提醒或确认",
    "故障邮件": "供应商通知线路或网络突发故障，与计划内割接无关",
    "其它": "不属于以上任何类型的邮件，如商务往来、账单、一般性通告等与割接/故障无关的内容",
}


class EmailTypeSample(BaseModel):
    """单个邮件类型的样本，主题与正文分开配置。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    subject: str = ""
    content: str = ""
    content_in_attachment: bool = False


class SupplierConfigCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1)
    email: EmailStr
    can_reply_directly: bool = False
    prompt_mode: Literal["auto", "manual"] = "manual"
    cutover_extract_prompt: str = ""
    line_custom_fields: list[LineCustomField] = Field(default_factory=list)
    line_query_keywords: list[str] = Field(default_factory=list)
    fixed_field_rules: dict[str, str] = Field(default_factory=dict)
    custom_fields: list[LineCustomField] = Field(default_factory=list)
    email_type_samples: dict[str, EmailTypeSample] = Field(default_factory=dict)
    extra_instructions: str = ""

    @model_validator(mode="after")
    def _check_prompt_config(self):
        if self.prompt_mode == "manual" and not self.cutover_extract_prompt:
            raise ValueError("手工提示词模式下请填写割接字段提取提示词")
        _check_query_keywords(self.line_custom_fields, self.line_query_keywords)
        check_fixed_field_rules(self.fixed_field_rules)
        check_custom_extract_fields(self.custom_fields)
        check_email_type_samples(self.email_type_samples)
        return self


class SupplierConfigUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1)
    email: EmailStr | None = None
    can_reply_directly: bool | None = None
    prompt_mode: Literal["auto", "manual"] | None = None
    cutover_extract_prompt: str | None = None
    line_custom_fields: list[LineCustomField] | None = None
    line_query_keywords: list[str] | None = None
    fixed_field_rules: dict[str, str] | None = None
    custom_fields: list[LineCustomField] | None = None
    email_type_samples: dict[str, EmailTypeSample] | None = None
    extra_instructions: str | None = None


class SupplierConfigRecord(TypedDict):
    id: int
    name: str
    email: str
    can_reply_directly: bool
    prompt_mode: str
    cutover_extract_prompt: str
    line_custom_fields: list[dict[str, Any]]
    line_query_keywords: list[str]
    fixed_field_rules: dict[str, str]
    custom_fields: list[dict[str, Any]]
    email_type_samples: dict[str, dict[str, Any]]
    extra_instructions: str
    create_time: str
    update_time: str
    supplier_mail_classify_prompt: str


class SupplierConfigConflictError(Exception):
    def __init__(self, field: str):
        self.field = field
        super().__init__(_conflict_message(field))


class SupplierConfigRepository:
    def __init__(self, db: EmailDatabase):
        self.db = db
        self.ensure_table()

    def ensure_table(self) -> None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS supplier_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE,
                    can_reply_directly INTEGER NOT NULL DEFAULT 0,
                    prompt_mode TEXT NOT NULL DEFAULT 'manual',
                    cutover_extract_prompt TEXT NOT NULL DEFAULT '',
                    line_custom_fields TEXT NOT NULL DEFAULT '[]',
                    line_query_keywords TEXT NOT NULL DEFAULT '[]',
                    fixed_field_rules TEXT NOT NULL DEFAULT '{}',
                    custom_fields TEXT NOT NULL DEFAULT '[]',
                    email_type_samples TEXT NOT NULL DEFAULT '{}',
                    extra_instructions TEXT NOT NULL DEFAULT '',
                    create_time TEXT NOT NULL,
                    update_time TEXT NOT NULL
                )
            ''')
            self._ensure_columns(cursor)
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_supplier_configs_email
                ON supplier_configs(email)
            ''')
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_configs_name
                ON supplier_configs(name)
            ''')
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS uq_supplier_configs_email
                ON supplier_configs(email)
            ''')
            conn.commit()

    @staticmethod
    def _ensure_columns(cursor) -> None:
        """为已有 SQLite 表补齐新增字段。"""
        cursor.execute("PRAGMA table_info(supplier_configs)")
        existing_columns = {row["name"] for row in cursor.fetchall()}
        required_columns = {
            "prompt_mode": "TEXT NOT NULL DEFAULT 'manual'",
            "line_custom_fields": "TEXT NOT NULL DEFAULT '[]'",
            "line_query_keywords": "TEXT NOT NULL DEFAULT '[]'",
            "fixed_field_rules": "TEXT NOT NULL DEFAULT '{}'",
            "custom_fields": "TEXT NOT NULL DEFAULT '[]'",
            "email_type_samples": "TEXT NOT NULL DEFAULT '{}'",
            "extra_instructions": "TEXT NOT NULL DEFAULT ''",
        }
        for column_name, column_def in required_columns.items():
            if column_name not in existing_columns:
                cursor.execute(
                    f'ALTER TABLE supplier_configs ADD COLUMN "{column_name}" {column_def}'
                )

    def create(self, payload: SupplierConfigCreate) -> SupplierConfigRecord:
        now = _current_time_text()
        conflict_error: SupplierConfigConflictError | None = None
        supplier_id: int | None = None
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO supplier_configs (
                        name, email, can_reply_directly, prompt_mode,
                        cutover_extract_prompt, line_custom_fields,
                        line_query_keywords, fixed_field_rules,
                        custom_fields, email_type_samples, extra_instructions,
                        create_time, update_time
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    payload.name,
                    str(payload.email),
                    int(payload.can_reply_directly),
                    payload.prompt_mode,
                    payload.cutover_extract_prompt,
                    json.dumps(
                        [field.model_dump() for field in payload.line_custom_fields],
                        ensure_ascii=False,
                    ),
                    json.dumps(payload.line_query_keywords, ensure_ascii=False),
                    json.dumps(payload.fixed_field_rules, ensure_ascii=False),
                    json.dumps(
                        [field.model_dump() for field in payload.custom_fields],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        {
                            mail_type: sample.model_dump()
                            for mail_type, sample in payload.email_type_samples.items()
                        },
                        ensure_ascii=False,
                    ),
                    payload.extra_instructions,
                    now,
                    now,
                ))
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                conflict_error = _conflict_error_from_integrity(exc)
            else:
                supplier_id = cursor.lastrowid
                conn.commit()

        if conflict_error is not None:
            raise conflict_error
        if supplier_id is None:
            raise RuntimeError("供应商配置创建后读取失败")
        record = self.get(supplier_id)
        if record is None:
            raise RuntimeError("供应商配置创建后读取失败")
        return record

    def get(self, supplier_id: int) -> SupplierConfigRecord | None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM supplier_configs WHERE id = ?', (supplier_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return _row_to_record(row)

    def get_by_email(self, email: str) -> SupplierConfigRecord | None:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM supplier_configs WHERE lower(email) = lower(?)', (email,))
            row = cursor.fetchone()
            if row is None:
                return None
            return _row_to_record(row)

    def list(self) -> list[SupplierConfigRecord]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT *
                FROM supplier_configs
                ORDER BY create_time DESC, id DESC
            ''')
            return [_row_to_record(row) for row in cursor.fetchall()]

    def update(
        self,
        supplier_id: int,
        payload: SupplierConfigUpdate,
    ) -> SupplierConfigRecord | None:
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return self.get(supplier_id)

        existing = self.get(supplier_id)
        if existing is None:
            return None
        merged_custom_fields = update_data.get(
            "line_custom_fields", existing["line_custom_fields"],
        )
        merged_keywords = update_data.get(
            "line_query_keywords", existing["line_query_keywords"],
        )
        _check_query_keywords(merged_custom_fields, merged_keywords)
        if "fixed_field_rules" in update_data:
            check_fixed_field_rules(update_data["fixed_field_rules"])
        if "custom_fields" in update_data:
            check_custom_extract_fields(update_data["custom_fields"])
        if "email_type_samples" in update_data:
            check_email_type_samples(update_data["email_type_samples"])

        set_clauses: list[str] = []
        values: list[str | int] = []
        for field_name, field_value in update_data.items():
            set_clauses.append(f"{field_name} = ?")
            if field_name == "can_reply_directly":
                values.append(int(field_value))
            elif field_name == "line_custom_fields":
                # model_dump(exclude_unset=True) 已将字段转为 dict 列表，直接序列化
                values.append(json.dumps(field_value, ensure_ascii=False))
            elif field_name == "line_query_keywords":
                values.append(json.dumps(field_value, ensure_ascii=False))
            elif field_name == "fixed_field_rules":
                values.append(json.dumps(field_value, ensure_ascii=False))
            elif field_name == "custom_fields":
                values.append(json.dumps(field_value, ensure_ascii=False))
            elif field_name == "email_type_samples":
                values.append(json.dumps(field_value, ensure_ascii=False))
            else:
                values.append(str(field_value))

        set_clauses.append("update_time = ?")
        values.append(_current_time_text())
        values.append(supplier_id)

        conflict_error: SupplierConfigConflictError | None = None
        updated_count = 0
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"UPDATE supplier_configs SET {', '.join(set_clauses)} WHERE id = ?",
                    values,
                )
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                conflict_error = _conflict_error_from_integrity(exc)
            else:
                updated_count = cursor.rowcount
                if updated_count > 0:
                    conn.commit()

        if conflict_error is not None:
            raise conflict_error
        if updated_count == 0:
            return None
        return self.get(supplier_id)

    def delete(self, supplier_id: int) -> bool:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM supplier_configs WHERE id = ?', (supplier_id,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted


def _current_time_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _conflict_error_from_integrity(error: sqlite3.IntegrityError) -> SupplierConfigConflictError:
    message = str(error)
    if "supplier_configs.name" in message:
        return SupplierConfigConflictError("name")
    if "supplier_configs.email" in message:
        return SupplierConfigConflictError("email")
    return SupplierConfigConflictError("unknown")


def _conflict_message(field: str) -> str:
    messages = {
        "name": "供应商名称已存在",
        "email": "供应商邮箱已存在",
    }
    return messages.get(field, "供应商名称或邮箱已存在")


def _row_to_record(row: sqlite3.Row) -> SupplierConfigRecord:
    line_custom_fields = _parse_json_list(row["line_custom_fields"])
    line_query_keywords = _parse_json_list(row["line_query_keywords"])
    fixed_field_rules = _parse_json_dict(row["fixed_field_rules"])
    custom_fields = _parse_json_list(
        row["custom_fields"] if "custom_fields" in row.keys() else "[]"
    )
    email_type_samples = _normalize_email_type_samples(
        _parse_json_dict(row["email_type_samples"])
    )
    extra_instructions = row["extra_instructions"] or ""
    stored_prompt = row["cutover_extract_prompt"] or ""
    prompt_mode = row["prompt_mode"] if "prompt_mode" in row.keys() else "manual"
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "can_reply_directly": bool(row["can_reply_directly"]),
        "prompt_mode": prompt_mode,
        "cutover_extract_prompt": _resolve_prompt(
            prompt_mode, line_custom_fields, line_query_keywords,
            fixed_field_rules, extra_instructions, stored_prompt,
            custom_fields,
        ),
        "line_custom_fields": line_custom_fields,
        "line_query_keywords": line_query_keywords,
        "fixed_field_rules": fixed_field_rules,
        "custom_fields": custom_fields,
        "email_type_samples": email_type_samples,
        "extra_instructions": extra_instructions,
        "create_time": row["create_time"],
        "update_time": row["update_time"],
        "supplier_mail_classify_prompt": build_mail_classify_prompt(
            row["name"], email_type_samples,
        ),
    }


def _parse_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return parsed


def _parse_json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def build_mail_classify_prompt(
    supplier_name: str,
    email_type_samples: dict[str, dict[str, Any]],
) -> str:
    """根据供应商配置的邮件类型样本生成邮件分类提示词（few-shot）。"""
    sections = [
        f'你是一个"邮件分类助手"。\n'
        f'请判断供应商「{supplier_name}」发来的邮件属于哪一种类型，并输出结构化 JSON。\n',
        "## 可选类型\n",
    ]
    for mail_type in MAIL_TYPE_OPTIONS:
        sections.append(f"* {mail_type}：{MAIL_TYPE_DESCRIPTIONS[mail_type]}")
    sections.append(f"* {OTHER_MAIL_TYPE}：{MAIL_TYPE_DESCRIPTIONS[OTHER_MAIL_TYPE]}")

    sample_sections = []
    for mail_type in MAIL_TYPE_OPTIONS:
        sample = email_type_samples.get(mail_type) or {}
        subject, content, content_in_attachment = _sample_fields(sample)
        if not subject and not content:
            continue
        lines = [f"### 类型：{mail_type}\n"]
        if subject:
            lines.append(f"样本主题：{subject}")
        if content:
            lines.append(f"样本正文：\n{content}")
        if content_in_attachment:
            lines.append("（注意：该供应商此类邮件的详细正文放在附件中，分类时需结合附件内容）")
        sample_sections.append("\n".join(lines) + "\n")

    if sample_sections:
        sections.append("\n## 样本参考（few-shot）\n")
        sections.extend(sample_sections)

    sections.append("""## 分类规则

* 结合邮件主题、正文与附件内容综合判断。
* 割接改期、割接取消、割接提醒通常引用了原定割接计划，以此区别于割接通知。
* 故障邮件描述的是突发故障，与计划内割接无关。
* 若邮件与割接、故障均无关，分类为「其它」，不得强行归入以上类型。
* 类型只能从可选类型中选择，不得自行创造新类型。

## 输出要求

只输出一个 JSON 对象，不要输出解释、分析过程或多余文本：

```json
{
  "mail_type": "<类型名>"
}
```""")
    return "\n".join(sections).strip() + "\n"


def check_email_type_samples(samples: dict[str, Any]) -> None:
    """校验邮件类型样本。

    - 类型名必须在内置列表中；
    - 割接通知为必填：主题与正文均不能为空；部分供应商会把详细正文放在
      附件中（content_in_attachment），但邮件正文本身仍存在，仍需提供；
    - 其余类型非必填。
    """
    for mail_type, sample in samples.items():
        if mail_type not in MAIL_TYPE_OPTIONS:
            raise ValueError(f"邮件类型 {mail_type} 不在支持的类型列表中")
        subject, content, _ = _sample_fields(sample)
        if mail_type == REQUIRED_MAIL_TYPE:
            if not subject:
                raise ValueError(f"邮件类型 {mail_type} 的主题样本不能为空")
            if not content:
                raise ValueError(f"邮件类型 {mail_type} 的正文样本不能为空")


def _sample_fields(sample: Any) -> tuple[str, str, bool]:
    """兼容 EmailTypeSample 模型与 dict 两种输入，返回（主题、正文、正文在附件中）。"""
    if isinstance(sample, EmailTypeSample):
        return sample.subject, sample.content, sample.content_in_attachment
    if isinstance(sample, dict):
        return (
            str(sample.get("subject") or "").strip(),
            str(sample.get("content") or "").strip(),
            bool(sample.get("content_in_attachment")),
        )
    return "", "", False


def _normalize_email_type_samples(samples: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """将库中的样本统一为 {subject, content, content_in_attachment} 结构。

    兼容早期版本存储的纯文本样本（作为正文处理）。
    """
    normalized: dict[str, dict[str, Any]] = {}
    for mail_type, sample in samples.items():
        if isinstance(sample, str):
            normalized[mail_type] = {
                "subject": "",
                "content": sample,
                "content_in_attachment": False,
            }
        elif isinstance(sample, dict):
            subject, content, content_in_attachment = _sample_fields(sample)
            normalized[mail_type] = {
                "subject": subject,
                "content": content,
                "content_in_attachment": content_in_attachment,
            }
    return normalized


def _check_query_keywords(
    line_custom_fields: list[LineCustomField] | list[dict[str, Any]],
    line_query_keywords: list[str],
) -> None:
    names = {
        field.name if isinstance(field, LineCustomField) else field.get("name")
        for field in line_custom_fields
    }
    for keyword in line_query_keywords:
        if keyword not in names:
            raise ValueError(
                f"线路查询关键字 {keyword} 必须是 line_array 中的自定义字段"
            )


def _resolve_prompt(
    prompt_mode: str,
    line_custom_fields: list[dict[str, Any]],
    line_query_keywords: list[str],
    fixed_field_rules: dict[str, str],
    extra_instructions: str,
    stored_prompt: str,
    custom_fields: list[dict[str, Any]] | None = None,
) -> str:
    """auto 模式根据固定字段与自定义字段自动生成提示词，否则使用手工提示词。"""
    if prompt_mode != "auto":
        return stored_prompt
    try:
        return build_cutover_extract_prompt(
            line_custom_fields, line_query_keywords,
            extra_instructions, fixed_field_rules,
            custom_fields=custom_fields or [],
        )
    except ValueError:
        return stored_prompt
