import os
import sqlite3
import tempfile
import unittest

from database import EmailDatabase


class EmailDatabaseTest(unittest.TestCase):
    def test_add_email_record_stores_reply_headers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "mail_listener.db")
            db = EmailDatabase(db_path)

            added = db.add_email_record(
                email_id=1,
                sender="sender@example.com",
                receiver="receiver@example.com",
                subject="Reply headers",
                content="hello",
                html_content="<p>hello</p>",
                attachments=[
                    "email_attachments/1/a.txt",
                    "email_attachments/1/b.xlsx",
                ],
                message_id="<message-1@example.com>",
                reply_to="support@example.com",
                references="<root@example.com> <parent@example.com>",
                in_reply_to="<parent@example.com>",
            )

            self.assertTrue(added)
            record = db.get_email_record(1)
            self.assertEqual(record["message_id"], "<message-1@example.com>")
            self.assertEqual(record["content"], "hello")
            self.assertEqual(record["html_content"], "<p>hello</p>")
            self.assertEqual(record["attachments"], [
                "email_attachments/1/a.txt",
                "email_attachments/1/b.xlsx",
            ])
            self.assertEqual(record["reply_to"], "support@example.com")
            self.assertEqual(record["references"], "<root@example.com> <parent@example.com>")
            self.assertEqual(record["in_reply_to"], "<parent@example.com>")

    def test_update_cutover_scene_targets_record_primary_key(self):
        """场景写入必须按记录主键定位，不能误按 IMAP UID（email_id）匹配。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(os.path.join(tmpdir, "mail_listener.db"))

            # 第一封：UID 故意设为与第二封记录主键相同的值，制造 ID 碰撞
            db.add_email_record(email_id=2, sender="a@example.com", receiver="r@example.com",
                                subject="s1", content="c1")
            db.add_email_record(email_id=9999, sender="b@example.com", receiver="r@example.com",
                                subject="s2", content="c2")
            target = db.get_email_record(9999)

            updated = db.update_email_record_cutover_scene(target["id"], "major_event")

            self.assertTrue(updated)
            self.assertEqual(db.get_email_record_by_id(target["id"])["cutover_scene"], "major_event")
            # 碰撞的 UID=2 那封不应被误写
            self.assertEqual(db.get_email_record(2)["cutover_scene"], "normal")
            # 主键不存在时返回 False
            self.assertFalse(db.update_email_record_cutover_scene(999999, "emergency"))

    def test_add_email_record_marks_duplicate_flag(self):
        """入库时自动标记重复邮件：后到的同主题同正文邮件 is_duplicate=1，首封不标记。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(os.path.join(tmpdir, "mail_listener.db"))

            db.add_email_record(email_id=1, sender="s@example.com", receiver="r@example.com",
                                subject="割接通知", content="正文")
            db.add_email_record(email_id=2, sender="s@example.com", receiver="r@example.com",
                                subject="割接通知", content="正文")
            db.add_email_record(email_id=3, sender="s@example.com", receiver="r@example.com",
                                subject="另一封", content="不同正文")

            self.assertEqual(db.get_email_record(1)["is_duplicate"], 0)
            self.assertEqual(db.get_email_record(2)["is_duplicate"], 1)
            self.assertEqual(db.get_email_record(3)["is_duplicate"], 0)

    def test_is_duplicate_backfilled_when_column_added(self):
        """存量库补 is_duplicate 列时应回填已存在的重复邮件标记。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "mail_listener.db")
            # 模拟旧库：无 is_duplicate 列，已存在两封同 hash 邮件
            conn = sqlite3.connect(db_path)
            conn.execute('''
                CREATE TABLE email_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id INTEGER NOT NULL,
                    sender TEXT, receiver TEXT, subject TEXT, subject_hash TEXT,
                    content TEXT, content_hash TEXT,
                    update_time DATETIME,
                    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(email_id)
                )
            ''')
            conn.execute(
                "INSERT INTO email_records (email_id, sender, subject, subject_hash, content, content_hash, create_time) "
                "VALUES (1, 's@example.com', '割接通知', 'h1', '正文', 'h2', '2026-08-20 10:00:00')")
            conn.execute(
                "INSERT INTO email_records (email_id, sender, subject, subject_hash, content, content_hash, create_time) "
                "VALUES (2, 's@example.com', '割接通知', 'h1', '正文', 'h2', '2026-08-20 11:00:00')")
            conn.commit()
            conn.close()

            # 实例化触发补列与回填
            db = EmailDatabase(db_path)

            self.assertEqual(db.get_email_record(1)["is_duplicate"], 0)
            self.assertEqual(db.get_email_record(2)["is_duplicate"], 1)

    def test_email_records_unique_scoped_by_receiver(self):
        """多邮箱场景：不同 receiver 的相同 UID 可并存，同 receiver 同 UID 拒绝。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(os.path.join(tmpdir, "mail_listener.db"))

            self.assertTrue(db.add_email_record(
                email_id=100, sender="s@example.com", receiver="box-a@example.com",
                subject="A邮箱邮件", content="a"))
            # 相同 UID、不同邮箱账号：应可并存
            self.assertTrue(db.add_email_record(
                email_id=100, sender="s@example.com", receiver="box-b@example.com",
                subject="B邮箱邮件", content="b"))
            # 相同 UID、相同邮箱账号：应拒绝
            self.assertFalse(db.add_email_record(
                email_id=100, sender="s@example.com", receiver="box-a@example.com",
                subject="重复邮件", content="dup"))

            # email_exists 按账号隔离
            self.assertTrue(db.email_exists(100, receiver="box-a@example.com"))
            self.assertTrue(db.email_exists(100, receiver="box-b@example.com"))
            self.assertFalse(db.email_exists(100, receiver="box-c@example.com"))
            # 不传 receiver 沿用全局判重（兼容存量路径）
            self.assertTrue(db.email_exists(100))
            self.assertFalse(db.email_exists(200))

    def test_legacy_db_migrates_email_id_unique_to_receiver_scoped(self):
        """存量库 UNIQUE(email_id) 应自动迁移为 UNIQUE(email_id, receiver) 且数据不丢。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "mail_listener.db")
            conn = sqlite3.connect(db_path)
            conn.execute('''
                CREATE TABLE email_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id INTEGER NOT NULL,
                    sender TEXT, receiver TEXT, subject TEXT, subject_hash TEXT,
                    content TEXT, content_hash TEXT,
                    update_time DATETIME,
                    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(email_id)
                )
            ''')
            conn.execute(
                "INSERT INTO email_records (email_id, sender, receiver, subject, subject_hash, content, content_hash) "
                "VALUES (1, 's@example.com', 'r@example.com', '存量邮件', 'h1', '正文', 'h2')")
            conn.commit()
            conn.close()

            db = EmailDatabase(db_path)

            # 迁移后存量数据完好
            record = db.get_email_record(1)
            self.assertEqual(record["subject"], "存量邮件")

            # 迁移后同 UID 不同账号可写入
            self.assertTrue(db.add_email_record(
                email_id=1, sender="s@example.com", receiver="other@example.com",
                subject="新邮箱同UID", content="x"))

            # 表结构已更新
            conn = sqlite3.connect(db_path)
            table_sql = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='email_records'"
            ).fetchone()[0]
            conn.close()
            self.assertIn("UNIQUE(email_id, receiver)", table_sql)

    def test_mail_account_crud(self):
        """邮箱账号增删改查与地址唯一约束。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(os.path.join(tmpdir, "mail_listener.db"))

            account_id = db.add_mail_account({
                "name": "值班邮箱",
                "email_address": "noc@example.com",
                "password_enc": "encrypted-token",
                "imap_server": "imap.example.com",
                "imap_port": 993,
                "imap_use_ssl": 1,
                "smtp_server": "smtp.example.com",
                "smtp_port": 465,
                "smtp_use_ssl": 1,
                "smtp_use_tls": 0,
                "enabled": 1,
            })
            self.assertIsNotNone(account_id)

            # 地址重复拒绝
            self.assertIsNone(db.add_mail_account({
                "name": "重复",
                "email_address": "NOC@example.com",  # 大小写不同也应撞库
                "imap_server": "imap.example.com",
            }))

            # 按主键/地址查询（地址忽略大小写）
            row = db.get_mail_account(account_id)
            self.assertEqual(row["email_address"], "noc@example.com")
            self.assertEqual(db.get_mail_account_by_address("noc@EXAMPLE.com")["id"], account_id)
            self.assertIsNone(db.get_mail_account_by_address("missing@example.com"))

            # 部分字段更新
            self.assertTrue(db.update_mail_account(account_id, {"enabled": 0, "imap_port": 1993}))
            row = db.get_mail_account(account_id)
            self.assertEqual(row["enabled"], 0)
            self.assertEqual(row["imap_port"], 1993)
            self.assertEqual(row["name"], "值班邮箱")  # 未传字段保持

            # 更新地址与其他账号冲突时返回 False
            second_id = db.add_mail_account({
                "name": "第二个",
                "email_address": "backup@example.com",
                "imap_server": "imap.example.com",
            })
            self.assertFalse(db.update_mail_account(second_id, {"email_address": "noc@example.com"}))

            # 列表与删除
            self.assertEqual(len(db.list_mail_accounts()), 2)
            self.assertTrue(db.delete_mail_account(account_id))
            self.assertFalse(db.delete_mail_account(account_id))
            self.assertEqual(len(db.list_mail_accounts()), 1)


if __name__ == "__main__":
    unittest.main()
