import unittest

import Handler.workspace_diagnostics as workspace_diagnostics


class WorkspaceDiagnosticsTests(unittest.TestCase):
    def _classification(self, **overrides):
        facts = {
            "workspace_path": "C:/repo-worktrees/owner-repo/issue-62",
            "current_branch": "circus/issue-62-workspace-diagnostics",
            "expected_branch": "circus/issue-62-workspace-diagnostics",
            "github_item": {"type": "issue", "number": 62, "state": "open"},
            "open_pr": {"number": 71, "url": "https://github.com/owner/repo/pull/71", "state": "open"},
        }
        classification = {
            "lifecycle_state": "recoverable",
            "reasons": ["dirty_worktree", "open_pr_exists"],
            "ambiguous": False,
            "facts": facts,
        }
        classification.update(overrides)
        return classification

    def test_build_workspace_lifecycle_diagnostic_consumes_classification_result(self):
        diagnostic = workspace_diagnostics.build_workspace_lifecycle_diagnostic(self._classification())

        self.assertEqual(diagnostic["state"], "recoverable")
        self.assertEqual(diagnostic["lifecycle_classification"], "recoverable")
        self.assertEqual(diagnostic["workspace"], "C:/repo-worktrees/owner-repo/issue-62")
        self.assertEqual(diagnostic["workspace_path"], "C:/repo-worktrees/owner-repo/issue-62")
        self.assertEqual(diagnostic["branch"], "circus/issue-62-workspace-diagnostics")
        self.assertEqual(diagnostic["branch_name"], "circus/issue-62-workspace-diagnostics")
        self.assertEqual(diagnostic["expected_branch"], "circus/issue-62-workspace-diagnostics")
        self.assertEqual(diagnostic["current_branch"], "circus/issue-62-workspace-diagnostics")
        self.assertEqual(diagnostic["issue"], "issue #62")
        self.assertEqual(diagnostic["issue_association"], {"type": "issue", "number": 62, "state": "open"})
        self.assertEqual(diagnostic["pr"], "PR #71 (open) https://github.com/owner/repo/pull/71")
        self.assertEqual(
            diagnostic["pr_association"],
            {"number": 71, "url": "https://github.com/owner/repo/pull/71", "state": "open"},
        )
        self.assertEqual(diagnostic["reasons"], ["dirty_worktree", "open_pr_exists"])
        self.assertEqual(diagnostic["classification_reasons"], ["dirty_worktree", "open_pr_exists"])
        self.assertFalse(diagnostic["ambiguous"])
        self.assertEqual(diagnostic["ambiguity_indicators"], [])
        self.assertEqual(diagnostic["recommended_action"], "Recover workspace before reassignment or cleanup.")
        self.assertEqual(diagnostic["recommended_operator_action"], "Recover workspace before reassignment or cleanup.")
        self.assertEqual(diagnostic["source"], "workspace_inventory.classify_workspace")

    def test_build_workspace_lifecycle_diagnostic_surfaces_ambiguous_blockers(self):
        diagnostic = workspace_diagnostics.build_workspace_lifecycle_diagnostic(
            self._classification(
                lifecycle_state="blocked-unsafe",
                reasons=["metadata_unavailable", "ambiguous_upstream", "unexpected_branch"],
                ambiguous=True,
                facts={"workspace_path": "C:/unknown", "current_branch": None, "expected_branch": "circus/issue-62"},
            )
        )

        self.assertEqual(diagnostic["state"], "blocked-unsafe")
        self.assertEqual(diagnostic["lifecycle_classification"], "blocked-unsafe")
        self.assertTrue(diagnostic["ambiguous"])
        self.assertEqual(diagnostic["branch"], "circus/issue-62")
        self.assertEqual(
            diagnostic["ambiguity_indicators"],
            ["ambiguous_upstream", "metadata_unavailable", "unexpected_branch"],
        )
        self.assertEqual(
            diagnostic["recommended_action"],
            "Inspect workspace manually before automation continues; do not clean up automatically.",
        )

    def test_retired_recommendation_preserves_workspace_until_cleanup_review(self):
        diagnostic = workspace_diagnostics.build_workspace_lifecycle_diagnostic(
            self._classification(lifecycle_state="retired", reasons=[])
        )

        self.assertEqual(
            diagnostic["recommended_action"],
            "Preserve until an explicit cleanup dry run and human review.",
        )
        self.assertEqual(
            diagnostic["recommended_operator_action"],
            "Preserve until an explicit cleanup dry run and human review.",
        )

    def test_render_workspace_lifecycle_report_outputs_human_readable_section(self):
        diagnostic = workspace_diagnostics.build_workspace_lifecycle_diagnostic(self._classification())

        report = workspace_diagnostics.render_workspace_lifecycle_report([diagnostic])

        self.assertIn("- workspace: `C:/repo-worktrees/owner-repo/issue-62`", report)
        self.assertIn("  - state: `recoverable`", report)
        self.assertIn("  - issue: `issue #62`", report)
        self.assertIn("  - PR: `PR #71 (open) https://github.com/owner/repo/pull/71`", report)
        self.assertIn("  - reasons: `dirty_worktree`, `open_pr_exists`", report)
        self.assertIn("  - ambiguity indicators: none", report)
        self.assertIn("  - recommended action: Recover workspace before reassignment or cleanup.", report)

    def test_collect_workspace_lifecycle_diagnostic_uses_inventory_and_classifier(self):
        calls = []

        def collect_workspace_inventory(repo_path, workspace_path, *, item, github_item):
            calls.append((repo_path, workspace_path, item, github_item))
            return {"workspace_path": workspace_path, "item_identity": item, "workspace_clean": True}

        def classify_workspace(facts, *, allow_cleanup, dry_run):
            self.assertEqual(facts["workspace_path"], "C:/worktree")
            self.assertTrue(allow_cleanup)
            self.assertTrue(dry_run)
            return {"lifecycle_state": "cleanup-eligible", "reasons": [], "ambiguous": False, "facts": facts}

        diagnostic = workspace_diagnostics.collect_workspace_lifecycle_diagnostic(
            repo_path="C:/repo",
            workspace_path="C:/worktree",
            item={"type": "issue", "number": 62},
            allow_cleanup=True,
            dry_run=True,
            collect_workspace_inventory_fn=collect_workspace_inventory,
            classify_workspace_fn=classify_workspace,
        )

        self.assertEqual(
            calls,
            [("C:/repo", "C:/worktree", {"type": "issue", "number": 62}, {"type": "issue", "number": 62})],
        )
        self.assertEqual(diagnostic["state"], "cleanup-eligible")
        self.assertEqual(diagnostic["issue"], "issue #62")

    def test_collect_workspace_lifecycle_diagnostic_forwards_review_context_to_classifier(self):
        item = {
            "type": "issue",
            "number": 62,
            "state": "open",
            "labels": ["state:changes-requested"],
            "review_pr": {"number": 63, "url": "https://github.com/owner/repo/pull/63", "state": "open"},
        }

        def collect_workspace_inventory(
            repo_path,
            workspace_path,
            *,
            item,
            workflow_labels,
            github_item,
            open_pr,
        ):
            return {
                "repo_path": repo_path,
                "workspace_path": workspace_path,
                "item": item,
                "item_identity": {"type": item["type"], "number": item["number"]},
                "expected_branch": "circus/issue-62-workspace-diagnostics",
                "registered_workspace_entry": {"worktree": workspace_path},
                "workspace_path_exists": True,
                "current_branch": "circus/issue-62-workspace-diagnostics",
                "detached_head": False,
                "workspace_clean": True,
                "missing_upstream_tracking": False,
                "ambiguous_upstream": False,
                "open_pr": open_pr,
                "workflow_labels": workflow_labels,
                "github_item": github_item,
                "metadata_available": True,
            }

        diagnostic = workspace_diagnostics.collect_workspace_lifecycle_diagnostic(
            repo_path="C:/repo",
            workspace_path="C:/worktree",
            item=item,
            collect_workspace_inventory_fn=collect_workspace_inventory,
            classify_workspace_fn=workspace_diagnostics.workspace_inventory.classify_workspace,
        )

        self.assertEqual(diagnostic["pr"], "PR #63 (open) https://github.com/owner/repo/pull/63")
        self.assertIn("open_pr_exists", diagnostic["reasons"])
        self.assertEqual(diagnostic["state"], "recoverable")

    def test_collect_workspace_lifecycle_diagnostic_forwards_watchtower_run_context(self):
        item = {"type": "issue", "number": 62, "state": "open"}
        watchtower_run = {
            "run_dir": "C:/watchtower/runs/owner-repo/issue-62/run-001-agent",
            "status": "interrupted",
        }

        def collect_workspace_inventory(
            repo_path,
            workspace_path,
            *,
            item,
            github_item,
            watchtower_run,
        ):
            self.assertEqual(repo_path, "C:/repo")
            self.assertEqual(workspace_path, "C:/worktree")
            self.assertEqual(item, {"type": "issue", "number": 62, "state": "open"})
            self.assertEqual(github_item, {"type": "issue", "number": 62, "state": "open"})
            self.assertEqual(
                watchtower_run,
                {
                    "run_dir": "C:/watchtower/runs/owner-repo/issue-62/run-001-agent",
                    "status": "interrupted",
                },
            )
            return {
                "workspace_path": workspace_path,
                "item_identity": {"type": item["type"], "number": item["number"]},
                "expected_branch": "circus/issue-62-workspace-diagnostics",
                "registered_workspace_entry": {"worktree": workspace_path},
                "workspace_path_exists": True,
                "current_branch": "circus/issue-62-workspace-diagnostics",
                "detached_head": False,
                "workspace_clean": True,
                "missing_upstream_tracking": False,
                "ambiguous_upstream": False,
                "open_pr": None,
                "workflow_labels": [],
                "github_item": github_item,
                "watchtower_run": watchtower_run,
                "metadata_available": True,
            }

        diagnostic = workspace_diagnostics.collect_workspace_lifecycle_diagnostic(
            repo_path="C:/repo",
            workspace_path="C:/worktree",
            item=item,
            watchtower_run=watchtower_run,
            collect_workspace_inventory_fn=collect_workspace_inventory,
            classify_workspace_fn=workspace_diagnostics.workspace_inventory.classify_workspace,
        )

        self.assertEqual(diagnostic["state"], "suspended")
        self.assertIn("watchtower_run_incomplete", diagnostic["reasons"])


if __name__ == "__main__":
    unittest.main()