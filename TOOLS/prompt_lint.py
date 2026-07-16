#!/usr/bin/env python3
"""Lint and derive final prompts for the anna auto workflow."""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


def add(findings, severity, code, message):
    findings.append({"severity": severity, "code": code, "message": message})


FORBIDDEN_BODY_TERMS = [
    "大胸",
    "胸部大",
    "巨乳",
    "爆乳",
    "乳沟",
    "屁股大",
    "大屁股",
    "撅屁股",
    "擦边",
    "勾引",
]

TNS_STACKING_TERMS = [
    "胸部",
    "上围",
    "饱满",
    "丰满",
    "臀部",
    "腰胯",
    "腰臀",
    "体量",
    "S 型",
    "沙漏",
    "包臀",
    "迷你",
    "抹胸",
    "无肩带",
    "低腰",
    "紧身",
    "极细肩带",
    "低圆领",
    "低弧形",
    "低方领",
]

TNS_RISK_SECTION_LABELS = ("穿搭", "人物动作", "其他")
APPEARANCE_SECTION_LABELS = ("人物", "穿搭", "人物动作", "其他")
APPEARANCE_CHANGE_RE = re.compile(
    r"(?:服装|穿搭|上衣|内搭|外套|下装|短裙|短裤|长裤|连衣裙|颜色|领型|袖型|发型|头发)"
    r".{0,12}(?:变成|变为|换成|转为|逐渐变|更换|改变)"
)

UNSUPPORTED_TERMS = [
    "附件",
    "节点",
    "模型参数",
    "结果数",
]

REFERENCE_MODE_WARDROBE_IMAGE = "wardrobe-image"
REFERENCE_MODES = (REFERENCE_MODE_WARDROBE_IMAGE,)

WARDROBE_IMAGE_ANCHOR = (
    "@图2 是本次选中的衣柜人台商品图，只用于锁定整套服装的组件、颜色、版型、"
    "领口或肩带、层次、开合、腰线、裙裤轮廓、长度、图案、面料和袜类结构；"
    "服装自然贴合 @图1 人物，不采用 @图2 的人台、姿势或背景。"
)

REQUIRED_SECTION_LABELS = [
    "人物",
    "视频约束",
    "穿搭",
    "环境",
    "人物动作",
    "背景音乐",
    "其他",
]

PERSON_REQUIRED_TERMS = [
    "同一位成年女性",
    "多视角",
    "多表情角色参考图",
    "不是多人合照",
    "脸部严格参考左下角大脸",
    "身材严格参考正面、侧面和背面全身图",
    "脸部身份与身材一致",
    "画面中只出现这一位成年女性",
]

STANDALONE_SELLPOINT_LABELS = [
    "卖点与建议",
    "卖点与锁定",
]

ACTION_ADAPTED_PRESENTATION_TERMS = [
    "脸部",
    "表情",
    "视线",
    "肩颈",
    "领口",
    "上身比例",
    "上身轮廓",
    "服装轮廓",
    "穿搭轮廓",
    "腰线",
    "整体身形",
    "手部",
    "步态",
    "腿部",
    "裙摆",
    "发丝",
]

FIXED_ENVIRONMENT_TEMPLATES = {
    "wardrobe-image-01": "@图3 是本次随机选中的固定墙面环境；人物贴墙站立，墙上呈现轻微自然投影。",
}

FIXED_ACTION_TEMPLATES = {
    "01": "人物贴近墙面从正面站姿开始，肩背自然靠墙；全身沿墙面原地同步向左转至清晰的侧身姿态，一侧肩背始终轻靠墙面，侧身短暂停留后再沿墙面转回正面。转身过程中在适当时机自然融入撩头发、整理衣服、看向镜头、表情变化、叉腰、手放胸前等动作，动作范围集中在墙面前方半步内，墙上轻微投影随动作同步变化。转身幅度明确，动作舒展流畅、衔接自然，整体呈现甜美亲切、自然有韵律的状态。",
    "02": "人物贴近墙面从正面自然站姿开始，肩背自然靠墙；在原地摆出一个常见的女性拍照姿态，短暂停留后恢复正面自然站姿，随后面向镜头比心或比出 V 手势。动作过程中可自然融入撩头发、视线移动和表情变化，人物位置保持稳定，墙上轻微投影随动作同步变化。整体动作清晰流畅、衔接自然。",
    "03": "人物贴近墙面从半侧身站姿开始，一侧肩背轻靠墙面；保持半侧身状态，缓慢打开肩颈转向镜头，短暂停留后轻轻偏头。人物位置保持稳定，动作范围集中在墙面前方半步内，墙上轻微投影随动作同步变化。整体动作轻柔流畅、衔接自然。",
    "04": "人物贴近墙面从正面自然站姿开始，双手自然交叠在腰前；随后一只手抬起整理发丝并微微侧身，另一只手留在腰侧，最后自然看向镜头。人物位置保持稳定，动作范围集中在墙面前方半步内，墙上轻微投影随动作同步变化。整体动作清晰流畅、衔接自然。",
}

