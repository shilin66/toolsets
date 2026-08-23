"""
邮箱账号配置模块

邮箱凭据从 .env 迁移到数据库页面化管理：
- Fernet 对称加密存储密码，密钥取 MAIL_SECRET_KEY 环境变量或自动生成持久化
- 启动时若账号表为空且 .env 有邮箱配置，自动迁移为第一条账号
"""
import hashlib
import os
from dataclasses import dataclass
from typing import List, Optional

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from config import settings
from database import email_db

SECRET_KEY_PATH = os.path.join("data", "mail_secret.key")

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """获取（懒加载）Fernet 实例。密钥优先取环境变量，其次本地密钥文件。"""
    global _fernet
    if _fernet is not None:
        return _fernet

    env_key = os.environ.get("MAIL_SECRET_KEY", "").strip()
    if env_key:
        try:
            _fernet = Fernet(env_key.encode("utf-8"))
            return _fernet
        except Exception as e:
            raise RuntimeError(f"MAIL_SECRET_KEY 不是合法的 Fernet 密钥: {e}")

    if os.path.exists(SECRET_KEY_PATH):
        try:
            with open(SECRET_KEY_PATH, "rb") as f:
                file_key = f.read().strip()
            _fernet = Fernet(file_key)
            return _fernet
        except Exception as e:
            raise RuntimeError(f"邮箱密钥文件 {SECRET_KEY_PATH} 无效: {e}")

    # 首次使用：生成密钥并持久化（权限 0600）
    key = Fernet.generate_key()
    os.makedirs(os.path.dirname(SECRET_KEY_PATH) or ".", exist_ok=True)
    old_umask = os.umask(0o077)
    try:
        with open(SECRET_KEY_PATH, "wb") as f:
            f.write(key)
    finally:
        os.umask(old_umask)
    logger.info(f"已生成邮箱配置密钥文件: {SECRET_KEY_PATH}")
    _fernet = Fernet(key)
    return _fernet


def encrypt_password(plain_password: str) -> str:
    """加密邮箱密码/授权码，返回 base64 文本。"""
    if not plain_password:
        return ""
    return _get_fernet().encrypt(plain_password.encode("utf-8")).decode("utf-8")


def decrypt_password(encrypted_password: str) -> str:
    """解密邮箱密码/授权码；密文无效时返回空串并记录错误。"""
    if not encrypted_password:
        return ""
    try:
        return _get_fernet().decrypt(encrypted_password.encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as e:
        logger.error(f"邮箱密码解密失败（密钥可能不匹配）: {e}")
        return ""


@dataclass
class MailAccountConfig:
    """单个邮箱账号的连接配置（密码已解密）。"""

    id: int
    name: str
    email_address: str
    email_password: str
    imap_server: str
    imap_port: int = 993
    imap_use_ssl: bool = True
    smtp_server: str = ""
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    smtp_use_tls: bool = False
    enabled: bool = True

    def config_hash(self) -> str:
        """连接相关配置的指纹，用于判断监听是否需要重启。"""
        raw = "|".join([
            self.email_address, self.email_password,
            self.imap_server, str(self.imap_port), str(self.imap_use_ssl),
            self.smtp_server, str(self.smtp_port),
            str(self.smtp_use_ssl), str(self.smtp_use_tls),
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def account_row_to_config(row: dict) -> Optional[MailAccountConfig]:
    """数据库行转账号配置；密码解密失败时返回 None。"""
    password = decrypt_password(row.get("password_enc") or "")
    if not password:
        logger.error(f"邮箱账号 {row.get('email_address')} 密码缺失或解密失败，跳过")
        return None
    return MailAccountConfig(
        id=row["id"],
        name=row.get("name") or "",
        email_address=row["email_address"],
        email_password=password,
        imap_server=row["imap_server"],
        imap_port=int(row.get("imap_port") or 993),
        imap_use_ssl=bool(row.get("imap_use_ssl", 1)),
        smtp_server=row.get("smtp_server") or "",
        smtp_port=int(row.get("smtp_port") or 465),
        smtp_use_ssl=bool(row.get("smtp_use_ssl", 1)),
        smtp_use_tls=bool(row.get("smtp_use_tls", 0)),
        enabled=bool(row.get("enabled", 1)),
    )


def list_enabled_account_configs() -> List[MailAccountConfig]:
    """读取全部启用的邮箱账号配置（密码已解密）。"""
    configs: List[MailAccountConfig] = []
    for row in email_db.list_mail_accounts():
        if not row.get("enabled", 1):
            continue
        config = account_row_to_config(row)
        if config:
            configs.append(config)
    return configs


def seed_from_env_if_empty() -> None:
    """账号表为空且 .env 配置了邮箱时，迁移为第一条账号（兼容存量部署）。"""
    try:
        if email_db.list_mail_accounts():
            return
    except Exception as e:
        logger.error(f"检查邮箱账号表失败: {e}")
        return

    if not (settings.email_address and settings.imap_server and settings.email_password):
        logger.info("邮箱账号表为空且 .env 未配置完整邮箱信息，跳过迁移")
        return

    account_id = email_db.add_mail_account({
        "name": "默认邮箱(迁移)",
        "email_address": settings.email_address,
        "password_enc": encrypt_password(settings.email_password),
        "imap_server": settings.imap_server,
        "imap_port": settings.imap_port,
        "imap_use_ssl": int(bool(settings.imap_use_ssl)),
        "smtp_server": settings.smtp_server or "",
        "smtp_port": settings.smtp_port,
        "smtp_use_ssl": int(bool(settings.smtp_use_ssl)),
        "smtp_use_tls": int(bool(settings.smtp_use_tls)),
        "enabled": 1,
    })
    if account_id:
        logger.info(f"已从 .env 迁移邮箱配置到数据库: {settings.email_address}")
