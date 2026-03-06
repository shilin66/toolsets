"""
邮件监听服务主模块
"""
import time
import signal
import sys
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

from config import settings
from email_client import EmailClient
from filters import EmailFilter, create_default_rules
from actions import ActionManager
from models import EmailMessage, FilterRule
from database import email_db


class MailListener:
    """邮件监听服务"""
    
    def __init__(self):
        self.email_client = EmailClient()
        self.email_filter = EmailFilter()
        self.action_manager = ActionManager()
        self.running = False
        
        # 并发处理配置
        self.concurrent_processing = settings.concurrent_processing
        self.max_concurrent_emails = settings.max_concurrent_emails
        self.executor = None
        
        if self.concurrent_processing:
            self.executor = ThreadPoolExecutor(
                max_workers=self.max_concurrent_emails,
                thread_name_prefix="EmailProcessor"
            )
        
        # 设置日志
        logger.remove()
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        )
        
        # 创建日志目录
        import os
        os.makedirs("logs", exist_ok=True)
        
        logger.add(
            "logs/mail_listener.log",
            rotation="1 day",
            retention="30 days",
            level=settings.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
        )
        
        # 加载默认过滤规则
        self._load_default_rules()
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _load_default_rules(self):
        """加载默认过滤规则"""
        default_rules = create_default_rules()
        for rule in default_rules:
            self.email_filter.add_rule(rule)
    
    def add_filter_rule(self, rule: FilterRule):
        """添加过滤规则"""
        self.email_filter.add_rule(rule)
    
    def remove_filter_rule(self, rule_name: str):
        """移除过滤规则"""
        self.email_filter.remove_rule(rule_name)
    
    def get_filter_rules(self) -> List[FilterRule]:
        """获取所有过滤规则"""
        return self.email_filter.rules
    
    def start(self):
        """启动邮件监听服务"""
        logger.info("启动邮件监听服务...")
        logger.info(f"邮箱: {settings.email_address}")
        logger.info(f"IMAP服务器: {settings.imap_server}:{settings.imap_port} (SSL: {settings.imap_use_ssl})")
        
        if settings.email_hours_filter > 0:
            logger.info(f"邮件时间过滤: 监听 {settings.email_hours_filter} 小时内的邮件")
        else:
            logger.info("邮件时间过滤: 监听所有邮件")
        logger.info(f"过滤规则数量: {len(self.email_filter.rules)}")
        
        self.running = True
        
        # 初始连接测试
        if not self.email_client.connect():
            logger.error("无法连接到邮箱服务器，服务启动失败")
            return
        
        try:
            if settings.imap_idle_support:
                # 测试IDLE支持
                if self.email_client.test_idle_support():
                    logger.info("使用IDLE模式进行实时监听")
                    logger.info(f"IDLE超时时间: {settings.idle_timeout}秒")
                    logger.info(f"IDLE检查间隔: {settings.idle_check_interval}秒")
                    logger.info(f"重连延迟: {settings.idle_reconnect_delay}秒")
                    self._start_idle_mode()
                else:
                    logger.warning("服务器不支持IDLE，切换到轮询模式")
                    self._start_polling_mode()
            else:
                logger.info("使用轮询模式进行监听")
                logger.info(f"检查间隔: {settings.check_interval}秒")
                self._start_polling_mode()
                
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在停止服务...")
        except Exception as e:
            logger.error(f"服务运行异常: {e}")
        finally:
            self.stop()
    
    def _start_idle_mode(self):
        """启动IDLE模式"""
        # 启动IDLE监听
        if self.email_client.start_idle_monitoring(self._on_idle_notification):
            # 主线程保持运行
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        else:
            logger.error("IDLE模式启动失败，切换到轮询模式")
            self._start_polling_mode()
    
    def _start_polling_mode(self):
        """启动轮询模式"""
        while self.running:
            self._check_emails()
            time.sleep(settings.check_interval)
    
    def _on_idle_notification(self, mail_uids=None):
        """IDLE通知回调"""
        if mail_uids:
            logger.info(f"🔔 收到IDLE新邮件通知，处理特定邮件 UID: {mail_uids}")
            try:
                self._check_specific_emails(mail_uids)
            except Exception as e:
                logger.error(f"IDLE回调处理特定邮件时出错: {e}")
        else:
            logger.info("🔔 收到IDLE通知，执行常规邮件检查...")
            try:
                self._check_emails()
            except Exception as e:
                logger.error(f"IDLE回调处理邮件时出错: {e}")
    
    def stop(self):
        """停止邮件监听服务"""
        logger.info("正在停止邮件监听服务...")
        self.running = False
        
        # 停止IDLE监听
        if settings.imap_idle_support:
            self.email_client.stop_idle_monitoring()
        
        # 停止并发处理器
        if self.executor:
            logger.info("正在停止并发处理器...")
            self.executor.shutdown(wait=True, timeout=30)
            logger.info("并发处理器已停止")
        
        self.email_client.disconnect()
        logger.info("邮件监听服务已停止")
    
    def _check_emails(self):
        """检查新邮件"""
        try:
            # 获取未读邮件
            logger.info("📧 正在检查新邮件...")
            emails = self.email_client.get_unread_messages()
            
            if not emails:
                logger.info("没有发现新的未读邮件")
                return
            
            logger.info(f"📬 发现 {len(emails)} 封未读邮件，开始处理...")
            
            # 按时间倒序排列邮件（最新的邮件优先处理）
            emails_sorted = sorted(emails, key=lambda x: x.received_date, reverse=False)
            logger.info("邮件已按时间倒序排列（最新邮件优先）")
            
            # 根据配置选择处理方式
            if self.concurrent_processing and len(emails_sorted) > 1:
                self._process_emails_concurrent(emails_sorted)
            else:
                self._process_emails_sequential(emails_sorted)
                
        except Exception as e:
            logger.error(f"检查邮件时出错: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
    
    def _check_specific_emails(self, mail_uids: List[int]):
        """检查特定UID的邮件"""
        try:
            logger.info(f"📧 正在处理特定邮件 UID: {mail_uids}")
            emails = self.email_client.get_emails_by_uids(mail_uids)
            
            if not emails:
                logger.info("没有获取到有效的邮件")
                return
            
            logger.info(f"📬 成功获取 {len(emails)} 封邮件，开始处理...")
            
            # 按时间倒序排列邮件（最新的邮件优先处理）
            emails_sorted = sorted(emails, key=lambda x: x.received_date, reverse=False)
            logger.info("邮件已按时间倒序排列（最新邮件优先）")
            
            # 根据配置选择处理方式
            if self.concurrent_processing and len(emails_sorted) > 1:
                self._process_emails_concurrent(emails_sorted)
            else:
                self._process_emails_sequential(emails_sorted)
                
        except Exception as e:
            logger.error(f"处理特定邮件时出错: {e}")
            import traceback
            logger.error(f"详细错误信息: {traceback.format_exc()}")
    
    def _process_emails_sequential(self, emails: List[EmailMessage]):
        """顺序处理邮件"""
        logger.info(f"📝 使用顺序处理模式处理 {len(emails)} 封邮件")
        
        for i, email in enumerate(emails, 1):
            logger.info(f"处理第 {i}/{len(emails)} 封邮件 (UID: {email.uid})")
            self._process_email(email)
    
    def _process_emails_concurrent(self, emails: List[EmailMessage]):
        """并发处理邮件"""
        logger.info(f"🚀 使用并发处理模式处理 {len(emails)} 封邮件（最大并发数: {self.max_concurrent_emails}）")
        
        if not self.executor:
            logger.warning("并发处理器未初始化，回退到顺序处理")
            self._process_emails_sequential(emails)
            return
        
        # 提交所有邮件处理任务
        future_to_email = {}
        for email in emails:
            future = self.executor.submit(self._process_email, email)
            future_to_email[future] = email
        
        # 等待所有任务完成
        completed_count = 0
        failed_count = 0
        
        for future in as_completed(future_to_email):
            email = future_to_email[future]
            try:
                future.result()  # 获取结果，如果有异常会抛出
                completed_count += 1
                logger.debug(f"✓ 邮件 UID {email.uid} 处理完成 ({completed_count}/{len(emails)})")
            except Exception as e:
                failed_count += 1
                logger.error(f"✗ 邮件 UID {email.uid} 处理失败: {e}")
        
        logger.info(f"🎯 并发处理完成: 成功 {completed_count} 封，失败 {failed_count} 封")
    
    def _process_email(self, email: EmailMessage):
        """处理单封邮件"""
        logger.info(f"处理邮件: {email.subject} (来自: {email.sender}) (时间: {email.received_date})")
        
        try:
            # 检查邮件是否已处理
            if email_db.email_exists(email.uid):
                logger.info(f"邮件 UID {email.uid} 已处理过，跳过")
                return
            
            # 记录邮件到数据库（只记录 email_id 和 create_time）
            if email_db.add_email_record(email.uid, sender=email.sender):
                logger.info(f"✓ 邮件 UID {email.uid} 已记录到数据库")
            else:
                logger.warning(f"邮件 UID {email.uid} 记录失败（可能已存在）")
                return
            
            # 应用过滤规则
            matched_rules = self.email_filter.filter_email(email)
            
            if not matched_rules:
                logger.info(f"邮件 '{email.subject}' 未匹配任何规则，跳过处理")
                return
            
            # 执行匹配规则的操作
            matched_rule_names = []
            
            for rule in matched_rules:
                logger.info(f"执行操作: {rule.action} (规则: {rule.name})")
                matched_rule_names.append(rule.name)
                
                result = self.action_manager.execute_action(
                    rule.action,
                    email,
                    rule.action_params
                )
                
                if result.success:
                    logger.info(f"操作执行成功: {result.message}")
                else:
                    logger.error(f"操作执行失败: {result.message}")
                    all_success = False
            
            logger.info(f"邮件 UID {email.uid} 处理完成，匹配规则: {', '.join(matched_rule_names)}")
            
            # 注意：后续的 event_id 和 type 字段更新将在业务逻辑中处理
            # 当前只记录邮件已被处理
                    
        except Exception as e:
            logger.error(f"处理邮件时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，正在停止服务...")
        self.running = False


def main():
    """主函数"""
    try:
        listener = MailListener()
        listener.start()
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()