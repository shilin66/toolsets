"""The API must start before any user has a personal portal session."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api_server
import main
from database import EmailDatabase


class MainStartupTest(unittest.TestCase):
    def test_api_starts_without_a_logged_in_user_or_portal_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = EmailDatabase(str(root / 'test.db'))
            with (
                patch.object(api_server, 'email_db', db),
                patch.object(api_server, 'DATA_DIR', root),
                patch.object(api_server, '_portal_session_service', None),
                patch.object(main, 'logger') as log,
                patch.object(main.app, 'run') as serve,
            ):
                # Exercise the real startup path without installing process-wide
                # signal handlers or starting mail listeners in MainService.__init__.
                service = main.MainService.__new__(main.MainService)
                try:
                    service.start_api_server()
                    serve.assert_called_once_with(
                        host='0.0.0.0', port=main.settings.api_port,
                        debug=False, use_reloader=False, threaded=True,
                    )
                    log.error.assert_not_called()
                    self.assertEqual(main.app.test_client().get('/health').status_code, 200)
                    self.assertIsNone(api_server._portal_session_service)
                    self.assertFalse((root / 'rpa').exists())
                finally:
                    api_server._close_portal_session_service()
