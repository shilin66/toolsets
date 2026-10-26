import json
from functools import wraps

from flask import jsonify, request
from pydantic import ValidationError

from fastgpt_contracts import validate_draft_config
from mail_preview import build_mail_preview
from supplier_config import SupplierConfigCreate, SupplierConfigRepository
from unconfigured_mail_repository import ResultConflict, UnconfiguredMailRepository


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
    def __init__(self, db):
        self.db = db

    @staticmethod
    def serialize(row):
        item = dict(row)
        item['draft'] = json.loads(item.pop('draft_json')) if item.get('draft_json') else None
        item.pop('draft_json', None)
        return item

    def list(self, page=1, page_size=20, status='unpublished'):
        if status not in ('unpublished', 'published'):
            raise ValueError('草稿筛选状态必须为 unpublished 或 published')
        condition = "d.status = 'published'" if status == 'published' else "d.status != 'published'"
        with self.db.get_connection() as conn:
            total = conn.execute(f'SELECT count(*) FROM supplier_drafts d WHERE {condition}').fetchone()[0]
            rows = conn.execute(f'''SELECT d.*, count(s.email_records_id) AS sample_count
                FROM supplier_drafts d LEFT JOIN supplier_draft_samples s ON s.draft_id=d.id
                WHERE {condition}
                GROUP BY d.id ORDER BY d.update_time DESC, d.id DESC LIMIT ? OFFSET ?''',
                (page_size, (page - 1) * page_size)).fetchall()
            return {'items': [self.serialize(row) for row in rows], 'total': total,
                    'page': page, 'pageSize': page_size}

    def get(self, draft_id, page=1, page_size=20):
        with self.db.get_connection() as conn:
            row = conn.execute('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,)).fetchone()
            if not row:
                raise LookupError('供应商草稿不存在')
            item = self.serialize(row)
            samples = conn.execute('''SELECT e.id, e.subject, e.sender, e.receiver, e.mail_type,
                e.create_time, substr(e.content, 1, 300) AS content_summary
                FROM supplier_draft_samples s JOIN email_records e ON e.id=s.email_records_id
                WHERE s.draft_id=? ORDER BY e.id DESC LIMIT ? OFFSET ?''',
                (draft_id, page_size, (page - 1) * page_size)).fetchall()
            counts = conn.execute('''SELECT e.mail_type, count(*) AS count FROM supplier_draft_samples s
                JOIN email_records e ON e.id=s.email_records_id WHERE s.draft_id=? GROUP BY e.mail_type''',
                (draft_id,)).fetchall()
            item.update(samples=[dict(sample) for sample in samples],
                        sample_counts={row['mail_type']: row['count'] for row in counts})
            item['sample_count'] = sum(item['sample_counts'].values())
            return item

    def edit(self, draft_id, revision, config):
        if type(revision) is not int or not isinstance(config, dict):
            raise ValueError('必须提供 revision 和配置对象 config')
        validate_draft_config(config)
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,)).fetchone()
            if not row:
                raise LookupError('供应商草稿不存在')
            if row['status'] != 'review' or row['revision'] != revision:
                raise ResultConflict('草稿状态或版本已变化，请刷新后重试')
            value = json.loads(row['draft_json'])
            value['config'] = {**config, 'email': row['sender']}
            conn.execute('''UPDATE supplier_drafts SET draft_json=?, revision=revision+1,
                update_time=CURRENT_TIMESTAMP WHERE id=?''', (json.dumps(value, ensure_ascii=False), draft_id))
            conn.commit()
        return self.get(draft_id)

    def delete(self, draft_id, revision):
        if type(revision) is not int:
            raise ValueError('必须提供整数 revision')
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT revision FROM supplier_drafts WHERE id=?', (draft_id,)).fetchone()
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

    def publish(self, draft_id, revision):
        if type(revision) is not int:
            raise ValueError('必须提供整数 revision')
        SupplierConfigRepository(self.db)
        with self.db.get_connection() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT * FROM supplier_drafts WHERE id=?', (draft_id,)).fetchone()
            if not row:
                raise LookupError('供应商草稿不存在')
            if row['revision'] != revision:
                raise ResultConflict('草稿版本已变化，请刷新后重试')
            if row['status'] == 'published':
                return {'supplier_id': row['published_supplier_id'], 'draft_id': draft_id}
            if row['status'] != 'review':
                raise ResultConflict('当前草稿尚不可发布')
            config = json.loads(row['draft_json'])['config']
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
            for key in ('line_custom_fields', 'line_query_keywords', 'fixed_field_rules', 'custom_fields', 'email_type_samples'):
                values[key] = json.dumps(values[key], ensure_ascii=False)
            columns = ', '.join(values)
            placeholders = ', '.join('?' for _ in values)
            inserted = conn.execute(f'''INSERT INTO supplier_configs ({columns}, create_time, update_time)
                VALUES ({placeholders}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)''', list(values.values()))
            supplier_id = inserted.lastrowid
            conn.execute('''UPDATE supplier_drafts SET status='published', published_supplier_id=?,
                update_time=CURRENT_TIMESTAMP WHERE id=?''', (supplier_id, draft_id))
            conn.commit()
            return {'supplier_id': supplier_id, 'draft_id': draft_id}


def register_routes(app, get_db, require_api_key):
    def handle_errors(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            try:
                return jsonify({'success': True, 'data': func(*args, **kwargs)})
            except LookupError as exc:
                return jsonify({'success': False, 'message': str(exc)}), 404
            except ResultConflict as exc:
                return jsonify({'success': False, 'message': str(exc)}), 409
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
        return SupplierDraftRepository(get_db()).list(*pagination(), status=request.args.get('status', 'unpublished'))

    @app.route('/api/supplier-drafts/<int:draft_id>', methods=['GET', 'PUT', 'DELETE'])
    @require_api_key
    @handle_errors
    def supplier_draft_detail(draft_id):
        repo = SupplierDraftRepository(get_db())
        if request.method == 'GET':
            return repo.get(draft_id, *pagination())
        data = body()
        if request.method == 'DELETE':
            return repo.delete(draft_id, data.get('revision'))
        return repo.edit(draft_id, data.get('revision'), data.get('config'))

    @app.route('/api/supplier-drafts/<int:draft_id>/publish', methods=['POST'])
    @require_api_key
    @handle_errors
    def publish_supplier_draft(draft_id):
        return SupplierDraftRepository(get_db()).publish(draft_id, body().get('revision'))

    @app.route('/api/supplier-drafts/<int:draft_id>/retry', methods=['POST'])
    @require_api_key
    @handle_errors
    def retry_supplier_draft(draft_id):
        db = get_db()
        draft = SupplierDraftRepository(db).get(draft_id)
        if draft['status'] != 'generation_failed':
            raise ResultConflict('只允许重试生成失败的草稿')
        UnconfiguredMailRepository(db).retry(draft['source_email_records_id'], 'supplier_config_draft')
        return SupplierDraftRepository(db).get(draft_id)

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
        repo.retry(email_id, body().get('task_type'))
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
