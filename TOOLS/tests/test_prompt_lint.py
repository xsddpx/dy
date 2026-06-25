import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "prompt_lint.py"
SPEC = importlib.util.spec_from_file_location("prompt_lint", SCRIPT)
PROMPT_LINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROMPT_LINT)


GOOD_PROMPT = (
    "人物：以 @图1 中的人物作为身份、五官、发型、脸型和稳定身材比例依据。"
    "视频类型：穿搭展示；次类型：健身运动；近景穿搭展示结合轻运动互动节奏。"
    "穿搭：黑色修身上衣，高腰半裙，腰线清晰。"
    "姿态镜头：正面站姿，平视半身近景，手部轻整理衣摆。"
    "环境：现代室内镜前，柔和窗光和浅色墙面。"
    "卖点与锁定：修身剪裁呈现饱满的立体廓形，光影让腰胯比例明显，封面停顿稳定。"
    "表情节奏：开场眼神平静看向镜头，中段眉眼放松，结尾嘴角轻收并短暂停顿。"
    "整体动画：约 5-6 秒，画面人物站在室内镜前自然移动，手部轻整理衣摆后回到腰侧。"
    "背景音乐：轻柔电子节拍，节奏清晰。"
    "其他：真实皮肤纹理，自然光影，真实面料质感，穿搭轮廓清晰，腰线可见，构图稳定，画面物理真实。"
)


class PromptLintFlowTest(unittest.TestCase):
    def lint(self, text, route="anna", channel="auto"):
        return PROMPT_LINT.lint_text(text, Path("prompt.txt"), route, channel)

    def test_auto_anna_with_ten_section_prompt_passes(self):
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

    def test_missing_required_section_fails(self):
        result = self.lint(GOOD_PROMPT.replace("表情节奏：开场眼神平静看向镜头，中段眉眼放松，结尾嘴角轻收并短暂停顿。", ""))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_sections" for f in result["findings"]), result["findings"])

    def test_inline_label_mention_does_not_count_as_section(self):
        text = GOOD_PROMPT.replace(
            "表情节奏：开场眼神平静看向镜头，中段眉眼放松，结尾嘴角轻收并短暂停顿。",
            "",
        ).replace(
            "整体动画：约 5-6 秒，画面人物站在室内镜前自然移动，手部轻整理衣摆后回到腰侧。",
            "整体动画：约 5-6 秒，动作承接表情节奏：开场平静，中段放松，结尾短暂停顿。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_sections" for f in result["findings"]), result["findings"])

    def test_conditional_person_template_fails(self):
        text = GOOD_PROMPT.replace(
            "人物：以 @图1 中的人物作为身份、五官、发型、脸型和稳定身材比例依据。",
            "人物：以 @图1 中的人物作为身份依据；若 @图1 是多视角角色参考图，以左下大脸为主要身份依据。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "conditional_or_placeholder_terms" for f in result["findings"]), result["findings"])

    def test_placeholder_ellipsis_fails(self):
        result = self.lint(GOOD_PROMPT.replace("穿搭：黑色修身上衣，高腰半裙，腰线清晰。", "穿搭：..."))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "conditional_or_placeholder_terms" for f in result["findings"]), result["findings"])

    def test_camera_mode_conflict_is_left_to_prompt_review(self):
        result = self.lint(GOOD_PROMPT + "拍摄方式为固定手机机位，带轻微手持感。")
        self.assertEqual(result["decision"], "pass", result["findings"])

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
        result = self.lint(GOOD_PROMPT + "环境：同时吸收 grid-prompt.txt 中的参考宫格内容。参考类型识别：主类型=穿搭展示。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "internal_source_terms" for f in result["findings"]), result["findings"])

    def test_compliance_or_explanation_terms_fail(self):
        result = self.lint(GOOD_PROMPT + "合规说明：平台可发布，不涉及未成年或裸体内容，等待审核。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "compliance_or_explanation_terms" for f in result["findings"]), result["findings"])

    def test_old_reference_analysis_index_fails(self):
        result = self.lint(GOOD_PROMPT + "参考类型识别：主类型=穿搭展示；次类型=健身运动；判断依据=正面站姿。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "internal_source_terms" for f in result["findings"]), result["findings"])

    def test_missing_video_type_fails(self):
        text = GOOD_PROMPT.replace("视频类型：穿搭展示；次类型：健身运动；近景穿搭展示结合轻运动互动节奏。", "")
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_video_type" for f in result["findings"]), result["findings"])

    def test_invalid_video_type_fails(self):
        result = self.lint(GOOD_PROMPT.replace("视频类型：穿搭展示", "视频类型：随便展示"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "invalid_video_type" for f in result["findings"]), result["findings"])

    def test_invalid_sub_video_type_fails(self):
        result = self.lint(GOOD_PROMPT.replace("次类型：健身运动", "次类型：随便运动"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "invalid_video_type" for f in result["findings"]), result["findings"])

    def test_image_one_clothing_anchor_fails(self):
        result = self.lint(GOOD_PROMPT + "人物：以 @图1 中的人物和穿搭作为身份、五官、发型、姿态、穿搭和稳定身材比例依据。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "image_one_clothing_anchor" for f in result["findings"]), result["findings"])


if __name__ == "__main__":
    unittest.main()
