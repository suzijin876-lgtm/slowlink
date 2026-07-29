import unittest

from tests.test_v13883_cross_template_lottery_dedup import load_dedup


KEYWORD_TEMPLATE = """🎰 集联请你看《蜘蛛侠4：崭新之日》

创建者: 𝓟𝓮𝓽𝓻𝓲𝓬𝓱𝓸𝓻
参与次数上限: 1
跨群总参与次数上限: 1
已参与: 280人 (280票)
中奖概率(每张票): 0.7%

🔑 参与关键词: Peter Tingle

📮 抽奖条件:
参与要求: 集邮者联盟

🎁 奖品内容:
1. 电影票 x2

💡 活动说明:
有IMAX必选IMAX!

凭观影记录报销！不支持折现！

情侣/暧昧异性观影可报销双人票💗（单身的兄弟萌只能助攻到这儿了！赶紧约起来！）

ps:未避免离奇刺客/活动漏洞，最终解释权归集联所有，衷心祝愿大家观影愉快！

😊 开奖条件:
定时开奖: 2026-07-29 14:30

请先私聊机器人后再参与该抽奖。"""

BUTTON_TEMPLATE = KEYWORD_TEMPLATE.replace(
    "创建者: 𝓟𝓮𝓽𝓻𝓲𝓬𝓱𝓸𝓻",
    "创建者: 1022013997",
).replace(
    "🔑 参与关键词: Peter Tingle\n\n📮 抽奖条件:\n",
    "🔑 点击按钮参与\n",
)


class AqLotteryCrossTemplateDedupV13899Tests(unittest.TestCase):
    def test_keyword_and_button_templates_share_short_window_identity(self):
        dedup, _client = load_dedup()

        keyword = dedup.build_profile(
            KEYWORD_TEMPLATE,
            "https://t.me/Petrichor_Embys_chat/249126",
            "集邮者联盟",
        )
        button = dedup.build_profile(
            BUTTON_TEMPLATE,
            "https://t.me/Petrichor_Embys_channel/265",
            "Emby, Assemble！",
        )

        self.assertNotEqual(keyword["dedup_id"], button["dedup_id"])
        self.assertTrue(keyword["lottery_template_identity"].startswith("aq-event:"))
        self.assertEqual(
            keyword["lottery_template_identity"],
            button["lottery_template_identity"],
        )

    def test_button_crosspost_is_blocked_after_keyword_variant(self):
        dedup, _client = load_dedup()

        first_duplicate, _reason, _profile = dedup.check_and_mark(
            KEYWORD_TEMPLATE,
            "https://t.me/Petrichor_Embys_chat/249126",
            None,
            "strict",
            "集邮者联盟",
        )
        second_duplicate, reason, _profile = dedup.check_and_mark(
            BUTTON_TEMPLATE,
            "https://t.me/Petrichor_Embys_channel/265",
            None,
            "strict",
            "Emby, Assemble！",
        )

        self.assertFalse(first_duplicate)
        self.assertTrue(second_duplicate)
        self.assertEqual(reason, "同一抽奖的不同模板重复（10分钟内）")

    def test_changed_stable_event_fields_remain_distinct(self):
        dedup, _client = load_dedup()
        original = dedup.build_profile(KEYWORD_TEMPLATE)["lottery_template_identity"]
        variants = (
            BUTTON_TEMPLATE.replace("蜘蛛侠4：崭新之日", "蜘蛛侠5"),
            BUTTON_TEMPLATE.replace("2026-07-29 14:30", "2026-07-29 15:30"),
            BUTTON_TEMPLATE.replace("电影票 x2", "电影票 x3"),
            BUTTON_TEMPLATE.replace("参与要求: 集邮者联盟", "参与要求: 茶话领域"),
            BUTTON_TEMPLATE.replace("有IMAX必选IMAX!", "普通影厅也可以"),
        )

        self.assertTrue(original)
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(
                    original,
                    dedup.build_profile(variant)["lottery_template_identity"],
                )

    def test_incomplete_template_does_not_get_broad_identity(self):
        dedup, _client = load_dedup()
        without_requirement = BUTTON_TEMPLATE.replace("参与要求: 集邮者联盟\n", "")
        without_details = BUTTON_TEMPLATE.split("💡 活动说明:", 1)[0]

        self.assertEqual(
            dedup.build_profile(without_requirement)["lottery_template_identity"],
            "",
        )
        self.assertEqual(
            dedup.build_profile(without_details)["lottery_template_identity"],
            "",
        )

    def test_cross_template_correlation_expires_after_ten_minutes(self):
        dedup, client = load_dedup()

        first_duplicate, _reason, _profile = dedup.check_and_mark(
            KEYWORD_TEMPLATE,
            "https://t.me/Petrichor_Embys_chat/249126",
            None,
            "strict",
            "集邮者联盟",
        )
        client.now += 601
        second_duplicate, _reason, _profile = dedup.check_and_mark(
            BUTTON_TEMPLATE,
            "https://t.me/Petrichor_Embys_channel/265",
            None,
            "strict",
            "Emby, Assemble！",
        )

        self.assertFalse(first_duplicate)
        self.assertFalse(second_duplicate)


if __name__ == "__main__":
    unittest.main()
