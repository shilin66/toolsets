from io import BytesIO
import unittest

from PIL import Image

from rpa.ocr import (
    OcrRecognitionError,
    RapidOcrCaptchaRecognizer,
)


class FakeOcrResult:
    def __init__(self, texts: list[str] | None) -> None:
        self.txts = texts


class FakeOcrEngine:
    def __init__(self, texts: list[str] | None) -> None:
        self._texts = texts
        self.received_image: bytes | None = None
        self.used_detection: bool | None = None
        self.used_classification: bool | None = None

    def __call__(
        self,
        image: bytes,
        *,
        use_det: bool,
        use_cls: bool,
    ) -> FakeOcrResult:
        self.received_image = image
        self.used_detection = use_det
        self.used_classification = use_cls
        return FakeOcrResult(self._texts)


class ScriptedOcrEngine:
    def __init__(self, results: list[list[str] | None]) -> None:
        self._results = iter(results)
        self.received_images: list[bytes] = []

    def __call__(
        self,
        image: bytes,
        *,
        use_det: bool,
        use_cls: bool,
    ) -> FakeOcrResult:
        self.received_images.append(image)
        return FakeOcrResult(next(self._results))


def make_png() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (120, 40), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class RapidOcrCaptchaRecognizerTest(unittest.TestCase):
    def test_recognizes_a_cropped_captcha_as_one_text_line(self):
        # Given
        engine = FakeOcrEngine(["5 + 3", " = ?"])
        recognizer = RapidOcrCaptchaRecognizer(engine=engine)
        captcha_png = make_png()

        # When
        expression = recognizer.recognize(captcha_png)

        # Then
        self.assertEqual(expression, "5 + 3 = ?")
        self.assertEqual(engine.received_image, captcha_png)
        self.assertFalse(engine.used_detection)
        self.assertFalse(engine.used_classification)

    def test_rejects_an_empty_ocr_result(self):
        # Given
        recognizer = RapidOcrCaptchaRecognizer(
            engine=FakeOcrEngine(None)
        )

        # When / Then
        with self.assertRaises(OcrRecognitionError):
            recognizer.recognize(make_png())

    def test_tries_preprocessed_image_when_original_candidate_is_invalid(self):
        # Given
        engine = ScriptedOcrEngine(
            [
                ["q × 2 = ?"],
                ["9 × 2 = ?"],
            ]
        )
        recognizer = RapidOcrCaptchaRecognizer(engine=engine)
        captcha_png = make_png()

        # When
        expression = recognizer.recognize(captcha_png)

        # Then
        self.assertEqual(expression, "9 × 2 = ?")
        self.assertEqual(len(engine.received_images), 2)
        self.assertEqual(engine.received_images[0], captcha_png)
        self.assertNotEqual(engine.received_images[1], captcha_png)

    def test_removes_period_artifacts_before_validating_expression(self):
        # Given
        recognizer = RapidOcrCaptchaRecognizer(
            engine=FakeOcrEngine(["1.+ 7 =.?"])
        )

        # When
        expression = recognizer.recognize(make_png())

        # Then
        self.assertEqual(expression, "1+ 7 =?")


if __name__ == "__main__":
    unittest.main()
