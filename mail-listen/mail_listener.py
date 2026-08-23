"""
邮件监听服务主模块

支持多邮箱：每个启用的邮箱账号一个 MailListener（独立线程），
由 MailListenerManager 统一管理启停与热同步。
"""
import threading
import time
import signal
import sys
from datetime import datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

from config import settings, log_format
from email_client import EmailClient
from filters import EmailFilter, create_default_rules
from actions import ActionManager
from models import EmailMessage, FilterRule
from database import email_db
from supplier_config import SupplierConfigRepository
from mail_accounts import (
    MailAccountConfig,
    list_enabled_account_configs,
    seed_from_env_if_empty,
)


class MailListener:
    """邮件监听服务（单邮箱账号）"""

    def __init__(self, account: MailAccountConfig, on_email_received: Optional[callable] = None):
        self.account = account
        self.email_client = EmailClient(account)
        self.supplier_config_repository = SupplierConfigRepository(email_db)
        self.email_filter = EmailFilter(self.supplier_config_repository)
        self.action_manager = ActionManager()
        self.running = False
        self.poll_thread: threading.Thread | None = None
        # 收件回调：邮件成功入库后通知管理器更新“最后收件时间”
        self.on_email_received = on_email_received

        # 并发处理配置
        self.concurrent_processing = settings.concurrent_processing
        self.max_concurrent_emails = settings.max_concurrent_emails
        self.executor = None

        if self.concurrent_processing:
            self.executor = ThreadPoolExecutor(
                max_workers=self.max_concurrent_emails,
                thread_name_prefix=f"EmailProcessor-{account.id}"
            )

        # 加载默认过滤规则
        self._load_default_rules()
    
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
    
    def _with_account_context(self, func):
        """包装函数：执行时注入账号日志上下文，使整条调用链（含子线程/
        线程池任务）的日志带上邮箱标识。"""
        address = self.account.email_address

        def wrapper(*args, **kwargs):
            with logger.contextualize(account=address):
                return func(*args, **kwargs)

        return wrapper

    def start(self) -> bool:
        """启动邮件监听服务（非阻塞，监听在独立线程中运行）。"""
        return self._with_account_context(self._start_impl)()

    def _start_impl(self) -> bool:
        account = self.account
        logger.info(f"启动邮件监听服务: {account.email_address}")
        logger.info(f"IMAP服务器: {account.imap_server}:{account.imap_port} (SSL: {account.imap_use_ssl})")

        if settings.email_hours_filter > 0:
            logger.info(f"邮件时间过滤: 监听 {settings.email_hours_filter} 小时内的邮件")
        else:
            logger.info("邮件时间过滤: 监听所有邮件")
        logger.info(f"过滤规则数量: {len(self.email_filter.rules)}")

        self.running = True

        # 初始连接测试
        if not self.email_client.connect():
            self.running = False
            logger.error(f"无法连接到邮箱服务器，监听启动失败: {account.email_address}")
            return False

        use_idle = False
        if settings.imap_idle_support:
            if self.email_client.test_idle_support():
                logger.info(f"[{account.email_address}] 使用IDLE模式进行实时监听")
                logger.info(f"IDLE超时时间: {settings.idle_timeout}秒")
                logger.info(f"IDLE检查间隔: {settings.idle_check_interval}秒")
                logger.info(f"重连延迟: {settings.idle_reconnect_delay}秒")
                use_idle = True
            else:
                logger.warning(f"[{account.email_address}] 服务器不支持IDLE，切换到轮询模式")
        else:
            logger.info(f"[{account.email_address}] 使用轮询模式进行监听")
            logger.info(f"检查间隔: {settings.check_interval}秒")

        if use_idle:
            if not self.email_client.start_idle_monitoring(self._on_idle_notification):
                logger.error(f"[{account.email_address}] IDLE模式启动失败，切换到轮询模式")
                use_idle = False

        if not use_idle:
            # 子线程不自动继承 contextvars，用上下文包装器显式传递邮箱标识
            self.poll_thread = threading.Thread(
                target=self._with_account_context(self._polling_loop),
                name=f"MailPoller-{account.id}",
                daemon=True,
            )
            self.poll_thread.start()

        logger.info(f"✓ 邮件监听已启动: {account.email_address}")
        return True

    def _polling_loop(self):
        """轮询模式监听循环（独立线程）"""
        while self.running:
            self._check_emails()
            # 分段休眠，便于 stop() 及时退出
            for _ in range(settings.check_interval):
                if not self.running:
                    break
                time.sleep(1)
    
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
        """停止邮件监听服务（幂等：各步骤异常不向外抛出）"""
        self._with_account_context(self._stop_impl)()

    def _stop_impl(self):
        logger.info(f"正在停止邮件监听服务: {self.account.email_address}")
        self.running = False

        # 停止IDLE监听（未运行时内部会直接返回）
        try:
            self.email_client.stop_idle_monitoring()
        except Exception as e:
            logger.warning(f"停止IDLE监听出错: {e}")

        # 等待轮询线程退出
        if self.poll_thread and self.poll_thread.is_alive():
            self.poll_thread.join(timeout=5)

        # 停止并发处理器（shutdown 不支持 timeout 参数，仅能 wait）
        if self.executor:
            logger.info("正在停止并发处理器...")
            try:
                self.executor.shutdown(wait=True)
                logger.info("并发处理器已停止")
            except Exception as e:
                logger.warning(f"停止并发处理器出错: {e}")

        try:
            self.email_client.disconnect()
        except Exception as e:
            logger.warning(f"断开邮箱连接出错: {e}")
        logger.info(f"邮件监听服务已停止: {self.account.email_address}")
    
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
        
        # 提交所有邮件处理任务（包装器保证处理线程内日志带邮箱标识）
        future_to_email = {}
        for email in emails:
            future = self.executor.submit(self._with_account_context(self._process_email), email)
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
            # 检查邮件是否已处理（按账号地址隔离，避免多邮箱 UID 碰撞）
            if email_db.email_exists(email.uid, receiver=self.account.email_address):
                logger.info(f"邮件 UID {email.uid} 已处理过，跳过")
                return

            supplier_config = self.supplier_config_repository.get_by_email(email.sender)
            if supplier_config is None:
                logger.info(f"邮件 UID {email.uid} 发件人 {email.sender} 未配置为供应商，跳过入库和处理")
                return
            
            # 记录邮件到数据库
            if email_db.add_email_record(
                email.uid,
                sender=email.sender,
                receiver=self.account.email_address,
                subject=email.subject,
                content=email.content,
                html_content=email.html_content,
                attachments=email.attachments,
                message_id=email.message_id,
                reply_to=email.reply_to,
                references=email.references,
                in_reply_to=email.in_reply_to
            ):
                logger.info(f"✓ 邮件 UID {email.uid} 已记录到数据库")
                if self.on_email_received:
                    try:
                        self.on_email_received()
                    except Exception as e:
                        logger.warning(f"更新收件状态失败: {e}")
            else:
                logger.warning(f"邮件 UID {email.uid} 记录失败（可能已存在）")
                return

            duplicate_email = email_db.find_duplicate_email_record(email.uid)
            if duplicate_email:
                logger.info(
                    f"邮件 UID {email.uid} 与已记录邮件 UID "
                    f"{duplicate_email['email_id']} 的 subject_hash/content_hash 相同，"
                    "仅记录数据库，不执行后续操作（重复邮件将在割接任务列表展示）"
                )
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
            
            # 邮件表只保存邮件本身信息。
                    
        except Exception as e:
            logger.error(f"处理邮件时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")


