import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
EXPECTED_VERSION = "1.38.73"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


class PriorityWorkersV13863Tests(unittest.TestCase):
    def test_versions_are_bumped_to_v13863(self):
        self.assertEqual(read(ROOT / "VERSION").strip(), EXPECTED_VERSION)
        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', read(APP / "config.py"))

    def test_listener_uses_dedicated_priority_worker_without_raising_total_cap(self):
        bot_runner = read(APP / "bot_runner.py")
        self.assertIn("PRIORITY_WORKER_COUNT = 1", bot_runner)
        self.assertIn("worker_count = max(2, min(4, worker_count))", bot_runner)
        self.assertIn("normal_worker_count = worker_count - PRIORITY_WORKER_COUNT", bot_runner)
        self.assertIn("self._priority_worker(client, 0)", bot_runner)
        self.assertIn("self._normal_worker(client, i)", bot_runner)
        self.assertNotIn("self.workers += [asyncio.create_task(self._worker(client, i))", bot_runner)

    def test_priority_worker_blocks_on_priority_queue_directly(self):
        bot_runner = read(APP / "bot_runner.py")
        priority = re.search(
            r"async def _priority_worker\(.*?\n    async def _normal_worker",
            bot_runner,
            flags=re.S,
        )
        self.assertIsNotNone(priority)
        priority_body = priority.group(0)
        self.assertIn("item = await self.priority_queue.get()", priority_body)
        self.assertIn('meta["queue_type"] = "priority"', priority_body)
        self.assertIn("self.priority_queue.task_done()", priority_body)

        normal = re.search(
            r"async def _normal_worker\(.*?\n    async def _handle_message",
            bot_runner,
            flags=re.S,
        )
        self.assertIsNotNone(normal)
        normal_body = normal.group(0)
        self.assertIn("item = await self.queue.get()", normal_body)
        self.assertIn('meta["queue_type"] = "normal"', normal_body)
        self.assertNotIn("self.priority_queue.get_nowait()", normal_body)
        self.assertNotIn("not self.priority_queue.empty()", normal_body)


if __name__ == "__main__":
    unittest.main()


