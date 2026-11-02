import json
import time
import uuid
from datetime import datetime

from loguru import logger

from unconfigured_mail import ANALYSIS, DISCOVERY, accepted_branches, accepts_sender, normalize_sender, read_settings


SAMPLE_MAIL_TYPES = ('割接通知', '割接改期', '割接取消', '割接提醒')
SAMPLES_PER_CATEGORY = 3


def log_skip(account, email_id, sender, stage, reason_code):
    logger.info('未配置邮件策略不执行 account={} email_records_id={} sender={} stage={} reason_code={}',
                account, email_id, normalize_sender(sender), stage, reason_code)


def initialize_storage(cursor):
    statements = [
        '''CREATE TABLE IF NOT EXISTS mail_intake_cursors (
            account TEXT NOT NULL, folder TEXT NOT NULL, uidvalidity INTEGER NOT NULL,
            next_uid INTEGER NOT NULL, initialized_at TEXT NOT NULL,
            PRIMARY KEY (account, folder))''',
        '''CREATE TABLE IF NOT EXISTS supplier_drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, candidate_key TEXT NOT NULL UNIQUE,
            sender TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'collecting', draft_json TEXT,
            revision INTEGER NOT NULL DEFAULT 0, source_email_records_id INTEGER,
            published_supplier_id INTEGER, last_error TEXT NOT NULL DEFAULT '',
            create_time TEXT NOT NULL, update_time TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS supplier_draft_samples (
            draft_id INTEGER NOT NULL REFERENCES supplier_drafts(id),
            email_records_id INTEGER NOT NULL REFERENCES email_records(id),
            PRIMARY KEY (draft_id, email_records_id))''',
        '''CREATE TABLE IF NOT EXISTS mail_ai_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE,
            task_type TEXT NOT NULL, target_key TEXT NOT NULL,
            email_records_id INTEGER NOT NULL REFERENCES email_records(id),
            draft_id INTEGER, draft_revision INTEGER,
            status TEXT NOT NULL DEFAULT 'pending', attempt_id TEXT,
            attempts INTEGER NOT NULL DEFAULT 0, lease_until REAL,
            next_run_at REAL NOT NULL DEFAULT 0, accepted_branches TEXT NOT NULL,
            last_error TEXT NOT NULL DEFAULT '', result_json TEXT,
            create_time TEXT NOT NULL, update_time TEXT NOT NULL,
            UNIQUE (task_type, target_key))''',
        'CREATE INDEX IF NOT EXISTS idx_mail_ai_jobs_ready ON mail_ai_jobs(status, next_run_at)',
        'CREATE INDEX IF NOT EXISTS idx_mail_ai_jobs_email ON mail_ai_jobs(email_records_id)',
    ]
    statements.append('''CREATE TABLE IF NOT EXISTS unconfigured_sample_cleanup (
        email_records_id INTEGER PRIMARY KEY REFERENCES email_records(id))''')
    statements.append('''CREATE TABLE IF NOT EXISTS excluded_sender_mail_cleanup (
        email_records_id INTEGER PRIMARY KEY, next_run_at REAL NOT NULL DEFAULT 0)''')
    for statement in statements:
        cursor.execute(statement)
    if 'workflow_context' not in {row[1] for row in cursor.execute('PRAGMA table_info(mail_ai_jobs)')}:
        cursor.execute('ALTER TABLE mail_ai_jobs ADD COLUMN workflow_context TEXT')


class ResultConflict(ValueError):
    pass


