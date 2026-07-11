import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
EXPECTED_VERSION = "1.38.74"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


class StableSpeedV13857Tests(unittest.TestCase):
    def test_versions_are_bumped_to_v13857(self):
        self.assertEqual(read(ROOT / "VERSION").strip(), EXPECTED_VERSION)
        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', read(APP / "config.py"))

    def test_single_core_defaults_are_conservative(self):
        config = read(APP / "config.py")
        redis_store = read(APP / "redis_store.py")
        bot_runner = read(APP / "bot_runner.py")
        main = read(APP / "main.py")

        self.assertIn("WEB_THREADS", config)
        self.assertIn("LISTENER_WORKERS", config)
        self.assertIn('"worker_count": str(LISTENER_WORKERS)', redis_store)
        self.assertIn('get("worker_count", str(LISTENER_WORKERS))', bot_runner)
        self.assertIn("threads=WEB_THREADS", main)

    def test_light_state_payload_avoids_heavy_collections(self):
        web = read(APP / "web.py")
        light_branch = re.search(
            r"def _state_payload\(light: bool = False\).*?if light:\s*return (?P<body>\{.*?\})\s*dialogs =",
            web,
            flags=re.S,
        )
        self.assertIsNotNone(light_branch, "_state_payload should return a dedicated lightweight payload before heavy work")
        body = light_branch.group("body")
        for heavy in [
            "cache_stats",
            "code_rule_diagnostics",
            "list_events",
            "list_hits",
            "list_fails",
            "list_dedup_recent",
            "smembers",
            "_prepare_dialog_cache",
        ]:
            self.assertNotIn(heavy, body)

    def test_frontend_preserves_stats_when_light_payload_omits_them(self):
        index = read(APP / "templates" / "index.html")
        stats_guard = re.search(
            r"if\(data\.stats\)\s*\{(?P<body>.*?)\n\s*\}",
            index,
            flags=re.S,
        )
        self.assertIsNotNone(stats_guard, "updateStatus should only refresh counters when stats are present")
        body = stats_guard.group("body")
        self.assertIn("statTotal", body)
        self.assertIn("summaryListening", body)

    def test_mobile_monitor_list_has_card_layout_override(self):
        css = read(APP / "static" / "style.css")
        index = read(APP / "templates" / "index.html")

        self.assertIn("V1.38.58 mobile monitor list polish", css)
        self.assertRegex(css, r"#dialogList\s+\.dialog-row\s*\{[^}]*grid-template-columns:\s*34px minmax\(0,\s*1fr\)")
        self.assertRegex(css, r"#dialogList\s+\.dialog-main\s*\{[^}]*min-width:\s*0")
        self.assertIn("#dialogList .dialog-sub", css)
        self.assertIn('style="${show?\'\':\'display:none\'}"', index)
        self.assertNotIn("style=\"display:${show?'flex':'none'}\"", index)

    def test_cleanup_scan_continues_after_empty_batches(self):
        redis_store = read(APP / "redis_store.py")
        cleanup = re.search(
            r"def cleanup_expired_dedup_keys\(\) -> int:(?P<body>.*?)(?=\n\n\S|\Z)",
            redis_store,
            flags=re.S,
        )
        self.assertIsNotNone(cleanup)
        body = cleanup.group("body")
        self.assertIn("if not keys:\n                if cursor == 0:\n                    break\n                continue", body)
        self.assertNotIn("if not keys:\n                break", body)


if __name__ == "__main__":
    unittest.main()


