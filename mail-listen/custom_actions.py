"""
自定义操作示例
"""
import json
import os
from typing import Dict, Any
from datetime import datetime
from actions import BaseAction
from models import EmailMessage, ActionResult
from loguru import logger


class SaveToFileAction(BaseAction):
    """保存邮件到文件的操作"""
    
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """保存邮件到文件"""
        try:
            # 获取保存目录
            save_dir = params.get('directory', 'saved_emails')
            os.makedirs(save_dir, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{timestamp}_{email.uid}.json"
            filepath = os.path.join(save_dir, filename)
            
            # 构建邮件数据
            email_data = {
                'uid': email.uid,
                'subject': email.subject,
                'sender': email.sender,
                'recipients': email.recipients,
                'content': email.content,
                'html_content': email.html_content,
                'received_date': email.received_date.isoformat(),
                'attachments': email.attachments,
                'saved_at': datetime.now().isoformat()
            }
            
            # 保存到文件
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(email_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"邮件已保存到文件: {filepath}")
            
            return ActionResult(
                success=True,
                message=f"邮件已保存到 {filepath}",
                data={'filepath': filepath}
            )
            
        except Exception as e:
            logger.error(f"保存邮件到文件失败: {e}")
            return ActionResult(
                success=False,
                message=f"保存失败: {str(e)}"
            )


class WebhookAction(BaseAction):
    """Webhook通知操作"""
    
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """发送Webhook通知"""
        try:
            import requests
            
            webhook_url = params.get('url')
            if not webhook_url:
                return ActionResult(
                    success=False,
                    message="Webhook URL未配置"
                )
            
            # 构建通知数据
            payload = {
                'type': 'email_received',
                'data': {
                    'subject': email.subject,
                    'sender': email.sender,
                    'received_date': email.received_date.isoformat(),
                    'content_preview': email.content[:200] + '...' if len(email.content) > 200 else email.content
                },
                'timestamp': datetime.now().isoformat()
            }
            
            # 发送Webhook
            from config import settings
            response = requests.post(
                webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=settings.api_timeout
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook通知发送成功: {email.subject}")
                return ActionResult(
                    success=True,
                    message="Webhook通知发送成功"
                )
            else:
                logger.error(f"Webhook通知发送失败: {response.status_code}")
                return ActionResult(
                    success=False,
                    message=f"Webhook发送失败: {response.status_code}"
                )
                
        except Exception as e:
            logger.error(f"Webhook通知异常: {e}")
            return ActionResult(
                success=False,
                message=f"Webhook通知异常: {str(e)}"
            )


class EmailStatsAction(BaseAction):
    """邮件统计操作"""
    
    def __init__(self):
        self.stats_file = 'email_stats.json'
        self.stats = self._load_stats()
    
    def _load_stats(self) -> Dict[str, Any]:
        """加载统计数据"""
        try:
            if os.path.exists(self.stats_file):
                with open(self.stats_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载统计数据失败: {e}")
        
        return {
            'total_emails': 0,
            'senders': {},
            'daily_count': {},
            'last_updated': None
        }
    
    def _save_stats(self):
        """保存统计数据"""
        try:
            with open(self.stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存统计数据失败: {e}")
    
    def execute(self, email: EmailMessage, params: Dict[str, Any]) -> ActionResult:
        """更新邮件统计"""
        try:
            # 更新总数
            self.stats['total_emails'] += 1
            
            # 更新发件人统计
            sender = email.sender
            if sender in self.stats['senders']:
                self.stats['senders'][sender] += 1
            else:
                self.stats['senders'][sender] = 1
            
            # 更新日期统计
            date_key = email.received_date.strftime('%Y-%m-%d')
            if date_key in self.stats['daily_count']:
                self.stats['daily_count'][date_key] += 1
            else:
                self.stats['daily_count'][date_key] = 1
            
            # 更新时间戳
            self.stats['last_updated'] = datetime.now().isoformat()
            
            # 保存统计数据
            self._save_stats()
            
            logger.info(f"邮件统计已更新: 总计 {self.stats['total_emails']} 封邮件")
            
            return ActionResult(
                success=True,
                message="邮件统计已更新",
                data=self.stats
            )
            
        except Exception as e:
            logger.error(f"更新邮件统计失败: {e}")
            return ActionResult(
                success=False,
                message=f"统计更新失败: {str(e)}"
            )


# 使用示例：在mail_listener.py中注册这些自定义操作
def register_custom_actions(action_manager):
    """注册自定义操作"""
    action_manager.register_action('save_to_file', SaveToFileAction())
    action_manager.register_action('webhook', WebhookAction())
    action_manager.register_action('stats', EmailStatsAction())