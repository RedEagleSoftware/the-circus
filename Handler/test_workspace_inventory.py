import unittest
from types import SimpleNamespace

import Handler.workspace_inventory as workspace_inventory


def _result(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class ParseGitWorktreePorcelainTests(unittest.TestCase):
    def test_parse_multiple_entries_with_detached_and_missing_branch(self):
        output = (
            "worktree C:/repo\n"
            "HEAD aaaaaaa\n"
            "branch refs/heads/main\n"
            "\n"
            "worktree C:/repo-worktrees/issue-53\n"
            "HEAD bbbbbbb\n"
            "detached\n"
            "\n"
        )

        parsed = workspace_inventory.parse_git_worktree_porcelain(output)

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["worktree"], "C:/repo")
        self.assertEqual(parsed[0]["branch"], "refs/heads/main")
        self.assertEqual(parsed[1]["worktree"], "C:/repo-worktrees/issue-53")
        self.assertTrue(parsed[1]["detached"])
        self.assertNotIn("branch", parsed[1])


class ClassifyWorkspaceTests(unittest.TestCase):
    def _facts(self, **overrides):
        facts = {
            "metadata_available": True,
            "workflow_labels": [],
            "open_pr": None,
            "watchtower_run": None,
            "workspace_clean": True,
            "workspace_path_exists": True,
            "expected_branch": "circus/issue-53-inventory",
            "current_branch": "circus/issue-53-inventory",
            "detached_head": False,
            "registered_workspace_entry": {"worktree": "C:/repo-worktrees/issue-53"},
            "missing_upstream_tracking": False,
            "ambiguous_upstream": False,
            "github_item": {"state": "open"},
            "workspace_path": "C:/repo-worktrees/issue-53",
        }
        facts.update(overrides)
        return facts

    def test_classifies_planned(self):
        result = workspace_inventory.classify_workspace(
            self._facts(registered_workspace_entry=None, workspace_clean=None, workspace_path_exists=False)
        )
        self.assertEqual(result["lifecycle_state"], "planned")

    def test_classifies_unregistered_existing_workspace_as_blocked_unsafe(self):
        result = workspace_inventory.classify_workspace(
            self._facts(registered_workspace_entry=None, workspace_clean=True, workspace_path_exists=True)
        )
        self.assertEqual(result["lifecycle_state"], "blocked-unsafe")
        self.assertIn("unregistered_workspace", result["reasons"])

    def test_classifies_ready(self):
        result = workspace_inventory.classify_workspace(self._facts())
        self.assertEqual(result["lifecycle_state"], "ready")

    def test_classifies_active(self):
        result = workspace_inventory.classify_workspace(
            self._facts(workflow_labels=["state:agent-in-progress"])
        )
        self.assertEqual(result["lifecycle_state"], "active")
        self.assertIn("active_lock_label", result["reasons"])

    def test_classifies_suspended_from_watchtower_status(self):
        result = workspace_inventory.classify_workspace(
            self._facts(watchtower_run={"status": "interrupted"})
        )
        self.assertEqual(result["lifecycle_state"], "suspended")
        self.assertIn("watchtower_run_incomplete", result["reasons"])

    def test_classifies_recoverable_for_dirty_workspace_and_open_pr(self):
        result = workspace_inventory.classify_workspace(
            self._facts(workspace_clean=False, open_pr={"url": "https://example/pr/1", "state": "open"})
        )
        self.assertEqual(result["lifecycle_state"], "recoverable")
        self.assertIn("dirty_worktree", result["reasons"])
        self.assertIn("open_pr_exists", result["reasons"])

    def test_classifies_stale_clean(self):
        result = workspace_inventory.classify_workspace(
            self._facts(expected_branch="circus/issue-53-inventory", current_branch="circus/another-branch")
        )
        self.assertEqual(result["lifecycle_state"], "blocked-unsafe")

        stale_result = workspace_inventory.classify_workspace(
            self._facts(expected_branch=None, current_branch="circus/another-branch", workspace_clean=True)
        )
        self.assertEqual(stale_result["lifecycle_state"], "stale-clean")

    def test_classifies_retired(self):
        result = workspace_inventory.classify_workspace(
            self._facts(github_item={"state": "closed"}, workspace_clean=True)
        )
        self.assertEqual(result["lifecycle_state"], "retired")

    def test_classifies_cleanup_eligible_when_dry_run_allows_cleanup(self):
        result = workspace_inventory.classify_workspace(
            self._facts(github_item={"state": "closed"}, workspace_clean=True),
            allow_cleanup=True,
            dry_run=True,
        )
        self.assertEqual(result["lifecycle_state"], "cleanup-eligible")

    def test_classifies_detached_head_workspace_as_blocked_unsafe(self):
        result = workspace_inventory.classify_workspace(
            self._facts(current_branch=None, detached_head=True, workspace_clean=True),
            allow_cleanup=True,
            dry_run=True,
        )

        self.assertEqual(result["lifecycle_state"], "blocked-unsafe")
        self.assertIn("detached_head", result["reasons"])
        self.assertTrue(result["ambiguous"])

    def test_classifies_blocked_unsafe_for_ambiguous_or_conflicting_facts(self):
        result = workspace_inventory.classify_workspace(
            self._facts(metadata_available=False, ambiguous_upstream=True)
        )
        self.assertEqual(result["lifecycle_state"], "blocked-unsafe")
        self.assertIn("metadata_unavailable", result["reasons"])
        self.assertIn("ambiguous_upstream", result["reasons"])

    def test_reports_missing_upstream_tracking_as_recoverable(self):
        result = workspace_inventory.classify_workspace(
            self._facts(missing_upstream_tracking=True)
        )
        self.assertEqual(result["lifecycle_state"], "recoverable")
        self.assertIn("missing_upstream_tracking", result["reasons"])

    def test_format_workspace_diagnostic_includes_state_and_reasons(self):
        result = workspace_inventory.classify_workspace(
            self._facts(missing_upstream_tracking=True)
        )
        diagnostic = workspace_inventory.format_workspace_diagnostic(result)

        self.assertIn("state=recoverable", diagnostic)
        self.assertIn("missing_upstream_tracking", diagnostic)