FIXED_VIDEO_CONSTRAINT_TEMPLATES = {
    "01": "固定拍摄，单一连续膝盖以上中景；机位高度大致与人物胸部齐平；人物位于画面中央并贴近墙面，动作范围保持在墙前半步内；头顶保留适度空间，双肩、上身、腰线、腰胯与膝上区域完整清晰，画面下缘稳定落在膝盖附近，脚部始终位于画外；机位、视角、景别和构图全程保持不变。",
}

INTERNAL_SOURCE_TERMS = [
    "grid-prompt.txt",
    "reference-grid",
    "参考宫格",
    "参考类型识别",
    "主类型=",
    "次类型=",
    "判断依据=",
    "同时吸收",
    "融合",
    "吸收",
    "吸收grid",
    "吸收 grid",
    "根据grid",
    "根据 grid",
    "根据文档",
    "上述分析",
    "文件",
    "流程",
    "流程节点",
    "画面锚点",
    "身材表达使用艺术化穿搭语言",
    "艺术化穿搭语言：",
    "视频类型为",
    "视频生成 AI",
    "视频生成AI",
    "生成 AI 自由发挥",
    "生成AI自由发挥",
    "由 AI 自主完成",
    "由AI自主完成",
    "由视频生成 AI",
    "由视频生成AI",
]

COMPLIANCE_OR_EXPLANATION_TERMS = [
    "合规",
    "平台可发布",
    "审核",
    "未成年",
    "裸体",
    "低俗",
    "原视频人物身份",
    "真人脸",
    "账号标识",
    "字幕水印",
    "品牌商标",
    "专有 IP",
    "专有IP",
]

CONDITIONAL_OR_PLACEHOLDER_TERMS = [
    "若 @图1",
    "若@图1",
    "如果 @图1",
    "如果@图1",
    "如 @图1",
    "如@图1",
    "...",
    "……",
    "<",
    ">",
]

NON_MUSIC_SOUND_TERMS = [
    "环境声",
    "人声",
    "脚步声",
    "衣料声",
    "镜头声",
    "口播",
    "对白",
    "喘息",
    "音效",
]
SOUND_NEGATION_TERMS = ["不出现", "不要", "不含", "杜绝", "禁止", "没有"]
SOUND_SENTENCE_BOUNDARIES = "。！？!?；;\n"
SECTION_RE_TEMPLATE = r"(^|[。！？!?；;\n])\s*({label})："
SECTION_LABEL_SCAN_RE = re.compile(r"(^|[。！？!?；;\n])\s*([\u4e00-\u9fffA-Za-z0-9_/-]{1,16})：")
ALLOWED_INLINE_LABELS = set()
EXPLICIT_PROMPT_DURATION_RE = re.compile(
    r"(约\s*)?([0-9一二三四五六七八九十]+)\s*([-~到至]\s*[0-9一二三四五六七八九十]+)?\s*秒"
)

NEGATIVE_STYLE_TERMS = [
    "不要",
    "不生成",
    "不出现",
    "不含",
    "不夸张",
    "不塑料感",
    "不磨皮",
    "不网红滤镜",
    "不过度锐化",
    "不AI感",
    "禁止",
    "杜绝",
]

TEMPLATE_ACTION_TERMS = [
    "腰线停顿",
    "原地转身",
    "挑眉",
    "抿唇",
    "玻璃连廊",
    "轻舞律动",
]

ACTION_OVERLOAD_TERMS = [
    "整理",
    "扶",
    "转身",
    "轻舞",
    "摆胯",
    "低头",
    "抬眼",
    "回看",
]

ACTION_SEQUENCE_TERMS = [
    "先",
    "随后",
    "然后",
    "接着",
    "再",
    "最后",
]

BODY_PATH_TERMS = [
    "左手",
    "右手",
    "双手",
    "左脚",
    "右脚",
    "脚尖",
    "肩部",
    "肩胯",
    "髋部",
    "头部",
    "视线",
]

