import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


class DialogRefreshGuardV138601Tests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(APP))

    def tearDown(self):
        sys.modules.pop("dialog_guard", None)
        try:
            sys.path.remove(str(APP))
        except ValueError:
            pass

    def test_refresh_guard_rejects_obviously_incomplete_dialog_lists(self):
        from dialog_guard import should_keep_existing_dialog_cache

        self.assertTrue(should_keep_existing_dialog_cache(old_count=524, new_count=364))
        self.assertTrue(should_keep_existing_dialog_cache(old_count=523, new_count=364))
        self.assertFalse(should_keep_existing_dialog_cache(old_count=524, new_count=500))
        self.assertFalse(should_keep_existing_dialog_cache(old_count=0, new_count=364))
        self.assertFalse(should_keep_existing_dialog_cache(old_count=30, new_count=10))

    def test_refresh_route_keeps_old_cache_before_writing_new_cache(self):
        web = read(APP / "web.py")
        self.assertIn("should_keep_existing_dialog_cache", web)
        self.assertIn("疑似不完整", web)
        self.assertLess(
            web.index("should_keep_existing_dialog_cache"),
            web.index('set_json("dialog_cache", dialogs)'),
        )


if __name__ == "__main__":
    unittest.main()


