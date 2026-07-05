import unittest

from Handler import recovery


class RecoveryClassificationTests(unittest.TestCase):
    def test_classify_locked_item_recovery_blocks_ambiguous_workspace(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": "recoverable", "ambiguous": True},
            dependency_resolution={"status": "resolved"},
            workflow_state={"primary_state_labels": ["state:ready-for-dev"], "unsupported_state_labels": []},
        )

        self.assertEqual(resolution["decision"], "blocked_unsafe")
        self.assertTrue(resolution["non_destructive"])
        self.assertIn("ambiguous", resolution["reason"])

    def test_classify_locked_item_recovery_dependency_resume_blocked(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": "recoverable", "ambiguous": False},
            dependency_resolution={"status": "blocked"},
            workflow_state={"primary_state_labels": ["state:ready-for-dev"], "unsupported_state_labels": []},
        )

        self.assertEqual(resolution["decision"], "dependency_resume_blocked")
        self.assertTrue(resolution["non_destructive"])
        self.assertIn("dependencies", resolution["recommended_action"])

    def test_classify_locked_item_recovery_safe_resume(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": "ready", "ambiguous": False},
            dependency_resolution={"declared": True, "status": "resolved"},
            workflow_state={"primary_state_labels": ["state:ready-for-dev"], "unsupported_state_labels": []},
        )

        self.assertEqual(resolution["decision"], "safe_resume")
        self.assertEqual(resolution["blockers"], [])

    def test_classify_locked_item_recovery_recoverable_requires_human(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": "recoverable", "ambiguous": False},
            dependency_resolution={"declared": False, "status": "not-declared"},
            workflow_state={"primary_state_labels": ["state:ready-for-dev"], "unsupported_state_labels": []},
        )

        self.assertEqual(resolution["decision"], "blocked_unsafe")
        self.assertTrue(resolution["non_destructive"])

    def test_classify_locked_item_recovery_inconclusive_with_resolved_dependencies_needs_human(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": None, "ambiguous": False},
            dependency_resolution={"declared": True, "status": "resolved"},
            workflow_state={"primary_state_labels": ["state:ready-for-dev"], "unsupported_state_labels": []},
        )

        self.assertEqual(resolution["decision"], "stale_lock_needs_human")
        self.assertTrue(resolution["non_destructive"])

    def test_classify_locked_item_recovery_blocks_multiple_primary_state_labels(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": "ready", "ambiguous": False},
            dependency_resolution={"declared": True, "status": "resolved"},
            workflow_state={
                "primary_state_labels": ["state:ready-for-dev", "state:ready-for-review"],
                "unsupported_state_labels": [],
            },
        )

        self.assertEqual(resolution["decision"], "blocked_unsafe")
        self.assertIn("multiple primary workflow state labels", resolution["reason"])

    def test_classify_locked_item_recovery_blocks_unsupported_state_labels(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": "ready", "ambiguous": False},
            dependency_resolution={"declared": True, "status": "resolved"},
            workflow_state={
                "primary_state_labels": ["state:ready-for-dev"],
                "unsupported_state_labels": ["state:custom-unsupported"],
            },
        )

        self.assertEqual(resolution["decision"], "blocked_unsafe")
        self.assertIn("unsupported workflow state", resolution["reason"])


if __name__ == "__main__":
    unittest.main()