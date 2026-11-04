"""Central, default-deny HTTP authorization for mailbox-scoped users."""

import hmac
import os

from flask import g, jsonify, request

from user_access import Principal, UserAccessRepository

SESSION_COOKIE = 'noc_session'
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


def _same_secret(left, right):
    return isinstance(left, str) and isinstance(right, str) and hmac.compare_digest(left.encode(), right.encode())


def _secure_cookies():
    return request.is_secure or os.environ.get('NOC_COOKIE_SECURE', '').lower() in ('true', '1')


USER_READ_ENDPOINTS = frozenset({
    'check_admin_auth', 'auth_me', 'my_mailboxes', 'my_supplier_options',
    'list_email_records', 'get_dashboard_summary', 'list_ticket_records',
    'list_cutover_tasks', 'list_cutover_task_emails', 'list_cutover_email_mail_types',
    'get_cutover_template_columns',
    'operations_options', 'operations_summary', 'operations_suppliers', 'operations_details', 'operations_export',
})
PERSONAL_RPA_ENDPOINTS = frozenset({
    'get_rpa_session_status', 'begin_rpa_session_attempt', 'refresh_rpa_session_captcha',
    'login_rpa_session_with_password', 'request_rpa_session_sms', 'verify_rpa_session_sms',
    'logout_rpa_session',
})
USER_MANAGEMENT_ENDPOINTS = frozenset({'manage_users', 'user_mailboxes', 'update_user', 'release_user_portal_session'})
MAIL_CONFIGURATION_ENDPOINTS = frozenset({
    'list_mail_accounts_api', 'create_mail_account_api', 'update_mail_account_api',
    'delete_mail_account_api', 'mail_accounts_status_api', 'test_mail_account_preview_api', 'test_mail_account_api',
})
SHARED_CONFIGURATION_ENDPOINTS = frozenset({
    'list_supplier_configs', 'create_supplier_config', 'list_supplier_mail_types',
    'list_supplier_field_defaults', 'preview_supplier_prompt', 'upload_supplier_preview_attachment',
    'supplier_sample_attachment_source', 'preview_supplier_attachment_content', 'preview_supplier_extract', 'preview_supplier_sample', 'import_supplier_eml', 'get_supplier_config', 'update_supplier_config', 'delete_supplier_config',
    'query_circuits', 'list_circuits_admin', 'create_circuit_admin', 'update_circuit_admin',
    'delete_circuit_admin', 'export_circuits_xlsx', 'import_circuits_xlsx', 'generate_template_xlsx',
    'get_system_settings', 'update_system_settings', 'list_supplier_drafts',
})
DRAFT_ENDPOINTS = frozenset({'exclude_supplier_draft_sender', 'supplier_draft_detail', 'publish_supplier_draft', 'retry_supplier_draft'})
REPORT_ENDPOINTS = frozenset({'get_cutover_report_route', 'resolve_interrupted_report',
                              'pause_cutover_report', 'resume_cutover_report'})
EMAIL_ENDPOINTS = frozenset({
    'preview_cutover_attachment',
    'get_cutover_email_detail', 'update_cutover_email_read_state', 'delete_cutover_email_route',
    'retry_cutover_email_api_forward', 'update_cutover_line_binding', 'update_cutover_extraction',
    'generate_cutover_tasks', 'reply_cutover_email', 'confirm_cutover_reply', 'cancel_cutover_reply',
    'unconfigured_analysis_detail', 'supplier_sample_source', 'retry_unconfigured_analysis',
    'update_cutover_scene', 'create_ticket', 'save_unconfigured_mail_result',
})
TASK_ENDPOINTS = frozenset({
    'get_cutover_task', 'edit_cutover_task', 'switch_cutover_task_type', 'confirm_cutover_task',
    'report_cutover_task_route', 'download_cutover_task_excel',
})
FILE_ENDPOINTS = frozenset({'download_email_attachment', 'view_email_image', 'get_rpa_report_artifact',
                            'download_template_xlsx'})


def denied(message='无权执行此操作', status=403):
    return jsonify(success=False, message=message), status


def current_principal() -> Principal:
    return g.principal


