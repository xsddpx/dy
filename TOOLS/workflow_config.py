#!/usr/bin/env python3
"""Load and validate the single xdy workflow configuration."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "MATERIAL" / "xdy-workflow.json"
EXPECTED_SECTIONS = ("人物", "视频约束", "穿搭", "环境", "人物动作", "背景音乐", "其他")
REQUIRED_PERSON_BODY_PHRASES = (
    "胸部体量严格以正面、斜侧面和侧面全身图为准",
    "与角色图相同的体量",
    "胸廓前后比例",
    "侧向投影",
    "各角度全程稳定一致",
)
SLOW_ACTION_PHRASES = ("缓慢", "慢慢", "慢速", "轻缓", "徐徐", "渐渐", "slowly", "slow motion", "slow-motion")


class WorkflowConfigError(ValueError):
    """Raised when the checked-in workflow configuration is invalid."""


@lru_cache(maxsize=4)
def load_workflow_config(path: str | Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkflowConfigError(f"工作流配置不存在：{config_path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkflowConfigError(f"工作流配置不是合法 JSON：{exc.msg}") from exc
    validate_workflow_config(config, config_path.parent.parent)
    config["_path"] = str(config_path)
    return config


def validate_workflow_config(config: dict[str, Any], root: Path = PROJECT_ROOT) -> None:
    if config.get("schema_version") != 1:
        raise WorkflowConfigError("工作流配置 schema_version 必须为 1")
    generation = config.get("generation") or {}
    if generation.get("ratio") != "9:16":
        raise WorkflowConfigError("视频比例必须为 9:16")
    if generation.get("video_resolution") != "720p":
        raise WorkflowConfigError("视频分辨率必须为 720p")
    if generation.get("valid_durations") != [5, 6, 7]:
        raise WorkflowConfigError("合法时长必须严格为 5、6、7 秒")
    prompt = config.get("prompt") or {}
    if tuple(prompt.get("sections") or ()) != EXPECTED_SECTIONS:
        raise WorkflowConfigError("prompt 七段顺序与项目合同不一致")
    person = str(prompt.get("person") or "").strip()
    missing_person_body_phrases = [phrase for phrase in REQUIRED_PERSON_BODY_PHRASES if phrase not in person]
    if missing_person_body_phrases:
        raise WorkflowConfigError("prompt 人物固定段缺少胸部体量一致性锚点：" + "、".join(missing_person_body_phrases))
    if "全程保持正常速度，不使用慢动作" not in str(prompt.get("video_constraint") or ""):
        raise WorkflowConfigError("视频约束缺少正常速度与非慢动作要求")
    actions = prompt.get("actions") or {}
    if tuple(sorted(actions)) != ("01", "02", "03", "04"):
        raise WorkflowConfigError("动作模板必须严格包含 01–04")
    valid_durations = set(generation["valid_durations"])
    for action_id, action in actions.items():
        action_text = str(action.get("text") or "").strip()
        if not action_text:
            raise WorkflowConfigError(f"动作模板 {action_id} 正文为空")
        lowered_action_text = action_text.lower()
        found_slow_phrases = [phrase for phrase in SLOW_ACTION_PHRASES if phrase.lower() in lowered_action_text]
        if found_slow_phrases:
            raise WorkflowConfigError(
                f"动作模板 {action_id} 含缓慢描述：{'、'.join(found_slow_phrases)}"
            )
        if action.get("preferred_duration") not in valid_durations:
            raise WorkflowConfigError(f"动作模板 {action_id} 默认时长不合法")
    runtime = config.get("runtime") or {}
    if runtime.get("timezone") != "Asia/Shanghai":
        raise WorkflowConfigError("运行时区必须为 Asia/Shanghai")
    intervals = runtime.get("poll_intervals_seconds") or []
    if not intervals or any(not isinstance(value, int) or value <= 0 for value in intervals):
        raise WorkflowConfigError("Dreamina 轮询间隔必须是正整数数组")
    expected_categories = {"network", "login", "credits", "upload", "download", "timeout", "dependency", "parameter"}
    if set(runtime.get("environment_error_categories") or []) != expected_categories:
        raise WorkflowConfigError("环境错误分类与项目合同不一致")
    quality = config.get("quality") or {}
    if quality.get("frame_times") != [0.5, "middle", "end_minus_0.5"]:
        raise WorkflowConfigError("质检抽帧必须固定为 0.5 秒、中点和结束前 0.5 秒")
    if not isinstance(quality.get("proxy_max_bytes"), int) or quality["proxy_max_bytes"] <= 0:
        raise WorkflowConfigError("质检代理图字节上限必须是正整数")
    role_proxy_top_ratio = quality.get("role_proxy_top_ratio")
    if not isinstance(role_proxy_top_ratio, (int, float)) or not 0 < role_proxy_top_ratio <= 1:
        raise WorkflowConfigError("角色质检代理图顶部裁切比例必须在 0 到 1 之间")
    role_proxy_max_width = quality.get("role_proxy_max_width")
    if not isinstance(role_proxy_max_width, int) or role_proxy_max_width < 480:
        raise WorkflowConfigError("角色质检代理图最大宽度不得小于 480 像素")
    publish = config.get("publish") or {}
    if publish.get("tag_count") != 4:
        raise WorkflowConfigError("发布环节实际应用标签数必须固定为 4")
    if int(publish.get("candidate_tag_count") or 0) < publish["tag_count"]:
        raise WorkflowConfigError("候选标签池不能小于固定应用标签数")
    assets = config.get("assets") or {}
    for key in ("role_image", "environment_directory", "wardrobe"):
        value = assets.get(key)
        if not value or not (root / value).exists():
            raise WorkflowConfigError(f"配置资产不存在：{key}={value}")


def config_sha256(config: dict[str, Any] | None = None) -> str:
    active = dict(config or load_workflow_config())
    active.pop("_path", None)
    payload = json.dumps(active, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def project_path(root: Path, relative: str) -> Path:
    return (root / relative).resolve()


if __name__ == "__main__":
    print(json.dumps(load_workflow_config(), ensure_ascii=False, indent=2))
