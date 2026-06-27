import tempfile
import unittest

from Handler import workflow_classification


class WorkflowClassificationTests(unittest.TestCase):
    def test_validate_workflow_classification_accepts_json_payload(self):
        markdown_text = (
            "# Architecture Handoff\n\n"
            "```json\n"
            "{\n"
            "  \"workflow_classification_v1\": {\n"
            "    \"route\": \"state:ready-for-dev\",\n"
            "    \"confidence\": \"High\",\n"
            "    \"rationale\": \"Feature scope is implementation only\"\n"
            "  }\n"
            "}\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes={"state:ready-for-dev", "state:implementation-planning-changes-requested"},
        )

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["route"], "state:ready-for-dev")
        self.assertEqual(result["confidence"], "high")
        self.assertIn("Feature scope", result["rationale"])
        self.assertIsNone(result["diagnostic"])

    def test_validate_workflow_classification_accepts_yaml_payload(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification_v1:\n"
            "  route: state:ready-for-implementation-planning\n"
            "  confidence: medium\n"
            "  rationale: Route requires implementation planning\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes={"state:ready-for-implementation-planning"},
        )

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["route"], "state:ready-for-implementation-planning")
        self.assertEqual(result["confidence"], "medium")

    def test_validate_workflow_classification_reports_malformed_route(self):
        markdown_text = (
            "```json\n"
            "{\n"
            "  \"workflow_classification_v1\": {\n"
            "    \"route\": \"state:not-a-real-route\",\n"
            "    \"confidence\": \"low\",\n"
            "    \"rationale\": \"Example\"\n"
            "  }\n"
            "}\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes={"state:ready-for-dev"},
        )

        self.assertEqual(result["status"], "malformed")
        self.assertEqual(result["route"], "state:not-a-real-route")
        self.assertIn("known workflow state label", result["diagnostic"])

    def test_validate_workflow_classification_file_returns_absent_for_non_markdown_path(self):
        with tempfile.NamedTemporaryFile(suffix=".txt") as text_file:
            result = workflow_classification.validate_workflow_classification_file(
                text_file.name,
                valid_routes={"state:ready-for-dev"},
            )

        self.assertEqual(result["status"], "absent")
        self.assertIn("not a markdown artifact", result["diagnostic"])


if __name__ == "__main__":
    unittest.main()