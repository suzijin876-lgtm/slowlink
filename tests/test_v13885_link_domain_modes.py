import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def load_link_builder():
    fake_telethon = types.ModuleType("telethon")
    fake_tl = types.ModuleType("telethon.tl")
    fake_types = types.ModuleType("telethon.tl.types")
    fake_types.PeerChannel = type("PeerChannel", (), {})
    replacements = {
        "telethon": fake_telethon,
        "telethon.tl": fake_tl,
        "telethon.tl.types": fake_types,
    }
    old_modules = {name: sys.modules.get(name) for name in replacements}
    sys.modules.update(replacements)
    try:
        spec = importlib.util.spec_from_file_location("link_builder_v13885", APP / "link_builder.py")
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


class LinkDomainModesV13885Tests(unittest.TestCase):
    def test_public_link_defaults_to_t_me(self):
        link_builder = load_link_builder()
        chat = SimpleNamespace(id=3739634966, username="Jsoo8888")
        message = SimpleNamespace(id=115924, reply_to=None)

        self.assertEqual(
            link_builder.build_message_link(chat, message),
            "https://t.me/Jsoo8888/115924",
        )

    def test_invalid_public_domain_falls_back_to_t_me(self):
        link_builder = load_link_builder()
        chat = SimpleNamespace(id=3739634966, username="Jsoo8888")
        message = SimpleNamespace(id=115924, reply_to=None)

        self.assertEqual(
            link_builder.build_message_link(chat, message, "example.com"),
            "https://t.me/Jsoo8888/115924",
        )

    def test_listener_passes_cached_domain_to_link_builder(self):
        source = (APP / "bot_runner.py").read_text(encoding="utf-8-sig")

        self.assertIn(
            'build_message_link(chat, _evt_msg2, self._cached_str("public_link_domain"))',
            source,
        )

    def test_web_exposes_validated_immediate_domain_switch(self):
        web = (APP / "web.py").read_text(encoding="utf-8-sig")
        template = (APP / "templates" / "index.html").read_text(encoding="utf-8-sig")

        self.assertIn('@app.post("/set_link_domain")', web)
        self.assertIn('if value not in {"t.me", "telegram.me"}:', web)
        self.assertIn('set_value("public_link_domain", value)', web)
        self.assertIn("manager.clear_runtime_cache()", web)
        self.assertIn('action="/set_link_domain"', template)
        self.assertIn('id="publicLinkDomain"', template)
        self.assertIn('value="t.me"', template)
        self.assertIn('value="telegram.me"', template)

    def test_domain_setting_is_in_state_and_backup_restore(self):
        web = (APP / "web.py").read_text(encoding="utf-8-sig")

        self.assertGreaterEqual(web.count('"public_link_domain": _public_link_domain()'), 4)
        self.assertIn('if mode != "rules_only" and "public_link_domain" in payload:', web)
        self.assertIn('set_value("public_link_domain", domain)', web)


if __name__ == "__main__":
    unittest.main()
