import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo


TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
SCRIPT = TOOLS / "run_workspace.py"
SPEC = importlib.util.spec_from_file_location("run_workspace", SCRIPT)
RUN_WORKSPACE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN_WORKSPACE)
SHANGHAI = ZoneInfo("Asia/Shanghai")


def make_root(base: Path) -> Path:
    root = base / "repo"
    (root / "TEMP").mkdir(parents=True)
    (root / "OUTPUT").mkdir()
    return root


def make_run(root: Path, run_id: str, created_at: str, extra_event=None) -> Path:
    directory = root / "TEMP" / run_id
    directory.mkdir()
    record = directory / f"{run_id}-run-record.jsonl"
    events = [
        {
            "created_at": created_at,
            "stage": "run",
            "event": "started",
            "status": "in_progress",
            "data": {"run_id": run_id},
        }
    ]
    if extra_event:
        events.append(extra_event)
    record.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in events), encoding="utf-8")
    (directory / f"{run_id}-run-record.md").write_text(f"# {run_id} 运行记录\n", encoding="utf-8")
    summary = directory / "logs" / "summary"
    summary.mkdir(parents=True)
    (summary / f"{run_id}-summary.json").write_text(
        json.dumps({"run_id": run_id, "logs_dir": f"TEMP/{run_id}/logs"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return directory


def valid_prompt() -> str:
    lint = RUN_WORKSPACE.prompt_lint
    return (
        "人物：@图1 是同一位成年女性的多视角、多表情角色参考图，不是多人合照；"
        "脸部严格参考左下角大脸，身材严格参考正面、侧面和背面全身图，保持同一人物的脸部身份与身材一致。"
        "画面中只出现这一位成年女性。"
        "视频约束："
        + lint.FIXED_VIDEO_CONSTRAINT_TEMPLATES["01"]
        + "穿搭：黑色合体上衣搭配高腰直筒短裙，上衣采用哑光面料并呈现清晰腰线，短裙版型全程一致。"
        + "环境："
        + lint.FIXED_ENVIRONMENT_TEMPLATES["01"]
        + "人物动作："
        + lint.FIXED_ACTION_TEMPLATES["01"]
        + "背景音乐：轻快电子律动纯音乐，稳定四拍节奏，氛围俏皮自信。"
        + "其他：写实摄影风格，真实人物质感，均匀柔和的真实室内光影，真实皮肤纹理，真实面部结构，"
        "真实头发丝细节，真实服装材质，符合物理规律的光照和阴影，自然景深，真实镜头质感，真实环境透视，"
        "真实色彩。穿搭轮廓清晰，腰线可见，构图稳定，单一连续完整竖屏画面，人物和环境保持同一时空与稳定透视。"
    )


def make_contract_run(root: Path, run_id: str = "20260717-120000", prompt_version: int = 1) -> Path:
    role = root / "MATERIAL" / "fixed-role" / "anna.png"
    environment = root / "MATERIAL" / "fixed-environment" / "anna-room-01.png"
    role.parent.mkdir(parents=True, exist_ok=True)
    environment.parent.mkdir(parents=True, exist_ok=True)
    role.write_bytes(b"role")
    environment.write_bytes(b"environment")
    directory = make_run(root, run_id, "2026-07-17T12:00:00+08:00")
    grid = valid_prompt()
    (directory / "grid-prompt.txt").write_text(grid, encoding="utf-8")
    (directory / f"vid-prompt-v{prompt_version}.txt").write_text(
        RUN_WORKSPACE.prompt_lint.derive_prompt(grid, "fast"),
        encoding="utf-8",
    )
    (directory / "environment-path.txt").write_text(str(environment.resolve()) + "\n", encoding="utf-8")
    return directory


def append_record_event(directory: Path, run_id: str, **event) -> None:
    record = directory / f"{run_id}-run-record.jsonl"
    with record.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def append_generation_submit(root: Path, directory: Path, run_id: str, version: str, duration: int) -> dict:
    manifest = json.loads(
        (directory / "logs" / "contracts" / f"generation-{version}.json").read_text(encoding="utf-8")
    )
    append_record_event(
        directory,
        run_id,
        stage="dreamina",
        event="submit",
        status="querying",
        data={
            "version": version,
            "duration": duration,
            "ratio": "9:16",
            "video_resolution": "720p",
            "reference_images": manifest["reference_images"],
            "prompt": manifest["prompt"],
            "prompt_sha256": manifest["sha256"]["prompt"],
        },
    )
    return manifest


class RunWorkspaceTest(unittest.TestCase):
    def test_parse_time_normalizes_naive_and_utc(self):
        naive = RUN_WORKSPACE.parse_time("2026-07-12T08:09:10")
        utc = RUN_WORKSPACE.parse_time("2026-07-12T00:09:10Z")
        self.assertEqual(naive, utc)
        self.assertEqual(RUN_WORKSPACE.canonical_base(utc), "20260712-080910")

    def test_timestamp_fallbacks_to_first_event_then_legacy_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            directory = root / "TEMP" / "20260625-0955-topic"
            directory.mkdir()
            record = directory / "20260625-0955-topic-run-record.jsonl"
            record.write_text(
                json.dumps({"ts": "2026-06-25T01:59:21Z", "stage": "reference", "event": "start"}) + "\n",
                encoding="utf-8",
            )
            stamp, source = RUN_WORKSPACE.timestamp_for_run(directory, record)
            self.assertEqual(RUN_WORKSPACE.canonical_base(stamp), "20260625-095921")
            self.assertEqual(source, "first_event.ts")

            record.write_text("not json\n", encoding="utf-8")
            stamp, source = RUN_WORKSPACE.timestamp_for_run(directory, record)
            self.assertEqual(RUN_WORKSPACE.canonical_base(stamp), "20260625-095500")
            self.assertEqual(source, "legacy_name")

    def test_allocator_uses_suffixes_and_stops_after_99(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            when = datetime(2026, 7, 12, 8, 9, 10, tzinfo=SHANGHAI)
            base = "20260712-080910"
            (root / "TEMP" / base).mkdir()
            run_id, _ = RUN_WORKSPACE.allocate_run_dir(root, when)
            self.assertEqual(run_id, base + "-01")

            for index in range(2, 100):
                (root / "TEMP" / f"{base}-{index:02d}").mkdir()
            with self.assertRaises(RUN_WORKSPACE.WorkspaceError):
                RUN_WORKSPACE.allocate_run_dir(root, when)

    def test_allocator_is_atomic_under_concurrency(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            when = datetime(2026, 7, 12, 8, 9, 10, tzinfo=SHANGHAI)
            with ThreadPoolExecutor(max_workers=6) as executor:
                results = list(executor.map(lambda _: RUN_WORKSPACE.allocate_run_dir(root, when)[0], range(6)))
            self.assertEqual(
                sorted(results),
                ["20260712-080910", *(f"20260712-080910-{index:02d}" for index in range(1, 6))],
            )

    def test_init_creates_record_logs_and_output_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            result = RUN_WORKSPACE.init_workspace(
                root,
                when=datetime(2026, 7, 12, 8, 9, 10, tzinfo=SHANGHAI),
                source="test",
                data={"thread": "abc"},
            )
            self.assertEqual(result["run_id"], "20260712-080910")
            record = root / result["record_jsonl"]
            event = json.loads(record.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(event["data"], {"source": "test", "thread": "abc"})
            self.assertTrue((root / "TEMP" / result["run_id"] / "logs").is_dir())
            self.assertEqual(result["output_mp4"], "OUTPUT/20260712-080910.mp4")

    def test_plan_excludes_auxiliary_dirs_and_maps_dy_output_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            make_run(root, "old-b", "2026-07-12T08:09:10")
            make_run(root, "old-a", "2026-07-12T08:09:10")
            make_run(root, "dy-20260712-090000-topic", "2026-07-12T09:00:00")
            (root / "TEMP" / "candidate-1").mkdir()
            (root / "TEMP" / "candidate-1" / "candidate-run-record.jsonl").touch()
            (root / "TEMP" / "del").mkdir()
            output = root / "OUTPUT" / "20260712-090000-topic.mp4"
            output.write_bytes(b"video")

            plan = RUN_WORKSPACE.build_migration_plan(root)
            self.assertEqual(plan["run_count"], 3)
            self.assertEqual(plan["output_count"], 1)
            by_old = {item["old_id"]: item for item in plan["entries"]}
            self.assertEqual(by_old["old-a"]["new_id"], "20260712-080910")
            self.assertEqual(by_old["old-b"]["new_id"], "20260712-080910-01")
            self.assertEqual(
                by_old["dy-20260712-090000-topic"]["output_old"],
                "OUTPUT/20260712-090000-topic.mp4",
            )

    def test_apply_audit_and_rollback_preserve_external_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            old_id = "20260712-0809-topic"
            external = {
                "created_at": "2026-07-12T08:09:10",
                "stage": "google_drive",
                "event": "uploaded",
                "data": {
                    "run_id": old_id,
                    "local_temp": f"TEMP/{old_id}/grid-prompt.txt",
                    "local_output": f"OUTPUT/{old_id}.mp4",
                    "file_name": f"{old_id}.mp4",
                    "url": "https://drive.google.com/file/d/unchanged",
                },
            }
            directory = make_run(root, old_id, "2026-07-12T08:09:10", external)
            (directory / "grid-prompt.txt").write_text("prompt\n", encoding="utf-8")
            output = root / "OUTPUT" / f"{old_id}.mp4"
            output.write_bytes(b"unchanged-video")
            original_hash = RUN_WORKSPACE.sha256_file(output)

            plan = RUN_WORKSPACE.build_migration_plan(root)
            manifest = RUN_WORKSPACE.apply_migration(root, plan)
            new_id = plan["entries"][0]["new_id"]
            new_record = root / "TEMP" / new_id / f"{new_id}-run-record.jsonl"
            text = new_record.read_text(encoding="utf-8")
            self.assertIn(f'"run_id": "{new_id}"', text)
            self.assertIn(f"TEMP/{new_id}/grid-prompt.txt", text)
            self.assertIn(f"OUTPUT/{new_id}.mp4", text)
            self.assertIn(f'"file_name": "{old_id}.mp4"', text)
            self.assertIn("https://drive.google.com/file/d/unchanged", text)
            self.assertEqual(RUN_WORKSPACE.sha256_file(root / "OUTPUT" / f"{new_id}.mp4"), original_hash)
            self.assertEqual(RUN_WORKSPACE.audit_workspace(root)["decision"], "pass")

            RUN_WORKSPACE.rollback_migration(root, manifest)
            restored_record = root / "TEMP" / old_id / f"{old_id}-run-record.jsonl"
            self.assertTrue(restored_record.is_file())
            self.assertIn(f"TEMP/{old_id}/grid-prompt.txt", restored_record.read_text(encoding="utf-8"))
            self.assertEqual(RUN_WORKSPACE.sha256_file(root / "OUTPUT" / f"{old_id}.mp4"), original_hash)

    def test_migration_accepts_an_already_canonical_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            run_id = "20260712-080910"
            make_run(root, run_id, "2026-07-12T08:09:10")
            plan = RUN_WORKSPACE.build_migration_plan(root)
            self.assertEqual(plan["entries"][0]["new_id"], run_id)
            manifest = RUN_WORKSPACE.apply_migration(root, plan)
            self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["status"], "applied")
            self.assertEqual(RUN_WORKSPACE.audit_workspace(root)["decision"], "pass")
            RUN_WORKSPACE.rollback_migration(root, manifest)
            self.assertTrue((root / "TEMP" / run_id / f"{run_id}-run-record.jsonl").is_file())

    def test_apply_failure_automatically_restores_original_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            old_id = "20260712-0809-topic"
            make_run(root, old_id, "2026-07-12T08:09:10")
            output = root / "OUTPUT" / f"{old_id}.mp4"
            output.write_bytes(b"video")
            plan = RUN_WORKSPACE.build_migration_plan(root)
            with mock.patch.object(RUN_WORKSPACE, "apply_internal_changes", side_effect=RuntimeError("boom")):
                with self.assertRaises(RuntimeError):
                    RUN_WORKSPACE.apply_migration(root, plan)
            self.assertTrue((root / "TEMP" / old_id / f"{old_id}-run-record.jsonl").is_file())
            self.assertEqual(output.read_bytes(), b"video")

    def test_audit_rejects_orphan_and_invalid_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            make_run(root, "20260712-080910", "2026-07-12T08:09:10")
            (root / "OUTPUT" / "bad-name.mp4").touch()
            result = RUN_WORKSPACE.audit_workspace(root)
            self.assertEqual(result["decision"], "failed")
            self.assertTrue(any("非法正式成片名称" in error for error in result["errors"]))

    def test_audit_rejects_mismatched_record_filename(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            directory = root / "TEMP" / "20260712-080910"
            directory.mkdir()
            (directory / "old-run-record.jsonl").touch()
            result = RUN_WORKSPACE.audit_workspace(root)
            self.assertTrue(any("运行目录与记录文件名不一致" in error for error in result["errors"]))

    def test_pre_generation_contract_is_idempotent_and_refuses_changed_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            run_id = "20260717-120000"
            directory = make_contract_run(root, run_id)

            first = RUN_WORKSPACE.validate_pre_generation_contract(
                root, run_id, route="xdysp", duration=5, prompt_version=1
            )
            self.assertEqual(first["decision"], "pass", first["errors"])
            manifest_path = root / first["manifest"]
            original_manifest = manifest_path.read_bytes()
            manifest = json.loads(original_manifest)
            self.assertEqual(manifest["reference_images"][0], str((root / "MATERIAL/fixed-role/anna.png").resolve()))
            self.assertEqual(manifest["ratio"], "9:16")
            self.assertEqual(manifest["video_resolution"], "720p")

            repeated = RUN_WORKSPACE.validate_pre_generation_contract(
                root, run_id, route="xdysp", duration=5, prompt_version=1
            )
            self.assertEqual(repeated["decision"], "pass", repeated["errors"])
            self.assertEqual(manifest_path.read_bytes(), original_manifest)

            changed = valid_prompt().replace("氛围俏皮自信", "氛围轻松自信")
            (directory / "grid-prompt.txt").write_text(changed, encoding="utf-8")
            (directory / "vid-prompt-v1.txt").write_text(
                RUN_WORKSPACE.prompt_lint.derive_prompt(changed, "fast"), encoding="utf-8"
            )
            conflict = RUN_WORKSPACE.validate_pre_generation_contract(
                root, run_id, route="xdysp", duration=5, prompt_version=1
            )
            self.assertEqual(conflict["decision"], "failed")
            self.assertTrue(any("拒绝覆盖" in error for error in conflict["errors"]))
            self.assertEqual(manifest_path.read_bytes(), original_manifest)

    def test_pre_generation_contract_rejects_bad_duration_references_and_record_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            run_id = "20260717-120001"
            directory = make_contract_run(root, run_id)
            prompt = (directory / "vid-prompt-v1.txt").read_text(encoding="utf-8").replace("@图2", "@图3")
            (directory / "grid-prompt.txt").write_text(prompt, encoding="utf-8")
            (directory / "vid-prompt-v1.txt").write_text(prompt, encoding="utf-8")
            with (directory / f"{run_id}-run-record.jsonl").open("a", encoding="utf-8") as handle:
                handle.write("not-json\n")
            result = RUN_WORKSPACE.validate_pre_generation_contract(
                root, run_id, route="xdysp", duration=4, prompt_version=1, write_manifest=False
            )
            self.assertEqual(result["decision"], "failed")
            self.assertTrue(any("5、6 或 7" in error for error in result["errors"]))
            self.assertTrue(any("@图1、@图2" in error for error in result["errors"]))
            self.assertTrue(any("不是合法 JSON" in error for error in result["errors"]))

    def test_finalize_xdysp_success_ignores_later_artifact_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            run_id = "20260717-120002"
            directory = make_contract_run(root, run_id)
            precheck = RUN_WORKSPACE.validate_pre_generation_contract(
                root, run_id, route="xdysp", duration=5, prompt_version=1
            )
            self.assertEqual(precheck["decision"], "pass", precheck["errors"])
            append_generation_submit(root, directory, run_id, "v1", 5)
            append_record_event(
                directory, run_id, stage="dreamina", event="generation", status="success", data={"version": "v1"}
            )
            append_record_event(
                directory, run_id, stage="review", event="skipped", status="not_performed", data={}
            )
            append_record_event(
                directory,
                run_id,
                stage="output",
                event="created",
                status="ready",
                data={"output_video": f"OUTPUT/{run_id}.mp4"},
            )
            append_record_event(
                directory,
                run_id,
                stage="output",
                event="artifact",
                status=None,
                data={"path": f"OUTPUT/{run_id}.mp4"},
            )
            output = root / "OUTPUT" / f"{run_id}.mp4"
            output.write_bytes(b"video")
            append_record_event(
                directory,
                run_id,
                stage="google_drive",
                event="upload",
                status="uploaded",
                summary="根目录上传并核验完成",
                data={
                    "file_id": "drive-file",
                    "file_name": f"{run_id}.mp4",
                    "mime_type": "video/mp4",
                    "root_verified": True,
                    "parent_ids": ["drive-root-id"],
                    "size": output.stat().st_size,
                    "url": "https://drive.example/file",
                    "needs_retry": False,
                },
            )
            append_record_event(
                directory, run_id, stage="publish", event="not_requested", status="not_requested", data={}
            )

            with mock.patch.object(
                RUN_WORKSPACE, "probe_video", return_value={"width": 720, "height": 1280, "duration": 5.08}
            ):
                result = RUN_WORKSPACE.validate_finalize_contract(
                    root,
                    run_id,
                    route="xdysp",
                    duration=5,
                    publish_mode="not_requested",
                )
            self.assertEqual(result["decision"], "pass", result["errors"])

            append_record_event(
                directory,
                run_id,
                stage="google_drive",
                event="uploaded",
                status="success",
                data={
                    "file_id": "drive-file",
                    "file_name": f"{run_id}.mp4",
                    "mime_type": "video/mp4",
                    "root_verified": True,
                    "folder_name": "最终视频",
                    "size": output.stat().st_size,
                },
            )
            with mock.patch.object(
                RUN_WORKSPACE, "probe_video", return_value={"width": 720, "height": 1280, "duration": 4.0}
            ):
                rejected = RUN_WORKSPACE.validate_finalize_contract(
                    root,
                    run_id,
                    route="xdysp",
                    duration=5,
                    publish_mode="not_requested",
                )
            self.assertEqual(rejected["decision"], "failed")
            self.assertTrue(any("My Drive 根目录" in error for error in rejected["errors"]))
            self.assertTrue(any("偏差超过" in error for error in rejected["errors"]))

    def test_finalize_accepts_publish_adapter_blocked_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            run_id = "20260717-120003"
            directory = make_contract_run(root, run_id)
            precheck = RUN_WORKSPACE.validate_pre_generation_contract(
                root, run_id, route="xdy", duration=5, prompt_version=1
            )
            self.assertEqual(precheck["decision"], "pass", precheck["errors"])
            append_generation_submit(root, directory, run_id, "v1", 5)
            append_record_event(
                directory, run_id, stage="dreamina", event="success", status="success", data={"version": "v1"}
            )
            append_record_event(
                directory, run_id, stage="quality", event="bust_volume_review", status="pass", data={}
            )
            append_record_event(
                directory,
                run_id,
                stage="output",
                event="created",
                status="ready",
                data={"output_video": f"OUTPUT/{run_id}.mp4"},
            )
            output = root / "OUTPUT" / f"{run_id}.mp4"
            output.write_bytes(b"video")
            append_record_event(
                directory,
                run_id,
                stage="google_drive",
                event="failed",
                status="failed",
                summary="连接器失败",
                data={"needs_retry": True, "reason": "connector unavailable"},
            )
            append_record_event(
                directory,
                run_id,
                stage="publish",
                event="both_publish",
                status="blocked",
                data={
                    "platforms": [
                        {"platform": "douyin", "decision": "published"},
                        {"platform": "kuaishou", "decision": "blocked"},
                    ]
                },
            )
            with mock.patch.object(
                RUN_WORKSPACE, "probe_video", return_value={"width": 720, "height": 1280, "duration": 5.06}
            ):
                result = RUN_WORKSPACE.validate_finalize_contract(
                    root, run_id, route="xdy", duration=5, publish_mode="default"
                )
            self.assertEqual(result["decision"], "pass", result["errors"])

    def test_finalize_handles_failure_cancel_and_waiting_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            failed_id = "20260717-120004"
            failed_dir = make_contract_run(root, failed_id, prompt_version=5)
            precheck = RUN_WORKSPACE.validate_pre_generation_contract(
                root, failed_id, route="xdysp", duration=5, prompt_version=5
            )
            self.assertEqual(precheck["decision"], "pass", precheck["errors"])
            append_generation_submit(root, failed_dir, failed_id, "v5", 5)
            append_record_event(
                failed_dir,
                failed_id,
                stage="dreamina",
                event="failed",
                status="failed",
                data={"version": "v5", "reason_category": "tns"},
            )
            append_record_event(
                failed_dir, failed_id, stage="review", event="skipped", status="not_performed", data={}
            )
            append_record_event(
                failed_dir,
                failed_id,
                stage="google_drive",
                event="not_attempted",
                status="not_attempted",
                data={"needs_retry": False},
            )
            append_record_event(
                failed_dir,
                failed_id,
                stage="publish",
                event="not_requested",
                status="not_requested",
                data={},
            )
            failed = RUN_WORKSPACE.validate_finalize_contract(
                root,
                failed_id,
                route="xdysp",
                duration=5,
                publish_mode="not_requested",
                outcome="generation_failed",
            )
            self.assertEqual(failed["decision"], "pass", failed["errors"])

            quality_id = "20260717-120008"
            quality_dir = make_contract_run(root, quality_id)
            precheck = RUN_WORKSPACE.validate_pre_generation_contract(
                root, quality_id, route="xdy", duration=5, prompt_version=1
            )
            self.assertEqual(precheck["decision"], "pass", precheck["errors"])
            append_generation_submit(root, quality_dir, quality_id, "v1", 5)
            append_record_event(
                quality_dir,
                quality_id,
                stage="dreamina",
                event="success",
                status="success",
                data={"version": "v1"},
            )
            append_record_event(
                quality_dir,
                quality_id,
                stage="quality",
                event="bust_volume_review",
                status="blocked",
                data={},
            )
            append_record_event(
                quality_dir,
                quality_id,
                stage="google_drive",
                event="not_attempted",
                status="not_attempted",
                data={},
            )
            append_record_event(
                quality_dir,
                quality_id,
                stage="publish",
                event="not_requested",
                status="not_requested",
                data={},
            )
            quality_failed = RUN_WORKSPACE.validate_finalize_contract(
                root,
                quality_id,
                route="xdy",
                duration=5,
                publish_mode="not_requested",
                outcome="quality_failed",
            )
            self.assertEqual(quality_failed["decision"], "pass", quality_failed["errors"])

            cancel_id = "20260717-120005"
            cancel_dir = make_run(root, cancel_id, "2026-07-17T12:00:05+08:00")
            append_record_event(
                cancel_dir, cancel_id, stage="run", event="cancelled", status="cancelled", data={}
            )
            append_record_event(
                cancel_dir,
                cancel_id,
                stage="google_drive",
                event="not_attempted",
                status="not_attempted",
                data={},
            )
            append_record_event(
                cancel_dir,
                cancel_id,
                stage="publish",
                event="not_requested",
                status="not_requested",
                data={},
            )
            cancelled = RUN_WORKSPACE.validate_finalize_contract(
                root,
                cancel_id,
                route="xdy",
                duration=5,
                publish_mode="not_requested",
                outcome="cancelled",
            )
            self.assertEqual(cancelled["decision"], "pass", cancelled["errors"])

            waiting = RUN_WORKSPACE.validate_finalize_contract(
                root,
                cancel_id,
                route="xdy",
                duration=5,
                publish_mode="awaiting_confirmation",
                outcome="cancelled",
            )
            self.assertEqual(waiting["decision"], "failed")
            self.assertTrue(any("等待态" in error for error in waiting["errors"]))

    def test_contract_cli_returns_zero_one_and_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            (root / "TOOLS").mkdir()
            (root / "TOOLS" / "run_record.py").touch()
            run_id = "20260717-120006"
            make_contract_run(root, run_id)
            base = [sys.executable, str(SCRIPT), "--root", str(root), "contract"]
            passed = subprocess.run(
                [
                    *base,
                    run_id,
                    "--phase",
                    "pre-generation",
                    "--route",
                    "xdysp",
                    "--duration",
                    "5",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(passed.returncode, 0, passed.stderr or passed.stdout)

            missing_input_id = "20260717-120007"
            make_run(root, missing_input_id, "2026-07-17T12:00:07+08:00")
            failed = subprocess.run(
                [
                    *base,
                    missing_input_id,
                    "--phase",
                    "pre-generation",
                    "--route",
                    "xdysp",
                    "--duration",
                    "5",
                    "--no-write-manifest",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(failed.returncode, 1, failed.stderr or failed.stdout)

            operational = subprocess.run(
                [
                    *base,
                    "20260717-129999",
                    "--phase",
                    "pre-generation",
                    "--route",
                    "xdysp",
                    "--duration",
                    "5",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(operational.returncode, 2, operational.stderr or operational.stdout)


if __name__ == "__main__":
    unittest.main()
