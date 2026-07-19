import copy
import sys
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parents[1]
PROJECT_ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import workflow_config


class WorkflowConfigTest(unittest.TestCase):
    def config(self):
        value = copy.deepcopy(workflow_config.load_workflow_config())
        value.pop("_path", None)
        return value

    def test_person_template_must_keep_chest_volume_anchors(self):
        for phrase in workflow_config.REQUIRED_PERSON_BODY_PHRASES:
            with self.subTest(phrase=phrase):
                config = self.config()
                config["prompt"]["person"] = config["prompt"]["person"].replace(phrase, "")
                with self.assertRaisesRegex(workflow_config.WorkflowConfigError, "胸部体量一致性锚点"):
                    workflow_config.validate_workflow_config(config, PROJECT_ROOT)

    def test_quality_role_proxy_contract_is_validated(self):
        variants = (
            ("role_proxy_top_ratio", 0),
            ("role_proxy_top_ratio", 1.1),
            ("role_proxy_max_width", 320),
        )
        for key, value in variants:
            with self.subTest(key=key, value=value):
                config = self.config()
                config["quality"][key] = value
                with self.assertRaises(workflow_config.WorkflowConfigError):
                    workflow_config.validate_workflow_config(config, PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
