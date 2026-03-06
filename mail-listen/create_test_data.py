#!/usr/bin/env python
"""
创建event_records测试数据
"""
import sqlite3
from datetime import datetime, timedelta
import random
from database import email_db

def create_test_data():
    """创建测试数据"""
    
    print("=" * 60)
    print("创建 event_records 测试数据")
    print("=" * 60)
    
    # 告警类型和对应的典型持续时间范围（秒）
    alert_types = {
        'CPU_HIGH': (60, 1800),      # 1分钟到30分钟
        'MEMORY_HIGH': (120, 3600),  # 2分钟到1小时
        'DISK_FULL': (300, 7200),    # 5分钟到2小时
        'NETWORK_DOWN': (30, 900),   # 30秒到15分钟
        'SERVICE_DOWN': (180, 5400), # 3分钟到1.5小时
        'DATABASE_SLOW': (240, 2400) # 4分钟到40分钟
    }
    
    # 生成过去30天的测试数据
    base_date = datetime.now() - timedelta(days=30)
    
    test_records = []
    
    # 为每种类型生成不同数量的记录
    type_counts = {
        'CPU_HIGH': 25,
        'MEMORY_HIGH': 20,
        'DISK_FULL': 15,
        'NETWORK_DOWN': 30,
        'SERVICE_DOWN': 18,
        'DATABASE_SLOW': 12
    }
    
    record_id = 1000  # 从1000开始，避免与现有数据冲突
    
    for alert_type, count in type_counts.items():
        min_duration, max_duration = alert_types[alert_type]
        
        print(f"\n创建 {alert_type} 类型的 {count} 条记录...")
        
        for i in range(count):
            # 随机生成告警时间（过去30天内）
            days_ago = random.randint(0, 29)
            hours_ago = random.randint(0, 23)
            minutes_ago = random.randint(0, 59)
            
            alert_time = base_date + timedelta(
                days=days_ago,
                hours=hours_ago,
                minutes=minutes_ago
            )
            
            # 生成持续时间（80%在正常范围，20%异常长）
            if random.random() < 0.8:
                # 正常范围
                duration_seconds = random.randint(min_duration, max_duration)
            else:
                # 异常长时间（用于测试超时统计）
                duration_seconds = random.randint(max_duration, max_duration * 3)
            
            # 计算恢复时间
            recovery_time = alert_time + timedelta(seconds=duration_seconds)
            
            # 生成事件代码
            event_code = f"{alert_type}_TEST_{record_id:04d}"
            
            # 90%的记录是已恢复，10%是活跃状态
            if random.random() < 0.9:
                status = 'resolved'
                actual_recovery_time = recovery_time
                actual_duration = duration_seconds
            else:
                status = 'active'
                actual_recovery_time = None
                actual_duration = 0  # 活跃状态duration为0
            
            test_record = {
                'code': event_code,
                'type': alert_type,
                'status': status,
                'alert_time': alert_time,
                'recovery_time': actual_recovery_time,
                'duration_seconds': actual_duration,
                'create_time': alert_time,
                'update_time': recovery_time if actual_recovery_time else alert_time
            }
            
            test_records.append(test_record)
            record_id += 1
    
    # 插入数据到数据库
    print(f"\n插入 {len(test_records)} 条测试记录到数据库...")
    
    try:
        with email_db.get_connection() as conn:
            cursor = conn.cursor()
            
            # 批量插入数据
            insert_sql = '''
                INSERT INTO event_records 
                (code, type, status, alert_time, recovery_time, duration_seconds, create_time, update_time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            '''
            
            for record in test_records:
                cursor.execute(insert_sql, (
                    record['code'],
                    record['type'],
                    record['status'],
                    record['alert_time'],
                    record['recovery_time'],
                    record['duration_seconds'],
                    record['create_time'],
                    record['update_time']
                ))
            
            conn.commit()
            print(f"✅ 成功插入 {len(test_records)} 条测试记录")
            
    except Exception as e:
        print(f"❌ 插入数据失败: {e}")
        return
    
    # 显示数据统计
    print(f"\n【数据统计】")
    print("-" * 40)
    
    try:
        with email_db.get_connection() as conn:
            cursor = conn.cursor()
            
            # 总记录数
            cursor.execute("SELECT COUNT(*) as total FROM event_records")
            total = cursor.fetchone()['total']
            print(f"总记录数: {total}")
            
            # 按类型统计
            cursor.execute('''
                SELECT type, COUNT(*) as count, 
                       AVG(duration_seconds) as avg_duration,
                       MAX(duration_seconds) as max_duration
                FROM event_records 
                WHERE status = 'resolved' AND duration_seconds > 0
                GROUP BY type 
                ORDER BY count DESC
            ''')
            
            print("\n按类型统计 (已恢复的记录):")
            for row in cursor.fetchall():
                print(f"  {row['type']}: {row['count']} 条, "
                      f"平均 {row['avg_duration']:.0f}秒, "
                      f"最长 {row['max_duration']}秒")
            
            # 按状态统计
            cursor.execute('''
                SELECT status, COUNT(*) as count 
                FROM event_records 
                GROUP BY status
            ''')
            
            print("\n按状态统计:")
            for row in cursor.fetchall():
                print(f"  {row['status']}: {row['count']} 条")
            
            # 超时统计（以5分钟为阈值）
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_resolved,
                    COUNT(CASE WHEN duration_seconds > 300 THEN 1 END) as timeout_count
                FROM event_records 
                WHERE status = 'resolved' AND duration_seconds > 0
            ''')
            
            row = cursor.fetchone()
            if row['total_resolved'] > 0:
                timeout_rate = (row['timeout_count'] / row['total_resolved']) * 100
                print(f"\n超时统计 (阈值300秒):")
                print(f"  已恢复总数: {row['total_resolved']}")
                print(f"  超时数量: {row['timeout_count']}")
                print(f"  超时率: {timeout_rate:.2f}%")
    
    except Exception as e:
        print(f"❌ 统计查询失败: {e}")
    
    print(f"\n" + "=" * 60)
    print("✅ 测试数据创建完成")
    print("=" * 60)
    
    # 提供测试建议
    print(f"\n【测试建议】")
    print("-" * 40)
    print("现在可以测试以下场景:")
    print("1. 基本统计: GET /api/alert-duration-stats")
    print("2. 不同阈值: GET /api/alert-duration-stats?threshold_seconds=600")
    print("3. 时间范围: GET /api/alert-duration-stats?start_time=2025-10-01%2000:00:00")
    print("4. 组合查询: 时间范围 + 自定义阈值")


def clear_test_data():
    """清理测试数据"""
    print("清理测试数据...")
    
    try:
        with email_db.get_connection() as conn:
            cursor = conn.cursor()
            
            # 删除测试数据（以TEST_开头的事件代码）
            cursor.execute("DELETE FROM event_records WHERE code LIKE '%_TEST_%'")
            deleted_count = cursor.rowcount
            
            conn.commit()
            print(f"✅ 已删除 {deleted_count} 条测试记录")
            
    except Exception as e:
        print(f"❌ 清理数据失败: {e}")


def show_sample_queries():
    """显示示例查询"""
    print("\n【API测试示例】")
    print("-" * 40)
    
    api_key = "api-fEq4upv9YKHmaKg8aYJLAVFOLUDdEBDUsi3uCltCDHU1oYcOwu5vT3rbOWpNAzpg8"
    base_url = "http://localhost:5001"
    
    examples = [
        {
            "name": "基本统计查询",
            "url": f"{base_url}/api/alert-duration-stats",
            "description": "查询所有数据，使用默认阈值300秒"
        },
        {
            "name": "自定义阈值查询",
            "url": f"{base_url}/api/alert-duration-stats?threshold_seconds=600",
            "description": "使用10分钟阈值"
        },
        {
            "name": "时间范围查询",
            "url": f"{base_url}/api/alert-duration-stats?start_time=2025-10-15%2000:00:00&end_time=2025-11-15%2023:59:59",
            "description": "查询最近一个月的数据"
        },
        {
            "name": "短阈值查询",
            "url": f"{base_url}/api/alert-duration-stats?threshold_seconds=120",
            "description": "使用2分钟阈值，查看更多超时告警"
        },
        {
            "name": "长阈值查询", 
            "url": f"{base_url}/api/alert-duration-stats?threshold_seconds=1800",
            "description": "使用30分钟阈值，查看严重超时告警"
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['name']}")
        print(f"   描述: {example['description']}")
        print(f"   命令: curl -H \"Authorization: Bearer {api_key}\" \\")
        print(f"              \"{example['url']}\"")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        clear_test_data()
    elif len(sys.argv) > 1 and sys.argv[1] == "examples":
        show_sample_queries()
    else:
        print("这将创建大量测试数据用于测试统计接口")
        print("继续吗? (y/N): ", end="")
        
        choice = input().strip().lower()
        if choice in ['y', 'yes']:
            create_test_data()
            show_sample_queries()
        else:
            print("已取消")
            
    print(f"\n使用方法:")
    print(f"  python {sys.argv[0]}          # 创建测试数据")
    print(f"  python {sys.argv[0]} clear    # 清理测试数据") 
    print(f"  python {sys.argv[0]} examples # 显示测试示例")