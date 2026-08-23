from __future__ import annotations

# pyright: reportImplicitRelativeImport=false

import smtplib
from email.message import EmailMessage
from email.policy import SMTP
from typing import Final

import imapclient
from imapclient.exceptions import IMAPClientError
from loguru import logger

from mail_accounts import MailAccountConfig

SENT_FOLDER: Final = "已发送"
SEEN_FLAG: Final = br"\Seen"
TWENTY_ONE_CN_DOMAIN: Final = "21cn.com"
CONNECTION_TIMEOUT_SECONDS: Final = 20


def send_outbound_email(account: MailAccountConfig, message: EmailMessage) -> None:
    smtp_server = account.smtp_server or account.imap_server
    payload = message.as_bytes(policy=SMTP)
    if account.smtp_use_ssl:
        smtp_client = smtplib.SMTP_SSL(
            smtp_server,
            account.smtp_port,
            timeout=CONNECTION_TIMEOUT_SECONDS,
        )
    else:
        smtp_client = smtplib.SMTP(
            smtp_server,
            account.smtp_port,
            timeout=CONNECTION_TIMEOUT_SECONDS,
        )

    with smtp_client as client:
        if account.smtp_use_tls and not account.smtp_use_ssl:
            _ = client.starttls()
        _ = client.login(account.email_address, account.email_password)
        _ = client.send_message(message)

    provider_hosts = {
        host.strip().casefold().rstrip(".")
        for host in (
            account.imap_server,
            account.smtp_server,
            account.email_address.rpartition("@")[2],
        )
        if host.strip()
    }
    if not any(
        host == TWENTY_ONE_CN_DOMAIN
        or host.endswith(f".{TWENTY_ONE_CN_DOMAIN}")
        for host in provider_hosts
    ):
        return

    try:
        with imapclient.IMAPClient(
            account.imap_server,
        port=account.imap_port,
        ssl=account.imap_use_ssl,
        timeout=CONNECTION_TIMEOUT_SECONDS,
        ) as imap_client:
            _ = imap_client.login(account.email_address, account.email_password)
            _ = imap_client.append(SENT_FOLDER, payload, flags=[SEEN_FLAG])
    except (IMAPClientError, OSError) as error:
        logger.warning(f"21CN 已发送归档失败: {error}")
