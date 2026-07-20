import importlib.util
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WARDROBE_PATH = PROJECT_ROOT / "MATERIAL" / "anna-wardrobe.md"
MODULE_PATH = PROJECT_ROOT / "DOCS" / "MODULES" / "MAIN_02_CONTENT_PROMPT.md"
PROMPT_LINT_PATH = PROJECT_ROOT / "TOOLS" / "prompt_lint.py"
PROMPT_LINT_SPEC = importlib.util.spec_from_file_location("prompt_lint", PROMPT_LINT_PATH)
PROMPT_LINT = importlib.util.module_from_spec(PROMPT_LINT_SPEC)
PROMPT_LINT_SPEC.loader.exec_module(PROMPT_LINT)

OUTFIT_PATTERN = re.compile(
    r"^夏-(\d{2})\.\n"
    r"- 季节标签：([^\n]+)\n"
    r"- 款式提示词：([^\n]+)$",
    re.MULTILINE,
)
LOWER_BODY_TERMS = ("短裤", "长裤", "牛仔裤", "短裙", "连衣裙", "衬衫裙", "裙裤")
SHORT_HEM_TERMS = ("短裤", "短裙", "连衣裙", "衬衫裙")
LAYERING_TERMS = ("开衫", "西装外套", "外搭", "作为内搭", "外穿", "背带短裤")
NECKLINE_TERMS = ("方领", "圆领", "U 形领", "小立领", "V 形领", "交叠领", "挂脖", "翻领", "船领", "Polo")
AMBIGUOUS_OR_DRIFT_TERMS = ("或", "可选", "单侧", "另一侧", "自然敞开", "裙裤", "草帽", "发箍", "独立腰带")
HIGH_RISK_TERMS = tuple(PROMPT_LINT.TNS_STACKING_TERMS)
STABILITY_SUFFIX = (
    "服装颜色、面料、领型、袖型、层次、腰线位置和下装版型全程保持一致，"
    "衣料仅随动作自然形变，完整服装轮廓持续清晰。"
)

PERSON_PROMPT = "人物：" + PROMPT_LINT.PROMPT_CONFIG["person"]
OTHER_PROMPT = (
    "其他：写实摄影风格，真实人物质感，均匀柔和的真实室内光影，"
    "真实皮肤纹理，真实面部结构，真实头发丝细节，真实服装材质，"
    "符合物理规律的光照和阴影，自然景深，真实镜头质感，真实环境透视，"
    "真实色彩。服装颜色、面料、领型、袖型、层次、腰线位置和下装版型全程一致，"
    "衣料仅随动作自然形变；人物肩背与墙面保持自然贴靠接触，墙上轻微柔边低对比度"
    "投影随动作同步变化；穿搭轮廓和腰线清晰可读，构图稳定，单一连续完整竖屏画面，"
    "人物和环境保持同一时空与稳定透视。"
)


def build_prompt(outfit, action_template_id):
    return "\n".join(
        (
            PERSON_PROMPT,
            "视频约束：" + PROMPT_LINT.FIXED_VIDEO_CONSTRAINT_TEMPLATES["01"],
            "穿搭：" + outfit,
            "环境：" + PROMPT_LINT.FIXED_ENVIRONMENT_TEMPLATES["01"],
            "人物动作：" + PROMPT_LINT.FIXED_ACTION_TEMPLATES[action_template_id],
            "背景音乐：轻松时尚的电子纯音乐，稳定柔和节拍，中速，氛围自然自信。",
            OTHER_PROMPT,
        )
    )


class AnnaWardrobeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WARDROBE_PATH.read_text(encoding="utf-8")
        cls.module_text = MODULE_PATH.read_text(encoding="utf-8")
        cls.outfits = OUTFIT_PATTERN.findall(cls.text)

    def test_summer_slots_cover_full_month(self):
        identifiers = [identifier for identifier, _, _ in self.outfits]
        self.assertEqual(identifiers, [f"{day:02d}" for day in range(1, 32)])

    def test_each_outfit_has_complete_knee_up_description(self):
        for identifier, season, prompt in self.outfits:
            with self.subTest(identifier=identifier):
                self.assertEqual(season, "夏季")
                self.assertTrue(any(term in prompt for term in LOWER_BODY_TERMS), prompt)
                self.assertTrue(prompt.endswith(STABILITY_SUFFIX), prompt)

    def test_outfit_prompts_exclude_tns_stacking_terms_and_footwear(self):
        for identifier, _, prompt in self.outfits:
            with self.subTest(identifier=identifier):
                for term in HIGH_RISK_TERMS:
                    self.assertNotIn(term, prompt)
                self.assertNotIn("鞋", prompt)
                self.assertNotIn("脚部", prompt)

    def test_outfit_prompts_exclude_ambiguous_or_drift_prone_terms(self):
        for identifier, _, prompt in self.outfits:
            with self.subTest(identifier=identifier):
                for term in AMBIGUOUS_OR_DRIFT_TERMS:
                    self.assertNotIn(term, prompt)

    def test_short_hems_use_conservative_knee_up_length(self):
        for identifier, _, prompt in self.outfits:
            with self.subTest(identifier=identifier):
                if any(term in prompt for term in SHORT_HEM_TERMS):
                    self.assertIn("膝盖上方", prompt)

    def test_open_necklines_are_explicitly_shallow_or_high(self):
        neckline_boundaries = {
            "方领": "浅方领",
            "U 形领": "高位 U 形领",
            "V 形领": "浅 V 形领",
            "交叠领": "浅交叠领",
            "船领": "高位船领",
        }
        for identifier, _, prompt in self.outfits:
            with self.subTest(identifier=identifier):
                for neckline, safe_variant in neckline_boundaries.items():
                    if neckline in prompt:
                        self.assertIn(safe_variant, prompt)

    def test_wardrobe_preserves_style_diversity(self):
        prompts = [prompt for _, _, prompt in self.outfits]
        self.assertGreaterEqual(sum("连衣裙" in prompt for prompt in prompts), 7)
        self.assertGreaterEqual(
            sum("长裤" in prompt or "牛仔裤" in prompt for prompt in prompts),
            3,
        )
        self.assertGreaterEqual(
            sum(any(term in prompt for term in LAYERING_TERMS) for prompt in prompts),
            5,
        )
        self.assertGreaterEqual(sum("短裤" in prompt for prompt in prompts), 9)
        self.assertGreaterEqual(
            sum(any(term in prompt for term in NECKLINE_TERMS) for prompt in prompts),
            25,
        )

    def test_every_outfit_and_action_template_passes_fast_prompt_lint(self):
        for identifier, _, outfit in self.outfits:
            for action_template_id in sorted(PROMPT_LINT.FIXED_ACTION_TEMPLATES):
                with self.subTest(identifier=identifier, action_template_id=action_template_id):
                    result = PROMPT_LINT.lint_text(
                        build_prompt(outfit, action_template_id),
                        Path(f"summer-{identifier}-action-{action_template_id}.txt"),
                        route="anna",
                        channel="auto",
                    )
                    self.assertEqual(result["decision"], "pass", result["findings"])

    def test_writing_rules_keep_body_anchors_outside_clothing_sections(self):
        self.assertIn("每条款式提示词必须完整指定上装与膝上可见下装", self.text)
        self.assertIn("每套最多使用两层服装和一种图案", self.text)
        self.assertIn("人物身份与基础身材比例由固定角色图和人物段统一锚定", self.text)
        self.assertIn("不写鞋履", self.text)
        self.assertIn("默认采用高位或浅口领型", self.text)
        self.assertIn("裙裤下摆统一落在膝盖上方", self.text)
        self.assertIn("不在穿搭段重复扩写", self.module_text)
        self.assertIn("服装颜色、面料、领型、袖型、层次、腰线位置与下装版型全程一致", self.module_text)
        self.assertIn("人物身材体量与胸臀强化描述不在此段重复扩写", self.module_text)


if __name__ == "__main__":
    unittest.main()
