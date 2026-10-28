import json
import math
from datetime import datetime

from email_validator import EmailNotValidError, validate_email

from cutover_prompt import check_fixed_field_rules, get_fixed_field_definitions
from supplier_config import MAIL_TYPE_OPTIONS, check_email_type_name
from unconfigured_mail import MAIL_TYPES, normalize_sender


TASK_TYPES = ('unconfigured_mail_analyze', 'supplier_config_draft', 'cutover_time_extract')


def validate_draft_config(config):
    if not isinstance(config, dict):
        raise ValueError('配置草稿必须是对象')
    for key in ('name', 'email', 'cutover_extract_prompt', 'extra_instructions'):
        if key in config and not isinstance(config[key], str):
            raise ValueError(f'草稿 {key} 必须是字符串')
    if config.get('reply_email') is not None and not isinstance(config['reply_email'], str):
        raise ValueError('草稿 reply_email 必须是字符串或 null')
    if config.get('prompt_mode', 'auto') not in ('auto', 'manual'):
        raise ValueError('草稿提示词模式无效')
    for key in ('line_custom_fields', 'custom_fields'):
        fields = config.get(key, [])
        if not isinstance(fields, list) or any(not isinstance(field, dict) or
            any(not isinstance(field.get(part, ''), str) for part in ('name', 'description')) for field in fields):
            raise ValueError(f'草稿 {key} 必须是字段对象数组')
    keywords = config.get('line_query_keywords', [])
    if not isinstance(keywords, list) or any(not isinstance(value, str) for value in keywords):
        raise ValueError('草稿 line_query_keywords 必须是字符串数组')
    rules = config.get('fixed_field_rules', {})
    if not isinstance(rules, dict) or any(not isinstance(value, str) for value in rules.values()):
        raise ValueError('草稿 fixed_field_rules 必须是字符串规则对象')
    check_fixed_field_rules(rules)
    samples = config.get('email_type_samples', {})
    if not isinstance(samples, dict):
        raise ValueError('草稿 email_type_samples 必须是对象')
    for mail_type, sample in samples.items():
        check_email_type_name(mail_type)
        if not isinstance(sample, dict) or \
            any(not isinstance(sample.get(key, ''), str) for key in ('subject', 'content')) or \
            type(sample.get('content_in_attachment', False)) is not bool:
            raise ValueError('草稿邮件类型样本结构无效')
        source_id = sample.get('source_email_records_id')
        if source_id is not None and (type(source_id) is not int or source_id <= 0):
            raise ValueError('样本来源邮件编号无效')


def merge_draft_fixed_field_supplements(result):
    """兼容旧工作流及在途结果；新草稿直接返回 fixed_field_rules 完整覆盖规则。

    仅出现旧 fixed_field_supplements 字段时合成，不能向新规则或人工规则前置默认全文。
    """
    if 'fixed_field_supplements' not in result:
        return result
    supplements = result['fixed_field_supplements']
    if not isinstance(supplements, dict) or any(not isinstance(value, str) for value in supplements.values()):
        raise ValueError('fixed_field_supplements 必须是字符串规则对象')
    check_fixed_field_rules(supplements)
    if result['config'].get('prompt_mode', 'auto') != 'auto':
        raise ValueError('固定字段补充规则仅适用于自动提示词模式')
    if result['config'].get('fixed_field_rules'):
        raise ValueError('固定字段补充规则不能与完整覆盖规则同时返回')
    defaults = {field['name']: field['description']
        for fields in get_fixed_field_definitions().values() for field in fields}
    rules = {}
    for name, value in supplements.items():
        text = value.strip()
        if text and text != defaults[name].strip():
            rules[name] = (defaults[name] + '\n\n供应商补充提取规则：\n' + text
                + '\n\n适用顺序：补充规则仅对明确列出的来源或条件优先适用；未涉及部分沿用默认规则。'
                '不得改变输出结构、UTC 转换、枚举、判定阈值及无证据不推断的约束。')
    merged = {**result, 'config': {**result['config'], 'prompt_mode': 'auto', 'fixed_field_rules': rules}}
    del merged['fixed_field_supplements']
    return merged


def normalize_ai_reply_email(value, sender):
    """Validate one AI-proposed address; compare with the stored sender, never model config.email."""
    if value is None:
        return None
    try:
        address = validate_email(value.strip(), check_deliverability=False, allow_display_name=False).normalized
    except EmailNotValidError as exc:
        raise ValueError('草稿 reply_email 必须是单个合法邮箱地址或 null') from exc
    return None if normalize_sender(address) == normalize_sender(sender) else address


