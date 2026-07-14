import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
REGISTER_STATUS_RULE = (
    r"((?:[🫧🎫🎟️🎭🤖⏳].*?(?:自由|定时)注册.*"
    r"(?:\n[🫧🎫🎟️🎭🤖⏳].*\|\s*\d+.*)*\n?)+)"
    r"|((?:[🎉✨📱⏰].*?开放注册.*(?:\n[🎉✨📱⏰].*)*\n?)+)"
)

REGISTRATION_SUCCESS_NOTICE = """· 🎟️ 自由注册成功 - 卖淀粉肠的老王 [6451842119] 创建了 Wfzxw
· 📅 账号有效期 - 30 天
· 🚨 到期时间 - 2026-08-13 15:06:31
"""

OPEN_REGISTRATION_NOTICE = """🎟️ 自由注册已开启
🎫 总注册限制 | 461
🎟️ 已注册人数 | 451
🎭 剩余可注册 | 10
"""

SUCCESS_RATE_ANNOUNCEMENT = """🎟️ 自由注册成功率提升，现已开启
🚨 开放到期时间 - 2026-08-13 15:06:31
"""


def load_matcher():
    fake_store = types.ModuleType("redis_store")
    fake_store.smembers = lambda key: {REGISTER_STATUS_RULE} if key == "regex_rules" else set()
    fake_code_rules = types.ModuleType("code_rules")
    fake_code_rules.extract_code_detail = lambda _text: {}
    fake_code_rules.extract_trigger_code_detail = lambda _text: {}
    replacements = {
        "redis_store": fake_store,
        "code_rules": fake_code_rules,
    }
    old_modules = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location("matcher_v13882", APP / "matcher.py")
        module = importlib.util.module_from_spec(spec)
        assert spec is not None and spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        for name, old in old_modules.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


class RegistrationSuccessFilterV13882Tests(unittest.TestCase):
    def test_registration_success_notice_is_filtered_before_regex_rules(self):
        matcher = load_matcher()

        result = matcher.analyze_message(REGISTRATION_SUCCESS_NOTICE)

        self.assertFalse(result["matched"])
        self.assertTrue(result["registration_success_notice"])
        self.assertFalse(result["usage_notice"])
        self.assertFalse(result["closed_register_notice"])

    def test_all_matcher_entry_points_filter_registration_success_notice(self):
        matcher = load_matcher()

        matched, rule = matcher.match_rules(REGISTRATION_SUCCESS_NOTICE)
        details = matcher.match_rule_details(REGISTRATION_SUCCESS_NOTICE)

        self.assertFalse(matched)
        self.assertEqual(rule, "")
        self.assertFalse(details["matched"])
        self.assertTrue(details["registration_success_notice"])

    def test_real_open_registration_notice_still_matches(self):
        matcher = load_matcher()

        result = matcher.analyze_message(OPEN_REGISTRATION_NOTICE)

        self.assertTrue(result["matched"])
        self.assertEqual(result["rule"], REGISTER_STATUS_RULE)
        self.assertFalse(result.get("registration_success_notice", False))

    def test_success_rate_announcement_is_not_treated_as_personal_success(self):
        matcher = load_matcher()

        result = matcher.analyze_message(SUCCESS_RATE_ANNOUNCEMENT)

        self.assertTrue(result["matched"])
        self.assertFalse(result.get("registration_success_notice", False))

    def test_regex_debug_api_exposes_registration_success_filter_reason(self):
        web_source = (APP / "web.py").read_text(encoding="utf-8-sig")

        self.assertIn(
            '"registration_success_notice": details.get("registration_success_notice")',
            web_source,
        )


if __name__ == "__main__":
    unittest.main()
