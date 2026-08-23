#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "imapclient==3.0.1",
#     "python-dotenv==1.2.1",
#     "rich>=13,<15",
#     "typer>=0.17,<1",
# ]
# ///

# ─── How to run ───
# 1. Install uv (if not installed):
#      curl -LsSf https://astral.sh/uv/install.sh | sh
# 2. With the current project environment:
#      python scripts/detect_sent_folder.py
# 3. Or let uv create an isolated environment and read IMAP_SERVER/EMAIL_ADDRESS from .env:
#      uv run scripts/detect_sent_folder.py
# 4. Specify the 21CN server and account (password is always prompted securely):
#      uv run scripts/detect_sent_folder.py --server imap.21cn.com --username you@21cn.com
# 5. Or make executable and run:
#      chmod +x scripts/detect_sent_folder.py && ./scripts/detect_sent_folder.py
# ─────────────────

from __future__ import annotations

import os
from collections.abc import Sequence
from getpass import getpass
from typing import Annotated, Final, assert_never

import typer
from dotenv import load_dotenv
from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
from rich.console import Console
from rich.table import Table

type FolderEntry = tuple[tuple[bytes, ...], bytes | str | None, str]

SENT_FLAG: Final = br"\Sent"
LOCALIZED_SENT_FOLDER_NAMES: Final = frozenset({"已发送", "已发送邮件"})
CONSOLE: Final = Console()


def identify_declared_sent_folder(folders: Sequence[FolderEntry]) -> str | None:
    return next(
        (folder_name for flags, _delimiter, folder_name in folders if SENT_FLAG in flags),
        None,
    )


def identify_localized_sent_folder(folders: Sequence[FolderEntry]) -> str | None:
    return next(
        (
            folder_name
            for _flags, _delimiter, folder_name in folders
            if folder_name.strip() in LOCALIZED_SENT_FOLDER_NAMES
        ),
        None,
    )


def format_bytes(value: bytes | str | None) -> str:
    match value:
        case None:
            return "-"
        case bytes():
            return value.decode("ascii", errors="replace")
        case str():
            return value
        case unreachable:
            assert_never(unreachable)


def show_result(
    folders: Sequence[FolderEntry],
    declared_sent_folder: str | None,
    inferred_sent_folder: str | None,
) -> None:
    table = Table(title="IMAP 服务器文件夹")
    table.add_column("文件夹名称")
    table.add_column("分隔符")
    table.add_column("服务器标记")
    table.add_column("判定")

    for flags, delimiter, folder_name in folders:
        flag_text = " ".join(format_bytes(flag) for flag in flags) or "-"
        if folder_name == declared_sent_folder:
            verdict = "[bold green]服务器声明的 \\Sent[/bold green]"
        elif folder_name == inferred_sent_folder:
            verdict = "[yellow]名称推断候选[/yellow]"
        else:
            verdict = ""
        table.add_row(folder_name, format_bytes(delimiter), flag_text, verdict)

    CONSOLE.print(table)
    if declared_sent_folder is not None:
        CONSOLE.print(
            f"\n[bold green]已确认 sent_folder = {declared_sent_folder!r}[/bold green]"
        )
    elif inferred_sent_folder is not None:
        CONSOLE.print(
            "\n[yellow]服务器没有返回 \\Sent 标记，"
            + f"imapclient 根据名称推断 sent_folder = {inferred_sent_folder!r}[/yellow]"
        )
    else:
        CONSOLE.print(
            "\n[bold red]未找到已发送文件夹。"
            + "请对照 21CN 网页邮箱确认上表中的目录名。[/bold red]"
        )


def main(
    server: Annotated[
        str | None,
        typer.Option("--server", help="IMAP 服务器，默认读取 IMAP_SERVER"),
    ] = None,
    username: Annotated[
        str | None,
        typer.Option("--username", help="邮箱账号，默认读取 EMAIL_ADDRESS"),
    ] = None,
) -> None:
    resolved_server = server or os.environ.get("IMAP_SERVER")
    resolved_username = username or os.environ.get("EMAIL_ADDRESS")
    if not resolved_server:
        resolved_server = input("IMAP 服务器 [imap.21cn.com]: ").strip() or "imap.21cn.com"
    if not resolved_username:
        resolved_username = input("邮箱账号: ").strip()

    password = getpass("邮箱授权码/密码: ")
    port = int(os.environ.get("IMAP_PORT", "993"))
    use_ssl = os.environ.get("IMAP_USE_SSL", "true").strip().casefold() not in {
        "0",
        "false",
        "no",
        "off",
    }

    try:
        with IMAPClient(
            resolved_server,
            port=port,
            ssl=use_ssl,
            timeout=20,
        ) as client:
            _ = client.login(resolved_username, password)
            folders: list[FolderEntry] = client.list_folders()
            declared_sent_folder = identify_declared_sent_folder(folders)
            inferred_sent_folder: str | None = client.find_special_folder(
                SENT_FLAG
            ) or identify_localized_sent_folder(folders)
    except (IMAPClientError, OSError) as error:
        CONSOLE.print(f"[bold red]连接或登录失败：{error}[/bold red]")
        raise typer.Exit(code=1) from error

    show_result(folders, declared_sent_folder, inferred_sent_folder)


if __name__ == "__main__":
    _ = load_dotenv()
    typer.run(main)
