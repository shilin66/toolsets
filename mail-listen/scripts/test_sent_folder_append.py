#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "imapclient==3.0.1",
#     "pydantic[email]>=2.12,<3",
#     "python-dotenv==1.2.1",
#     "rich>=13,<15",
#     "typer>=0.17,<1",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. Run from the project root with the current environment:
#      python scripts/test_sent_folder_append.py --to receiver@example.com
# 3. Or run in an isolated uv environment:
#      uv run scripts/test_sent_folder_append.py --to receiver@example.com
# 4. Override 21CN enterprise servers when needed:
#      uv run scripts/test_sent_folder_append.py --to receiver@example.com --smtp-server smtp-ent.21cn.com --imap-server imap-ent.21cn.com
# ─────────────────

from __future__ import annotations

import os
import smtplib
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError
from rich.console import Console

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))
if not __package__:
    __package__ = "scripts"

from .sent_folder_append_core import (
    FolderEntry,
    PreparedMessage,
    RecipientRejectedError,
    SENT_FOLDER,
    SentFolderNotFoundError,
    append_to_sent,
    build_test_message,
    deliver_message,
    has_sent_folder,
)

CONSOLE = Console()


class ConnectionSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    username: EmailStr
    recipient: EmailStr
    smtp_server: str = Field(min_length=1)
    smtp_port: int = Field(ge=1, le=65535)
    smtp_use_ssl: bool
    smtp_use_tls: bool
    imap_server: str = Field(min_length=1)
    imap_port: int = Field(ge=1, le=65535)
    imap_use_ssl: bool


@dataclass(frozen=True, slots=True)
class ImapClientAdapter:
    client: IMAPClient

    def append(self, folder: str, msg: bytes, flags: list[bytes]) -> None:
        _ = self.client.append(folder, msg, flags=flags)


def load_settings(
    recipient: str | None,
    smtp_server: str | None,
    imap_server: str | None,
) -> ConnectionSettings:
    username = os.environ.get("EMAIL_ADDRESS") or input("邮箱账号: ").strip()
    resolved_recipient = recipient or os.environ.get("TEST_RECIPIENT") or username
    return ConnectionSettings.model_validate(
        {
            "username": username,
            "recipient": resolved_recipient,
            "smtp_server": smtp_server
            or os.environ.get("SMTP_SERVER")
            or "smtp-ent.21cn.com",
            "smtp_port": os.environ.get("SMTP_PORT", "465"),
            "smtp_use_ssl": os.environ.get("SMTP_USE_SSL", "true"),
            "smtp_use_tls": os.environ.get("SMTP_USE_TLS", "false"),
            "imap_server": imap_server
            or os.environ.get("IMAP_SERVER")
            or "imap-ent.21cn.com",
            "imap_port": os.environ.get("IMAP_PORT", "993"),
            "imap_use_ssl": os.environ.get("IMAP_USE_SSL", "true"),
        }
    )


def send_via_smtp(
    settings: ConnectionSettings,
    password: str,
    message: PreparedMessage,
) -> None:
    tls_context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(
            settings.smtp_server,
            settings.smtp_port,
            timeout=20,
            context=tls_context,
        ) as client:
            deliver_message(client, password, message)
        return

    with smtplib.SMTP(settings.smtp_server, settings.smtp_port, timeout=20) as client:
        if settings.smtp_use_tls:
            _ = client.starttls(context=tls_context)
        deliver_message(client, password, message)


def run_live_test(
    settings: ConnectionSettings,
    password: str,
    message: PreparedMessage,
) -> None:
    with IMAPClient(
        settings.imap_server,
        port=settings.imap_port,
        ssl=settings.imap_use_ssl,
        timeout=20,
    ) as archive_client:
        _ = archive_client.login(str(settings.username), password)
        folders: list[FolderEntry] = archive_client.list_folders()
        if not has_sent_folder(folders):
            raise SentFolderNotFoundError(folder=SENT_FOLDER)

        send_via_smtp(settings, password, message)
        CONSOLE.print("[green]1. SMTP 发送成功[/green]")
        append_to_sent(ImapClientAdapter(archive_client), SENT_FOLDER, message)
        CONSOLE.print(f"[green]2. 已追加到 {SENT_FOLDER!r}[/green]")


def main(
    recipient: Annotated[
        str | None,
        typer.Option("--to", help="收件人；默认发给自己"),
    ] = None,
    smtp_server: Annotated[
        str | None,
        typer.Option("--smtp-server", help="SMTP 服务器"),
    ] = None,
    imap_server: Annotated[
        str | None,
        typer.Option("--imap-server", help="IMAP 服务器"),
    ] = None,
) -> None:
    try:
        settings = load_settings(recipient, smtp_server, imap_server)
    except ValidationError as error:
        CONSOLE.print(f"[bold red]参数错误：{error}[/bold red]")
        raise typer.Exit(code=2) from error

    CONSOLE.print(
        f"将从 {settings.username} 向 {settings.recipient} 真实发送一封测试邮件，"
        f"并追加到 {SENT_FOLDER!r}。"
    )
    if not typer.confirm("继续？"):
        raise typer.Exit()

    password = getpass("邮箱授权码/密码: ")
    message = build_test_message(
        str(settings.username),
        str(settings.recipient),
        datetime.now().astimezone(),
    )
    try:
        run_live_test(settings, password, message)
    except (
        IMAPClientError,
        OSError,
        RecipientRejectedError,
        SentFolderNotFoundError,
        smtplib.SMTPException,
    ) as error:
        CONSOLE.print(f"[bold red]测试失败：{error}[/bold red]")
        raise typer.Exit(code=1) from error

    CONSOLE.print(f"主题：{message.subject}")
    CONSOLE.print(f"Message-ID：{message.message_id}")
    CONSOLE.print("[bold green]追加完成，请刷新 Foxmail 的“已发送”目录确认。[/bold green]")


if __name__ == "__main__":
    _ = load_dotenv()
    typer.run(main)
