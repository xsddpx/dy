import importlib.util
import io
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "prompt_lint.py"
PROJECT_ROOT = SCRIPT.parents[1]
SPEC = importlib.util.spec_from_file_location("prompt_lint", SCRIPT)
PROMPT_LINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROMPT_LINT)


PERSON_PROMPT = "人物：" + PROMPT_LINT.PROMPT_CONFIG["person"]

PERSON_ACTION_PROMPT = "人物动作：" + PROMPT_LINT.FIXED_ACTION_TEMPLATES["01"]

VIDEO_CONSTRAINT_PROMPT = "视频约束：" + PROMPT_LINT.FIXED_VIDEO_CONSTRAINT_TEMPLATES["01"]

ENVIRONMENT_PROMPT = "环境：" + PROMPT_LINT.FIXED_ENVIRONMENT_TEMPLATES["01"]

OTHER_PROMPT = "其他：写实摄影风格，真实人物质感，均匀柔和的真实室内光影，真实皮肤纹理，真实面部结构，真实头发丝细节，真实服装材质，符合物理规律的光照和阴影，自然景深，真实镜头质感，真实环境透视，真实色彩。穿搭轮廓清晰，腰线可见，构图稳定，单一连续完整竖屏画面，人物和环境保持同一时空与稳定透视。"

GOOD_PROMPT = (
    PERSON_PROMPT
    + VIDEO_CONSTRAINT_PROMPT
    + "穿搭：黑色合体上衣搭配高腰直筒短裙，上衣采用哑光面料并呈现清晰腰线，短裙版型全程一致。"
    + ENVIRONMENT_PROMPT
    + PERSON_ACTION_PROMPT
    + "背景音乐：轻快电子律动纯音乐，稳定四拍节奏，氛围俏皮自信。"
    + OTHER_PROMPT
)

