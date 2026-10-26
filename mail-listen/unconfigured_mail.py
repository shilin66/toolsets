"""未配置供应商的动态处理策略；策略跳过仅由调用方写运行日志。"""

import json
import re
from email.utils import parseaddr


DEFAULT_SETTINGS = {
    'supplier_auto_discovery_enabled': False,
    'unconfigured_cutover_analysis_enabled': False,
    'unconfigured_sender_filter_mode': 'all',
    'unconfigured_sender_filter_list': [],
}
DISCOVERY = 'supplier_auto_discovery_enabled'
ANALYSIS = 'unconfigured_cutover_analysis_enabled'
MAIL_TYPES = ('割接通知', '割接改期', '割接取消', '割接提醒', '故障邮件', '其它')
ADDRESS_PATTERN = re.compile(r"[a-z0-9.!#$%&'+/=?^_`{|}~-]+@(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", re.I)


def normalize_sender(value: str) -> str:
    return parseaddr(value or '')[1].strip().lower()


def validate_settings(values: dict) -> dict:
    result = {key: values.get(key, default) for key, default in DEFAULT_SETTINGS.items()}
    for key in (DISCOVERY, ANALYSIS):
        if type(result[key]) is not bool:
            raise ValueError(f'{key} 必须是布尔值')
    if result['unconfigured_sender_filter_mode'] not in ('all', 'allowlist', 'blocklist'):
        raise ValueError('发件人过滤方式无效')
    rules = result['unconfigured_sender_filter_list']
    if not isinstance(rules, list) or any(not isinstance(rule, str) for rule in rules):
        raise ValueError('发件人名单必须是字符串数组')
    normalized = []
    for rule in rules:
        rule = rule.strip().lower()
        address = 'domain-check' + rule[1:] if rule.startswith('*@') else rule
        if not ADDRESS_PATTERN.fullmatch(address):
            raise ValueError('名单仅支持完整邮箱地址或 *@example.com')
        if rule not in normalized:
            normalized.append(rule)
    if result['unconfigured_sender_filter_mode'] == 'allowlist' and not normalized:
        raise ValueError('仅处理指定发件人时，名单不能为空')
    result['unconfigured_sender_filter_list'] = normalized
    return result


def read_settings(db, conn=None) -> dict:
    if conn is None:
        with db.get_connection() as connection:
            return read_settings(db, connection)
    stored = dict(conn.execute('SELECT key, value FROM system_settings').fetchall())
    return validate_settings({key: json.loads(stored[key]) if key in stored else default
                              for key, default in DEFAULT_SETTINGS.items()})


def accepts_sender(values: dict, sender: str) -> bool:
    mode = values['unconfigured_sender_filter_mode']
    if mode == 'all':
        return True
    address = normalize_sender(sender)
    domain = address.rpartition('@')[2]
    matched = any(rule == address or rule == '*@' + domain
                  for rule in values['unconfigured_sender_filter_list'])
    return matched if mode == 'allowlist' else not matched


def accepted_branches(values: dict, sender: str) -> dict:
    allowed = accepts_sender(values, sender)
    return {key: allowed and values[key] for key in (DISCOVERY, ANALYSIS)}
