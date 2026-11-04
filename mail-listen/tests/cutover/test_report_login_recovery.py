import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import cutover_report
from rpa.cutover_report import PortalCutoverReportRpa
from rpa.session_models import PortalEnvironment, PortalSessionError


class ReportLoginRecoveryTest(unittest.TestCase):
    def test_partial_backbone_submission_must_not_be_replayed_after_login(self):
        for completed in (0, 1):
            with self.subTest(completed=completed), tempfile.TemporaryDirectory() as directory:
                rpa = Mock()
                rpa.fill_backbone_form.side_effect = [SimpleNamespace(operation_log=())] * completed + [
                    PortalSessionError('RPA_SESSION_REQUIRED', 'expired')]
                with patch.object(cutover_report, 'PortalCutoverReportRpa', return_value=rpa), \
                        patch.object(cutover_report, '_report_artifact_directory', return_value=Path(directory)), \
                        patch.object(cutover_report, '_resolve_backbone_forms', return_value=[{}, {}]), \
                        patch.object(cutover_report, '_resolve_source_email_attachment', return_value=Path(directory)/'mail.eml'):
                    with self.assertRaises(PortalSessionError) as caught:
                        cutover_report.report_cutover_task({'id':1,'line_type':'backbone'},
                            environment=PortalEnvironment.TEST, data_dir=Path(directory),
                            session_settings=SimpleNamespace())
                self.assertEqual(caught.exception.code,
                    'RPA_SESSION_REQUIRED_AFTER_SUBMIT' if completed else 'RPA_SESSION_REQUIRED')

    def test_login_redirect_after_submit_is_classified_as_unknown_result(self):
        rpa = PortalCutoverReportRpa(SimpleNamespace(timeout_ms=5000, username_selector='#user',
                                                   mobile_phone_selector='#phone', report_backbone_submit_selector='#submit'))
        for action in ('backbone', 'customer'):
            with self.subTest(action=action), \
                    patch.object(rpa, '_pace_before_action'), \
                    patch.object(rpa, '_find_visible', return_value=Mock()), \
                    patch.object(rpa, '_first_visible', return_value=Mock()):
                with self.assertRaises(PortalSessionError) as caught:
                    if action == 'backbone':
                        rpa._submit_backbone_form(Mock())
                    else:
                        rpa._complete_import_dialogs(Mock(), Mock(), Path('/tmp/unused.webp'), [])
                self.assertEqual(caught.exception.code, 'RPA_SESSION_REQUIRED_AFTER_SUBMIT')
