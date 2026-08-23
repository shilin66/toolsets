"""解析并计算登录页中的简单算术验证码。"""

from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Final, assert_never


class RpaError(Exception):
    """RPA 功能的基础异常。"""


@dataclass(frozen=True, slots=True)
class CaptchaParseError(RpaError):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class CaptchaRecognitionError(RpaError):
    reason: str

    def __str__(self) -> str:
        return self.reason


class CaptchaOperator(StrEnum):
    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"


@dataclass(frozen=True, slots=True)
class CaptchaExpression:
    left: int
    operator: CaptchaOperator
    right: int


_EXPRESSION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?P<left>\d{1,4})\s*(?P<operator>[+\-xX×*÷/])\s*"
    r"(?P<right>\d{1,4})\s*=\s*\?"
)
_FULL_WIDTH_TRANSLATION: Final[dict[int, str]] = str.maketrans(
    "０１２３４５６７８９＋－＊／＝？",
    "0123456789+-*/=?",
)
_OPERATORS: Final[dict[str, CaptchaOperator]] = {
    "+": CaptchaOperator.ADD,
    "-": CaptchaOperator.SUBTRACT,
    "x": CaptchaOperator.MULTIPLY,
    "X": CaptchaOperator.MULTIPLY,
    "×": CaptchaOperator.MULTIPLY,
    "*": CaptchaOperator.MULTIPLY,
    "÷": CaptchaOperator.DIVIDE,
    "/": CaptchaOperator.DIVIDE,
}


def solve_captcha(page_text: str) -> str:
    """从页面文本中提取算术表达式，并返回验证码答案。"""
    normalized_text = page_text.translate(_FULL_WIDTH_TRANSLATION)
    expression_match = _EXPRESSION_PATTERN.search(normalized_text)
    if expression_match is None:
        raise CaptchaParseError(reason="页面中没有可识别的算术验证码")

    expression = CaptchaExpression(
        left=int(expression_match.group("left")),
        operator=_OPERATORS[expression_match.group("operator")],
        right=int(expression_match.group("right")),
    )

    match expression.operator:
        case CaptchaOperator.ADD:
            result = expression.left + expression.right
        case CaptchaOperator.SUBTRACT:
            result = expression.left - expression.right
        case CaptchaOperator.MULTIPLY:
            result = expression.left * expression.right
        case CaptchaOperator.DIVIDE:
            if expression.right == 0 or expression.left % expression.right != 0:
                raise CaptchaParseError(reason="除法验证码的结果不是有效整数")
            result = expression.left // expression.right
        case unreachable:
            assert_never(unreachable)

    return str(result)
