import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULES_DIR = PROJECT_ROOT / "DOCS" / "MODULES"
PROJECT_DOC = PROJECT_ROOT / "DOCS" / "PROJECT.md"
ROUTE_FILES = (
    PROJECT_DOC,
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "SKILLS" / "xdy" / "SKILL.md",
    PROJECT_ROOT / "SKILLS" / "xdysp" / "SKILL.md",
    *sorted(MODULES_DIR.glob("*.md")),
)
MODULE_REFERENCE_RE = re.compile(r"(?:DOCS/MODULES/)?((?:MAIN|AUX)_[A-Z0-9_]+\.md)")
LEGACY_MODULE_RE = re.compile(r"MODULE_\d{2}_[A-Z0-9_]+\.md")


class TestDocRoutes(unittest.TestCase):
    def test_expected_main_and_auxiliary_documents_exist(self):
        expected = {
            "MAIN_01_RUN_LIFECYCLE.md",
            "MAIN_02_CONTENT_PROMPT.md",
            "MAIN_03_VIDEO_DELIVERY.md",
            "MAIN_04_PUBLISH.md",
            "AUX_ENV_REPAIR.md",
            "AUX_COMMENT_REPLY.md",
        }
        actual = {path.name for path in MODULES_DIR.glob("*.md")}
        self.assertEqual(actual, expected)

    def test_all_routed_module_references_resolve(self):
        references = set()
        for path in ROUTE_FILES:
            references.update(MODULE_REFERENCE_RE.findall(path.read_text(encoding="utf-8")))

        self.assertTrue(references)
        missing = sorted(name for name in references if not (MODULES_DIR / name).is_file())
        self.assertEqual(missing, [])

    def test_routing_files_do_not_use_legacy_module_names(self):
        offenders = []
        for path in ROUTE_FILES:
            if LEGACY_MODULE_RE.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])

    def test_project_main_route_follows_execution_order(self):
        text = PROJECT_DOC.read_text(encoding="utf-8")
        names = [
            "MAIN_01_RUN_LIFECYCLE.md",
            "MAIN_02_CONTENT_PROMPT.md",
            "MAIN_03_VIDEO_DELIVERY.md",
            "MAIN_04_PUBLISH.md",
        ]
        positions = [text.index(name) for name in names]
        self.assertEqual(positions, sorted(positions))

    def test_contract_gates_are_executable_and_waiting_is_not_final(self):
        lifecycle = (MODULES_DIR / "MAIN_01_RUN_LIFECYCLE.md").read_text(encoding="utf-8")
        delivery = (MODULES_DIR / "MAIN_03_VIDEO_DELIVERY.md").read_text(encoding="utf-8")
        self.assertIn('xdy_flow.py complete "$RUN_ID"', lifecycle)
        self.assertIn('xdy_flow.py resume "$RUN_ID"', lifecycle)
        self.assertIn("不可变 `logs/contracts/generation-vN.json`", delivery)
        self.assertIn("等待发布确认时不能收尾", lifecycle)
        self.assertIn("原子追加唯一 `run/completed`", lifecycle)

    def test_routing_docs_use_project_virtualenv_python(self):
        offenders = []
        bare_python = re.compile(r"(?<![\w./-])python3(?:\s|$)")
        for path in ROUTE_FILES:
            if bare_python.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
