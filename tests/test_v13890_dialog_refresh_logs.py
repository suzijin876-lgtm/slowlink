import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


class _Pipeline:
    def __init__(self):
        self.calls = []

    def lpush(self, *args):
        self.calls.append(("lpush", args))
        return self

    def ltrim(self, *args):
        self.calls.append(("ltrim", args))
        return self

    def execute(self):
        self.calls.append(("execute", ()))
        return []


class _Redis:
    def __init__(self):
        self.pipe = _Pipeline()

    def get(self, _key):
        return None

    def pipeline(self):
        return self.pipe


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8-sig")


class DialogRefreshLoggingV13890Tests(unittest.TestCase):
    def test_add_fail_can_store_without_emitting_a_second_log_line(self):
        fake_redis = _Redis()
        fake_redis_module = types.ModuleType("redis")
        fake_redis_module.Redis = lambda *args, **kwargs: fake_redis
        previous_redis_module = sys.modules.get("redis")
        sys.modules["redis"] = fake_redis_module
        sys.path.insert(0, str(APP))
        try:
            sys.modules.pop("redis_store", None)
            import redis_store

            redis_store.r = fake_redis
            redis_store.log_line = Mock()
            redis_store.add_fail(
                {"stage": "refresh_dialogs", "error": "partial result"},
                emit_log=False,
            )

            redis_store.log_line.assert_not_called()
            stored = next(args for name, args in fake_redis.pipe.calls if name == "lpush")
            self.assertEqual(stored[0], "fails")
            self.assertEqual(json.loads(stored[1])["error"], "partial result")
        finally:
            sys.modules.pop("redis_store", None)
            if previous_redis_module is None:
                sys.modules.pop("redis", None)
            else:
                sys.modules["redis"] = previous_redis_module
            try:
                sys.path.remove(str(APP))
            except ValueError:
                pass

    def test_refresh_logs_only_after_the_result_passes_the_cache_guard(self):
        runner = read("app/bot_runner.py")
        collector = re.search(
            r"async def _list_dialogs_with_client\(.*?(?=\n\s+async def list_dialogs)",
            runner,
            flags=re.S,
        )
        self.assertIsNotNone(collector)
        self.assertNotIn('push_event("success"', collector.group(0))

        web = read("app/web.py")
        route = re.search(
            r"def refresh_dialogs\(\):(?P<body>.*?)(?=\n@app\.)",
            web,
            flags=re.S,
        )
        self.assertIsNotNone(route)
        body = route.group("body")
        incomplete = re.search(
            r"if should_keep_existing_dialog_cache\(.*?(?=\n\s+set_json\(\"dialog_cache\")",
            body,
            flags=re.S,
        )
        self.assertIsNotNone(incomplete)
        self.assertIn("emit_log=False", incomplete.group(0))
        self.assertEqual(incomplete.group(0).count('push_event("warning", message)'), 1)
        self.assertLess(
            body.index('set_json("dialog_cache", dialogs)'),
            body.index('push_event("success", msg)'),
        )


if __name__ == "__main__":
    unittest.main()
