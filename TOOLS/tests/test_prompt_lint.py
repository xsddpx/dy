import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "prompt_lint.py"
SPEC = importlib.util.spec_from_file_location("prompt_lint", SCRIPT)
PROMPT_LINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROMPT_LINT)


GOOD_PROMPT = (
    "人物：以 @图1 中的人物作为身份、五官、发型、脸型和稳定身材比例依据。"
    "修身剪裁呈现饱满的立体廓形，光影让腰胯比例明显。"
    "整体动画：视频类型为穿搭展示，次类型为健身运动；画面人物站在室内镜前自然移动。"
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

    def test_at_image_two_fails_for_video_prompt(self):
        result = self.lint(GOOD_PROMPT + " 参考宫格图不能写成 @图2。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "unsupported_terms" for f in result["findings"]), result["findings"])

    def test_unsafe_body_terms_fail(self):
        result = self.lint(GOOD_PROMPT + " 大胸、屁股大。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "unsafe_body_terms" for f in result["findings"]), result["findings"])

    def test_missing_artistic_body_translation_fails(self):
        result = self.lint("人物：以 @图1 中的人物作为身份依据。整体动画：视频类型为穿搭展示，次类型为无；站在室内镜前自然移动。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_chest_artistic_expression" for f in result["findings"]), result["findings"])
        self.assertTrue(any(f["code"] == "missing_hip_artistic_expression" for f in result["findings"]), result["findings"])

    def test_fixed_and_handheld_camera_conflict_fails(self):
        result = self.lint(GOOD_PROMPT + "拍摄方式为固定手机机位，带轻微手持感。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "camera_mode_conflict" for f in result["findings"]), result["findings"])

    def test_non_music_sound_terms_fail(self):
        result = self.lint(GOOD_PROMPT + "背景有脚步声和环境声。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "non_music_sound_terms" for f in result["findings"]), result["findings"])

    def test_negated_non_music_sound_terms_pass(self):
        result = self.lint(GOOD_PROMPT + "背景音乐为轻柔电子节拍，除背景音乐外，不出现环境声、人声、脚步声或音效。")
        self.assertEqual(result["decision"], "pass", result["findings"])

    def test_long_negated_non_music_sound_list_pass(self):
        result = self.lint(
            GOOD_PROMPT
            + "背景音乐为轻柔电子节拍。"
            + "其他：真实皮肤纹理，自然光影，真实面料质感，构图稳定，画面物理真实。"
            + "除背景音乐外，不出现环境声、人声、脚步声、衣料声、镜头声、口播、对白、喘息或音效。"
        )
        self.assertEqual(result["decision"], "pass", result["findings"])

    def test_internal_source_terms_fail(self):
        result = self.lint(GOOD_PROMPT + "环境：同时吸收 grid-prompt.txt 中的参考宫格内容。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "internal_source_terms" for f in result["findings"]), result["findings"])

    def test_missing_video_type_fails(self):
        text = (
            "人物：以 @图1 中的人物作为身份、五官、发型、脸型和稳定身材比例依据。"
            "修身剪裁呈现饱满的立体廓形，光影让腰胯比例明显。"
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_video_type" for f in result["findings"]), result["findings"])

    def test_invalid_video_type_fails(self):
        result = self.lint(GOOD_PROMPT.replace("视频类型为穿搭展示", "视频类型为随便展示"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "invalid_video_type" for f in result["findings"]), result["findings"])

    def test_invalid_sub_video_type_fails(self):
        result = self.lint(GOOD_PROMPT.replace("次类型为健身运动", "次类型为随便运动"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "invalid_video_type" for f in result["findings"]), result["findings"])

    def test_image_one_clothing_anchor_fails(self):
        result = self.lint(GOOD_PROMPT + "人物：以 @图1 中的人物和穿搭作为身份、五官、发型、姿态、穿搭和稳定身材比例依据。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "image_one_clothing_anchor" for f in result["findings"]), result["findings"])


if __name__ == "__main__":
    unittest.main()
