import hashlib
import importlib
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
EXPECTED_VERSION = "1.38.73"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def load_dedup():
    fake_redis = types.ModuleType("redis_store")
    fake_redis.r = object()
    fake_redis.sha = lambda value: hashlib.sha256(str(value).encode("utf-8")).hexdigest()
    fake_redis.format_time = lambda: "2026-07-08 00:00:00"
    sys.modules["redis_store"] = fake_redis
    sys.modules.pop("dedup", None)
    sys.path.insert(0, str(APP))
    return importlib.import_module("dedup")


class RegisterBatchDedupV13865Tests(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("dedup", None)
        sys.modules.pop("redis_store", None)
        try:
            sys.path.remove(str(APP))
        except ValueError:
            pass

    def test_versions_are_bumped_to_v13865(self):
        self.assertEqual(read(ROOT / "VERSION").strip(), EXPECTED_VERSION)
        self.assertIn(f'APP_VERSION = "{EXPECTED_VERSION}"', read(APP / "config.py"))

    def test_register_batches_with_same_header_but_different_codes_do_not_share_text_hash(self):
        dedup = load_dedup()
        header = "imycdbot generated 30 day register codes 10"
        first = header + "\n\n" + "\n".join([
            "t.me/imycdbot?start=SAKURA-30-Register_n1B0UfXbFs",
            "t.me/imycdbot?start=SAKURA-30-Register_nUYxaQJbJc",
            "t.me/imycdbot?start=SAKURA-30-Register_K2iAt4CYiW",
            "t.me/imycdbot?start=SAKURA-30-Register_vSfrvmAgqe",
            "t.me/imycdbot?start=SAKURA-30-Register_VnuCxEYTJc",
            "t.me/imycdbot?start=SAKURA-30-Register_jMrnCYjWyP",
            "t.me/imycdbot?start=SAKURA-30-Register_IZGwJHkaGu",
            "t.me/imycdbot?start=SAKURA-30-Register_qqWYHn2e88",
            "t.me/imycdbot?start=SAKURA-30-Register_Xn2XVoqfyW",
            "t.me/imycdbot?start=SAKURA-30-Register_vfxUDYwuZh",
        ])
        second = header + "\n\n" + "\n".join([
            "t.me/imycdbot?start=SAKURA-30-Register_BFHN3fWm6y",
            "t.me/imycdbot?start=SAKURA-30-Register_9wmbKzZYg1",
            "t.me/imycdbot?start=SAKURA-30-Register_BPNBRTMq5F",
            "t.me/imycdbot?start=SAKURA-30-Register_rt2Hmrym2m",
            "t.me/imycdbot?start=SAKURA-30-Register_py9D3HZsju",
            "t.me/imycdbot?start=SAKURA-30-Register_Kq2YGHa7gG",
            "t.me/imycdbot?start=SAKURA-30-Register_qFUwV8yvUi",
            "t.me/imycdbot?start=SAKURA-30-Register_BnbVHHH0nx",
            "t.me/imycdbot?start=SAKURA-30-Register_3RnPegTjW1",
            "t.me/imycdbot?start=SAKURA-30-Register_jFM6grUMN2",
        ])

        first_profile = dedup.build_profile(first)
        second_profile = dedup.build_profile(second)

        self.assertNotEqual(first_profile["text_hash"], second_profile["text_hash"])
        self.assertNotEqual(first_profile["dedup_id"], second_profile["dedup_id"])


if __name__ == "__main__":
    unittest.main()


