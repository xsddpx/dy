from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import prompt_lint
import xdy_flow
from workflow_config import SLOW_ACTION_PHRASES


def make_root(base: Path) -> Path:
    root = base / "repo"
    (root / "TEMP").mkdir(parents=True)
    (root / "OUTPUT").mkdir()
    (root / "TOOLS").mkdir()
    (root / "TOOLS" / "run_record.py").touch()
    for relative in (
        "MATERIAL/fixed-role/anna.png",
        "MATERIAL/anna-wardrobe.md",
        "MATERIAL/publish-tag-pool.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    environment = root / "MATERIAL/fixed-environment/anna-room-01.png"
    environment.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "MATERIAL/fixed-environment/anna-room-01.png", environment)
    return root


def make_video(root: Path, duration: int = 5) -> Path:
    path = root / "fixture.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg"),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=720x1280:r=24",
            "-t",
            str(duration),
            str(path),
        ],
        check=True,
    )
    return path


def make_fake_dreamina(root: Path, video: Path | None, *, tns: bool = False) -> tuple[Path, Path]:
    script = root / "fake_dreamina.py"
    counter = root / "submit-count.txt"
    query_body = (
        'print(json.dumps({"submit_id": submit_id, "gen_status": "fail", "fail_reason": "pre-TNS check did not pass"}))'
        if tns
        else (
            f'd=Path(next(x.split("=",1)[1] for x in a if x.startswith("--download_dir="))); '
            f'd.mkdir(parents=True,exist_ok=True); shutil.copy2({str(video)!r},d/"result.mp4"); '
            'print(json.dumps({"submit_id": submit_id, "gen_status": "success"}))'
        )
    )
    script.write_text(
        f"""#!/usr/bin/env python3
import json, shutil, sys
from pathlib import Path
a=sys.argv[1:]
counter=Path({str(counter)!r})
if a[0]=="list_task":
    print("[]")
elif a[0]=="multimodal2video":
    count=int(counter.read_text() if counter.exists() else "0")+1
    counter.write_text(str(count))
    print(json.dumps({{"submit_id":f"fake-{{count}}","gen_status":"querying"}}))
elif a[0]=="query_result":
    submit_id=next(x.split("=",1)[1] for x in a if x.startswith("--submit_id="))
    {query_body}
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, counter


def make_fake_publish_adapter(root: Path, *, douyin: str = "published", kuaishou: str = "published") -> tuple[Path, Path]:
    script = root / "fake_publish_adapter.py"
    counter = root / "publish-count.txt"
    script.write_text(
        f"""#!/usr/bin/env python3
import json, sys
from pathlib import Path
a=sys.argv[1:]
out=Path(a[a.index("--out-dir")+1]); out.mkdir(parents=True,exist_ok=True)
counter=Path({str(counter)!r}); counter.write_text(str(int(counter.read_text() if counter.exists() else "0")+1))
platforms=[
    {{"platform":"douyin","decision":{douyin!r},"report_json":str(out/"douyin-publish-report.json"),"requested_tags":[],"applied_tags":[]}},
    {{"platform":"kuaishou","decision":{kuaishou!r},"report_json":str(out/"kuaishou-publish-report.json"),"requested_tags":[],"applied_tags":[]}},
]
decision="published" if all(x["decision"]=="published" for x in platforms) else "blocked"
report={{"decision":decision,"platforms":platforms}}
(out/"publish-both-report.json").write_text(json.dumps(report))
print(json.dumps(report))
sys.exit(0 if decision=="published" else 1)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, counter


class XdyFlowTest(unittest.TestCase):
    def test_every_wardrobe_action_prompt_passes_and_speed_is_fixed(self):
        entries = xdy_flow.parse_wardrobe(ROOT / "MATERIAL/anna-wardrobe.md")
        for wardrobe, text in entries.items():
            for action in xdy_flow.PROMPT["actions"]:
                prompt = xdy_flow.build_prompt(text, action)
                result = prompt_lint.lint_text(prompt, Path(f"{wardrobe}-{action}.txt"))
                self.assertEqual(result["decision"], "pass", (wardrobe, action, result["findings"]))
                self.assertIn("全程保持正常速度，不使用慢动作", prompt)
                action_text = xdy_flow.PROMPT["actions"][action]["text"].lower()
                for phrase in SLOW_ACTION_PHRASES:
                    self.assertNotIn(phrase.lower(), action_text, (action, phrase))
        self.assertEqual(
            {key: value["preferred_duration"] for key, value in xdy_flow.PROMPT["actions"].items()},
            {"01": 7, "02": 6, "03": 5, "04": 6},
        )

    def test_xdysp_end_to_end_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            video = make_video(root)
            fake, counter = make_fake_dreamina(root, video)
            run_id = xdy_flow.initialize_run(
                root,
                route="xdysp",
                publish_mode="default",
                source="test",
                theme=None,
                wardrobe="01",
                environment=None,
                action="03",
                duration=5,
                seed=1,
                title=None,
                description=None,
                tags=None,
            )
            first = xdy_flow.resume_run(root, run_id, dreamina_bin=str(fake), poll_timeout=10)
            self.assertEqual(first["next_action"], "upload_drive")
            self.assertEqual(counter.read_text(), "1")
            xdy_flow.record_drive(root, run_id, {"status": "failed", "reason": "fake", "needs_retry": True})
            completed = xdy_flow.resume_run(root, run_id, dreamina_bin=str(fake), poll_timeout=10)
            self.assertTrue(completed["terminal"])
            repeated = xdy_flow.resume_run(root, run_id, dreamina_bin=str(fake), poll_timeout=10)
            self.assertTrue(repeated["terminal"])
            xdy_flow.complete_run(root, run_id)
            self.assertEqual(counter.read_text(), "1")
            record = root / "TEMP" / run_id / f"{run_id}-run-record.jsonl"
            events = xdy_flow.read_events(record)
            self.assertEqual(sum(item.get("event") == "completed" for item in events), 1)
            self.assertLess(record.stat().st_size, 10_000)

    def test_tns_retries_only_change_wardrobe_and_stop_at_v5(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            fake, counter = make_fake_dreamina(root, None, tns=True)
            run_id = xdy_flow.initialize_run(
                root,
                route="xdysp",
                publish_mode="not_requested",
                source="test",
                theme=None,
                wardrobe="01",
                environment=None,
                action="02",
                duration=6,
                seed=2,
                title=None,
                description=None,
                tags=None,
            )
            state = xdy_flow.resume_run(root, run_id, dreamina_bin=str(fake), poll_timeout=10)
            self.assertTrue(state["terminal"])
            self.assertEqual(counter.read_text(), "5")
            events = xdy_flow.read_events(root / "TEMP" / run_id / f"{run_id}-run-record.jsonl")
            prompts = [item for item in events if item.get("stage") == "content" and item.get("event") == "prompt_version"]
            self.assertEqual([item["data"]["version"] for item in prompts], ["v1", "v2", "v3", "v4", "v5"])
            self.assertEqual(len({item["data"]["wardrobe"] for item in prompts}), 5)
            for item in prompts[1:]:
                self.assertEqual(item["data"]["inherited_action"], "02")
                self.assertEqual(item["data"]["inherited_duration"], 6)
            terminal = xdy_flow.latest_non_artifact(events, "dreamina")
            self.assertEqual(terminal["event"], "failed")
            self.assertEqual(terminal["data"]["reason_category"], "tns")

    def test_record_drive_rejects_unverified_root_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            video = make_video(root)
            fake, _ = make_fake_dreamina(root, video)
            run_id = xdy_flow.initialize_run(
                root,
                route="xdysp",
                publish_mode="not_requested",
                source="test",
                theme=None,
                wardrobe="01",
                environment=None,
                action="03",
                duration=5,
                seed=3,
                title=None,
                description=None,
                tags=None,
            )
            xdy_flow.resume_run(root, run_id, dreamina_bin=str(fake), poll_timeout=10)
            output = root / "OUTPUT" / f"{run_id}.mp4"
            with self.assertRaises(xdy_flow.FlowError):
                xdy_flow.record_drive(
                    root,
                    run_id,
                    {
                        "status": "uploaded",
                        "file_name": output.name,
                        "mime_type": "video/mp4",
                        "size": output.stat().st_size,
                        "file_id": "fake",
                        "root_verified": False,
                    },
                )

    def test_default_publish_records_single_platform_failure_and_completes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            video = make_video(root)
            dreamina, _ = make_fake_dreamina(root, video)
            publisher, publish_counter = make_fake_publish_adapter(root, douyin="blocked")
            run_id = xdy_flow.initialize_run(
                root,
                route="xdy",
                publish_mode="default",
                source="test",
                theme=None,
                wardrobe="01",
                environment=None,
                action="03",
                duration=5,
                seed=4,
                title=None,
                description=None,
                tags=None,
            )
            waiting_quality = xdy_flow.resume_run(root, run_id, dreamina_bin=str(dreamina), poll_timeout=10)
            self.assertEqual(waiting_quality["next_action"], "review_quality")
            directory = root / "TEMP" / run_id
            checklist = json.loads((directory / "quality/quality-checklist.json").read_text(encoding="utf-8"))
            self.assertEqual(checklist["role_proxy_top_ratio"], 0.52)
            self.assertEqual(checklist["role_proxy_max_width"], 960)
            self.assertIn("相近朝向", checklist["role_reference_scope"])
            self.assertIn("三帧均无法判断", checklist["decision_rule"])
            role_proxy = root / checklist["role_proxy"]
            self.assertLess(role_proxy.stat().st_size, 100000)
            role_proxy_meta = xdy_flow.video_probe(root, role_proxy)
            self.assertGreaterEqual(role_proxy_meta["width"], 720)
            self.assertLess(role_proxy_meta["height"] / role_proxy_meta["width"], 0.6)
            xdy_flow.record_quality(root, run_id, "pass")
            xdy_flow.record_drive(root, run_id, {"status": "failed", "reason": "fake", "needs_retry": True})
            completed = xdy_flow.resume_run(root, run_id, publish_adapter=str(publisher))
            self.assertTrue(completed["terminal"])
            self.assertEqual(completed["terminal_status"], "failed")
            self.assertEqual(publish_counter.read_text(), "1")
            events = xdy_flow.read_events(root / "TEMP" / run_id / f"{run_id}-run-record.jsonl")
            both = xdy_flow.latest_non_artifact(events, "publish", "both_publish")
            self.assertEqual(both["status"], "blocked")
            self.assertEqual({item["platform"] for item in both["data"]["platforms"]}, {"douyin", "kuaishou"})
            run_completed = xdy_flow.latest_non_artifact(events, "run", "completed")
            self.assertEqual(run_completed["status"], "failed")
            self.assertEqual(run_completed["data"]["outcome"], "publish_failed")
            xdy_flow.resume_run(root, run_id, publish_adapter=str(publisher))
            self.assertEqual(publish_counter.read_text(), "1")

    def test_confirmation_can_be_cancelled_without_publishing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            video = make_video(root)
            dreamina, _ = make_fake_dreamina(root, video)
            publisher, publish_counter = make_fake_publish_adapter(root)
            run_id = xdy_flow.initialize_run(
                root,
                route="xdy",
                publish_mode="awaiting_confirmation",
                source="test",
                theme=None,
                wardrobe="02",
                environment=None,
                action="03",
                duration=5,
                seed=5,
                title=None,
                description=None,
                tags=None,
            )
            xdy_flow.resume_run(root, run_id, dreamina_bin=str(dreamina), poll_timeout=10)
            xdy_flow.record_quality(root, run_id, "pass")
            xdy_flow.record_drive(root, run_id, {"status": "failed", "reason": "fake", "needs_retry": True})
            waiting = xdy_flow.resume_run(root, run_id, publish_adapter=str(publisher))
            self.assertEqual(waiting["next_action"], "await_confirmation")
            completed = xdy_flow.resume_run(root, run_id, cancel_publish=True, publish_adapter=str(publisher))
            self.assertTrue(completed["terminal"])
            self.assertFalse(publish_counter.exists())

    def test_quality_blocked_closes_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            video = make_video(root)
            dreamina, _ = make_fake_dreamina(root, video)
            run_id = xdy_flow.initialize_run(
                root,
                route="xdy",
                publish_mode="default",
                source="test",
                theme=None,
                wardrobe="03",
                environment=None,
                action="03",
                duration=5,
                seed=6,
                title=None,
                description=None,
                tags=None,
            )
            xdy_flow.resume_run(root, run_id, dreamina_bin=str(dreamina), poll_timeout=10)
            xdy_flow.record_quality(root, run_id, "blocked")
            completed = xdy_flow.resume_run(root, run_id)
            self.assertTrue(completed["terminal"])
            self.assertFalse((root / "OUTPUT" / f"{run_id}.mp4").exists())

    def test_resume_uses_prepared_v2_after_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(Path(tmp))
            video = make_video(root)
            dreamina, counter = make_fake_dreamina(root, video)
            run_id = xdy_flow.initialize_run(
                root,
                route="xdysp",
                publish_mode="not_requested",
                source="test",
                theme=None,
                wardrobe="04",
                environment=None,
                action="03",
                duration=5,
                seed=7,
                title=None,
                description=None,
                tags=None,
            )
            directory, record = xdy_flow.run_paths(root, run_id)
            xdy_flow.append(record, run_id, "dreamina", "submitted", "querying", {"version": "v1", "submit_id": "old", "manifest": "old", "manifest_sha256": "old"})
            xdy_flow.append(record, run_id, "dreamina", "tns", "blocked", {"version": "v1", "submit_id": "old", "reason_category": "tns"})
            xdy_flow.create_next_prompt(root, directory, record, run_id, xdy_flow.read_events(record), 2)
            state = xdy_flow.resume_run(root, run_id, dreamina_bin=str(dreamina), poll_timeout=10)
            self.assertEqual(state["next_action"], "upload_drive")
            self.assertEqual(counter.read_text(), "1")
            self.assertTrue((directory / "vid-prompt-v2.txt").is_file())
            self.assertFalse((directory / "vid-prompt-v3.txt").exists())


if __name__ == "__main__":
    unittest.main()
