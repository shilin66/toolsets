from __future__ import annotations

import unittest

from scripts.detect_sent_folder import (
    identify_declared_sent_folder,
    identify_localized_sent_folder,
)


class DetectSentFolderScriptTests(unittest.TestCase):
    def test_identifies_folder_marked_with_sent_flag(self) -> None:
        # Given
        folders = [
            ((b"\\HasNoChildren",), "/", "INBOX"),
            ((b"\\Sent", b"\\HasNoChildren"), "/", "SentMail"),
        ]

        # When
        sent_folder = identify_declared_sent_folder(folders)

        # Then
        self.assertEqual(sent_folder, "SentMail")

    def test_identifies_chinese_sent_folder_without_sent_flag(self) -> None:
        # Given
        folders = [
            ((b"\\HasNoChildren",), "/", "INBOX"),
            ((b"\\HasNoChildren",), "/", "已发送"),
        ]

        # When
        sent_folder = identify_localized_sent_folder(folders)

        # Then
        self.assertEqual(sent_folder, "已发送")


if __name__ == "__main__":
    _ = unittest.main()