class UnconfiguredMailRepository:
    def __init__(self, db):
        self.db = db

    @staticmethod
    def enqueue(conn, task_type, email_id, branches, draft_id=None, revision=None):
        now = datetime.now().isoformat(' ', timespec='seconds')
        conn.execute('''INSERT OR IGNORE INTO mail_ai_jobs
            (request_id, task_type, target_key, email_records_id, draft_id, draft_revision,
             accepted_branches, create_time, update_time)
            SELECT ?, ?, ?, ?, ?, ?, ?, ?, ? WHERE EXISTS (
                SELECT 1 FROM email_records e WHERE e.id=? AND NOT EXISTS (
                    SELECT 1 FROM mail_deletions d WHERE d.email_records_id=e.id))''',
            (str(uuid.uuid4()), task_type, str(draft_id if draft_id is not None else email_id),
             email_id, draft_id, revision, json.dumps(branches), now, now, email_id))

    def ingest(self, email, receiver, is_read=False):
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if self.db._is_email_deleted(conn, email.uid, receiver):
                log_skip(receiver, None, email.sender, 'intake', 'mail_deleted')
                return None
            existing = conn.execute('SELECT id FROM email_records WHERE email_id=? AND receiver=?',
                                    (email.uid, receiver)).fetchone()
            if existing:
                return existing['id']
            policy = read_settings(self.db, conn)
            branches = accepted_branches(policy, email.sender)
            now = datetime.now().isoformat(' ', timespec='seconds')
            result = conn.execute('''INSERT INTO email_records
                (email_id, sender, receiver, subject, subject_hash, content, content_hash,
                 html_content, attachments, message_id, reply_to, "references", in_reply_to,
                 is_read, processing_origin, create_time, update_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'unconfigured', ?, ?)''',
                (email.uid, normalize_sender(email.sender), receiver, email.subject,
                 self.db._hash_text(email.subject), email.content, self.db._hash_text(email.content),
                 email.html_content, self.db._serialize_attachments(email.attachments),
                 email.message_id, email.reply_to, email.references, email.in_reply_to,
                 int(is_read), now, now))
            email_id = result.lastrowid
            if any(branches.values()):
                self.enqueue(conn, 'unconfigured_mail_analyze', email_id, branches)
            else:
                reason = 'sender_filtered' if not accepts_sender(policy, email.sender) else 'features_disabled'
                log_skip(receiver, email_id, email.sender, 'intake', reason)
            conn.commit()
            return email_id

    def cursor(self, account, folder, uidvalidity, uidnext):
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('''INSERT OR IGNORE INTO mail_intake_cursors
                VALUES (?, ?, ?, ?, ?)''',
                (account, folder, uidvalidity, uidnext, datetime.now().isoformat()))
            row = conn.execute('SELECT * FROM mail_intake_cursors WHERE account=? AND folder=?',
                               (account, folder)).fetchone()
            if row['uidvalidity'] != uidvalidity:
                raise ResultConflict('UIDVALIDITY 已变化；需维护人员确认邮箱后重新建立新邮件边界')
            conn.commit()
            return row['next_uid']

    def advance_cursor(self, account, folder, uidvalidity, next_uid):
        with self.db.get_connection() as conn:
            conn.execute('''UPDATE mail_intake_cursors SET next_uid=?
                WHERE account=? AND folder=? AND uidvalidity=? AND next_uid < ?''',
                (next_uid, account, folder, uidvalidity, next_uid))
            conn.commit()

    def claim(self, lease_seconds=600, combined=False):
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            now = time.time()
            conn.execute('''UPDATE mail_ai_jobs SET status='failed', last_error='任务租约过期，重试次数已用尽'
                WHERE status='running' AND lease_until < ? AND attempts >= 3
                AND NOT EXISTS (SELECT 1 FROM mail_deletions d
                    WHERE d.email_records_id=mail_ai_jobs.email_records_id)''', (now,))
            conn.execute('''UPDATE supplier_drafts SET status='generation_failed',
                last_error='任务租约过期，重试次数已用尽', update_time=CURRENT_TIMESTAMP
                WHERE status='generating' AND draft_json IS NULL AND id IN
                (SELECT draft_id FROM mail_ai_jobs WHERE status='failed' AND task_type='supplier_config_draft'
                    AND NOT EXISTS (SELECT 1 FROM mail_deletions d
                        WHERE d.email_records_id=mail_ai_jobs.email_records_id))''')
            while True:
                row = conn.execute('''SELECT j.*, e.sender, e.receiver FROM mail_ai_jobs j
                    JOIN email_records e ON e.id=j.email_records_id
                    WHERE ((j.status='pending' AND j.next_run_at <= ?)
                       OR (j.status='running' AND j.lease_until < ? AND j.attempts < 3))
                    AND NOT EXISTS (SELECT 1 FROM mail_deletions d WHERE d.email_records_id=e.id)
                    AND (?=0 OR NOT EXISTS (
                        SELECT 1 FROM mail_ai_jobs active JOIN email_records other ON other.id=active.email_records_id
                        WHERE active.id != j.id AND active.status='running' AND active.lease_until >= ?
                        AND lower(other.sender)=lower(e.sender)))
                    ORDER BY j.id LIMIT 1''', (now, now, int(combined), now)).fetchone()
                if not row:
                    conn.commit()
                    return None
                job = dict(row)
                original = json.loads(job['accepted_branches'])
                current = accepted_branches(read_settings(self.db, conn), job['sender'])
                branches = {key: original.get(key, False) and current[key] for key in (DISCOVERY, ANALYSIS)}
                supplier = conn.execute('SELECT id FROM supplier_configs WHERE lower(email)=?',
                                        (normalize_sender(job['sender']),)).fetchone()
                required = {'supplier_config_draft': DISCOVERY, 'cutover_time_extract': ANALYSIS}.get(job['task_type'])
                allowed = branches[required] if required else any(branches.values())
                if supplier or not allowed:
                    conn.execute("UPDATE mail_ai_jobs SET status='cancelled' WHERE id=?", (job['id'],))
                    if job['draft_id']:
                        conn.execute("UPDATE supplier_drafts SET status='collecting' WHERE id=? AND status='generating' AND draft_json IS NULL", (job['draft_id'],))
                    log_skip(job['receiver'], job['email_records_id'], job['sender'], job['task_type'],
                             'supplier_configured' if supplier else 'policy_no_longer_allows')
                    continue
                job['attempt_id'] = str(uuid.uuid4())
                job['attempts'] += 1
                job['status'] = 'running'
                conn.execute('''UPDATE mail_ai_jobs SET status='running', attempt_id=?, attempts=?,
                    lease_until=?, update_time=CURRENT_TIMESTAMP WHERE id=?''',
                    (job['attempt_id'], job['attempts'], now + lease_seconds, job['id']))
                if combined and job['task_type'] == 'unconfigured_mail_analyze':
                    job['workflow_context'] = self._combined_context(conn, job, branches)
                    conn.execute('UPDATE mail_ai_jobs SET workflow_context=? WHERE id=?',
                                 (json.dumps(job['workflow_context']), job['id']))
                conn.commit()
                return job

    def _combined_context(self, conn, job, branches):
        previous = json.loads(job['workflow_context']) if job.get('workflow_context') else None
        draft = None
        if branches[DISCOVERY]:
            if previous:
                # A deleted candidate must not be recreated by a retry of its old mail.
                draft = conn.execute('SELECT * FROM supplier_drafts WHERE id=?', (previous['draft_id'],)).fetchone()
            else:
                sender = normalize_sender(job['sender'])
                conn.execute('''INSERT OR IGNORE INTO supplier_drafts
                    (candidate_key, sender, display_name, create_time, update_time)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)''', (sender, sender, sender))
                draft = conn.execute('SELECT * FROM supplier_drafts WHERE candidate_key=?', (sender,)).fetchone()
        return {
            'should_generate_supplier_draft': bool(draft and draft['status'] == 'collecting' and draft['draft_json'] is None
                and self._sample_count(conn, draft['id'], '割接通知') < SAMPLES_PER_CATEGORY),
            'should_analyze_cutover_time': bool(branches[ANALYSIS]),
            'draft_id': draft['id'] if draft else None,
            'draft_revision': draft['revision'] if draft else None,
        }

    def fail(self, job, error, transient=False):
        retry = transient and job['attempts'] < 3
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            updated = conn.execute('''UPDATE mail_ai_jobs SET status=?, last_error=?, next_run_at=?,
                lease_until=NULL, update_time=CURRENT_TIMESTAMP
                WHERE id=? AND attempt_id=? AND status='running'
                AND EXISTS (SELECT 1 FROM email_records e WHERE e.id=mail_ai_jobs.email_records_id)
                AND NOT EXISTS (SELECT 1 FROM mail_deletions d
                    WHERE d.email_records_id=mail_ai_jobs.email_records_id)''',
                ('pending' if retry else 'failed', error[:1000],
                 time.time() + (30 if job['attempts'] == 1 else 120), job['id'], job['attempt_id']))
            if updated.rowcount and job['draft_id'] and not retry:
                conn.execute('''UPDATE supplier_drafts SET status='generation_failed', last_error=?
                    WHERE id=? AND revision=? AND status='generating' ''',
                    (error[:1000], job['draft_id'], job['draft_revision']))
            conn.commit()

    def complete(self, envelope):
        from fastgpt_contracts import validate_envelope

        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''SELECT j.*, e.sender FROM mail_ai_jobs j
                JOIN email_records e ON e.id=j.email_records_id WHERE j.request_id=?''',
                               (envelope.get('request_id'),)).fetchone()
            if not row:
                raise ResultConflict('未知任务')
            job = dict(row)
            if conn.execute('SELECT 1 FROM mail_deletions WHERE email_records_id=?',
                            (job['email_records_id'],)).fetchone():
                raise ResultConflict('邮件已删除或正在删除，拒绝处理结果')
            result = validate_envelope(envelope, job)
            if job['status'] == 'succeeded':
                return json.loads(job['result_json'])
            if job['status'] != 'running' or job['lease_until'] < time.time():
                raise ResultConflict('任务未运行或结果租约已过期')
            record = conn.execute('SELECT * FROM email_records WHERE id=?',
                                  (job['email_records_id'],)).fetchone()
            if record['processing_origin'] != 'unconfigured':
                raise ResultConflict('任务来源不匹配')
            self._save_result(conn, job, record, result)
            conn.commit()
            self.cleanup_excess_samples()
            return result

    def _save_result(self, conn, job, record, result):
        if job['task_type'] == 'unconfigured_mail_analyze':
            self._classification(conn, job, record, result)
        elif job['task_type'] == 'supplier_config_draft':
            result['config']['email'] = normalize_sender(record['sender'])
            # A classification example is source material, not an AI-generated summary.
            samples = result['config'].setdefault('email_type_samples', {})
            samples['割接通知'] = {
                **samples.get('割接通知', {}),
                'source_email_records_id': record['id'],
                'subject': record['subject'] or '',
                'content': record['html_content'] or record['content'] or '',
            }
            changed = conn.execute('''UPDATE supplier_drafts SET draft_json=?, status='review',
                revision=revision+1, last_error='', update_time=CURRENT_TIMESTAMP
                WHERE id=? AND revision=? AND status='generating' AND draft_json IS NULL''',
                (json.dumps(result, ensure_ascii=False), job['draft_id'], job['draft_revision']))
            if not changed.rowcount:
                raise ResultConflict('草稿已被修改，拒绝覆盖')
        else:
            conn.execute('UPDATE email_records SET unconfigured_analysis_json=? WHERE id=?',
                         (json.dumps(result, ensure_ascii=False), record['id']))
            if result.get('reply') and not record['reply_status']:
                conn.execute('''UPDATE email_records SET reply_status='pending',
                    pending_reply_content=?, pending_reply_scene=? WHERE id=? AND reply_status='' ''',
                    (result['reply']['content'], result['scene'], record['id']))
        conn.execute('''UPDATE mail_ai_jobs SET status='succeeded', result_json=?, last_error='',
            lease_until=NULL, update_time=CURRENT_TIMESTAMP WHERE id=?''',
            (json.dumps(result, ensure_ascii=False), job['id']))

    def complete_combined(self, envelope):
        from fastgpt_contracts import validate_envelope

        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('''SELECT j.*, e.sender FROM mail_ai_jobs j JOIN email_records e
                ON e.id=j.email_records_id WHERE j.request_id=?''', (envelope.get('request_id'),)).fetchone()
            if not row or row['task_type'] != 'unconfigured_mail_analyze' or not row['workflow_context']:
                raise ResultConflict('未知合并任务')
            job = dict(row)
            if envelope.get('task_type') != 'unconfigured_mail_process':
                raise ValueError('合并任务类型不匹配')
            if conn.execute('SELECT 1 FROM mail_deletions WHERE email_records_id=?', (job['email_records_id'],)).fetchone():
                raise ResultConflict('邮件已删除或正在删除，拒绝处理结果')
            result = envelope.get('result')
            if not isinstance(result, dict):
                raise ValueError('合并结果必须是对象')
            classification = self._branch_result(result.get('classification'))
            classified = validate_envelope({**envelope, 'task_type':job['task_type'], 'result':classification}, job)
            if job['status'] == 'succeeded':
                return json.loads(job['result_json'])
            if job['status'] != 'running' or job['lease_until'] < time.time():
                raise ResultConflict('任务未运行或结果租约已过期')
            record = conn.execute('SELECT * FROM email_records WHERE id=?', (job['email_records_id'],)).fetchone()
            if record['processing_origin'] != 'unconfigured':
                raise ResultConflict('任务来源不匹配')
            context = json.loads(job['workflow_context'])
            self._classification(conn, job, record, classified, context)
            conn.execute('''UPDATE mail_ai_jobs SET status='succeeded', result_json=?, last_error='',
                lease_until=NULL, update_time=CURRENT_TIMESTAMP WHERE id=?''',
                (json.dumps(classified, ensure_ascii=False), job['id']))
            # Each logical branch has its own validation and savepoint. One bad result must
            # never roll back classification, a valid sibling, or its pending reply.
            for name, task in (('time_analysis', 'cutover_time_extract'), ('supplier_draft', 'supplier_config_draft')):
                child = conn.execute("SELECT * FROM mail_ai_jobs WHERE email_records_id=? AND task_type=? AND status='pending'",
                                     (record['id'], task)).fetchone()
                if not child:
                    continue
                child = {**dict(child), 'sender':job['sender'], 'attempt_id':job['attempt_id']}
                conn.execute("UPDATE mail_ai_jobs SET attempts=attempts+1, attempt_id=? WHERE id=?", (job['attempt_id'], child['id']))
                conn.execute('SAVEPOINT branch_result')
                try:
                    branch = self._branch_result(result.get(name))
                    validated = validate_envelope({'schema_version':1, 'task_type':task,
                        'request_id':child['request_id'], 'attempt_id':child['attempt_id'],
                        'email_records_id':record['id'], 'result':branch}, child)
                    self._save_result(conn, child, record, validated)
                except (ValueError, TypeError, KeyError) as exc:
                    conn.execute('ROLLBACK TO branch_result')
                    conn.execute("UPDATE mail_ai_jobs SET status='failed', last_error=?, update_time=CURRENT_TIMESTAMP WHERE id=?",
                                 (str(exc)[:1000], child['id']))
                    if child['draft_id']:
                        conn.execute("UPDATE supplier_drafts SET status='generation_failed', last_error=? WHERE id=? AND status='generating' AND draft_json IS NULL",
                                     (str(exc)[:1000], child['draft_id']))
                finally:
                    conn.execute('RELEASE branch_result')
            conn.commit()
            self.cleanup_excess_samples()
            return classified

    @staticmethod
    def _branch_result(branch):
        if not isinstance(branch, dict) or branch.get('status') != 'succeeded' or not isinstance(branch.get('result'), dict):
            error = branch.get('error') if isinstance(branch, dict) else None
            raise ValueError(error[:1000] if isinstance(error, str) and error.strip() else '工作流未返回有效的分支结果')
        return branch['result']

    def _classification(self, conn, job, record, result, context=None):
        conn.execute('UPDATE email_records SET mail_type=? WHERE id=?',
                     (result['mail_type'], record['id']))
        original = json.loads(job['accepted_branches'])
        current = accepted_branches(read_settings(self.db, conn), record['sender'])
        branches = {key: original.get(key, False) and current[key] for key in (DISCOVERY, ANALYSIS)}
        if conn.execute('SELECT id FROM supplier_configs WHERE lower(email)=?',
                        (normalize_sender(record['sender']),)).fetchone():
            log_skip(record['receiver'], record['id'], record['sender'], 'classification', 'supplier_configured')
            return
        notice = result['mail_type'] == '割接通知'
        for branch, task in ((DISCOVERY, 'supplier_config_draft'), (ANALYSIS, 'cutover_time_extract')):
            if not branches[branch]:
                log_skip(record['receiver'], record['id'], record['sender'], task, 'branch_not_accepted')
        if branches[DISCOVERY]:
            sender = normalize_sender(record['sender'])
            if context is None:
                conn.execute('''INSERT OR IGNORE INTO supplier_drafts
                    (candidate_key, sender, display_name, create_time, update_time)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)''', (sender, sender, sender))
                draft = conn.execute('SELECT * FROM supplier_drafts WHERE candidate_key=?', (sender,)).fetchone()
            else:
                draft = conn.execute('SELECT * FROM supplier_drafts WHERE id=? AND candidate_key=?',
                                     (context['draft_id'], sender)).fetchone()
            retained = bool(draft and draft['status'] != 'published' and self._collect_sample(conn, draft['id'], record, result['mail_type']))
            can_generate = context is None or (context['should_generate_supplier_draft'] and draft
                                               and context['draft_revision'] == draft['revision'])
            if notice and retained and can_generate and draft['status'] == 'collecting' and draft['draft_json'] is None:
                conn.execute("UPDATE supplier_drafts SET status='generating', source_email_records_id=?, update_time=CURRENT_TIMESTAMP WHERE id=?",
                             (record['id'], draft['id']))
                # A cancelled job never replays its old sample; a new notice may start this candidate.
                conn.execute("DELETE FROM mail_ai_jobs WHERE task_type='supplier_config_draft' AND target_key=? AND status='cancelled'", (str(draft['id']),))
                self.enqueue(conn, 'supplier_config_draft', record['id'], branches, draft['id'], draft['revision'])
            elif notice:
                log_skip(record['receiver'], record['id'], record['sender'], 'supplier_config_draft', 'draft_already_exists')
        if notice and branches[ANALYSIS] and (context is None or context['should_analyze_cutover_time']):
            self.enqueue(conn, 'cutover_time_extract', record['id'], branches)
        elif not notice:
            log_skip(record['receiver'], record['id'], record['sender'], 'classification', 'not_cutover_notice')

    @staticmethod
    def _sample_count(conn, draft_id, mail_type):
        return conn.execute('''SELECT count(*) FROM supplier_draft_samples s
            JOIN email_records e ON e.id=s.email_records_id WHERE s.draft_id=? AND e.mail_type=?''',
            (draft_id, mail_type)).fetchone()[0]

    def _collect_sample(self, conn, draft_id, record, mail_type):
        # Called inside BEGIN IMMEDIATE after classification; retries consume no extra slot.
        if conn.execute('SELECT 1 FROM supplier_draft_samples WHERE draft_id=? AND email_records_id=?',
                        (draft_id, record['id'])).fetchone():
            return True
        if mail_type in SAMPLE_MAIL_TYPES and self._sample_count(conn, draft_id, mail_type) < SAMPLES_PER_CATEGORY:
            conn.execute('INSERT INTO supplier_draft_samples VALUES (?, ?)', (draft_id, record['id']))
            return True
        conn.execute('INSERT OR IGNORE INTO unconfigured_sample_cleanup VALUES (?)', (record['id'],))
        log_skip(record['receiver'], record['id'], record['sender'], 'sample',
                 'sample_limit_reached' if mail_type in SAMPLE_MAIL_TYPES else 'not_sample_category')
        return False

    def cleanup_excess_samples(self):
        from sample_retention import cleanup_excess_samples
        cleanup_excess_samples(self.db)

    def retry(self, email_id, task_type, *, draft_id=None, principal=None):
        if task_type not in ('unconfigured_mail_analyze', 'cutover_time_extract', 'supplier_config_draft'):
            raise ValueError('任务类型无效')
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            if conn.execute('SELECT 1 FROM mail_deletions WHERE email_records_id=?',
                            (email_id,)).fetchone():
                raise ResultConflict('邮件已删除或正在删除，不能重试')
            condition = ' AND draft_id=?' if draft_id is not None else ''
            params = [email_id, task_type, *([draft_id] if draft_id is not None else [])]
            row = conn.execute(f"SELECT * FROM mail_ai_jobs WHERE email_records_id=? AND task_type=? AND status='failed'{condition}",
                               params).fetchone()
            if not row:
                raise ResultConflict('只允许重试实际执行失败的任务')
            if row['draft_id'] and principal is not None:
                from user_access import UserAccessRepository
                scope, scope_params = UserAccessRepository.draft_scope(principal, operate=True)
                if not conn.execute(f'SELECT 1 FROM supplier_drafts d WHERE d.id=? AND ({scope})',
                                    [row['draft_id'], *scope_params]).fetchone():
                    raise LookupError('草稿不存在或来源邮箱未获操作授权')
            conn.execute("UPDATE mail_ai_jobs SET status='pending', attempts=0, attempt_id=NULL, next_run_at=0, last_error='' WHERE id=?", (row['id'],))
            if row['draft_id']:
                changed = conn.execute("UPDATE supplier_drafts SET status='generating', last_error='' WHERE id=? AND status='generation_failed' AND draft_json IS NULL", (row['draft_id'],))
                if not changed.rowcount:
                    raise ResultConflict('已有配置草稿不能重新生成')
            conn.commit()

    def projection(self, email_id, conn=None):
        if conn is None:
            with self.db.get_connection() as connection:
                return self.projection(email_id, connection)
        jobs = conn.execute('''SELECT task_type, status, last_error, update_time FROM mail_ai_jobs
            WHERE email_records_id=? AND status != 'cancelled' ORDER BY id''', (email_id,)).fetchall()
        draft = conn.execute('SELECT draft_id FROM supplier_draft_samples WHERE email_records_id=?', (email_id,)).fetchone()
        record = conn.execute('SELECT unconfigured_analysis_json FROM email_records WHERE id=?', (email_id,)).fetchone()
        return {'ai_tasks': [dict(row) for row in jobs],
                'supplier_draft_id': draft['draft_id'] if draft else None,
                'unconfigured_analysis': json.loads(record[0]) if record and record[0] else None}
