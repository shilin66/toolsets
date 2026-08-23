#!/usr/bin/env python
"""
创建 email_records 测试数据
"""
from database import email_db


def create_test_data(count: int = 10):
    for index in range(1, count + 1):
        email_db.add_email_record(
            email_id=900000 + index,
            sender=f"sender{index}@example.com",
            receiver=[f"receiver{index}@example.com"],
            subject=f"测试邮件 {index}",
            content=f"测试邮件正文 {index}",
        )

    print(f"已创建 {count} 条邮件测试数据")


if __name__ == "__main__":
    create_test_data()
