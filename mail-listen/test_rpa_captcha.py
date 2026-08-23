import unittest

from rpa.captcha import CaptchaParseError, solve_captcha


class CaptchaSolverTest(unittest.TestCase):
    def test_solves_multiplication_when_page_contains_chinese_login_text(self):
        # Given
        page_text = "欢迎登录\n请输入用户名\n请输入验证码\n6 × 5 = ?\n登录"

        # When
        answer = solve_captcha(page_text)

        # Then
        self.assertEqual(answer, "30")

    def test_solves_full_width_addition_when_captcha_uses_localized_characters(self):
        # Given
        page_text = "１２ ＋ ７ ＝ ？"

        # When
        answer = solve_captcha(page_text)

        # Then
        self.assertEqual(answer, "19")

    def test_rejects_page_text_when_no_supported_expression_exists(self):
        # Given
        page_text = "请输入验证码"

        # When / Then
        with self.assertRaises(CaptchaParseError):
            solve_captcha(page_text)

    def test_rejects_division_when_result_is_not_an_integer(self):
        # Given
        page_text = "7 ÷ 2 = ?"

        # When / Then
        with self.assertRaises(CaptchaParseError):
            solve_captcha(page_text)


if __name__ == "__main__":
    unittest.main()
