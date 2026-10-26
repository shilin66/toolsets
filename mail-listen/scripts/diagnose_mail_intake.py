"""只读核对漏邮件：不导入应用、不入库、不改已读标记、不重放业务操作。

在工作台原有 Python 环境中运行，沿用数据库邮箱配置与现有密钥。
SUBJECT 搜索不限制未读或日期；只读取目标邮件头，不读取正文或附件。
当前 FLAGS 不能证明收件时的状态，历史排除原因仍需与日志对照。
"""

import argparse
import json
import os
import signal
import sqlite3
import sys
import time
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta, timezone
from email.header import decode_header
from email.parser import BytesHeaderParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError


HEADER_FIELDS = 'BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]'


class DiagnosticTimeout(RuntimeError):
    pass


@contextmanager
def deadline(seconds):
    """CLI 在 Linux/macOS 主线程运行；总时限包含 DNS、搜索和逐文件夹检查。"""
    if seconds <= 0 or not hasattr(signal, 'SIGALRM'):
        raise ValueError('总时限必须为正数，且运行环境需支持 SIGALRM（Linux/macOS）')
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    def expire(_signum, _frame):
        raise DiagnosticTimeout(f'达到总运行时限 {seconds:g} 秒；最后一条进度可定位阻塞步骤')
    signal.signal(signal.SIGALRM, expire)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(signal.ITIMER_REAL,
                            max(0.000001, previous_timer[0] - (time.monotonic() - started)),
                            previous_timer[1])


@contextmanager
def close_on_error(client):
    # 命令超时/人工中断后立即断开诊断连接，避免退出时再等待 LOGOUT。
    try:
        yield
    except BaseException:
        try:
            client.shutdown()
        except Exception:
            pass
        raise


def decode_value(value):
    parts = []
    for part, encoding in decode_header(value or ''):
        if isinstance(part, bytes):
            try:
                part = part.decode(encoding or 'utf-8', errors='replace')
            except LookupError:
                part = part.decode('utf-8', errors='replace')
        parts.append(part)
    return ''.join(parts)


def before_cutoff(value, cutoff):
    if cutoff is None:
        return False
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value < cutoff


def scan_folder(client, folder, ticket, cutoff, progress, received_date=None):
    progress(f'打开只读文件夹 {folder!r}')
    info = client.select_folder(folder, readonly=True)
    # 默认不限制未读或日期；日期范围仅由操作人员显式指定，并保留前后一天。
    criteria = ['SUBJECT', ticket]
    if received_date:
        criteria += ['SINCE', received_date - timedelta(days=1),
                     'BEFORE', received_date + timedelta(days=2)]
    progress(f'搜索文件夹 {folder!r}，编号 {ticket!r}'
             + (f'，收件日期窗口 {received_date.isoformat()} 前后一天' if received_date else '，不限日期'))
    uids = sorted(client.search(criteria))
    progress(f'文件夹 {folder!r} 搜索返回 {len(uids)} 个 UID')
    matches = []
    for start in range(0, len(uids), 100):
        batch = uids[start:start + 100]
        progress(f'读取 {folder!r} 邮件头 {start + 1}～{start + len(batch)}/{len(uids)}')
        response = client.fetch(batch, ['FLAGS', 'INTERNALDATE', HEADER_FIELDS])
        if any(uid not in response for uid in batch):
            raise RuntimeError('搜索后有 UID 无法读取，请重试；本次结果不完整')
        for uid in batch:
            data = response[uid]
            raw = next((value for key, value in data.items()
                        if isinstance(key, bytes) and key.upper().startswith(b'BODY[HEADER')), None)
            if not isinstance(raw, bytes) or not raw:
                raise RuntimeError('服务器未返回邮件头，本次不能判定目标邮件不存在')
            header = BytesHeaderParser().parsebytes(raw)
            subject = decode_value(header.get('Subject'))
            if ticket.casefold() not in subject.casefold():
                continue
            if b'FLAGS' not in data:
                raise RuntimeError('服务器未返回已读标记，本次不能判定邮件状态')
            date_raw = header.get('Date', '')
            try:
                sent_at = parsedate_to_datetime(date_raw)
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                sent_at = None
            internal = data.get(b'INTERNALDATE')
            flags = [flag.decode(errors='replace') if isinstance(flag, bytes) else str(flag)
                     for flag in data.get(b'FLAGS', ())]
            matches.append({
                'folder': folder, 'uid': uid, 'uidvalidity': info.get(b'UIDVALIDITY'),
                'subject': subject, 'from': decode_value(header.get('From')),
                'message_id': header.get('Message-ID', ''), 'date_header': date_raw,
                'date_header_iso': sent_at.isoformat() if sent_at else None,
                'internaldate': internal.isoformat() if isinstance(internal, datetime) else None,
                'flags_now': flags, 'is_read_now': '\\Seen' in flags,
                'date_header_before_cutoff': before_cutoff(sent_at, cutoff),
                'internaldate_before_cutoff': before_cutoff(internal, cutoff),
            })
    return matches


