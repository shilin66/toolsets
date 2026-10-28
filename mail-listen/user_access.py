"""User identity and mailbox grants; business records keep their existing IDs."""

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from werkzeug.security import check_password_hash, generate_password_hash

if TYPE_CHECKING:
    from database import EmailDatabase


@dataclass(frozen=True)
class Principal:
    user_id: int | None
    username: str
    display_name: str
    is_admin: bool = False

    @classmethod
    def admin(cls):
        return cls(None, 'admin', '管理员', True)

    @property
    def key(self) -> str:
        return 'admin' if self.is_admin else f'user-{self.user_id}'

    def public(self) -> dict:
        return {'id': self.user_id, 'username': self.username,
                'display_name': self.display_name, 'is_admin': self.is_admin}


def initialize_access_storage(cursor) -> None:
    for statement in (
        '''CREATE TABLE IF NOT EXISTS app_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            display_name TEXT NOT NULL, password_hash TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''',
        '''CREATE TABLE IF NOT EXISTS user_mailbox_grants (
            user_id INTEGER NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES mail_accounts(id) ON DELETE CASCADE,
            can_operate INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(user_id, account_id))''',
        '''CREATE TABLE IF NOT EXISTS user_sessions (
            token_hash TEXT PRIMARY KEY, user_id INTEGER REFERENCES app_users(id),
            admin_key_hash TEXT, csrf_token TEXT NOT NULL, expires_at REAL NOT NULL)''',
        '''CREATE INDEX IF NOT EXISTS idx_user_sessions_expiry ON user_sessions(expires_at)''',
        '''CREATE TABLE IF NOT EXISTS auth_login_attempts (
            bucket TEXT PRIMARY KEY, failures INTEGER NOT NULL,
            window_started REAL NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS portal_sessions (
            principal_key TEXT NOT NULL, environment TEXT NOT NULL,
            username TEXT NOT NULL, account_key TEXT NOT NULL,
            version TEXT NOT NULL, state_path TEXT NOT NULL,
            PRIMARY KEY(principal_key,environment), UNIQUE(environment,account_key))''',
        '''CREATE TABLE IF NOT EXISTS rpa_report_jobs (
            report_id INTEGER PRIMARY KEY, principal_key TEXT NOT NULL,
            user_id INTEGER, username TEXT NOT NULL, environment TEXT NOT NULL,
            session_version TEXT NOT NULL, state_path TEXT NOT NULL,
            task_snapshot TEXT NOT NULL, settings_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending')''',
        '''CREATE TABLE IF NOT EXISTS supplier_sample_access (
            supplier_id INTEGER PRIMARY KEY, owner_user_id INTEGER,
            source_email_ids TEXT NOT NULL DEFAULT '[]')''',
    ):
        cursor.execute(statement)
    # Keep published sample provenance even after its draft is deleted.
    published = cursor.execute('''SELECT published_supplier_id, source_email_records_id, id
        FROM supplier_drafts WHERE published_supplier_id IS NOT NULL''').fetchall()
    for draft in published:
        sources = {row[0] for row in cursor.execute(
            'SELECT email_records_id FROM supplier_draft_samples WHERE draft_id=?', (draft[2],)).fetchall()}
        if draft[1] is not None:
            sources.add(draft[1])
        cursor.execute('INSERT OR IGNORE INTO supplier_sample_access VALUES (?,NULL,?)',
                       (draft[0], json.dumps(sorted(sources))))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class UserAccessRepository:
    def __init__(self, db: 'EmailDatabase'):
        self.db = db

    @staticmethod
    def _user(row) -> dict:
        return {key: row[key] for key in ('id', 'username', 'display_name', 'enabled', 'created_at')}

    def create_user(self, username: str, password: str, display_name: str = '') -> dict:
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{2,64}', username.strip()):
            raise ValueError('用户名需为 2–64 位字母、数字、点、下划线或短横线')
        if not isinstance(password, str) or not 10 <= len(password) <= 128:
            raise ValueError('密码长度需为 10–128 位')
        if not isinstance(display_name, str) or len(display_name.strip()) > 80:
            raise ValueError('显示名称不能超过 80 个字符')
        username = username.strip()
        password_hash = generate_password_hash(password, method='scrypt')
        try:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    'INSERT INTO app_users(username,display_name,password_hash) VALUES (?,?,?)',
                    (username, display_name.strip() or username, password_hash),
                )
                row = conn.execute('SELECT * FROM app_users WHERE id=?', (cursor.lastrowid,)).fetchone()
                conn.commit()
                return self._user(row)
        except sqlite3.IntegrityError as error:
            raise ValueError('该用户名已存在') from error

    def list_users(self) -> list[dict]:
        with self.db.get_connection() as conn:
            return [self._user(row) for row in conn.execute('SELECT * FROM app_users ORDER BY id')]

    def update_user(self, user_id, body):
        values, fields = [], []
        if not isinstance(body, dict):
            raise ValueError('用户设置无效')
        if 'enabled' in body:
            if type(body['enabled']) is not bool:
                raise ValueError('enabled 必须为布尔值')
            fields.append('enabled=?')
            values.append(int(body['enabled']))
        if 'password' in body:
            password = body['password']
            if not isinstance(password, str) or not 10 <= len(password) <= 128:
                raise ValueError('密码长度需为 10–128 位')
            fields.append('password_hash=?')
            values.append(generate_password_hash(password, method='scrypt'))
        if not fields:
            raise ValueError('请选择启用状态或提供新密码')
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            cursor = conn.execute(f"UPDATE app_users SET {','.join(fields)} WHERE id=?", [*values, user_id])
            if not cursor.rowcount:
                raise ValueError('用户不存在')
            conn.execute('DELETE FROM user_sessions WHERE user_id=?', (user_id,))
            conn.commit()

    def get_principal(self, user_id: int) -> Principal | None:
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM app_users WHERE id=? AND enabled=1', (user_id,)).fetchone()
        return Principal(row['id'], row['username'], row['display_name']) if row else None

    def verify_user(self, username: str, password: str) -> Principal | None:
        if not isinstance(username, str) or not isinstance(password, str) or len(password) > 128:
            return None
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM app_users WHERE username=? AND enabled=1', (username.strip(),)).fetchone()
        if row and check_password_hash(row['password_hash'], password):
            return Principal(row['id'], row['username'], row['display_name'])
        return None

    def create_session(self, principal: Principal, admin_key: str) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = time.time()
        with self.db.get_connection() as conn:
            conn.execute('DELETE FROM user_sessions WHERE expires_at <= ?', (now,))
            conn.execute('INSERT INTO user_sessions VALUES (?,?,?,?,?)', (
                _digest(token), principal.user_id,
                _digest(admin_key) if principal.is_admin else None, csrf, now + 12 * 3600,
            ))
            conn.commit()
        return token, csrf

    def resolve_session(self, token: str, admin_key: str) -> tuple[Principal, str] | None:
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM user_sessions WHERE token_hash=? AND expires_at>?',
                               (_digest(token), time.time())).fetchone()
        if row is None:
            return None
        if row['admin_key_hash']:
            if not admin_key or not hmac.compare_digest(row['admin_key_hash'], _digest(admin_key)):
                return None
            principal = Principal.admin()
        else:
            principal = self.get_principal(row['user_id'])
        return (principal, row['csrf_token']) if principal else None

    def revoke_session(self, token: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute('DELETE FROM user_sessions WHERE token_hash=?', (_digest(token),))
            conn.commit()

    def record_login_attempt(self, remote_address: str, *, success: bool = False) -> bool:
        bucket, now = _digest(remote_address), time.time()
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('DELETE FROM auth_login_attempts WHERE window_started<?', (now - 300,))
            if success:
                conn.execute('DELETE FROM auth_login_attempts WHERE bucket=?', (bucket,))
                conn.commit()
                return True
            row = conn.execute('SELECT failures FROM auth_login_attempts WHERE bucket=?', (bucket,)).fetchone()
            if row and row['failures'] >= 20:
                return False
            conn.execute('''INSERT INTO auth_login_attempts VALUES (?,1,?)
                ON CONFLICT(bucket) DO UPDATE SET failures=failures+1''', (bucket, now))
            conn.commit()
            return True

    def set_grants(self, user_id: int, grants: list[dict]) -> None:
        if not isinstance(grants, list) or len(grants) > 1000:
            raise ValueError('邮箱授权列表无效')
        normalized = []
        for grant in grants:
            if (not isinstance(grant, dict) or type(grant.get('account_id')) is not int
                    or type(grant.get('can_operate', False)) is not bool):
                raise ValueError('邮箱授权需包含整数 account_id 与布尔 can_operate')
            normalized.append((user_id, grant['account_id'], int(grant.get('can_operate', False))))
        if len({item[1] for item in normalized}) != len(normalized):
            raise ValueError('邮箱授权不能重复')
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if not conn.execute('SELECT id FROM app_users WHERE id=?', (user_id,)).fetchone():
                raise ValueError('用户不存在')
            for _, account_id, _ in normalized:
                if not conn.execute('SELECT id FROM mail_accounts WHERE id=?', (account_id,)).fetchone():
                    raise ValueError('邮箱不存在')
            conn.execute('DELETE FROM user_mailbox_grants WHERE user_id=?', (user_id,))
            conn.executemany('INSERT INTO user_mailbox_grants VALUES (?,?,?)', normalized)
            conn.commit()

    def list_grants(self, user_id: int) -> list[dict]:
        with self.db.get_connection() as conn:
            return [dict(row) for row in conn.execute('''SELECT g.account_id,g.can_operate,
                m.email_address,m.name FROM user_mailbox_grants g
                JOIN mail_accounts m ON m.id=g.account_id WHERE g.user_id=? ORDER BY m.id''', (user_id,))]

    def mailbox_options(self, principal: Principal) -> list[dict]:
        if principal.is_admin:
            return [{'account_id': row['id'], 'email_address': row['email_address'],
                     'name': row['name'], 'can_operate': True} for row in self.db.list_mail_accounts()]
        return self.list_grants(principal.user_id)

    @staticmethod
    def email_scope(principal: Principal | None, alias: str = 'email_records', *, operate=False) -> tuple[str, list]:
        if principal is None or principal.is_admin:
            return '1=1', []
        operation = ' AND g.can_operate=1' if operate else ''
        return (f'''EXISTS (SELECT 1 FROM user_mailbox_grants g
            JOIN mail_accounts m ON m.id=g.account_id JOIN app_users u ON u.id=g.user_id
            WHERE g.user_id=? AND u.enabled=1{operation}
            AND m.email_address=TRIM({alias}.receiver) COLLATE NOCASE)''', [principal.user_id])

    def can_access_email(self, principal: Principal, email_id: int, *, operate=False) -> bool:
        scope, params = self.email_scope(principal, operate=operate)
        with self.db.get_connection() as conn:
            return conn.execute(f'SELECT 1 FROM email_records WHERE id=? AND {scope}',
                                [email_id, *params]).fetchone() is not None

    @classmethod
    def draft_scope(cls, principal, alias='d', *, operate=False):
        if principal is None or principal.is_admin:
            return '1=1', []
        scope, params = cls.email_scope(principal, 'e', operate=operate)
        # A generated draft can contain information from all its source mails.
        # Require access to the entire source set, including its generation source.
        return (f'''EXISTS (SELECT 1 FROM supplier_draft_samples s WHERE s.draft_id={alias}.id)
            AND NOT EXISTS (SELECT 1 FROM supplier_draft_samples s
                LEFT JOIN email_records e ON e.id=s.email_records_id
                WHERE s.draft_id={alias}.id AND NOT ({scope}))
            AND ({alias}.source_email_records_id IS NULL OR EXISTS
                (SELECT 1 FROM email_records e WHERE e.id={alias}.source_email_records_id AND {scope}))''',
                [*params, *params])

    def can_access_draft(self, principal, draft_id, *, operate=False):
        scope, params = self.draft_scope(principal, operate=operate)
        with self.db.get_connection() as conn:
            return conn.execute(f'SELECT 1 FROM supplier_drafts d WHERE d.id=? AND {scope}',
                                [draft_id, *params]).fetchone() is not None

    def can_access_supplier_samples(self, principal, supplier_id, *, operate=False):
        if principal.is_admin:
            return True
        with self.db.get_connection() as conn:
            access = conn.execute('SELECT * FROM supplier_sample_access WHERE supplier_id=?', (supplier_id,)).fetchone()
        if not access:
            return False  # Legacy samples without provenance remain administrator-only.
        if access['owner_user_id'] == principal.user_id:
            return True  # Manually entered samples belong to their author.
        sources = json.loads(access['source_email_ids'])
        return bool(sources) and all(self.can_access_email(principal, email_id, operate=operate) for email_id in sources)

    def supplier_for_principal(self, principal, record):
        if self.can_access_supplier_samples(principal, record['id']):
            if self.can_access_supplier_samples(principal, record['id'], operate=True):
                return record
            return {**record, 'samples_read_only': True}
        return {**record, 'email_type_samples': {}, 'supplier_mail_classify_prompt': '',
                'samples_restricted': True, 'samples_read_only': True}
