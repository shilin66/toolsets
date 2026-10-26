import unittest

from unconfigured_mail import DEFAULT_SETTINGS, normalize_sender, validate_settings, accepts_sender


class UnconfiguredPolicyTest(unittest.TestCase):
    def test_defaults_disable_both_features(self):
        self.assertFalse(DEFAULT_SETTINGS['supplier_auto_discovery_enabled'])
        self.assertFalse(DEFAULT_SETTINGS['unconfigured_cutover_analysis_enabled'])

    def test_normalized_address_and_exact_domain(self):
        settings = validate_settings({**DEFAULT_SETTINGS,
            'unconfigured_sender_filter_mode': 'allowlist',
            'unconfigured_sender_filter_list': ['*@Example.com', 'NOC@other.com']})
        self.assertEqual(normalize_sender('NOC < Person@Example.com >'), 'person@example.com')
        self.assertTrue(accepts_sender(settings, 'NOC <Person@example.com>'))
        self.assertTrue(accepts_sender(settings, 'noc@other.com'))
        self.assertFalse(accepts_sender(settings, 'person@sub.example.com'))
        self.assertFalse(accepts_sender(settings, 'example.com@evil.com'))

    def test_modes_and_invalid_settings(self):
        for update in ({'supplier_auto_discovery_enabled': 'false'},
                       {'unconfigured_sender_filter_mode': 'allowlist'},
                       {'unconfigured_sender_filter_list': ['n*@example.com']},
                       {'unconfigured_sender_filter_mode': 'invalid'}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                validate_settings({**DEFAULT_SETTINGS, **update})
        settings = validate_settings({**DEFAULT_SETTINGS,
            'unconfigured_sender_filter_mode': 'blocklist',
            'unconfigured_sender_filter_list': ['*@example.com']})
        self.assertFalse(accepts_sender(settings, 'person@example.com'))
        self.assertTrue(accepts_sender(settings, 'person@other.com'))

