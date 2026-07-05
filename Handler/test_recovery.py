import unittest

from Handler import recovery


class RecoveryClassificationTests(unittest.TestCase):
    def test_classify_locked_item_recovery_skips_ambiguous_workspace(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": "recoverable", "ambiguous": True},
            dependency_resolution={"status": "resolved"},
        )

        self.assertEqual(resolution["recovery_decision"], "skip")
        self.assertFalse(resolution["should_unlock"])

    def test_classify_locked_item_recovery_dependency_blocked(self):
        resolution = recovery.classify_locked_item_recovery(
            workspace_lifecycle={"lifecycle_classification": "recoverable", "ambiguous": False},
            dependency_resolution={"status": "blocked"},
        )

        self.assertEqual(resolution["recovery_decision"], "dependency-blocked")
        self.assertTrue(resolution["should_unlock"])
        self.assertTrue(resolution["should_dependency_block"])


if __name__ == "__main__":
    unittest.main()