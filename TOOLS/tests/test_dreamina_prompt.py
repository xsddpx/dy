import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "dreamina_prompt.py"
SPEC = importlib.util.spec_from_file_location("dreamina_prompt", SCRIPT)
DREAMINA_PROMPT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DREAMINA_PROMPT)


class DreaminaPromptTest(unittest.TestCase):
    def test_rewrites_anna_to_graph1(self):
        text = "画面人物以 @anna 为身份锚点。"
        self.assertEqual(DREAMINA_PROMPT.rewrite_prompt(text, "anna", "auto"), "画面人物以 @图1 为身份锚点。")

    def test_rewrites_confirmation_image_to_graph1(self):
        text = "画面人物以本次确认图为身份锚点。"
        self.assertEqual(DREAMINA_PROMPT.rewrite_prompt(text, "anna", "auto"), "画面人物以@图1为身份锚点。")

    def test_rejects_non_auto_route_or_channel(self):
        with self.assertRaises(ValueError):
            DREAMINA_PROMPT.rewrite_prompt("x", "duo", "auto")
        with self.assertRaises(ValueError):
            DREAMINA_PROMPT.rewrite_prompt("x", "anna", "direct")

    def test_validation_requires_graph1(self):
        errors = DREAMINA_PROMPT.validate_prompt("画面人物保持 anna 身份锚点。", "anna", "auto")
        self.assertTrue(any("缺少 @图1" in error for error in errors), errors)

    def test_validation_blocks_unsupported_terms(self):
        errors = DREAMINA_PROMPT.validate_prompt("画面人物以 @图1 和 @图2 为身份锚点。", "anna", "auto")
        self.assertTrue(any("不支持" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
