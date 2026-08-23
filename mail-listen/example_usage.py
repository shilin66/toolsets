#!/usr/bin/env python
"""
数据库使用示例
"""
from database import email_db


def add_sample_email(email_id: int, subject: str, content: str):
    print(f"\n记录邮件: email_id={email_id}, subject={subject}")

    if email_db.email_exists(email_id):
        print("  邮件已存在，跳过")
        return

    email_db.add_email_record(
        email_id=email_id,
        sender="sender@example.com",
        receiver=["receiver@example.com"],
        subject=subject,
        content=content,
    )
    print("  已记录邮件")


def show_statistics():
    print("\n" + "=" * 60)
    print("统计信息")
    print("=" * 60)

    stats = email_db.get_statistics()
    email_stats = stats.get('email_records', {})

    print("\n【邮件记录】")
    print(f"  总数: {email_stats.get('total', 0)}")
    print(f"  今日: {email_stats.get('today', 0)}")

    print("\n【最近邮件】")
    for record in email_db.get_email_records(limit=5):
        print(f"  - UID: {record['email_id']}")
        print(f"    发件人: {record['sender']}")
        print(f"    收件人: {record['receiver']}")
        print(f"    主题: {record['subject']}")
        print(f"    主题Hash: {record['subject_hash']}")
        print(f"    正文Hash: {record['content_hash']}")


if __name__ == "__main__":
    print("=" * 60)
    print("数据库使用示例")
    print("=" * 60)

    add_sample_email(40001, "测试邮件 1", "测试正文 1")
    add_sample_email(40002, "测试邮件 2", "测试正文 2")
    add_sample_email(40001, "重复邮件", "重复正文")
    show_statistics()

    print("\n" + "=" * 60)
    print("示例完成")
    print("=" * 60)
