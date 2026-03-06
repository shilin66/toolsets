"""
数据库管理模块
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from loguru import logger
from contextlib import contextmanager


class EmailDatabase:
    """邮件数据库管理类"""
    
    def __init__(self, db_path: str = None):
        if db_path is None:
            # 默认使用data目录
            data_dir = os.path.join(os.getcwd(), "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "mail_listener.db")
        
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库表"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 创建邮件记录表（新结构）
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS email_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email_id INTEGER NOT NULL,
                        sender TEXT,
                        event_id INTEGER,
                        type TEXT,
                        update_time DATETIME,
                        create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(email_id),
                        FOREIGN KEY (event_id) REFERENCES event_records(id)
                    )
                ''')

                # 创建事件记录表
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS event_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        code TEXT,
                        monitor_id TEXT,
                        type TEXT NOT NULL,
                        status TEXT,
                        alert_time DATETIME,
                        recovery_time DATETIME,
                        duration_seconds INTEGER DEFAULT 0,
                        update_time DATETIME,
                        create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # 创建索引
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_email_id ON email_records(email_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_email_event_id ON email_records(event_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_email_type ON email_records(type)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_email_create_time ON email_records(create_time)
                ''')
                
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_event_code ON event_records(code)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_event_type ON event_records(type)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_event_status ON event_records(status)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_event_create_time ON event_records(create_time)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_event_monitor_id ON event_records(monitor_id)
                ''')
                
                conn.commit()
                logger.info(f"数据库初始化完成: {self.db_path}")
                
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    

    
    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # 使结果可以按列名访问
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    # ==================== 邮件记录操作 ====================
    
    def add_email_record(self, email_id: int, sender: str = None) -> bool:
        """添加邮件记录（初始记录，只记录邮件ID、发件人和创建时间）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 检查是否已存在
                cursor.execute('SELECT id FROM email_records WHERE email_id = ?', (email_id,))
                if cursor.fetchone():
                    logger.debug(f"邮件ID {email_id} 已存在，跳过添加")
                    return False
                
                # 插入新记录
                cursor.execute('''
                    INSERT INTO email_records (email_id, sender, create_time)
                    VALUES (?, ?, ?)
                ''', (email_id, sender, datetime.now()))
                
                conn.commit()
                logger.info(f"成功添加邮件记录: email_id={email_id}")
                return True
                
        except sqlite3.IntegrityError:
            logger.debug(f"邮件ID {email_id} 已存在（唯一约束）")
            return False
        except Exception as e:
            logger.error(f"添加邮件记录失败: {e}")
            return False
    
    def update_email_record(self, email_id: int, event_id: int = None, 
                           email_type: str = None) -> bool:
        """更新邮件记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 构建更新语句
                set_clauses = ["update_time = ?"]
                values = [datetime.now()]
                
                if event_id is not None:
                    set_clauses.append("event_id = ?")
                    values.append(event_id)
                
                if email_type is not None:
                    set_clauses.append("type = ?")
                    values.append(email_type)
                
                values.append(email_id)
                
                sql = f"UPDATE email_records SET {', '.join(set_clauses)} WHERE email_id = ?"
                cursor.execute(sql, values)
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"成功更新邮件记录: email_id={email_id}")
                    return True
                else:
                    logger.warning(f"未找到邮件记录: email_id={email_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"更新邮件记录失败: {e}")
            return False
    
    def get_email_record(self, email_id: int) -> Optional[Dict[str, Any]]:
        """获取邮件记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM email_records WHERE email_id = ?', (email_id,))
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"获取邮件记录失败: {e}")
            return None
    
    def email_exists(self, email_id: int) -> bool:
        """检查邮件是否已处理"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM email_records WHERE email_id = ?', (email_id,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"检查邮件是否存在失败: {e}")
            return False
    
    def get_email_records(self, limit: int = 100, offset: int = 0, 
                         email_type: str = None, event_id: int = None) -> List[Dict[str, Any]]:
        """获取邮件记录列表"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                conditions = []
                params = []
                
                if email_type:
                    conditions.append("type = ?")
                    params.append(email_type)
                
                if event_id is not None:
                    conditions.append("event_id = ?")
                    params.append(event_id)
                
                where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                
                sql = f'''
                    SELECT * FROM email_records 
                    {where_clause}
                    ORDER BY create_time DESC 
                    LIMIT ? OFFSET ?
                '''
                
                params.extend([limit, offset])
                cursor.execute(sql, params)
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"获取邮件记录列表失败: {e}")
            return []
    
    # ==================== 事件记录操作 ====================
    
    def add_event_record(self, code: str, event_type: str, status: str = None, monitor_id: str = None) -> Optional[int]:
        """添加事件记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                now = datetime.now()
                cursor.execute('''
                    INSERT INTO event_records (code, type, status, create_time, update_time, monitor_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (code, event_type, status, now, now, monitor_id))
                
                event_id = cursor.lastrowid
                conn.commit()
                logger.info(f"成功添加事件记录: id={event_id}, code={code}, type={event_type}")
                return event_id
                
        except Exception as e:
            logger.error(f"添加事件记录失败: {e}")
            return None
    
    def update_event_record(self, event_id: int, status: str = None, 
                           alert_time: datetime = None, recovery_time: datetime = None,
                           duration_seconds: int = None) -> bool:
        """更新事件记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 构建更新语句
                set_clauses = ["update_time = ?"]
                values = [datetime.now()]
                
                if status is not None:
                    set_clauses.append("status = ?")
                    values.append(status)
                
                if alert_time is not None:
                    set_clauses.append("alert_time = ?")
                    values.append(alert_time)
                
                if recovery_time is not None:
                    set_clauses.append("recovery_time = ?")
                    values.append(recovery_time)
                
                if duration_seconds is not None:
                    set_clauses.append("duration_seconds = ?")
                    values.append(duration_seconds)
                
                values.append(event_id)
                
                sql = f"UPDATE event_records SET {', '.join(set_clauses)} WHERE id = ?"
                cursor.execute(sql, values)
                
                if cursor.rowcount > 0:
                    conn.commit()
                    logger.info(f"成功更新事件记录: id={event_id}")
                    return True
                else:
                    logger.warning(f"未找到事件记录: id={event_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"更新事件记录失败: {e}")
            return False
    
    def get_event_record(self, event_id: int) -> Optional[Dict[str, Any]]:
        """获取事件记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM event_records WHERE id = ?', (event_id,))
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"获取事件记录失败: {e}")
            return None
    
    def get_event_records(self, limit: int = 100, offset: int = 0, 
                         event_type: str = None, status: str = None, 
                         code: str = None, monitor_id: str = None) -> List[Dict[str, Any]]:
        """获取事件记录列表"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                conditions = []
                params = []
                
                if event_type:
                    conditions.append("type = ?")
                    params.append(event_type)
                
                if status:
                    conditions.append("status = ?")
                    params.append(status)
                
                if code:
                    conditions.append("code = ?")
                    params.append(code)

                if monitor_id:
                    conditions.append("monitor_id = ?")
                    params.append(monitor_id)
                
                where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                
                sql = f'''
                    SELECT * FROM event_records 
                    {where_clause}
                    ORDER BY create_time DESC 
                    LIMIT ? OFFSET ?
                '''
                
                params.extend([limit, offset])
                cursor.execute(sql, params)
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"获取事件记录列表失败: {e}")
            return []
    
    def get_active_event_by_code_and_type(self, code: str, event_type: str, monitor_id: str = None) -> Optional[Dict[str, Any]]:
        """根据code和type获取活跃的事件（未恢复的告警）"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                sql = '''
                    SELECT * FROM event_records 
                    WHERE code = ? AND type = ? AND status = 'active'
                '''
                params = [code, event_type]
                
                if monitor_id:
                    sql += " AND monitor_id = ?"
                    params.append(monitor_id)
                
                sql += " ORDER BY create_time DESC LIMIT 1"
                
                cursor.execute(sql, params)
                row = cursor.fetchone()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"获取活跃事件失败: {e}")
            return None
    
    # ==================== 统计信息 ====================
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 邮件记录统计
                cursor.execute('SELECT COUNT(*) as total FROM email_records')
                total_emails = cursor.fetchone()['total']
                
                cursor.execute('''
                    SELECT type, COUNT(*) as count 
                    FROM email_records 
                    GROUP BY type
                ''')
                email_type_stats = {row['type'] or 'null': row['count'] for row in cursor.fetchall()}
                
                cursor.execute('''
                    SELECT COUNT(*) as today_count 
                    FROM email_records 
                    WHERE DATE(create_time) = DATE('now')
                ''')
                today_emails = cursor.fetchone()['today_count']
                
                # 事件记录统计
                cursor.execute('SELECT COUNT(*) as total FROM event_records')
                total_events = cursor.fetchone()['total']
                
                cursor.execute('''
                    SELECT status, COUNT(*) as count 
                    FROM event_records 
                    GROUP BY status
                ''')
                event_status_stats = {row['status'] or 'null': row['count'] for row in cursor.fetchall()}
                
                cursor.execute('''
                    SELECT type, COUNT(*) as count 
                    FROM event_records 
                    GROUP BY type
                ''')
                event_type_stats = {row['type'] or 'null': row['count'] for row in cursor.fetchall()}
                
                cursor.execute('''
                    SELECT COUNT(*) as today_count 
                    FROM event_records 
                    WHERE DATE(create_time) = DATE('now')
                ''')
                today_events = cursor.fetchone()['today_count']
                
                # 活跃告警数
                cursor.execute('''
                    SELECT COUNT(*) as active_count 
                    FROM event_records 
                    WHERE status = 'active'
                ''')
                active_alerts = cursor.fetchone()['active_count']
                
                return {
                    'email_records': {
                        'total': total_emails,
                        'today': today_emails,
                        'type_distribution': email_type_stats
                    },
                    'event_records': {
                        'total': total_events,
                        'today': today_events,
                        'active_alerts': active_alerts,
                        'status_distribution': event_status_stats,
                        'type_distribution': event_type_stats
                    }
                }
                
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def get_alert_duration_statistics(self, start_time: str = None, end_time: str = None, 
                                    threshold_seconds: int = 300) -> Dict[str, Any]:
        """获取告警持续时间统计
        
        Args:
            start_time: 开始时间 (格式: YYYY-MM-DD HH:MM:SS)
            end_time: 结束时间 (格式: YYYY-MM-DD HH:MM:SS)
            threshold_seconds: 告警时间阈值（秒），默认300秒（5分钟）
            
        Returns:
            Dict: 包含各类型告警超时统计的字典
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 构建时间过滤条件
                time_conditions = []
                params = [threshold_seconds]
                
                if start_time:
                    time_conditions.append("alert_time >= ?")
                    params.append(start_time)
                
                if end_time:
                    time_conditions.append("alert_time <= ?")
                    params.append(end_time)
                
                where_clause = ""
                if time_conditions:
                    where_clause = f"AND {' AND '.join(time_conditions)}"
                
                # 查询各类型中告警时间超过阈值的数量
                sql = f'''
                    SELECT 
                        type,
                        COUNT(*) as total_count,
                        COUNT(CASE WHEN duration_seconds > ? THEN 1 END) as timeout_count,
                        AVG(duration_seconds) as avg_duration,
                        MAX(duration_seconds) as max_duration,
                        MIN(duration_seconds) as min_duration
                    FROM event_records 
                    WHERE status = 'resolved' 
                      AND duration_seconds > 0
                      {where_clause}
                    GROUP BY type
                    ORDER BY timeout_count DESC, type
                '''
                
                cursor.execute(sql, params)
                type_stats = []

                # 将查询结果转换为字典，便于后续处理
                type_stats_dict = {}
                for row in cursor.fetchall():
                    type_stats_dict[row['type']] = {
                        'type': row['type'],
                        'total_count': row['total_count'],
                        'timeout_count': row['timeout_count'],
                        'avg_duration': round(row['avg_duration'] or 0, 2),
                        'max_duration': row['max_duration'] or 0,
                        'min_duration': row['min_duration'] or 0
                    }
                # 确保包含所有指定的类型
                required_types = ['node_down', 'fms_system', 'ups_failure', 'hardware', 'link_optical_receive','core_network_port']

                # 对于每个必需的类型，如果不存在则添加默认值
                for required_type in required_types:
                    if required_type not in type_stats_dict:
                        type_stats_dict[required_type] = {
                            'type': required_type,
                            'total_count': 0,
                            'timeout_count': 0,
                            'avg_duration': 0.0,
                            'max_duration': 0,
                            'min_duration': 0
                        }

                # 将字典转换为列表
                type_stats = list(type_stats_dict.values())
                # 总体统计
                total_sql = f'''
                    SELECT 
                        COUNT(*) as total_alerts,
                        COUNT(CASE WHEN duration_seconds > ? THEN 1 END) as total_timeout,
                        AVG(duration_seconds) as overall_avg_duration
                    FROM event_records 
                    WHERE status = 'resolved' 
                      AND duration_seconds > 0
                      {where_clause}
                '''
                
                cursor.execute(total_sql, params)
                total_row = cursor.fetchone()
                
                total_timeout_rate = 0
                if total_row['total_alerts'] > 0:
                    total_timeout_rate = (total_row['total_timeout'] / total_row['total_alerts'] * 100)
                
                # 时间范围内的活跃告警（未恢复且超过阈值）
                active_sql = f'''
                    SELECT 
                        type,
                        COUNT(*) as active_timeout_count
                    FROM event_records 
                    WHERE status = 'active' 
                      AND alert_time IS NOT NULL
                      AND (julianday('now') - julianday(alert_time)) * 86400 > ?
                      {where_clause}
                    GROUP BY type
                '''
                
                cursor.execute(active_sql, params)
                active_timeouts = {row['type']: row['active_timeout_count'] for row in cursor.fetchall()}
                dong_zhi_door_alert_counts  = self.count_kamonitor_alert_emails(start_time, end_time)
                type_stats.append({
                    'type': 'dong_zhi_door',
                    'total_count': dong_zhi_door_alert_counts,
                    'timeout_count': 0,
                    'avg_duration': 0.0,
                    'max_duration': 0,
                    'min_duration': 0
                })
                return {
                    'start_time': start_time,
                    'end_time': end_time,
                    'by_type': type_stats,
                }
                
        except Exception as e:
            logger.error(f"获取告警持续时间统计失败: {e}")
            return {
                'error': str(e),
                'query_params': {
                    'start_time': start_time,
                    'end_time': end_time,
                    'threshold_seconds': threshold_seconds
                }
            }
    
    def cleanup_old_records(self, days: int = 30) -> Dict[str, int]:
        """清理旧记录"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # 清理邮件记录
                cursor.execute('''
                    DELETE FROM email_records 
                    WHERE create_time < datetime('now', '-{} days')
                '''.format(days))
                deleted_emails = cursor.rowcount
                
                # 清理事件记录
                cursor.execute('''
                    DELETE FROM event_records 
                    WHERE create_time < datetime('now', '-{} days')
                '''.format(days))
                deleted_events = cursor.rowcount
                
                conn.commit()
                
                if deleted_emails > 0 or deleted_events > 0:
                    logger.info(f"清理了 {deleted_emails} 条邮件记录和 {deleted_events} 条事件记录（超过 {days} 天）")
                
                return {
                    'emails': deleted_emails,
                    'events': deleted_events
                }
                
        except Exception as e:
            logger.error(f"清理旧记录失败: {e}")
            return {'emails': 0, 'events': 0}

            return {'emails': 0, 'events': 0}

    def count_kamonitor_alert_emails(self, start_time: str = None, end_time: str = None) -> int:
        """统计发件人包含kamonitor@@sinnet.com.cn并且类型是alert的邮件数量"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # 构建时间过滤条件
                time_conditions = []
                params = []

                if start_time:
                    time_conditions.append("create_time >= ?")
                    params.append(start_time)

                if end_time:
                    time_conditions.append("create_time <= ?")
                    params.append(end_time)

                where_clause = "WHERE sender LIKE '%kamonitor2@sinnet.com.cn%' AND type = 'alert'"

                if time_conditions:
                    where_clause += " AND " + " AND ".join(time_conditions)

                sql = f'''
                    SELECT COUNT(*) as count
                    FROM email_records 
                    {where_clause}
                '''

                cursor.execute(sql, params)

                row = cursor.fetchone()
                return row['count'] if row else 0

        except Exception as e:
            logger.error(f"统计kamonitor告警邮件失败: {e}")
            return 0
# 全局数据库实例
email_db = EmailDatabase()