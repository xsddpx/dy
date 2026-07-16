import importlib.util
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))
SCRIPT = TOOLS_DIR / "select_wardrobe.py"
SPEC = importlib.util.spec_from_file_location("select_wardrobe", SCRIPT)
SELECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SELECTOR)


def write_png(path, width=9, height=16):
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )


def write_entry(root, identifier, *, prompt="黑色上衣搭配白色高腰短裙。", extra=None, width=9, height=16):
    directory = root / f"衣柜图-{identifier}"
    directory.mkdir()
    write_png(directory / f"衣柜图-{identifier}.png", width, height)
    (directory / "服装描述.md").write_text(
        f"# 衣柜图-{identifier}\n\n"
        f"- 图片：衣柜图-{identifier}.png\n"
        f"- 款式提示词：{prompt}\n",
        encoding="utf-8",
    )
    if extra:
        (directory / extra).touch()
    return directory


class SelectWardrobeTest(unittest.TestCase):
    def test_discover_valid_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_entry(root, "001")
            write_entry(root, "002")
            entries = SELECTOR.discover(root)
            self.assertEqual([entry.identifier for entry in entries], ["001", "002"])

    def test_entry_rejects_extra_file_and_non_nine_sixteen_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extra = write_entry(root, "001", extra="source.jpg")
            with self.assertRaises(SELECTOR.WardrobeError):
                SELECTOR.read_entry(extra)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wrong_ratio = write_entry(root, "001", width=10, height=16)
            with self.assertRaises(SELECTOR.WardrobeError):
                SELECTOR.read_entry(wrong_ratio)

    def test_entry_rejects_number_mismatch_and_empty_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = write_entry(root, "001")
            description = directory / "服装描述.md"
            description.write_text(description.read_text(encoding="utf-8").replace("# 衣柜图-001", "# 衣柜图-002"), encoding="utf-8")
            with self.assertRaises(SELECTOR.WardrobeError):
                SELECTOR.read_entry(directory)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = write_entry(root, "001", prompt=" ")
            with self.assertRaises(SELECTOR.WardrobeError):
                SELECTOR.read_entry(directory)

    def test_random_selection_avoids_previous_when_possible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = [SELECTOR.read_entry(write_entry(root, value)) for value in ("001", "002")]
            selected = SELECTOR.select_entry(entries, previous_id="001", seed=7)
            self.assertEqual(selected.identifier, "002")

    def test_single_entry_can_repeat_and_requested_id_is_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            entries = [SELECTOR.read_entry(write_entry(root, "001"))]
            self.assertEqual(SELECTOR.select_entry(entries, previous_id="001").identifier, "001")
            self.assertEqual(SELECTOR.select_entry(entries, wardrobe_id="衣柜图-001").identifier, "001")
            with self.assertRaises(SELECTOR.WardrobeError):
                SELECTOR.select_entry(entries, wardrobe_id="002")

    def test_previous_id_reads_latest_formal_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            for run_id, wardrobe_id in (("20260716-100000", "001"), ("20260716-110000", "002")):
                run_dir = temp_root / run_id
                run_dir.mkdir()
                event = {"stage": "wardrobe", "event": "selected", "data": {"wardrobe_id": wardrobe_id}}
                (run_dir / f"{run_id}-run-record.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
            self.assertEqual(SELECTOR.previous_wardrobe_id(temp_root), "002")

    def test_lock_entry_writes_paths_prompt_and_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wardrobe = root / "wardrobe"
            wardrobe.mkdir()
            entry = SELECTOR.read_entry(write_entry(wardrobe, "001"))
            run_dir = root / "TEMP" / "20260716-120000"
            run_dir.mkdir(parents=True)
            (run_dir / "20260716-120000-run-record.jsonl").write_text(
                json.dumps({"stage": "run", "event": "started"}) + "\n",
                encoding="utf-8",
            )
            record = SELECTOR.lock_entry(run_dir, entry)
            self.assertEqual((run_dir / "wardrobe-image-path.txt").read_text().strip(), str(entry.image))
            self.assertEqual((run_dir / "wardrobe-description.txt").read_text().strip(), entry.prompt)
            self.assertTrue(record.is_file())
            with self.assertRaises(SELECTOR.WardrobeError):
                SELECTOR.lock_entry(run_dir, entry)

    def test_lock_entry_requires_initialized_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wardrobe = root / "wardrobe"
            wardrobe.mkdir()
            entry = SELECTOR.read_entry(write_entry(wardrobe, "001"))
            with self.assertRaises(SELECTOR.WardrobeError):
                SELECTOR.lock_entry(root / "missing-run", entry)

    def test_empty_wardrobe_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SELECTOR.WardrobeError):
                SELECTOR.discover(Path(tmp))


if __name__ == "__main__":
    unittest.main()
