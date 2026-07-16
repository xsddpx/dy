import importlib.util
import json
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


class RunWorkspaceTest(unittest.TestCase):
    def test_run_id_only_allows_no_suffix_or_01_through_99(self):
        base = "20260712-080910"
        for run_id in (base, f"{base}-01", f"{base}-09", f"{base}-10", f"{base}-99"):
            with self.subTest(run_id=run_id):
                self.assertIsNotNone(RUN_WORKSPACE.RUN_ID_RE.fullmatch(run_id))
        for run_id in (f"{base}-00", f"{base}-1", f"{base}-100"):
            with self.subTest(run_id=run_id):
                self.assertIsNone(RUN_WORKSPACE.RUN_ID_RE.fullmatch(run_id))

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
                    "local_temp": f"TEMP/{old_id}/vid-prompt-v1.txt",
                    "local_output": f"OUTPUT/{old_id}.mp4",
                    "file_name": f"{old_id}.mp4",
                    "url": "https://drive.google.com/file/d/unchanged",
                },
            }
            directory = make_run(root, old_id, "2026-07-12T08:09:10", external)
            (directory / "vid-prompt-v1.txt").write_text("prompt\n", encoding="utf-8")
            output = root / "OUTPUT" / f"{old_id}.mp4"
            output.write_bytes(b"unchanged-video")
            original_hash = RUN_WORKSPACE.sha256_file(output)

            plan = RUN_WORKSPACE.build_migration_plan(root)
            manifest = RUN_WORKSPACE.apply_migration(root, plan)
            new_id = plan["entries"][0]["new_id"]
            new_record = root / "TEMP" / new_id / f"{new_id}-run-record.jsonl"
            text = new_record.read_text(encoding="utf-8")
            self.assertIn(f'"run_id": "{new_id}"', text)
            self.assertIn(f"TEMP/{new_id}/vid-prompt-v1.txt", text)
            self.assertIn(f"OUTPUT/{new_id}.mp4", text)
            self.assertIn(f'"file_name": "{old_id}.mp4"', text)
            self.assertIn("https://drive.google.com/file/d/unchanged", text)
            self.assertEqual(RUN_WORKSPACE.sha256_file(root / "OUTPUT" / f"{new_id}.mp4"), original_hash)
            self.assertEqual(RUN_WORKSPACE.audit_workspace(root)["decision"], "pass")

            RUN_WORKSPACE.rollback_migration(root, manifest)
            restored_record = root / "TEMP" / old_id / f"{old_id}-run-record.jsonl"
            self.assertTrue(restored_record.is_file())
            self.assertIn(f"TEMP/{old_id}/vid-prompt-v1.txt", restored_record.read_text(encoding="utf-8"))
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
            self.assertEqual(result["decision"], "failed")
            self.assertTrue(
                any(
                    "运行记录缺失：TEMP/20260712-080910/20260712-080910-run-record.jsonl" in error
                    for error in result["errors"]
                )
            )
            self.assertTrue(any("运行目录与记录文件名不一致" in error for error in result["errors"]))

    def test_audit_rejects_canonical_directory_without_exact_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            (root / "TEMP" / "20260712-080910-01").mkdir()
            result = RUN_WORKSPACE.audit_workspace(root)
            self.assertEqual(result["decision"], "failed")
            self.assertTrue(
                any(
                    "运行记录缺失：TEMP/20260712-080910-01/20260712-080910-01-run-record.jsonl"
                    in error
                    for error in result["errors"]
                )
            )

    def test_audit_rejects_zero_suffix_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            (root / "TEMP" / "20260712-080910-00").mkdir()
            result = RUN_WORKSPACE.audit_workspace(root)
            self.assertEqual(result["decision"], "failed")
            self.assertTrue(any("非法正式运行目录" in error for error in result["errors"]))

    def test_audit_allows_explicit_auxiliary_directory_with_timestamp_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            directory = root / "TEMP" / "20260712-080910"
            directory.mkdir()
            (directory / RUN_WORKSPACE.AUXILIARY_MARKER).write_text(
                "not a video run workspace\n",
                encoding="utf-8",
            )
            (directory / "wardrobe-assets").mkdir()

            result = RUN_WORKSPACE.audit_workspace(root)

            self.assertEqual(result["decision"], "pass")
            self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
