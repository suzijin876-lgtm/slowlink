import importlib
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
EXPECTED_VERSION = "1.38.76"


RULES = [
    {
        "name": "Register/Renew 完整码",
        "pattern": r"[^\s]+(?:-[^\s]+)*-\d+-(?:Register|Renew)_[A-Za-z0-9_-]+",
        "group": "0",
        "enabled": True,
        "fast": True,
        "trigger": False,
        "strict_context": False,
        "note": "",
    },
    {
        "name": "中文字段邀请码/注册码",
        "pattern": r"(?:邀请码|注册码|注册代码)[:：\s]+([A-Za-z0-9_-]+(?:-[A-Za-z0-9_-]+)*)",
        "group": "1",
        "enabled": True,
        "fast": True,
        "trigger": False,
        "strict_context": True,
        "note": "",
    },
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_code_rules():
    fake_redis = types.ModuleType("redis_store")
    fake_redis.get_json = lambda key, default=None: RULES
    fake_redis.set_json = lambda key, value: None
    sys.modules["redis_store"] = fake_redis
    sys.modules.pop("code_rules", None)
    sys.path.insert(0, str(APP))
    return importlib.import_module("code_rules")


class CodeExtractionV13862Tests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("code_rules", None)
        sys.modules.pop("redis_store", None)
        try:
            sys.path.remove(str(APP))
        except ValueError:
            pass

    def test_versions_are_bumped_to_v13862(self):
        self.assertEqual(read(ROOT / "VERSION").strip(), EXPECTED_VERSION)
        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', read(APP / "config.py"))

    def test_generated_register_code_with_markdown_stars_is_not_deduped_as_count_1(self):
        code_rules = load_code_rules()
        text = "🎯 miraiemby_bot已为您生成了 1天 注册码 1 个\n\nMirai-1-Register_**NPNB410s"

        detail = code_rules.extract_code_detail(text)

        self.assertEqual(detail.get("code"), "Mirai-1-Register_NPNB410s")
        self.assertEqual(detail.get("identity"), "strong_register_renew:Mirai-1-Register_NPNB410s")
        self.assertNotEqual(detail.get("identity"), "field_code:1")


if __name__ == "__main__":
    unittest.main()


