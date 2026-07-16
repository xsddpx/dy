import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parents[1]
SCRIPT = TOOLS_DIR / "prepare_wardrobe_image.py"
SPEC = importlib.util.spec_from_file_location("prepare_wardrobe_image", SCRIPT)
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


def write_png_header(path, width, height):
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )


class PrepareWardrobeImageTest(unittest.TestCase):
    def test_common_builtin_size_uses_minimal_native_crop(self):
        self.assertEqual(PREPARE.compute_crop(941, 1672), (936, 1664, 2, 4))

    def test_exact_nine_sixteen_is_unchanged(self):
        self.assertEqual(PREPARE.compute_crop(1080, 1920), (1080, 1920, 0, 0))

    def test_rejects_large_crop_or_small_output(self):
        with self.assertRaises(PREPARE.PrepareWardrobeImageError):
            PREPARE.compute_crop(1024, 1536)
        with self.assertRaises(PREPARE.PrepareWardrobeImageError):
            PREPARE.compute_crop(360, 640)

    def test_crop_limit_cannot_exceed_contract(self):
        with self.assertRaises(PREPARE.PrepareWardrobeImageError):
            PREPARE.compute_crop(941, 1672, max_crop_fraction=0.021)

    def test_prepare_rejects_existing_output_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            output = root / "output.png"
            write_png_header(source, 941, 1672)
            output.touch()
            with self.assertRaises(PREPARE.PrepareWardrobeImageError):
                PREPARE.prepare_image(source, output)

    def test_prepare_requires_ffmpeg(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            write_png_header(source, 941, 1672)
            with mock.patch.object(PREPARE.shutil, "which", return_value=None):
                with self.assertRaises(PREPARE.PrepareWardrobeImageError):
                    PREPARE.prepare_image(source, root / "output.png")

    def test_prepare_success_uses_only_native_crop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            output = root / "output.png"
            write_png_header(source, 941, 1672)

            def fake_run(command, **_kwargs):
                self.assertEqual(command[command.index("-vf") + 1], "crop=936:1664:2:4")
                self.assertNotIn("scale", " ".join(command))
                self.assertNotIn("pad", " ".join(command))
                write_png_header(Path(command[-1]), 936, 1664)
                return PREPARE.subprocess.CompletedProcess(command, 0, "", "")

            with mock.patch.object(PREPARE.shutil, "which", return_value="/usr/bin/ffmpeg"):
                with mock.patch.object(PREPARE.subprocess, "run", side_effect=fake_run):
                    self.assertEqual(PREPARE.prepare_image(source, output), (936, 1664))

            self.assertEqual(PREPARE.png_dimensions(output), (936, 1664))
            self.assertLessEqual(936, 941)
            self.assertLessEqual(1664, 1672)

    def test_prepare_failure_does_not_replace_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            output = root / "output.png"
            write_png_header(source, 941, 1672)
            output.write_bytes(b"keep")
            failed = PREPARE.subprocess.CompletedProcess([], 1, "", "failed")
            with mock.patch.object(PREPARE.shutil, "which", return_value="/usr/bin/ffmpeg"):
                with mock.patch.object(PREPARE.subprocess, "run", return_value=failed):
                    with self.assertRaises(PREPARE.PrepareWardrobeImageError):
                        PREPARE.prepare_image(source, output, overwrite=True)
            self.assertEqual(output.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
