#!/usr/bin/env python
"""
邮件监听系统主程序
同时启动 API 服务和邮件监听服务
"""
import sys
import signal
import threading
import time
from loguru import logger

from api_server import app
from mail_listener import MailListener
from config import settings


class MainService:
    """主服务管理类"""
    
    def __init__(self):
        self.mail_listener = None
        self.api_thread = None
        self.running = False
        
        # 配置日志
        logger.remove()
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>"
        )
        
        logger.add(
            "logs/main.log",
            rotation="1 day",
            retention="30 days",
            level=settings.log_level,
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} - {message}"
        )
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        logger.info(f"收到信号 {signum}，正在停止服务...")
        self.stop()
    
    def start_api_server(self):
        """启动 API 服务"""
        try:
            logger.info("=" * 60)
            logger.info("启动 API 服务")
            logger.info("=" * 60)
            logger.info(f"API 地址: http://0.0.0.0:{settings.api_port}")
            logger.info("API 接口:")
            logger.info("  POST   /api/alert       - 创建告警事件")
            logger.info("  POST   /api/recovery    - 创建恢复事件")
            logger.info("  GET    /api/event/<code> - 根据事件代码查询")
            logger.info("  GET    /api/events      - 查询事件列表")
            logger.info("  GET    /api/statistics  - 获取统计信息")
            logger.info("  GET    /health          - 健康检查")
            logger.info("=" * 60)
            
            # 关闭 Flask 的默认日志
            import logging
            log = logging.getLogger('werkzeug')
            log.setLevel(logging.ERROR)
            
            # 启动 Flask 应用
            app.run(
                host='0.0.0.0',
                port=settings.api_port,
                debug=False,
                use_reloader=False,
                threaded=True
            )
        except Exception as e:
            logger.error(f"API 服务启动失败: {e}")
    
    def start_mail_listener(self):
        """启动邮件监听服务（在主线程中运行）"""
        try:
            logger.info("=" * 60)
            logger.info("启动邮件监听服务")
            logger.info("=" * 60)
            
            self.mail_listener = MailListener()
            self.mail_listener.start()
            
        except Exception as e:
            logger.error(f"邮件监听服务启动失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
    
    def start(self):
        """启动所有服务"""
        logger.info("=" * 60)
        logger.info("邮件监听系统启动")
        logger.info("=" * 60)
        logger.info(f"邮箱: {settings.email_address}")
        logger.info(f"IMAP服务器: {settings.imap_server}:{settings.imap_port}")
        logger.info(f"日志级别: {settings.log_level}")
        logger.info("=" * 60)
        
        self.running = True
        
        # 启动 API 服务（在独立线程中）
        self.api_thread = threading.Thread(
            target=self.start_api_server,
            name="API-Server",
            daemon=True
        )
        self.api_thread.start()
        logger.info("✓ API 服务线程已启动")
        
        # 等待 API 服务启动
        time.sleep(2)
        
        logger.info("=" * 60)
        logger.info("API 服务已启动，现在启动邮件监听服务...")
        logger.info("=" * 60)
        logger.info("按 Ctrl+C 停止服务")
        logger.info("=" * 60)
        
        # 在主线程中启动邮件监听服务
        try:
            self.start_mail_listener()
        except KeyboardInterrupt:
            logger.info("收到中断信号")
        except Exception as e:
            logger.error(f"邮件监听服务异常: {e}")
        finally:
            self.stop()
    
    def stop(self):
        """停止所有服务"""
        if not self.running:
            return
        
        logger.info("=" * 60)
        logger.info("正在停止所有服务...")
        logger.info("=" * 60)
        
        self.running = False
        
        # 停止邮件监听服务
        if self.mail_listener:
            try:
                logger.info("停止邮件监听服务...")
                self.mail_listener.stop()
                logger.info("✓ 邮件监听服务已停止")
            except Exception as e:
                logger.error(f"停止邮件监听服务时出错: {e}")
        
        # API 服务会随着主程序退出而停止
        logger.info("✓ API 服务已停止")
        
        logger.info("=" * 60)
        logger.info("所有服务已停止")
        logger.info("=" * 60)
        
        sys.exit(0)
    
    def status(self):
        """显示服务状态"""
        logger.info("=" * 60)
        logger.info("服务状态")
        logger.info("=" * 60)
        
        # API 服务状态
        if self.api_thread and self.api_thread.is_alive():
            logger.info("✓ API 服务: 运行中")
        else:
            logger.info("✗ API 服务: 已停止")
        
        # 邮件监听服务状态（在主线程中运行）
        if self.mail_listener and self.running:
            logger.info("✓ 邮件监听服务: 运行中")
        else:
            logger.info("✗ 邮件监听服务: 已停止")
        
        logger.info("=" * 60)


def main():
    """主函数"""
    try:
        service = MainService()
        service.start()
    except Exception as e:
        logger.error(f"服务启动失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
