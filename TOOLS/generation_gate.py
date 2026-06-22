#!/usr/bin/env python3
"""Gate Dreamina video submission for the anna auto workflow."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_record import append_artifact, append_event, refresh_markdown


FIXED_CAMERA_TERMS = ["固定手机机位", "固定手机支架", "固定机位", "稳定机位", "手机支架"]
HANDHELD_CAMERA_TERMS = ["手持", "轻微手持", "手持自拍", "手持跟拍", "跟拍"]
FORBIDDEN_PROMPT_TERMS = [
    "附件",
    "节点",
    "画布",
    "模型参数",
    "分辨率",
    "结果数",
    "@图2",
    "@图3",
]


def read_json(path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_existing(path_value, root, report_path=None):
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    candidates = [path] if path.is_absolute() else [root / path]
    if report_path and not path.is_absolute():
        candidates.append(report_path.parent / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0].resolve()


def add_error(errors, message):
    errors.append(message)


def add_warning(warnings, message):
    warnings.append(message)


def validate_grid_report(path, root, errors, warnings):
    if not path.exists():
        add_error(errors, f"宫格报告不存在：{path}")
        return {}
    report = read_json(path)
    decision = report.get("decision")
    if decision != "pass":
        add_error(errors, f"宫格报告结论不是 pass：{decision}")
    validation = report.get("validation")
    if not validation:
        add_error(errors, "宫格报告缺少 validation 内容验证结果")
    elif validation.get("decision") != "pass":
        add_error(errors, f"宫格内容验证不是 pass：{validation.get('decision')}")
        for item in validation.get("errors", []):
            add_error(errors, f"宫格内容验证错误：{item}")
    if report.get("errors"):
        add_error(errors, "宫格报告存在 errors，不能提交正式生成")
    if report.get("chrome_js_unavailable"):
        add_error(errors, "Chrome JS 权限不可用时生成的宫格不能提交正式生成")
    if report.get("duration_sec", 0) <= 0:
        add_error(errors, "宫格报告视频时长为 0 或不可读")
    if report.get("capture_mode") in {"custom-rect", "chrome-window"}:
        add_error(errors, f"宫格截图方式不允许进入正式生成：{report.get('capture_mode')}")
    if any(frame.get("mode") == "natural-playback" for frame in report.get("frames", [])):
        add_error(errors, "宫格使用自然播放间隔截图，不能提交正式生成")
    if not report.get("has_current_src"):
        add_warning(warnings, "宫格报告未确认 video currentSrc；正式运行前建议复查播放源")
    grid_path = resolve_existing(report.get("grid_path"), root, path)
    if not grid_path or not grid_path.exists():
        add_error(errors, f"宫格图不存在：{report.get('grid_path')}")
    return {
        "report": str(path.resolve()),
        "grid": str(grid_path) if grid_path else None,
        "decision": decision,
        "validation_decision": validation.get("decision") if validation else None,
        "capture_mode": report.get("capture_mode"),
        "duration_sec": report.get("duration_sec"),
    }


def validate_prompt_lint(path, errors):
    if not path.exists():
        add_error(errors, f"Prompt lint 报告不存在：{path}")
        return {}
    data = read_json(path)
    results = data if isinstance(data, list) else data.get("results", [])
    if not results:
        add_error(errors, "Prompt lint 报告没有结果项")
        return {"report": str(path.resolve()), "results": 0}
    for item in results:
        if item.get("decision") != "pass":
            add_error(errors, f"Prompt lint 未通过：{Path(item.get('path', '')).name or path.name}")
        if item.get("route") != "anna":
            add_error(errors, f"Prompt lint 路线不是 anna：{item.get('route')}")
        if item.get("channel") != "auto":
            add_error(errors, f"Prompt lint 通道不是 auto：{item.get('channel')}")
    return {
        "report": str(path.resolve()),
        "results": len(results),
        "decisions": [item.get("decision") for item in results],
        "routes": [item.get("route") for item in results],
        "channels": [item.get("channel") for item in results],
    }


def validate_dreamina_prompt(path, errors):
    if not path:
        add_error(errors, "Dreamina 通道缺少 --prompt-file")
        return {}
    if not path.exists():
        add_error(errors, f"Dreamina vid prompt 文件不存在：{path}")
        return {"prompt_file": str(path)}
    text = path.read_text(encoding="utf-8", errors="replace")
    if "@图1" not in text:
        add_error(errors, "Dreamina vid prompt 缺少 @图1 图片引用（@图1=自动门禁选中的确认图）")
    found = [term for term in FORBIDDEN_PROMPT_TERMS if term in text]
    if found:
        add_error(errors, f"Dreamina vid prompt 含不支持或内部流程词：{', '.join(found)}")
    fixed_hits = [term for term in FIXED_CAMERA_TERMS if term in text]
    handheld_hits = [term for term in HANDHELD_CAMERA_TERMS if term in text]
    if fixed_hits and handheld_hits:
        add_error(errors, f"Dreamina vid prompt 拍摄方式冲突：固定机位与手持描述不能同时出现（固定：{', '.join(fixed_hits)}；手持：{', '.join(handheld_hits)}）")
    return {
        "prompt_file": str(path.resolve()),
        "required_refs": ["@图1"],
        "contains_graph1": "@图1" in text,
        "contains_graph2": "@图2" in text,
        "fixed_camera_terms": fixed_hits,
        "handheld_camera_terms": handheld_hits,
        "forbidden_terms": found,
    }


def write_report(out_dir, report, record_jsonl=None):
    report_json = out_dir / "formal-generation-gate-report.json"
    report_md = out_dir / "formal-generation-gate-report.md"
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# 正式生成门禁报告",
        "",
        f"- 结论：{report['decision']}",
        "- 路线：anna",
        "- 通道：auto",
        "- 生成引擎：dreamina",
        f"- 提交清单：{report.get('generation_manifest') or '未生成'}",
        "",
        "## 问题",
    ]
    lines.extend([f"- {item}" for item in report.get("errors", [])] or ["- 无"])
    if report.get("warnings"):
        lines.extend(["", "## 提醒"])
        lines.extend([f"- {item}" for item in report["warnings"]])
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if record_jsonl:
        append_event(record_jsonl, stage="generation_gate", event="generation_gate", status=report["decision"], summary=f"dreamina 正式生成门禁 {report['decision']}", data=report)
        append_artifact(record_jsonl, stage="generation_gate", path=str(report_json), kind="generation-gate-report", status=report["decision"], keep=True, summary="正式生成门禁 JSON")
        refresh_markdown(record_jsonl)
    return report_json, report_md


def main():
    parser = argparse.ArgumentParser(description="检查 dy 项目 Dreamina 视频生成提交前硬门。")
    parser.add_argument("--engine", choices=["dreamina"], default="dreamina")
    parser.add_argument("--route", choices=["anna"], required=True)
    parser.add_argument("--channel", choices=["auto"], required=True)
    parser.add_argument("--reference-url", required=True)
    parser.add_argument("--grid-report", required=True)
    parser.add_argument("--prompt-lint-report", default=None, help="TNS 收敛重试时必填；默认非 TNS 提交不要求 vid prompt lint")
    parser.add_argument("--tns-retry", action="store_true", help="TNS/安全拦截后的 prompt 收敛重试")
    parser.add_argument("--prompt-file", required=True)
    parser.add_argument("--confirmation-image", required=True, help="自动门禁选中的 Dreamina 原始确认图")
    parser.add_argument("--anna-role", default="MATERIAL/fixed-role/anna.png")
    parser.add_argument("--out-dir", default=None, help="默认 TEMP/generation-gates/YYYYMMDD-HHMMSS")
    parser.add_argument("--record-jsonl", default=None, help="可选：追加写入 TEMP/RUN_ID/RUN_ID-run-record.jsonl")
    args = parser.parse_args()

    root = Path.cwd()
    out_dir = Path(args.out_dir) if args.out_dir else root / "TEMP/generation-gates" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    errors = []
    warnings = []
    grid_report_path = resolve_existing(args.grid_report, root)
    prompt_lint_path = resolve_existing(args.prompt_lint_report, root) if args.prompt_lint_report else None
    prompt_file = resolve_existing(args.prompt_file, root)
    confirmation_image = resolve_existing(args.confirmation_image, root)
    anna_role = resolve_existing(args.anna_role, root)

    if not confirmation_image.exists():
        add_error(errors, f"auto 通道确认图不存在：{confirmation_image}")
    if not anna_role.exists():
        add_error(errors, f"anna 原始角色卡不存在：{anna_role}")

    grid = validate_grid_report(grid_report_path, root, errors, warnings)
    if args.tns_retry:
        if not prompt_lint_path:
            add_error(errors, "TNS 收敛重试必须提供 --prompt-lint-report")
            prompt_lint = {"required": True, "provided": False}
        else:
            prompt_lint = validate_prompt_lint(prompt_lint_path, errors)
            prompt_lint["required"] = True
            prompt_lint["provided"] = True
    else:
        prompt_lint = {
            "required": False,
            "provided": bool(prompt_lint_path),
            "report": str(prompt_lint_path) if prompt_lint_path else None,
            "skipped": True,
            "reason": "非 TNS 默认不运行 prompt_lint；仅 TNS 收敛重试强制检查",
        }
    dreamina_prompt = validate_dreamina_prompt(prompt_file, errors)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "reference_url": args.reference_url,
        "engine": "dreamina",
        "route": "anna",
        "channel": "auto",
        "tns_retry": args.tns_retry,
        "expected_dreamina_mode": "multimodal2video",
        "expected_dreamina_model_version": "seedance2.0_vip",
        "expected_ratio": "9:16",
        "expected_resolution": "720p",
        "expected_duration": "random 5-6s",
        "expected_result_count": 1,
        "expected_inputs": [str(confirmation_image)],
        "attachment_policy": "只挂自动通道人脸门禁通过的 Dreamina 原始确认图；不挂角色卡或参考宫格",
        "grid": grid,
        "prompt_lint": prompt_lint,
        "dreamina_prompt": dreamina_prompt,
        "errors": errors,
        "warnings": warnings,
        "decision": "fail" if errors else "pass",
    }

    manifest_path = out_dir / "dreamina-generation-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest["generation_manifest"] = str(manifest_path)
    report_json, report_md = write_report(out_dir, manifest, args.record_jsonl)
    print(json.dumps({
        "decision": manifest["decision"],
        "report_json": str(report_json),
        "report_md": str(report_md),
        "generation_manifest": str(manifest_path),
        "errors": errors,
        "warnings": warnings,
    }, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
