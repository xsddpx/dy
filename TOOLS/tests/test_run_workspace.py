import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
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
        "人物："
        + lint.PROMPT_CONFIG["person"]
        + "视频约束："
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
    (directory / f"vid-prompt-v{prompt_version}.txt").write_text(valid_prompt() + "\n", encoding="utf-8")
    (directory / "environment-path.txt").write_text(str(environment.resolve()) + "\n", encoding="utf-8")
    return directory


class RunWorkspaceTest(unittest.TestCase):
    def test_parse_time_normalizes_naive_and_utc(self):
        naive = RUN_WORKSPACE.parse_time("2026-07-12T08:09:10")
        utc = RUN_WORKSPACE.parse_time("2026-07-12T00:09:10Z")
        self.assertEqual(naive, utc)
        self.assertEqual(RUN_WORKSPACE.canonical_base(utc), "20260712-080910")


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
            (directory / "vid-prompt-v1.txt").write_text(changed + "\n", encoding="utf-8")
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
