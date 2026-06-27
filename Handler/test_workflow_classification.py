import tempfile
import unittest

from Handler import workflow_classification


class WorkflowClassificationTests(unittest.TestCase):
    def test_validate_workflow_classification_accepts_valid_yaml_block(self):
        markdown_text = (
            "# Architecture Handoff\n\n"
            "```yaml\n"
            "workflow_classification:\n"
            "  implementation_complexity: medium\n"
            "  safety_risk: low\n"
            "  slice_size: single_slice\n"
            "  architecture_uncertainty: minor\n"
            "  routing_recommendation: continue\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes={"state:ready-for-dev", "state:implementation-planning-changes-requested"},
        )

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["implementation_complexity"], "medium")
        self.assertEqual(result["safety_risk"], "low")
        self.assertEqual(result["slice_size"], "single_slice")
        self.assertEqual(result["architecture_uncertainty"], "minor")
        self.assertEqual(result["routing_recommendation"], "continue")
        self.assertIsNone(result["diagnostic"])

    def test_validate_workflow_classification_returns_absent_when_block_missing(self):
        markdown_text = (
            "# Implementation Plan\n\n"
            "No advisory classification was included in this artifact.\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "absent")
        self.assertIsNone(result["diagnostic"])

    def test_validate_workflow_classification_reports_unsupported_value(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification:\n"
            "  implementation_complexity: medium\n"
            "  safety_risk: critical\n"
            "  slice_size: single_slice\n"
            "  architecture_uncertainty: minor\n"
            "  routing_recommendation: continue\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "malformed")
        self.assertIn("unsupported value for `safety_risk`", result["diagnostic"])

    def test_validate_workflow_classification_reports_unsupported_field(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification:\n"
            "  implementation_complexity: medium\n"
            "  safety_risk: low\n"
            "  slice_size: single_slice\n"
            "  architecture_uncertainty: minor\n"
            "  routing_recommendation: continue\n"
            "  reviewer_depth: deep\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "malformed")
        self.assertIn("unsupported workflow_classification field", result["diagnostic"])
        self.assertIn("reviewer_depth", result["diagnostic"])

    def test_validate_workflow_classification_reports_missing_required_field(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification:\n"
            "  implementation_complexity: medium\n"
            "  safety_risk: low\n"
            "  slice_size: single_slice\n"
            "  architecture_uncertainty: minor\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "malformed")
        self.assertIn("missing required workflow_classification field", result["diagnostic"])
        self.assertIn("routing_recommendation", result["diagnostic"])

    def test_validate_workflow_classification_reports_malformed_indentation(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification:\n"
            " implementation_complexity: medium\n"
            "  safety_risk: low\n"
            "  slice_size: single_slice\n"
            "  architecture_uncertainty: minor\n"
            "  routing_recommendation: continue\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "malformed")
        self.assertIn("malformed indentation", result["diagnostic"])

    def test_validate_workflow_classification_reports_duplicate_blocks(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification:\n"
            "  implementation_complexity: low\n"
            "  safety_risk: low\n"
            "  slice_size: single_slice\n"
            "  architecture_uncertainty: none\n"
            "  routing_recommendation: continue\n"
            "```\n\n"
            "```yaml\n"
            "workflow_classification:\n"
            "  implementation_complexity: high\n"
            "  safety_risk: high\n"
            "  slice_size: multi_slice\n"
            "  architecture_uncertainty: significant\n"
            "  routing_recommendation: escalate\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "malformed")
        self.assertIn("multiple workflow_classification blocks", result["diagnostic"])

    def test_validate_workflow_classification_reports_inline_scalar_root(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification: continue\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "malformed")
        self.assertIn("root must be a nested mapping", result["diagnostic"])

    def test_validate_workflow_classification_reports_inline_mapping_root(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification: {implementation_complexity: medium}\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "malformed")
        self.assertIn("root must be a nested mapping", result["diagnostic"])

    def test_validate_workflow_classification_reports_inline_sequence_root(self):
        markdown_text = (
            "```yaml\n"
            "workflow_classification: []\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "malformed")
        self.assertIn("root must be a nested mapping", result["diagnostic"])

    def test_validate_workflow_classification_rejects_nested_root_key(self):
        markdown_text = (
            "```yaml\n"
            "metadata:\n"
            "  workflow_classification:\n"
            "    implementation_complexity: medium\n"
            "    safety_risk: low\n"
            "    slice_size: single_slice\n"
            "    architecture_uncertainty: minor\n"
            "    routing_recommendation: continue\n"
            "```\n"
        )

        result = workflow_classification.validate_workflow_classification(
            markdown_text,
            valid_routes=set(),
        )

        self.assertEqual(result["status"], "absent")
        self.assertIsNone(result["diagnostic"])

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