class CollectWorkspaceInventoryTests(unittest.TestCase):
    def test_collect_inventory_uses_handler_branch_slug_length_convention(self):
        expected_branch = "circus/issue-53-add-workspace-inventory-and-lifecycle-classification-service"

        def fake_run(_, args):
            if args == ["worktree", "list", "--porcelain"]:
                return _result(
                    stdout=(
                        "worktree C:/repo-worktrees/issue-53\n"
                        "HEAD bbbbbbb\n"
                        f"branch refs/heads/{expected_branch}\n"
                        "\n"
                    )
                )
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return _result(stdout=f"{expected_branch}\n")
            if args == ["status", "--porcelain"]:
                return _result(stdout="")
            if args == ["branch", "--list", expected_branch]:
                return _result(stdout=f"  {expected_branch}\n")
            if args == ["ls-remote", "--heads", "origin", expected_branch]:
                return _result(stdout=f"abc\trefs/heads/{expected_branch}\n")
            if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
                return _result(stdout=f"origin/{expected_branch}\n")
            raise AssertionError(f"Unexpected git command: {args}")

        facts = workspace_inventory.collect_workspace_inventory(
            repo_path="C:/repo",
            workspace_path="C:/repo-worktrees/issue-53",
            item={
                "type": "issue",
                "number": 53,
                "title": "Add Workspace Inventory and Lifecycle Classification Service",
            },
            run_git_command=fake_run,
        )

        self.assertEqual(facts["expected_branch"], expected_branch)
        self.assertEqual(facts["current_branch"], expected_branch)

    def test_collect_inventory_gathers_git_facts_with_no_destructive_commands(self):
        calls = []

        def fake_run(path, args):
            calls.append((path, args))
            if args == ["worktree", "list", "--porcelain"]:
                return _result(
                    stdout=(
                        "worktree C:/repo\n"
                        "HEAD aaaaaaa\n"
                        "branch refs/heads/main\n"
                        "\n"
                        "worktree C:/repo-worktrees/issue-53\n"
                        "HEAD bbbbbbb\n"
                        "branch refs/heads/circus/issue-53-inventory\n"
                        "\n"
                    )
                )
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return _result(stdout="circus/issue-53-inventory\n")
            if args == ["status", "--porcelain"]:
                return _result(stdout="")
            if args == ["branch", "--list", "circus/issue-53-inventory"]:
                return _result(stdout="  circus/issue-53-inventory\n")
            if args == ["ls-remote", "--heads", "origin", "circus/issue-53-inventory"]:
                return _result(stdout="abc\trefs/heads/circus/issue-53-inventory\n")
            if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
                return _result(stdout="origin/circus/issue-53-inventory\n")
            raise AssertionError(f"Unexpected git command: {args}")

        facts = workspace_inventory.collect_workspace_inventory(
            repo_path="C:/repo",
            workspace_path="C:/repo-worktrees/issue-53",
            item={"type": "issue", "number": 53, "title": "Inventory"},
            workflow_labels=["state:ready-for-dev"],
            open_pr={"url": "https://example/pr/53", "state": "open"},
            watchtower_run={"status": "ok"},
            run_git_command=fake_run,
        )

        self.assertEqual(facts["current_branch"], "circus/issue-53-inventory")
        self.assertTrue(facts["workspace_clean"])
        self.assertTrue(facts["local_branch_exists"])
        self.assertTrue(facts["remote_branch_exists"])
        self.assertEqual(facts["upstream_branch"], "origin/circus/issue-53-inventory")
        self.assertEqual(facts["workflow_labels"], ["state:ready-for-dev"])
        self.assertEqual(facts["open_pr"]["url"], "https://example/pr/53")

        destructive_keywords = {
            "reset",
            "rebase",
            "push",
            "checkout",
            "switch",
            "merge",
            "branch",
            "worktree",
            "clean",
        }
        allowed_prefixes = {
            ("worktree", "list"),
            ("rev-parse", "--abbrev-ref"),
            ("status", "--porcelain"),
            ("branch", "--list"),
            ("ls-remote", "--heads"),
        }
        for _, args in calls:
            prefix = tuple(args[:2]) if len(args) >= 2 else tuple(args)
            self.assertIn(prefix, allowed_prefixes)
            if args[0] in destructive_keywords:
                self.assertIn(prefix, allowed_prefixes)

    def test_collect_inventory_detects_missing_upstream_tracking(self):
        def fake_run(_, args):
            if args == ["worktree", "list", "--porcelain"]:
                return _result(stdout="worktree C:/repo-worktrees/issue-53\n\n")
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return _result(stdout="circus/issue-53-inventory\n")
            if args == ["status", "--porcelain"]:
                return _result(stdout="")
            if args == ["branch", "--list", "circus/issue-53-inventory"]:
                return _result(stdout="  circus/issue-53-inventory\n")
            if args == ["ls-remote", "--heads", "origin", "circus/issue-53-inventory"]:
                return _result(stdout="")
            if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
                return _result(returncode=128, stderr="fatal: no upstream configured for branch\n")
            raise AssertionError(f"Unexpected git command: {args}")

        facts = workspace_inventory.collect_workspace_inventory(
            repo_path="C:/repo",
            workspace_path="C:/repo-worktrees/issue-53",
            expected_branch="circus/issue-53-inventory",
            run_git_command=fake_run,
        )

        self.assertTrue(facts["missing_upstream_tracking"])
        self.assertFalse(facts["ambiguous_upstream"])

    def test_collect_inventory_detached_head_is_blocked_unsafe_and_not_cleanup_eligible(self):
        expected_branch = "circus/issue-53-inventory"

        def fake_run(_, args):
            if args == ["worktree", "list", "--porcelain"]:
                return _result(
                    stdout=(
                        "worktree C:/repo-worktrees/issue-53\n"
                        "HEAD bbbbbbb\n"
                        "detached\n"
                        "\n"
                    )
                )
            if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
                return _result(stdout="HEAD\n")
            if args == ["status", "--porcelain"]:
                return _result(stdout="")
            if args == ["branch", "--list", expected_branch]:
                return _result(stdout=f"  {expected_branch}\n")
            if args == ["ls-remote", "--heads", "origin", expected_branch]:
                return _result(stdout=f"abc\trefs/heads/{expected_branch}\n")
            if args == ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
                return _result(stdout=f"origin/{expected_branch}\n")
            raise AssertionError(f"Unexpected git command: {args}")

        facts = workspace_inventory.collect_workspace_inventory(
            repo_path="C:/repo",
            workspace_path="C:/repo-worktrees/issue-53",
            expected_branch=expected_branch,
            run_git_command=fake_run,
        )

        self.assertTrue(facts["detached_head"])
        self.assertIsNone(facts["current_branch"])

        result = workspace_inventory.classify_workspace(facts, allow_cleanup=True, dry_run=True)
        self.assertEqual(result["lifecycle_state"], "blocked-unsafe")
        self.assertIn("detached_head", result["reasons"])

    def test_collect_inventory_skips_workspace_git_probes_for_absent_unregistered_workspace(self):
        calls = []

        def fake_run(_, args):
            calls.append(args)
            if args == ["worktree", "list", "--porcelain"]:
                return _result(stdout="worktree C:/repo\n\n")
            if args == ["branch", "--list", "circus/issue-53-inventory"]:
                return _result(stdout="")
            if args == ["ls-remote", "--heads", "origin", "circus/issue-53-inventory"]:
                return _result(stdout="")
            raise AssertionError(f"Unexpected git command: {args}")

        facts = workspace_inventory.collect_workspace_inventory(
            repo_path="C:/repo",
            workspace_path="C:/repo-worktrees/issue-53",
            expected_branch="circus/issue-53-inventory",
            run_git_command=fake_run,
            path_exists=lambda _: False,
        )

        self.assertIsNone(facts["current_branch"])
        self.assertIsNone(facts["workspace_clean"])
        self.assertIsNone(facts["upstream_branch"])
        self.assertFalse(facts["workspace_path_exists"])

        workspace_git_commands = {
            ("rev-parse", "--abbrev-ref", "HEAD"),
            ("status", "--porcelain"),
            ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
        }
        call_tuples = {tuple(call) for call in calls}
        for command in workspace_git_commands:
            self.assertNotIn(command, call_tuples)

        result = workspace_inventory.classify_workspace(facts)
        self.assertEqual(result["lifecycle_state"], "planned")

    def test_collect_inventory_classifies_unregistered_existing_workspace_as_blocked_unsafe(self):
        def fake_run(_, args):
            if args == ["worktree", "list", "--porcelain"]:
                return _result(stdout="worktree C:/repo\n\n")
            if args == ["branch", "--list", "circus/issue-53-inventory"]:
                return _result(stdout="")
            if args == ["ls-remote", "--heads", "origin", "circus/issue-53-inventory"]:
                return _result(stdout="")
            raise AssertionError(f"Unexpected git command: {args}")

        facts = workspace_inventory.collect_workspace_inventory(
            repo_path="C:/repo",
            workspace_path="C:/repo-worktrees/issue-53",
            expected_branch="circus/issue-53-inventory",
            run_git_command=fake_run,
            path_exists=lambda _: True,
        )

        result = workspace_inventory.classify_workspace(facts)
        self.assertEqual(result["lifecycle_state"], "blocked-unsafe")
        self.assertIn("unregistered_workspace", result["reasons"])


if __name__ == "__main__":
    unittest.main()
