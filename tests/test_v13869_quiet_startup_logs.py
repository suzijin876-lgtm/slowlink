import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
EXPECTED_VERSION = "1.38.73"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


class QuietStartupLogsV13869Tests(unittest.TestCase):
    def test_versions_are_bumped_to_v13869(self):
        self.assertEqual(read(ROOT / "VERSION").strip(), EXPECTED_VERSION)
        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', read(APP / "config.py"))

    def test_default_log_verbose_is_disabled(self):
        config = read(APP / "config.py")
        self.assertIn('LOG_VERBOSE = os.getenv("LOG_VERBOSE", "0") == "1"', config)

    def test_startup_path_uses_single_summary_in_default_mode(self):
        bot_runner = read(APP / "bot_runner.py")
        self.assertIn("def _verbose_log(", bot_runner)
        self.assertIn("def _verbose_event(", bot_runner)

        noisy_fragments = [
            'log_line("info", "监听线程已创建，等待 Telegram 连接")',
            'push_event("info", "监听启动中")',
            'log_line("info", "监听线程进入事件循环")',
            'log_line("info", "正在连接 Telegram")',
            'log_line("info", "启动时刷新会话缓存，用于目标快速解析")',
            'push_event("info", f"已刷新会话缓存：{len(dialogs)} 个，快速解析缓存：{len(self.entity_cache)} 个键")',
            'log_line("info", f"开始预缓存转发目标：{targets}")',
            'push_event("success", "转发目标已预缓存：" + ", ".join(ok[:5]))',
            'log_line("info", f"消息处理线程已启动：优先 {PRIORITY_WORKER_COUNT}，普通 {normal_worker_count}")',
            'push_event("success", "监听已启动，正在接收新消息")',
        ]
        for fragment in noisy_fragments:
            self.assertNotIn(fragment, bot_runner)

        summary = re.search(r"startup_summary = f\"(?P<text>.*?)\"", bot_runner)
        self.assertIsNotNone(summary)
        text = summary.group("text")
        for required in ["监听已启动：会话", "缓存", "目标", "线程 优先", "普通", "耗时"]:
            self.assertIn(required, text)

    def test_auto_restore_does_not_emit_extra_success_event(self):
        web = read(APP / "web.py")
        self.assertIn('log_line("info", f"SlowLink {APP_VERSION} 启动")', web)
        self.assertNotIn('push_event("info", f"容器启动后自动恢复监听：{msg}")', web)


if __name__ == "__main__":
    unittest.main()
