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

UNSUPPORTED_TERMS = [
    "@图2",
    "@图3",
    "附件",
    "节点",
    "模型参数",
    "结果数",
]

REQUIRED_SECTION_LABELS = [
    "人物",
    "视频类型",
    "穿搭",
    "姿态镜头",
    "环境",
    "卖点与锁定",
    "表情节奏",
    "整体动画",
    "背景音乐",
    "其他",
]

CHEST_SAFE_EXPRESSIONS = [
    "饱满的立体廓形",
    "高感知度的面料张力",
    "上身丰盈的沙漏型线条",
    "领口与上身轮廓清晰",
]

HIP_SAFE_EXPRESSIONS = [
    "腰胯比例明显",
    "臀胯轮廓自然凸显",
    "高腰线与下装包裹出稳定曲线",
    "古典雕塑般的 S 形动态",
]

REFERENCE_TYPES = [
    "舞蹈律动",
    "健身运动",
    "穿搭展示",
    "镜前自拍",
    "走路回头",
    "坐姿互动",
    "双人互动",
    "生活场景剧情",
]

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
VIDEO_TYPE_RE = re.compile(r"视频类型：\s*(?P<main>[^，,。；;\s]+)\s*[；;]\s*次类型：\s*(?P<sub>[^，,。；;\s]+)")


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


def video_type_finding(text):
    matches = list(VIDEO_TYPE_RE.finditer(text))
    if not matches:
        return "missing_video_type", "最终 vid prompt 缺少“视频类型：...；次类型：...；”类型段"
    invalid = []
    for match in matches:
        main_type = match.group("main")
        sub_type = match.group("sub")
        if main_type not in REFERENCE_TYPES:
            invalid.append(f"主类型={main_type}")
        if sub_type and sub_type != "无" and sub_type not in REFERENCE_TYPES:
            invalid.append(f"次类型={sub_type}")
    if invalid:
        return "invalid_video_type", f"最终 vid prompt 含非法参考类型：{', '.join(invalid)}"
    return None, None


def section_spans(text, labels):
    positions = []
    missing = []
    for label in labels:
        match = re.search(SECTION_RE_TEMPLATE.format(label=re.escape(label)), text)
        if match:
            positions.append((label, match.start(2)))
        else:
            missing.append(label)
    spans = []
    for index, (label, start) in enumerate(positions):
        content_start = start + len(label) + 1
        content_end = positions[index + 1][1] if index + 1 < len(positions) else len(text)
        spans.append((label, start, content_start, content_end))
    return positions, missing, spans


def section_finding(text, labels=None, section_name="十段标签"):
    labels = labels or REQUIRED_SECTION_LABELS
    positions, missing, spans = section_spans(text, labels)
    if missing:
        return "missing_sections", f"最终 prompt 缺少{section_name}：{', '.join(missing)}"
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


