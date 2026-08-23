"""
邮件操作处理模块
"""
import json
import uuid
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any
from loguru import logger

from models import EmailMessage, ActionResult, APIRequest
from config import settings
from database import email_db
from email_attachments import build_attachment_url
from html_image import render_email_body_to_image_url
from supplier_config import SupplierConfigRepository


class BaseAction(ABC):
    """操作基类"""
    
    @abstractmethod
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """执行操作"""
        pass


def extract_fastgpt_reply(payload) -> str:
    """兼容 FastGPT 的多种返回格式，提取回复文本。"""
    if not isinstance(payload, dict):
        return str(payload)
    choices = payload.get('choices')
    if isinstance(choices, list) and choices:
        message = choices[0].get('message') or {}
        if message.get('content'):
            return message['content']
    data = payload.get('data')
    if isinstance(data, dict) and data.get('responseText'):
        return data['responseText']
    if payload.get('responseText'):
        return payload['responseText']
    return json.dumps(payload, ensure_ascii=False, indent=2)


def extract_json_objects(text: str) -> list:
    """从 AI 返回文本中提取所有顶层 JSON 对象（容忍 ``` 围栏与 --- 分隔）。

    与供应商配置页「预览提取」的前端解析逻辑一致：括号配对扫描，
    解析失败的片段直接跳过。
    """
    objects = []
    cleaned = (text or "").replace("```json", "").replace("```", "")
    index = 0
    while index < len(cleaned):
        start = cleaned.find("{", index)
        if start == -1:
            break
        depth = 0
        in_string = False
        escaped = False
        end = -1
        for j in range(start, len(cleaned)):
            ch = cleaned[j]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end == -1:
            break
        try:
            parsed = json.loads(cleaned[start:end + 1])
            if isinstance(parsed, dict):
                objects.append(parsed)
        except json.JSONDecodeError:
            pass
        index = end + 1
    return objects


def parse_mail_type_from_ai_reply(text: str) -> str:
    """从 FastGPT 返回文本中解析邮件分类结果 mail_type，解析不到返回空字符串。"""
    for obj in extract_json_objects(text or ""):
        mail_type = obj.get("mail_type")
        if isinstance(mail_type, str) and mail_type.strip():
            return mail_type.strip()
    return ""


def build_security_time(db) -> str:
    """从系统配置读取重保时间，拼接为 开始时间/结束时间 格式，未配置时返回空字符串。"""
    settings_map = db.get_system_settings()
    guard_start = settings_map.get('guard_start_time')
    guard_end = settings_map.get('guard_end_time')
    if guard_start and guard_end:
        return f"{guard_start}/{guard_end}"
    return ""


