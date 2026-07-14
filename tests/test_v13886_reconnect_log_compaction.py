import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_RUNNER = ROOT / "app" / "bot_runner.py"


def read_bot_runner() -> str:
    return BOT_RUNNER.read_text(encoding="utf-8-sig")


class ReconnectLogCompactionV13886Tests(unittest.TestCase):
    def test_delay_reconnect_reason_is_short_and_does_not_include_rule(self):
        source = read_bot_runner()
        method = re.search(
            r"def _record_telegram_delay\(.*?(?=\n\s+async def _reconnect_listener_client)",
            source,
            flags=re.S,
        )
        self.assertIsNotNone(method)
        body = method.group(0)

        self.assertNotIn("rule_short", body)
        self.assertNotIn("，规则 ", body)
        self.assertIn("准备轻量重连", body)

    def test_delay_handler_does_not_emit_a_separate_info_line(self):
        source = read_bot_runner()
        self.assertNotIn(
            'log_line("info", f"Telegram 推送延迟 {telegram_delay_sec:.1f}s，来源 {source_name}")',
            source,
        )

    def test_reconnect_result_is_logged_once_through_web_event(self):
        source = read_bot_runner()
        method = re.search(
            r"async def _reconnect_listener_client\(.*?(?=\n\s+async def _priority_worker)",
            source,
            flags=re.S,
        )
        self.assertIsNotNone(method)
        body = method.group(0)

        self.assertNotIn('log_line("warning", f"重连：{reason}")', body)
        self.assertNotIn('push_event("warning", f"推送延迟偏高，轻量重连中：{reason}")', body)
        self.assertNotIn('log_line("info", "重连完成")', body)
        self.assertNotIn('log_line("error", f"自动重连监听失败：{e}")', body)
        self.assertEqual(body.count('push_event("success", "轻量重连完成，复用已有缓存")'), 1)
        self.assertEqual(body.count('push_event("error", f"自动重连监听失败：{e}")'), 1)

    def test_idle_reconnect_notice_is_concise_chinese(self):
        source = read_bot_runner()
        self.assertNotIn('self._reconnect_reason = "30min no message"', source)
        self.assertIn('self._reconnect_reason = "连续 30 分钟未收到消息"', source)
        self.assertIn('push_event("warning", f"{self._reconnect_reason}，准备轻量重连")', source)

    def test_idle_reconnect_uses_latest_message_or_reconnect_as_baseline(self):
        source = read_bot_runner()
        self.assertIn(
            "now - max(self._last_message_time, self._last_delay_reconnect_ts) > 1800",
            source,
        )


if __name__ == "__main__":
    unittest.main()
