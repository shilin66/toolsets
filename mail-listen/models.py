"""
数据模型定义
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
from enum import Enum


class EmailMessage(BaseModel):
    """邮件消息模型"""
    uid: int
    subject: str
    sender: str
    recipients: List[str]
    content: str
    html_content: Optional[str] = None
    received_date: datetime
    attachments: List[str] = []
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class FilterRule(BaseModel):
    """过滤规则模型"""
    name: str
    enabled: bool = True
    conditions: Dict[str, Any]  # 过滤条件
    action: str  # 执行的操作类型
    action_params: Dict[str, Any] = {}  # 操作参数


class ActionResult(BaseModel):
    """操作结果模型"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class APIRequest(BaseModel):
    """API请求模型"""
    chatId: str
    stream: bool = False
    detail: bool = False
    messages: List[Dict[str, str]]