import json
from functools import wraps

from flask import g, jsonify, request
from pydantic import ValidationError

from fastgpt_contracts import validate_draft_config
from mail_preview import build_mail_preview
from supplier_config import SupplierConfigCreate, SupplierConfigRepository, SupplierReviewMetadata
from unconfigured_mail_repository import ResultConflict, UnconfiguredMailRepository
from user_access import UserAccessRepository


def draft_validation_message(error):
    """Show field-specific guidance without Pydantic internals or input snapshots."""
    labels = {'name': '供应商名称', 'email': '发件邮箱', 'reply_email': '回复邮箱',
              'line_custom_fields': '线路自定义字段', 'custom_fields': '顶层自定义字段',
              'line_query_keywords': '线路查询关键字', 'email_type_samples': '邮件分类样本',
              'prompt_mode': '提示词模式', 'cutover_extract_prompt': '割接字段提取提示词'}
    messages = []
    for item in error.errors(include_url=False, include_input=False):
        loc = item.get('loc') or ()
        field = loc[0] if loc else None
        label = labels.get(field, '配置')
        if field in ('line_custom_fields', 'custom_fields') and len(loc) > 1 and isinstance(loc[1], int):
            label += f'第 {loc[1] + 1} 项'
            if len(loc) > 2:
                label += '的' + {'name': '字段名', 'description': '提取规则'}.get(loc[2], '配置')
        if field in ('email', 'reply_email'):
            message = f'{label}格式不正确，请填写一个完整邮箱地址'
        elif item['type'] in ('missing', 'string_too_short'):
            message = f'{label}不能为空'
        elif item['type'] == 'value_error' and item.get('ctx', {}).get('error'):
            # These are the application's own validators, already written in Chinese.
            message = str(item['ctx']['error'])
            if loc:
                message = f'{label}：{message}'
        else:
            message = f'{label}格式不正确，请检查填写内容'
        if message not in messages:
            messages.append(message)
    return '；'.join(messages) or '配置校验失败，请检查填写内容'


