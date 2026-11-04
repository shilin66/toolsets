"""Report compression preserves evidence and falls back to the original PNG."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from rpa.report_screenshot import save_report_screenshot
from rpa.cutover_report import PortalCutoverReportRpa
from rpa.session_config import PortalSessionSettings


class ReportScreenshotStorageTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.source = Image.new('RGB', (1920, 1081), 'white')
        draw = ImageDraw.Draw(self.source)
        for row in range(40):
            draw.text((32, row * 24), f'Circuit 00001234 / step {row}', fill='#234567')
        buffer = BytesIO()
        self.source.save(buffer, format='PNG')
        self.png = buffer.getvalue()

    def test_webp_is_smaller_with_identical_dimensions_and_pixels(self):
        target = self.root / 'reports/step.webp'
        actual = save_report_screenshot(self.png, target)
        self.assertEqual(actual, target)
        self.assertLess(actual.stat().st_size, len(self.png))
        self.assertEqual(actual.stat().st_mode & 0o777, 0o600)
        with Image.open(actual) as image:
            self.assertEqual(image.format, 'WEBP')
            self.assertEqual(image.size, self.source.size)
            self.assertEqual(image.convert('RGB').tobytes(), self.source.tobytes())
        self.assertEqual(list(target.parent.iterdir()), [actual])

    def test_png_callers_keep_original_bytes(self):
        target = self.root / 'legacy.png'
        actual = save_report_screenshot(self.png, target)
        self.assertEqual(actual, target)
        self.assertEqual(actual.read_bytes(), self.png)

    def test_encoding_error_preserves_original_png_and_returns_actual_path(self):
        for error in (OSError('encoder unavailable'), KeyError('WEBP')):
            with self.subTest(error=type(error).__name__), patch.object(Image.Image, 'save', side_effect=error):
                actual = save_report_screenshot(self.png, self.root / 'failure.webp')
            self.assertEqual(actual, self.root / 'failure.png')
            self.assertEqual(actual.read_bytes(), self.png)
            self.assertFalse((self.root / 'failure.webp').exists())

    def test_operation_log_and_failure_reference_actual_fallback_file(self):
        page = Mock()
        page.screenshot.return_value = self.png
        updates = []
        rpa = PortalCutoverReportRpa(PortalSessionSettings(_env_file=None), operation_step_callback=updates.append)
        log = []
        with patch.object(rpa, '_wait_for_page_settled'), patch.object(Image.Image, 'save', side_effect=OSError()):
            entry = rpa._capture_operation_step(page, self.root / 'result.webp', log, 'ready', 'Ready')
            failure = rpa._capture_failure_screenshot(page, self.root)
        self.assertEqual(updates, [entry])
        self.assertEqual(log, [entry])
        for actual in (entry.screenshot_path, failure):
            self.assertEqual(actual.suffix, '.png')
            self.assertEqual(actual.read_bytes(), self.png)

    def test_larger_encoding_keeps_original_png(self):
        def oversized_encode(image, output, **kwargs):
            output.write(b'x' * (len(self.png) + 1))

        with patch.object(Image.Image, 'save', oversized_encode):
            actual = save_report_screenshot(self.png, self.root / 'step.webp')
        self.assertEqual(actual.suffix, '.png')
        self.assertEqual(actual.read_bytes(), self.png)

    def test_tall_full_page_beyond_webp_limit_is_preserved_as_png(self):
        source = Image.new('RGB', (1280, 16384), 'white')
        output = BytesIO()
        source.save(output, format='PNG')
        actual = save_report_screenshot(output.getvalue(), self.root / 'tall.webp')
        self.assertEqual(actual.suffix, '.png')
        with Image.open(actual) as image:
            self.assertEqual(image.size, source.size)