class MailListenerManager:
    """多邮箱监听管理器：按数据库启用的账号动态启停监听，支持热更新。"""

    def __init__(self):
        self._listeners: Dict[int, MailListener] = {}
        self._hashes: Dict[int, str] = {}
        self._status: Dict[int, dict] = {}
        # 可重入锁：sync() 持锁期间 _start_listener/_stop_listener 会经 _update_status 再次加锁
        self._lock = threading.RLock()

    def note_email_received(self, account_id: int):
        """监听器回调：记录该账号最后一次成功收件时间。"""
        with self._lock:
            self._status.setdefault(account_id, {})["last_email_at"] = (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )

    def get_status(self) -> Dict[int, dict]:
        """返回各账号监听状态快照：{account_id: {running, error, last_email_at}}。"""
        with self._lock:
            return {account_id: dict(status) for account_id, status in self._status.items()}

    def start_all(self):
        """服务启动入口：迁移 .env 存量配置后同步启动全部监听。"""
        seed_from_env_if_empty()
        self.sync()

    def sync(self):
        """对比数据库启用账号与运行中监听，增量启停/重启。"""
        with self._lock:
            try:
                configs = {c.id: c for c in list_enabled_account_configs()}
            except Exception as e:
                logger.error(f"读取邮箱账号配置失败，跳过同步: {e}")
                return

            # 停止已删除/禁用/配置变更的监听
            for account_id in list(self._listeners):
                config = configs.get(account_id)
                if config is None:
                    logger.info(f"邮箱账号 {account_id} 已删除或禁用，停止监听")
                    self._stop_listener(account_id)
                elif self._hashes.get(account_id) != config.config_hash():
                    logger.info(f"邮箱账号 {config.email_address} 配置变更，重启监听")
                    self._stop_listener(account_id)

            # 启动新增或配置变更的监听
            failed_addresses = []
            for account_id, config in configs.items():
                if account_id in self._listeners:
                    continue
                if not self._start_listener(config):
                    failed_addresses.append(config.email_address)

            # 清理已删除/禁用账号的状态记录（configs 仅含启用账号）
            for account_id in list(self._status):
                if account_id not in configs:
                    self._status.pop(account_id, None)

            logger.info(f"邮箱监听同步完成，当前运行 {len(self._listeners)} 个监听")
            return failed_addresses

    def _start_listener(self, config: MailAccountConfig) -> bool:
        listener = MailListener(
            config,
            on_email_received=lambda: self.note_email_received(config.id),
        )
        try:
            if listener.start():
                self._listeners[config.id] = listener
                self._hashes[config.id] = config.config_hash()
                self._update_status(config.id, running=True, error=None)
                return True
            listener.stop()
            self._update_status(config.id, running=False, error="连接邮箱服务器失败，请检查服务器/端口/授权码")
        except Exception as e:
            logger.error(f"启动邮箱监听失败 [{config.email_address}]: {e}")
            listener.stop()
            self._update_status(config.id, running=False, error=str(e))
        return False

    def _update_status(self, account_id: int, running: bool, error: Optional[str]):
        with self._lock:
            status = self._status.setdefault(account_id, {})
            status["running"] = running
            status["error"] = error

    def _stop_listener(self, account_id: int):
        listener = self._listeners.pop(account_id, None)
        self._hashes.pop(account_id, None)
        if listener:
            try:
                listener.stop()
            except Exception as e:
                logger.error(f"停止邮箱监听失败: {e}")
        self._update_status(account_id, running=False, error=None)

    def stop_all(self):
        """优雅停止全部监听。"""
        with self._lock:
            for account_id in list(self._listeners):
                self._stop_listener(account_id)


# 全局监听管理器单例（main 与 api_server 共用，支持页面热更新）
listener_manager = MailListenerManager()


def _setup_standalone_logging():
    """独立运行 mail_listener.py 时的日志配置（由 main.py 启动时已在 main.py 配置）。"""
    logger.remove()
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format=log_format,
    )

    import os
    os.makedirs("logs", exist_ok=True)

    logger.add(
        "logs/mail_listener.log",
        rotation="1 day",
        retention="30 days",
        level=settings.log_level,
        format=log_format,
    )


def main():
    """主函数（独立运行单入口，生产由 main.py 统一拉起）"""
    _setup_standalone_logging()

    def _signal_handler(signum, frame):
        logger.info(f"收到信号 {signum}，正在停止服务...")
        listener_manager.stop_all()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        listener_manager.start_all()
        # 监听均在独立线程运行，主线程保持存活
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("收到中断信号，正在停止服务...")
        listener_manager.stop_all()
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
