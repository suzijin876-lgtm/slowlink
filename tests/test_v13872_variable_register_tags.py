import importlib.util
import re
import sys
import time
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
EXPECTED_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8-sig").strip()
LEGACY_PURE_CODE_RULE = r"^(?!.*码使用)[^-]+-\d+-(?:Register|Renew)_.+$"
SAFE_PURE_CODE_RULE = (
    r"^(?!.*码使用)(?:[^\s-]+-)+\d+(?:-[^\s-]+)*-"
    r"(?:Register|Renew)_(?:[A-Za-z0-9_-]|数字|字母)+$"
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_code_rules_with_fake_redis():
    fake_redis_store = types.ModuleType("redis_store")
    fake_redis_store.get_json = lambda key, default=None: default
    fake_redis_store.set_json = lambda *args, **kwargs: None

    old = sys.modules.get("redis_store")
    sys.modules["redis_store"] = fake_redis_store
    sys.path.insert(0, str(APP))
    try:
        sys.modules.pop("code_rules", None)
        import code_rules
        return code_rules
    finally:
        try:
            sys.path.remove(str(APP))
        except ValueError:
            pass
        if old is None:
            sys.modules.pop("redis_store", None)
        else:
            sys.modules["redis_store"] = old


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.operations = []

    def srem(self, key, value):
        self.operations.append(("srem", key, value))
        return self

    def sadd(self, key, value):
        self.operations.append(("sadd", key, value))
        return self

    def execute(self):
        results = []
        for operation, key, value in self.operations:
            results.append(getattr(self.client, operation)(key, value))
        return results


class FakeRedisClient:
    def __init__(self, regex_rules):
        self.values = {}
        self.sets = {"regex_rules": set(regex_rules)}

    def setnx(self, key, value):
        if key in self.values:
            return False
        self.values[key] = str(value)
        return True

    def sismember(self, key, value):
        return value in self.sets.get(key, set())

    def srem(self, key, value):
        values = self.sets.setdefault(key, set())
        existed = value in values
        values.discard(value)
        return int(existed)

    def sadd(self, key, value):
        values = self.sets.setdefault(key, set())
        before = len(values)
        values.add(value)
        return int(len(values) != before)

    def pipeline(self):
        return FakePipeline(self)


def load_redis_store_with_fake_client(client):
    fake_redis = types.ModuleType("redis")
    fake_redis.Redis = lambda *args, **kwargs: client
    fake_config = types.ModuleType("config")
    fake_config.REDIS_HOST = "redis"
    fake_config.REDIS_PORT = 6379
    fake_config.LISTENER_WORKERS = 2

    replacements = {"redis": fake_redis, "config": fake_config}
    old_modules = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location("redis_store_v13872", APP / "redis_store.py")
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


class VariableRegisterTagsV13872Tests(unittest.TestCase):
    def test_versions_are_bumped_to_v13872(self):
        self.assertEqual(read(ROOT / "VERSION").strip(), EXPECTED_VERSION)
        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', read(APP / "config.py"))

    def test_existing_register_format_remains_supported(self):
        code_rules = load_code_rules_with_fake_redis()
        expected = "飞了个喵-30-Register_8snhzn9Agg"

        detail = code_rules.extract_code_detail("已为您生成了\n" + expected)

        self.assertEqual(detail.get("code"), expected)
        self.assertEqual(detail.get("identity"), "strong_register_renew:" + expected)

    def test_register_format_supports_middle_tag(self):
        code_rules = load_code_rules_with_fake_redis()
        expected = "WENJIAN-30-AUDIO-Register_sHLLQcf4vd"

        detail = code_rules.extract_code_detail("已为您生成了\n" + expected)

        self.assertEqual(detail.get("code"), expected)
        self.assertEqual(detail.get("identity"), "strong_register_renew:" + expected)

    def test_register_format_supports_multiple_middle_tags_and_renew(self):
        code_rules = load_code_rules_with_fake_redis()
        expected = "WENJIAN-30-AUDIO-HQ-Renew_sHLLQcf4vd"

        detail = code_rules.extract_code_detail("已为您生成了\n" + expected)

        self.assertEqual(detail.get("code"), expected)
        self.assertEqual(detail.get("identity"), "strong_register_renew:" + expected)

    def test_incomplete_register_prefix_is_not_used_as_generic_invite_code(self):
        code_rules = load_code_rules_with_fake_redis()
        text = "已为您生成了\nWENJIAN-30-AUDIO-Register_"

        detail = code_rules.extract_code_detail(text)

        self.assertEqual(detail, {})

    def test_startup_migrates_only_known_pure_code_trigger_rule(self):
        timed_rule = r"🫧.*?(?:自由|定时)注册"
        client = FakeRedisClient({LEGACY_PURE_CODE_RULE, timed_rule})
        redis_store = load_redis_store_with_fake_client(client)

        redis_store.ensure_defaults()

        rules = client.sets["regex_rules"]
        self.assertNotIn(LEGACY_PURE_CODE_RULE, rules)
        self.assertIn(SAFE_PURE_CODE_RULE, rules)
        self.assertIn(timed_rule, rules)
        self.assertEqual(len(rules), 2)

    def test_migrated_pure_code_rule_matches_tags_and_stays_fast(self):
        client = FakeRedisClient(set())
        redis_store = load_redis_store_with_fake_client(client)
        pattern = getattr(redis_store, "SAFE_PURE_CODE_TRIGGER_RULE", "")

        self.assertEqual(pattern, SAFE_PURE_CODE_RULE)
        compiled = re.compile(pattern, re.I | re.M)
        self.assertIsNotNone(compiled.search("飞了个喵-30-Register_8snhzn9Agg"))
        self.assertIsNotNone(compiled.search("WENJIAN-30-AUDIO-Register_sHLLQcf4vd"))
        self.assertIsNotNone(compiled.search("WENJIAN-30-AUDIO-HQ-Renew_sHLLQcf4vd"))
        self.assertIsNone(compiled.search("注册码使用 WENJIAN-30-AUDIO-Register_sHLLQcf4vd"))

        adversarial = ("ABCD-" * 1700)[:8192]
        started = time.perf_counter()
        self.assertIsNone(compiled.search(adversarial))
        self.assertLess((time.perf_counter() - started) * 1000, 100)


if __name__ == "__main__":
    unittest.main()
