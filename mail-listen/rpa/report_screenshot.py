"""Store full-resolution report evidence with lossless compression."""
from io import BytesIO
from pathlib import Path

from loguru import logger
from PIL import Image

from mail_artifacts import write_private_bytes


def save_report_screenshot(png: bytes, target: Path) -> Path:
    content = png
    if target.suffix.lower() == '.webp':
        try:
            with Image.open(BytesIO(png)) as image:
                output = BytesIO()
                image.save(output, format='WEBP', lossless=True, method=4, exact=True,
                           icc_profile=image.info.get('icc_profile', b''))
                compressed = output.getvalue()
            if len(compressed) < len(png):
                content = compressed
            else:
                target = target.with_suffix('.png')
        except (OSError, ValueError, KeyError) as error:
            # Compression is optional; keep the full evidence if the encoder fails
            # (including full-page screenshots beyond WebP's dimension limit).
            logger.warning('上报截图压缩失败，保留 PNG: {}', type(error).__name__)
            target = target.with_suffix('.png')
    return write_private_bytes(target.parent, target, content)
