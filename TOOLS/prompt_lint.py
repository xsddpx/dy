#!/usr/bin/env python3
"""Lint TNS retry prompts for the anna auto workflow."""

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
    "同时吸收",
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
]

CHEST_ART_TERMS = [
    "饱满的立体廓形",
    "高感知度的面料张力",
    "上身丰盈的沙漏型线条",
    "领口与上身轮廓清晰",
]

HIP_ART_TERMS = [
    "腰胯比例明显",
    "臀胯轮廓自然凸显",
    "高腰线与下装包裹出稳定曲线",
    "古典雕塑般的 S 形动态",
    "古典雕塑般的S形动态",
]

FIXED_CAMERA_TERMS = ["固定手机机位", "固定手机支架", "固定机位", "稳定机位", "手机支架"]
HANDHELD_CAMERA_TERMS = ["手持", "轻微手持", "手持自拍", "手持跟拍", "跟拍"]
META_INSTRUCTION_TERMS = ["身材表达使用艺术化穿搭语言", "艺术化穿搭语言："]
DEFAULT_INDOOR_BACKGROUND_TERMS = ["背景只做同类室内浅墙", "背景仍为同类室内浅墙", "同类室内浅墙与地面光线"]
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
VIDEO_TYPE_RE = re.compile(r"视频类型为(?P<main>[^，。；;\s]+)(?:，次类型为(?P<sub>[^，。；;\s]+))?")


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
        return "missing_video_type", "vid prompt 缺少“视频类型为...”类型指令"
    invalid = []
    for match in matches:
        main_type = match.group("main")
        sub_type = match.group("sub")
        if main_type not in REFERENCE_TYPES:
            invalid.append(f"主类型={main_type}")
        if sub_type and sub_type != "无" and sub_type not in REFERENCE_TYPES:
            invalid.append(f"次类型={sub_type}")
    if invalid:
        return "invalid_video_type", f"vid prompt 含非法参考类型：{', '.join(invalid)}"
    return None, None


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
    if not re.search(r"@?[^\s，。；;]*确认图|confirmation[-_ ]?image|@图1", text, re.IGNORECASE):
        add(findings, "error", "missing_confirmation_image", "auto/fast 视频 prompt 缺少 @图1 单图身份引用或说明")
    unsupported_hits = [term for term in UNSUPPORTED_TERMS if term in text]
    if unsupported_hits:
        add(findings, "error", "unsupported_terms", f"prompt 含本项目不接收的内部流程词：{', '.join(unsupported_hits)}")
    internal_source_hits = [term for term in INTERNAL_SOURCE_TERMS if term in text]
    if internal_source_hits:
        add(findings, "error", "internal_source_terms", f"vid prompt 含 Dreamina 不可执行的内部来源词：{', '.join(internal_source_hits)}")
    type_code, type_message = video_type_finding(text)
    if type_code:
        add(findings, "error", type_code, type_message)
    clothing_conflicts = image_one_clothing_conflict(text)
    if clothing_conflicts:
        add(findings, "error", "image_one_clothing_anchor", "@图1 只能作为身份、五官、发型、脸型和稳定身材比例依据，auto/fast 不得把 @图1 穿搭作为依据")
    forbidden_hits = [term for term in FORBIDDEN_BODY_TERMS if term in text]
    if forbidden_hits:
        add(findings, "error", "unsafe_body_terms", f"vid prompt 含直白身材或低俗词：{', '.join(forbidden_hits)}")
    if not any(term in text for term in CHEST_ART_TERMS):
        add(findings, "error", "missing_chest_artistic_expression", "缺少上身曲线的艺术化转译")
    if not any(term in text for term in HIP_ART_TERMS):
        add(findings, "error", "missing_hip_artistic_expression", "缺少腰胯曲线的艺术化转译")

    fixed_hits = [term for term in FIXED_CAMERA_TERMS if term in text]
    handheld_hits = [term for term in HANDHELD_CAMERA_TERMS if term in text]
    if fixed_hits and handheld_hits:
        add(findings, "error", "camera_mode_conflict", f"拍摄方式冲突：固定机位与手持描述不能同时出现（固定：{', '.join(fixed_hits)}；手持：{', '.join(handheld_hits)}）")

    meta_hits = [term for term in META_INSTRUCTION_TERMS if term in text]
    if meta_hits:
        add(findings, "error", "meta_instruction_leak", f"prompt 含内部规则说明：{', '.join(meta_hits)}")
    indoor_background_hits = [term for term in DEFAULT_INDOOR_BACKGROUND_TERMS if term in text]
    if indoor_background_hits:
        add(findings, "error", "default_indoor_background_lock", f"prompt 含默认室内背景硬编码：{', '.join(indoor_background_hits)}")
    non_music_sound_hits = positive_sound_hits(text)
    if non_music_sound_hits:
        add(findings, "error", "non_music_sound_terms", f"vid prompt 含音乐以外的声音：{', '.join(non_music_sound_hits)}")

    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warn")
    infos = sum(1 for f in findings if f["severity"] == "info")
    return {
        "path": str(path),
        "route": "anna",
        "channel": "auto",
        "bytes": len(text.encode("utf-8")),
        "errors": errors,
        "warnings": warnings,
        "infos": infos,
        "decision": "fail" if errors else "pass",
        "findings": findings,
    }


def write_reports(results, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "report.json"
    report_md = out_dir / "report.md"
    report_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# TNS vid prompt lint 报告",
        "",
        f"- 样本数：{len(results)}",
        f"- 通过：{sum(1 for r in results if r['decision'] == 'pass')}",
        f"- 失败：{sum(1 for r in results if r['decision'] == 'fail')}",
        "",
        "| 结论 | 路线 | 通道 | 错误数 | 文件 | 主要发现 |",
        "|---|---|---|---:|---|---|",
    ]
    for item in results:
        top = "; ".join(f["message"] for f in item["findings"][:4]) or "无"
        lines.append(f"| {item['decision']} | anna | auto | {item['errors']} | {Path(item['path']).name} | {top} |")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_json, report_md


def main():
    parser = argparse.ArgumentParser(description="检查 dy 项目的 vid prompt 是否满足 TNS 收敛硬门。")
    parser.add_argument("prompts", nargs="+", help="vid prompt 文本文件")
    parser.add_argument("--route", choices=["anna"], default="anna")
    parser.add_argument("--channel", choices=["auto"], default="auto")
    parser.add_argument("--out-dir", default=None, help="输出目录，默认 TEMP/prompt-lint-runs/YYYYMMDD-HHMMSS")
    args = parser.parse_args()

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


if __name__ == "__main__":
    raise SystemExit(main())