class APIForwardAction(BaseAction):
    """API转发操作"""
    
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """转发邮件到API"""
        try:
            # 只有确定进行 API 转发的邮件才渲染正文图片（解析阶段不再转图）；
            # 渲染失败返回 None 不阻断转发，转发内容中不携带 image_url 即可
            if not email.image_url:
                email.image_url = render_email_body_to_image_url(
                    email.html_content, email.content, email.uid
                )

            # 生成随机聊天ID
            chat_id = str(uuid.uuid4())
            
            # 构建邮件内容
            content = self._build_content(email, params)
            
            # 构建API请求
            api_request = APIRequest(
                chatId=chat_id,
                stream=False,
                detail=False,
                messages=[{
                    "content": content,
                    "role": "user"
                }]
            )
            
            # 发送请求
            headers = {
                'Authorization': f'Bearer {settings.api_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(
                settings.api_url,
                json=api_request.model_dump(),
                headers=headers,
                timeout=settings.api_timeout,
                verify=False
            )
            
            if response.status_code == 200 or response.status_code == 202:
                logger.info(f"成功转发邮件到API: {email.subject}")
                response_payload = response.json()
                mail_type = self._save_ai_reply_result(email, response_payload)
                return ActionResult(
                    success=True,
                    message="邮件转发成功",
                    data={
                        "chat_id": chat_id,
                        "mail_type": mail_type,
                        "response": response_payload,
                    }
                )
            else:
                logger.error(f"API转发失败: {response.status_code} - {response.text}")
                return ActionResult(
                    success=False,
                    message=f"API转发失败: {response.status_code}"
                )
                
        except Exception as e:
            logger.error(f"API转发异常: {e}")
            return ActionResult(
                success=False,
                message=f"API转发异常: {str(e)}"
            )

    def _save_ai_reply_result(self, email: EmailMessage, response_payload) -> str:
        """解析 FastGPT 返回值：回写邮件类型与提取解析结果，失败不影响转发结果。"""
        try:
            reply_text = extract_fastgpt_reply(response_payload)
            mail_type = parse_mail_type_from_ai_reply(reply_text)
            email_record = email_db.get_email_record(email.uid)
            if email_record:
                if mail_type and email_db.update_email_record_mail_type(
                    email_record["id"], mail_type
                ):
                    logger.info(f"邮件类型已回写: UID {email.uid} -> {mail_type}")
                if reply_text.strip():
                    email_db.update_email_record_extract_result(
                        email_record["id"], reply_text
                    )
            return mail_type
        except Exception as e:
            logger.warning(f"解析回写 FastGPT 返回值失败（不影响转发）: {e}")
            return ""

    def _build_content(self, email: EmailMessage, params: Dict[str, Any]) -> str:
        """构建邮件内容"""
        priority = params.get('priority', '')
        category = params.get('category', '')
        email_record = email_db.get_email_record(email.uid)
        email_records_id = email_record.get('id') if email_record else None

        # 构建邮件内容字典
        content_dict = {
            "email_records_id": email_records_id,
            "email_id": email.uid,
            "subject": email.subject,
            "sender": email.sender,
            "content": email.html_content or email.content,
            "attachments": email.attachments,
            "attachment_urls": [
                build_attachment_url(relative_path)
                for relative_path in email.attachments
            ],
            "supplier_name": None,
            "supplier_can_reply_directly": None,
            "supplier_cutover_extract_prompt": None,
            "supplier_mail_classify_prompt": None,
            "securityTime": build_security_time(email_db),
        }
        supplier = SupplierConfigRepository(email_db).get_by_email(email.sender)
        if supplier:
            content_dict["supplier_name"] = supplier["name"]
            content_dict["supplier_can_reply_directly"] = supplier["can_reply_directly"]
            content_dict["supplier_cutover_extract_prompt"] = supplier["cutover_extract_prompt"]
            content_dict["supplier_mail_classify_prompt"] = supplier["supplier_mail_classify_prompt"]

        # 添加优先级和分类信息（如果存在）
        if priority:
            content_dict["priority"] = priority
        if category:
            content_dict["category"] = category

        if email.image_url:
            content_dict["image_url"] = email.image_url

        # 将字典转换为 JSON 字符串
        return json.dumps(content_dict, ensure_ascii=False, indent=2)


class LogAction(BaseAction):
    """日志记录操作"""
    
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """记录邮件到日志"""
        try:
            log_level = params.get('level', 'info').lower()
            message = f"邮件处理 - 标题: {email.subject}, 发件人: {email.sender}"
            
            if log_level == 'debug':
                logger.debug(message)
            elif log_level == 'info':
                logger.info(message)
            elif log_level == 'warning':
                logger.warning(message)
            elif log_level == 'error':
                logger.error(message)
            
            return ActionResult(
                success=True,
                message="日志记录成功"
            )
            
        except Exception as e:
            logger.error(f"日志记录异常: {e}")
            return ActionResult(
                success=False,
                message=f"日志记录异常: {str(e)}"
            )


class IgnoreAction(BaseAction):
    """忽略操作"""
    
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """忽略邮件"""
        logger.debug(f"忽略邮件: {email.subject}")
        return ActionResult(
            success=True,
            message="邮件已忽略"
        )


class ActionManager:
    """操作管理器"""
    
    def __init__(self):
        self.actions = {
            'api_forward': APIForwardAction(),
            'log': LogAction(),
            'ignore': IgnoreAction()
        }
    
    def register_action(self, name: str, action: BaseAction):
        """注册新的操作"""
        self.actions[name] = action
        logger.info(f"注册操作: {name}")
    
    def execute_action(self, action_name: str, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """执行操作"""
        if action_name not in self.actions:
            logger.error(f"未知操作: {action_name}")
            return ActionResult(
                success=False,
                message=f"未知操作: {action_name}"
            )
        
        try:
            return self.actions[action_name].execute(email, params)
        except Exception as e:
            logger.error(f"执行操作 {action_name} 时出错: {e}")
            return ActionResult(
                success=False,
                message=f"执行操作失败: {str(e)}"
            )