def _email_id(db, endpoint):
    arguments = request.view_args or {}
    if endpoint in TASK_ENDPOINTS:
        task = db.get_cutover_task(arguments.get('task_id'))
        return task['email_records_id'] if task else None
    if endpoint in REPORT_ENDPOINTS:
        report = db.get_cutover_report(arguments.get('report_id'))
        task = db.get_cutover_task(report['task_id']) if report else None
        return task['email_records_id'] if task else None
    if 'email_records_id' in arguments:
        return arguments['email_records_id']
    if endpoint in {'unconfigured_analysis_detail', 'supplier_sample_source', 'retry_unconfigured_analysis'}:
        return arguments.get('email_id')
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValueError('请求必须包含 email_records_id')
    value = body.get('email_records_id')
    if type(value) is bool or value is None:
        raise ValueError('请使用邮件记录 ID（email_records_id），不能使用跨邮箱重复的邮件 UID')
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError('email_records_id 必须是整数') from error


def register_access_routes(app, get_db, get_admin_key, get_data_dir):
    def repository():
        return UserAccessRepository(get_db())

    @app.before_request
    def authenticate_and_authorize():
        if not request.path.startswith('/api/'):
            return None
        if request.endpoint in {'auth_login', 'auth_session'}:
            return None
        if request.endpoint in {'download_email_attachment', 'view_email_image'} and request.method in {'GET', 'HEAD'}:
            from artifact_access import verify_artifact_token
            if verify_artifact_token(request.path, request.args.get('access_token'), get_admin_key()):
                return None
        repo = repository()
        authorization = request.headers.get('Authorization')
        g.csrf_token = ''
        if authorization:
            key = get_admin_key()
            if not key or not _same_secret(authorization, f'Bearer {key}'):
                return denied('登录凭据无效', 401)
            g.principal = Principal.admin()
        else:
            session = repo.resolve_session(request.cookies.get(SESSION_COOKIE, ''), get_admin_key())
            if session is None:
                return denied('请先登录', 401)
            g.principal, g.csrf_token = session
            if request.method not in SAFE_METHODS:
                supplied = request.headers.get('X-CSRF-Token', '')
                if not supplied or not _same_secret(supplied, g.csrf_token):
                    return denied('请求校验失败，请刷新页面后重试')
        principal, endpoint = g.principal, request.endpoint
        if principal.is_admin and endpoint in PERSONAL_RPA_ENDPOINTS | {'report_cutover_task_route'}:
            return denied('API Key 管理员不能使用综调会话或上报，请使用普通用户账号登录')
        if principal.is_admin:
            return None
        if endpoint in USER_MANAGEMENT_ENDPOINTS:
            return denied('用户与邮箱授权仅管理员可管理')
        if endpoint in MAIL_CONFIGURATION_ENDPOINTS:
            return denied('邮箱配置仅管理员可使用')
        if endpoint in SHARED_CONFIGURATION_ENDPOINTS:
            return None
        if endpoint in DRAFT_ENDPOINTS:
            if repo.can_access_draft(principal, request.view_args['draft_id'], operate=request.method not in SAFE_METHODS):
                return None
            return denied('草稿不存在或来源邮箱未获授权', 404)
        if endpoint in USER_READ_ENDPOINTS and request.method in SAFE_METHODS:
            return None
        if endpoint in PERSONAL_RPA_ENDPOINTS or endpoint == 'auth_logout':
            return None
        if endpoint in EMAIL_ENDPOINTS | TASK_ENDPOINTS | REPORT_ENDPOINTS:
            try:
                email_id = _email_id(get_db(), endpoint)
            except ValueError as error:
                return denied(str(error), 400)
            if email_id is None or not repo.can_access_email(principal, email_id):
                return denied('记录不存在或未获授权', 404)
            if request.method not in SAFE_METHODS and not repo.can_access_email(principal, email_id, operate=True):
                return denied('当前邮箱仅授予查看权限')
            if endpoint == 'retry_unconfigured_analysis':
                body = request.get_json(silent=True) or {}
                if isinstance(body, dict) and body.get('task_type') == 'supplier_config_draft':
                    with get_db().get_connection() as conn:
                        drafts = conn.execute("SELECT draft_id FROM mail_ai_jobs WHERE email_records_id=? AND task_type='supplier_config_draft' AND status='failed' AND draft_id IS NOT NULL", (email_id,)).fetchall()
                    if any(not repo.can_access_draft(principal, row['draft_id'], operate=True) for row in drafts):
                        return denied('草稿相关邮箱未授予操作权限')
            return None
        if endpoint in FILE_ENDPOINTS and request.method in SAFE_METHODS:
            from access_artifacts import can_access_artifact
            if can_access_artifact(get_db(), principal, endpoint, request.view_args or {}, get_data_dir()):
                return None
            return denied('文件不存在或未获授权', 404)
        return denied()

    @app.after_request
    def protect_authenticated_responses(response):
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.post('/api/auth/login')
    def auth_login():
        origin = request.headers.get('Origin')
        # The explicit HTTPS deployment setting also covers TLS terminated by a proxy.
        expected_origin = f'https://{request.host}' if _secure_cookies() else request.host_url.rstrip('/')
        if origin and origin != expected_origin:
            return denied('不允许跨站登录')
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return denied('请提供登录信息', 400)
        repo = repository()
        if not repo.record_login_attempt(request.remote_addr or 'unknown'):
            return denied('登录尝试过于频繁，请五分钟后重试', 429)
        principal = None
        if payload.get('mode') == 'admin':
            key = payload.get('api_key')
            if get_admin_key() and _same_secret(key, get_admin_key()):
                principal = Principal.admin()
        else:
            principal = repo.verify_user(payload.get('username'), payload.get('password'))
        if principal is None:
            return denied('用户名、密码或 API Key 不正确', 401)
        repo.record_login_attempt(request.remote_addr or 'unknown', success=True)
        repo.revoke_session(request.cookies.get(SESSION_COOKIE, ''))
        token, csrf = repo.create_session(principal, get_admin_key())
        response = jsonify(success=True, data={**principal.public(), 'csrf_token': csrf})
        response.set_cookie(SESSION_COOKIE, token, max_age=12 * 3600, httponly=True,
                            secure=_secure_cookies(),
                            samesite='Strict', path='/')
        return response

    @app.get('/api/auth/me')
    def auth_me():
        return jsonify(success=True, data={**g.principal.public(), 'csrf_token': g.csrf_token})

    @app.get('/api/auth/session')
    def auth_session():
        session = repository().resolve_session(request.cookies.get(SESSION_COOKIE, ''), get_admin_key())
        data = {**session[0].public(), 'csrf_token': session[1]} if session else None
        return jsonify(success=True, data=data)

    @app.post('/api/auth/logout')
    def auth_logout():
        repository().revoke_session(request.cookies.get(SESSION_COOKIE, ''))
        response = jsonify(success=True)
        response.delete_cookie(SESSION_COOKIE, path='/', httponly=True, samesite='Strict')
        return response

    @app.route('/api/users', methods=['GET', 'POST'])
    def manage_users():
        repo = repository()
        if request.method == 'GET':
            return jsonify(success=True, data=repo.list_users())
        body = request.get_json(silent=True) or {}
        try:
            user = repo.create_user(body.get('username'), body.get('password'), body.get('display_name', ''))
        except (ValueError, AttributeError) as error:
            return denied(str(error), 400)
        return jsonify(success=True, data=user), 201

    @app.route('/api/users/<int:user_id>/mailboxes', methods=['GET', 'PUT'])
    def user_mailboxes(user_id):
        repo = repository()
        if request.method == 'PUT':
            body = request.get_json(silent=True) or {}
            try:
                repo.set_grants(user_id, body.get('grants'))
            except (ValueError, AttributeError) as error:
                return denied(str(error), 400)
        return jsonify(success=True, data=repo.list_grants(user_id))

    @app.patch('/api/users/<int:user_id>')
    def update_user(user_id):
        try:
            repository().update_user(user_id, request.get_json(silent=True))
        except ValueError as error:
            return denied(str(error), 400)
        return jsonify(success=True)

    @app.get('/api/me/mailboxes')
    def my_mailboxes():
        return jsonify(success=True, data=repository().mailbox_options(g.principal))

    @app.get('/api/me/suppliers')
    def my_supplier_options():
        from supplier_config import SupplierConfigRepository
        SupplierConfigRepository(get_db())
        scope, params = repository().email_scope(g.principal)
        with get_db().get_connection() as conn:
            rows = conn.execute(f'''SELECT DISTINCT sc.name FROM supplier_configs sc
                JOIN email_records ON lower(sc.email)=lower(email_records.sender)
                WHERE {scope} ORDER BY sc.name''', params).fetchall()
        return jsonify(success=True, data=[{'name': row['name']} for row in rows])
