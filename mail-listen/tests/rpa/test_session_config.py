import unittest
from pathlib import Path

from rpa.session_config import PortalSessionSettings
from rpa.session_models import PortalEnvironment, PortalSessionError


class PortalSessionSettingsTest(unittest.TestCase):
    def test_session_keepalive_is_enabled_with_ten_minute_interval(self):
        # Given / When
        settings = PortalSessionSettings(_env_file=None)

        # Then
        self.assertTrue(settings.session_keepalive_enabled)
        self.assertEqual(settings.session_keepalive_interval_seconds, 600)

    def test_test_environment_uses_configured_urls_and_isolated_state(self):
        # Given
        settings = PortalSessionSettings(
            _env_file=None,
            test_login_url=(
                "https://ofm.crm.189.cn:23122/portal/"
                "?ignoreDisableDevtool=true#/pLogin"
            ),
            test_mobile_login_url=(
                "https://ofm.crm.189.cn:23122/portal/"
                "?ignoreDisableDevtool=true#/login"
            ),
            test_session_check_url=(
                "https://ofm.crm.189.cn:23122/portal/"
                "?ignoreDisableDevtool=true#/"
            ),
        )

        # When
        target = settings.resolve_environment(PortalEnvironment.TEST)

        # Then
        self.assertEqual(
            str(target.login_url),
            (
                "https://ofm.crm.189.cn:23122/portal/"
                "?ignoreDisableDevtool=true#/pLogin"
            ),
        )
        self.assertEqual(
            str(target.mobile_login_url),
            (
                "https://ofm.crm.189.cn:23122/portal/"
                "?ignoreDisableDevtool=true#/login"
            ),
        )
        self.assertEqual(
            str(target.session_check_url),
            (
                "https://ofm.crm.189.cn:23122/portal/"
                "?ignoreDisableDevtool=true#/"
            ),
        )
        self.assertEqual(target.state_path, Path("data/rpa/auth-state-test.json"))

    def test_unconfigured_production_environment_is_rejected(self):
        # Given
        settings = PortalSessionSettings.model_construct()

        # When / Then
        with self.assertRaisesRegex(PortalSessionError, "生产环境地址未配置"):
            settings.resolve_environment(PortalEnvironment.PRODUCTION)

    def test_unconfigured_test_environment_is_rejected(self):
        # Given
        settings = PortalSessionSettings.model_construct(
            test_login_url=None,
            test_mobile_login_url=None,
            test_session_check_url=None,
        )

        # When / Then
        with self.assertRaisesRegex(PortalSessionError, "测试环境地址未配置"):
            settings.resolve_environment(PortalEnvironment.TEST)

    def test_production_environment_has_its_own_urls_and_state(self):
        # Given
        settings = PortalSessionSettings(
            _env_file=None,
            production_login_url="https://prod.example.com/portal/#/pLogin",
            production_mobile_login_url="https://prod.example.com/portal/#/login",
            production_session_check_url="https://prod.example.com/portal/#/",
            production_state_path=Path("data/rpa/auth-state-production.json"),
        )

        # When
        target = settings.resolve_environment(PortalEnvironment.PRODUCTION)

        # Then
        self.assertEqual(str(target.login_url), "https://prod.example.com/portal/#/pLogin")
        self.assertEqual(target.state_path, Path("data/rpa/auth-state-production.json"))


if __name__ == "__main__":
    unittest.main()
