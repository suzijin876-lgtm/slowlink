import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

fake_telethon = types.ModuleType("telethon")
fake_tl = types.ModuleType("telethon.tl")
fake_types = types.ModuleType("telethon.tl.types")
fake_types.PeerChannel = type("PeerChannel", (), {})
old_modules = {
    name: sys.modules.get(name)
    for name in ("telethon", "telethon.tl", "telethon.tl.types")
}
sys.modules.update({
    "telethon": fake_telethon,
    "telethon.tl": fake_tl,
    "telethon.tl.types": fake_types,
})
try:
    from link_builder import build_message_link
finally:
    for name, old in old_modules.items():
        if old is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = old


class PublicLinkPreviewDomainV13884Tests(unittest.TestCase):
    def test_public_message_uses_telegram_me_preview_domain(self):
        chat = SimpleNamespace(id=3739634966, username="Jsoo8888")
        message = SimpleNamespace(id=115924, reply_to=None)

        self.assertEqual(
            build_message_link(chat, message, "telegram.me"),
            "https://telegram.me/Jsoo8888/115924",
        )

    def test_public_forum_topic_uses_telegram_me_preview_domain(self):
        chat = SimpleNamespace(id=3739634966, username="public_forum")
        reply_to = SimpleNamespace(reply_to_top_id=321, reply_to_msg_id=None, forum_topic=True)
        message = SimpleNamespace(id=456, reply_to=reply_to)

        self.assertEqual(
            build_message_link(chat, message, "telegram.me"),
            "https://telegram.me/public_forum/321/456",
        )

    def test_private_message_keeps_t_me_c_domain(self):
        chat = SimpleNamespace(id=-1003739634966, username=None)
        message = SimpleNamespace(id=115924, reply_to=None)

        self.assertEqual(
            build_message_link(chat, message, "telegram.me"),
            "https://t.me/c/3739634966/115924",
        )

    def test_private_forum_topic_keeps_t_me_c_domain(self):
        chat = SimpleNamespace(id=3739634966, username=None)
        reply_to = SimpleNamespace(reply_to_top_id=321, reply_to_msg_id=None, forum_topic=True)
        message = SimpleNamespace(id=456, reply_to=reply_to)

        self.assertEqual(
            build_message_link(chat, message, "telegram.me"),
            "https://t.me/c/3739634966/321/456",
        )


if __name__ == "__main__":
    unittest.main()
