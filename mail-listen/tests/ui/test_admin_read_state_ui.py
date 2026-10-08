import unittest
from pathlib import Path


class AdminReadStateUiTest(unittest.TestCase):
    def test_cutover_list_and_detail_declare_read_state_controls(self):
        project_dir = Path(__file__).resolve().parents[2]
        source = (project_dir / "static" / "admin-views.js").read_text(encoding="utf-8")
        styles = (project_dir / "static" / "admin.css").read_text(encoding="utf-8")
        translations = (project_dir / "static" / "admin-i18n.js").read_text(encoding="utf-8")

        self.assertIn('read_status: ""', source)
        self.assertIn('/read-state`', source)
        self.assertIn('@click.stop="toggleReadState(row)"', source)
        self.assertIn('class="mail-read-state-control"', source)
        self.assertIn("readStateBusyIds.value = [...readStateBusyIds.value, row.id]", source)
        self.assertIn(':aria-busy="readStateBusyIds.includes(row.id)"', source)
        self.assertNotIn("readStateBusyId !== null && readStateBusyId !== row.id", source)
        self.assertIn('.mail-read-state-control', styles)
        self.assertEqual(translations.count('markAsRead:'), 3)
        self.assertEqual(translations.count('markAsUnread:'), 3)


if __name__ == "__main__":
    unittest.main()
