#!/usr/bin/env python
"""
数据库使用示例
"""
from database import email_db
from datetime import datetime


def process_alert_email(email_id: int, code: str, event_type: str):
    """
    处理告警邮件
    
    Args:
        email_id: 邮件ID
        code: 事件代码（如：SERVER01_CPU_HIGH）
        event_type: 事件类型（6个场景之一）
    """
    print(f"\n处理告警邮件: email_id={email_id}, code={code}, type={event_type}")
    
    # 1. 检查邮件是否已处理
    if email_db.email_exists(email_id):
        print(f"  ⚠️  邮件已处理，跳过")
        return
    
    # 2. 记录邮件
    email_db.add_email_record(email_id)
    print(f"  ✓ 记录邮件")
    
    # 3. 创建事件记录
    event_id = email_db.add_event_record(
        code=code,
        event_type=event_type,
        status="active"
    )
    print(f"  ✓ 创建事件: event_id={event_id}")
    
    # 4. 关联邮件和事件
    email_db.update_email_record(
        email_id=email_id,
        event_id=event_id,
        email_type="告警"
    )
    print(f"  ✓ 关联邮件和事件")
    
    # 5. 记录告警时间
    email_db.update_event_record(
        event_id=event_id,
        alert_time=datetime.now()
    )
    print(f"  ✓ 记录告警时间")


def process_recovery_email(email_id: int, code: str, event_type: str):
    """
    处理恢复邮件
    
    Args:
        email_id: 邮件ID
        code: 事件代码
        event_type: 事件类型
    """
    print(f"\n处理恢复邮件: email_id={email_id}, code={code}, type={event_type}")
    
    # 1. 检查邮件是否已处理
    if email_db.email_exists(email_id):
        print(f"  ⚠️  邮件已处理，跳过")
        return
    
    # 2. 记录邮件
    email_db.add_email_record(email_id)
    print(f"  ✓ 记录邮件")
    
    # 3. 查找对应的活跃事件
    active_event = email_db.get_active_event_by_code_and_type(code, event_type)
    
    if not active_event:
        print(f"  ⚠️  未找到对应的活跃事件")
        return
    
    print(f"  ✓ 找到活跃事件: event_id={active_event['id']}")
    
    # 4. 关联邮件和事件
    email_db.update_email_record(
        email_id=email_id,
        event_id=active_event['id'],
        email_type="恢复"
    )
    print(f"  ✓ 关联邮件和事件")
    
    # 5. 更新事件状态和恢复时间
    email_db.update_event_record(
        event_id=active_event['id'],
        status="resolved",
        recovery_time=datetime.now()
    )
    print(f"  ✓ 更新事件状态为已恢复")


def show_statistics():
    """显示统计信息"""
    print("\n" + "=" * 60)
    print("统计信息")
    print("=" * 60)
    
    stats = email_db.get_statistics()
    
    print(f"\n【邮件记录】")
    print(f"  总数: {stats['email_records']['total']}")
    print(f"  今日: {stats['email_records']['today']}")
    print(f"  类型分布: {stats['email_records']['type_distribution']}")
    
    print(f"\n【事件记录】")
    print(f"  总数: {stats['event_records']['total']}")
    print(f"  今日: {stats['event_records']['today']}")
    print(f"  活跃告警: {stats['event_records']['active_alerts']}")
    print(f"  状态分布: {stats['event_records']['status_distribution']}")
    print(f"  类型分布: {stats['event_records']['type_distribution']}")
    
    # 显示活跃告警详情
    active_alerts = email_db.get_event_records(status="active")
    if active_alerts:
        print(f"\n【活跃告警详情】")
        for alert in active_alerts:
            print(f"  - ID: {alert['id']}")
            print(f"    代码: {alert['code']}")
            print(f"    类型: {alert['type']}")
            print(f"    告警时间: {alert['alert_time']}")
            print()


if __name__ == "__main__":
    print("=" * 60)
    print("数据库使用示例")
    print("=" * 60)
    
    # 场景1：服务器1 CPU告警
    process_alert_email(
        email_id=40001,
        code="SERVER01_CPU_HIGH",
        event_type="CPU_HIGH"
    )
    
    # 场景2：服务器2 内存告警
    process_alert_email(
        email_id=40002,
        code="SERVER02_MEMORY_HIGH",
        event_type="MEMORY_HIGH"
    )
    
    # 场景3：数据库1 响应慢告警
    process_alert_email(
        email_id=40003,
        code="DB01_DATABASE_SLOW",
        event_type="DATABASE_SLOW"
    )
    
    # 场景4：服务器1 CPU恢复
    process_recovery_email(
        email_id=40004,
        code="SERVER01_CPU_HIGH",
        event_type="CPU_HIGH"
    )
    
    # 场景5：重复处理同一封邮件（测试去重）
    process_alert_email(
        email_id=40001,
        code="SERVER01_CPU_HIGH",
        event_type="CPU_HIGH"
    )
    
    # 显示统计信息
    show_statistics()
    
    print("\n" + "=" * 60)
    print("✅ 示例完成")
    print("=" * 60)
