import os
import tempfile
import unittest
from unittest.mock import patch

import Handler.workflow_parity as workflow_parity


class WorkflowParityTests(unittest.TestCase):
    def test_evaluate_workflow_governance_parity_passes_for_aligned_inventory(self):
        canonical_states = {
            "state:ready": {
                "description": "Ready",
                "color": "1D76DB",
                "dispatch": {
                    "agent": "codex",
                    "mode": "developer",
                    "model": "gpt-5.5",
                    "effort": "High",
                },
            },
            "state:blocked": {
                "description": "Blocked",
                "color": "D73A4A",
                "human_owned": True,
                "terminal": True,
            },
            "state:agent-in-progress": {
                "description": "Locked",
                "color": "8250DF",
            },
        }
        required_labels = {
            "state:ready": {"description": "Ready", "color": "1D76DB"},
            "state:blocked": {"description": "Blocked", "color": "D73A4A"},
            "state:agent-in-progress": {"description": "Locked", "color": "8250DF"},
        }
        label_map = {
            "state:ready": {
                "agent": "codex",
                "mode": "developer",
                "model": "gpt-5.5",
                "effort": "High",
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            doc_path = os.path.join(temp_dir, "workflow.md")
            with open(doc_path, "w", encoding="utf-8") as workflow_doc:
                workflow_doc.write("state:ready\nstate:blocked\nstate:agent-in-progress\n")

            with patch.object(workflow_parity, "WORKFLOW_STATES", canonical_states):
                with patch.object(workflow_parity, "REQUIRED_WORKFLOW_LABELS", required_labels):
                    with patch.object(workflow_parity, "LABEL_MAP", label_map):
                        parity = workflow_parity.evaluate_workflow_governance_parity(
                            repo_root=temp_dir,
                            documentation_paths=["workflow.md"],
                        )

        self.assertTrue(parity["ok"])
        self.assertEqual(parity["errors"], [])

    def test_evaluate_workflow_governance_parity_reports_missing_label_metadata(self):
        canonical_states = {
            "state:ready": {
                "description": "Ready",
                "color": "1D76DB",
                "dispatch": {
                    "agent": "codex",
                    "mode": "developer",
                    "model": "gpt-5.5",
                    "effort": "High",
                },
            },
            "state:blocked": {"description": "Blocked", "color": "D73A4A"},
        }
        required_labels = {
            "state:ready": {"description": "Ready", "color": "1D76DB"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            doc_path = os.path.join(temp_dir, "workflow.md")
            with open(doc_path, "w", encoding="utf-8") as workflow_doc:
                workflow_doc.write("state:ready\nstate:blocked\n")

            with patch.object(workflow_parity, "WORKFLOW_STATES", canonical_states):
                with patch.object(workflow_parity, "REQUIRED_WORKFLOW_LABELS", required_labels):
                    with patch.object(workflow_parity, "LABEL_MAP", {"state:ready": canonical_states["state:ready"]["dispatch"]}):
                        parity = workflow_parity.evaluate_workflow_governance_parity(
                            repo_root=temp_dir,
                            documentation_paths=["workflow.md"],
                        )

        self.assertFalse(parity["ok"])
        self.assertTrue(any("required label metadata missing" in error for error in parity["errors"]))

    def test_evaluate_workflow_governance_parity_reports_extra_documented_state(self):
        canonical_states = {
            "state:ready": {
                "description": "Ready",
                "color": "1D76DB",
                "dispatch": {
                    "agent": "codex",
                    "mode": "developer",
                    "model": "gpt-5.5",
                    "effort": "High",
                },
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            doc_path = os.path.join(temp_dir, "workflow.md")
            with open(doc_path, "w", encoding="utf-8") as workflow_doc:
                workflow_doc.write("state:ready\nstate:legacy\n")

            with patch.object(workflow_parity, "WORKFLOW_STATES", canonical_states):
                with patch.object(
                    workflow_parity,
                    "REQUIRED_WORKFLOW_LABELS",
                    {"state:ready": {"description": "Ready", "color": "1D76DB"}},
                ):
                    with patch.object(workflow_parity, "LABEL_MAP", {"state:ready": canonical_states["state:ready"]["dispatch"]}):
                        parity = workflow_parity.evaluate_workflow_governance_parity(
                            repo_root=temp_dir,
                            documentation_paths=["workflow.md"],
                        )

        self.assertFalse(parity["ok"])
        self.assertTrue(any("unsupported by canonical workflow inventory" in error for error in parity["errors"]))
        self.assertIn("state:legacy", parity["details"]["unsupported_documented_states"])

    def test_evaluate_workflow_governance_parity_reports_contradictory_dispatch_human_ownership(self):
        canonical_states = {
            "state:ready": {
                "description": "Ready",
                "color": "1D76DB",
                "human_owned": True,
                "dispatch": {
                    "agent": "codex",
                    "mode": "developer",
                    "model": "gpt-5.5",
                    "effort": "High",
                },
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            doc_path = os.path.join(temp_dir, "workflow.md")
            with open(doc_path, "w", encoding="utf-8") as workflow_doc:
                workflow_doc.write("state:ready\n")

            with patch.object(workflow_parity, "WORKFLOW_STATES", canonical_states):
                with patch.object(
                    workflow_parity,
                    "REQUIRED_WORKFLOW_LABELS",
                    {"state:ready": {"description": "Ready", "color": "1D76DB"}},
                ):
                    with patch.object(workflow_parity, "LABEL_MAP", {"state:ready": canonical_states["state:ready"]["dispatch"]}):
                        parity = workflow_parity.evaluate_workflow_governance_parity(
                            repo_root=temp_dir,
                            documentation_paths=["workflow.md"],
                        )

        self.assertFalse(parity["ok"])
        self.assertTrue(any("human-owned and dispatchable" in error for error in parity["errors"]))


if __name__ == "__main__":
    unittest.main()