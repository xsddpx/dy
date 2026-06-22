import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "prompt_lint.py"
SPEC = importlib.util.spec_from_file_location("prompt_lint", SCRIPT)
PROMPT_LINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROMPT_LINT)


GOOD_PROMPT = (
    "画面人物以本次确认图为身份锚点，站在室内镜前自然移动。"
    "修身剪裁呈现饱满的立体廓形，光影让腰胯比例明显。"
)


class PromptLintFlowTest(unittest.TestCase):
    def lint(self, text, route="anna", channel="auto"):
        return PROMPT_LINT.lint_text(text, Path("prompt.txt"), route, channel)

    def test_auto_anna_with_confirmation_image_passes(self):
        result = self.lint(GOOD_PROMPT)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertEqual(result["route"], "anna")
        self.assertEqual(result["channel"], "auto")

    def test_without_confirmation_image_fails(self):
        result = self.lint("室内镜前自然移动。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_confirmation_image" for f in result["findings"]), result["findings"])

    def test_non_anna_or_non_auto_fails(self):
        self.assertEqual(self.lint(GOOD_PROMPT, route="other")["decision"], "fail")
        self.assertEqual(self.lint(GOOD_PROMPT, channel="other")["decision"], "fail")

    def test_unsupported_terms_fail(self):
        result = self.lint(GOOD_PROMPT + " @图2 模型参数。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "unsupported_terms" for f in result["findings"]), result["findings"])

    def test_unsafe_body_terms_fail(self):
        result = self.lint(GOOD_PROMPT + " 大胸、屁股大。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "unsafe_body_terms" for f in result["findings"]), result["findings"])

    def test_missing_artistic_body_translation_fails(self):
        result = self.lint("画面人物以本次确认图为身份锚点，站在室内镜前自然移动。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_chest_artistic_expression" for f in result["findings"]), result["findings"])
        self.assertTrue(any(f["code"] == "missing_hip_artistic_expression" for f in result["findings"]), result["findings"])

    def test_fixed_and_handheld_camera_conflict_fails(self):
        result = self.lint(GOOD_PROMPT + "拍摄方式为固定手机机位，带轻微手持感。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "camera_mode_conflict" for f in result["findings"]), result["findings"])


if __name__ == "__main__":
    unittest.main()
