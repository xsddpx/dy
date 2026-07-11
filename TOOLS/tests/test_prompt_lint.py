import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "prompt_lint.py"
SPEC = importlib.util.spec_from_file_location("prompt_lint", SCRIPT)
PROMPT_LINT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROMPT_LINT)


PERSON_PROMPT = (
    "人物：@图1 是同一位成年女性的多视角、多表情角色参考图，不是多人合照；"
    "以 @图1 中左下大脸和正面脸为主要身份依据，特别保持五官比例、脸型、眼神、鼻唇结构、发型分线和自然神态；"
    "以 @图1 中正面、侧面和背面全身图为稳定身材依据，特别保持上身体量、胸部体量比例、纤细腰线、腰胯比例和整体 S 型曲线。"
    "侧面、背面和表情小图只用于辅助保持发型、脸型、身材比例和整体气质。画面中只出现这一位成年女性。"
)

POSE_PROMPT = (
    "姿态镜头：固定拍摄，竖屏中近景，镜头略高于腰部并保持位置不变，裁切从头顶到大腿上段；"
    "她以松弛妩媚的状态完成自然转身展示，修身剪裁和高腰半裙让上身轮廓、清晰腰线与腰胯比例在连续动作中自然可读。"
)

ANIMATION_PROMPT = (
    "整体动画：保持单一连续固定镜头，以自然转身展示为主要动作目标，人物松弛妩媚且身体保持流动感，"
    "穿搭轮廓和腰线在动作中持续可读，发丝和裙摆随身体运动自然摆动，人物始终留在画面内。"
)

GOOD_PROMPT = (
    PERSON_PROMPT
    + "视频类型：穿搭展示；次类型：生活场景剧情；固定拍摄一条出门穿搭短视频。"
    + "穿搭：黑色修身上衣搭配高腰半裙，上衣贴合上身并露出清晰腰线，半裙包覆腰胯并停在膝上。"
    + POSE_PROMPT
    + "环境：现代酒店窗边，柔和窗光、浅色墙面和干净木地板，背景有衣架与小桌，空间透视清楚。"
    + ANIMATION_PROMPT
    + "背景音乐：轻柔电子节拍，节奏清晰。"
    + "其他：写实摄影风格，真实人物质感，自然光影，真实皮肤纹理，真实面部结构，真实头发丝细节，真实服装材质，符合物理规律的光照和阴影，自然景深，真实镜头质感，真实环境透视，真实色彩。穿搭轮廓清晰，腰线可见，构图稳定，单一连续完整竖屏画面，人物和环境保持同一时空与稳定透视。"
)

