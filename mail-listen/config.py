"""
配置管理模块
"""
from pydantic import field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


def log_format(record) -> str:
    """统一日志格式：带账号上下文的日志自动附加 [邮箱地址] 标识。

    作为 loguru 的 format 回调使用（logger.add(format=log_format)），
    控制台/文件两类 sink 通用；非 TTY 环境下颜色标记由 loguru 自动剥离。
    """
    account = record["extra"].get("account")
    tag = f" [{account}]" if account else ""
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level>"
        + tag
        + " | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>\n{exception}"
    )


class Settings(BaseSettings):
    """应用配置"""
    
    # 邮箱配置（可选：仅用于首次启动时自动迁移到数据库，之后以管理台页面配置为准）
    imap_server: str = ""
    imap_port: int = 993
    imap_use_ssl: bool = True
    email_address: str = ""
    email_password: str = ""
    smtp_server: str = ""
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    smtp_use_tls: bool = False
    
    # API配置
    api_url: str = ""
    api_token: str = ""
    api_key: str = ""  # API Key for authentication
    api_port: int = 5000
    fe_domain: str = ""  # 前端域名，配置后用于生成图片访问地址
    api_public_base_url: str = ""  # 生成本地资源 URL 时使用的外部可访问地址
    api_timeout: int = 30  # API 请求超时时间（秒）
    
    # 监听配置
    check_interval: int = 30
    mark_as_read: bool = True
    email_hours_filter: int = 0  # 监听指定小时内的邮件，0表示监听所有邮件
    imap_idle_support: bool = True  # 邮箱服务器是否支持IDLE模式
    idle_timeout: int = 1800  # IDLE模式超时时间（秒）
    idle_reconnect_delay: int = 5  # IDLE连接断开后重连延迟（秒）
    idle_check_interval: int = 30  # IDLE检查间隔（秒），控制多久重启一次IDLE连接
    max_emails_per_batch: int = 50  # 每批处理的最大邮件数量
    search_timeout: int = 30  # 搜索操作超时时间（秒）
    
    # 并发配置
    concurrent_processing: bool = True  # 是否启用并发处理
    max_concurrent_emails: int = 5  # 最大并发处理邮件数量
    
    # 日志配置
    log_level: str = "INFO"

    # solarwinds配置
    sw_username: str = ""
    sw_password: str = ""
    
    @field_validator('api_url', 'api_token')
    @classmethod
    def validate_required_fields(cls, v, info):
        if not v:
            raise ValueError(f'{info.field_name} 不能为空')
        return v
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# 全局配置实例
settings = Settings()
