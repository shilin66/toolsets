"""Locks shared by web workers, keepalive and report runners on one host."""
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path

from .session_models import PortalSessionError


@contextmanager
def session_lock(path: Path | None, *, blocking=False):
    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError as error:
            raise PortalSessionError('RPA_BUSY', '当前账号正在登录、检查或上报，请稍后重试') from error
        yield
    finally:
        os.close(descriptor)
