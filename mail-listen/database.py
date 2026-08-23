"""
数据库管理模块
"""
import hashlib
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger


# 重复邮件判定：存在 subject_hash/content_hash 相同、UID 不同且接收更早的记录。
# 与 mail_listener 入库后 find_duplicate_email_record 的时序语义一致；外层表须以 email_records 引用。
DUPLICATE_EMAIL_EXISTS_SQL = """EXISTS(
    SELECT 1 FROM email_records AS d
    WHERE d.subject_hash = email_records.subject_hash
      AND d.content_hash = email_records.content_hash
      AND d.email_id != email_records.email_id
      AND email_records.subject_hash IS NOT NULL
      AND email_records.content_hash IS NOT NULL
      AND (d.create_time < email_records.create_time
           OR (d.create_time = email_records.create_time AND d.id < email_records.id))
)"""


class EmailDatabase:
    """邮件数据库管理类"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            # 默认使用 data 目录
            data_dir = os.path.join(os.getcwd(), "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "mail_listener.db")

        self.db_path = db_path
        # WAL 只需首次启用（数据库文件级持久属性），后续连接跳过避免多余开销；
        # 多进程/多线程各自实例化时仍会幂等检查一次实际 journal_mode
        self._wal_enabled = False
        self.init_database()

    def init_database(self):
        """初始化数据库表"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS email_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email_id INTEGER NOT NULL,
                        sender TEXT,
                        receiver TEXT,
                        subject TEXT,
                        subject_hash TEXT,
                        content TEXT,
                        content_hash TEXT,
                        message_id TEXT,
                        reply_to TEXT,
                        "references" TEXT,
                        in_reply_to TEXT,
                        update_time DATETIME,
                        create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(email_id, receiver)
                    )
                ''')

                self._ensure_email_records_columns(cursor)
                self._migrate_email_records_unique(cursor)

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS ticket_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email_records_id INTEGER NOT NULL,
                        status TEXT,
                        carrier_ticket_no TEXT,
                        cut_task_id TEXT,
                        cut_start_time DATETIME,
                        cut_end_time DATETIME,
                        update_time DATETIME,
                        create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (email_records_id) REFERENCES email_records(id)
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cutover_tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email_records_id INTEGER NOT NULL,
                        ticket_id INTEGER,
                        line_type TEXT NOT NULL DEFAULT 'customer',
                        supplier TEXT,
                        carrier_ticket_no TEXT,
                        title TEXT,
                        status TEXT NOT NULL DEFAULT 'draft',
                        fill_payload TEXT,
                        fill_result TEXT,
                        customer_excel_filename TEXT,
                        confirmed_at DATETIME,
                        create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        update_time DATETIME,
                        UNIQUE(email_records_id, line_type),
                        FOREIGN KEY (email_records_id) REFERENCES email_records(id),
                        FOREIGN KEY (ticket_id) REFERENCES ticket_records(id)
                    )
                ''')
                self._migrate_cutover_task_line_type(cursor)

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS cutover_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL,
                        report_type TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        result TEXT,
                        create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (task_id) REFERENCES cutover_tasks(id)
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        update_time DATETIME
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS mail_accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        email_address TEXT NOT NULL UNIQUE COLLATE NOCASE,
                        password_enc TEXT,
                        imap_server TEXT NOT NULL,
                        imap_port INTEGER NOT NULL DEFAULT 993,
                        imap_use_ssl INTEGER NOT NULL DEFAULT 1,
                        smtp_server TEXT,
                        smtp_port INTEGER NOT NULL DEFAULT 465,
                        smtp_use_ssl INTEGER NOT NULL DEFAULT 1,
                        smtp_use_tls INTEGER NOT NULL DEFAULT 0,
                        enabled INTEGER NOT NULL DEFAULT 1,
                        create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        update_time DATETIME
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS supplier_circuits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        supplier TEXT,
                        supplier_circuit_id TEXT,
                        circuit_id TEXT,
                        line_type TEXT,
                        line_status TEXT,
                        remark TEXT,
                        create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        update_time DATETIME
                    )
                ''')

                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_email_id ON email_records(email_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_email_subject_hash ON email_records(subject_hash)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_email_content_hash ON email_records(content_hash)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_email_create_time ON email_records(create_time)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_ticket_email_records_id ON ticket_records(email_records_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_ticket_carrier_ticket_no ON ticket_records(carrier_ticket_no)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_ticket_cut_task_id ON ticket_records(cut_task_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_cutover_task_status ON cutover_tasks(status)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_cutover_task_carrier_ticket_no ON cutover_tasks(carrier_ticket_no)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_cutover_report_task_id ON cutover_reports(task_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_supplier_circuits_supplier ON supplier_circuits(supplier)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_supplier_circuits_supplier_circuit_id ON supplier_circuits(supplier_circuit_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_mail_accounts_enabled ON mail_accounts(enabled)
                ''')

                conn.commit()
                logger.info(f"数据库初始化完成: {self.db_path}")

        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise

    def _ensure_email_records_columns(self, cursor):
        """为已有 SQLite 表补齐新增字段。"""
        cursor.execute("PRAGMA table_info(email_records)")
        existing_columns = {row["name"] for row in cursor.fetchall()}
        required_columns = {
            "message_id": "TEXT",
            "reply_to": "TEXT",
            "references": "TEXT",
            "in_reply_to": "TEXT",
            "html_content": "TEXT",
            "attachments": "TEXT",
            "cutover_scene": "TEXT DEFAULT 'normal'",
            "cutover_scene_remark": "TEXT NOT NULL DEFAULT ''",
            "mail_type": "TEXT NOT NULL DEFAULT ''",
            "extract_result": "TEXT NOT NULL DEFAULT ''",
            "is_duplicate": "INTEGER NOT NULL DEFAULT 0",
            "reply_status": "TEXT NOT NULL DEFAULT ''",
            "pending_reply_content": "TEXT NOT NULL DEFAULT ''",
            "pending_reply_scene": "TEXT NOT NULL DEFAULT ''",
            "reply_time": "TEXT NOT NULL DEFAULT ''",
        }

        for column_name, column_type in required_columns.items():
            if column_name not in existing_columns:
                cursor.execute(f'ALTER TABLE email_records ADD COLUMN "{column_name}" {column_type}')

        # is_duplicate 首次补列时回填存量重复邮件（入库时自动标记，查询直接读列）
        if "is_duplicate" not in existing_columns:
            cursor.execute(
                f"UPDATE email_records SET is_duplicate = 1 WHERE {DUPLICATE_EMAIL_EXISTS_SQL}"
            )

    def _migrate_email_records_unique(self, cursor):
        """旧版 UNIQUE(email_id) 迁移为 UNIQUE(email_id, receiver)，支持多邮箱 UID 并存。"""
        cursor.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'email_records'")
        row = cursor.fetchone()
        if not row or not row["sql"]:
            return
        table_sql = row["sql"]
        if not re.search(r"UNIQUE\s*\(\s*email_id\s*\)", table_sql):
            return

        logger.info("检测到 email_records 旧唯一约束 UNIQUE(email_id)，迁移为 UNIQUE(email_id, receiver)")
        new_sql = re.sub(
            r"UNIQUE\s*\(\s*email_id\s*\)",
            "UNIQUE(email_id, receiver)",
            table_sql,
        )
        new_sql = re.sub(
            r"CREATE TABLE( IF NOT EXISTS)? email_records",
            "CREATE TABLE email_records_new",
            new_sql,
            count=1,
        )
        cursor.execute(new_sql)

        cursor.execute("PRAGMA table_info(email_records)")
        columns = [col["name"] for col in cursor.fetchall()]
        quoted = ", ".join(f'"{c}"' for c in columns)
        cursor.execute(f"INSERT INTO email_records_new ({quoted}) SELECT {quoted} FROM email_records")
        cursor.execute("DROP TABLE email_records")
        cursor.execute("ALTER TABLE email_records_new RENAME TO email_records")
        logger.info("email_records 唯一约束迁移完成")

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            # busy_timeout 为连接级属性，每次连接都要设置；
            # WAL 为数据库文件级持久属性，只需首次启用，后续连接幂等跳过，
            # 避免多邮箱监听线程与 API 并发写入时出现 database is locked
            conn.execute("PRAGMA busy_timeout=5000")
            if not self._wal_enabled:
                cursor = conn.execute("PRAGMA journal_mode=WAL")
                mode = cursor.fetchone()[0]
                cursor.close()
                if str(mode).lower() == "wal":
                    self._wal_enabled = True
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            if conn:
                conn.close()

    @staticmethod
    def _hash_text(value: Optional[str]) -> Optional[str]:
        """计算文本 SHA-256，用于快速比对标题/正文是否重复。"""
        if value is None:
            return None
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _serialize_receiver(receiver: Any = None) -> Optional[str]:
        """收件人可能是列表，统一序列化成 JSON 文本保存。"""
        if receiver is None:
            return None
        if isinstance(receiver, str):
            return receiver
        return json.dumps(receiver, ensure_ascii=False)

    @staticmethod
    def _serialize_attachments(attachments: Optional[list[str]] = None) -> str:
        if not attachments:
            return "[]"
        return json.dumps(attachments, ensure_ascii=False)

    @staticmethod
    def deserialize_attachments(value: Any = None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if not isinstance(value, str) or not value.strip():
            return []
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, list):
            return []
        return [str(item) for item in parsed if item]

    @classmethod
    def _row_to_email_record(cls, row: sqlite3.Row) -> Dict[str, Any]:
        record = dict(row)
        record["attachments"] = cls.deserialize_attachments(record.get("attachments"))
        return record

    def add_email_record(
        self,
        email_id: int,
        sender: str = None,
        receiver: Any = None,
        subject: str = None,
        content: str = None,
        html_content: str = None,
        attachments: Optional[list[str]] = None,
        message_id: str = None,
        reply_to: str = None,
        references: str = None,
        in_reply_to: str = None,
    ) -> bool:
        """添加邮件记录，保存邮件基础信息和内容 hash。

        多邮箱监听后不同邮箱的 IMAP UID 可能相同，传入 receiver（账号地址）
        时按 (email_id, receiver) 判重；不传则沿用旧的全局 email_id 判重。
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                receiver_text = self._serialize_receiver(receiver)
                if receiver_text is not None:
                    cursor.execute(
                        'SELECT id FROM email_records WHERE email_id = ? AND receiver = ?',
                        (email_id, receiver_text),
                    )
                else:
                    cursor.execute('SELECT id FROM email_records WHERE email_id = ?', (email_id,))
                if cursor.fetchone():
                    logger.debug(f"邮件ID {email_id} (receiver={receiver_text}) 已存在，跳过添加")
                    return False

                subject_hash = self._hash_text(subject)
                content_hash = self._hash_text(content)
                now = datetime.now()

                cursor.execute('''
                    INSERT INTO email_records (
                        email_id, sender, receiver, subject, subject_hash,
                        content, content_hash, html_content, attachments,
                        message_id, reply_to,
                        "references", in_reply_to, create_time, update_time
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    email_id, sender, receiver_text, subject, subject_hash,
                    content, content_hash, html_content,
                    self._serialize_attachments(attachments),
                    message_id, reply_to,
                    references, in_reply_to, now, now,
                ))

                # 重复邮件标记：存在更早的同 subject_hash/content_hash 记录则置位
                if receiver_text is not None:
                    cursor.execute(
                        f"UPDATE email_records SET is_duplicate = 1 "
                        f"WHERE email_id = ? AND receiver = ? AND {DUPLICATE_EMAIL_EXISTS_SQL}",
                        (email_id, receiver_text),
                    )
                else:
                    cursor.execute(
                        f"UPDATE email_records SET is_duplicate = 1 "
                        f"WHERE email_id = ? AND {DUPLICATE_EMAIL_EXISTS_SQL}",
                        (email_id,),
                    )

                conn.commit()
                logger.info(f"成功添加邮件记录: email_id={email_id}")
                return True

        except sqlite3.IntegrityError:
            logger.debug(f"邮件ID {email_id} 已存在（唯一约束）")
            return False
        except Exception as e:
            logger.error(f"添加邮件记录失败: {e}")
            return False

    def update_email_record(
        self,
        email_id: int,
        sender: str = None,
        receiver: Any = None,
        subject: str = None,
        content: str = None,
        html_content: str = None,
        attachments: Optional[list[str]] = None,
        message_id: str = None,
        reply_to: str = None,
        references: str = None,
        in_reply_to: str = None,
    ) -> bool:
        """更新邮件记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                set_clauses = ["update_time = ?"]
                values = [datetime.now()]

                if sender is not None:
                    set_clauses.append("sender = ?")
                    values.append(sender)

                if receiver is not None:
                    set_clauses.append("receiver = ?")
                    values.append(self._serialize_receiver(receiver))

                if subject is not None:
                    set_clauses.append("subject = ?")
                    values.append(subject)
                    set_clauses.append("subject_hash = ?")
                    values.append(self._hash_text(subject))

                if content is not None:
                    set_clauses.append("content = ?")
                    values.append(content)
                    set_clauses.append("content_hash = ?")
                    values.append(self._hash_text(content))

                if html_content is not None:
                    set_clauses.append("html_content = ?")
                    values.append(html_content)

                if attachments is not None:
                    set_clauses.append("attachments = ?")
                    values.append(self._serialize_attachments(attachments))

                if message_id is not None:
                    set_clauses.append("message_id = ?")
                    values.append(message_id)

                if reply_to is not None:
                    set_clauses.append("reply_to = ?")
                    values.append(reply_to)

                if references is not None:
                    set_clauses.append('"references" = ?')
                    values.append(references)

                if in_reply_to is not None:
                    set_clauses.append("in_reply_to = ?")
                    values.append(in_reply_to)

                values.append(email_id)

                sql = f"UPDATE email_records SET {', '.join(set_clauses)} WHERE email_id = ?"
                cursor.execute(sql, values)

                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"成功更新邮件记录: email_id={email_id}")
                    return True

                logger.warning(f"未找到邮件记录: email_id={email_id}")
                return False

        except Exception as e:
            logger.error(f"更新邮件记录失败: {e}")
            return False

    def get_email_record(self, email_id: int) -> Optional[Dict[str, Any]]:
        """获取邮件记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM email_records WHERE email_id = ?', (email_id,))
                row = cursor.fetchone()
                return self._row_to_email_record(row) if row else None

        except Exception as e:
            logger.error(f"获取邮件记录失败: {e}")
            return None

    def get_email_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """根据 email_records 主键获取邮件记录。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM email_records WHERE id = ?', (record_id,))
                row = cursor.fetchone()
                return self._row_to_email_record(row) if row else None

        except Exception as e:
            logger.error(f"根据主键获取邮件记录失败: {e}")
            return None

    def update_email_record_cutover_scene(
        self, record_id: int, scene: str, scene_remark: str | None = None,
    ) -> bool:
        """按记录主键更新邮件记录的割接场景（FastGPT 回写）。

        scene_remark 传入时同步写入场景说明（如命中的特殊规则内容），
        不传则保持原备注不变。
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if scene_remark is None:
                    cursor.execute(
                        'UPDATE email_records SET cutover_scene = ? WHERE id = ?',
                        (scene, record_id),
                    )
                else:
                    cursor.execute(
                        'UPDATE email_records SET cutover_scene = ?, cutover_scene_remark = ? WHERE id = ?',
                        (scene, scene_remark, record_id),
                    )
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"更新邮件割接场景失败: {e}")
            return False

    def save_pending_reply(
        self, record_id: int, reply_content: str, cutover_scene: str = '',
    ) -> bool:
        """登记待人工确认的回复草稿（/api/cutover/reply 只落库不发送）。

        重复调用视为覆盖上一次的草稿，状态重置为 pending。
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE email_records SET reply_status = ?, pending_reply_content = ?, '
                    'pending_reply_scene = ?, reply_time = \'\' WHERE id = ?',
                    ('pending', reply_content or '', cutover_scene or '', record_id),
                )
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"登记待确认回复失败: {e}")
            return False

    def mark_reply_sent(self, record_id: int, reply_time: str) -> bool:
        """确认发送成功后标记回复状态（保留草稿内容与场景供回溯）。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE email_records SET reply_status = ?, reply_time = ? WHERE id = ?',
                    ('sent', reply_time, record_id),
                )
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"标记回复已发送失败: {e}")
            return False

    def cancel_pending_reply(self, record_id: int) -> bool:
        """放弃待确认回复：清空草稿内容与场景。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE email_records SET reply_status = ?, pending_reply_content = \'\', '
                    'pending_reply_scene = \'\', reply_time = \'\' WHERE id = ?',
                    ('cancelled', record_id),
                )
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"取消待确认回复失败: {e}")
            return False

    def update_email_record_mail_type(self, record_id: int, mail_type: str) -> bool:
        """按记录主键更新邮件分类类型（解析 FastGPT 返回值后回写）。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE email_records SET mail_type = ? WHERE id = ?',
                    (mail_type or '', record_id),
                )
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"更新邮件类型失败: {e}")
            return False

    def update_email_record_extract_result(self, record_id: int, extract_result: str) -> bool:
        """按记录主键保存提取解析结果（FastGPT 转发返回的原始文本）。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE email_records SET extract_result = ? WHERE id = ?',
                    (extract_result or '', record_id),
                )
                conn.commit()
                return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"保存提取解析结果失败: {e}")
            return False

    def email_exists(self, email_id: int, receiver: Optional[str] = None) -> bool:
        """检查邮件是否已处理。传入 receiver 时按 (email_id, receiver) 判重。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if receiver:
                    cursor.execute(
                        'SELECT 1 FROM email_records WHERE email_id = ? AND receiver = ?',
                        (email_id, receiver),
                    )
                else:
                    cursor.execute('SELECT 1 FROM email_records WHERE email_id = ?', (email_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查邮件是否存在失败: {e}")
            return False

    def get_email_records(
        self,
        limit: int = 100,
        offset: int = 0,
        sender: str = None,
    ) -> List[Dict[str, Any]]:
        """获取邮件记录列表"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                conditions = []
                params = []

                if sender:
                    conditions.append("sender LIKE ?")
                    params.append(f"%{sender}%")

                where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

                sql = f'''
                    SELECT * FROM email_records
                    {where_clause}
                    ORDER BY create_time DESC
                    LIMIT ? OFFSET ?
                '''

                params.extend([limit, offset])
                cursor.execute(sql, params)

                rows = cursor.fetchall()
                return [self._row_to_email_record(row) for row in rows]

        except Exception as e:
            logger.error(f"获取邮件记录列表失败: {e}")
            return []

    def find_duplicate_email_record(self, email_id: int) -> Optional[Dict[str, Any]]:
        """按 subject_hash 和 content_hash 查找不同 UID 的重复邮件。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT duplicate.*
                    FROM email_records AS current
                    JOIN email_records AS duplicate
                      ON duplicate.subject_hash = current.subject_hash
                     AND duplicate.content_hash = current.content_hash
                     AND duplicate.email_id != current.email_id
                    WHERE current.email_id = ?
                      AND current.subject_hash IS NOT NULL
                      AND current.content_hash IS NOT NULL
                    ORDER BY duplicate.create_time ASC
                    LIMIT 1
                ''', (email_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error(f"查找重复邮件失败: {e}")
            return None

    def add_ticket_record(
        self,
        email_records_id: int,
        carrier_ticket_no: str,
        cut_start_time: datetime,
        cut_end_time: datetime,
        status: str = None,
        cut_task_id: str = None,
    ) -> Optional[int]:
        """新增工单记录。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('SELECT id FROM email_records WHERE id = ?', (email_records_id,))
                if not cursor.fetchone():
                    logger.warning(f"未找到邮件记录主键: id={email_records_id}")
                    return None

                now = datetime.now()
                cursor.execute('''
                    INSERT INTO ticket_records (
                        email_records_id, status, carrier_ticket_no, cut_task_id,
                        cut_start_time, cut_end_time, create_time, update_time
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    email_records_id, status, carrier_ticket_no, cut_task_id,
                    cut_start_time, cut_end_time, now, now,
                ))

                ticket_id = cursor.lastrowid
                conn.commit()
                logger.info(
                    f"成功添加工单记录: id={ticket_id}, "
                    f"email_records_id={email_records_id}, carrier_ticket_no={carrier_ticket_no}"
                )
                return ticket_id

        except Exception as e:
            logger.error(f"添加工单记录失败: {e}")
            return None

    def find_duplicate_ticket_record(
        self,
        carrier_ticket_no: str,
        cut_start_time: datetime,
        cut_end_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        """按运营商单号和割接起止时间查找重复工单。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT *
                    FROM ticket_records
                    WHERE carrier_ticket_no = ?
                      AND cut_start_time = ?
                      AND cut_end_time = ?
                    ORDER BY create_time ASC
                    LIMIT 1
                ''', (carrier_ticket_no, cut_start_time, cut_end_time))
                row = cursor.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error(f"查找重复工单失败: {e}")
            return None

    def get_ticket_record(self, ticket_id: int) -> Optional[Dict[str, Any]]:
        """获取工单记录。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM ticket_records WHERE id = ?', (ticket_id,))
                row = cursor.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error(f"获取工单记录失败: {e}")
            return None

    @staticmethod
    def _migrate_cutover_task_line_type(cursor):
        """旧版 cutover_tasks 表（无 line_type、邮件唯一）迁移为按类型拆分的新表。"""
        cursor.execute("PRAGMA table_info(cutover_tasks)")
        columns = {row['name'] for row in cursor.fetchall()}
        if not columns or 'line_type' in columns:
            return

        logger.info("检测到旧版 cutover_tasks 表，开始迁移 line_type 字段")
        cursor.execute('''
            CREATE TABLE cutover_tasks_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email_records_id INTEGER NOT NULL,
                ticket_id INTEGER,
                line_type TEXT NOT NULL DEFAULT 'customer',
                supplier TEXT,
                carrier_ticket_no TEXT,
                title TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                fill_payload TEXT,
                fill_result TEXT,
                customer_excel_filename TEXT,
                confirmed_at DATETIME,
                create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                update_time DATETIME,
                UNIQUE(email_records_id, line_type),
                FOREIGN KEY (email_records_id) REFERENCES email_records(id),
                FOREIGN KEY (ticket_id) REFERENCES ticket_records(id)
            )
        ''')

        cursor.execute('SELECT * FROM cutover_tasks')
        for row in cursor.fetchall():
            fill_result = json.loads(row['fill_result']) if row['fill_result'] else {}
            if not isinstance(fill_result, dict):
                fill_result = {}
            has_customer = bool(fill_result.get('circuits'))
            has_backbone = bool(fill_result.get('backbone_circuits'))
            line_types = []
            if has_customer or not has_backbone:
                line_types.append('customer')
            if has_backbone:
                line_types.append('backbone')

            for line_type in line_types:
                if line_type == 'backbone':
                    split_result = {
                        'title': fill_result.get('title'),
                        'backbone_circuits': fill_result.get('backbone_circuits') or [],
                        'validation_messages': fill_result.get('validation_messages') or [],
                        'cutStartTime': fill_result.get('cutStartTime'),
                        'cutEndTime': fill_result.get('cutEndTime'),
                    }
                    excel_filename = None
                else:
                    split_result = fill_result
                    excel_filename = row['customer_excel_filename']
                cursor.execute('''
                    INSERT INTO cutover_tasks_new (
                        email_records_id, ticket_id, line_type, supplier, carrier_ticket_no,
                        title, status, fill_payload, fill_result,
                        customer_excel_filename, confirmed_at, create_time, update_time
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['email_records_id'], row['ticket_id'], line_type,
                    row['supplier'], row['carrier_ticket_no'], row['title'],
                    row['status'], row['fill_payload'],
                    json.dumps(split_result, ensure_ascii=False),
                    excel_filename, row['confirmed_at'],
                    row['create_time'], row['update_time'],
                ))

        cursor.execute('DROP TABLE cutover_tasks')
        cursor.execute('ALTER TABLE cutover_tasks_new RENAME TO cutover_tasks')
        logger.info("cutover_tasks 表 line_type 迁移完成")

    @staticmethod
    def _serialize_json(value: Any) -> Optional[str]:
        """将 dict/list 序列化为 JSON 文本，已是字符串则原样保存。"""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _deserialize_json(value: Any) -> Any:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @classmethod
    def _row_to_cutover_task(cls, row: sqlite3.Row) -> Dict[str, Any]:
        task = dict(row)
        task['fill_payload'] = cls._deserialize_json(task.get('fill_payload'))
        task['fill_result'] = cls._deserialize_json(task.get('fill_result'))
        return task

    def upsert_cutover_task(
        self,
        email_records_id: int,
        line_type: str = 'customer',
        supplier: str = None,
        carrier_ticket_no: str = None,
        title: str = None,
        fill_payload: Any = None,
        fill_result: Any = None,
        customer_excel_filename: str = None,
        ticket_id: int = None,
    ) -> Optional[int]:
        """按邮件记录与线路类型创建或覆盖更新割接任务，状态重置为 draft。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('SELECT id FROM email_records WHERE id = ?', (email_records_id,))
                if not cursor.fetchone():
                    logger.warning(f"未找到邮件记录主键: id={email_records_id}")
                    return None

                now = datetime.now()
                payload_text = self._serialize_json(fill_payload)
                result_text = self._serialize_json(fill_result)

                cursor.execute(
                    'SELECT id FROM cutover_tasks WHERE email_records_id = ? AND line_type = ?',
                    (email_records_id, line_type),
                )
                existing = cursor.fetchone()

                if existing:
                    task_id = existing['id']
                    cursor.execute('''
                        UPDATE cutover_tasks
                        SET supplier = ?, carrier_ticket_no = ?, title = ?,
                            status = 'draft', fill_payload = ?, fill_result = ?,
                            customer_excel_filename = ?, ticket_id = ?,
                            confirmed_at = NULL, update_time = ?
                        WHERE id = ?
                    ''', (
                        supplier, carrier_ticket_no, title,
                        payload_text, result_text,
                        customer_excel_filename, ticket_id,
                        now, task_id,
                    ))
                else:
                    cursor.execute('''
                        INSERT INTO cutover_tasks (
                            email_records_id, ticket_id, line_type, supplier, carrier_ticket_no,
                            title, status, fill_payload, fill_result,
                            customer_excel_filename, create_time, update_time
                        )
                        VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)
                    ''', (
                        email_records_id, ticket_id, line_type, supplier, carrier_ticket_no,
                        title, payload_text, result_text,
                        customer_excel_filename, now, now,
                    ))
                    task_id = cursor.lastrowid

                conn.commit()
                logger.info(
                    f"保存割接任务成功: id={task_id}, email_records_id={email_records_id}, line_type={line_type}"
                )
                return task_id

        except Exception as e:
            logger.error(f"保存割接任务失败: {e}")
            return None

    def get_cutover_task(self, task_id: int) -> Optional[Dict[str, Any]]:
        """获取割接任务。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM cutover_tasks WHERE id = ?', (task_id,))
                row = cursor.fetchone()
                return self._row_to_cutover_task(row) if row else None

        except Exception as e:
            logger.error(f"获取割接任务失败: {e}")
            return None

    def list_cutover_tasks_by_email(self, email_records_id: int) -> List[Dict[str, Any]]:
        """根据邮件记录主键获取其全部割接任务。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM cutover_tasks WHERE email_records_id = ? ORDER BY line_type, id',
                    (email_records_id,),
                )
                return [self._row_to_cutover_task(row) for row in cursor.fetchall()]

        except Exception as e:
            logger.error(f"根据邮件获取割接任务失败: {e}")
            return []

    def delete_cutover_task(self, task_id: int) -> bool:
        """删除割接任务及其上报记录。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM cutover_reports WHERE task_id = ?', (task_id,))
                cursor.execute('DELETE FROM cutover_tasks WHERE id = ?', (task_id,))
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除割接任务成功: id={task_id}")
                    return True
                logger.warning(f"未找到割接任务: id={task_id}")
                return False

        except Exception as e:
            logger.error(f"删除割接任务失败: {e}")
            return False

    def update_cutover_task(self, task_id: int, **fields: Any) -> bool:
        """部分更新割接任务字段，JSON 字段自动序列化。"""
        allowed_columns = {
            'status', 'fill_payload', 'fill_result', 'customer_excel_filename',
            'ticket_id', 'supplier', 'carrier_ticket_no', 'title', 'confirmed_at',
            'line_type',
        }
        json_columns = {'fill_payload', 'fill_result'}
        set_clauses = []
        values = []

        for column, value in fields.items():
            if column not in allowed_columns:
                continue
            set_clauses.append(f'{column} = ?')
            values.append(self._serialize_json(value) if column in json_columns else value)

        if not set_clauses:
            return False

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                set_clauses.append('update_time = ?')
                values.append(datetime.now())
                values.append(task_id)
                cursor.execute(
                    f"UPDATE cutover_tasks SET {', '.join(set_clauses)} WHERE id = ?",
                    values,
                )
                if cursor.rowcount > 0:
                    conn.commit()
                    return True
                logger.warning(f"未找到割接任务: id={task_id}")
                return False

        except Exception as e:
            logger.error(f"更新割接任务失败: {e}")
            return False

    def add_cutover_report(
        self,
        task_id: int,
        report_type: str = None,
        status: str = 'pending',
        result: Any = None,
    ) -> Optional[int]:
        """新增割接上报记录。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('SELECT id FROM cutover_tasks WHERE id = ?', (task_id,))
                if not cursor.fetchone():
                    logger.warning(f"未找到割接任务: id={task_id}")
                    return None

                cursor.execute('''
                    INSERT INTO cutover_reports (task_id, report_type, status, result)
                    VALUES (?, ?, ?, ?)
                ''', (task_id, report_type, status, self._serialize_json(result)))

                report_id = cursor.lastrowid
                conn.commit()
                logger.info(f"新增割接上报记录: id={report_id}, task_id={task_id}")
                return report_id

        except Exception as e:
            logger.error(f"新增割接上报记录失败: {e}")
            return None

    def update_cutover_report(self, report_id: int, status: str = None, result: Any = None) -> bool:
        """更新割接上报记录状态与结果。"""
        set_clauses = []
        values = []
        if status is not None:
            set_clauses.append('status = ?')
            values.append(status)
        if result is not None:
            set_clauses.append('result = ?')
            values.append(self._serialize_json(result))
        if not set_clauses:
            return False

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                values.append(report_id)
                cursor.execute(
                    f"UPDATE cutover_reports SET {', '.join(set_clauses)} WHERE id = ?",
                    values,
                )
                if cursor.rowcount > 0:
                    conn.commit()
                    return True
                return False

        except Exception as e:
            logger.error(f"更新割接上报记录失败: {e}")
            return False

    def get_cutover_reports(self, task_id: int) -> List[Dict[str, Any]]:
        """获取某个任务的全部上报记录，按时间倒序。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM cutover_reports
                    WHERE task_id = ?
                    ORDER BY create_time DESC, id DESC
                ''', (task_id,))
                reports = []
                for row in cursor.fetchall():
                    report = dict(row)
                    report['result'] = self._deserialize_json(report.get('result'))
                    reports.append(report)
                return reports

        except Exception as e:
            logger.error(f"获取割接上报记录失败: {e}")
            return []

    def get_statistics(self) -> Dict[str, Any]:
        """获取邮件统计信息"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('SELECT COUNT(*) as total FROM email_records')
                total_emails = cursor.fetchone()['total']

                cursor.execute('''
                    SELECT COUNT(*) as today_count
                    FROM email_records
                    WHERE DATE(create_time) = DATE('now')
                ''')
                today_emails = cursor.fetchone()['today_count']

                cursor.execute('SELECT COUNT(*) as total FROM ticket_records')
                total_tickets = cursor.fetchone()['total']

                cursor.execute('''
                    SELECT COUNT(*) as today_count
                    FROM ticket_records
                    WHERE DATE(create_time) = DATE('now')
                ''')
                today_tickets = cursor.fetchone()['today_count']

                return {
                    'email_records': {
                        'total': total_emails,
                        'today': today_emails,
                    },
                    'ticket_records': {
                        'total': total_tickets,
                        'today': today_tickets,
                    }
                }

        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}

    def cleanup_old_records(self, days: int = 30) -> Dict[str, int]:
        """清理旧邮件记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute('''
                    DELETE FROM ticket_records
                    WHERE create_time < datetime('now', '-{} days')
                       OR email_records_id IN (
                           SELECT id FROM email_records
                           WHERE create_time < datetime('now', '-{} days')
                       )
                '''.format(days, days))
                deleted_tickets = cursor.rowcount

                cursor.execute('''
                    DELETE FROM email_records
                    WHERE create_time < datetime('now', '-{} days')
                '''.format(days))
                deleted_emails = cursor.rowcount

                conn.commit()

                if deleted_emails > 0 or deleted_tickets > 0:
                    logger.info(
                        f"清理了 {deleted_emails} 条邮件记录和 "
                        f"{deleted_tickets} 条工单记录（超过 {days} 天）"
                    )

                return {'emails': deleted_emails, 'tickets': deleted_tickets}

        except Exception as e:
            logger.error(f"清理旧记录失败: {e}")
            return {'emails': 0, 'tickets': 0}

    def count_kamonitor_alert_emails(self, start_time: str = None, end_time: str = None) -> int:
        """统计发件人包含 kamonitor2@sinnet.com.cn 的邮件数量。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                time_conditions = []
                params = []

                if start_time:
                    time_conditions.append("create_time >= ?")
                    params.append(start_time)

                if end_time:
                    time_conditions.append("create_time <= ?")
                    params.append(end_time)

                where_clause = "WHERE sender LIKE '%kamonitor2@sinnet.com.cn%'"

                if time_conditions:
                    where_clause += " AND " + " AND ".join(time_conditions)

                sql = f'''
                    SELECT COUNT(*) as count
                    FROM email_records
                    {where_clause}
                '''

                cursor.execute(sql, params)

                row = cursor.fetchone()
                return row['count'] if row else 0

        except Exception as e:
            logger.error(f"统计 kamonitor 邮件失败: {e}")
            return 0

    # ---------- 线路表（supplier_circuits） ----------

    SUPPLIER_CIRCUIT_COLUMNS = (
        'supplier', 'supplier_circuit_id', 'circuit_id',
        'line_type', 'line_status', 'remark',
    )

    @classmethod
    def _normalize_circuit_fields(cls, data: Dict[str, Any]) -> Dict[str, str]:
        """只保留线路表字段，统一转为去除首尾空白的字符串。"""
        normalized = {}
        for column in cls.SUPPLIER_CIRCUIT_COLUMNS:
            value = data.get(column)
            normalized[column] = str(value).strip() if value is not None else ''
        return normalized

    def count_supplier_circuits(self) -> int:
        """统计线路表总条数。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) AS total FROM supplier_circuits')
                row = cursor.fetchone()
                return row['total'] if row else 0
        except Exception as e:
            logger.error(f"统计线路表失败: {e}")
            return 0

    def get_supplier_circuit(self, circuit_pk: int) -> Optional[Dict[str, Any]]:
        """按主键获取单条线路。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM supplier_circuits WHERE id = ?', (circuit_pk,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"获取线路失败: {e}")
            return None

    def get_all_supplier_circuits(self) -> List[Dict[str, Any]]:
        """获取全部线路，供关键字匹配使用。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM supplier_circuits ORDER BY id')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取全部线路失败: {e}")
            return []

    def list_supplier_circuits(
        self,
        supplier: str = None,
        line_type: str = None,
        line_status: str = None,
        keyword: str = None,
        limit: int = None,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """分页查询线路列表，keyword 模糊匹配供应商编号/Circuit ID/备注。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                conditions = []
                params: List[Any] = []

                if supplier:
                    conditions.append('supplier = ?')
                    params.append(supplier)
                if line_type:
                    conditions.append('line_type = ?')
                    params.append(line_type)
                if line_status:
                    conditions.append('line_status = ?')
                    params.append(line_status)
                if keyword:
                    conditions.append(
                        '(supplier_circuit_id LIKE ? OR circuit_id LIKE ? OR remark LIKE ?)'
                    )
                    like_value = f'%{keyword}%'
                    params.extend([like_value, like_value, like_value])

                where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ''

                cursor.execute(
                    f'SELECT COUNT(*) AS total FROM supplier_circuits {where_clause}',
                    params,
                )
                total = cursor.fetchone()['total']

                sql = f'SELECT * FROM supplier_circuits {where_clause} ORDER BY id'
                if limit is not None:
                    sql += ' LIMIT ? OFFSET ?'
                    params.extend([limit, offset])
                cursor.execute(sql, params)

                return {'rows': [dict(row) for row in cursor.fetchall()], 'total': total}

        except Exception as e:
            logger.error(f"查询线路列表失败: {e}")
            return {'rows': [], 'total': 0}

    def supplier_circuit_options(self) -> Dict[str, List[str]]:
        """获取筛选下拉选项：供应商/类型/线路状态去重值。"""
        options = {'suppliers': [], 'line_types': [], 'line_statuses': []}
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                for column, key in (
                    ('supplier', 'suppliers'),
                    ('line_type', 'line_types'),
                    ('line_status', 'line_statuses'),
                ):
                    cursor.execute(
                        f"SELECT DISTINCT {column} AS value FROM supplier_circuits "
                        f"WHERE {column} IS NOT NULL AND {column} != '' ORDER BY value"
                    )
                    options[key] = [row['value'] for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"获取线路筛选选项失败: {e}")
        return options

    def create_supplier_circuit(self, data: Dict[str, Any]) -> Optional[int]:
        """新增一条线路。"""
        try:
            fields = self._normalize_circuit_fields(data)
            now = datetime.now()
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO supplier_circuits (
                        supplier, supplier_circuit_id, circuit_id,
                        line_type, line_status, remark, create_time, update_time
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    fields['supplier'], fields['supplier_circuit_id'], fields['circuit_id'],
                    fields['line_type'], fields['line_status'], fields['remark'], now, now,
                ))
                circuit_pk = cursor.lastrowid
                conn.commit()
                logger.info(f"新增线路成功: id={circuit_pk}, supplier_circuit_id={fields['supplier_circuit_id']}")
                return circuit_pk
        except Exception as e:
            logger.error(f"新增线路失败: {e}")
            return None

    def update_supplier_circuit(self, circuit_pk: int, data: Dict[str, Any]) -> bool:
        """更新一条线路，仅更新传入的字段。"""
        try:
            set_clauses = []
            values: List[Any] = []
            for column in self.SUPPLIER_CIRCUIT_COLUMNS:
                if column not in data:
                    continue
                value = data[column]
                set_clauses.append(f'{column} = ?')
                values.append(str(value).strip() if value is not None else '')

            if not set_clauses:
                return False

            with self.get_connection() as conn:
                cursor = conn.cursor()
                set_clauses.append('update_time = ?')
                values.append(datetime.now())
                values.append(circuit_pk)
                cursor.execute(
                    f"UPDATE supplier_circuits SET {', '.join(set_clauses)} WHERE id = ?",
                    values,
                )
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新线路成功: id={circuit_pk}")
                    return True
                logger.warning(f"未找到线路: id={circuit_pk}")
                return False
        except Exception as e:
            logger.error(f"更新线路失败: {e}")
            return False

    def delete_supplier_circuit(self, circuit_pk: int) -> bool:
        """删除一条线路。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM supplier_circuits WHERE id = ?', (circuit_pk,))
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除线路成功: id={circuit_pk}")
                    return True
                logger.warning(f"未找到线路: id={circuit_pk}")
                return False
        except Exception as e:
            logger.error(f"删除线路失败: {e}")
            return False

    def replace_all_supplier_circuits(self, rows: List[Dict[str, Any]]) -> int:
        """全量替换线路表：同一事务内清空后批量写入，返回写入条数。"""
        try:
            now = datetime.now()
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM supplier_circuits')
                for row in rows:
                    fields = self._normalize_circuit_fields(row)
                    cursor.execute('''
                        INSERT INTO supplier_circuits (
                            supplier, supplier_circuit_id, circuit_id,
                            line_type, line_status, remark, create_time, update_time
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        fields['supplier'], fields['supplier_circuit_id'], fields['circuit_id'],
                        fields['line_type'], fields['line_status'], fields['remark'], now, now,
                    ))
                conn.commit()
                logger.info(f"全量替换线路表成功: 共 {len(rows)} 条")
                return len(rows)
        except Exception as e:
            logger.error(f"全量替换线路表失败: {e}")
            raise

    # ---------- 系统配置（key-value） ----------

    def get_system_settings(self) -> Dict[str, Optional[str]]:
        """读取全部系统配置，返回 {key: value} 字典。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT key, value FROM system_settings')
                return {row["key"]: row["value"] for row in cursor.fetchall()}
        except Exception as e:
            logger.error(f"读取系统配置失败: {e}")
            return {}

    def set_system_setting(self, key: str, value: Optional[str]) -> None:
        """写入一条系统配置，已存在则更新。value 为 None 表示清空。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO system_settings (key, value, update_time)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        update_time = excluded.update_time
                ''', (key, value, datetime.now()))
                conn.commit()
        except Exception as e:
            logger.error(f"写入系统配置失败: {e}")
            raise

    # ---------- 邮箱账号配置 ----------

    _MAIL_ACCOUNT_FIELDS = (
        "name", "email_address", "password_enc", "imap_server", "imap_port",
        "imap_use_ssl", "smtp_server", "smtp_port", "smtp_use_ssl",
        "smtp_use_tls", "enabled",
    )

    def list_mail_accounts(self) -> List[Dict[str, Any]]:
        """按创建顺序返回全部邮箱账号。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM mail_accounts ORDER BY id')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"查询邮箱账号列表失败: {e}")
            return []

    def get_last_email_time_by_receiver(self, receiver: str) -> Optional[str]:
        """返回该接收邮箱最近一条邮件记录的入库时间，无记录返回 None。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT MAX(create_time) AS last_time FROM email_records WHERE receiver = ?',
                    (receiver,),
                )
                row = cursor.fetchone()
                return row['last_time'] if row else None
        except Exception as e:
            logger.error(f"查询最后收件时间失败: {e}")
            return None

    def get_mail_account(self, account_id: int) -> Optional[Dict[str, Any]]:
        """按主键获取邮箱账号。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM mail_accounts WHERE id = ?', (account_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"获取邮箱账号失败: {e}")
            return None

    def get_mail_account_by_address(self, email_address: str) -> Optional[Dict[str, Any]]:
        """按邮箱地址（忽略大小写）获取账号。"""
        if not email_address:
            return None
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT * FROM mail_accounts WHERE lower(email_address) = lower(?)',
                    (email_address.strip(),),
                )
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"按地址获取邮箱账号失败: {e}")
            return None

    def add_mail_account(self, fields: Dict[str, Any]) -> Optional[int]:
        """新增邮箱账号，返回主键；地址重复或字段缺失时返回 None。"""
        missing = [k for k in ("email_address", "imap_server") if not fields.get(k)]
        if missing:
            logger.error(f"新增邮箱账号缺少必填字段: {missing}")
            return None
        defaults = {
            "name": "",
            "password_enc": "",
            "imap_port": 993,
            "imap_use_ssl": 1,
            "smtp_server": "",
            "smtp_port": 465,
            "smtp_use_ssl": 1,
            "smtp_use_tls": 0,
            "enabled": 1,
        }
        try:
            now = datetime.now()
            # 显式 INSERT 会绕过列默认值，未传字段统一补默认
            values = [fields.get(k, defaults.get(k)) for k in self._MAIL_ACCOUNT_FIELDS]
            placeholders = ", ".join("?" for _ in self._MAIL_ACCOUNT_FIELDS)
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f'INSERT INTO mail_accounts ({", ".join(self._MAIL_ACCOUNT_FIELDS)}, '
                    f'create_time, update_time) VALUES ({placeholders}, ?, ?)',
                    (*values, now, now),
                )
                conn.commit()
                account_id = cursor.lastrowid
                logger.info(f"新增邮箱账号成功: id={account_id}, address={fields.get('email_address')}")
                return account_id
        except sqlite3.IntegrityError:
            logger.error(f"邮箱账号已存在: {fields.get('email_address')}")
            return None
        except Exception as e:
            logger.error(f"新增邮箱账号失败: {e}")
            return None

    def update_mail_account(self, account_id: int, fields: Dict[str, Any]) -> bool:
        """更新邮箱账号，fields 仅包含需要更新的字段；地址冲突或账号不存在返回 False。"""
        update_fields = {k: v for k, v in fields.items() if k in self._MAIL_ACCOUNT_FIELDS}
        if not update_fields:
            return False
        try:
            set_clauses = [f"{k} = ?" for k in update_fields]
            values = list(update_fields.values())
            values.append(datetime.now())
            values.append(account_id)
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f'UPDATE mail_accounts SET {", ".join(set_clauses)}, update_time = ? '
                    f'WHERE id = ?',
                    values,
                )
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"更新邮箱账号成功: id={account_id}")
                    return True
                logger.warning(f"未找到邮箱账号: id={account_id}")
                return False
        except sqlite3.IntegrityError:
            logger.error(f"邮箱账号地址冲突: id={account_id}, address={update_fields.get('email_address')}")
            return False
        except Exception as e:
            logger.error(f"更新邮箱账号失败: {e}")
            return False

    def delete_mail_account(self, account_id: int) -> bool:
        """删除邮箱账号。"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM mail_accounts WHERE id = ?', (account_id,))
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"删除邮箱账号成功: id={account_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"删除邮箱账号失败: {e}")
            return False


# 全局数据库实例
email_db = EmailDatabase()