class PromptLintFlowTest(unittest.TestCase):
    def lint(self, text, route="anna", channel="auto"):
        return PROMPT_LINT.lint_text(text, Path("prompt.txt"), route, channel)

    def test_auto_anna_with_seven_section_prompt_passes(self):
        result = self.lint(GOOD_PROMPT)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertEqual(result["route"], "anna")
        self.assertEqual(result["channel"], "auto")
        self.assertEqual(result["mode"], "fast")

    def test_documented_fixed_templates_match_linter_contract(self):
        doc = (PROJECT_ROOT / "DOCS/MODULES/MAIN_02_CONTENT_PROMPT.md").read_text(encoding="utf-8")
        config = (PROJECT_ROOT / "MATERIAL/xdy-workflow.json").read_text(encoding="utf-8")
        self.assertTrue((PROJECT_ROOT / "MATERIAL/fixed-environment/anna-room-01.png").exists())
        self.assertIn("MATERIAL/xdy-workflow.json", doc)
        self.assertIn("不复制固定模板", doc)
        self.assertIn("全程保持正常速度，不使用慢动作", config)
        self.assertEqual(PROMPT_LINT.PROMPT_CONFIG["video_constraint"], PROMPT_LINT.FIXED_VIDEO_CONSTRAINT_TEMPLATES["01"])

        self.assertIn("单一连续膝盖以上中景", VIDEO_CONSTRAINT_PROMPT)
        self.assertIn("机位高度大致与人物胸部齐平", VIDEO_CONSTRAINT_PROMPT)
        self.assertIn("人物位于画面中央并贴近墙面", VIDEO_CONSTRAINT_PROMPT)
        self.assertIn("动作范围保持在墙前半步内", VIDEO_CONSTRAINT_PROMPT)
        self.assertIn("脚部始终位于画外", VIDEO_CONSTRAINT_PROMPT)
        self.assertIn("全程保持正常速度", VIDEO_CONSTRAINT_PROMPT)
        self.assertIn("不使用慢动作", VIDEO_CONSTRAINT_PROMPT)
        self.assertNotIn("人物展示；", VIDEO_CONSTRAINT_PROMPT)
        self.assertNotIn("舞蹈律动", VIDEO_CONSTRAINT_PROMPT)

    def test_non_template_environment_fails(self):
        text = GOOD_PROMPT.replace(ENVIRONMENT_PROMPT, "环境：现代酒店窗边，柔和窗光和木地板。")
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "invalid_environment_template" for f in result["findings"]), result["findings"])

    def test_person_action_text_is_not_exactly_validated(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：人物在原地完成一圈转身展示。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertFalse(any(f["code"] == "invalid_action_template" for f in result["findings"]), result["findings"])

    def test_action_template_01_with_its_video_constraint_passes(self):
        text = GOOD_PROMPT.replace(
            VIDEO_CONSTRAINT_PROMPT,
            "视频约束：" + PROMPT_LINT.FIXED_VIDEO_CONSTRAINT_TEMPLATES["01"],
        ).replace(
            PERSON_ACTION_PROMPT,
            "人物动作：" + PROMPT_LINT.FIXED_ACTION_TEMPLATES["01"],
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])

    def test_action_template_02_with_fixed_video_constraint_passes(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：" + PROMPT_LINT.FIXED_ACTION_TEMPLATES["02"],
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])

    def test_new_action_templates_with_fixed_video_constraint_pass(self):
        for template_id in ("03", "04"):
            with self.subTest(template_id=template_id):
                text = GOOD_PROMPT.replace(
                    PERSON_ACTION_PROMPT,
                    "人物动作：" + PROMPT_LINT.FIXED_ACTION_TEMPLATES[template_id],
                )
                result = self.lint(text)
                self.assertEqual(result["decision"], "pass", result["findings"])

    def test_legacy_overall_animation_section_fails(self):
        text = GOOD_PROMPT.replace(PERSON_ACTION_PROMPT, "整体动画：" + PROMPT_LINT.FIXED_ACTION_TEMPLATES["01"])
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "missing_sections" for f in result["findings"]), result["findings"])

    def test_person_section_missing_fixed_anchors_fails(self):
        text = GOOD_PROMPT.replace(PERSON_PROMPT, "人物：@图1 是同一位成年女性。")
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "missing_person_anchors" for f in result["findings"]), result["findings"])

    def test_fixed_person_template_explicitly_locks_chest_volume(self):
        person = PROMPT_LINT.PROMPT_CONFIG["person"]
        for phrase in (
            "胸部体量严格以正面、斜侧面和侧面全身图为准",
            "与角色图相同的体量",
            "胸廓前后比例",
            "侧向投影",
            "各角度全程稳定一致",
        ):
            self.assertIn(phrase, person)

    def test_extra_expression_section_fails(self):
        text = GOOD_PROMPT.replace("人物动作：", "表情节奏：自然微笑。人物动作：")
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "unexpected_sections" for f in result["findings"]), result["findings"])

    def test_duplicate_required_section_fails(self):
        result = self.lint(GOOD_PROMPT + "环境：重复环境段。")
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "duplicate_sections" for f in result["findings"]), result["findings"])

    def test_standalone_sellpoint_section_fails(self):
        text = GOOD_PROMPT.replace(
            "人物动作：",
            "卖点与建议：上身轮廓和腰线清楚。人物动作：",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "standalone_sellpoint_section" for f in result["findings"]), result["findings"])

    def test_legacy_standalone_sellpoint_lock_section_fails(self):
        text = GOOD_PROMPT.replace(
            "人物动作：",
            "卖点与锁定：上身轮廓和腰线清楚。人物动作：",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "standalone_sellpoint_section" for f in result["findings"]), result["findings"])

    def test_direct_vid_prompt_lint_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "vid-prompt-v1.txt"
            out = Path(tmp) / "lint"
            source.write_text(GOOD_PROMPT, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = PROMPT_LINT.main(["lint", str(source), "--out-dir", str(out)])
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertTrue((out / "report.json").is_file())

    def test_top_level_help_only_mentions_direct_vid_lint(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = PROMPT_LINT.main(["--help"])
        help_text = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("lint", help_text)
        self.assertNotIn("derive", help_text)
        self.assertIn("vid-prompt-v1.txt", help_text)
        self.assertIn("省略 lint", help_text)

    def test_lint_subcommand_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "vid-prompt-v1.txt"
            out_dir = Path(tmp) / "lint-report"
            source.write_text(GOOD_PROMPT, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = PROMPT_LINT.main(["lint", str(source), "--out-dir", str(out_dir)])
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertTrue((out_dir / "report.json").exists())

    def test_legacy_lint_invocation_still_writes_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "vid-prompt-v1.txt"
            out_dir = Path(tmp) / "legacy-lint-report"
            source.write_text(GOOD_PROMPT, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = PROMPT_LINT.main([str(source), "--out-dir", str(out_dir)])
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertTrue((out_dir / "report.json").exists())

    def test_without_role_image_fails(self):
        result = self.lint("室内镜前自然移动。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_role_image" for f in result["findings"]), result["findings"])

    def test_non_anna_or_non_auto_fails(self):
        self.assertEqual(self.lint(GOOD_PROMPT, route="other")["decision"], "fail")
        self.assertEqual(self.lint(GOOD_PROMPT, channel="other")["decision"], "fail")

    def test_unsupported_terms_fail(self):
        result = self.lint(GOOD_PROMPT + " @图3 模型参数。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "unsupported_terms" for f in result["findings"]), result["findings"])

    def test_without_environment_image_fails(self):
        result = self.lint(GOOD_PROMPT.replace(ENVIRONMENT_PROMPT, "环境：固定室内环境。"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_environment_image" for f in result["findings"]), result["findings"])

    def test_unsafe_body_terms_fail(self):
        result = self.lint(GOOD_PROMPT + " 大胸、屁股大。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "unsafe_body_terms" for f in result["findings"]), result["findings"])

    def test_tns_stacking_terms_fail_in_content_sections(self):
        variants = (
            GOOD_PROMPT.replace(
                "穿搭：黑色合体上衣搭配高腰直筒短裙，上衣采用哑光面料并呈现清晰腰线，短裙版型全程一致。",
                "穿搭：白色低圆领紧身上衣搭配包臀迷你裙。",
            ),
            GOOD_PROMPT.replace(
                PERSON_ACTION_PROMPT,
                "人物动作：人物原地展示饱满上围与丰满臀部，服装轮廓清楚。",
            ),
            GOOD_PROMPT.replace(
                OTHER_PROMPT,
                "其他：写实摄影风格，突出胸部体量、腰胯比例和沙漏轮廓。",
            ),
        )
        for text in variants:
            with self.subTest(text=text):
                result = self.lint(text)
                self.assertEqual(result["decision"], "fail", result["findings"])
                self.assertTrue(
                    any(f["code"] == "tns_stacking_terms" for f in result["findings"]),
                    result["findings"],
                )

    def test_neutral_camera_body_landmarks_do_not_trigger_tns_rule(self):
        result = self.lint(GOOD_PROMPT)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertFalse(
            any(f["code"] == "tns_stacking_terms" for f in result["findings"]),
            result["findings"],
        )

    def test_appearance_changes_fail(self):
        variants = (
            GOOD_PROMPT.replace(
                "画面中只出现这一位成年女性。",
                "画面中只出现这一位成年女性，动作中发型变成金色短发。",
            ),
            GOOD_PROMPT.replace(
                "画面中只出现这一位成年女性。",
                "画面中只出现这一位成年女性，头发由黑色转为金色。",
            ),
            GOOD_PROMPT.replace(
                OTHER_PROMPT,
                OTHER_PROMPT + "上衣由白色逐渐变成红色。",
            ),
        )
        for text in variants:
            with self.subTest(text=text):
                result = self.lint(text)
                self.assertEqual(result["decision"], "fail", result["findings"])
                self.assertTrue(
                    any(f["code"] == "appearance_change_terms" for f in result["findings"]),
                    result["findings"],
                )

    def test_non_template_action_with_visible_presentation_passes(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：她轻轻侧过脸再看向镜头，肩颈、领口、表情和手部整理发丝的动作清楚可见。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertFalse(any(f["code"] == "invalid_action_template" for f in result["findings"]), result["findings"])
        self.assertFalse(any(f["code"] == "missing_action_adapted_presentation" for f in result["findings"]), result["findings"])

    def test_missing_action_adapted_presentation_warns(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：她自然移动。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "missing_action_adapted_presentation" for f in result["findings"]), result["findings"])

    def test_other_person_handheld_camera_fails(self):
        text = GOOD_PROMPT.replace(
            VIDEO_CONSTRAINT_PROMPT,
            "视频约束：他人手持拍摄，单一连续膝盖以上中景，呈现穿搭。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "other_handheld_camera_terms" for f in result["findings"]), result["findings"])

    def test_generic_handheld_camera_fails(self):
        text = GOOD_PROMPT.replace(
            VIDEO_CONSTRAINT_PROMPT,
            "视频约束：手持镜头，单一连续膝盖以上中景，呈现穿搭。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "other_handheld_camera_terms" for f in result["findings"]), result["findings"])

    def test_missing_fixed_camera_relation_fails(self):
        text = GOOD_PROMPT.replace(
            VIDEO_CONSTRAINT_PROMPT,
            "视频约束：单一连续膝盖以上中景，人物居中，脚部位于画外。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "missing_fixed_camera_relation" for f in result["findings"]), result["findings"])

    def test_multiple_camera_relations_fail(self):
        text = GOOD_PROMPT.replace(
            VIDEO_CONSTRAINT_PROMPT,
            "视频约束：固定拍摄和他人手持拍摄同时使用，单一连续膝盖以上中景，呈现穿搭。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "multiple_camera_relations" for f in result["findings"]), result["findings"])

    def test_missing_fixed_shooting_format_fails(self):
        text = GOOD_PROMPT.replace(
            VIDEO_CONSTRAINT_PROMPT,
            "视频约束：固定拍摄，膝盖以上中景，人物居中，脚部位于画外。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "missing_fixed_shooting_format" for f in result["findings"]), result["findings"])

    def test_camera_relation_in_person_action_fails(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：固定拍摄，人物自然转身展示穿搭，腰线清楚。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "camera_relation_in_person_action" for f in result["findings"]), result["findings"])

    def test_missing_required_section_fails(self):
        result = self.lint(GOOD_PROMPT.replace(PERSON_ACTION_PROMPT, ""))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_sections" for f in result["findings"]), result["findings"])

    def test_removed_pose_camera_section_fails(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "姿态镜头：固定拍摄，竖屏中近景。人物动作：固定拍摄，人物自然转身展示穿搭。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "unexpected_sections" for f in result["findings"]), result["findings"])

    def test_conditional_person_template_fails(self):
        text = GOOD_PROMPT.replace(
            PERSON_PROMPT,
            "人物：以 @图1 中的人物作为身份依据；若 @图1 是多视角角色参考图，以左下大脸为主要身份依据。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "conditional_or_placeholder_terms" for f in result["findings"]), result["findings"])

    def test_placeholder_ellipsis_fails(self):
        result = self.lint(GOOD_PROMPT.replace("穿搭：黑色合体上衣搭配高腰直筒短裙，上衣采用哑光面料并呈现清晰腰线，短裙版型全程一致。", "穿搭：..."))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "conditional_or_placeholder_terms" for f in result["findings"]), result["findings"])

    def test_camera_mode_conflict_fails(self):
        result = self.lint(GOOD_PROMPT + "拍摄方式为固定手机机位，带轻微手持感。")
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "mixed_camera_relation" for f in result["findings"]), result["findings"])

    def test_prompt_explicit_duration_fails(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：约 6 秒内她原地从侧身转向镜头，完成一次轻微重心切换后停在舞蹈节奏点。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "prompt_explicit_duration" for f in result["findings"]), result["findings"])

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

    def test_image_one_frame_anchor_fails(self):
        result = self.lint(GOOD_PROMPT + "人物：以 @图1 中的人物作为身份和画面锚点。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "internal_source_terms" for f in result["findings"]), result["findings"])

    def test_missing_video_constraint_fails(self):
        text = GOOD_PROMPT.replace(VIDEO_CONSTRAINT_PROMPT, "")
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_video_constraint" for f in result["findings"]), result["findings"])

    def test_invalid_video_constraint_fails(self):
        result = self.lint(GOOD_PROMPT.replace(VIDEO_CONSTRAINT_PROMPT, "视频约束：随意拍摄和自由构图。"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "invalid_video_constraint" for f in result["findings"]), result["findings"])

    def test_legacy_video_type_section_fails(self):
        result = self.lint(GOOD_PROMPT.replace(VIDEO_CONSTRAINT_PROMPT, "视频类型：人物展示；固定拍摄，单一连续中全景。"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_video_constraint" for f in result["findings"]), result["findings"])

    def test_runway_roaming_action_terms_fail(self):
        for action in (
            "T台走秀步态",
            "沿场景行走",
            "边走边拍",
            "走近走远",
            "沿通道慢走并走近镜头",
            "连续走三步后继续前行",
            "沿场景跟拍",
        ):
            with self.subTest(action=action):
                result = self.lint(GOOD_PROMPT.replace(PERSON_ACTION_PROMPT, f"人物动作：{action}，保持单一连续画面。"))
                self.assertEqual(result["decision"], "fail", result["findings"])
                self.assertTrue(
                    any(f["code"] == "runway_roaming_action_terms" for f in result["findings"]),
                    result["findings"],
                )

    def test_non_template_half_step_action_passes(self):
        result = self.lint(GOOD_PROMPT.replace(PERSON_ACTION_PROMPT, "人物动作：原地转向镜头并向侧前方调整半步，腰线清楚，保持单一连续画面。"))
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertFalse(any(f["code"] == "invalid_action_template" for f in result["findings"]), result["findings"])

    def test_out_of_frame_action_terms_fail(self):
        result = self.lint(GOOD_PROMPT.replace(PERSON_ACTION_PROMPT, "人物动作：自然展示穿搭，最后走出画面。"))
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "out_of_frame_action_terms" for f in result["findings"]), result["findings"])

    def test_unmapped_video_constraint_fails(self):
        result = self.lint(GOOD_PROMPT.replace(VIDEO_CONSTRAINT_PROMPT, "视频约束：走路回头，自由跟拍。"))
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "invalid_video_constraint" for f in result["findings"]), result["findings"])

    def test_image_one_clothing_anchor_fails(self):
        result = self.lint(GOOD_PROMPT + "人物：以 @图1 中的人物和穿搭作为身份、五官、发型、姿态、穿搭和稳定身材比例依据。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "image_one_clothing_anchor" for f in result["findings"]), result["findings"])

    def test_long_negative_style_list_warns(self):
        text = GOOD_PROMPT.replace(
            OTHER_PROMPT,
            "其他：皮肤真实，不要刻意磨皮美化，写实摄影风格，真实人物质感，自然光影，不夸张，不塑料感，不磨皮，不网红滤镜，不过度锐化，不AI感，不生成拼图、分屏、多格或多姿势拼贴。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "long_negative_style_list" for f in result["findings"]), result["findings"])

    def test_template_action_stack_warns(self):
        result = self.lint(GOOD_PROMPT + "腰线停顿，原地转身，挑眉，抿唇，玻璃连廊，轻舞律动。")
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "template_action_stack" for f in result["findings"]), result["findings"])

    def test_overdirected_timeline_warns(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：第 1 个动作侧身站定，第 2 个动作原地转身，第 3 个动作整理衣摆，第 4 个动作肩胯律动，第 5 个动作抬眼，第 6 个动作停住。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "overdirected_timeline" for f in result["findings"]), result["findings"])

    def test_overchoreographed_sequence_warns(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：她先侧身站定，随后抬起右手，然后左脚向前，再转动肩部，最后移动视线看向镜头。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "overchoreographed_action" for f in result["findings"]), result["findings"])

    def test_body_part_path_stack_warns(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：左手整理衣摆，右手扶腰，左脚承重，右脚轻点，肩部转动，视线移向镜头。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "overchoreographed_action" for f in result["findings"]), result["findings"])

    def test_goal_oriented_action_prompt_passes_without_choreography_warning(self):
        result = self.lint(GOOD_PROMPT)
        self.assertFalse(any(f["code"] == "overchoreographed_action" for f in result["findings"]), result["findings"])

    def test_generation_ai_meta_instruction_fails(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：人物自然展示穿搭，具体动作衔接、视线、表情与结尾由视频生成 AI 根据音乐与场景自然发挥。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "internal_source_terms" for f in result["findings"]), result["findings"])

    def test_cliche_stable_ending_warns(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：她从侧身转向镜头，完成一次轻微重心切换后停住，最后保持稳定构图自然收束。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "cliche_stable_ending" for f in result["findings"]), result["findings"])

    def test_cliche_clearest_moment_ending_warns(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：她从侧身转向镜头，最后卡在腰线最清楚的一刻。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "cliche_stable_ending" for f in result["findings"]), result["findings"])

    def test_mixed_camera_relation_fails(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：固定机位竖屏中近景，镜头略低于胸口，带轻微手持感，人物原地转身时镜头后退并推近保持构图。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "mixed_camera_relation" for f in result["findings"]), result["findings"])

    def test_mirror_selfie_fails_as_self_held_camera(self):
        result = self.lint(GOOD_PROMPT + "镜前自拍，镜中手机，试衣镜前转身，镜面反射。")
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "self_held_camera_terms" for f in result["findings"]), result["findings"])

    def test_arm_extended_selfie_fails_as_self_held_camera(self):
        result = self.lint(GOOD_PROMPT + "手臂伸出持机，伸出自拍。")
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "self_held_camera_terms" for f in result["findings"]), result["findings"])

    def test_visible_recording_device_terms_fail(self):
        text = GOOD_PROMPT.replace(
            PERSON_ACTION_PROMPT,
            "人物动作：手机被架在长椅上，固定竖屏中景，她走近后伸手取回手机。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "visible_recording_device_terms" for f in result["findings"]), result["findings"])


if __name__ == "__main__":
    unittest.main()