def diagnose(db_path, address, ticket, checked_at, *, hours=2, all_folders=False,
             key_path=None, client_factory=IMAPClient, progress=None, received_date=None):
    progress = progress or (lambda message: None)
    if not ticket.strip() or checked_at.tzinfo is None or hours < 0:
        raise ValueError('编号不能为空；检查时间必须包含时区；小时范围不能为负数')
    path = Path(db_path).resolve()
    if not path.is_file():
        raise ValueError('数据库不存在；请指定工作台实际使用的数据库')
    cutoff = checked_at - timedelta(hours=hours) if hours else None
    progress('读取现有数据库与邮箱配置')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA query_only=ON')
        row = conn.execute('''SELECT email_address, password_enc, imap_server, imap_port,
            imap_use_ssl FROM mail_accounts WHERE lower(email_address)=lower(?)''', (address,)).fetchone()
        if row is None:
            raise ValueError('数据库中没有该监听邮箱')
        account = dict(row)
        key = os.environ.get('MAIL_SECRET_KEY', '').strip().encode()
        if not key:
            secret_path = Path(key_path) if key_path else path.parent / 'mail_secret.key'
            if not secret_path.is_file():
                raise ValueError('现有邮箱密钥不存在；诊断不会生成新密钥')
            key = secret_path.read_bytes().strip()
        try:
            password = Fernet(key).decrypt(account['password_enc'].encode()).decode()
        except (InvalidToken, ValueError, UnicodeError) as exc:
            raise ValueError('现有邮箱配置无法解密；请核对原密钥') from exc
        address = account['email_address']
        records = [dict(record) for record in conn.execute('''SELECT id, email_id, subject, create_time
            FROM email_records WHERE receiver=? AND instr(subject, ?) > 0''', (address, ticket))]
        tables = {table[0] for table in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        cursor = None
        if 'mail_intake_cursors' in tables:
            cursor_row = conn.execute('SELECT * FROM mail_intake_cursors WHERE account=? AND folder=?',
                                      (address, 'INBOX')).fetchone()
            cursor = dict(cursor_row) if cursor_row else None
        matches, folder_errors = [], []
        progress(f'连接 IMAP {account["imap_server"]!r}（socket 超时 20 秒）')
        with client_factory(host=account['imap_server'], port=int(account['imap_port'] or 993),
                            ssl=bool(account['imap_use_ssl']), use_uid=True, timeout=20) as client, close_on_error(client):
            client.normalise_times = False  # 保留服务器 INTERNALDATE 的原始时区。
            progress(f'登录监听邮箱 {address!r}')
            client.login(address, password)
            if hasattr(client, 'id_'):
                progress('发送 IMAP 客户端身份信息')
                try:
                    client.id_({'name': 'mail-listen-diagnostic', 'version': '1.0'})
                except IMAPClientError:
                    pass
            folders = ['INBOX']
            if all_folders:
                progress('读取文件夹列表')
                folders.extend(name for flags, _, name in client.list_folders()
                               if b'\\Noselect' not in flags and name.upper() != 'INBOX')
            progress(f'准备检查 {len(set(folders))} 个文件夹')
            for folder in dict.fromkeys(folders):
                try:
                    found = scan_folder(client, folder, ticket, cutoff, progress, received_date)
                except IMAPClientError:
                    if not all_folders:
                        raise
                    folder_errors.append({'folder': folder, 'error_type': 'IMAPClientError'})
                    progress(f'文件夹 {folder!r} 检查失败（IMAPClientError），搜索不完整')
                    continue
                for match in found:
                    # 其他文件夹的 UID 与 INBOX 独立，不能拿来匹配应用入库键。
                    match['database_record_ids'] = [record[0] for record in conn.execute(
                        'SELECT id FROM email_records WHERE email_id=? AND receiver=?',
                        (match['uid'], address))] if folder.upper() == 'INBOX' else None
                    progress('找到目标：' + json.dumps(match, ensure_ascii=False))
                matches.extend(found)
            progress('检查完成，退出诊断连接')
    return {'account': address, 'ticket': ticket, 'checked_at': checked_at.isoformat(),
            'cutoff': cutoff.isoformat() if cutoff else None, 'database_matches': records,
            'intake_cursor': cursor, 'matches': matches, 'folder_errors': folder_errors,
            'search_received_date': received_date.isoformat() if received_date else None,
            'note': 'FLAGS 是当前状态，不能证明首次轮询时已读；有 folder_errors 时搜索不完整。'
                    '指定收件日期后，未找到不代表日期窗口外也不存在。'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path('data/mail_listener.db'))
    parser.add_argument('--secret-key-file', type=Path)
    parser.add_argument('--account', required=True)
    parser.add_argument('--ticket', required=True)
    parser.add_argument('--checked-at', type=datetime.fromisoformat, required=True,
                        help='当时轮询时间，含时区，例如 2026-10-14T15:09:48+08:00')
    parser.add_argument('--hours', type=int, default=2, help='线上 EMAIL_HOURS_FILTER 值，0 为不限制')
    parser.add_argument('--all-folders', action='store_true')
    parser.add_argument('--received-date', type=date.fromisoformat,
                        help='可选：按服务器收件日期前后一天缩小搜索；例如 2026-10-14')
    parser.add_argument('--max-seconds', type=float, default=90, help='总运行时限，默认 90 秒')
    args = parser.parse_args()
    started = time.monotonic()
    def progress(message):
        print(f'[{time.monotonic() - started:.1f}s] {message}', file=sys.stderr, flush=True)
    try:
        with deadline(args.max_seconds):
            result = diagnose(args.database, args.account, args.ticket, args.checked_at, hours=args.hours,
                              all_folders=args.all_folders, key_path=args.secret_key_file,
                              received_date=args.received_date, progress=progress)
    except KeyboardInterrupt:
        parser.exit(130, '诊断已中止，未改变邮件状态或入库记录。\n')
    except (ValueError, OSError, sqlite3.Error, IMAPClientError, RuntimeError) as exc:
        # 不输出连接异常原文或 traceback，避免外部响应夹带认证信息。
        message = str(exc) if type(exc) in (ValueError, RuntimeError, DiagnosticTimeout) else type(exc).__name__
        parser.exit(1, '诊断失败：' + message + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