class SupplierDraftRepository:
    def __init__(self, db, principal=None):
        self.db = db
        self.principal = principal

    def scope(self, *, operate=False):
        return UserAccessRepository.draft_scope(self.principal, operate=operate)

    @staticmethod
    def sample_sources(conn, item):
        sources = {row[0] for row in conn.execute(
            'SELECT email_records_id FROM supplier_draft_samples WHERE draft_id=?', (item['id'],))}
        if item['source_email_records_id'] is not None:
            sources.add(item['source_email_records_id'])
        for sample in (item.get('draft') or {}).get('config', {}).get('email_type_samples', {}).values():
            source_id = sample.get('source_email_records_id') or item['source_email_records_id']
            if source_id is None:
                return set()  # Legacy copies without provenance stay administrator-only.
            sources.add(source_id)
        return sources

    def can_access_samples(self, conn, item, *, operate=False):
        if self.principal is None or self.principal.is_admin:
            return True
        sources = self.sample_sources(conn, item)
        if not sources:
            return False
        scope, params = UserAccessRepository.email_scope(self.principal, 'e', operate=operate)
        count = conn.execute(f"SELECT count(*) FROM email_records e WHERE e.id IN ({','.join('?' for _ in sources)}) AND ({scope})",
                             [*sources, *params]).fetchone()[0]
        return count == len(sources)  # Deleted sources never make a retained copy public.

    def serialize(self, row, conn):
        item = dict(row)
        item['draft'] = json.loads(item.pop('draft_json')) if item.get('draft_json') else None
        item.pop('draft_json', None)
        if item['draft']:
            config = item['draft']['config']
            if not self.can_access_samples(conn, item):
                config.update(email_type_samples={}, review_metadata={}, supplier_mail_classify_prompt='',
                              samples_restricted=True, samples_read_only=True)
                item['draft']['evidence'] = []
                item['draft']['unresolved_questions'] = []
            elif not self.can_access_samples(conn, item, operate=True):
                config['samples_read_only'] = True
        return item

    def list(self, page=1, page_size=20, status='unpublished'):
        if status not in ('unpublished', 'published'):
            raise ValueError('草稿筛选状态必须为 unpublished 或 published')
        condition = "d.status = 'published'" if status == 'published' else "d.status != 'published'"
        scope, params = self.scope()
        mail_scope, mail_params = UserAccessRepository.email_scope(self.principal, 'e')
        condition += f' AND ({scope})'
        with self.db.get_connection() as conn:
            total = conn.execute(f'SELECT count(*) FROM supplier_drafts d WHERE {condition}', params).fetchone()[0]
            rows = conn.execute(f'''SELECT d.*, (SELECT count(*) FROM supplier_draft_samples s
                JOIN email_records e ON e.id=s.email_records_id
                WHERE s.draft_id=d.id AND ({mail_scope})) AS sample_count
                FROM supplier_drafts d WHERE {condition}
                ORDER BY d.update_time DESC, d.id DESC LIMIT ? OFFSET ?''',
                [*mail_params, *params, page_size, (page - 1) * page_size]).fetchall()
            return {'items': [self.serialize(row, conn) for row in rows], 'total': total,
                    'page': page, 'pageSize': page_size}

    def get(self, draft_id, page=1, page_size=20):
        scope, params = self.scope()
        mail_scope, mail_params = UserAccessRepository.email_scope(self.principal, 'e')
        with self.db.get_connection() as conn:
            row = conn.execute(f'SELECT d.* FROM supplier_drafts d WHERE d.id=? AND {scope}', [draft_id, *params]).fetchone()
            if not row:
                raise LookupError('供应商草稿不存在')
            item = self.serialize(row, conn)
            samples = conn.execute(f'''SELECT e.id, e.subject, e.sender, e.receiver, e.mail_type,
                e.create_time, substr(e.content, 1, 300) AS content_summary
                FROM supplier_draft_samples s JOIN email_records e ON e.id=s.email_records_id
                WHERE s.draft_id=? AND ({mail_scope}) ORDER BY e.id DESC LIMIT ? OFFSET ?''',
                [draft_id, *mail_params, page_size, (page - 1) * page_size]).fetchall()
            counts = conn.execute(f'''SELECT e.mail_type, count(*) AS count FROM supplier_draft_samples s
                JOIN email_records e ON e.id=s.email_records_id
                WHERE s.draft_id=? AND ({mail_scope}) GROUP BY e.mail_type''',
                [draft_id, *mail_params]).fetchall()
            item.update(samples=[dict(sample) for sample in samples],
                        sample_counts={row['mail_type']: row['count'] for row in counts})
            item['sample_count'] = sum(item['sample_counts'].values())
            return item

    def edit(self, draft_id, revision, config):
        if type(revision) is not int or not isinstance(config, dict):
            raise ValueError('必须提供 revision 和配置对象 config')
        validate_draft_config(config)
        if "review_metadata" in config:
            config = {**config, "review_metadata": SupplierReviewMetadata.model_validate(config["review_metadata"]).model_dump()}
        scope, params = self.scope(operate=True)
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(f'SELECT d.* FROM supplier_drafts d WHERE d.id=? AND {scope}', [draft_id, *params]).fetchone()
            if not row:
                raise LookupError('供应商草稿不存在')
            if row['status'] != 'review' or row['revision'] != revision:
                raise ResultConflict('草稿状态或版本已变化，请刷新后重试')
            value = json.loads(row['draft_json'])
            if not self.can_access_samples(conn, {**dict(row), 'draft': value}, operate=True):
                protected = ('email_type_samples', 'review_metadata', 'supplier_mail_classify_prompt')
                if any(field in config for field in protected):
                    raise PermissionError('邮件样本来源邮箱未授予操作权限，其他配置字段仍可修改')
                config = {**config, **{field: value['config'][field] for field in protected if field in value['config']}}
            value['config'] = {**config, 'email': row['sender']}
            conn.execute('''UPDATE supplier_drafts SET draft_json=?, revision=revision+1,
                update_time=CURRENT_TIMESTAMP WHERE id=?''', (json.dumps(value, ensure_ascii=False), draft_id))
            conn.commit()
        return self.get(draft_id)

    def delete(self, draft_id, revision):
        if type(revision) is not int:
            raise ValueError('必须提供整数 revision')
        scope, params = self.scope(operate=True)
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(f'SELECT d.revision FROM supplier_drafts d WHERE d.id=? AND {scope}', [draft_id, *params]).fetchone()
            if not row:
                raise LookupError('供应商草稿不存在')
            if row['revision'] != revision:
                raise ResultConflict('草稿版本已变化，请刷新后重试')
            # Removing the generation jobs also invalidates their outstanding results.
            # Classification, time analysis, mail records and published suppliers remain intact.
            conn.execute("DELETE FROM mail_ai_jobs WHERE draft_id=? AND task_type='supplier_config_draft'", (draft_id,))
            conn.execute('DELETE FROM supplier_draft_samples WHERE draft_id=?', (draft_id,))
            conn.execute('DELETE FROM supplier_drafts WHERE id=?', (draft_id,))
            conn.commit()
        return {'draft_id': draft_id, 'deleted': True}

    def exclude_sender(self, draft_id, revision, *, data_dir=None):
        from unconfigured_mail import read_settings, normalize_sender, ADDRESS_PATTERN
        from cutover_deletion import prepare_cutover_email_deletion, DeletionConflict
        from excluded_sender_cleanup import cleanup_excluded_sender_mail
        from email_attachments import DATA_DIR

        data_dir = data_dir if data_dir is not None else DATA_DIR
        SupplierConfigRepository(self.db)

        if type(revision) is not int:
            raise ValueError('必须提供整数 revision')
        scope, params = self.scope(operate=True)
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(f'SELECT d.* FROM supplier_drafts d WHERE d.id=? AND {scope}',
                               [draft_id, *params]).fetchone()
            if not row:
                raise LookupError('供应商草稿不存在')
            if row['revision'] != revision:
                raise ResultConflict('草稿版本已变化，请刷新后重试')
            sender = normalize_sender(row['sender'])
            if not ADDRESS_PATTERN.fullmatch(sender):
                raise ValueError('发件人邮箱格式无效，无法加入排除名单')
            if row['status'] == 'published' or conn.execute(
                'SELECT 1 FROM supplier_configs WHERE lower(email)=?', (sender,)).fetchone():
                raise ResultConflict('该地址已有正式供应商配置，不能通过草稿排除')
            mail_scope, mail_params = UserAccessRepository.email_scope(self.principal, 'e', operate=True)
            targets = conn.execute("""SELECT e.id FROM email_records e
                WHERE e.processing_origin='unconfigured' AND lower(e.sender)=?""", (sender,)).fetchall()
            if conn.execute(f"""SELECT 1 FROM email_records e WHERE e.processing_origin='unconfigured'
                AND lower(e.sender)=? AND NOT ({mail_scope})""", [sender, *mail_params]).fetchone():
                raise ResultConflict('该发件人的历史邮件涉及未获操作授权的邮箱，无法完成此操作')
            policy = read_settings(self.db, conn)
            mode = policy['unconfigured_sender_filter_mode']
            if mode == 'allowlist':
                raise ResultConflict('当前使用“仅处理指定发件人”，请先在系统配置中调整发件人范围；本次未修改名单或草稿')
            # In all mode the stored list is inactive and could be an old allowlist.
            # Do not accidentally activate those entries as exclusions.
            addresses = list(policy['unconfigured_sender_filter_list']) if mode == 'blocklist' else []
            if sender not in addresses:
                addresses.append(sender)
            for key, value in (('unconfigured_sender_filter_mode', 'blocklist'),
                               ('unconfigured_sender_filter_list', addresses)):
                conn.execute('''INSERT INTO system_settings (key,value,update_time) VALUES (?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(key) DO UPDATE SET value=excluded.value,update_time=excluded.update_time''',
                    (key, json.dumps(value, ensure_ascii=False)))
            # Invalidate unfinished work too: late AI responses cannot recreate the draft
            # or produce new replies after this transaction commits.
            conn.execute('''UPDATE mail_ai_jobs SET status='cancelled',lease_until=NULL,update_time=CURRENT_TIMESTAMP
                WHERE status IN ('pending','running','failed') AND email_records_id IN (
                    SELECT id FROM email_records WHERE processing_origin='unconfigured' AND lower(sender)=?)''', (sender,))
            for target in targets:
                try:
                    prepare_cutover_email_deletion(conn, data_dir, target['id'])
                except DeletionConflict as error:
                    raise ResultConflict(str(error)) from error
                conn.execute('INSERT OR IGNORE INTO excluded_sender_mail_cleanup(email_records_id) VALUES (?)', (target['id'],))
            conn.execute("DELETE FROM mail_ai_jobs WHERE draft_id=? AND task_type='supplier_config_draft'", (draft_id,))
            conn.execute('DELETE FROM supplier_draft_samples WHERE draft_id=?', (draft_id,))
            conn.execute('DELETE FROM supplier_drafts WHERE id=?', (draft_id,))
            conn.commit()
        cleanup_excluded_sender_mail(self.db, data_dir=data_dir)
        return {'draft_id': draft_id, 'sender': sender, 'excluded': True}

    def publish(self, draft_id, revision):
        if type(revision) is not int:
            raise ValueError('必须提供整数 revision')
        SupplierConfigRepository(self.db)
        scope, params = self.scope(operate=True)
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute(f'SELECT d.* FROM supplier_drafts d WHERE d.id=? AND {scope}', [draft_id, *params]).fetchone()
            if not row:
                raise LookupError('供应商草稿不存在')
            if row['revision'] != revision:
                raise ResultConflict('草稿版本已变化，请刷新后重试')
            if row['status'] == 'published':
                return {'supplier_id': row['published_supplier_id'], 'draft_id': draft_id}
            if row['status'] != 'review':
                raise ResultConflict('当前草稿尚不可发布')
            draft = json.loads(row['draft_json'])
            config = draft['config']
            config.setdefault('review_metadata', {'questions': draft.get('unresolved_questions', []), 'confirmations': {}})
            config['email'] = row['sender']
            if not isinstance(config.get('name'), str) or not config['name'].strip():
                raise ValueError('启用前请填写供应商名称')
            if isinstance(config.get('reply_email'), str) and not config['reply_email'].strip():
                config['reply_email'] = None
            if not isinstance(config.get('email_type_samples'), dict) or '割接通知' not in config['email_type_samples']:
                raise ValueError('发布前必须补全割接通知主题和正文样本')
            payload = SupplierConfigCreate.model_validate(config)
            conflict = conn.execute('SELECT id FROM supplier_configs WHERE lower(email)=lower(?) OR lower(name)=lower(?)',
                                    (str(payload.email), payload.name)).fetchone()
            if conflict:
                raise ResultConflict('供应商邮箱或名称已有正式配置，请人工核对')
            values = payload.model_dump(mode='json')
            values['reply_email'] = values['reply_email'] or values['email']
            for key in ('line_custom_fields', 'line_query_keywords', 'fixed_field_rules', 'custom_fields', 'email_type_samples', 'review_metadata'):
                values[key] = json.dumps(values[key], ensure_ascii=False)
            columns = ', '.join(values)
            placeholders = ', '.join('?' for _ in values)
            inserted = conn.execute(f'''INSERT INTO supplier_configs ({columns}, create_time, update_time)
                VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)''', list(values.values()))
            supplier_id = inserted.lastrowid
            sources = self.sample_sources(conn, {**dict(row), 'draft': draft})
            conn.execute('INSERT INTO supplier_sample_access VALUES (?,NULL,?)',
                         (supplier_id, json.dumps(sorted(sources))))
            conn.execute('''UPDATE supplier_drafts SET status='published', published_supplier_id=?,
                update_time=CURRENT_TIMESTAMP WHERE id=?''', (supplier_id, draft_id))
            conn.commit()
            return {'supplier_id': supplier_id, 'draft_id': draft_id}


