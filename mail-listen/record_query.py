import sqlite3
from typing import TypedDict

from loguru import logger

from cutover_task import CUTOVER_SCENE_NORMAL, CUTOVER_TAG_DUPLICATE, cutover_scene_label
from database import EmailDatabase
from email_attachments import build_attachment_url


class QueryPage(TypedDict):
    page: int
    page_size: int
    offset: int


class EmailRecordListResult(TypedDict):
    items: list[dict]
    total: int
    page: int
    pageSize: int


class TicketRecordListResult(TypedDict):
    items: list[dict]
    total: int
    page: int
    pageSize: int


class CutoverTaskListResult(TypedDict):
    items: list[dict]
    total: int
    page: int
    pageSize: int


class CutoverTaskEmailListResult(TypedDict):
    items: list[dict]
    total: int
    page: int
    pageSize: int


class OperationsSummary(TypedDict):
    pending_tasks: int
    failed_tasks: int
    today_emails: int
    last_email_at: str | None


def _supplier_name_by_sender(db: EmailDatabase) -> dict[str, str]:
    """构建发件人邮箱 -> 供应商名称映射（小写邮箱为键），列表供应商列统一按发件人所属供应商显示。"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name, email FROM supplier_configs")
            return {row["email"].lower(): row["name"] for row in cursor.fetchall()}
    except sqlite3.OperationalError as error:
        # 供应商配置表不存在时（如未初始化的临时库）不影响列表查询
        logger.warning(f"查询供应商配置映射失败，供应商列不做兜底: {error}")
        return {}


def _cutover_task_line_count(line_type: str | None, fill_result: dict) -> int:
    """按任务线路类型统计填报线路条数。"""
    if line_type == "backbone":
        return len(fill_result.get("backbone_circuits") or [])
    return len(fill_result.get("circuits") or [])


class RecordQueryRepository:
    def __init__(self, db: EmailDatabase):
        self.db = db

    def get_operations_summary(self) -> OperationsSummary:
        with self.db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM cutover_tasks WHERE status = 'draft') AS pending_tasks,
                    (SELECT COUNT(*) FROM cutover_tasks WHERE status = 'report_failed') AS failed_tasks,
                    (SELECT COUNT(*) FROM email_records
                     WHERE DATE(create_time) = DATE('now', 'localtime')) AS today_emails,
                    (SELECT MAX(create_time) FROM email_records) AS last_email_at
                """
            ).fetchone()

        return {
            "pending_tasks": row["pending_tasks"],
            "failed_tasks": row["failed_tasks"],
            "today_emails": row["today_emails"],
            "last_email_at": row["last_email_at"],
        }

    def list_email_records(self, page: QueryPage, sender: str | None, receiver: str | None = None) -> EmailRecordListResult:
        conditions = []
        params: list[str | int] = []
        if sender:
            conditions.append("sender LIKE ?")
            params.append(f"%{sender}%")
        if receiver:
            conditions.append("receiver = ?")
            params.append(receiver.strip())
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) as total FROM email_records {where_clause}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""
                SELECT id, email_id, sender, receiver, subject, content,
                       html_content, attachments,
                       message_id, reply_to, create_time, update_time
                FROM email_records
                {where_clause}
                ORDER BY create_time DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page["page_size"], page["offset"]],
            )
            rows = []
            for row in cursor.fetchall():
                item = dict(row)
                item["attachments"] = self.db.deserialize_attachments(item.get("attachments"))
                item["attachment_urls"] = [
                    build_attachment_url(relative_path)
                    for relative_path in item["attachments"]
                ]
                rows.append(item)

        return {
            "items": rows,
            "total": total,
            "page": page["page"],
            "pageSize": page["page_size"],
        }

    def list_ticket_records(self, page: QueryPage, status: str | None) -> TicketRecordListResult:
        where_clause = ""
        params: list[str | int] = []
        if status:
            where_clause = "WHERE ticket_records.status = ?"
            params.append(status)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) as total FROM ticket_records {where_clause}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""
                SELECT ticket_records.id, ticket_records.email_records_id,
                       ticket_records.status, ticket_records.carrier_ticket_no,
                       ticket_records.cut_task_id, ticket_records.cut_start_time,
                       ticket_records.cut_end_time, ticket_records.create_time,
                       ticket_records.update_time, email_records.sender,
                       email_records.receiver, email_records.subject
                FROM ticket_records
                LEFT JOIN email_records ON email_records.id = ticket_records.email_records_id
                {where_clause}
                ORDER BY ticket_records.create_time DESC, ticket_records.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page["page_size"], page["offset"]],
            )
            rows = [dict(row) for row in cursor.fetchall()]

        return {
            "items": rows,
            "total": total,
            "page": page["page"],
            "pageSize": page["page_size"],
        }

    def list_cutover_tasks(
        self,
        page: QueryPage,
        status: str | None,
        supplier: str | None,
    ) -> CutoverTaskListResult:
        conditions = []
        params: list[str | int] = []
        if status:
            conditions.append("cutover_tasks.status = ?")
            params.append(status)
        if supplier:
            conditions.append("cutover_tasks.supplier LIKE ?")
            params.append(f"%{supplier}%")
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) as total FROM cutover_tasks {where_clause}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""
                SELECT cutover_tasks.id, cutover_tasks.email_records_id,
                       cutover_tasks.ticket_id, cutover_tasks.line_type,
                       cutover_tasks.supplier,
                       cutover_tasks.carrier_ticket_no, cutover_tasks.title,
                       cutover_tasks.status, cutover_tasks.fill_result,
                       cutover_tasks.customer_excel_filename,
                       cutover_tasks.confirmed_at, cutover_tasks.create_time,
                       cutover_tasks.update_time,
                       email_records.sender, email_records.receiver, email_records.subject
                FROM cutover_tasks
                LEFT JOIN email_records ON email_records.id = cutover_tasks.email_records_id
                {where_clause}
                ORDER BY cutover_tasks.update_time DESC, cutover_tasks.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page["page_size"], page["offset"]],
            )
            rows = []
            for row in cursor.fetchall():
                item = dict(row)
                fill_result = self.db._deserialize_json(item.pop("fill_result", None)) or {}
                item["line_count"] = _cutover_task_line_count(item.get("line_type"), fill_result)
                item["validation_count"] = len(fill_result.get("validation_messages") or [])
                rows.append(item)

        return {
            "items": rows,
            "total": total,
            "page": page["page"],
            "pageSize": page["page_size"],
        }

    def list_cutover_task_emails(
        self,
        page: QueryPage,
        status: str | None,
        supplier: str | None,
        sender: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        tag: str | None = None,
        mail_type: str | None = None,
        receiver: str | None = None,
    ) -> CutoverTaskEmailListResult:
        """按邮件维度列出供应商邮件及其割接任务，每封邮件内嵌其割接任务列表。"""
        # 列表范围 = 全部已入库的供应商邮件（入库前已做供应商校验）
        conditions = []
        params: list[str | int] = []
        # 任务级条件（同时作用于内嵌任务列表）与邮件级条件（仅过滤邮件）分开维护
        task_conditions = []
        task_params: list[str | int] = []
        if status:
            task_conditions.append("cutover_tasks.status = ?")
            task_params.append(status)

        conditions.extend(task_conditions)
        params.extend(task_params)
        # 供应商过滤（邮件级）与显示口径一致：按发件人所属供应商匹配；
        # 发件人未配置供应商时退回按任务上的供应商匹配
        if supplier:
            sender_config_exists = (
                "EXISTS(SELECT 1 FROM supplier_configs AS sc "
                "WHERE lower(sc.email) = lower(email_records.sender))"
            )
            conditions.append(
                "(EXISTS(SELECT 1 FROM supplier_configs AS sc "
                "WHERE lower(sc.email) = lower(email_records.sender) AND sc.name LIKE ?) "
                f"OR (NOT {sender_config_exists} "
                "AND EXISTS(SELECT 1 FROM cutover_tasks AS t "
                "WHERE t.email_records_id = email_records.id AND t.supplier LIKE ?)))"
            )
            params.append(f"%{supplier}%")
            params.append(f"%{supplier}%")
        # 标签过滤（邮件级）：场景标签按 cutover_scene 匹配，duplicate 按重复邮件判定
        if tag:
            if tag == CUTOVER_TAG_DUPLICATE:
                conditions.append("email_records.is_duplicate = 1")
            else:
                conditions.append("email_records.cutover_scene = ?")
                params.append(tag)
        # 邮件类型过滤（邮件级）：按 FastGPT 转发解析出的分类结果精确匹配
        if mail_type:
            conditions.append("email_records.mail_type = ?")
            params.append(mail_type.strip())
        if sender:
            conditions.append("email_records.sender LIKE ?")
            params.append(f"%{sender}%")
        # 接收邮箱过滤（邮件级）：按监听邮箱地址精确匹配
        if receiver:
            conditions.append("email_records.receiver = ?")
            params.append(receiver.strip())
        if start_time:
            conditions.append("email_records.create_time >= ?")
            params.append(start_time.strip())
        if end_time:
            end_value = end_time.strip()
            # 仅传日期时视为当天全天
            if len(end_value) == 10:
                end_value = f"{end_value} 23:59:59"
            conditions.append("email_records.create_time <= ?")
            params.append(end_value)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT COUNT(DISTINCT email_records.id) as total
                FROM email_records
                LEFT JOIN cutover_tasks ON cutover_tasks.email_records_id = email_records.id
                {where_clause}
                """,
                params,
            )
            total = cursor.fetchone()["total"]
            cursor.execute(
                f"""
                SELECT email_records.id, email_records.email_id,
                       email_records.sender, email_records.receiver, email_records.subject,
                       email_records.create_time,
                       email_records.cutover_scene,
                       email_records.cutover_scene_remark,
                       email_records.mail_type,
                       email_records.is_duplicate,
                       email_records.reply_status,
                       COUNT(cutover_tasks.id) as task_count,
                       MAX(cutover_tasks.update_time) as latest_update_time,
                       GROUP_CONCAT(DISTINCT cutover_tasks.supplier) as suppliers,
                       GROUP_CONCAT(DISTINCT cutover_tasks.carrier_ticket_no) as carrier_ticket_nos
                FROM email_records
                LEFT JOIN cutover_tasks ON cutover_tasks.email_records_id = email_records.id
                {where_clause}
                GROUP BY email_records.id
                ORDER BY MAX(COALESCE(cutover_tasks.update_time, email_records.create_time)) DESC,
                         email_records.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page["page_size"], page["offset"]],
            )
            emails = [dict(row) for row in cursor.fetchall()]

            email_ids = [item["id"] for item in emails]
            tasks_by_email: dict[int, list[dict]] = {email_id: [] for email_id in email_ids}
            if email_ids:
                placeholders = ",".join("?" * len(email_ids))
                nested_conditions = list(task_conditions) + [f"email_records_id IN ({placeholders})"]
                nested_params = list(task_params) + email_ids
                cursor.execute(
                    f"""
                    SELECT * FROM cutover_tasks
                    WHERE {' AND '.join(nested_conditions)}
                    ORDER BY update_time DESC, id DESC
                    """,
                    nested_params,
                )
                for row in cursor.fetchall():
                    task = dict(row)
                    task.pop("fill_payload", None)
                    fill_result = self.db._deserialize_json(task.pop("fill_result", None)) or {}
                    task["line_count"] = _cutover_task_line_count(task.get("line_type"), fill_result)
                    task["validation_count"] = len(fill_result.get("validation_messages") or [])
                    tasks_by_email[task["email_records_id"]].append(task)

            supplier_name_by_sender = _supplier_name_by_sender(self.db)
            for item in emails:
                item["tasks"] = tasks_by_email.get(item["id"], [])
                item["cutover_scene"] = item.get("cutover_scene") or CUTOVER_SCENE_NORMAL
                item["cutover_scene_label"] = cutover_scene_label(item["cutover_scene"])
                item["cutover_scene_remark"] = item.get("cutover_scene_remark") or ""
                item["mail_type"] = item.get("mail_type") or ""
                item["is_duplicate"] = bool(item.get("is_duplicate"))
                item["reply_status"] = item.get("reply_status") or ""
                # 供应商列统一按发件人所属供应商显示；发件人未匹配到配置时退回任务聚合值
                sender = (item.get("sender") or "").lower()
                item["suppliers"] = supplier_name_by_sender.get(sender) or item.get("suppliers")

        return {
            "items": emails,
            "total": total,
            "page": page["page"],
            "pageSize": page["page_size"],
        }

    def get_distinct_mail_types(self) -> list[str]:
        """返回已解析的邮件类型去重列表（非空），供列表标签筛选下拉使用。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT mail_type FROM email_records "
                "WHERE mail_type IS NOT NULL AND mail_type != '' "
                "ORDER BY mail_type"
            )
            return [row["mail_type"] for row in cursor.fetchall()]

    def get_cutover_email_detail(self, email_records_id: int) -> dict | None:
        """获取割接邮件详情：邮件基本信息、正文、附件及其下的割接任务列表。"""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, email_id, sender, receiver, subject, content,
                       html_content, attachments, cutover_scene, cutover_scene_remark,
                       mail_type, extract_result, is_duplicate,
                       reply_status, pending_reply_content, pending_reply_scene, reply_time,
                       reply_to,
                       create_time, update_time
                FROM email_records
                WHERE id = ?
                """,
                (email_records_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            email = dict(row)
            email["cutover_scene"] = email.get("cutover_scene") or CUTOVER_SCENE_NORMAL
            email["cutover_scene_label"] = cutover_scene_label(email["cutover_scene"])
            email["cutover_scene_remark"] = email.get("cutover_scene_remark") or ""
            email["mail_type"] = email.get("mail_type") or ""
            email["extract_result"] = email.get("extract_result") or ""
            email["is_duplicate"] = bool(email.get("is_duplicate"))
            email["reply_status"] = email.get("reply_status") or ""
            email["pending_reply_content"] = email.get("pending_reply_content") or ""
            email["pending_reply_scene"] = email.get("pending_reply_scene") or ""
            email["pending_reply_scene_label"] = cutover_scene_label(email["pending_reply_scene"]) \
                if email["pending_reply_scene"] else ""
            email["reply_time"] = email.get("reply_time") or ""
            email["reply_to"] = email.get("reply_to") or ""
            email["attachments"] = self.db.deserialize_attachments(email.get("attachments"))
            email["attachment_urls"] = [
                build_attachment_url(relative_path)
                for relative_path in email["attachments"]
            ]

            cursor.execute(
                """
                SELECT * FROM cutover_tasks
                WHERE email_records_id = ?
                ORDER BY line_type, id
                """,
                (email_records_id,),
            )
            tasks = []
            for task_row in cursor.fetchall():
                task = dict(task_row)
                task.pop("fill_payload", None)
                fill_result = self.db._deserialize_json(task.pop("fill_result", None)) or {}
                task["line_count"] = _cutover_task_line_count(task.get("line_type"), fill_result)
                task["validation_count"] = len(fill_result.get("validation_messages") or [])
                tasks.append(task)
            email["tasks"] = tasks

        return email


def build_query_page(page_value: str | None, page_size_value: str | None) -> QueryPage:
    page = _positive_int(page_value, 1)
    page_size = min(_positive_int(page_size_value, 20), 100)
    return {
        "page": page,
        "page_size": page_size,
        "offset": (page - 1) * page_size,
    }


def _positive_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if parsed < 1:
        return default
    return parsed
