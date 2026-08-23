from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import format_datetime, make_msgid
from typing import Final, Protocol

SEEN_FLAG: Final = br"\Seen"
SENT_FOLDER: Final = "已发送"

type FolderEntry = tuple[tuple[bytes, ...], bytes | str | None, str]


@dataclass(frozen=True, slots=True)
class PreparedMessage:
    sender: str
    recipient: str
    subject: str
    message_id: str
    payload: bytes


class SmtpSession(Protocol):
    def login(self, user: str, password: str) -> tuple[int, bytes]: ...

    def sendmail(
        self,
        from_addr: str,
        to_addrs: str,
        msg: bytes,
    ) -> Mapping[str, tuple[int, bytes]]: ...


class ImapSession(Protocol):
    def append(
        self,
        folder: str,
        msg: bytes,
        flags: list[bytes],
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RecipientRejectedError(Exception):
    recipient: str

    def __str__(self) -> str:
        return f"收件人 {self.recipient} 被 SMTP 服务器拒绝"


@dataclass(frozen=True, slots=True)
class SentFolderNotFoundError(Exception):
    folder: str

    def __str__(self) -> str:
        return f"IMAP 服务器上不存在文件夹 {self.folder!r}"


def build_test_message(
    sender: str,
    recipient: str,
    now: datetime,
) -> PreparedMessage:
    message_id = make_msgid(domain=sender.partition("@")[2])
    subject = f"已发送同步测试 {now:%Y-%m-%d %H:%M:%S}"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message["Date"] = format_datetime(now)
    message["Message-ID"] = message_id
    message.set_content("这是一封用于验证21CN已发送文件夹同步的测试邮件。")
    return PreparedMessage(
        sender=sender,
        recipient=recipient,
        subject=subject,
        message_id=message_id,
        payload=message.as_bytes(policy=SMTP),
    )


def deliver_message(
    client: SmtpSession,
    password: str,
    message: PreparedMessage,
) -> None:
    _ = client.login(message.sender, password)
    refused_recipients = client.sendmail(
        message.sender,
        message.recipient,
        message.payload,
    )
    if refused_recipients:
        raise RecipientRejectedError(recipient=message.recipient)


def append_to_sent(
    client: ImapSession,
    sent_folder: str,
    message: PreparedMessage,
) -> None:
    # _ = client.append(sent_folder, message.payload, flags=[SEEN_FLAG])
    _ = client.append(sent_folder, message.payload, flags=[SEEN_FLAG])


def has_sent_folder(folders: Sequence[FolderEntry]) -> bool:
    return any(folder_name == SENT_FOLDER for _flags, _delimiter, folder_name in folders)
