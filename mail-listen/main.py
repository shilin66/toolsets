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
from mail_listener import listener_manager
from config import settings, log_format


class MainService:
    """主服务管理类"""
    
    def __init__(self):
        self.api_thread = None
        self.running = False
        
        # 配置日志（统一格式：带邮箱标识，见 config.log_format）
        logger.remove()
        logger.add(
            sys.stdout,
            level=settings.log_level,
            format=log_format,
        )
        
        logger.add(
            "logs/main.log",
            rotation="1 day",
            retention="30 days",
            level=settings.log_level,
            format=log_format,
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
            logger.info("  GET    /health          - 健康检查")
            logger.info("  POST   /api/tickets     - 新增工单记录")
            logger.info("  GET    /api/template-xlsx - 生成模板 Excel")
            logger.info("  POST   /api/template-xlsx - 生成并填充模板 Excel")
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
        """启动邮件监听服务（多邮箱，监听在独立线程中运行）"""
        try:
            logger.info("=" * 60)
            logger.info("启动邮件监听服务")
            logger.info("=" * 60)

            listener_manager.start_all()

        except Exception as e:
            logger.error(f"邮件监听服务启动失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
    
    def start(self):
        """启动所有服务"""
        logger.info("=" * 60)
        logger.info("邮件监听系统启动")
        logger.info("=" * 60)
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
        
        # 启动邮件监听服务（监听线程独立运行，主线程保持存活）
        try:
            self.start_mail_listener()
            while self.running:
                time.sleep(1)
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
        try:
            logger.info("停止邮件监听服务...")
            listener_manager.stop_all()
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
        
        # 邮件监听服务状态（监听线程独立运行）
        if self.running:
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
