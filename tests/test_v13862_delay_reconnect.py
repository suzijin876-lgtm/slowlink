import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
EXPECTED_VERSION = (ROOT / "VERSION").read_text(encoding="utf-8-sig").strip()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


class DelayReconnectV13862Tests(unittest.TestCase):
    def test_versions_are_bumped_to_v13862(self):
        self.assertEqual(read(ROOT / "VERSION").strip(), EXPECTED_VERSION)
        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', read(APP / "config.py"))

    def test_delay_reconnect_thresholds_are_responsive_but_bounded(self):
        bot_runner = read(APP / "bot_runner.py")
        self.assertIn("TELEGRAM_DELAY_HIGH_SECONDS = 30", bot_runner)
        self.assertIn("TELEGRAM_DELAY_IMMEDIATE_RECONNECT_SECONDS = 60", bot_runner)
        self.assertIn("TELEGRAM_DELAY_RECONNECT_COUNT = 2", bot_runner)
        self.assertIn("TELEGRAM_DELAY_RECONNECT_COOLDOWN_SECONDS = 180", bot_runner)
        self.assertNotIn("delay_sec >= 300", bot_runner)
        self.assertNotIn("_telegram_delay_high_count >= 3", bot_runner)
        self.assertNotIn(">= 300:", bot_runner)

    def test_record_delay_uses_new_threshold_constants(self):
        bot_runner = read(APP / "bot_runner.py")
        method = re.search(
            r"def _record_telegram_delay\(.*?\n    async def _reconnect_listener_client",
            bot_runner,
            flags=re.S,
        )
        self.assertIsNotNone(method)
        body = method.group(0)
        self.assertIn("delay_sec >= TELEGRAM_DELAY_IMMEDIATE_RECONNECT_SECONDS", body)
        self.assertIn("self._telegram_delay_high_count >= TELEGRAM_DELAY_RECONNECT_COUNT", body)
        self.assertIn("now - self._last_delay_reconnect_ts >= TELEGRAM_DELAY_RECONNECT_COOLDOWN_SECONDS", body)
        self.assertIn("单次 Telegram 推送延迟", body)
        self.assertIn("连续", body)


if __name__ == "__main__":
    unittest.main()


