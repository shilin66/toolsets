"""使用本地 RapidOCR 识别图片验证码。"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

import cv2
import numpy as np
from PIL import (
    Image,
    ImageEnhance,
    ImageOps,
    UnidentifiedImageError,
)

from rpa.captcha import (
    CaptchaParseError,
    CaptchaRecognitionError,
    solve_captcha,
)


class OcrOutput(Protocol):
    txts: Sequence[str] | None


class OcrEngine(Protocol):
    def __call__(
        self,
        image: bytes,
        *,
        use_det: bool,
        use_cls: bool,
    ) -> OcrOutput:
        """识别一张已裁剪的文字图片。"""


@dataclass(frozen=True, slots=True)
class OcrRecognitionError(CaptchaRecognitionError):
    """本地 OCR 无法返回有效验证码文本。"""


class RapidOcrCaptchaRecognizer:
    """延迟初始化 OCR，并返回首个通过算式校验的识别结果。"""

    def __init__(self, engine: OcrEngine | None = None) -> None:
        self._engine = engine

    def recognize(self, image_png: bytes) -> str:
        """离线识别验证码图片，不产生任何网络请求。"""
        if not image_png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise OcrRecognitionError(reason="验证码截图不是有效的 PNG 图片")

        engine = self._engine
        if engine is None:
            engine = self._load_engine()
            self._engine = engine

        candidates: list[str] = []
        for candidate_image in self._candidate_images(image_png):
            try:
                result = engine(
                    candidate_image,
                    use_det=False,
                    use_cls=False,
                )
            except (OSError, RuntimeError) as error:
                raise OcrRecognitionError(
                    reason="本地 OCR 引擎执行失败"
                ) from error

            raw_expression = (
                "".join(result.txts).strip() if result.txts else ""
            )
            if not raw_expression:
                candidates.append("<空>")
                continue

            candidates.append(
                self._summarize_candidate(raw_expression)
            )
            expression = self._normalize_candidate(raw_expression)
            try:
                solve_captcha(expression)
            except CaptchaParseError:
                continue
            return expression

        candidate_summary = "、".join(dict.fromkeys(candidates))
        raise OcrRecognitionError(
            reason=(
                "本地 OCR 未识别出有效算术验证码"
                f"（候选：{candidate_summary}）"
            )
        )

    @staticmethod
    def _candidate_images(image_png: bytes) -> Iterator[bytes]:
        """生成少量固定预处理版本，降低彩色描边造成的误识别。"""
        yield image_png

        try:
            with Image.open(BytesIO(image_png)) as source:
                source.load()
                rgb_image = source.convert("RGB")
        except (OSError, UnidentifiedImageError) as error:
            raise OcrRecognitionError(
                reason="无法读取验证码 PNG 图片"
            ) from error

        enlarged = rgb_image.resize(
            (rgb_image.width * 4, rgb_image.height * 4),
            Image.Resampling.LANCZOS,
        )
        grayscale = ImageOps.autocontrast(
            enlarged.convert("L")
        ).convert("RGB")
        high_contrast = ImageEnhance.Contrast(enlarged).enhance(2.5)
        yield RapidOcrCaptchaRecognizer._encode_png(grayscale)

        rgb_array = np.asarray(rgb_image)
        darkest_channel = np.min(rgb_array, axis=2).astype(np.uint8)
        gray_image = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2GRAY)
        for source_image, threshold in (
            (darkest_channel, 200),
            (gray_image, 180),
            (darkest_channel, 220),
            (darkest_channel, 250),
        ):
            _, binary_image = cv2.threshold(
                source_image,
                threshold,
                255,
                cv2.THRESH_BINARY,
            )
            binary_image = cv2.resize(
                binary_image,
                None,
                fx=4,
                fy=4,
                interpolation=cv2.INTER_CUBIC,
            )
            encoded, image_buffer = cv2.imencode(".png", binary_image)
            if not encoded:
                continue
            yield image_buffer.tobytes()

        yield RapidOcrCaptchaRecognizer._encode_png(high_contrast)

    @staticmethod
    def _encode_png(image: Image.Image) -> bytes:
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def _summarize_candidate(candidate: str) -> str:
        single_line = " ".join(candidate.split())
        return repr(single_line[:40])

    @staticmethod
    def _normalize_candidate(candidate: str) -> str:
        """移除彩色描边常被 OCR 误判出的孤立小数点。"""
        return candidate.replace(".", "")

    @staticmethod
    def _load_engine() -> OcrEngine:
        try:
            from rapidocr import RapidOCR
        except ImportError as error:
            raise OcrRecognitionError(
                reason=(
                    "未安装本地 OCR 依赖，请执行 "
                    "pip install -r requirements.txt"
                )
            ) from error

        try:
            return RapidOCR()
        except (OSError, RuntimeError) as error:
            raise OcrRecognitionError(
                reason="无法初始化本地 OCR 模型"
            ) from error