TIMELINE_MARKERS = [
    "第 1",
    "第 2",
    "第 3",
    "第 4",
    "第 5",
    "第 6",
    "第1",
    "第2",
    "第3",
    "第4",
    "第5",
    "第6",
    "前 1 秒",
    "最后 1 秒",
]

ENDING_CLICHE_TERMS = [
    "稳定收束",
    "自然收束",
    "稳定构图自然收束",
    "保持稳定构图",
    "最清楚的一刻",
    "卡在",
]

SELF_HELD_CAMERA_TERMS = [
    "自拍",
    "自己持机",
    "人物持机",
    "手机前置",
    "胸口持机",
    "脸侧持机",
    "腰侧持机",
    "腰侧斜向",
    "短自拍杆",
    "手臂伸出",
    "伸出持机",
    "手机放低",
    "取回手机",
]

FIXED_CAMERA_TERMS = [
    "固定机位",
    "固定拍摄",
    "固定镜头",
    "固定竖屏",
]

OTHER_HANDHELD_CAMERA_TERMS = [
    "他人手持",
    "朋友手持",
    "摄影者手持",
    "手持拍摄",
    "手持镜头",
    "手持感",
]

OUT_OF_FRAME_ACTION_TERMS = [
    "走出画面",
    "走出镜头",
    "走出取景范围",
    "离开画面",
    "离开镜头",
    "走到画外",
    "消失在画面",
    "消失在镜头",
    "出框",
    "出画",
]

RUNWAY_ROAMING_ACTION_TERMS = [
    "T 台走秀",
    "T台走秀",
    "模特走秀",
    "走秀步态",
    "猫步",
    "巡场",
    "沿场景行走",
    "边走边拍",
    "走近走远",
    "沿通道慢走",
    "沿通道行走",
    "沿连廊行走",
    "沿走廊行走",
    "沿步道行走",
    "走近镜头",
    "走向镜头",
    "连续走",
    "走两步",
    "走三步",
    "继续向前走",
    "继续前行",
    "全身跟拍",
    "行走跟拍",
    "沿场景跟拍",
    "后退跟拍",
]

VISIBLE_RECORDING_DEVICE_TERMS = [
    "架手机",
    "手机被",
    "手机架在",
    "手机被架",
    "被架在",
    "取回手机",
    "拿起手机结束",
    "手伸向手机",
    "靠近手机镜头",
    "前景手机",
    "底部手机",
    "手机前景",
    "支架",
    "三脚架",
]


def positive_sound_hits(text):
    hits = []
    for term in NON_MUSIC_SOUND_TERMS:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            boundary = max(text.rfind(mark, 0, index) for mark in SOUND_SENTENCE_BOUNDARIES)
            prefix = text[boundary + 1:index]
            if not any(negation in prefix for negation in SOUND_NEGATION_TERMS):
                hits.append(term)
                break
            start = index + len(term)
    return hits


def video_constraint_finding(text):
    constraint_text = section_content(text, "视频约束")
    if constraint_text is None:
        return "missing_video_constraint", "最终 vid prompt 缺少“视频约束：...”段"
    if fixed_template_id(constraint_text, FIXED_VIDEO_CONSTRAINT_TEMPLATES) is None:
        return "invalid_video_constraint", "视频约束必须完整使用固定构图模板 01"
    return None, None


def section_spans(text, labels):
    positions = []
    missing = []
    for label in labels:
        matches = []
        for actual_label in [label]:
            match = re.search(SECTION_RE_TEMPLATE.format(label=re.escape(actual_label)), text)
            if match:
                matches.append((match.start(2), actual_label))
        if matches:
            start, actual_label = min(matches, key=lambda item: item[0])
            positions.append((label, start, actual_label))
        else:
            missing.append(label)
    spans = []
    for index, (label, start, actual_label) in enumerate(positions):
        content_start = start + len(actual_label) + 1
        content_end = positions[index + 1][1] if index + 1 < len(positions) else len(text)
        spans.append((label, start, content_start, content_end))
    return positions, missing, spans


