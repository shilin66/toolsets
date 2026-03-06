"""
邮件过滤器模块
"""
import re
from typing import List, Dict, Any
from loguru import logger

from models import EmailMessage, FilterRule


class EmailFilter:
    """邮件过滤器"""
    
    def __init__(self):
        self.rules: List[FilterRule] = []
    
    def add_rule(self, rule: FilterRule):
        """添加过滤规则"""
        self.rules.append(rule)
        logger.info(f"添加过滤规则: {rule.name}")
    
    def remove_rule(self, rule_name: str):
        """移除过滤规则"""
        self.rules = [rule for rule in self.rules if rule.name != rule_name]
        logger.info(f"移除过滤规则: {rule_name}")
    
    def filter_email(self, email: EmailMessage) -> List[FilterRule]:
        """过滤邮件，返回匹配的规则"""
        matched_rules = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
                
            if self._check_conditions(email, rule.conditions):
                matched_rules.append(rule)
                logger.info(f"邮件 '{email.subject}' 匹配规则: {rule.name}")
        
        return matched_rules
    
    def _check_conditions(self, email: EmailMessage, conditions: Dict[str, Any]) -> bool:
        """检查邮件是否满足条件"""
        for field, condition in conditions.items():
            if not self._check_field_condition(email, field, condition):
                return False
        return True
    
    def _check_field_condition(self, email: EmailMessage, field: str, condition: Any) -> bool:
        """检查单个字段条件"""
        # 获取邮件字段值
        field_value = getattr(email, field, None)
        if field_value is None:
            return False
        
        # 如果是字符串字段，转换为小写进行比较
        if isinstance(field_value, str):
            field_value = field_value.lower()
        
        # 处理不同类型的条件
        if isinstance(condition, dict):
            return self._check_complex_condition(field_value, condition)
        elif isinstance(condition, str):
            # 简单字符串匹配
            return condition.lower() in field_value if isinstance(field_value, str) else False
        elif isinstance(condition, list):
            # 列表匹配（任一匹配即可）
            return any(self._check_field_condition(email, field, c) for c in condition)
        
        return False
    
    def _check_complex_condition(self, field_value: Any, condition: Dict[str, Any]) -> bool:
        """检查复杂条件"""
        condition_type = condition.get('type', 'contains')
        value = condition.get('value', '')
        
        if isinstance(field_value, str):
            field_value = field_value.lower()
            if isinstance(value, str):
                value = value.lower()
        
        if condition_type == 'contains':
            return value in field_value if isinstance(field_value, str) else False
        elif condition_type == 'equals':
            return field_value == value
        elif condition_type == 'starts_with':
            return field_value.startswith(value) if isinstance(field_value, str) else False
        elif condition_type == 'ends_with':
            return field_value.endswith(value) if isinstance(field_value, str) else False
        elif condition_type == 'regex':
            try:
                return bool(re.search(value, field_value, re.IGNORECASE)) if isinstance(field_value, str) else False
            except re.error:
                logger.error(f"正则表达式错误: {value}")
                return False
        elif condition_type == 'not_contains':
            return value not in field_value if isinstance(field_value, str) else True
        
        return False


# 预定义的过滤规则示例
def create_default_rules() -> List[FilterRule]:
    """创建默认过滤规则"""
    rules = [
        FilterRule(
            name="ipmonitor的邮件",
            conditions={
                "sender": {"type": "contains", "value": "ipmonitor@sinnet.com.cn"}
            },
            action="api_forward",
            action_params={"priority": "high"}
        ),
        FilterRule(
            name="kamonitor2的邮件",
            conditions={
                "sender": {"type": "contains", "value": "kamonitor2@sinnet.com.cn"},
            },
            action="api_forward",
            action_params={"category": "system"}
        ),
        FilterRule(
            name="shixxxxlin的邮件",
            conditions={
                "sender": {"type": "contains", "value": "shixxxxlin@gmail.com"},
            },
            action="api_forward",
            action_params={"category": "system"}
        ),
    ]
    
    return rules