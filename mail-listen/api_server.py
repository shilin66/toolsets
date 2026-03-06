#!/usr/bin/env python
"""
邮件监听系统 API 服务
"""
from flask import Flask, request, jsonify
from datetime import datetime
from loguru import logger
import sys
from functools import wraps

from database import email_db
from config import settings
from node_interface import get_target_node_interfaces

app = Flask(__name__)

# 配置日志
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

# API Key 配置
API_KEY = settings.api_key

def require_api_key(f):
    """API Key 校验装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 获取 Authorization 头
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({
                'success': False,
                'message': '缺少 Authorization 头'
            }), 401
        
        # 检查 Bearer 格式
        if not auth_header.startswith('Bearer '):
            return jsonify({
                'success': False,
                'message': 'Authorization 头格式错误，应为: Bearer <api_key>'
            }), 401
        
        # 提取 API Key
        provided_key = auth_header[7:]  # 去掉 "Bearer " 前缀
        
        if provided_key != API_KEY:
            logger.warning("API Key 校验失败")
            return jsonify({
                'success': False,
                'message': 'API Key 无效'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function

def parse_time(time_str, field_name="time"):
    """
    解析时间字符串，支持多种格式
    
    Args:
        time_str: 时间字符串
        field_name: 字段名称（用于日志）
    
    Returns:
        datetime: 解析后的时间对象
    """
    if not time_str:
        return datetime.now()
    
    try:
        # 首选格式：2025-11-01 22:53:17
        return datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            # 备选格式：ISO 格式
            return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        except ValueError:
            logger.warning(f"{field_name} 格式错误，使用当前时间: {time_str}")
            return datetime.now()


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'message': '服务运行正常',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/api/alert', methods=['POST'])
@require_api_key
def create_alert():
    """
    接口1：创建告警事件
    
    参数：
        email_id: 邮件ID
        email_type: 邮件类型（如：告警）
        event_code: 事件代码
        event_type: 事件类型（6个场景之一）
        status: 事件状态（如：active）
        alert_time: 告警时间（ISO格式字符串，可选，默认当前时间）
    
    返回：
        {
            "success": true,
            "message": "告警事件创建成功",
            "data": {
                "event_id": 1,
                "email_id": 12345
            }
        }
    """
    try:
        # 获取参数
        data = request.get_json()
        
        email_id = data.get('email_id')
        email_type = data.get('email_type')
        event_code = data.get('event_code')
        event_type = data.get('event_type')
        monitor_id = data.get('monitor_id')
        status = data.get('status', 'active')
        alert_time_str = data.get('alert_time')

        if event_type == "core_network_port":
            email_id = 0
        # 参数验证
        if email_id is None or not email_type or not event_code or not event_type:
            return jsonify({
                'success': False,
                'message': '缺少必需参数：email_id, email_type, event_code, event_type'
            }), 400
        
        # 解析告警时间
        alert_time = parse_time(alert_time_str, "alert_time")
        
        # 检查邮件是否存在
        if email_id != 0 and  not email_db.email_exists(email_id):
            return jsonify({
                'success': False,
                'message': f'邮件 ID {email_id} 不存在，请先通过邮件监听记录邮件'
            }), 404
        
        # 1. 创建事件记录
        event_id = email_db.add_event_record(
            code=event_code,
            event_type=event_type,
            status=status,
            monitor_id=monitor_id
        )
        
        if not event_id:
            return jsonify({
                'success': False,
                'message': '创建事件记录失败'
            }), 500
        
        logger.info(f"创建事件记录: event_id={event_id}, code={event_code}, type={event_type}")
        
        # 2. 更新事件的告警时间
        email_db.update_event_record(
            event_id=event_id,
            alert_time=alert_time
        )
        
        # 3. 更新邮件记录，关联事件
        if event_type != "core_network_port":
            success = email_db.update_email_record(
                email_id=email_id,
                event_id=event_id,
                email_type=email_type
            )

            if not success:
                return jsonify({
                    'success': False,
                    'message': f'更新邮件记录失败：email_id={email_id}'
                }), 500
        
        logger.info(f"告警事件创建成功: event_id={event_id}, email_id={email_id}")
        
        return jsonify({
            'success': True,
            'message': '告警事件创建成功',
            'data': {
                'event_id': event_id,
                'email_id': email_id,
                'event_code': event_code,
                'event_type': event_type,
                'monitor_id': monitor_id,
                'status': status,
                'alert_time': alert_time.strftime('%Y-%m-%d %H:%M:%S')
            }
        }), 201
        
    except Exception as e:
        logger.error(f"创建告警事件失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500


@app.route('/api/recovery', methods=['POST'])
@require_api_key
def create_recovery():
    """
    接口2：创建恢复事件
    
    参数：
        email_id: 邮件ID
        email_type: 邮件类型（如：恢复）
        event_code: 事件代码
        status: 事件状态（如：resolved）
        recovery_time: 恢复时间（ISO格式字符串，可选，默认当前时间）
    
    返回：
        {
            "success": true,
            "message": "恢复事件处理成功",
            "data": {
                "event_id": 1,
                "email_id": 12346
            }
        }
    """
    try:
        # 获取参数
        data = request.get_json()
        
        email_id = data.get('email_id')
        email_type = data.get('email_type')
        event_code = data.get('event_code')
        event_type = data.get('event_type')
        monitor_id = data.get('monitor_id')
        status = data.get('status', 'resolved')
        recovery_time_str = data.get('recovery_time')

        if event_type == "core_network_port":
            email_id = 0
        # 参数验证
        if email_id is None or not email_type or not event_code:
            return jsonify({
                'success': False,
                'message': '缺少必需参数：email_id, email_type, event_code'
            }), 400
        
        # 解析恢复时间
        recovery_time = parse_time(recovery_time_str, "recovery_time")
        
        # 检查邮件是否存在
        if email_id != 0 and not email_db.email_exists(email_id):
            return jsonify({
                'success': False,
                'message': f'邮件 ID {email_id} 不存在，请先通过邮件监听记录邮件'
            }), 404
        
        # 1. 根据 event_code 和 monitor_id 查找活跃事件
        # 注意：这里需要知道 event_type，但接口参数中没有提供
        # 我们需要查询所有匹配 code 且状态为 active 的事件
        active_events = email_db.get_event_records(code=event_code, monitor_id=monitor_id, limit=1)
        
        if not active_events:
            # 没有找到匹配的活跃事件，创建一个活跃事件
            event_id = email_db.add_event_record(
                code=event_code,
                event_type=event_type,
                status=status,
                monitor_id=monitor_id
            )
            return jsonify({
                'success': False,
                'message': f'未找到事件代码为 {event_code} 的活跃事件'
            }), 404
        
        active_event = active_events[0]
        event_id = active_event['id']
        
        logger.info(f"找到活跃事件: event_id={event_id}, code={event_code}")
        
        # 计算告警持续时间
        duration_seconds = 0
        if active_event.get('alert_time') and recovery_time:
            try:
                # 解析告警时间
                alert_time_obj = active_event['alert_time']
                if isinstance(alert_time_obj, str):
                    alert_time_obj = datetime.fromisoformat(alert_time_obj.replace('Z', '+00:00'))
                
                # 移除时区信息进行计算
                if alert_time_obj.tzinfo:
                    alert_time_obj = alert_time_obj.replace(tzinfo=None)
                if recovery_time.tzinfo:
                    recovery_time_calc = recovery_time.replace(tzinfo=None)
                else:
                    recovery_time_calc = recovery_time
                
                # 计算持续时间（秒）
                duration = recovery_time_calc - alert_time_obj
                duration_seconds = int(duration.total_seconds())
                
                logger.info(f"计算告警持续时间: {duration_seconds} 秒")
                
            except Exception as e:
                logger.warning(f"计算告警持续时间失败: {e}")
                duration_seconds = 0
        
        # 2. 更新事件状态、恢复时间和持续时间
        success = email_db.update_event_record(
            event_id=event_id,
            status=status,
            recovery_time=recovery_time,
            duration_seconds=duration_seconds
        )
        
        if not success:
            return jsonify({
                'success': False,
                'message': f'更新事件记录失败：event_id={event_id}'
            }), 500
        
        # 3. 更新邮件记录，关联事件
        if event_type != "core_network_port":
            success = email_db.update_email_record(
                email_id=email_id,
                event_id=event_id,
                email_type=email_type
            )

            if not success:
                return jsonify({
                    'success': False,
                    'message': f'更新邮件记录失败：email_id={email_id}'
                }), 500
        
        logger.info(f"恢复事件处理成功: event_id={event_id}, email_id={email_id}")
        
        return jsonify({
            'success': True,
            'message': '恢复事件处理成功',
            'data': {
                'event_id': event_id,
                'email_id': email_id,
                'email_id': email_id,
                'event_code': event_code,
                'monitor_id': monitor_id,
                'status': status,
                'recovery_time': recovery_time.strftime('%Y-%m-%d %H:%M:%S')
            }
        }), 200
        
    except Exception as e:
        logger.error(f"处理恢复事件失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500


@app.route('/api/event', methods=['GET'])
@require_api_key
def get_event():
    """
    接口3：根据事件代码查询事件记录
    
    参数：
        event_code: 事件代码（查询参数）
        event_type: 事件类型（查询参数）
        monitor_id: 监控ID（查询参数）
        status: 事件状态过滤（可选，查询参数）
        limit: 返回数量限制（可选，查询参数，默认10）
    
    返回：
        {
            "success": true,
            "message": "查询成功",
            "data": [
                {
                    "id": 1,
                    "code": "SERVER01_CPU_HIGH",
                    "type": "CPU_HIGH",
                    "status": "resolved",
                    "alert_time": "2025-11-10T12:00:00",
                    "recovery_time": "2025-11-10T12:05:00",
                    "create_time": "2025-11-10T12:00:00",
                    "is_timeout": false,
                    "duration_minutes": 5.0
                }
            ],
            "count": 1
        }
    """
    try:
        # 获取查询参数
        event_code = request.args.get('event_code')
        if not event_code:
             return jsonify({
                'success': False,
                'message': '缺少必需参数：event_code'
            }), 400
        event_type = request.args.get('event_type')
        monitor_id = request.args.get('monitor_id')
        status = request.args.get('status')
        limit = request.args.get('limit', 10, type=int)
        timeout_minutes = request.args.get('timeout_minutes', 3, type=int)  # 默认3分钟
        
        # 查询事件记录
        events = email_db.get_event_records(
            code=event_code,
            event_type=event_type,
            monitor_id=monitor_id,
            status=status,
            limit=limit
        )
        
        # 处理每个事件，添加超时检查
        current_time = datetime.now()
        processed_events = []
        
        for event in events:
            # 解析告警时间
            if event['alert_time']:
                try:
                    if isinstance(event['alert_time'], str):
                        alert_time = datetime.fromisoformat(event['alert_time'].replace('Z', '+00:00'))
                    else:
                        alert_time = event['alert_time']
                    
                    # 计算持续时间
                    if event['recovery_time']:
                        # 已恢复，计算告警到恢复的时间
                        if isinstance(event['recovery_time'], str):
                            recovery_time = datetime.fromisoformat(event['recovery_time'].replace('Z', '+00:00'))
                        else:
                            recovery_time = event['recovery_time']
                        
                        # 移除时区信息进行计算
                        if alert_time.tzinfo:
                            alert_time = alert_time.replace(tzinfo=None)
                        if recovery_time.tzinfo:
                            recovery_time = recovery_time.replace(tzinfo=None)
                        
                        duration = (recovery_time - alert_time).total_seconds() / 60
                        is_timeout = False  # 已恢复的不算超时
                    else:
                        # 未恢复，计算告警到现在的时间
                        if alert_time.tzinfo:
                            alert_time = alert_time.replace(tzinfo=None)
                        
                        duration = (current_time - alert_time).total_seconds() / 60
                        is_timeout = duration > timeout_minutes and event['status'] == 'active'
                    
                    event['duration_minutes'] = round(duration, 2)
                    event['is_timeout'] = is_timeout
                    
                    if is_timeout:
                        logger.warning(f"事件 {event['code']} 超时: {duration:.2f} 分钟 > {timeout_minutes} 分钟")
                    
                except Exception as e:
                    logger.error(f"处理事件时间时出错: {e}")
                    event['duration_minutes'] = None
                    event['is_timeout'] = False
            else:
                event['duration_minutes'] = None
                event['is_timeout'] = False
            
            processed_events.append(event)
        
        logger.info(f"查询事件: code={event_code}, status={status}, 找到 {len(processed_events)} 条记录")
        
        return jsonify({
            'success': True,
            'message': '查询成功',
            'data': processed_events,
            'count': len(processed_events)
        }), 200
        
    except Exception as e:
        logger.error(f"查询事件失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500


@app.route('/api/events', methods=['GET'])
@require_api_key
def get_events():
    """
    查询事件列表（额外接口）
    
    参数：
        event_type: 事件类型过滤（可选）
        status: 事件状态过滤（可选）
        limit: 返回数量限制（可选，默认10）
        offset: 偏移量（可选，默认0）
        timeout_minutes: 超时阈值（可选，默认3分钟）
    """
    try:
        event_type = request.args.get('event_type')
        status = request.args.get('status')
        limit = request.args.get('limit', 10, type=int)
        offset = request.args.get('offset', 0, type=int)
        timeout_minutes = request.args.get('timeout_minutes', 3, type=int)
        
        events = email_db.get_event_records(
            event_type=event_type,
            status=status,
            limit=limit,
            offset=offset
        )
        
        # 处理每个事件，添加超时检查
        current_time = datetime.now()
        processed_events = []
        
        for event in events:
            if event['alert_time']:
                try:
                    if isinstance(event['alert_time'], str):
                        alert_time = datetime.fromisoformat(event['alert_time'].replace('Z', '+00:00'))
                    else:
                        alert_time = event['alert_time']
                    
                    if event['recovery_time']:
                        if isinstance(event['recovery_time'], str):
                            recovery_time = datetime.fromisoformat(event['recovery_time'].replace('Z', '+00:00'))
                        else:
                            recovery_time = event['recovery_time']
                        
                        if alert_time.tzinfo:
                            alert_time = alert_time.replace(tzinfo=None)
                        if recovery_time.tzinfo:
                            recovery_time = recovery_time.replace(tzinfo=None)
                        
                        duration = (recovery_time - alert_time).total_seconds() / 60
                        is_timeout = False
                    else:
                        if alert_time.tzinfo:
                            alert_time = alert_time.replace(tzinfo=None)
                        
                        duration = (current_time - alert_time).total_seconds() / 60
                        is_timeout = duration > timeout_minutes and event['status'] == 'active'
                    
                    event['duration_minutes'] = round(duration, 2)
                    event['is_timeout'] = is_timeout
                    
                except Exception as e:
                    logger.error(f"处理事件时间时出错: {e}")
                    event['duration_minutes'] = None
                    event['is_timeout'] = False
            else:
                event['duration_minutes'] = None
                event['is_timeout'] = False
            
            processed_events.append(event)
        
        return jsonify({
            'success': True,
            'message': '查询成功',
            'data': processed_events,
            'count': len(processed_events)
        }), 200
        
    except Exception as e:
        logger.error(f"查询事件列表失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500


@app.route('/api/statistics', methods=['GET'])
@require_api_key
def get_statistics():
    """
    获取统计信息（额外接口）
    """
    try:
        stats = email_db.get_statistics()
        
        return jsonify({
            'success': True,
            'message': '查询成功',
            'data': stats
        }), 200
        
    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500


@app.route('/api/alert-duration-stats', methods=['GET'])
@require_api_key
def get_alert_duration_statistics():
    """
    获取告警持续时间统计
    
    查询参数：
        start_time: 开始时间（格式：YYYY-MM-DD HH:MM:SS）
        end_time: 结束时间（格式：YYYY-MM-DD HH:MM:SS）
        threshold_seconds: 告警时间阈值（秒），默认300秒（5分钟）
    
    返回：
        {
            "success": true,
            "message": "查询成功",
            "data": {
                "query_params": {
                    "start_time": "2025-11-01 00:00:00",
                    "end_time": "2025-11-30 23:59:59",
                    "threshold_seconds": 300
                },
                "summary": {
                    "total_alerts": 100,
                    "total_timeout": 25,
                    "timeout_rate": 25.0,
                    "overall_avg_duration": 450.5
                },
                "by_type": [
                    {
                        "type": "CPU_HIGH",
                        "total_count": 50,
                        "timeout_count": 15,
                        "timeout_rate": 30.0,
                        "avg_duration": 520.3,
                        "max_duration": 1800,
                        "min_duration": 60
                    }
                ],
                "active_timeouts": {
                    "CPU_HIGH": 3,
                    "MEMORY_HIGH": 1
                }
            }
        }
    """
    try:
        # 获取查询参数
        start_time = request.args.get('start_time')
        end_time = request.args.get('end_time')
        threshold_seconds = request.args.get('threshold_seconds', 300, type=int)
        
        # 参数验证
        if threshold_seconds <= 0:
            return jsonify({
                'success': False,
                'message': '告警时间阈值必须大于0'
            }), 400
        
        # 时间格式验证
        if start_time:
            try:
                datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': '开始时间格式错误，应为：YYYY-MM-DD HH:MM:SS'
                }), 400
        
        if end_time:
            try:
                datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': '结束时间格式错误，应为：YYYY-MM-DD HH:MM:SS'
                }), 400
        # 如果start_time和end_time都为None，则使用默认值：查询统计上一个月的数据
        if not start_time and not end_time:
            # 获取当前日期
            now = datetime.now()
            # 计算上个月的开始和结束时间
            # 上个月第一天
            if now.month == 1:
                start_time = datetime(now.year - 1, 12, 1).strftime('%Y-%m-%d %H:%M:%S')
            else:
                start_time = datetime(now.year, now.month - 1, 1).strftime('%Y-%m-%d %H:%M:%S')

            # 本月第一天（作为结束时间）
            if now.month == 1:
                end_time = datetime(now.year, 1, 1).strftime('%Y-%m-%d %H:%M:%S')
            else:
                end_time = datetime(now.year, now.month, 1).strftime('%Y-%m-%d %H:%M:%S')

        # 获取统计数据
        stats = email_db.get_alert_duration_statistics(
            start_time=start_time,
            end_time=end_time,
            threshold_seconds=threshold_seconds
        )

        # 检查是否有错误
        if 'error' in stats:
            return jsonify({
                'success': False,
                'message': f'统计查询失败: {stats["error"]}',
                'query_params': stats.get('query_params', {})
            }), 500
        
        logger.info(f"告警持续时间统计查询成功: start_time={start_time}, end_time={end_time}, threshold={threshold_seconds}s")
        
        return jsonify({
            'success': True,
            'message': '查询成功',
            'data': stats
        }), 200
        
    except Exception as e:
        logger.error(f"获取告警持续时间统计失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500

@app.route('/api/get_node_interface', methods=['GET'])
@require_api_key
def get_node_interface():
    try:
       target_node_name = request.args.get('target_node_name')
       status = request.args.get('status')
       # target_node_name  不能为空
       if not target_node_name:
           return jsonify({
               'success': False,
               'message': '请提供目标节点名称'
           }), 400
       interfaces = get_target_node_interfaces(target_node_name, status)
       # 遍历interfaces 取出name，拼接成markdown中列表的格式文本,不需要是数组，只需要是一个字符串
       interfaces_txt = '\n'.join([f"- {interface['name']}" for interface in interfaces])
       return jsonify({
           'interfaces': interfaces,
           'interfaces_txt': interfaces_txt
       }), 200
    except Exception as e:
        logger.error(f"获取接口列表失败: {e}")
        return jsonify({
            'success': False,
            'message': f'服务器错误: {str(e)}'
        }), 500


if __name__ == '__main__':
    
    logger.info("启动 API 服务...")
    logger.info(f"API 地址: http://0.0.0.0:{settings.api_port}")
    logger.info("API Key 使用方式:")
    logger.info("  Header: Authorization: Bearer <your-api-key>")

    app.run(host='0.0.0.0', port=settings.api_port, debug=True)
