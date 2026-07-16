import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "select_fixed_environment.py"
SPEC = importlib.util.spec_from_file_location("select_fixed_environment", SCRIPT)
SELECTOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SELECTOR)


class SelectFixedEnvironmentTest(unittest.TestCase):
    def test_discover_only_accepts_numbered_formal_pngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in (
                "anna-room-01.png",
                "anna-room-02.png",
                "anna-room-before-20260712.png",
                "anna-room.png",
                "anna-room-03.jpg",
            ):
                (directory / name).touch()

            self.assertEqual(
                [path.name for path in SELECTOR.discover(directory)],
                ["anna-room-01.png", "anna-room-02.png"],
            )

    def test_seeded_selection_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in ("anna-room-01.png", "anna-room-02.png", "anna-room-03.png"):
                (directory / name).touch()

            first = SELECTOR.select_environment(directory, seed=17)
            second = SELECTOR.select_environment(directory, seed=17)
            self.assertEqual(first, second)

    def test_empty_directory_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                SELECTOR.select_environment(Path(tmp))

    def test_first_selection_writes_environment_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "environments"
            directory.mkdir()
            for name in ("anna-room-01.png", "anna-room-02.png"):
                (directory / name).touch()
            output = root / "run" / "environment-path.txt"
            expected = SELECTOR.select_environment(directory, seed=17)

            code = SELECTOR.main(
                [
                    "--directory",
                    str(directory),
                    "--out",
                    str(output),
                    "--seed",
                    "17",
                ]
            )

            self.assertEqual(code, 0)
            self.assertEqual(output.read_text(encoding="utf-8"), str(expected) + "\n")

    def test_existing_environment_lock_is_not_reselected_or_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "environments"
            directory.mkdir()
            (directory / "anna-room-01.png").touch()
            output = root / "environment-path.txt"
            original = "/locked/anna-room-99.png\n"
            output.write_text(original, encoding="utf-8")

            with mock.patch.object(SELECTOR, "select_environment") as select_environment:
                with self.assertRaisesRegex(
                    SystemExit,
                    "refusing to overwrite existing environment lock",
                ):
                    SELECTOR.main(
                        [
                            "--directory",
                            str(directory),
                            "--out",
                            str(output),
                        ]
                    )

            select_environment.assert_not_called()
            self.assertEqual(output.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