def section_finding(text, labels=None, section_name="七段标签"):
    labels = labels or REQUIRED_SECTION_LABELS
    positions, missing, spans = section_spans(text, labels)
    if missing:
        return "missing_sections", f"最终 prompt 缺少{section_name}：{', '.join(missing)}"
    duplicates = [
        label
        for label in labels
        if len(list(re.finditer(SECTION_RE_TEMPLATE.format(label=re.escape(label)), text))) > 1
    ]
    if duplicates:
        return "duplicate_sections", f"最终 prompt 的七段标签各保留一次：{', '.join(duplicates)}"
    detected_labels = [match.group(2) for match in SECTION_LABEL_SCAN_RE.finditer(text)]
    unexpected = [
        label
        for label in detected_labels
        if label not in labels and label not in ALLOWED_INLINE_LABELS
    ]
    if unexpected:
        return "unexpected_sections", f"最终 prompt 只使用固定七段标签：{', '.join(dict.fromkeys(unexpected))}"
    out_of_order = [
        labels[index]
        for index in range(1, len(positions))
        if positions[index][1] < positions[index - 1][1]
    ]
    if out_of_order:
        return "section_order", f"最终 prompt {section_name}顺序错误：{', '.join(out_of_order)}"
    empty = []
    for label, _, content_start, content_end in spans:
        if not text[content_start:content_end].strip(" \t\r\n。；;"):
            empty.append(label)
    if empty:
        return "empty_sections", f"最终 prompt 段落为空：{', '.join(empty)}"
    return None, None


def section_content(text, label):
    _, missing, spans = section_spans(text, REQUIRED_SECTION_LABELS)
    if label in missing:
        return None
    for section_label, _, content_start, content_end in spans:
        if section_label == label:
            return text[content_start:content_end]
    return None


def reference_section_locations(text, reference):
    _, _, spans = section_spans(text, REQUIRED_SECTION_LABELS)
    locations = []
    for match in re.finditer(re.escape(reference), text):
        location = "段外文本"
        for section_label, _, content_start, content_end in spans:
            if content_start <= match.start() < content_end:
                location = section_label
                break
        locations.append(location)
    return locations


def image_one_clothing_conflict(text):
    compact = re.sub(r"\s+", "", text)
    patterns = [
        "@图1中的人物和穿搭作为",
        "@图1中人物和穿搭作为",
        "@图1中的穿搭作为",
        "@图1中穿搭作为",
        "@图1的穿搭作为",
    ]
    return [pattern for pattern in patterns if pattern in compact]


def section_text_or_empty(text, label):
    content = section_content(text, label)
    return content or ""


def fixed_template_id(content, templates):
    if content is None:
        return None
    normalized = re.sub(r"\s+", "", content)
    for template_id, template in templates.items():
        if normalized == re.sub(r"\s+", "", template):
            return template_id
    return None


def count_term_hits(text, terms):
    return [(term, text.count(term)) for term in terms if text.count(term)]


def add_prompt_style_findings(findings, text):
    other_text = section_text_or_empty(text, "其他")
    negative_hits = count_term_hits(other_text, NEGATIVE_STYLE_TERMS)
    negative_count = sum(count for _, count in negative_hits)
    if negative_count >= 6:
        add(
            findings,
            "warn",
            "long_negative_style_list",
            "其他段反向审美约束过长，优先改成短正向摄影约束",
        )

    template_hits = count_term_hits(text, TEMPLATE_ACTION_TERMS)
    if len(template_hits) >= 4:
        add(
            findings,
            "warn",
            "template_action_stack",
            "prompt 堆叠了多组近期常见模板动作，建议换成一个更明确的短视频主动作链",
        )

    person_action_text = section_text_or_empty(text, "人物动作")
    timeline_hits = count_term_hits(person_action_text, TIMELINE_MARKERS)
    if len(timeline_hits) >= 4:
        add(
            findings,
            "warn",
            "overdirected_timeline",
            "人物动作逐秒编排过细，建议保留一个连续主动作链",
        )

    if EXPLICIT_PROMPT_DURATION_RE.search(text):
        add(
            findings,
            "error",
            "prompt_explicit_duration",
            "prompt 正文聚焦可见画面，视频长度统一由 Dreamina --duration 参数控制",
        )

    action_text = section_text_or_empty(text, "人物动作")
    action_hits = count_term_hits(action_text, ACTION_OVERLOAD_TERMS)
    if len(action_hits) >= 6:
        add(
            findings,
            "warn",
            "action_overload",
            "人物动作包含过多动作方向，建议压到一个主动作链和一个节奏点",
        )

    sequence_count = sum(count for _, count in count_term_hits(action_text, ACTION_SEQUENCE_TERMS))
    body_path_hits = count_term_hits(action_text, BODY_PATH_TERMS)
    if sequence_count >= 4 or len(body_path_hits) >= 5:
        add(
            findings,
            "warn",
            "overchoreographed_action",
            "动作编排细节过多，建议删除分解动作，只保留主要动作目标、人物状态和画面结果",
        )

    ending_hits = count_term_hits(person_action_text, ENDING_CLICHE_TERMS)
    if ending_hits:
        add(
            findings,
            "warn",
            "cliche_stable_ending",
            "人物动作结尾不要固定写稳定收束、自然收束或卡在最清楚的一刻，优先保持自然动作节奏、小幅侧身状态或手臂自然回落状态",
        )

    compact = re.sub(r"\s+", "", text)
    has_fixed = any(term in compact for term in FIXED_CAMERA_TERMS)
    has_other_handheld = any(term in compact for term in OTHER_HANDHELD_CAMERA_TERMS)
    has_active_camera = any(term in compact for term in ("跟拍", "后退", "推近"))
    if has_fixed and (has_other_handheld or has_active_camera or "手持感" in compact):
        add(
            findings,
            "error",
            "mixed_camera_relation",
            "固定拍摄需在整段视频中保持机位、视角和构图关系不变",
        )