def parse_response(payload):
    from actions import extract_fastgpt_reply

    if isinstance(payload, dict) and 'schema_version' in payload:
        return payload
    text = extract_fastgpt_reply(payload).strip()
    if text.startswith('```') and text.endswith('```'):
        text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError('FastGPT 结果必须是 JSON 对象')
    return result


def timestamp(value, field):
    if not isinstance(value, str):
        raise ValueError(f'{field} 必须是带时区的时间')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError(f'{field} 时间无效') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f'{field} 缺少时区')
    return parsed


def validate_envelope(envelope, job):
    if type(envelope.get('schema_version')) is not int or envelope['schema_version'] != 1:
        raise ValueError('不支持的结果版本')
    for key in ('task_type', 'request_id', 'attempt_id', 'email_records_id'):
        if type(envelope.get(key)) is not type(job[key]) or envelope[key] != job[key]:
            raise ValueError(f'结果关联字段不匹配：{key}')
    result = envelope.get('result')
    if not isinstance(result, dict):
        raise ValueError('result 必须是对象')
    task = job['task_type']
    if task == 'unconfigured_mail_analyze':
        if result.get('mail_type') not in MAIL_TYPES or type(result.get('needs_review')) is not bool:
            raise ValueError('邮件分类或待核实标记无效')
        if not isinstance(result.get('classification_reason'), str):
            raise ValueError('邮件分类缺少依据')
    elif task == 'supplier_config_draft':
        validate_draft_config(result.get('config'))
        if any(name not in MAIL_TYPE_OPTIONS for name in result['config'].get('email_type_samples', {})):
            raise ValueError('自动生成的供应商草稿仅支持预置割接分类，自定义分类请人工添加')
        for key in ('evidence', 'unresolved_questions'):
            if not isinstance(result.get(key), list) or any(not isinstance(item, str) for item in result[key]):
                raise ValueError(f'{key} 必须是字符串数组')
        result = merge_draft_fixed_field_supplements(result)
        # AI drafts use field rules unless a legacy result explicitly selects manual mode.
        # Persist this default so publishing does not fall back to the formal API's manual mode.
        result = {**result, 'config': {'prompt_mode': 'auto', **result['config'],
            # Supplier names are assigned by a reviewer, never inferred from mail.
            'name': '',
            'reply_email': normalize_ai_reply_email(result['config'].get('reply_email'), job['sender'])}}
    elif task == 'cutover_time_extract':
        validate_time_analysis(result)
    else:
        raise ValueError('未知任务类型')
    return result


def validate_time_analysis(result):
    status = result.get('analysis_status')
    if status not in ('ready', 'needs_review'):
        raise ValueError('分析状态无效')
    if not isinstance(result.get('reason'), str) or not result['reason'].strip():
        raise ValueError('分析缺少判断依据')
    timestamp(result.get('assessed_at'), 'assessed_at')
    if status == 'needs_review':
        if result.get('scene') is not None or result.get('reply') is not None:
            raise ValueError('待核实结果不能包含场景判断或回复')
        for field in ('cutover_start', 'cutover_end'):
            if result.get(field) is not None:
                timestamp(result[field], field)
        return
    scene = result.get('scene')
    if scene not in ('normal', 'emergency', 'major_event', 'in_window'):
        raise ValueError('割接场景无效')
    start = timestamp(result.get('cutover_start'), 'cutover_start')
    end = timestamp(result.get('cutover_end'), 'cutover_end')
    # Match configured suppliers: an ended window still counts as already started.
    if end < start:
        raise ValueError('割接时间倒置，应返回待核实')
    for field in ('source_timezone', 'source_time_text'):
        if not isinstance(result.get(field), str) or not result[field].strip():
            raise ValueError(f'缺少时间依据：{field}')
    hours = result.get('hours_until_start')
    if type(hours) not in (int, float) or not math.isfinite(hours):
        raise ValueError('hours_until_start 必须是有限数值')
    reply = result.get('reply')
    if scene != 'normal' and reply is None:
        raise ValueError('紧急、重保或窗口内割接缺少待审核回复')
    if reply is not None:
        if scene == 'normal' or not isinstance(reply, dict) or not isinstance(reply.get('content'), str) or not reply['content'].strip():
            raise ValueError('回复内容或场景无效')
    if scene == 'major_event':
        window = result.get('security_window')
        if not isinstance(window, dict):
            raise ValueError('重保判断缺少重保窗口')
        guard_start = timestamp(window.get('start'), 'security_window.start')
        guard_end = timestamp(window.get('end'), 'security_window.end')
        if guard_start > guard_end or start > guard_end or end < guard_start:
            raise ValueError('重保窗口无效或没有交集')