class PromptLintFlowTest(unittest.TestCase):
    def lint(self, text, route="anna", channel="auto"):
        return PROMPT_LINT.lint_text(text, Path("prompt.txt"), route, channel)

    def test_auto_anna_with_eight_section_prompt_passes(self):
        result = self.lint(GOOD_PROMPT)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertEqual(result["route"], "anna")
        self.assertEqual(result["channel"], "auto")
        self.assertEqual(result["mode"], "fast")

    def test_person_section_missing_fixed_anchors_fails(self):
        text = GOOD_PROMPT.replace(PERSON_PROMPT, "人物：@图1 是同一位成年女性。")
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "missing_person_anchors" for f in result["findings"]), result["findings"])

    def test_extra_expression_section_fails(self):
        text = GOOD_PROMPT.replace("整体动画：", "表情节奏：自然微笑。整体动画：")
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "unexpected_sections" for f in result["findings"]), result["findings"])

    def test_duplicate_required_section_fails(self):
        result = self.lint(GOOD_PROMPT + "环境：重复环境段。")
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "duplicate_sections" for f in result["findings"]), result["findings"])

    def test_standalone_sellpoint_section_fails(self):
        text = GOOD_PROMPT.replace(
            "整体动画：",
            "卖点与建议：上身轮廓和腰线清楚。整体动画：",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "standalone_sellpoint_section" for f in result["findings"]), result["findings"])

    def test_legacy_standalone_sellpoint_lock_section_fails(self):
        text = GOOD_PROMPT.replace(
            "整体动画：",
            "卖点与锁定：上身轮廓和腰线清楚。整体动画：",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "standalone_sellpoint_section" for f in result["findings"]), result["findings"])

    def test_derive_fast_copies_grid_prompt(self):
        self.assertEqual(PROMPT_LINT.derive_prompt(GOOD_PROMPT, "fast"), GOOD_PROMPT + "\n")

    def test_derive_main_writes_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "grid-prompt.txt"
            out = Path(tmp) / "vid-prompt-v1.txt"
            source.write_text(GOOD_PROMPT, encoding="utf-8")
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = PROMPT_LINT.main(["derive", str(source), "--mode", "fast", "--out", str(out)])
            self.assertEqual(code, 0, stdout.getvalue())
            self.assertEqual(out.read_text(encoding="utf-8"), GOOD_PROMPT + "\n")

    def test_top_level_help_mentions_derive_and_legacy_lint(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = PROMPT_LINT.main(["--help"])
        help_text = stdout.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("derive", help_text)
        self.assertIn("lint", help_text)
        self.assertIn("python3 TOOLS/prompt_lint.py derive", help_text)
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

    def test_closeup_presentation_without_full_body_passes(self):
        text = GOOD_PROMPT.replace(
            POSE_PROMPT,
            "姿态镜头：固定拍摄，竖屏脸侧近景，镜头从脸部裁到胸口上方并保持不变；她随轻缓动画侧过脸再看向镜头，肩颈、领口、表情和手部整理发丝的动作清楚可见。",
        ).replace(
            ANIMATION_PROMPT,
            "整体动画：单一连续固定镜头，她轻轻侧过脸再看向镜头，手部整理一次发丝，镜头保持稳定近景构图。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertFalse(any(f["code"] == "missing_animation_adapted_presentation" for f in result["findings"]), result["findings"])

    def test_missing_animation_adapted_presentation_warns(self):
        text = GOOD_PROMPT.replace(
            POSE_PROMPT,
            "姿态镜头：固定拍摄，竖屏近景，镜头保持稳定，她随动画自然移动。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "missing_animation_adapted_presentation" for f in result["findings"]), result["findings"])

    def test_other_person_handheld_camera_fails(self):
        text = GOOD_PROMPT.replace(
            POSE_PROMPT,
            "姿态镜头：他人手持拍摄，竖屏中近景，镜头略高于腰部；她从侧身转向镜头后停住半拍，上身轮廓和腰线清楚可见。",
        ).replace(
            "固定拍摄一条出门穿搭短视频",
            "他人手持拍摄一条出门穿搭短视频",
        ).replace(
            ANIMATION_PROMPT,
            "整体动画：单一连续他人手持镜头，她从侧身转向镜头后完成一次轻微重心切换，摄影者保持稳定中近景构图。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "other_handheld_camera_terms" for f in result["findings"]), result["findings"])

    def test_generic_handheld_camera_fails(self):
        text = GOOD_PROMPT.replace(
            POSE_PROMPT,
            "姿态镜头：手持镜头，竖屏中近景，人物自然转身展示穿搭。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "other_handheld_camera_terms" for f in result["findings"]), result["findings"])

    def test_missing_allowed_camera_relation_fails(self):
        text = GOOD_PROMPT.replace(
            POSE_PROMPT,
            "姿态镜头：竖屏中近景，镜头略高于腰部；她从侧身转向镜头后停住半拍，上身轮廓和腰线清楚可见。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "missing_allowed_camera_relation" for f in result["findings"]), result["findings"])

    def test_multiple_camera_relations_fail(self):
        text = GOOD_PROMPT.replace(
            POSE_PROMPT,
            "姿态镜头：固定拍摄和他人手持拍摄同时使用，竖屏中近景；她从侧身转向镜头后停住半拍，上身轮廓和腰线清楚可见。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "multiple_camera_relations" for f in result["findings"]), result["findings"])

    def test_missing_required_section_fails(self):
        result = self.lint(GOOD_PROMPT.replace(ANIMATION_PROMPT, ""))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_sections" for f in result["findings"]), result["findings"])

    def test_inline_label_mention_does_not_count_as_section(self):
        text = GOOD_PROMPT.replace(
            ANIMATION_PROMPT,
            "",
        ).replace(
            POSE_PROMPT,
            "姿态镜头：固定拍摄，竖屏中近景，镜头略高于胸口并保持角度不变；动作承接整体动画：转向镜头后停住半拍。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_sections" for f in result["findings"]), result["findings"])

    def test_conditional_person_template_fails(self):
        text = GOOD_PROMPT.replace(
            PERSON_PROMPT,
            "人物：以 @图1 中的人物作为身份依据；若 @图1 是多视角角色参考图，以左下大脸为主要身份依据。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "conditional_or_placeholder_terms" for f in result["findings"]), result["findings"])

    def test_placeholder_ellipsis_fails(self):
        result = self.lint(GOOD_PROMPT.replace("穿搭：黑色修身上衣搭配高腰半裙，上衣贴合上身并露出清晰腰线，半裙包覆腰胯并停在膝上。", "穿搭：..."))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "conditional_or_placeholder_terms" for f in result["findings"]), result["findings"])

    def test_camera_mode_conflict_fails(self):
        result = self.lint(GOOD_PROMPT + "拍摄方式为固定手机机位，带轻微手持感。")
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "mixed_camera_relation" for f in result["findings"]), result["findings"])

    def test_prompt_explicit_duration_fails(self):
        text = GOOD_PROMPT.replace(
            ANIMATION_PROMPT,
            "整体动画：约 6 秒单一连续固定镜头，她原地从侧身转向镜头，完成一次轻微重心切换后停在舞蹈节奏点。",
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

    def test_missing_video_type_fails(self):
        text = GOOD_PROMPT.replace("视频类型：穿搭展示；次类型：生活场景剧情；固定拍摄一条出门穿搭短视频。", "")
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "missing_video_type" for f in result["findings"]), result["findings"])

    def test_invalid_video_type_fails(self):
        result = self.lint(GOOD_PROMPT.replace("视频类型：穿搭展示", "视频类型：随便展示"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "invalid_video_type" for f in result["findings"]), result["findings"])

    def test_invalid_sub_video_type_fails(self):
        result = self.lint(GOOD_PROMPT.replace("次类型：生活场景剧情", "次类型：随便运动"))
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "invalid_video_type" for f in result["findings"]), result["findings"])

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
                result = self.lint(GOOD_PROMPT.replace(ANIMATION_PROMPT, f"整体动画：{action}，保持单一连续画面。"))
                self.assertEqual(result["decision"], "fail", result["findings"])
                self.assertTrue(
                    any(f["code"] == "runway_roaming_action_terms" for f in result["findings"]),
                    result["findings"],
                )

    def test_half_step_action_terms_pass(self):
        result = self.lint(GOOD_PROMPT.replace(ANIMATION_PROMPT, "整体动画：原地转向镜头并向侧前方调整半步，保持单一连续画面。"))
        self.assertEqual(result["decision"], "pass", result["findings"])

    def test_out_of_frame_action_terms_fail(self):
        result = self.lint(GOOD_PROMPT.replace(ANIMATION_PROMPT, "整体动画：自然展示穿搭，最后走出画面。"))
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "out_of_frame_action_terms" for f in result["findings"]), result["findings"])

    def test_walk_back_video_type_with_stationary_action_passes(self):
        result = self.lint(GOOD_PROMPT.replace("视频类型：穿搭展示", "视频类型：走路回头"))
        self.assertEqual(result["decision"], "pass", result["findings"])

    def test_image_one_clothing_anchor_fails(self):
        result = self.lint(GOOD_PROMPT + "人物：以 @图1 中的人物和穿搭作为身份、五官、发型、姿态、穿搭和稳定身材比例依据。")
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "image_one_clothing_anchor" for f in result["findings"]), result["findings"])

    def test_long_negative_style_list_warns(self):
        text = GOOD_PROMPT.replace(
            "其他：写实摄影风格，真实人物质感，自然光影，真实皮肤纹理，真实面部结构，真实头发丝细节，真实服装材质，符合物理规律的光照和阴影，自然景深，真实镜头质感，真实环境透视，真实色彩。穿搭轮廓清晰，腰线可见，构图稳定，单一连续完整竖屏画面，人物和环境保持同一时空与稳定透视。",
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
            ANIMATION_PROMPT,
            "整体动画：第 1 个动作侧身站定，第 2 个动作原地转身，第 3 个动作整理衣摆，第 4 个动作肩胯律动，第 5 个动作抬眼，第 6 个动作停住。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "overdirected_timeline" for f in result["findings"]), result["findings"])

    def test_overchoreographed_sequence_warns(self):
        text = GOOD_PROMPT.replace(
            ANIMATION_PROMPT,
            "整体动画：她先侧身站定，随后抬起右手，然后左脚向前，再转动肩部，最后移动视线看向镜头。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "overchoreographed_action" for f in result["findings"]), result["findings"])

    def test_body_part_path_stack_warns(self):
        text = GOOD_PROMPT.replace(
            ANIMATION_PROMPT,
            "整体动画：左手整理衣摆，右手扶腰，左脚承重，右脚轻点，肩部转动，视线移向镜头。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "overchoreographed_action" for f in result["findings"]), result["findings"])

    def test_goal_oriented_action_prompt_passes_without_choreography_warning(self):
        result = self.lint(GOOD_PROMPT)
        self.assertFalse(any(f["code"] == "overchoreographed_action" for f in result["findings"]), result["findings"])

    def test_generation_ai_meta_instruction_fails(self):
        text = GOOD_PROMPT.replace(
            ANIMATION_PROMPT,
            "整体动画：人物自然展示穿搭，具体动作衔接、视线、表情与结尾由视频生成 AI 根据音乐与场景自然发挥。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail", result["findings"])
        self.assertTrue(any(f["code"] == "internal_source_terms" for f in result["findings"]), result["findings"])

    def test_cliche_stable_ending_warns(self):
        text = GOOD_PROMPT.replace(
            ANIMATION_PROMPT,
            "整体动画：单一连续画面，她从侧身转向镜头，完成一次轻微重心切换后停住，最后保持稳定构图自然收束。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "cliche_stable_ending" for f in result["findings"]), result["findings"])

    def test_cliche_clearest_moment_ending_warns(self):
        text = GOOD_PROMPT.replace(
            ANIMATION_PROMPT,
            "整体动画：单一连续画面，她从侧身转向镜头，最后卡在腰线最清楚的一刻。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "pass", result["findings"])
        self.assertTrue(any(f["code"] == "cliche_stable_ending" for f in result["findings"]), result["findings"])

    def test_mixed_camera_relation_fails(self):
        text = GOOD_PROMPT.replace(
            POSE_PROMPT,
            "姿态镜头：固定机位竖屏中近景，镜头略低于胸口，带轻微手持感，人物原地转身时镜头后退并推近保持构图。",
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
            POSE_PROMPT,
            "姿态镜头：手机被架在长椅上，固定竖屏中景，她走近后伸手取回手机。",
        )
        result = self.lint(text)
        self.assertEqual(result["decision"], "fail")
        self.assertTrue(any(f["code"] == "visible_recording_device_terms" for f in result["findings"]), result["findings"])


if __name__ == "__main__":
    unittest.main()
