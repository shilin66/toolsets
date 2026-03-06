"""
邮件客户端模块
"""
import email
import time
import threading
from typing import List, Optional, Callable
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from loguru import logger
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
from models import EmailMessage
from config import settings


class EmailClient:
    """邮件客户端"""

    def __init__(self):
        self.client: Optional[IMAPClient] = None
        self.connected = False
        self.idle_thread: Optional[threading.Thread] = None
        self.idle_running = False
        self.idle_callback: Optional[Callable] = None
        self._idle_lock = threading.Lock()
    
    def _make_timezone_aware(self, dt: datetime) -> datetime:
        """确保datetime对象包含时区信息"""
        if dt.tzinfo is None:
            # 如果没有时区信息，假设是本地时区
            return dt.replace(tzinfo=timezone.utc)
        return dt
    
    def _get_cutoff_datetime(self, hours: int) -> datetime:
        """获取截止时间，确保时区一致"""
        now = datetime.now(timezone.utc)
        return now - timedelta(hours=hours)
    
    def _filter_uids_by_time(self, uids: List[int], hours: int) -> List[int]:
        """根据时间过滤邮件UID（客户端过滤）"""

        if not uids or hours <= 0:
            return uids
        
        cutoff_date = self._get_cutoff_datetime(hours)
        filtered_uids = []
        
        logger.debug(f"开始客户端时间过滤，截止时间: {cutoff_date}")
        # 遍历最后20个uid
        uids = uids[-20:]
        for uid in uids:
            try:
                # 获取邮件的基本信息（只获取日期，不解析全部内容）
                response = self.client.fetch(uid, ['INTERNALDATE'])
                if uid in response:
                    internal_date = response[uid][b'INTERNALDATE']
                    email_date = self._make_timezone_aware(internal_date)
                    
                    if email_date >= cutoff_date:
                        filtered_uids.append(uid)
                        logger.debug(f"UID {uid} 通过时间过滤: {email_date}")
                    else:
                        logger.debug(f"UID {uid} 被时间过滤排除: {email_date}")
            except Exception as e:
                logger.debug(f"获取UID {uid} 时间信息失败: {e}，保留该邮件")
                filtered_uids.append(uid)  # 出错时保留邮件
        
        logger.debug(f"时间过滤完成: {len(uids)} -> {len(filtered_uids)}")
        return filtered_uids
    
    def _search_with_timeout(self, search_criteria: list, timeout: int = None) -> list:
        """带超时控制的搜索方法（线程安全版本）"""
        if timeout is None:
            timeout = settings.search_timeout
        
        import concurrent.futures
        
        def do_search():
            """执行搜索的内部函数"""
            return self.client.search(search_criteria)
        
        try:
            logger.debug(f"开始搜索，超时时间: {timeout}秒，条件: {search_criteria}")
            
            # 使用线程池执行器实现超时控制
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(do_search)
                try:
                    messages = future.result(timeout=timeout)
                    logger.debug(f"搜索完成，找到 {len(messages)} 封邮件")
                    return messages
                except concurrent.futures.TimeoutError:
                    logger.error(f"搜索操作超时（{timeout}秒）")
                    return []
                    
        except Exception as e:
            logger.error(f"搜索失败: {e}")
            
            # 检测连接错误并重置状态
            error_str = str(e)
            if "Broken pipe" in error_str or isinstance(e, (ConnectionError, OSError)):
                logger.warning(f"检测到连接断开 ({e})，标记为未连接状态")
                self.connected = False
                
            return []

    def connect(self) -> bool:
        """连接到邮箱服务器"""
        try:
            self.client = IMAPClient(
                settings.imap_server,
                port=settings.imap_port,
                ssl=settings.imap_use_ssl,
                use_uid=True,
            )
            self.client.login(settings.email_address, settings.email_password)
            self.client.select_folder('INBOX')
            self.client._imap.debug = 4
            self.connected = True
            logger.info(f"成功连接到邮箱: {settings.email_address} (SSL: {settings.imap_use_ssl})")
            return True
        except Exception as e:
            logger.error(f"连接邮箱失败: {e}")
            self.connected = False
            return False

    def disconnect(self):
        """断开连接"""
        if self.client and self.connected:
            try:
                self.client.logout()
                self.connected = False
                logger.info("已断开邮箱连接")
            except Exception as e:
                logger.error(f"断开连接时出错: {e}")

    def get_unread_messages(self) -> List[EmailMessage]:
        """获取未读邮件（优化版，支持大量邮件）"""
        if not self.connected:
            if not self.connect():
                return []

        try:
            messages = []
            
            # 如果配置了小时过滤，尝试使用SINCE搜索
            if settings.email_hours_filter > 0:
                since_date = self._get_cutoff_datetime(settings.email_hours_filter)
                
                # 尝试多种日期格式，兼容不同的IMAP服务器
                date_formats = [
                    since_date.strftime("%d-%b-%Y"),  # 标准格式: 06-Nov-2025
                    since_date.strftime("%Y-%m-%d"),  # ISO格式: 2025-11-06
                    since_date.strftime("%m/%d/%Y"),  # 美式格式: 11/06/2025
                ]
                
                logger.info(f"搜索 {settings.email_hours_filter} 小时内的未读邮件（自 {since_date.strftime('%Y-%m-%d %H:%M:%S')}）")
                
                # 尝试不同的日期格式
                for date_format in date_formats:
                    try:
                        search_criteria = ['UNSEEN', f'SINCE {date_format}']
                        logger.debug(f"尝试日期格式: {date_format}")
                        messages = self._search_with_timeout(search_criteria, timeout=10)
                        
                        if messages:
                            logger.info(f"使用日期格式 '{date_format}' 搜索到 {len(messages)} 封邮件")
                            break
                        else:
                            logger.debug(f"日期格式 '{date_format}' 未找到邮件")
                    except Exception as e:
                        logger.debug(f"日期格式 '{date_format}' 搜索失败: {e}")
                        continue
                
                # 如果所有日期格式都失败，回退到获取所有未读邮件
                if not messages:
                    logger.warning("服务器可能不支持SINCE搜索，回退到获取所有未读邮件进行客户端过滤")
                    messages = self._search_with_timeout(['UNSEEN'])
                    logger.info(f"获取到所有未读邮件: {len(messages)} 封，将进行客户端时间过滤")
            else:
                # 没有配置小时过滤，直接搜索所有未读邮件
                logger.info("搜索所有未读邮件")
                messages = self._search_with_timeout(['UNSEEN'])
            
            if not messages:
                logger.info("没有找到未读邮件")
                return []
            
            logger.info(f"搜索到 {len(messages)} 封未读邮件")
            
            # 限制处理数量，优先处理最新的邮件
            if len(messages) > settings.max_emails_per_batch:
                logger.warning(f"未读邮件数量 ({len(messages)}) 超过批处理限制 ({settings.max_emails_per_batch})")
                logger.info(f"只处理最新的 {settings.max_emails_per_batch} 封邮件")
                messages = messages[-settings.max_emails_per_batch:]  # 取最新的邮件
            
            email_messages = []
            processed_count = 0
            cutoff_date = None
            
            # 如果配置了小时过滤，准备客户端过滤
            if settings.email_hours_filter > 0:
                cutoff_date = self._get_cutoff_datetime(settings.email_hours_filter)
            
            for uid in messages:
                try:
                    email_msg = self._parse_email(uid)
                    if email_msg:
                        # 客户端时间过滤（适用于所有邮箱服务器）
                        if cutoff_date:
                            email_date = self._make_timezone_aware(email_msg.received_date)
                            if email_date < cutoff_date:
                                logger.debug(f"跳过超出时间范围的邮件: {email_msg.subject}")
                                continue

                        email_messages.append(email_msg)
                        processed_count += 1

                        # 标记为已读（如果配置启用）
                        if settings.mark_as_read:
                            self.client.add_flags(uid, ['\\Seen'])
                        
                        # 每处理10封邮件输出一次进度
                        if processed_count % 10 == 0:
                            logger.info(f"已处理 {processed_count}/{len(messages)} 封邮件")
                
                except Exception as e:
                    logger.error(f"处理邮件 UID {uid} 时出错: {e}")
                    continue

            if settings.email_hours_filter > 0:
                logger.info(f"获取到 {len(email_messages)} 封 {settings.email_hours_filter} 小时内的未读邮件")
            else:
                logger.info(f"获取到 {len(email_messages)} 封未读邮件")
            return email_messages

        except Exception as e:
            logger.error(f"获取邮件失败: {e}")
            return []

    def _parse_email(self, uid: int) -> Optional[EmailMessage]:
        """解析邮件内容"""
        try:
            # 获取邮件数据
            response = self.client.fetch(uid, ['RFC822'])
            email_data = response[uid][b'RFC822']

            # 解析邮件
            msg = email.message_from_bytes(email_data)

            # 解析主题
            subject = self._decode_header(msg.get('Subject', ''))

            # 解析发件人
            sender = self._decode_header(msg.get('From', ''))

            # 解析收件人
            recipients = [self._decode_header(msg.get('To', ''))]

            # 解析日期
            date_str = msg.get('Date')
            received_date = parsedate_to_datetime(date_str) if date_str else datetime.now()

            # 解析邮件内容
            content, html_content = self._extract_content(msg)
            content = (html_content or "") + (content or "")
            # 解析附件
            attachments = self._extract_attachments(msg)

            return EmailMessage(
                uid=uid,
                subject=subject,
                sender=sender,
                recipients=recipients,
                content=content,
                html_content=html_content,
                received_date=received_date,
                attachments=attachments
            )

        except Exception as e:
            logger.error(f"解析邮件 {uid} 失败: {e}")
            return None

    def _decode_header(self, header: str) -> str:
        """解码邮件头"""
        if not header:
            return ""

        decoded_parts = decode_header(header)
        decoded_string = ""

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                if encoding:
                    decoded_string += part.decode(encoding)
                else:
                    decoded_string += part.decode('utf-8', errors='ignore')
            else:
                decoded_string += part

        return decoded_string

    def _extract_content(self, msg) -> tuple[str, Optional[str]]:
        """提取邮件内容"""
        text_content = ""
        html_content = None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if "attachment" not in content_disposition:
                    if content_type == "text/plain":
                        text_content += part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    elif content_type == "text/html":
                        html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        else:
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                text_content = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
            elif content_type == "text/html":
                html_content = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        # 如果HTML内容存在，提取body部分并处理特殊标签
        if html_content:
            try:
                from bs4 import BeautifulSoup

                # 解析HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                print('======================\n')
                print(soup)

                # 提取body内容
                body = soup.find('body')
                if body:
                    # 移除所有img标签
                    for img in body.find_all('img'):
                        img.decompose()

                    # 将<br>标签替换为换行符
                    for br in body.find_all('br'):
                        br.replace_with('\n')

                    # 获取处理后的文本
                    html_content = body.get_text()
                else:
                    # 如果没有找到body标签，处理整个HTML
                    # 移除所有img标签
                    for img in soup.find_all('img'):
                        img.decompose()

                    # 将<br>标签替换为换行符
                    for br in soup.find_all('br'):
                        br.replace_with('\n')

                    # 获取处理后的文本
                    html_content = soup.get_text()

            except Exception as e:
                logger.warning(f"处理HTML内容时出错: {e}")

        return text_content.strip(), html_content

    def _extract_attachments(self, msg) -> List[str]:
        """提取附件信息"""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition"))
                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        attachments.append(self._decode_header(filename))

        return attachments

    def get_emails_by_uids(self, uids: List[int]) -> List[EmailMessage]:
        """根据UID列表获取特定邮件"""
        if not self.connected:
            if not self.connect():
                return []

        emails = []
        try:
            for uid in uids:
                email_msg = self._parse_email(uid)
                if email_msg:
                    # 检查小时过滤
                    if settings.email_hours_filter > 0:
                        cutoff_date = self._get_cutoff_datetime(settings.email_hours_filter)
                        email_date = self._make_timezone_aware(email_msg.received_date)
                        if email_date < cutoff_date:
                            logger.debug(f"跳过超出时间范围的邮件: {email_msg.subject}")
                            continue

                    emails.append(email_msg)

                    # 标记为已读（如果配置启用）
                    if settings.mark_as_read:
                        self.client.add_flags(uid, ['\\Seen'])

            logger.info(f"根据UID获取到 {len(emails)} 封邮件")
            return emails

        except Exception as e:
            logger.error(f"根据UID获取邮件失败: {e}")
            return []

    def start_idle_monitoring(self, callback: Callable):
        """启动IDLE模式监听"""
        if not settings.imap_idle_support:
            logger.warning("IDLE模式未启用，请使用定时轮询模式")
            return False

        if self.idle_running:
            logger.warning("IDLE监听已在运行中")
            return True

        self.idle_callback = callback
        self.idle_running = True

        # 启动IDLE监听线程
        self.idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self.idle_thread.start()

        logger.info("IDLE模式监听已启动")
        return True

    def stop_idle_monitoring(self):
        """停止IDLE模式监听"""
        if not self.idle_running:
            return

        logger.info("正在停止IDLE模式监听...")
        self.idle_running = False

        # 等待IDLE线程结束
        if self.idle_thread and self.idle_thread.is_alive():
            self.idle_thread.join(timeout=5)

        logger.info("IDLE模式监听已停止")

    def _idle_loop(self):
        """IDLE监听循环"""
        seen_uids = set()
        last_check_time = datetime.now()
        idle_start_time = datetime.now()  # 记录IDLE开始时间
        while self.idle_running:
            try:
                # 确保连接正常
                if not self.connected:
                    if not self.connect():
                        logger.error("IDLE模式连接失败，等待重连...")
                        time.sleep(settings.idle_reconnect_delay)
                        continue

                # 检查服务器是否支持IDLE
                if not self._check_idle_capability():
                    logger.error("服务器不支持IDLE命令")
                    self.idle_running = False
                    break

                # 检查是否需要强制重启IDLE连接（基于IDLE_TIMEOUT）
                current_time = datetime.now()
                idle_duration = (current_time - idle_start_time).total_seconds()
                
                if idle_duration >= settings.idle_timeout:
                    logger.info(f"⏰ IDLE连接已运行 {idle_duration:.0f}秒，达到超时时间 {settings.idle_timeout}秒，强制重启连接")
                    try:
                        if self.client:
                            self.client.idle_done()
                    except:
                        pass
                    # 重新连接
                    self.connected = False
                    if not self.connect():
                        logger.error("IDLE超时重连失败，等待重试...")
                        time.sleep(settings.idle_reconnect_delay)
                        continue
                    idle_start_time = datetime.now()  # 重置IDLE开始时间

                logger.debug("开始IDLE监听...")

                # 启动IDLE
                logger.debug("发送IDLE命令...")
                self.client.idle()

                # 等待新邮件通知或短期超时检查
                check_timeout = settings.idle_check_interval
                logger.debug(f"等待IDLE通知，检查间隔: {check_timeout}秒")
                responses = self.client.idle_check(timeout=check_timeout)

                if responses:
                    # 收到响应，停止IDLE并处理
                    logger.debug("停止IDLE命令...")
                    self.client.idle_done()

                    logger.info(f"🔔 收到IDLE响应: {responses}")

                    # 解析IDLE响应，提取新邮件的UID
                    new_mail_uids = self._parse_idle_responses(responses)

                    if new_mail_uids:
                        logger.info(f"🚨 立即输出邮件ID: {new_mail_uids}")
                        logger.info(f"✅ 检测到 {len(new_mail_uids)} 封新邮件: {new_mail_uids}")
                        # 处理特定的新邮件
                        if self.idle_callback:
                            try:
                                self.idle_callback(new_mail_uids)
                            except Exception as e:
                                logger.error(f"IDLE回调执行失败: {e}")
                        else:
                            logger.warning("IDLE回调函数未设置")
                    else:
                        logger.info("收到IDLE通知但未提取到邮件UID")

                    # 处理完响应后，继续下一轮IDLE循环
                    logger.debug("处理完成，准备重新开始IDLE监听")

                else:
                    # 短期超时，停止IDLE并重新开始（保持同一个连接）
                    logger.debug(f"⏰ IDLE检查间隔超时（{check_timeout}秒），重新开始监听")
                    self.client.idle_done()
                    
                    # IDLE重启时检查是否有遗漏的邮件
                    self._check_missed_emails_during_restart(last_check_time)
                    last_check_time = datetime.now()

                # 短暂休息，避免过于频繁的重连
                time.sleep(0.1)

            except IMAPClientError as e:
                logger.error(f"IDLE模式IMAP错误: {e}")
                self.connected = False
                try:
                    if self.client:
                        self.client.idle_done()
                except:
                    pass
                
                # 异常重连前检查遗漏的邮件
                self._check_missed_emails_during_restart(last_check_time)
                last_check_time = datetime.now()
                idle_start_time = datetime.now()  # 重置IDLE开始时间
                time.sleep(settings.idle_reconnect_delay)

            except Exception as e:
                logger.error(f"IDLE模式异常: {e}")
                self.connected = False
                try:
                    if self.client:
                        self.client.idle_done()
                except:
                    pass
                
                # 异常重连前检查遗漏的邮件
                self._check_missed_emails_during_restart(last_check_time)
                last_check_time = datetime.now()
                idle_start_time = datetime.now()  # 重置IDLE开始时间
                time.sleep(settings.idle_reconnect_delay)

        logger.info("IDLE监听循环结束")

    def _check_missed_emails_during_restart(self, last_check_time: datetime):
        """检查IDLE重启期间可能遗漏的邮件"""
        try:
            if not self.connected:
                return
            
            logger.debug(f"检查自 {last_check_time.strftime('%H:%M:%S')} 以来可能遗漏的邮件")
            
            # 搜索未读邮件
            search_criteria = ['UNSEEN']
            recent_uids = self._search_with_timeout(search_criteria, timeout=5)
            
            if recent_uids:
                # 如果配置了小时过滤，进行时间过滤
                if settings.email_hours_filter > 0:
                    filtered_uids = self._filter_uids_by_time(recent_uids, settings.email_hours_filter)
                    new_uids = filtered_uids[-min(len(filtered_uids), 5):] if filtered_uids else []
                else:
                    # 只取最新的几封邮件
                    new_uids = recent_uids[-min(len(recent_uids), 5):]
                
                if new_uids:
                    logger.info(f"🔍 IDLE重启检查发现可能遗漏的邮件: {new_uids}")
                    
                    # 调用回调处理遗漏的邮件
                    if self.idle_callback:
                        try:
                            self.idle_callback(new_uids)
                        except Exception as e:
                            logger.error(f"处理遗漏邮件回调失败: {e}")
                else:
                    logger.debug("IDLE重启检查：没有发现遗漏的邮件")
            else:
                logger.debug("IDLE重启检查：没有未读邮件")
                
        except Exception as e:
            logger.debug(f"检查遗漏邮件时出错: {e}")  # 使用debug级别，避免过多错误日志

    def _parse_idle_responses(self, responses) -> List[int]:
        """解析IDLE响应，提取新邮件的UID"""
        new_mail_uids = []

        try:
            for response in responses:
                logger.debug(f"解析IDLE响应: {response} (类型: {type(response)})")

                # QQ邮箱的IDLE响应格式是元组: (序号, b'EXISTS')
                if isinstance(response, tuple) and len(response) == 2:
                    seq_num, command = response
                    command_str = command.decode() if isinstance(command, bytes) else str(command)

                    logger.debug(f"解析元组响应: 序号={seq_num}, 命令={command_str}")

                    if command_str == 'EXISTS':
                        # EXISTS表示邮箱中有新邮件
                        logger.info(f"检测到EXISTS响应，邮箱总邮件数: {seq_num}")

                        try:
                            # 根据小时过滤配置搜索邮件
                            if settings.email_hours_filter > 0:
                                # 搜索指定小时内的未读邮件，使用兼容性搜索
                                logger.info(f"IDLE事件触发：搜索 {settings.email_hours_filter} 小时内的未读邮件")
                                search_criteria = ['UNSEEN']  # 先搜索所有未读邮件，后续客户端过滤
                            else:
                                # 搜索所有未读邮件，但只取最新的几封
                                search_criteria = ['UNSEEN']
                                logger.info("IDLE事件触发：搜索最新的未读邮件")
                            
                            recent_uids = self._search_with_timeout(search_criteria, timeout=10)
                            if recent_uids:
                                if settings.email_hours_filter > 0:
                                    # 如果配置了小时过滤，需要进行客户端时间过滤
                                    filtered_uids = self._filter_uids_by_time(recent_uids, settings.email_hours_filter)
                                    max_uids = min(len(filtered_uids), settings.max_emails_per_batch)
                                    new_uids = filtered_uids[-max_uids:] if filtered_uids else []
                                    logger.info(f"从EXISTS响应中提取到 {settings.email_hours_filter} 小时内的邮件UID: {new_uids}")
                                else:
                                    # 如果没有配置小时过滤，只取最新的2封
                                    new_uids = recent_uids[-2:]
                                    logger.info(f"从EXISTS响应中提取到最新邮件UID: {new_uids}")
                                
                                new_mail_uids.extend(new_uids)
                        except Exception as e:
                            logger.error(f"解析EXISTS响应失败: {e}")

                    elif command_str == 'RECENT':
                        # RECENT表示有新邮件标记
                        logger.info(f"检测到RECENT响应: {seq_num}")
                        try:
                            # 根据小时过滤配置搜索RECENT邮件
                            if settings.email_hours_filter > 0:
                                # 使用兼容性搜索，后续客户端过滤
                                search_criteria = ['RECENT']
                            else:
                                search_criteria = ['RECENT']
                            
                            recent_uids = self._search_with_timeout(search_criteria, timeout=10)
                            if recent_uids:
                                if settings.email_hours_filter > 0:
                                    filtered_uids = self._filter_uids_by_time(recent_uids, settings.email_hours_filter)
                                    max_uids = min(len(filtered_uids), settings.max_emails_per_batch)
                                    new_uids = filtered_uids[-max_uids:] if filtered_uids else []
                                else:
                                    new_uids = recent_uids[-2:]
                                new_mail_uids.extend(new_uids)
                                logger.info(f"从RECENT响应中提取到邮件UID: {new_uids}")
                        except Exception as e:
                            logger.error(f"解析RECENT响应失败: {e}")

                # 处理字符串格式的响应
                else:
                    response_str = str(response)
                    logger.debug(f"解析字符串响应: {response_str}")

                    if 'EXISTS' in response_str:
                        try:
                            # 根据小时过滤配置搜索邮件
                            if settings.email_hours_filter > 0:
                                # 使用兼容性搜索，后续客户端过滤
                                search_criteria = ['UNSEEN']
                            else:
                                search_criteria = ['UNSEEN']
                            
                            recent_uids = self._search_with_timeout(search_criteria, timeout=10)
                            if recent_uids:
                                if settings.email_hours_filter > 0:
                                    filtered_uids = self._filter_uids_by_time(recent_uids, settings.email_hours_filter)
                                    max_uids = min(len(filtered_uids), settings.max_emails_per_batch)
                                    new_uids = filtered_uids[-max_uids:] if filtered_uids else []
                                else:
                                    new_uids = recent_uids[-2:]
                                new_mail_uids.extend(new_uids)
                                logger.info(f"从字符串EXISTS响应中提取到邮件UID: {new_uids}")
                        except Exception as e:
                            logger.error(f"解析字符串EXISTS响应失败: {e}")

                    elif 'FETCH' in response_str:
                        # 尝试从FETCH响应中提取UID
                        import re
                        uid_match = re.search(r'(\d+)\s+FETCH', response_str)
                        if uid_match:
                            uid = int(uid_match.group(1))
                            if uid not in new_mail_uids:
                                new_mail_uids.append(uid)
                                logger.info(f"从FETCH响应中提取到邮件UID: {uid}")

        except Exception as e:
            logger.error(f"解析IDLE响应时出错: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")

        # 去重并返回
        unique_uids = list(set(new_mail_uids))
        logger.info(f"解析完成，提取到的唯一邮件UID: {unique_uids}")
        return unique_uids

    def _check_idle_capability(self) -> bool:
        """检查服务器是否支持IDLE"""
        try:
            capabilities = self.client.capabilities()
            return b'IDLE' in capabilities
        except Exception as e:
            logger.error(f"检查IDLE能力失败: {e}")
            return False

    def test_idle_support(self) -> bool:
        """测试服务器IDLE支持"""
        if not self.connected:
            if not self.connect():
                return False

        try:
            has_idle = self._check_idle_capability()
            if has_idle:
                logger.info("服务器支持IDLE命令")
            else:
                logger.warning("服务器不支持IDLE命令")
            return has_idle
        except Exception as e:
            logger.error(f"测试IDLE支持失败: {e}")
            return False
