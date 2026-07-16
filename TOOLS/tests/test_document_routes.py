import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_NAMES = [
    "01_RUN_INIT.md",
    "02_CONTENT_AND_PROMPT.md",
    "03_VIDEO_GENERATION.md",
    "04_REVIEW_AND_UPLOAD.md",
    "05_PUBLISH.md",
    "06_RUN_FINALIZE.md",
]


class DocumentRoutesTest(unittest.TestCase):
    def test_pipeline_filenames_are_the_execution_order(self):
        pipeline = PROJECT_ROOT / "DOCS" / "PIPELINE"
        self.assertEqual(
            sorted(path.name for path in pipeline.glob("*.md")),
            PIPELINE_NAMES,
        )

        project = (PROJECT_ROOT / "DOCS" / "PROJECT.md").read_text(encoding="utf-8")
        positions = []
        for name in PIPELINE_NAMES:
            reference = f"PIPELINE/{name}"
            self.assertIn(reference, project)
            positions.append(project.index(reference))
        self.assertEqual(positions, sorted(positions))

    def test_independent_workflows_and_runbooks_exist(self):
        expected = [
            "DOCS/WORKFLOWS/WARDROBE_INGEST.md",
            "DOCS/WORKFLOWS/COMMENT_TRIAGE_AND_REPLY.md",
            "DOCS/RUNBOOKS/ENVIRONMENT_REPAIR.md",
            "DOCS/RUNBOOKS/ENVIRONMENT_CASES.md",
        ]
        for relative in expected:
            self.assertTrue((PROJECT_ROOT / relative).is_file(), relative)

    def test_active_docs_have_no_legacy_module_or_prompt_route(self):
        self.assertFalse((PROJECT_ROOT / "DOCS" / "MODULES").exists())
        roots = [
            PROJECT_ROOT / "AGENTS.md",
            PROJECT_ROOT / "README.md",
            PROJECT_ROOT / "DOCS",
            PROJECT_ROOT / "SKILLS",
        ]
        files = []
        for root in roots:
            if root.is_file():
                files.append(root)
            else:
                files.extend(path for path in root.rglob("*") if path.suffix in {".md", ".yaml"})

        forbidden = [
            "DOCS/MODULES",
            "MODULE_01_REFERENCE",
            "MODULE_02_DREAMINA_VIDEO",
            "MODULE_03_PUBLISH",
            "MODULE_04_RECORDS",
            "MODULE_05_WARDROBE_IMAGE_ASSETS",
            "MODULE_06_COMMENT_REPLY",
            "grid-prompt",
            "prompt_lint.py derive",
            "python3 TOOLS/",
        ]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for term in forbidden:
                self.assertNotIn(term, text, f"{term} found in {path}")

    def test_drive_success_delivery_template_does_not_embed_an_image(self):
        workflow = (
            PROJECT_ROOT / "DOCS" / "WORKFLOWS" / "WARDROBE_INGEST.md"
        ).read_text(encoding="utf-8")
        success_template = workflow.split("入库成功且 Drive 上传完成后", 1)[1].split(
            "附上 Drive 链接后", 1
        )[0]
        self.assertIn("Google Drive 链接", success_template)
        self.assertNotIn("![", success_template)

    def test_local_markdown_links_resolve(self):
        files = [PROJECT_ROOT / "README.md", *(PROJECT_ROOT / "DOCS").rglob("*.md")]
        for path in files:
            text = path.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if target.startswith(("http://", "https://", "#", "/")):
                    continue
                target_path = target.split("#", 1)[0]
                self.assertTrue(
                    (path.parent / target_path).resolve().exists(),
                    f"broken link in {path}: {target}",
                )


if __name__ == "__main__":
    unittest.main()
