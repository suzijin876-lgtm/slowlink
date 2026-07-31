import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.test_v13893_exclude_texts import load_matcher
from tests.test_v139_chinese_guess_codes import FakeRedisClient, load_redis_store


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
OLD_LOTTERY_RULE = r"\n\n🎁 抽奖活动已开始"
NEW_LOTTERY_RULE = r"(?m)^抽奖活动已开始！?$"


def node(**values):
    return SimpleNamespace(**values)


def rich_lottery_message():
    return node(
        message="",
        rich_message=node(
            blocks=[
                node(video_id=123, caption=node(text=node())),
                node(text=node(texts=[node(text="🎉"), node(text=" 野草地")])),
                node(text=node(text="抽奖活动已开始！")),
                node(),
                node(
                    text=node(
                        texts=[
                            node(text="发布群组："),
                            node(text=node(text="野草地"), url="https://t.me/ycdgroup"),
                        ]
                    )
                ),
            ]
        ),
        reply_markup=node(
            rows=[
                node(
                    buttons=[
                        node(
                            text="🚀 打开活动",
                            url="https://t.me/MyLuckyStar8_Bot?startapp=example",
                        )
                    ]
                )
            ]
        ),
    )


class RichMessageLotteryV1391Tests(unittest.TestCase):
    def test_rich_message_blocks_are_extracted_with_line_boundaries(self):
        matcher = load_matcher()

        text = matcher.get_text(rich_lottery_message())

        self.assertEqual(text, "🎉 野草地\n抽奖活动已开始！\n发布群组：野草地")
        self.assertNotIn("打开活动", text)
        self.assertNotIn("startapp", text)

    def test_normal_message_text_remains_the_primary_source(self):
        matcher = load_matcher()
        message = rich_lottery_message()
        message.message = "普通消息原文"

        self.assertEqual(matcher.get_text(message), "普通消息原文")

    def test_new_lottery_rule_matches_extracted_rich_message_text(self):
        matcher = load_matcher(regex_rules={NEW_LOTTERY_RULE})

        result = matcher.analyze_message(matcher.get_text(rich_lottery_message()))

        self.assertTrue(result["matched"])
        self.assertEqual(result["rule"], NEW_LOTTERY_RULE)

    def test_known_old_lottery_rule_is_replaced_without_touching_other_rules(self):
        preserved_rule = "🍀 祝所有参与者好运！"
        client = FakeRedisClient({OLD_LOTTERY_RULE, preserved_rule})
        redis_store = load_redis_store(client)

        redis_store.ensure_defaults()

        rules = client.smembers("regex_rules")
        self.assertNotIn(OLD_LOTTERY_RULE, rules)
        self.assertIn(NEW_LOTTERY_RULE, rules)
        self.assertIn(preserved_rule, rules)

    def test_priority_queue_uses_the_same_message_text_extractor(self):
        source = (APP / "bot_runner.py").read_text(encoding="utf-8-sig")

        self.assertIn("raw_text = get_text(event.message)", source)
        self.assertNotIn('getattr(event.message, "message", "")', source)


if __name__ == "__main__":
    unittest.main()
