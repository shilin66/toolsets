"""RPA 登录命令行入口。"""

import sys

from pydantic import ValidationError

from rpa.config import RpaSettings
from rpa.login import LoginFailedError, PortalLoginRpa


def main() -> int:
    """加载环境变量并执行一次登录。"""
    try:
        settings = RpaSettings()
    except ValidationError as error:
        print(
            f"RPA 配置无效（{error.error_count()} 项），"
            "请检查 RPA_ 和 OPENAI_COMPATIBLE_ 环境变量。",
            file=sys.stderr,
        )
        return 2

    try:
        result = PortalLoginRpa(settings).login()
    except LoginFailedError as error:
        print(f"登录失败：{error}", file=sys.stderr)
        return 1

    print(f"登录成功，会话已保存到：{result.storage_state_path}")
    print(f"登录后页面截图已保存到：{result.success_screenshot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