def register_routes(app, get_db, require_api_key, get_data_dir=None):
    def handle_errors(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            try:
                return jsonify({'success': True, 'data': func(*args, **kwargs)})
            except LookupError as exc:
                return jsonify({'success': False, 'message': str(exc)}), 404
            except ResultConflict as exc:
                return jsonify({'success': False, 'message': str(exc)}), 409
            except PermissionError as exc:
                return jsonify({'success': False, 'message': str(exc)}), 403
            except ValidationError as exc:
                return jsonify({'success': False, 'message': draft_validation_message(exc)}), 400
            except ValueError as exc:
                return jsonify({'success': False, 'message': str(exc)}), 400
        return wrapped

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('请求必须是 JSON 对象')
        return data

    def pagination():
        return max(1, int(request.args.get('page', 1))), min(100, max(1, int(request.args.get('pageSize', 20))))

    @app.route('/api/supplier-drafts', methods=['GET'])
    @require_api_key
    @handle_errors
    def list_supplier_drafts():
        return SupplierDraftRepository(get_db(), g.principal).list(*pagination(), status=request.args.get('status', 'unpublished'))

    @app.route('/api/supplier-drafts/<int:draft_id>', methods=['GET', 'PUT', 'DELETE'])
    @require_api_key
    @handle_errors
    def supplier_draft_detail(draft_id):
        repo = SupplierDraftRepository(get_db(), g.principal)
        if request.method == 'GET':
            return repo.get(draft_id, *pagination())
        data = body()
        if request.method == 'DELETE':
            return repo.delete(draft_id, data.get('revision'))
        return repo.edit(draft_id, data.get('revision'), data.get('config'))

    @app.route('/api/supplier-drafts/<int:draft_id>/exclude-sender', methods=['POST'])
    @require_api_key
    @handle_errors
    def exclude_supplier_draft_sender(draft_id):
        return SupplierDraftRepository(get_db(), g.principal).exclude_sender(
            draft_id, body().get('revision'), data_dir=get_data_dir() if get_data_dir else None)

    @app.route('/api/supplier-drafts/<int:draft_id>/publish', methods=['POST'])
    @require_api_key
    @handle_errors
    def publish_supplier_draft(draft_id):
        return SupplierDraftRepository(get_db(), g.principal).publish(draft_id, body().get('revision'))

    @app.route('/api/supplier-drafts/<int:draft_id>/retry', methods=['POST'])
    @require_api_key
    @handle_errors
    def retry_supplier_draft(draft_id):
        db = get_db()
        draft = SupplierDraftRepository(db, g.principal).get(draft_id)
        if draft['status'] != 'generation_failed':
            raise ResultConflict('只允许重试生成失败的草稿')
        UnconfiguredMailRepository(db).retry(draft['source_email_records_id'], 'supplier_config_draft',
                                            draft_id=draft_id, principal=g.principal)
        return SupplierDraftRepository(db, g.principal).get(draft_id)

    @app.route('/api/unconfigured-mail/results', methods=['POST'])
    @require_api_key
    @handle_errors
    def save_unconfigured_mail_result():
        data = body()
        if data.get('task_type') != 'cutover_time_extract':
            raise ValueError('此回调仅接受割接时间分析结果')
        return UnconfiguredMailRepository(get_db()).complete(data)

    @app.route('/api/emails/<int:email_id>/analysis-retry', methods=['POST'])
    @require_api_key
    @handle_errors
    def retry_unconfigured_analysis(email_id):
        repo = UnconfiguredMailRepository(get_db())
        repo.retry(email_id, body().get('task_type'), principal=g.principal)
        return repo.projection(email_id)

    @app.route('/api/emails/<int:email_id>/analysis', methods=['GET'])
    @require_api_key
    @handle_errors
    def unconfigured_analysis_detail(email_id):
        db = get_db()
        record = db.get_email_record_by_id(email_id)
        if not record:
            raise LookupError('邮件不存在')
        return UnconfiguredMailRepository(db).projection(email_id)

    @app.route('/api/suppliers/sample-attachment-source', methods=['POST'])
    @require_api_key
    @handle_errors
    def supplier_sample_attachment_source():
        """Resolve configured samples, including old configs without a source ID."""
        from email_attachments import build_attachment_url

        data = body()
        source_id = data.get('source_email_records_id')
        if source_id is not None and (type(source_id) is not int or source_id <= 0):
            raise ValueError('样本来源邮件编号无效')
        db = get_db()
        scope, params = UserAccessRepository.email_scope(g.principal)
        with db.get_connection() as conn:
            if source_id is not None:
                row = conn.execute(f'SELECT id,attachments FROM email_records WHERE id=? AND {scope}', [source_id, *params]).fetchone()
                if not row:
                    raise LookupError('来源邮件不存在或未获授权')
            else:
                subject, content = data.get('subject'), data.get('content')
                if not isinstance(subject, str) or not isinstance(content, str):
                    raise ValueError('样本主题和正文必须是文本')
                if not subject.strip() and not content.strip():
                    return None
                rows = conn.execute(f"""SELECT id,attachments FROM email_records
                    WHERE trim(subject, char(9)||char(10)||char(13)||' ')=?
                    AND trim(coalesce(nullif(html_content,''),content,''), char(9)||char(10)||char(13)||' ')=?
                    AND {scope} ORDER BY id LIMIT 2""", [subject.strip(), content.strip(), *params]).fetchall()
                # Never guess between identical bodies with different attachments.
                if len(rows) != 1:
                    return None
                row = rows[0]
        return {'id': row['id'], 'attachment_urls': [build_attachment_url(path)
            for path in db.deserialize_attachments(row['attachments'])]}

    @app.route('/api/emails/<int:email_id>/source', methods=['GET'])
    @require_api_key
    @handle_errors
    def supplier_sample_source(email_id):
        from email_attachments import build_attachment_url

        record = get_db().get_email_record_by_id(email_id)
        if not record:
            raise LookupError('邮件不存在')
        result = {key: record.get(key) for key in ('id', 'subject', 'sender', 'receiver', 'content', 'html_content', 'mail_type', 'create_time')}
        result['preview_html'] = build_mail_preview(result['html_content'])
        result['attachment_urls'] = [build_attachment_url(path) for path in record.get('attachments', [])]
        return result
