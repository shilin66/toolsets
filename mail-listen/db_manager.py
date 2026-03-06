"""
数据库管理工具
"""
import sys
from datetime import datetime, timedelta
from loguru import logger
from database import email_db


def show_statistics():
    """显示统计信息"""
    logger.info("=== 邮件处理统计 ===")
    
    stats = email_db.get_statistics()
    
    if not stats:
        logger.error("获取统计信息失败")
        return
    
    logger.info(f"总记录数: {stats.get('total_records', 0)}")
    logger.info(f"今日记录数: {stats.get('today_records', 0)}")
    
    logger.info("\n按状态分布:")
    for status, count in stats.get('status_distribution', {}).items():
        logger.info(f"  {status}: {count}")
    
    logger.info("\n按类型分布:")
    for email_type, count in stats.get('type_distribution', {}).items():
        logger.info(f"  {email_type}: {count}")


def show_recent_records(limit: int = 20):
    """显示最近的记录"""
    logger.info(f"=== 最近 {limit} 条记录 ===")
    
    records = email_db.get_email_records(limit=limit)
    
    if not records:
        logger.info("没有找到记录")
        return
    
    for record in records:
        created_time = record['created_time']
        logger.info(f"ID: {record['email_id']} | "
                   f"类型: {record['type'] or 'N/A'} | "
                   f"状态: {record['status'] or 'N/A'} | "
                   f"时间: {created_time}")


def show_records_by_status(status: str, limit: int = 10):
    """按状态显示记录"""
    logger.info(f"=== 状态为 '{status}' 的记录 ===")
    
    records = email_db.get_email_records(limit=limit, status=status)
    
    if not records:
        logger.info(f"没有找到状态为 '{status}' 的记录")
        return
    
    for record in records:
        created_time = record['created_time']
        logger.info(f"ID: {record['email_id']} | "
                   f"类型: {record['type'] or 'N/A'} | "
                   f"通知状态: {record['notify_status'] or 'N/A'} | "
                   f"时间: {created_time}")


def cleanup_old_records(days: int = 30):
    """清理旧记录"""
    logger.info(f"=== 清理超过 {days} 天的记录 ===")
    
    deleted_count = email_db.cleanup_old_records(days)
    
    if deleted_count > 0:
        logger.info(f"成功清理 {deleted_count} 条记录")
    else:
        logger.info("没有需要清理的记录")


def test_database():
    """测试数据库功能"""
    logger.info("=== 数据库功能测试 ===")
    
    # 测试添加记录
    test_email_id = 999999
    logger.info(f"测试添加记录: {test_email_id}")
    
    success = email_db.add_email_record(
        email_id=test_email_id,
        email_type='test',
        status='test_status',
        notify_status='test_notify'
    )
    
    if success:
        logger.info("✅ 添加记录成功")
        
        # 测试获取记录
        record = email_db.get_email_record(test_email_id)
        if record:
            logger.info(f"✅ 获取记录成功: {record}")
            
            # 测试更新记录
            update_success = email_db.update_email_record(
                email_id=test_email_id,
                status='updated_status',
                alert_time=datetime.now()
            )
            
            if update_success:
                logger.info("✅ 更新记录成功")
                
                # 再次获取验证
                updated_record = email_db.get_email_record(test_email_id)
                logger.info(f"✅ 更新后的记录: {updated_record}")
            else:
                logger.error("❌ 更新记录失败")
        else:
            logger.error("❌ 获取记录失败")
    else:
        logger.error("❌ 添加记录失败")
    
    logger.info("数据库功能测试完成")


def main():
    """主函数"""
    logger.remove()
    logger.add(sys.stdout, level="INFO", 
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> - <level>{message}</level>")
    
    if len(sys.argv) < 2:
        logger.info("数据库管理工具")
        logger.info("用法:")
        logger.info("  python db_manager.py stats          - 显示统计信息")
        logger.info("  python db_manager.py recent [数量]   - 显示最近记录")
        logger.info("  python db_manager.py status <状态>  - 按状态查询")
        logger.info("  python db_manager.py cleanup [天数] - 清理旧记录")
        logger.info("  python db_manager.py test           - 测试数据库")
        return
    
    command = sys.argv[1]
    
    try:
        if command == "stats":
            show_statistics()
        elif command == "recent":
            limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
            show_recent_records(limit)
        elif command == "status":
            if len(sys.argv) < 3:
                logger.error("请指定状态")
                return
            status = sys.argv[2]
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            show_records_by_status(status, limit)
        elif command == "cleanup":
            days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            cleanup_old_records(days)
        elif command == "test":
            test_database()
        else:
            logger.error(f"未知命令: {command}")
    
    except Exception as e:
        logger.error(f"执行命令失败: {e}")


if __name__ == "__main__":
    main()