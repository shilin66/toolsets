"""
邮件操作处理模块
"""
import uuid
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any
from loguru import logger

from models import EmailMessage, ActionResult, APIRequest
from config import settings


class BaseAction(ABC):
    """操作基类"""
    
    @abstractmethod
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """执行操作"""
        pass


class APIForwardAction(BaseAction):
    """API转发操作"""
    
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """转发邮件到API"""
        try:
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
                json=api_request.dict(),
                headers=headers,
                timeout=settings.api_timeout,
                verify=False
            )
            
            if response.status_code == 200 or response.status_code == 202:
                logger.info(f"成功转发邮件到API: {email.subject}")
                return ActionResult(
                    success=True,
                    message="邮件转发成功",
                    data={"chat_id": chat_id, "response": response.json()}
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
    
    def _build_content(self, email: EmailMessage, params: Dict[str, Any]) -> str:
        """构建邮件内容"""
        priority = params.get('priority', '')
        category = params.get('category', '')
        
        content_parts = []
        
        # 添加优先级和分类信息
        # if priority:
        #     content_parts.append(f"优先级: {priority}")
        # if category:
        #     content_parts.append(f"分类: {category}")
        
        # 添加邮件基本信息
        content_parts.extend([
            f"邮件ID: {email.uid}\n"
            f"标题: {email.subject}",
            f"发件人: {email.sender}",
            # f"收件时间: {email.received_date.strftime('%Y-%m-%d %H:%M:%S')}",
            f"正文: {email.content}"
        ])
        
        # 添加附件信息
        if email.attachments:
            content_parts.append(f"附件: {', '.join(email.attachments)}")
        
        return "\n".join(content_parts)


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