def lint_text(
    text,
    path,
    route="anna",
    channel="auto",
    reference_mode=REFERENCE_MODE_WARDROBE_IMAGE,
):
    findings = []
    if route != "anna":
        add(findings, "error", "unsupported_route", "dy 项目只支持 anna 路线")
    if channel != "auto":
        add(findings, "error", "unsupported_channel", "dy 项目只支持 auto 通道")
    if reference_mode not in REFERENCE_MODES:
        add(
            findings,
            "error",
            "unsupported_reference_mode",
            f"不支持的图片参考模式：{reference_mode}",
        )
    if "@图1" not in text:
        add(findings, "error", "missing_role_image", "auto/fast 视频 prompt 缺少 @图1 角色图身份引用或说明")
    if "@图2" not in text:
        add(findings, "error", "missing_wardrobe_image", "三图模式缺少 @图2 衣柜人台商品图引用")
    if "@图3" not in text:
        add(findings, "error", "missing_environment_image", "三图模式缺少 @图3 固定环境图引用")
    unsupported_hits = [term for term in UNSUPPORTED_TERMS if term in text]
    if unsupported_hits:
        add(findings, "error", "unsupported_terms", f"prompt 含本项目不接收的内部流程词：{', '.join(unsupported_hits)}")
    internal_source_hits = [term for term in INTERNAL_SOURCE_TERMS if term in text]
    if internal_source_hits:
        add(findings, "error", "internal_source_terms", f"prompt 含生成工具不可执行的内部来源词：{', '.join(internal_source_hits)}")
    compliance_hits = [term for term in COMPLIANCE_OR_EXPLANATION_TERMS if term in text]
    if compliance_hits:
        add(findings, "error", "compliance_or_explanation_terms", f"prompt 含合规说明、排除清单或平台解释词：{', '.join(compliance_hits)}")
    conditional_hits = [term for term in CONDITIONAL_OR_PLACEHOLDER_TERMS if term in text]
    if conditional_hits:
        add(findings, "error", "conditional_or_placeholder_terms", f"prompt 含条件分支或占位符：{', '.join(conditional_hits)}")
    visible_device_hits = [term for term in VISIBLE_RECORDING_DEVICE_TERMS if term in text]
    if visible_device_hits:
        add(findings, "error", "visible_recording_device_terms", f"prompt 可能导致拍摄设备入镜：{', '.join(visible_device_hits)}")
    self_held_hits = [term for term in SELF_HELD_CAMERA_TERMS if term in text]
    if self_held_hits:
        add(
            findings,
            "error",
            "self_held_camera_terms",
            f"prompt 只允许固定拍摄，人物不持机：{', '.join(self_held_hits)}",
        )
    other_handheld_hits = [term for term in OTHER_HANDHELD_CAMERA_TERMS if term in text]
    if other_handheld_hits:
        add(
            findings,
            "error",
            "other_handheld_camera_terms",
            f"prompt 只允许固定拍摄，不使用他人手持拍摄：{', '.join(other_handheld_hits)}",
        )
    out_of_frame_hits = [term for term in OUT_OF_FRAME_ACTION_TERMS if term in text]
    if out_of_frame_hits:
        add(
            findings,
            "error",
            "out_of_frame_action_terms",
            f"人物必须从开场到结尾始终留在画面内：{', '.join(out_of_frame_hits)}",
        )
    action_text = section_text_or_empty(text, "人物动作")
    runway_roaming_hits = [term for term in RUNWAY_ROAMING_ACTION_TERMS if term in action_text]
    if runway_roaming_hits:
        add(
            findings,
            "error",
            "runway_roaming_action_terms",
            f"人物动作以原地展示、生活化互动和半步内调整为主，删除持续巡场式行走：{', '.join(runway_roaming_hits)}",
        )
    standalone_sellpoint_hits = [
        label
        for label in STANDALONE_SELLPOINT_LABELS
        if re.search(SECTION_RE_TEMPLATE.format(label=re.escape(label)), text)
    ]
    if standalone_sellpoint_hits:
        add(
            findings,
            "error",
            "standalone_sellpoint_section",
            f"prompt 不再使用独立卖点段，请把内容并入人物动作：{', '.join(standalone_sellpoint_hits)}",
        )
    section_code, section_message = section_finding(text)
    if section_code:
        add(findings, "error", section_code, section_message)
    tns_section_hits = {}
    for label in TNS_RISK_SECTION_LABELS:
        content = section_content(text, label)
        if content is None:
            continue
        hits = [term for term in TNS_STACKING_TERMS if term in content]
        if hits:
            tns_section_hits[label] = hits
    if tns_section_hits:
        details = "; ".join(
            f"{label}：{', '.join(hits)}"
            for label, hits in tns_section_hits.items()
        )
        add(
            findings,
            "error",
            "tns_stacking_terms",
            f"人物身材强化与高风险服装词不进入最终 prompt：{details}",
        )
    appearance_change_sections = []
    for label in APPEARANCE_SECTION_LABELS:
        content = section_content(text, label)
        if content is not None and APPEARANCE_CHANGE_RE.search(content):
            appearance_change_sections.append(label)
    if appearance_change_sections:
        add(
            findings,
            "error",
            "appearance_change_terms",
            "人物与服装外观需全程一致，不写换装、变色或发型变化："
            + ", ".join(appearance_change_sections),
        )
    person_text = section_content(text, "人物")
    if person_text is not None:
        missing_person_terms = [term for term in PERSON_REQUIRED_TERMS if term not in person_text]
        if missing_person_terms:
            add(
                findings,
                "error",
                "missing_person_anchors",
                f"人物段需完整保留固定身份和身材锚点：{', '.join(missing_person_terms)}",
            )
    constraint_code, constraint_message = video_constraint_finding(text)
    if constraint_code:
        add(findings, "error", constraint_code, constraint_message)
    environment_text = section_content(text, "环境")
    expected_environment_template_id = "wardrobe-image-01"
    if (
        environment_text is not None
        and fixed_template_id(environment_text, FIXED_ENVIRONMENT_TEMPLATES)
        != expected_environment_template_id
    ):
        add(
            findings,
            "error",
            "invalid_environment_template",
            f"环境必须完整使用固定模板 {expected_environment_template_id}",
        )
    outfit_text = section_content(text, "穿搭")
    if reference_mode == REFERENCE_MODE_WARDROBE_IMAGE:
        image_two_conflicts = [
            location
            for location in reference_section_locations(text, "@图2")
            if location != "穿搭"
        ]
        image_three_conflicts = [
            location
            for location in reference_section_locations(text, "@图3")
            if location != "环境"
        ]
        if image_two_conflicts or image_three_conflicts:
            details = []
            if image_two_conflicts:
                details.append(
                    "@图2 仅用于穿搭段，冲突位置："
                    + ", ".join(dict.fromkeys(image_two_conflicts))
                )
            if image_three_conflicts:
                details.append(
                    "@图3 仅用于环境段，冲突位置："
                    + ", ".join(dict.fromkeys(image_three_conflicts))
                )
            add(
                findings,
                "error",
                "wardrobe_image_role_conflict",
                "衣柜图三图模式必须隔离人物、服装和环境角色；" + "；".join(details),
            )
        if outfit_text is None or WARDROBE_IMAGE_ANCHOR not in outfit_text:
            add(
                findings,
                "error",
                "missing_wardrobe_image_anchor",
                "衣柜图模式的穿搭段必须完整写明 @图2 的服装专用角色和人台隔离规则",
            )
    person_action_text = section_content(text, "人物动作")
    clothing_conflicts = image_one_clothing_conflict(text)
    if clothing_conflicts:
        add(findings, "error", "image_one_clothing_anchor", "@图1 只作为人物脸部和身材参考，auto/fast 不得把 @图1 穿搭作为依据")
    shooting_text = section_content(text, "视频约束")
    if shooting_text is not None:
        compact_shooting = re.sub(r"\s+", "", shooting_text)
        has_fixed = any(term in compact_shooting for term in FIXED_CAMERA_TERMS)
        has_other_handheld = any(term in compact_shooting for term in OTHER_HANDHELD_CAMERA_TERMS)
        if not has_fixed:
            add(
                findings,
                "error",
                "missing_fixed_camera_relation",
                "视频约束必须明确使用固定拍摄",
            )
        elif has_fixed and has_other_handheld:
            add(
                findings,
                "error",
                "multiple_camera_relations",
                "视频约束只能使用固定拍摄，不能同时写手持拍摄",
            )
        if "单一连续膝盖以上中景" not in compact_shooting:
            add(
                findings,
                "error",
                "missing_fixed_shooting_format",
                "视频约束必须使用单一连续膝盖以上中景，并保持脚部位于画外",
            )
    if person_action_text is not None:
        action_camera_hits = [
            term
            for term in FIXED_CAMERA_TERMS + OTHER_HANDHELD_CAMERA_TERMS
            if term in person_action_text
        ]
        if action_camera_hits:
            add(
                findings,
                "error",
                "camera_relation_in_person_action",
                f"拍摄方式、景别和构图只写入视频约束，人物动作不重复：{', '.join(action_camera_hits)}",
            )
    if person_action_text is not None and not any(term in person_action_text for term in ACTION_ADAPTED_PRESENTATION_TERMS):
        add(
            findings,
            "warn",
            "missing_action_adapted_presentation",
            "人物动作需写出膝盖以上中景可见的服装轮廓、上身比例、腰线或自然肢体表现",
        )
    forbidden_hits = [term for term in FORBIDDEN_BODY_TERMS if term in text]
    if forbidden_hits:
        add(findings, "error", "unsafe_body_terms", f"prompt 含直白身材或低俗词：{', '.join(forbidden_hits)}")
    non_music_sound_hits = positive_sound_hits(text)
    if non_music_sound_hits:
        add(findings, "error", "non_music_sound_terms", f"prompt 含音乐以外的声音：{', '.join(non_music_sound_hits)}")
    add_prompt_style_findings(findings, text)

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warn")
    infos = sum(1 for f in findings if f["severity"] == "info")
    return {
        "path": str(path),
        "route": "anna",
        "channel": "auto",
        "mode": "fast",
        "reference_mode": reference_mode,
        "bytes": len(text.encode("utf-8")),
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
        "decision": "fail" if errors else "pass",
        "findings": findings,
    }


