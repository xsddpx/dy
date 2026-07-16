import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = PROJECT_ROOT / "TOOLS"
sys.path.insert(0, str(TOOLS_DIR))

PROMPT_LINT_SPEC = importlib.util.spec_from_file_location("prompt_lint", TOOLS_DIR / "prompt_lint.py")
PROMPT_LINT = importlib.util.module_from_spec(PROMPT_LINT_SPEC)
PROMPT_LINT_SPEC.loader.exec_module(PROMPT_LINT)

SELECTOR_SPEC = importlib.util.spec_from_file_location("select_wardrobe", TOOLS_DIR / "select_wardrobe.py")
SELECTOR = importlib.util.module_from_spec(SELECTOR_SPEC)
SELECTOR_SPEC.loader.exec_module(SELECTOR)

WARDROBE_DIR = PROJECT_ROOT / "MATERIAL" / "wardrobe-images"
PERSON_PROMPT = (
    "人物：@图1 是同一位成年女性的多视角、多表情角色参考图，不是多人合照；"
    "脸部严格参考左下角大脸，身材严格参考正面、侧面和背面全身图，"
    "保持同一人物的脸部身份与身材一致。画面中只出现这一位成年女性。"
)
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
            "穿搭：" + PROMPT_LINT.WARDROBE_IMAGE_ANCHOR + "同时保持" + outfit,
            "环境：" + PROMPT_LINT.FIXED_ENVIRONMENT_TEMPLATES["wardrobe-image-01"],
            "人物动作：" + PROMPT_LINT.FIXED_ACTION_TEMPLATES[action_template_id],
            "背景音乐：轻松时尚的电子纯音乐，稳定柔和节拍，中速，氛围自然自信。",
            OTHER_PROMPT,
        )
    )


class AnnaWardrobeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries = SELECTOR.discover(WARDROBE_DIR)

    def test_legacy_wardrobe_document_is_removed(self):
        self.assertFalse((PROJECT_ROOT / "MATERIAL" / "anna-wardrobe.md").exists())

    def test_all_entries_use_folder_contract(self):
        self.assertTrue(self.entries)
        self.assertEqual(
            [entry.identifier for entry in self.entries],
            sorted(entry.identifier for entry in self.entries),
        )
        for entry in self.entries:
            with self.subTest(identifier=entry.identifier):
                self.assertEqual(entry.directory.name, f"衣柜图-{entry.identifier}")
                self.assertEqual(entry.image.name, f"衣柜图-{entry.identifier}.png")
                self.assertEqual(entry.description_file.name, "服装描述.md")
                self.assertTrue(entry.prompt)

    def test_every_description_and_action_template_passes_three_image_lint(self):
        for entry in self.entries:
            for action_template_id in sorted(PROMPT_LINT.FIXED_ACTION_TEMPLATES):
                with self.subTest(identifier=entry.identifier, action_template_id=action_template_id):
                    result = PROMPT_LINT.lint_text(
                        build_prompt(entry.prompt, action_template_id),
                        Path(f"wardrobe-{entry.identifier}-action-{action_template_id}.txt"),
                    )
                    self.assertEqual(result["decision"], "pass", result["findings"])

    def test_description_is_injected_verbatim_after_image_anchor(self):
        for entry in self.entries:
            prompt = build_prompt(entry.prompt, "01")
            self.assertIn(PROMPT_LINT.WARDROBE_IMAGE_ANCHOR + "同时保持" + entry.prompt, prompt)


if __name__ == "__main__":
    unittest.main()