def lint_text(text, path, route="anna", channel="auto"):
    findings = []
    if route != "anna":
        add(findings, "error", "unsupported_route", "dy 项目只支持 anna 路线")
    if channel != "auto":
        add(findings, "error", "unsupported_channel", "dy 项目只支持 auto 通道")
    if "@图1" not in text:
        add(findings, "error", "missing_role_image", "auto/fast 视频 prompt 缺少 @图1 单图身份引用或说明")
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
    section_code, section_message = section_finding(text)
    if section_code:
        add(findings, "error", section_code, section_message)
    type_code, type_message = video_type_finding(text)
    if type_code:
        add(findings, "error", type_code, type_message)
    clothing_conflicts = image_one_clothing_conflict(text)
    if clothing_conflicts:
        add(findings, "error", "image_one_clothing_anchor", "@图1 只能作为身份、五官、发型、脸型和稳定身材比例依据，auto/fast 不得把 @图1 穿搭作为依据")
    sellpoint_text = section_content(text, "卖点与锁定")
    if sellpoint_text is not None:
        if not any(term in sellpoint_text for term in CHEST_SAFE_EXPRESSIONS):
            add(findings, "error", "missing_chest_safe_expression", "卖点与锁定段必须至少包含一条胸部体量安全表达")
        if not any(term in sellpoint_text for term in HIP_SAFE_EXPRESSIONS):
            add(findings, "error", "missing_hip_safe_expression", "卖点与锁定段必须至少包含一条臀胯比例安全表达")
    forbidden_hits = [term for term in FORBIDDEN_BODY_TERMS if term in text]
    if forbidden_hits:
        add(findings, "error", "unsafe_body_terms", f"prompt 含直白身材或低俗词：{', '.join(forbidden_hits)}")
    non_music_sound_hits = positive_sound_hits(text)
    if non_music_sound_hits:
        add(findings, "error", "non_music_sound_terms", f"prompt 含音乐以外的声音：{', '.join(non_music_sound_hits)}")

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warn")
    infos = sum(1 for f in findings if f["severity"] == "info")
    return {
        "path": str(path),
        "route": "anna",
        "channel": "auto",
        "mode": "fast",
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


def lint_derived_prompt(text, path, mode):
    return lint_text(text, path)


def derive_main(argv):
    parser = argparse.ArgumentParser(description="从 grid-prompt.txt 机械派生阶段 prompt。")
    parser.add_argument("grid_prompt", help="模块 01 写出的 TEMP/RUN_ID/grid-prompt.txt")
    parser.add_argument("--mode", choices=["fast"], required=True)
    parser.add_argument("--out", required=True, help="派生 prompt 输出路径")
    args = parser.parse_args(argv)

    source = Path(args.grid_prompt).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    if not source.exists():
        print(json.dumps({"error": "grid-prompt 文件不存在", "missing": str(source)}, ensure_ascii=False), file=sys.stderr)
        return 2

    source_text = source.read_text(encoding="utf-8", errors="replace")
    source_lint = lint_text(source_text, source)
    if source_lint["decision"] != "pass":
        print(json.dumps({"decision": "fail", "source_lint": source_lint}, ensure_ascii=False, indent=2))
        return 1

    try:
        derived = derive_prompt(source_text, args.mode)
    except ValueError as exc:
        print(json.dumps({"decision": "fail", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    derived_lint = lint_derived_prompt(derived, out_path, args.mode)
    if derived_lint["decision"] != "pass":
        print(json.dumps({"decision": "fail", "source_lint": source_lint, "derived_lint": derived_lint}, ensure_ascii=False, indent=2))
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(derived, encoding="utf-8")
    print(json.dumps({
        "decision": "pass",
        "mode": args.mode,
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
        "| 结论 | 路线 | 通道 | 视频模式 | 错误数 | 文件 | 主要发现 |",
        "|---|---|---|---|---:|---|---|",
    ]
    for item in results:
        top = "; ".join(f["message"] for f in item["findings"][:4]) or "无"
        lines.append(f"| {item['decision']} | anna | auto | fast | {item['errors']} | {Path(item['path']).name} | {top} |")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_json, report_md


def lint_main(argv=None):
    parser = argparse.ArgumentParser(description="检查 dy 项目的最终 prompt 是否满足 TNS 收敛硬门。")
    parser.add_argument("prompts", nargs="+", help="最终 prompt 文本文件")
    parser.add_argument("--route", choices=["anna"], default="anna")
    parser.add_argument("--channel", choices=["auto"], default="auto")
    parser.add_argument("--out-dir", default=None, help="输出目录，默认 TEMP/prompt-lint-runs/YYYYMMDD-HHMMSS")
    args = parser.parse_args(argv)

    files = [Path(p).expanduser().resolve() for p in args.prompts]
    missing = [str(p) for p in files if not p.exists()]
    if missing:
        print(json.dumps({"error": "prompt 文件不存在", "missing": missing}, ensure_ascii=False), file=sys.stderr)
        return 2

    results = [lint_text(file.read_text(encoding="utf-8", errors="replace"), file, args.route, args.channel) for file in files]
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


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "derive":
        return derive_main(argv[1:])
    return lint_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
