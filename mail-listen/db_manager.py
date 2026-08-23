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
    
    email_stats = stats.get('email_records', {})
    ticket_stats = stats.get('ticket_records', {})
    logger.info(f"邮件总记录数: {email_stats.get('total', 0)}")
    logger.info(f"今日邮件记录数: {email_stats.get('today', 0)}")
    logger.info(f"工单总记录数: {ticket_stats.get('total', 0)}")
    logger.info(f"今日工单记录数: {ticket_stats.get('today', 0)}")


def show_recent_records(limit: int = 20):
    """显示最近的记录"""
    logger.info(f"=== 最近 {limit} 条记录 ===")
    
    records = email_db.get_email_records(limit=limit)
    
    if not records:
        logger.info("没有找到记录")
        return
    
    for record in records:
        created_time = record['create_time']
        logger.info(f"ID: {record['email_id']} | "
                   f"发件人: {record['sender'] or 'N/A'} | "
                   f"主题: {record['subject'] or 'N/A'} | "
                   f"时间: {created_time}")


def show_records_by_sender(sender: str, limit: int = 10):
    """按发件人显示记录"""
    logger.info(f"=== 发件人包含 '{sender}' 的记录 ===")
    
    records = email_db.get_email_records(limit=limit, sender=sender)
    
    if not records:
        logger.info(f"没有找到发件人包含 '{sender}' 的记录")
        return
    
    for record in records:
        created_time = record['create_time']
        logger.info(f"ID: {record['email_id']} | "
                   f"发件人: {record['sender'] or 'N/A'} | "
                   f"主题: {record['subject'] or 'N/A'} | "
                   f"时间: {created_time}")


def cleanup_old_records(days: int = 30):
    """清理旧记录"""
    logger.info(f"=== 清理超过 {days} 天的记录 ===")
    
    deleted_count = email_db.cleanup_old_records(days)
    
    if any(deleted_count.values()):
        logger.info(f"成功清理记录: {deleted_count}")
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
        sender='sender@example.com',
        receiver=['receiver@example.com'],
        subject='test subject',
        content='test content'
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
                subject='updated subject',
                content='updated content'
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
        logger.info("  python db_manager.py sender <发件人> - 按发件人查询")
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
        elif command == "sender":
            if len(sys.argv) < 3:
                logger.error("请指定发件人")
                return
            sender = sys.argv[2]
            limit = int(sys.argv[3]) if len(sys.argv) > 3 else 10
            show_records_by_sender(sender, limit)
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
