"""Explicit UIDVALIDITY recovery; dry-run by default, never reads or replays mail."""

import argparse
import sqlite3
from pathlib import Path


def reset_cursor(db_path, account, folder, expected_validity, new_validity, uidnext, apply=False):
    if min(expected_validity, new_validity, uidnext) <= 0 or expected_validity == new_validity:
        raise ValueError('UIDVALIDITY 必须为不同的正整数，UIDNEXT 必须为正整数')
    if not Path(db_path).is_file():
        raise ValueError('数据库文件不存在')
    conn = sqlite3.connect(db_path)
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT uidvalidity, next_uid FROM mail_intake_cursors WHERE account=? AND folder=?',
                           (account, folder)).fetchone()
        if not row or row[0] != expected_validity:
            raise ValueError('现有游标不存在或 UIDVALIDITY 与预期不符，未修改')
        largest = conn.execute('SELECT COALESCE(MAX(email_id), 0) FROM email_records WHERE receiver=?',
                               (account,)).fetchone()[0]
        if uidnext <= largest:
            raise ValueError('新 UIDNEXT 与历史 UID 命名空间重叠；需要另行迁移邮件唯一键，不能直接重置')
        result = {'account': account, 'folder': folder, 'previous_uidvalidity': row[0],
                  'previous_next_uid': row[1], 'uidvalidity': new_validity, 'next_uid': uidnext,
                  'applied': apply}
        if apply:
            conn.execute('UPDATE mail_intake_cursors SET uidvalidity=?, next_uid=?, initialized_at=CURRENT_TIMESTAMP WHERE account=? AND folder=?',
                         (new_validity, uidnext, account, folder))
            conn.commit()
        return result
    finally:
        conn.close()


if __name__ == '__main__':
    import json

    parser = argparse.ArgumentParser(description='停服务后按邮箱当前 UIDNEXT 重建新邮件边界；默认仅检查')
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--account', required=True)
    parser.add_argument('--folder', default='INBOX')
    parser.add_argument('--expected-validity', type=int, required=True)
    parser.add_argument('--new-validity', type=int, required=True)
    parser.add_argument('--uidnext', type=int, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(reset_cursor(args.database, args.account, args.folder, args.expected_validity,
                                      args.new_validity, args.uidnext, args.apply), ensure_ascii=False))
    except (ValueError, sqlite3.Error) as exc:
        parser.exit(1, str(exc) + '\n')