def derive_prompt(text, mode):
    if mode == "fast":
        return text.rstrip() + "\n"
    raise ValueError(f"未知派生模式：{mode}")


def lint_derived_prompt(text, path, mode, reference_mode=REFERENCE_MODE_WARDROBE_IMAGE):
    return lint_text(text, path, reference_mode=reference_mode)


def build_derive_parser():
    parser = argparse.ArgumentParser(
        prog="prompt_lint.py derive",
        description="从 grid-prompt.txt 机械派生阶段 prompt。",
    )
    parser.add_argument("grid_prompt", help="模块 01 写出的 TEMP/RUN_ID/grid-prompt.txt")
    parser.add_argument("--mode", choices=["fast"], required=True)
    parser.add_argument(
        "--reference-mode",
        choices=REFERENCE_MODES,
        default=REFERENCE_MODE_WARDROBE_IMAGE,
        help="固定使用 wardrobe-image：人物+衣柜图+环境三图",
    )
    parser.add_argument("--out", required=True, help="派生 prompt 输出路径")
    return parser


def derive_main(argv):
    parser = build_derive_parser()
    args = parser.parse_args(argv)

    source = Path(args.grid_prompt).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    if not source.exists():
        print(json.dumps({"error": "grid-prompt 文件不存在", "missing": str(source)}, ensure_ascii=False), file=sys.stderr)
        return 2

    source_text = source.read_text(encoding="utf-8", errors="replace")
    source_lint = lint_text(source_text, source, reference_mode=args.reference_mode)
    if source_lint["decision"] != "pass":
        print(json.dumps({"decision": "fail", "source_lint": source_lint}, ensure_ascii=False, indent=2))
        return 1

    try:
        derived = derive_prompt(source_text, args.mode)
    except ValueError as exc:
        print(json.dumps({"decision": "fail", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    derived_lint = lint_derived_prompt(
        derived,
        out_path,
        args.mode,
        reference_mode=args.reference_mode,
    )
    if derived_lint["decision"] != "pass":
        print(json.dumps({"decision": "fail", "source_lint": source_lint, "derived_lint": derived_lint}, ensure_ascii=False, indent=2))
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(derived, encoding="utf-8")
    print(json.dumps({
        "decision": "pass",
        "mode": args.mode,
        "reference_mode": args.reference_mode,
        "source": str(source),
        "out": str(out_path),
        "source_lint": source_lint["decision"],
        "derived_lint": derived_lint["decision"],
    }, ensure_ascii=False, indent=2))
    return 0


def write_reports(results, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "report.json"
    report_md = out_dir / "report.md"
    report_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# TNS final prompt lint 报告",
        "",
        f"- 样本数：{len(results)}",
        f"- 通过：{sum(1 for r in results if r['decision'] == 'pass')}",
        f"- 失败：{sum(1 for r in results if r['decision'] == 'fail')}",
        "",
        "| 结论 | 路线 | 通道 | 视频模式 | 图片参考模式 | 错误数 | 文件 | 主要发现 |",
        "|---|---|---|---|---|---:|---|---|",
    ]
    for item in results:
        top = "; ".join(f["message"] for f in item["findings"][:4]) or "无"
        lines.append(
            f"| {item['decision']} | anna | auto | fast | {item['reference_mode']} | "
            f"{item['errors']} | {Path(item['path']).name} | {top} |"
        )
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_json, report_md


def build_lint_parser(prog="prompt_lint.py"):
    parser = argparse.ArgumentParser(
        prog=prog,
        description="检查 dy 项目的最终 prompt 是否满足 TNS 收敛硬门。",
    )
    parser.add_argument("prompts", nargs="+", help="最终 prompt 文本文件")
    parser.add_argument("--route", choices=["anna"], default="anna")
    parser.add_argument("--channel", choices=["auto"], default="auto")
    parser.add_argument(
        "--reference-mode",
        choices=REFERENCE_MODES,
        default=REFERENCE_MODE_WARDROBE_IMAGE,
    )
    parser.add_argument("--out-dir", default=None, help="输出目录，默认 TEMP/prompt-lint-runs/YYYYMMDD-HHMMSS")
    return parser


def lint_main(argv=None, prog="prompt_lint.py"):
    parser = build_lint_parser(prog)
    args = parser.parse_args(argv)

    files = [Path(p).expanduser().resolve() for p in args.prompts]
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        print(json.dumps({"error": "prompt 文件不存在", "missing": missing}, ensure_ascii=False), file=sys.stderr)
        return 2

    results = [
        lint_text(
            file.read_text(encoding="utf-8", errors="replace"),
            file,
            args.route,
            args.channel,
            args.reference_mode,
        )
        for file in files
    ]
    out_dir = Path(args.out_dir) if args.out_dir else Path.cwd() / "TEMP/prompt-lint-runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    report_json, report_md = write_reports(results, out_dir)
    print(json.dumps({
        "output_dir": str(out_dir),
        "report_json": str(report_json),
        "report_md": str(report_md),
        "total": len(results),
        "pass": sum(1 for r in results if r["decision"] == "pass"),
        "fail": sum(1 for r in results if r["decision"] == "fail"),
    }, ensure_ascii=False, indent=2))
    return 1 if any(r["decision"] == "fail" for r in results) else 0


def top_level_help():
    parser = argparse.ArgumentParser(
        prog="prompt_lint.py",
        description="检查和派生 dy 项目的最终 prompt。",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "子命令:\n"
            "  lint    检查最终 prompt；兼容旧式写法，省略 lint 也会进入 lint\n"
            "  derive  从 grid-prompt.txt 机械派生阶段 prompt\n"
            "\n"
            "常用:\n"
            "  python3 TOOLS/prompt_lint.py derive \"TEMP/$RUN_ID/grid-prompt.txt\" --mode fast --out \"TEMP/$RUN_ID/vid-prompt-v1.txt\"\n"
            "  python3 TOOLS/prompt_lint.py lint \"TEMP/$RUN_ID/vid-prompt-v1.txt\"\n"
            "  python3 TOOLS/prompt_lint.py \"TEMP/$RUN_ID/vid-prompt-v1.txt\"\n"
            "\n"
            "查看子命令参数:\n"
            "  python3 TOOLS/prompt_lint.py derive --help\n"
            "  python3 TOOLS/prompt_lint.py lint --help"
        ),
    )
    parser.add_argument("command", nargs="?", help="子命令：lint 或 derive；省略时按旧式 lint 处理")
    parser.print_help()
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {"-h", "--help"}:
        return top_level_help()
    if argv and argv[0] == "derive":
        return derive_main(argv[1:])
    if argv and argv[0] == "lint":
        return lint_main(argv[1:], prog="prompt_lint.py lint")
    return lint_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
