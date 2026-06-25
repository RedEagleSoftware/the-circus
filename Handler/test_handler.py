import unittest
import tempfile
import os
import json
import re
from unittest.mock import Mock, patch, MagicMock

import Handler.handler as handler
import Handler.github_client as github_client
import Handler.target_instructions as target_instructions
import Handler.workflow_labels as workflow_labels
import Handler.workflow_states as workflow_states


class HandlerObservabilityTests(unittest.TestCase):
    def setUp(self):
        handler.EXECUTABLE_PATHS.clear()

    def test_get_circus_runtime_root_is_derived_from_module_location_without_env_var(self):
        expected_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(handler.__file__)), os.pardir))

        with patch.dict(
            os.environ,
            {
                "CIRCUS_ROOT": "C:/wrong/path",
                "THE_CIRCUS_PATH": "C:/also/wrong",
            },
            clear=False,
        ):
            resolved_root = handler.get_circus_runtime_root()

        self.assertEqual(resolved_root, expected_root)

    def test_validate_required_executables_reports_found_paths(self):
        def which_side_effect(command_name):
            mapping = {
                "gh": "C:/tools/gh.exe",
                "git": "C:/tools/git.exe",
                "junie": "C:/tools/junie.exe",
                "codex": "C:/tools/codex.exe",
            }
            return mapping.get(command_name)

        with patch.object(handler, "report_python_environment_versions"):
            with patch.object(handler.shutil, "which", side_effect=which_side_effect):
                with patch("builtins.print") as mock_print:
                    resolved = handler.validate_required_executables()

        self.assertEqual(
            resolved,
            {
                "gh": "C:/tools/gh.exe",
                "git": "C:/tools/git.exe",
                "junie": "C:/tools/junie.exe",
                "codex": "C:/tools/codex.exe",
            },
        )
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Found executable 'gh'" in line for line in printed_lines))
        self.assertTrue(any("Found executable 'git'" in line for line in printed_lines))
        self.assertTrue(any("Found executable 'junie'" in line for line in printed_lines))
        self.assertTrue(any("Found executable 'codex'" in line for line in printed_lines))

    def test_validate_required_executables_fails_when_required_tool_missing(self):
        def which_side_effect(command_name):
            mapping = {
                "gh": "C:/tools/gh.exe",
                "git": "C:/tools/git.exe",
                "junie": None,
                "codex": "C:/tools/codex.exe",
            }
            return mapping.get(command_name)

        with patch.object(handler, "report_python_environment_versions"):
            with patch.object(handler.shutil, "which", side_effect=which_side_effect):
                with patch("builtins.print") as mock_print:
                    resolved = handler.validate_required_executables()

        self.assertIsNone(resolved)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("missing required executable 'junie'" in line for line in printed_lines))
        self.assertTrue(any("Startup aborted" in line for line in printed_lines))

    def test_validate_required_executables_prefers_env_override_for_junie(self):
        def which_side_effect(command_name):
            if command_name == "C:/custom/junie.exe":
                return "C:/custom/junie.exe"

            mapping = {
                "gh": "C:/tools/gh.exe",
                "git": "C:/tools/git.exe",
                "codex": "C:/tools/codex.exe",
            }
            return mapping.get(command_name)

        with patch.dict(os.environ, {"CIRCUS_JUNIE_EXECUTABLE": "C:/custom/junie.exe"}, clear=False):
            with patch.object(handler, "report_python_environment_versions"):
                with patch.object(handler.shutil, "which", side_effect=which_side_effect):
                    with patch("builtins.print") as mock_print:
                        resolved = handler.validate_required_executables()

        self.assertEqual(resolved["junie"], "C:/custom/junie.exe")
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("via CIRCUS_JUNIE_EXECUTABLE" in line for line in printed_lines))

    def test_report_python_environment_versions_prints_python_and_pip_versions(self):
        pip_result = Mock(returncode=0, stdout="pip 24.1 from /venv/lib/python3.12/site-packages/pip (python 3.12)\n")

        with patch.object(handler.sys, "version_info", Mock(major=3, minor=12, micro=4)):
            with patch.object(handler.sys, "executable", "/venv/bin/python"):
                with patch.object(handler.subprocess, "run", return_value=pip_result) as mock_run:
                    with patch("builtins.print") as mock_print:
                        handler.report_python_environment_versions()

        mock_run.assert_called_once_with(
            ["/venv/bin/python", "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertIn("[Startup] Python version: 3.12.4", printed_lines)
        self.assertIn("[Startup] Pip version: 24.1", printed_lines)

    def test_report_python_environment_versions_warns_and_continues_when_pip_lookup_fails(self):
        with patch.object(handler.sys, "version_info", Mock(major=3, minor=11, micro=9)):
            with patch.object(
                handler.subprocess,
                "run",
                side_effect=handler.subprocess.TimeoutExpired(cmd=["python", "-m", "pip", "--version"], timeout=10),
            ):
                with patch("builtins.print") as mock_print:
                    handler.report_python_environment_versions()

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertIn("[Startup] Python version: 3.11.9", printed_lines)
        self.assertTrue(any("[Startup] Warning: Unable to determine pip version:" in line for line in printed_lines))

    def test_validate_target_repo_workspace_missing_path(self):
        with patch("builtins.print") as mock_print:
            is_valid = handler.validate_target_repo_workspace(None, "owner/repo")

        self.assertFalse(is_valid)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("CIRCUS_TARGET_REPO_PATH is required" in line for line in printed_lines))

    def test_validate_target_repo_workspace_nonexistent_path(self):
        with patch("builtins.print") as mock_print:
            is_valid = handler.validate_target_repo_workspace("C:\\does-not-exist", "owner/repo")

        self.assertFalse(is_valid)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("does not exist" in line for line in printed_lines))

    def test_validate_target_repo_workspace_not_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "not-a-dir.txt")
            with open(file_path, "w", encoding="utf-8") as file_handle:
                file_handle.write("test")

            with patch("builtins.print") as mock_print:
                is_valid = handler.validate_target_repo_workspace(file_path, "owner/repo")

        self.assertFalse(is_valid)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("is not a directory" in line for line in printed_lines))

    def test_validate_target_repo_workspace_not_git_repo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("builtins.print") as mock_print:
                is_valid = handler.validate_target_repo_workspace(temp_dir, "owner/repo")

        self.assertFalse(is_valid)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("does not appear to be a git repository" in line for line in printed_lines))

    def test_validate_target_repo_workspace_warns_on_remote_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            os.makedirs(os.path.join(temp_dir, ".git"), exist_ok=True)

            with patch.object(handler, "get_git_remote_origin_url", return_value="git@github.com:other/repo.git"):
                with patch("builtins.print") as mock_print:
                    is_valid = handler.validate_target_repo_workspace(temp_dir, "owner/repo")

        self.assertTrue(is_valid)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("remote appears to mismatch" in line for line in printed_lines))

    def test_resolve_worktree_root_uses_configured_environment_override(self):
        with patch.dict(os.environ, {"CIRCUS_WORKTREE_ROOT": "C:/repos/worktrees"}, clear=False):
            worktree_root, source = handler.resolve_worktree_root("C:/repos/target", "owner-repo")

        self.assertEqual(
            handler.normalize_path_for_display(worktree_root),
            "C:/repos/worktrees",
        )
        self.assertEqual(source, "env:CIRCUS_WORKTREE_ROOT")

    def test_resolve_worktree_root_derives_default_from_target_repo_name_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CIRCUS_WORKTREE_ROOT", None)
            worktree_root, source = handler.resolve_worktree_root("C:/repos/target", "owner-repo")

        self.assertEqual(worktree_root, os.path.normpath("C:/repos/target-worktrees"))
        self.assertEqual(source, "derived-default")

    def test_resolve_item_workspace_metadata_sanitizes_repository_slug_for_issue_workspace_path(self):
        item = {"type": "issue", "number": 32}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/repos/target"):
            with patch.object(handler, "REPO", "Red Eagle Software/The.Circus"):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("CIRCUS_WORKTREE_ROOT", None)
                    metadata = handler.resolve_item_workspace_metadata(item)

        self.assertEqual(metadata["workspace_name"], "issue-32")
        self.assertEqual(metadata["workspace_item_identity"], "issue-32")
        self.assertEqual(metadata["workspace_path"], "C:/repos/target-worktrees/red-eagle-software-the-circus/issue-32")

    def test_resolve_item_workspace_metadata_generates_pull_request_workspace_path(self):
        item = {"type": "pull_request", "number": 77}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/repos/target"):
            with patch.object(handler, "REPO", "RedEagleSoftware/the-circus"):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("CIRCUS_WORKTREE_ROOT", None)
                    metadata = handler.resolve_item_workspace_metadata(item)

        self.assertEqual(metadata["workspace_name"], "pr-77")
        self.assertEqual(metadata["workspace_item_identity"], "pull_request-77")
        self.assertEqual(metadata["workspace_path"], "C:/repos/target-worktrees/redeaglesoftware-the-circus/pr-77")

    def test_verify_github_repo_access_success(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value='{"nameWithOwner": "owner/repo"}'):
                self.assertTrue(handler.verify_github_repo_access())

    def test_resolve_dispatch_config_marks_unsupported_state(self):
        item = {"type": "issue", "number": 12, "labels": []}

        result = handler.resolve_dispatch_config(item, ["state:unknown-state"])

        self.assertIsNone(result)
        self.assertIn("unsupported workflow state", item["comment"])
        self.assertIn("unsupported workflow state label", item["skip_reason"])

    def test_process_one_item_reports_locked_skip(self):
        items = [
            {
                "type": "issue",
                "number": 10,
                "title": "Already running",
                "labels": [{"name": handler.LOCK_LABEL}],
            }
        ]

        with patch("builtins.print") as mock_print:
            dispatched = handler.process_one_item(items)

        self.assertEqual(dispatched, "no-dispatch")
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(
            any("[Poll] Skipping issue #10" in line and "lock label" in line for line in printed_lines)
        )

    def test_process_one_item_releases_lock_when_launch_brief_generation_fails(self):
        item = {
            "type": "issue",
            "number": 22,
            "title": "Fail during setup",
            "labels": [{"name": "state:ready-for-dev"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(
                    handler,
                    "prepare_developer_branch",
                    return_value={"ok": True, "branch": "circus/issue-22-fail-during-setup"},
                ):
                    with patch.object(handler, "write_launch_brief", side_effect=OSError("disk full")):
                        with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                            with patch.object(handler, "add_comment") as mock_add_comment:
                                with patch.object(handler, "launch_agent") as mock_launch_agent:
                                    with patch("builtins.print") as mock_print:
                                        dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        mock_launch_agent.assert_not_called()
        self.assertIn("failed before launch brief generation completed", item["comment"])
        self.assertIn("The lock label `state:agent-in-progress` was released", item["comment"])

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Failed to write launch brief for issue #22: disk full" in line for line in printed_lines))
        self.assertTrue(any("Releasing lock for issue #22" in line for line in printed_lines))
        self.assertTrue(any("Lock cleanup succeeded for issue #22" in line for line in printed_lines))

    def test_process_one_item_keeps_lock_after_successful_dispatch(self):
        item = {
            "type": "issue",
            "number": 23,
            "title": "Successful dispatch",
            "labels": [{"name": "state:ready-for-dev"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(
                    handler,
                    "prepare_developer_branch",
                    return_value={"ok": True, "branch": "circus/issue-23-successful-dispatch"},
                ):
                    with patch.object(handler, "write_launch_brief", return_value="Watchtower/runs/issue-23/run-001-developer/launch-brief.md"):
                        with patch.object(handler, "launch_agent", return_value=True):
                            with patch.object(handler, "unlock_item") as mock_unlock:
                                with patch.object(handler, "add_comment") as mock_add_comment:
                                    dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "success")
        mock_unlock.assert_not_called()
        mock_add_comment.assert_not_called()

    def test_process_one_item_releases_lock_when_junie_fails_before_start(self):
        item = {
            "type": "issue",
            "number": 31,
            "title": "Junie command unavailable",
            "labels": [{"name": "state:ready-for-dev"}],
        }
        launch_brief_path = "Watchtower/runs/issue-31/run-001-developer/launch-brief.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "lock_item", return_value=True):
                with patch.object(handler, "get_current_item", return_value=(item, True)):
                    with patch.object(
                        handler,
                        "prepare_developer_branch",
                        return_value={"ok": True, "branch": "circus/issue-31-junie-command-unavailable"},
                    ):
                        with patch.object(handler, "write_launch_brief", return_value=launch_brief_path):
                            with patch.object(handler.subprocess, "run", side_effect=FileNotFoundError("junie not found")):
                                with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                                    with patch.object(handler, "add_comment") as mock_add_comment:
                                        with patch("builtins.print") as mock_print:
                                            dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("failed to start junie before execution began", item["comment"])
        self.assertIn("The lock label `state:agent-in-progress` was released", item["comment"])
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Junie failed to launch before execution started" in line for line in printed_lines))

    def test_process_one_item_releases_lock_when_codex_architect_fails_before_start(self):
        item = {
            "type": "issue",
            "number": 32,
            "title": "Codex command unavailable",
            "labels": [{"name": "state:ready-for-architecture"}],
        }
        launch_brief_path = "Watchtower/runs/issue-32/run-001-architect/launch-brief.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "lock_item", return_value=True):
                with patch.object(handler, "get_current_item", return_value=(item, True)):
                    with patch.object(handler, "prepare_architect_execution_branch", return_value={"ok": True, "branch": "main"}):
                        with patch.object(handler, "write_launch_brief", return_value=launch_brief_path):
                            with patch.object(handler.subprocess, "run", side_effect=FileNotFoundError("codex not found")):
                                with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                                    with patch.object(handler, "add_comment") as mock_add_comment:
                                        with patch.object(handler, "advance_architect_workflow_on_success") as mock_advance_transition:
                                            with patch("builtins.print") as mock_print:
                                                dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        mock_advance_transition.assert_not_called()
        self.assertIn("failed to start codex before execution began", item["comment"])
        self.assertIn("The lock label `state:agent-in-progress` was released", item["comment"])
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Codex failed to launch before execution started" in line for line in printed_lines))

    def test_poll_cycle_observability_when_idle(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler, "validate_required_executables", return_value={"gh": "gh", "git": "git", "junie": "junie", "codex": "codex"}):
                    with patch.object(handler, "validate_target_repo_workspace", return_value=True):
                        with patch.object(handler, "verify_github_repo_access", return_value=True):
                            with patch.object(handler, "get_max_steps_per_run", return_value=1):
                                with patch.object(handler, "get_labeled_items", return_value=([], [], [], True)):
                                    with patch.object(handler, "process_one_item", return_value="no-dispatch"):
                                        with patch.object(handler.time, "sleep", side_effect=RuntimeError("stop")) as mock_sleep:
                                            with patch("builtins.print") as mock_print:
                                                with self.assertRaises(RuntimeError):
                                                    handler.poll()

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Handler] Max workflow steps per issue this run: 1" in line for line in printed_lines))
        self.assertTrue(any("[Poll] Starting cycle #1..." in line for line in printed_lines))
        self.assertTrue(any("[Poll] Retrieved issues=0, prs=0, candidates=0." in line for line in printed_lines))
        self.assertTrue(any("[Poll] No candidate items matched workflow labels this cycle." in line for line in printed_lines))
        self.assertTrue(
            any(
                f"[Handler] No eligible workflow step found. Sleeping {handler.POLL_INTERVAL} seconds before re-polling."
                in line
                for line in printed_lines
            )
        )
        mock_sleep.assert_called_once_with(handler.POLL_INTERVAL)

    def test_poll_exits_when_startup_repository_access_check_fails(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(
                    handler,
                    "validate_required_executables",
                    return_value={"gh": "gh", "git": "git", "junie": "junie", "codex": "codex"},
                ):
                    with patch.object(handler, "validate_target_repo_workspace", return_value=True):
                        with patch.object(handler, "verify_github_repo_access", return_value=False):
                            with patch.object(handler, "get_labeled_items") as mock_get_labeled_items:
                                with patch.object(handler.time, "sleep") as mock_sleep:
                                    with patch("builtins.print") as mock_print:
                                        handler.poll()

        mock_get_labeled_items.assert_not_called()
        mock_sleep.assert_not_called()
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Handler] Startup check failed. Exiting." in line for line in printed_lines))

    def test_get_max_steps_per_run_defaults_to_one_when_env_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(handler.get_max_steps_per_run(), 1)

    def test_get_max_steps_per_run_uses_configured_value(self):
        with patch.dict(os.environ, {"CIRCUS_MAX_WORKFLOW_STEPS_PER_ISSUE": "2"}, clear=True):
            self.assertEqual(handler.get_max_steps_per_run(), 2)

    def test_poll_allows_second_dispatch_and_repolls_when_max_steps_is_two(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(
                    handler,
                    "validate_required_executables",
                    return_value={"gh": "gh", "git": "git", "junie": "junie", "codex": "codex"},
                ):
                    with patch.object(handler, "validate_target_repo_workspace", return_value=True):
                        with patch.object(handler, "verify_github_repo_access", return_value=True):
                            with patch.object(handler, "get_max_steps_per_run", return_value=2):
                                with patch.object(
                                    handler,
                                    "get_labeled_items",
                                    side_effect=[
                                        ([], [], [{"number": 1}], True),
                                        ([], [], [{"number": 1}], True),
                                        ([], [], [], False),
                                    ],
                                ) as mock_get_labeled_items:
                                    with patch.object(handler, "process_one_item", side_effect=["success", "success"]) as mock_process:
                                        with patch("builtins.print") as mock_print:
                                            handler.poll()

        self.assertEqual(mock_get_labeled_items.call_count, 3)
        self.assertEqual(mock_process.call_count, 2)

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Handler] Re-polling for next eligible workflow step." in line for line in printed_lines))
        self.assertTrue(any("[GitHub] Failed to retrieve issues/PRs this cycle; stopping current run." in line for line in printed_lines))

    def test_poll_stops_when_reviewer_completes_without_result_artifact(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(
                    handler,
                    "validate_required_executables",
                    return_value={"gh": "gh", "git": "git", "junie": "junie", "codex": "codex"},
                ):
                    with patch.object(handler, "validate_target_repo_workspace", return_value=True):
                        with patch.object(handler, "verify_github_repo_access", return_value=True):
                            with patch.object(handler, "get_max_steps_per_run", return_value=2):
                                with patch.object(
                                    handler,
                                    "get_labeled_items",
                                    side_effect=[
                                        ([], [], [{"number": 9}], True),
                                        ([], [], [{"number": 10}], True),
                                    ],
                                ) as mock_get_labeled_items:
                                    with patch.object(handler, "process_one_item", side_effect=["review-result-missing", "success"]) as mock_process:
                                        with patch("builtins.print") as mock_print:
                                            handler.poll()

        self.assertEqual(mock_get_labeled_items.call_count, 1)
        self.assertEqual(mock_process.call_count, 1)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Handler] Stopping run: reviewer completed without review-result artifact." in line for line in printed_lines))
        self.assertFalse(any("[Handler] Re-polling for next eligible workflow step." in line for line in printed_lines))

    def test_process_one_item_skips_issue_when_per_run_max_is_reached(self):
        capped_item = {
            "type": "issue",
            "number": 5,
            "title": "Capped issue",
            "labels": [{"name": "state:ready-for-dev"}],
        }
        dispatch_item = {
            "type": "issue",
            "number": 6,
            "title": "Dispatchable issue",
            "labels": [{"name": "state:ready-for-dev"}],
        }
        issue_steps_this_run = {"issue-5": 2}
        capped_issue_keys = set()

        dispatch_resolution = (
            "state:ready-for-dev",
            {"agent": "junie", "mode": "developer", "model": "gpt-5.3-codex", "effort": "Medium"},
        )

        with patch.object(handler, "resolve_dispatch_config", return_value=dispatch_resolution):
            with patch.object(handler, "lock_item", return_value=True) as mock_lock:
                with patch.object(handler, "get_current_item", return_value=(dispatch_item, True)):
                    with patch.object(handler, "prepare_developer_branch", return_value={"ok": True, "branch": "circus/issue-6-branch"}):
                        with patch.object(handler, "resolve_role_prompt_path", return_value="TheFarm/roles/developer.md"):
                            with patch.object(handler, "write_launch_brief", return_value="Watchtower/runs/issue-6/run-001-developer/launch-brief.md"):
                                with patch.object(handler, "launch_agent", return_value=True):
                                    with patch("builtins.print") as mock_print:
                                        on_dispatch_success = Mock()
                                        result = handler.process_one_item(
                                            [capped_item, dispatch_item],
                                            issue_steps_this_run=issue_steps_this_run,
                                            max_steps_per_run=2,
                                            capped_issue_keys=capped_issue_keys,
                                            on_dispatch_success=on_dispatch_success,
                                        )

        self.assertEqual(result, "success")
        self.assertIn("issue-5", capped_issue_keys)
        self.assertEqual(mock_lock.call_count, 1)
        self.assertEqual(mock_lock.call_args_list[0].args[0], dispatch_item)
        on_dispatch_success.assert_called_once_with(dispatch_item, "state:ready-for-dev")

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("issue #5 reached max workflow steps for this Handler run (2/2)." in line for line in printed_lines))
        self.assertTrue(any("Current state label for issue #5: state:ready-for-dev." in line for line in printed_lines))
        self.assertTrue(any("Human decision required: restart Handler to allow more steps" in line for line in printed_lines))

    def test_process_one_item_does_not_change_labels_when_skipping_capped_issue(self):
        capped_item = {
            "type": "issue",
            "number": 5,
            "title": "Capped issue",
            "labels": [{"name": "state:ready-for-dev"}],
        }
        issue_steps_this_run = {"issue-5": 2}
        capped_issue_keys = set()

        dispatch_resolution = (
            "state:ready-for-dev",
            {"agent": "junie", "mode": "developer", "model": "gpt-5.3-codex", "effort": "Medium"},
        )

        with patch.object(handler, "resolve_dispatch_config", return_value=dispatch_resolution):
            with patch.object(handler, "add_label") as mock_add_label:
                with patch.object(handler, "remove_label") as mock_remove_label:
                    result = handler.process_one_item(
                        [capped_item],
                        issue_steps_this_run=issue_steps_this_run,
                        max_steps_per_run=2,
                        capped_issue_keys=capped_issue_keys,
                    )

        self.assertEqual(result, "no-dispatch")
        mock_add_label.assert_not_called()
        mock_remove_label.assert_not_called()

    def test_poll_per_issue_step_count_resets_between_handler_invocations(self):
        captured_issue_steps = []

        def fake_process_one_item(items, **kwargs):
            captured_issue_steps.append(kwargs["issue_steps_this_run"])
            return "lock-failed"

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(
                    handler,
                    "validate_required_executables",
                    return_value={"gh": "gh", "git": "git", "junie": "junie", "codex": "codex"},
                ):
                    with patch.object(handler, "validate_target_repo_workspace", return_value=True):
                        with patch.object(handler, "verify_github_repo_access", return_value=True):
                            with patch.object(handler, "get_max_steps_per_run", return_value=2):
                                with patch.object(handler, "get_labeled_items", return_value=([], [], [{"number": 1}], True)):
                                    with patch.object(handler, "process_one_item", side_effect=fake_process_one_item):
                                        handler.poll()
                                        handler.poll()

        self.assertEqual(len(captured_issue_steps), 2)
        self.assertEqual(captured_issue_steps[0], {})
        self.assertEqual(captured_issue_steps[1], {})
        self.assertIsNot(captured_issue_steps[0], captured_issue_steps[1])

    def test_get_candidates_fetches_without_label_filter(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="[]") as mock_run:
                items, ok = handler.get_candidates("issue", "issue list")

        self.assertEqual(items, [])
        self.assertTrue(ok)
        mock_run.assert_called_once_with("gh issue list --repo owner/repo --json number,labels,title,url")

    def test_github_client_get_item_fetches_issue_view_and_attaches_type(self):
        payload = json.dumps(
            {
                "number": 11,
                "title": "Prevent stale launch",
                "url": "https://github.com/owner/repo/issues/11",
                "labels": [{"name": "state:ready-for-review"}],
            }
        )

        mock_run = Mock(return_value=payload)

        item, ok = github_client.get_item("issue", 11, "owner/repo", mock_run)

        self.assertTrue(ok)
        self.assertEqual(item["type"], "issue")
        self.assertEqual(item["number"], 11)
        mock_run.assert_called_once_with("gh issue view 11 --repo owner/repo --json number,labels,title,url")

    def test_github_client_get_item_reports_failure_when_command_returns_none(self):
        item, ok = github_client.get_item("pr", 23, "owner/repo", Mock(return_value=None))

        self.assertIsNone(item)
        self.assertFalse(ok)

    def test_build_thin_prompt_includes_target_repo_and_launch_brief_path(self):
        item = {"type": "issue", "number": 3, "title": "Implement launch brief", "url": "https://github.com/owner/repo/issues/3"}
        expected_profile_path = f"{handler.normalize_path_for_display(handler.get_circus_runtime_root())}/TheFarm/roles/developer.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            prompt = handler.build_thin_prompt(
                item,
                "state:ready-for-dev",
                "developer",
                os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                "Watchtower/runs/issue-3/run-001-developer/launch-brief.md",
            )

        self.assertIn("- target repo path: C:/target/repo", prompt)
        self.assertIn(f"- agent profile source path: {expected_profile_path}", prompt)
        self.assertIn(
            "- launch brief artifact path: Watchtower/runs/issue-3/run-001-developer/launch-brief.md",
            prompt,
        )

    def test_build_thin_prompt_mentions_target_repository_guidance_when_discovered(self):
        item = {"type": "issue", "number": 3, "title": "Implement launch brief"}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(
                handler.target_instructions,
                "discover_target_instruction_paths",
                return_value=["C:/target/repo/AGENTS.md"],
            ):
                prompt = handler.build_thin_prompt(
                    item,
                    "state:ready-for-dev",
                    "developer",
                    os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                    "Watchtower/runs/issue-3/run-001-developer/launch-brief.md",
                )

        self.assertIn("- target repository guidance: available in launch brief", prompt)

    def test_build_thin_prompt_omits_target_repository_guidance_note_when_none_discovered(self):
        item = {"type": "issue", "number": 3, "title": "Implement launch brief"}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(
                handler.target_instructions,
                "discover_target_instruction_paths",
                return_value=[],
            ):
                prompt = handler.build_thin_prompt(
                    item,
                    "state:ready-for-dev",
                    "developer",
                    os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                    "Watchtower/runs/issue-3/run-001-developer/launch-brief.md",
                )

        self.assertNotIn("- target repository guidance: available in launch brief", prompt)

    def test_build_thin_prompt_includes_execution_branch_when_present(self):
        item = {
            "type": "issue",
            "number": 9,
            "title": "Architect context",
            "execution_branch": "main",
        }

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            prompt = handler.build_thin_prompt(
                item,
                "state:ready-for-architecture",
                "architect",
                os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                "Watchtower/runs/issue-9/run-001-architect/launch-brief.md",
            )

        self.assertIn("- execution branch: main", prompt)

    def test_build_thin_prompt_for_reviewer_includes_exact_review_result_path_instruction(self):
        item = {
            "type": "issue",
            "number": 9,
            "title": "Review changes",
        }
        review_result_path = "C:/abs/Watchtower/runs/issue-9/run-001-reviewer/review-result.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            prompt = handler.build_thin_prompt(
                item,
                "state:ready-for-review",
                "reviewer",
                os.path.normpath(os.path.join("TheFarm", "roles", "reviewer.md")),
                "Watchtower/runs/issue-9/run-001-reviewer/launch-brief.md",
                review_result_path=review_result_path,
            )

        self.assertIn("- reviewer artifact contract: You must write `review-result.md` before exiting.", prompt)
        self.assertIn(f"- reviewer result artifact absolute path: {review_result_path}", prompt)
        self.assertIn("  - Outcome: APPROVED", prompt)
        self.assertIn("  - Outcome: CHANGES_REQUESTED", prompt)
        self.assertIn("  - Outcome: BLOCKED", prompt)

    def test_build_thin_prompt_for_architect_review_includes_exact_result_path_instruction(self):
        item = {
            "type": "issue",
            "number": 12,
            "title": "Architect review",
        }
        architect_review_result_path = "C:/abs/Watchtower/runs/issue-12/run-001-architect-review/architect-review-result.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            prompt = handler.build_thin_prompt(
                item,
                "state:ready-for-architect-review",
                "architect-review",
                os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                "Watchtower/runs/issue-12/run-001-architect-review/launch-brief.md",
                review_result_path=architect_review_result_path,
            )

        self.assertIn(
            "- architect review artifact contract: You must write `architect-review-result.md` before exiting.",
            prompt,
        )
        self.assertIn(f"- architect review result artifact absolute path: {architect_review_result_path}", prompt)
        self.assertIn("  - Outcome: APPROVED", prompt)
        self.assertIn("  - Outcome: CHANGES_REQUESTED", prompt)
        self.assertIn("  - Outcome: BLOCKED", prompt)

    def test_launch_agent_junie_runs_with_target_workspace_and_task_handoff(self):
        item = {
            "type": "issue",
            "number": 3,
            "title": "Implement launch brief path handoff",
            "url": "https://github.com/owner/repo/issues/3",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-3/run-001-developer/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-3/run-001-developer/launch-brief.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                    with patch.object(
                        handler,
                        "finalize_developer_success_with_pull_request",
                        return_value=True,
                    ) as mock_finalize:
                        with patch("builtins.print") as mock_print:
                            launched = handler.launch_agent(
                                item,
                                "state:ready-for-dev",
                                config,
                                os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                                launch_brief_path,
                            )

        self.assertTrue(launched)
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(command[0], "junie")
        self.assertEqual(command[1:3], ["--project", "C:/target/repo"])
        self.assertEqual(command[3:5], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[5:7], ["--effort", "medium"])
        self.assertEqual(
            command[7],
            f"Read the launch brief at {absolute_launch_brief_path} and execute the assigned workflow.",
        )

        self.assertEqual(mock_subprocess_run.call_args.kwargs["cwd"], "C:/target/repo")
        self.assertTrue(mock_subprocess_run.call_args.kwargs["text"])
        self.assertNotIn("input", mock_subprocess_run.call_args.kwargs)
        mock_finalize.assert_called_once_with(
            item,
            launch_brief_path,
            from_state_label="state:ready-for-dev",
        )

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any(f"[Dispatch] Launch brief display path: {launch_brief_path}" in line for line in printed_lines))
        self.assertTrue(
            any(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}" in line for line in printed_lines)
        )
        self.assertTrue(any("[Dispatch] Junie target repo path: C:/target/repo" in line for line in printed_lines))
        self.assertTrue(any("Junie handoff path: passing short positional task argument" in line for line in printed_lines))
        self.assertTrue(any("[Dispatch] Junie execution cwd: C:/target/repo" in line for line in printed_lines))
        self.assertTrue(any("[Dispatch] Junie exit code: 0" in line for line in printed_lines))

        executing_lines = [line for line in printed_lines if line.startswith("[Dispatch] Executing: ")]
        self.assertEqual(len(executing_lines), 1)
        self.assertIn("--project C:/target/repo", executing_lines[0])
        self.assertIn("--model gpt-5.3-codex", executing_lines[0])
        self.assertIn("--effort medium", executing_lines[0])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", executing_lines[0])
        self.assertFalse(any("--prompt-file" in line for line in executing_lines))

    def test_launch_agent_junie_non_zero_exit_comments_for_human_inspection(self):
        item = {
            "type": "issue",
            "number": 15,
            "title": "Fix README implementation",
            "url": "https://github.com/owner/repo/issues/15",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-15/run-001-developer/launch-brief.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.subprocess, "run", return_value=Mock(returncode=7)):
                with patch.object(handler, "add_comment") as mock_add_comment:
                    with patch("builtins.print") as mock_print:
                        launched = handler.launch_agent(
                            item,
                            "state:ready-for-dev",
                            config,
                            os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                            launch_brief_path,
                        )

        self.assertFalse(launched)
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("exited with non-zero status (7)", item["comment"])
        self.assertIn("lock label `state:agent-in-progress` remains", item["comment"])
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Dispatch] Junie exit code: 7" in line for line in printed_lines))
        self.assertTrue(any("human inspection is required" in line for line in printed_lines))

    def test_launch_agent_junie_developer_success_runs_post_run_pr_flow(self):
        item = {
            "type": "issue",
            "number": 16,
            "title": "Implement feature",
            "url": "https://github.com/owner/repo/issues/16",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value="C:/abs/brief.md"):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                    with patch.object(
                        handler,
                        "finalize_developer_success_with_pull_request",
                        return_value=True,
                    ) as mock_finalize:
                        launched = handler.launch_agent(
                            item,
                            "state:ready-for-dev",
                            config,
                            os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                            "Watchtower/runs/issue-16/run-001-developer/launch-brief.md",
                        )

        self.assertTrue(launched)
        mock_finalize.assert_called_once_with(
            item,
            "Watchtower/runs/issue-16/run-001-developer/launch-brief.md",
            from_state_label="state:ready-for-dev",
        )

    def test_launch_agent_junie_changes_requested_success_runs_post_run_pr_flow(self):
        item = {
            "type": "issue",
            "number": 66,
            "title": "Implement review follow-up",
            "url": "https://github.com/owner/repo/issues/66",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value="C:/abs/brief.md"):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                    with patch.object(
                        handler,
                        "finalize_developer_success_with_pull_request",
                        return_value=True,
                    ) as mock_finalize:
                        launched = handler.launch_agent(
                            item,
                            "state:changes-requested",
                            config,
                            os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                            "Watchtower/runs/issue-66/run-002-developer/launch-brief.md",
                        )

        self.assertTrue(launched)
        mock_finalize.assert_called_once_with(
            item,
            "Watchtower/runs/issue-66/run-002-developer/launch-brief.md",
            from_state_label="state:changes-requested",
        )

    def test_launch_agent_junie_developer_non_zero_exit_does_not_advance_workflow_labels(self):
        item = {
            "type": "issue",
            "number": 17,
            "title": "Developer run fails",
            "url": "https://github.com/owner/repo/issues/17",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value="C:/abs/brief.md"):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=9)):
                    with patch.object(handler, "add_comment") as mock_add_comment:
                        with patch.object(handler, "advance_developer_workflow_on_success") as mock_advance:
                            launched = handler.launch_agent(
                                item,
                                "state:ready-for-dev",
                                config,
                                os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                                "Watchtower/runs/issue-17/run-001-developer/launch-brief.md",
                            )

        self.assertFalse(launched)
        mock_add_comment.assert_called_once_with(item)
        mock_advance.assert_not_called()

    def test_finalize_developer_success_with_changes_commits_pushes_creates_pr_then_transitions(self):
        item = {
            "type": "issue",
            "number": 31,
            "title": "Add PR automation",
            "url": "https://github.com/owner/repo/issues/31",
            "working_branch": "circus/issue-31-add-pr-automation",
        }

        git_results = [
            Mock(returncode=0, stdout=" M Handler/handler.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="[circus/issue-31-add-pr-automation abc123] commit\n", stderr=""),
            Mock(returncode=0, stdout="branch set up\n", stderr=""),
        ]

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "run_git_command_in_repo", side_effect=git_results) as mock_git:
                    with patch.object(
                        handler,
                        "run_command",
                        side_effect=["[]", "https://github.com/owner/repo/pull/41"],
                    ) as mock_run_command:
                        with patch.object(handler, "advance_developer_workflow_on_success", return_value=True) as mock_advance:
                            with patch.object(handler, "add_comment") as mock_add_comment:
                                transitioned = handler.finalize_developer_success_with_pull_request(
                                    item,
                                    "Watchtower/runs/issue-31/run-001-developer/launch-brief.md",
                                )

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_git.call_args_list,
            [
                unittest.mock.call("C:/target/repo", ["status", "--porcelain"]),
                unittest.mock.call("C:/target/repo", ["add", "-A"]),
                unittest.mock.call("C:/target/repo", ["commit", "-m", "Implement issue #31: Add PR automation"]),
                unittest.mock.call("C:/target/repo", ["push", "-u", "origin", "circus/issue-31-add-pr-automation"]),
            ],
        )
        self.assertEqual(len(mock_run_command.call_args_list), 2)
        self.assertIn("gh pr list --repo owner/repo", mock_run_command.call_args_list[0].args[0])
        self.assertIn("gh pr create --repo owner/repo", mock_run_command.call_args_list[1].args[0])
        self.assertIn("--body-file", mock_run_command.call_args_list[1].args[0])
        self.assertNotIn("--body ", mock_run_command.call_args_list[1].args[0])
        self.assertIn('"Issue #31: Add PR automation"', mock_run_command.call_args_list[1].args[0])
        mock_advance.assert_called_once_with(item, from_state_label="state:ready-for-dev")
        mock_add_comment.assert_not_called()

    def test_create_pull_request_with_body_file_writes_real_newlines_and_cleans_up_temp_file(self):
        captured = {}

        pr_body = "Closes #2\n\n## Linked Issue\n- https://github.com/owner/repo/issues/2\n"

        def fake_run_command(cmd):
            captured["command"] = cmd

            self.assertIn("gh pr create --repo owner/repo", cmd)
            self.assertIn("--body-file", cmd)
            self.assertNotIn("--body ", cmd)

            body_file_match = re.search(r'--body-file ("(?:[^"\\]|\\.)*")', cmd)
            self.assertIsNotNone(body_file_match)

            body_file_path = json.loads(body_file_match.group(1))
            captured["body_file_path"] = body_file_path

            with open(body_file_path, "r", encoding="utf-8") as body_file:
                captured["body_file_contents"] = body_file.read()

            return "https://github.com/owner/repo/pull/98"

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", side_effect=fake_run_command):
                pr_url = handler.create_pull_request_with_body_file(
                    "circus/issue-2-real-newlines",
                    "Issue #2: Preserve markdown newlines",
                    pr_body,
                )

        self.assertEqual(pr_url, "https://github.com/owner/repo/pull/98")
        self.assertEqual(captured["body_file_contents"], pr_body)
        self.assertIn("\n## Linked Issue\n", captured["body_file_contents"])
        self.assertNotIn("\\n", captured["body_file_contents"])
        self.assertFalse(os.path.exists(captured["body_file_path"]))

    def test_finalize_developer_success_reuses_existing_pr_without_duplicate_creation(self):
        item = {
            "type": "issue",
            "number": 32,
            "title": "Use existing PR",
            "url": "https://github.com/owner/repo/issues/32",
            "working_branch": "circus/issue-32-use-existing-pr",
        }

        git_results = [
            Mock(returncode=0, stdout=" M Handler/handler.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="[circus/issue-32-use-existing-pr abc123] commit\n", stderr=""),
            Mock(returncode=0, stdout="branch set up\n", stderr=""),
        ]

        existing_pr_payload = '[{"url":"https://github.com/owner/repo/pull/77"}]'

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "run_git_command_in_repo", side_effect=git_results):
                    with patch.object(handler, "run_command", return_value=existing_pr_payload) as mock_run_command:
                        with patch.object(handler, "advance_developer_workflow_on_success", return_value=True) as mock_advance:
                            transitioned = handler.finalize_developer_success_with_pull_request(
                                item,
                                "Watchtower/runs/issue-32/run-001-developer/launch-brief.md",
                            )

        self.assertTrue(transitioned)
        self.assertEqual(len(mock_run_command.call_args_list), 1)
        self.assertIn("gh pr list --repo owner/repo", mock_run_command.call_args_list[0].args[0])
        self.assertNotIn("gh pr create", mock_run_command.call_args_list[0].args[0])
        mock_advance.assert_called_once_with(item, from_state_label="state:ready-for-dev")

    def test_finalize_developer_success_push_failure_prevents_transition(self):
        item = {
            "type": "issue",
            "number": 33,
            "title": "Push fails",
            "url": "https://github.com/owner/repo/issues/33",
            "working_branch": "circus/issue-33-push-fails",
        }

        git_results = [
            Mock(returncode=0, stdout=" M Handler/handler.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="[circus/issue-33-push-fails abc123] commit\n", stderr=""),
            Mock(returncode=1, stdout="", stderr="remote rejected"),
        ]

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "run_git_command_in_repo", side_effect=git_results):
                with patch.object(handler, "run_command") as mock_run_command:
                    with patch.object(handler, "advance_developer_workflow_on_success") as mock_advance:
                        with patch.object(handler, "add_comment") as mock_add_comment:
                            transitioned = handler.finalize_developer_success_with_pull_request(
                                item,
                                "Watchtower/runs/issue-33/run-001-developer/launch-brief.md",
                            )

        self.assertFalse(transitioned)
        mock_run_command.assert_not_called()
        mock_advance.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("failed to prepare a pull request", item["comment"])
        self.assertIn("unable to push developer branch", item["comment"])

    def test_finalize_developer_success_pr_creation_failure_prevents_transition(self):
        item = {
            "type": "issue",
            "number": 34,
            "title": "PR create fails",
            "url": "https://github.com/owner/repo/issues/34",
            "working_branch": "circus/issue-34-pr-create-fails",
        }

        git_results = [
            Mock(returncode=0, stdout=" M Handler/handler.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="[circus/issue-34-pr-create-fails abc123] commit\n", stderr=""),
            Mock(returncode=0, stdout="branch set up\n", stderr=""),
        ]

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "run_git_command_in_repo", side_effect=git_results):
                with patch.object(handler, "run_command", side_effect=["[]", None]) as mock_run_command:
                    with patch.object(handler, "advance_developer_workflow_on_success") as mock_advance:
                        with patch.object(handler, "add_comment") as mock_add_comment:
                            transitioned = handler.finalize_developer_success_with_pull_request(
                                item,
                                "Watchtower/runs/issue-34/run-001-developer/launch-brief.md",
                            )

        self.assertFalse(transitioned)
        self.assertEqual(len(mock_run_command.call_args_list), 2)
        self.assertIn("gh pr list", mock_run_command.call_args_list[0].args[0])
        self.assertIn("gh pr create", mock_run_command.call_args_list[1].args[0])
        mock_advance.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("failed to prepare a pull request", item["comment"])
        self.assertIn("unable to create pull request", item["comment"])

    def test_finalize_developer_success_without_changes_adds_no_change_comment(self):
        item = {
            "type": "issue",
            "number": 35,
            "title": "No-op run",
            "url": "https://github.com/owner/repo/issues/35",
            "working_branch": "circus/issue-35-no-op-run",
        }

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(
                handler,
                "run_git_command_in_repo",
                return_value=Mock(returncode=0, stdout="", stderr=""),
            ):
                with patch.object(handler, "run_command") as mock_run_command:
                    with patch.object(handler, "advance_developer_workflow_on_success") as mock_advance:
                        with patch.object(handler, "add_comment") as mock_add_comment:
                            transitioned = handler.finalize_developer_success_with_pull_request(
                                item,
                                "Watchtower/runs/issue-35/run-001-developer/launch-brief.md",
                            )

        self.assertFalse(transitioned)
        mock_run_command.assert_not_called()
        mock_advance.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("detected no changes", item["comment"])
        self.assertIn("No pull request was created", item["comment"])

    def test_finalize_developer_success_with_workspace_path_uses_workspace_for_git_operations(self):
        item = {
            "type": "issue",
            "number": 49,
            "title": "Fix workspace post-run detection",
            "url": "https://github.com/owner/repo/issues/49",
            "working_branch": "circus/issue-49-fix-workspace-path",
            "workspace_path": "C:/worktrees/issue-49",
        }

        git_results = [
            Mock(returncode=0, stdout=" M Handler/developer_flow.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="[circus/issue-49-fix-workspace-path abc123] commit\n", stderr=""),
            Mock(returncode=0, stdout="branch set up\n", stderr=""),
        ]

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "run_git_command_in_repo", side_effect=git_results) as mock_git:
                    with patch.object(handler, "run_command", side_effect=["[]", "https://github.com/owner/repo/pull/49"]):
                        with patch.object(handler, "advance_developer_workflow_on_success", return_value=True) as mock_advance:
                            transitioned = handler.finalize_developer_success_with_pull_request(
                                item,
                                "Watchtower/runs/issue-49/run-001-developer/launch-brief.md",
                            )

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_git.call_args_list,
            [
                unittest.mock.call("C:/worktrees/issue-49", ["status", "--porcelain"]),
                unittest.mock.call("C:/worktrees/issue-49", ["add", "-A"]),
                unittest.mock.call("C:/worktrees/issue-49", ["commit", "-m", "Implement issue #49: Fix workspace post-run detection"]),
                unittest.mock.call("C:/worktrees/issue-49", ["push", "-u", "origin", "circus/issue-49-fix-workspace-path"]),
            ],
        )
        mock_advance.assert_called_once_with(item, from_state_label="state:ready-for-dev")

    def test_finalize_developer_success_without_changes_mentions_inspected_workspace_path(self):
        item = {
            "type": "issue",
            "number": 49,
            "title": "No-op workspace run",
            "url": "https://github.com/owner/repo/issues/49",
            "working_branch": "circus/issue-49-no-op-workspace",
            "workspace_path": "C:/worktrees/issue-49",
        }

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(
                handler,
                "run_git_command_in_repo",
                return_value=Mock(returncode=0, stdout="", stderr=""),
            ) as mock_git:
                with patch.object(handler, "run_command") as mock_run_command:
                    with patch.object(handler, "advance_developer_workflow_on_success") as mock_advance:
                        with patch.object(handler, "add_comment") as mock_add_comment:
                            transitioned = handler.finalize_developer_success_with_pull_request(
                                item,
                                "Watchtower/runs/issue-49/run-001-developer/launch-brief.md",
                            )

        self.assertFalse(transitioned)
        self.assertEqual(
            mock_git.call_args_list,
            [unittest.mock.call("C:/worktrees/issue-49", ["status", "--porcelain"])],
        )
        mock_run_command.assert_not_called()
        mock_advance.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("Inspected path: `C:/worktrees/issue-49`", item["comment"])

    def test_finalize_developer_success_resumed_run_with_workspace_path_uses_workspace_even_with_existing_branch(self):
        item = {
            "type": "issue",
            "number": 49,
            "title": "Resume run with pending workspace changes",
            "url": "https://github.com/owner/repo/issues/49",
            "working_branch": "circus/issue-49-resume",
            "workspace_path": "C:/worktrees/issue-49",
        }

        git_results = [
            Mock(returncode=0, stdout=" M Handler/handler.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="[circus/issue-49-resume abc123] commit\n", stderr=""),
            Mock(returncode=0, stdout="branch set up\n", stderr=""),
        ]

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "run_git_command_in_repo", side_effect=git_results) as mock_git:
                    with patch.object(handler, "run_command", side_effect=["[]", "https://github.com/owner/repo/pull/50"]):
                        with patch.object(handler, "advance_developer_workflow_on_success", return_value=True):
                            with patch.object(handler, "get_current_git_branch") as mock_get_branch:
                                transitioned = handler.finalize_developer_success_with_pull_request(
                                    item,
                                    "Watchtower/runs/issue-49/run-001-developer/launch-brief.md",
                                )

        self.assertTrue(transitioned)
        mock_get_branch.assert_not_called()
        self.assertEqual(mock_git.call_args_list[0], unittest.mock.call("C:/worktrees/issue-49", ["status", "--porcelain"]))
        self.assertEqual(mock_git.call_args_list[3], unittest.mock.call("C:/worktrees/issue-49", ["push", "-u", "origin", "circus/issue-49-resume"]))

    def test_finalize_developer_success_without_workspace_path_falls_back_to_target_repo(self):
        item = {
            "type": "issue",
            "number": 49,
            "title": "Fallback to target repo",
            "url": "https://github.com/owner/repo/issues/49",
            "working_branch": "circus/issue-49-fallback",
        }

        git_results = [
            Mock(returncode=0, stdout=" M Handler/developer_flow.py\n", stderr=""),
            Mock(returncode=0, stdout="", stderr=""),
            Mock(returncode=0, stdout="[circus/issue-49-fallback abc123] commit\n", stderr=""),
            Mock(returncode=0, stdout="branch set up\n", stderr=""),
        ]

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "run_git_command_in_repo", side_effect=git_results) as mock_git:
                    with patch.object(handler, "run_command", side_effect=["[]", "https://github.com/owner/repo/pull/51"]):
                        with patch.object(handler, "advance_developer_workflow_on_success", return_value=True):
                            transitioned = handler.finalize_developer_success_with_pull_request(
                                item,
                                "Watchtower/runs/issue-49/run-001-developer/launch-brief.md",
                            )

        self.assertTrue(transitioned)
        self.assertEqual(mock_git.call_args_list[0], unittest.mock.call("C:/target/repo", ["status", "--porcelain"]))
        self.assertEqual(mock_git.call_args_list[3], unittest.mock.call("C:/target/repo", ["push", "-u", "origin", "circus/issue-49-fallback"]))

    def test_build_codex_architect_task_text_includes_handoff_and_comment_requirements(self):
        task_text = handler.build_codex_architect_task_text("C:/abs/Watchtower/runs/issue-9/run-001-architect/launch-brief.md")

        self.assertIn(
            "Read the launch brief at C:/abs/Watchtower/runs/issue-9/run-001-architect/launch-brief.md",
            task_text,
        )
        self.assertIn("execute the architect workflow", task_text)
        self.assertIn("Produce or update the architecture handoff artifact", task_text)
        self.assertIn("leave a GitHub comment summarizing the handoff or blocker", task_text)

    def test_build_codex_systems_architect_task_text_mentions_structured_recommendation_contract(self):
        task_text = handler.build_codex_systems_architect_task_text(
            "C:/abs/Watchtower/runs/issue-70/run-001-systems-architect/launch-brief.md"
        )

        self.assertIn(
            "Read the launch brief at C:/abs/Watchtower/runs/issue-70/run-001-systems-architect/launch-brief.md",
            task_text,
        )
        self.assertIn("execute the systems architect workflow", task_text)
        self.assertIn("structured GitHub issue comment as the primary human review artifact", task_text)
        self.assertIn("## Systems Architect Recommendation", task_text)
        self.assertIn("### Recommendation", task_text)
        self.assertIn("### Rationale", task_text)
        self.assertIn("### Proposed Follow-up", task_text)
        self.assertIn("### Risks / Tradeoffs", task_text)
        self.assertIn("state:ready-for-roadmap-update", task_text)
        self.assertIn("state:systems-architecture-changes-requested", task_text)
        self.assertIn("Watchtower artifacts for run history and observability", task_text)
        self.assertIn("If blocked, leave a GitHub comment", task_text)
        self.assertNotIn("architecture handoff", task_text)

    def test_build_codex_roadmap_updater_task_text_mentions_documentation_pr_contract(self):
        task_text = handler.build_codex_roadmap_updater_task_text(
            "C:/abs/Watchtower/runs/issue-20/run-001-roadmap-updater/launch-brief.md"
        )

        self.assertIn(
            "Read the launch brief at C:/abs/Watchtower/runs/issue-20/run-001-roadmap-updater/launch-brief.md",
            task_text,
        )
        self.assertIn("execute the roadmap updater workflow", task_text)
        self.assertIn("human-approved Systems Architect recommendation", task_text)
        self.assertIn("Update documentation and knowledge artifacts", task_text)
        self.assertIn("Create a documentation PR", task_text)
        self.assertIn("Leave a summary comment on the issue linking to the PR", task_text)
        self.assertIn("Do not modify runtime code", task_text)
        self.assertIn("Do not modify workflow labels directly", task_text)
        self.assertIn("Do not auto-merge", task_text)
        self.assertNotIn("architecture handoff", task_text)

    def test_build_codex_implementation_planner_task_text_mentions_plan_contract(self):
        task_text = handler.build_codex_implementation_planner_task_text(
            "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md",
            "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/implementation-plan.md",
        )

        self.assertIn(
            "Read the launch brief at C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md",
            task_text,
        )
        self.assertIn("execute the implementation planner workflow", task_text)
        self.assertIn("Review the architecture handoff", task_text)
        self.assertIn("Publish a structured implementation plan as a GitHub issue comment", task_text)
        self.assertIn(
            "Write implementation-plan.md to this exact absolute path: "
            "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/implementation-plan.md before exiting",
            task_text,
        )
        self.assertIn("Do not modify runtime code", task_text)
        self.assertIn("Do not modify workflow labels directly", task_text)

    def test_is_codex_sandbox_bypass_enabled_defaults_to_false_when_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(handler.is_codex_sandbox_bypass_enabled())

    def test_is_codex_sandbox_bypass_enabled_only_for_true_case_insensitive(self):
        with patch.dict(os.environ, {"CIRCUS_CODEX_BYPASS_SANDBOX": "true"}, clear=True):
            self.assertTrue(handler.is_codex_sandbox_bypass_enabled())

        with patch.dict(os.environ, {"CIRCUS_CODEX_BYPASS_SANDBOX": "TrUe"}, clear=True):
            self.assertTrue(handler.is_codex_sandbox_bypass_enabled())

        with patch.dict(os.environ, {"CIRCUS_CODEX_BYPASS_SANDBOX": "false"}, clear=True):
            self.assertFalse(handler.is_codex_sandbox_bypass_enabled())

        with patch.dict(os.environ, {"CIRCUS_CODEX_BYPASS_SANDBOX": "1"}, clear=True):
            self.assertFalse(handler.is_codex_sandbox_bypass_enabled())

    def test_build_codex_command_with_optional_sandbox_bypass_adds_flag_only_when_enabled(self):
        enabled_command = handler.build_codex_command_with_optional_sandbox_bypass(
            "gpt-5.3-codex",
            "C:/target/repo",
            "Prompt text",
            bypass_sandbox=True,
        )
        disabled_command = handler.build_codex_command_with_optional_sandbox_bypass(
            "gpt-5.3-codex",
            "C:/target/repo",
            "Prompt text",
            bypass_sandbox=False,
        )

        self.assertEqual(enabled_command[0], "codex")
        self.assertEqual(enabled_command[1], "exec")
        self.assertEqual(enabled_command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(enabled_command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", enabled_command)
        self.assertEqual(enabled_command[-1], "Prompt text")

        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", disabled_command)
        self.assertEqual(disabled_command[1], "exec")
        self.assertEqual(disabled_command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(disabled_command[4:6], ["--cd", "C:/target/repo"])
        self.assertEqual(disabled_command[-1], "Prompt text")

    def test_label_map_routes_ready_for_architect_review_to_codex_architect_review_mode(self):
        config = handler.LABEL_MAP["state:ready-for-architect-review"]

        self.assertEqual(config["agent"], "codex")
        self.assertEqual(config["mode"], "architect-review")

    def test_label_map_routes_ready_for_implementation_planning_to_codex_implementation_planner_mode(self):
        config = handler.LABEL_MAP["state:ready-for-implementation-planning"]

        self.assertEqual(config["agent"], "codex")
        self.assertEqual(config["mode"], "implementation-planner")

    def test_required_workflow_labels_include_ready_for_system_architecture(self):
        self.assertIn("state:ready-for-systems-architecture", workflow_labels.REQUIRED_WORKFLOW_LABELS)

    def test_required_workflow_labels_define_planned_as_non_dispatch_pending_human_approval(self):
        planned = workflow_labels.REQUIRED_WORKFLOW_LABELS["state:planned"]

        self.assertEqual(
            planned["description"],
            "Generated implementation issue pending human plan approval; not dispatchable.",
        )

    def test_planned_state_is_human_owned_and_not_dispatchable(self):
        planned = workflow_states.WORKFLOW_STATES["state:planned"]

        self.assertTrue(planned["human_owned"])
        self.assertNotIn("dispatch", planned)
        self.assertNotIn("state:planned", handler.LABEL_MAP)

    def test_label_map_is_derived_from_workflow_state_dispatch_definitions(self):
        expected = {
            label: state["dispatch"]
            for label, state in workflow_states.WORKFLOW_STATES.items()
            if state.get("dispatch")
        }

        self.assertEqual(handler.LABEL_MAP, expected)

    def test_required_workflow_labels_are_derived_from_workflow_states(self):
        expected = {
            label: {
                "description": state["description"],
                "color": state["color"],
            }
            for label, state in workflow_states.WORKFLOW_STATES.items()
        }

        self.assertEqual(workflow_labels.REQUIRED_WORKFLOW_LABELS, expected)

    def test_resolve_dispatch_config_routes_ready_for_system_architecture_to_codex_systems_architect(self):
        item = {"type": "issue", "number": 71, "labels": []}

        state_label, dispatch_config = handler.resolve_dispatch_config(
            item,
            ["state:ready-for-systems-architecture"],
        )

        self.assertEqual(state_label, "state:ready-for-systems-architecture")
        self.assertEqual(dispatch_config["agent"], "codex")
        self.assertEqual(dispatch_config["mode"], "systems-architect")

    def test_resolve_dispatch_config_routes_systems_architecture_changes_requested_to_codex_systems_architect(self):
        item = {"type": "issue", "number": 72, "labels": []}

        state_label, dispatch_config = handler.resolve_dispatch_config(
            item,
            ["state:systems-architecture-changes-requested"],
        )

        self.assertEqual(state_label, "state:systems-architecture-changes-requested")
        self.assertEqual(dispatch_config["agent"], "codex")
        self.assertEqual(dispatch_config["mode"], "systems-architect")

    def test_resolve_dispatch_config_routes_ready_for_roadmap_update_to_codex_roadmap_updater(self):
        item = {"type": "issue", "number": 20, "labels": []}

        state_label, dispatch_config = handler.resolve_dispatch_config(
            item,
            ["state:ready-for-roadmap-update"],
        )

        self.assertEqual(state_label, "state:ready-for-roadmap-update")
        self.assertEqual(dispatch_config["agent"], "codex")
        self.assertEqual(dispatch_config["mode"], "roadmap-updater")

    def test_build_codex_reviewer_task_text_contains_required_contract_and_safety_instructions(self):
        task_text = handler.build_codex_reviewer_task_text(
            "C:/abs/Watchtower/runs/issue-9/run-001-reviewer/launch-brief.md",
            "https://github.com/owner/repo/pull/99",
            "C:/abs/Watchtower/runs/issue-9/run-001-reviewer/review-result.md",
        )

        self.assertIn(
            "Read the launch brief at C:/abs/Watchtower/runs/issue-9/run-001-reviewer/launch-brief.md",
            task_text,
        )
        self.assertIn("execute the reviewer workflow", task_text)
        self.assertIn("Review the linked pull request at https://github.com/owner/repo/pull/99", task_text)
        self.assertIn(
            "Write review-result.md to this exact absolute path: C:/abs/Watchtower/runs/issue-9/run-001-reviewer/review-result.md",
            task_text,
        )
        self.assertIn("Outcome: APPROVED", task_text)
        self.assertIn("Outcome: CHANGES_REQUESTED", task_text)
        self.assertIn("Outcome: BLOCKED", task_text)
        self.assertIn("Leave a review comment on the pull request", task_text)
        self.assertIn("Do not modify workflow labels directly", task_text)
        self.assertIn("Do not auto-merge", task_text)

    def test_build_codex_architect_review_task_text_contains_required_contract_and_safety_instructions(self):
        task_text = handler.build_codex_architect_review_task_text(
            "C:/abs/Watchtower/runs/issue-9/run-001-architect-review/launch-brief.md",
            "https://github.com/owner/repo/pull/99",
            "C:/abs/Watchtower/runs/issue-9/run-001-architect-review/architect-review-result.md",
        )

        self.assertIn(
            "Read the launch brief at C:/abs/Watchtower/runs/issue-9/run-001-architect-review/launch-brief.md",
            task_text,
        )
        self.assertIn("execute the architect review workflow", task_text)
        self.assertIn("Review the linked pull request at https://github.com/owner/repo/pull/99", task_text)
        self.assertIn(
            "Write architect-review-result.md to this exact absolute path: C:/abs/Watchtower/runs/issue-9/run-001-architect-review/architect-review-result.md",
            task_text,
        )
        self.assertIn("Outcome: APPROVED", task_text)
        self.assertIn("Outcome: CHANGES_REQUESTED", task_text)
        self.assertIn("Outcome: BLOCKED", task_text)
        self.assertIn("Comment on the pull request with architectural review findings", task_text)
        self.assertIn("Do not modify workflow labels directly", task_text)
        self.assertIn("Do not auto-merge", task_text)

    def test_launch_agent_codex_architect_runs_with_exec_cd_and_task_handoff(self):
        item = {
            "type": "issue",
            "number": 9,
            "title": "Define architecture handoff",
            "url": "https://github.com/owner/repo/issues/9",
        }
        config = {
            "agent": "codex",
            "mode": "architect",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-9/run-001-architect/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-9/run-001-architect/launch-brief.md"

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                        with patch.object(handler, "advance_architect_workflow_on_success") as mock_advance_transition:
                            with patch("builtins.print") as mock_print:
                                launched = handler.launch_agent(
                                    item,
                                    "state:ready-for-architecture",
                                    config,
                                    os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                                    launch_brief_path,
                                )

        self.assertTrue(launched)
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(command[0], "codex")
        self.assertEqual(command[1], "exec")
        self.assertEqual(command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", command[-1])
        self.assertIn("execute the architect workflow", command[-1])
        self.assertIn("Produce or update the architecture handoff artifact", command[-1])
        self.assertIn("leave a GitHub comment summarizing the handoff or blocker", command[-1])

        self.assertEqual(mock_subprocess_run.call_args.kwargs["cwd"], "C:/target/repo")
        self.assertTrue(mock_subprocess_run.call_args.kwargs["text"])
        mock_advance_transition.assert_called_once_with(item)

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any(f"[Dispatch] Launch brief display path: {launch_brief_path}" in line for line in printed_lines))
        self.assertTrue(
            any(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}" in line for line in printed_lines)
        )
        self.assertTrue(any("[Dispatch] Codex target repo path: C:/target/repo" in line for line in printed_lines))
        self.assertTrue(any("Codex sandbox bypass disabled (default-safe mode)" in line for line in printed_lines))
        self.assertTrue(any("Codex handoff path: passing short positional prompt argument" in line for line in printed_lines))
        self.assertTrue(any("[Dispatch] Codex execution cwd: C:/target/repo" in line for line in printed_lines))
        self.assertTrue(any("[Dispatch] Codex exit code: 0" in line for line in printed_lines))

        executing_lines = [line for line in printed_lines if line.startswith("[Dispatch] Executing: ")]
        self.assertEqual(len(executing_lines), 1)
        self.assertIn("codex exec --model gpt-5.3-codex --cd C:/target/repo", executing_lines[0])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", executing_lines[0])
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", executing_lines[0])

    def test_launch_agent_codex_architect_success_does_not_trigger_developer_pr_flow(self):
        item = {
            "type": "issue",
            "number": 62,
            "title": "Architect should not create PR",
            "url": "https://github.com/owner/repo/issues/62",
        }
        config = {
            "agent": "codex",
            "mode": "architect",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value="C:/abs/brief.md"):
                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                        with patch.object(handler, "advance_architect_workflow_on_success", return_value=True):
                            with patch.object(handler, "finalize_developer_success_with_pull_request") as mock_finalize:
                                launched = handler.launch_agent(
                                    item,
                                    "state:ready-for-architecture",
                                    config,
                                    os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                                    "Watchtower/runs/issue-62/run-001-architect/launch-brief.md",
                                )

        self.assertTrue(launched)
        mock_finalize.assert_not_called()

    def test_launch_agent_codex_architect_adds_sandbox_bypass_flag_when_enabled(self):
        item = {
            "type": "issue",
            "number": 12,
            "title": "Run architect with sandbox bypass",
            "url": "https://github.com/owner/repo/issues/12",
        }
        config = {
            "agent": "codex",
            "mode": "architect",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-12/run-001-architect/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-12/run-001-architect/launch-brief.md"

        with patch.dict(os.environ, {"CIRCUS_CODEX_BYPASS_SANDBOX": "true"}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                        with patch.object(handler, "advance_architect_workflow_on_success") as mock_advance_transition:
                            with patch("builtins.print") as mock_print:
                                launched = handler.launch_agent(
                                    item,
                                    "state:ready-for-architecture",
                                    config,
                                    os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                                    launch_brief_path,
                                )

        self.assertTrue(launched)
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(command[0], "codex")
        self.assertEqual(command[1], "exec")
        self.assertEqual(command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertEqual(command[-1], handler.build_codex_architect_task_text(absolute_launch_brief_path))
        mock_advance_transition.assert_called_once_with(item)

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("WARNING: Codex sandbox bypass ENABLED" in line for line in printed_lines))

        executing_lines = [line for line in printed_lines if line.startswith("[Dispatch] Executing: ")]
        self.assertEqual(len(executing_lines), 1)
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", executing_lines[0])

    def test_launch_agent_codex_systems_architect_runs_with_exec_cd_and_strategy_task_handoff(self):
        item = {
            "type": "issue",
            "number": 73,
            "title": "Run systems architect workflow",
            "url": "https://github.com/owner/repo/issues/73",
        }
        config = {
            "agent": "codex",
            "mode": "systems-architect",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-73/run-001-systems-architect/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-73/run-001-systems-architect/launch-brief.md"

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                        with patch.object(
                            handler,
                            "advance_systems_architect_workflow_on_success",
                            return_value=True,
                        ) as mock_advance_transition:
                            with patch.object(handler, "finalize_developer_success_with_pull_request") as mock_finalize:
                                launched = handler.launch_agent(
                                    item,
                                    "state:ready-for-systems-architecture",
                                    config,
                                    os.path.normpath(os.path.join("TheFarm", "roles", "systems-architect.md")),
                                    launch_brief_path,
                                )

        self.assertTrue(launched)
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(command[0], "codex")
        self.assertEqual(command[1], "exec")
        self.assertEqual(command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", command[-1])
        self.assertIn("execute the systems architect workflow", command[-1])
        self.assertIn("structured GitHub issue comment as the primary human review artifact", command[-1])
        self.assertNotIn("architecture handoff", command[-1])

        self.assertEqual(mock_subprocess_run.call_args.kwargs["cwd"], "C:/target/repo")
        self.assertTrue(mock_subprocess_run.call_args.kwargs["text"])
        mock_advance_transition.assert_called_once_with(
            item,
            from_state_label="state:ready-for-systems-architecture",
        )
        mock_finalize.assert_not_called()

    def test_launch_agent_codex_systems_architect_changes_requested_uses_strategy_task_handoff(self):
        item = {
            "type": "issue",
            "number": 173,
            "title": "Revise systems architecture recommendation",
            "url": "https://github.com/owner/repo/issues/173",
        }
        config = {
            "agent": "codex",
            "mode": "systems-architect",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-173/run-002-systems-architect/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-173/run-002-systems-architect/launch-brief.md"

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                        with patch.object(
                            handler,
                            "advance_systems_architect_workflow_on_success",
                            return_value=True,
                        ) as mock_advance_transition:
                            launched = handler.launch_agent(
                                item,
                                "state:systems-architecture-changes-requested",
                                config,
                                os.path.normpath(os.path.join("TheFarm", "roles", "systems-architect.md")),
                                launch_brief_path,
                            )

        self.assertTrue(launched)
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(command[0], "codex")
        self.assertEqual(command[1], "exec")
        self.assertEqual(command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", command[-1])
        self.assertIn("execute the systems architect workflow", command[-1])
        self.assertIn("structured GitHub issue comment as the primary human review artifact", command[-1])
        self.assertNotIn("architecture handoff", command[-1])

        self.assertEqual(mock_subprocess_run.call_args.kwargs["cwd"], "C:/target/repo")
        self.assertTrue(mock_subprocess_run.call_args.kwargs["text"])
        mock_advance_transition.assert_called_once_with(
            item,
            from_state_label="state:systems-architecture-changes-requested",
        )

    def test_launch_agent_codex_implementation_planner_routes_to_plan_review_state(self):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Draft implementation plan",
            "url": "https://github.com/owner/repo/issues/43",
        }
        config = {
            "agent": "codex",
            "mode": "implementation-planner",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        implementation_plan_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/implementation-plan.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                    with patch.object(
                        handler,
                        "build_implementation_plan_path",
                        return_value=implementation_plan_path,
                    ):
                        with patch.object(handler.os.path, "isfile", return_value=True):
                            with patch.object(handler, "parse_implementation_plan_outcome", return_value="READY"):
                                with patch.object(
                                    handler,
                                    "advance_implementation_planning_workflow_on_success",
                                    return_value=True,
                                ) as mock_advance_transition:
                                    launched = handler.launch_agent(
                                        item,
                                        "state:ready-for-implementation-planning",
                                        config,
                                        os.path.normpath(os.path.join("TheFarm", "roles", "implementation-planner.md")),
                                        launch_brief_path,
                                    )

        self.assertTrue(launched)
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(command[0], "codex")
        self.assertEqual(command[1], "exec")
        self.assertEqual(command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", command[-1])
        self.assertIn("execute the implementation planner workflow", command[-1])
        self.assertIn(
            f"Write implementation-plan.md to this exact absolute path: {implementation_plan_path}",
            command[-1],
        )

        mock_advance_transition.assert_called_once_with(
            item,
            from_state_label="state:ready-for-implementation-planning",
        )

    def test_launch_agent_codex_implementation_planner_missing_plan_artifact_fails_without_transition(self):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Draft implementation plan",
            "url": "https://github.com/owner/repo/issues/43",
        }
        config = {
            "agent": "codex",
            "mode": "implementation-planner",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        implementation_plan_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/implementation-plan.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                    with patch.object(
                        handler,
                        "build_implementation_plan_path",
                        return_value=implementation_plan_path,
                    ):
                        with patch.object(handler.os.path, "isfile", return_value=False):
                            with patch.object(handler, "add_comment") as mock_add_comment:
                                with patch.object(
                                    handler,
                                    "advance_implementation_planning_workflow_on_success",
                                ) as mock_advance_transition:
                                    with patch.object(handler, "update_run_status") as mock_update_status:
                                        launched = handler.launch_agent(
                                            item,
                                            "state:ready-for-implementation-planning",
                                            config,
                                            os.path.normpath(
                                                os.path.join("TheFarm", "roles", "implementation-planner.md")
                                            ),
                                            launch_brief_path,
                                        )

        self.assertFalse(launched)
        mock_subprocess_run.assert_called_once()
        mock_advance_transition.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertTrue(item.get("missing_implementation_plan_artifact"))
        self.assertIn("required artifact was not produced", item["comment"])
        self.assertIn(implementation_plan_path, item["comment"])
        implementation_planner = mock_update_status.call_args.kwargs["implementation_planner"]
        self.assertIsNone(implementation_planner["outcome"])
        self.assertFalse(implementation_planner["outcome_valid"])
        self.assertEqual(
            implementation_planner["diagnostic"],
            f"missing implementation plan artifact at {implementation_plan_path}",
        )
        self.assertEqual(implementation_planner["implementation_plan"], implementation_plan_path)

    def test_launch_agent_codex_implementation_planner_blocked_outcome_stops_without_transition(self):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Draft implementation plan",
            "url": "https://github.com/owner/repo/issues/43",
        }
        config = {
            "agent": "codex",
            "mode": "implementation-planner",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        implementation_plan_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/implementation-plan.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                    with patch.object(
                        handler,
                        "build_implementation_plan_path",
                        return_value=implementation_plan_path,
                    ):
                        with patch.object(handler.os.path, "isfile", return_value=True):
                            with patch.object(handler, "parse_implementation_plan_outcome", return_value="BLOCKED"):
                                with patch.object(handler, "add_comment") as mock_add_comment:
                                    with patch.object(
                                        handler,
                                        "advance_implementation_planning_workflow_on_success",
                                    ) as mock_advance_transition:
                                        with patch("builtins.print") as mock_print:
                                            with patch.object(handler, "update_run_status") as mock_update_status:
                                                launched = handler.launch_agent(
                                                    item,
                                                    "state:ready-for-implementation-planning",
                                                    config,
                                                    os.path.normpath(
                                                        os.path.join("TheFarm", "roles", "implementation-planner.md")
                                                    ),
                                                    launch_brief_path,
                                                )

        self.assertFalse(launched)
        mock_subprocess_run.assert_called_once()
        mock_advance_transition.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("blocked outcome", item["comment"])
        self.assertIn("`BLOCKED`", item["comment"])
        implementation_planner = mock_update_status.call_args.kwargs["implementation_planner"]
        self.assertEqual(implementation_planner["outcome"], "BLOCKED")
        self.assertTrue(implementation_planner["outcome_valid"])
        self.assertIsNone(implementation_planner["recommended_route"])
        mock_print.assert_any_call(
            "[Dispatch] Implementation planner reported BLOCKED outcome; "
            "workflow remains in implementation planning."
        )

    def test_launch_agent_codex_implementation_planner_escalation_required_outcome_stops_with_route_recommendation(
        self,
    ):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Draft implementation plan",
            "url": "https://github.com/owner/repo/issues/43",
        }
        config = {
            "agent": "codex",
            "mode": "implementation-planner",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        implementation_plan_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/implementation-plan.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                    with patch.object(
                        handler,
                        "build_implementation_plan_path",
                        return_value=implementation_plan_path,
                    ):
                        with patch.object(handler.os.path, "isfile", return_value=True):
                            with patch.object(
                                handler,
                                "parse_implementation_plan_outcome",
                                return_value="ESCALATION_REQUIRED",
                            ):
                                with patch.object(handler, "add_comment") as mock_add_comment:
                                    with patch.object(
                                        handler,
                                        "advance_implementation_planning_workflow_on_success",
                                    ) as mock_advance_transition:
                                        with patch("builtins.print") as mock_print:
                                            with patch.object(handler, "write_run_result"):
                                                with patch.object(handler, "update_run_status") as mock_update_status:
                                                    launched = handler.launch_agent(
                                                        item,
                                                        "state:ready-for-implementation-planning",
                                                        config,
                                                        os.path.normpath(
                                                            os.path.join("TheFarm", "roles", "implementation-planner.md")
                                                        ),
                                                        launch_brief_path,
                                                    )

        self.assertFalse(launched)
        mock_subprocess_run.assert_called_once()
        mock_advance_transition.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("`ESCALATION_REQUIRED`", item["comment"])
        self.assertIn("state:systems-architecture-changes-requested", item["comment"])
        self.assertEqual(mock_update_status.call_args.kwargs["outcome"], "escalation required")
        self.assertEqual(
            mock_update_status.call_args.kwargs["artifacts"]["recommended_route"],
            "state:systems-architecture-changes-requested",
        )
        implementation_planner = mock_update_status.call_args.kwargs["implementation_planner"]
        self.assertEqual(implementation_planner["outcome"], "ESCALATION_REQUIRED")
        self.assertEqual(
            implementation_planner["recommended_route"],
            "state:systems-architecture-changes-requested",
        )
        mock_print.assert_any_call(
            "[Dispatch] Implementation planner reported ESCALATION_REQUIRED outcome; "
            "recommended human route: state:systems-architecture-changes-requested."
        )

    def test_launch_agent_codex_implementation_planner_invalid_outcome_stops_without_transition(self):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Draft implementation plan",
            "url": "https://github.com/owner/repo/issues/43",
        }
        config = {
            "agent": "codex",
            "mode": "implementation-planner",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/launch-brief.md"
        implementation_plan_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/implementation-plan.md"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                    with patch.object(
                        handler,
                        "build_implementation_plan_path",
                        return_value=implementation_plan_path,
                    ):
                        with patch.object(handler.os.path, "isfile", return_value=True):
                            with patch.object(handler, "parse_implementation_plan_outcome", return_value=None):
                                with patch.object(handler, "add_comment") as mock_add_comment:
                                    with patch.object(
                                        handler,
                                        "advance_implementation_planning_workflow_on_success",
                                    ) as mock_advance_transition:
                                        with patch("builtins.print") as mock_print:
                                            with patch.object(handler, "update_run_status") as mock_update_status:
                                                launched = handler.launch_agent(
                                                    item,
                                                    "state:ready-for-implementation-planning",
                                                    config,
                                                    os.path.normpath(
                                                        os.path.join("TheFarm", "roles", "implementation-planner.md")
                                                    ),
                                                    launch_brief_path,
                                                )

        self.assertFalse(launched)
        mock_subprocess_run.assert_called_once()
        mock_advance_transition.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertTrue(item.get("invalid_implementation_plan_outcome"))
        self.assertIn("did not include a valid outcome declaration", item["comment"])
        implementation_planner = mock_update_status.call_args.kwargs["implementation_planner"]
        self.assertIsNone(implementation_planner["outcome"])
        self.assertFalse(implementation_planner["outcome_valid"])
        self.assertIn("missing or invalid", implementation_planner["diagnostic"])
        mock_print.assert_any_call(
            "[Dispatch] Implementation planner outcome was missing or invalid; "
            "workflow will not advance."
        )

    def test_launch_agent_codex_systems_architect_changes_requested_advances_to_human_review(self):
        item = {
            "type": "issue",
            "number": 174,
            "title": "Revise systems architecture recommendation",
            "url": "https://github.com/owner/repo/issues/174",
        }
        config = {
            "agent": "codex",
            "mode": "systems-architect",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-174/run-002-systems-architect/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-174/run-002-systems-architect/launch-brief.md"

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                        with patch.object(
                            handler,
                            "advance_systems_architect_workflow_on_success",
                            return_value=True,
                        ) as mock_advance_transition:
                            launched = handler.launch_agent(
                                item,
                                "state:systems-architecture-changes-requested",
                                config,
                                os.path.normpath(os.path.join("TheFarm", "roles", "systems-architect.md")),
                                launch_brief_path,
                            )

        self.assertTrue(launched)
        mock_advance_transition.assert_called_once_with(
            item,
            from_state_label="state:systems-architecture-changes-requested",
        )

    def test_launch_agent_codex_architect_non_zero_exit_does_not_advance_workflow_labels(self):
        item = {
            "type": "issue",
            "number": 13,
            "title": "Architect run fails",
            "url": "https://github.com/owner/repo/issues/13",
        }
        config = {
            "agent": "codex",
            "mode": "architect",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-13/run-001-architect/launch-brief.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-13/run-001-architect/launch-brief.md"

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=7)) as mock_subprocess_run:
                        with patch.object(handler, "add_comment") as mock_add_comment:
                            with patch.object(handler, "advance_architect_workflow_on_success") as mock_advance_transition:
                                launched = handler.launch_agent(
                                    item,
                                    "state:ready-for-architecture",
                                    config,
                                    os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                                    launch_brief_path,
                                )

        self.assertFalse(launched)
        mock_subprocess_run.assert_called_once()
        mock_add_comment.assert_called_once_with(item)
        mock_advance_transition.assert_not_called()
        self.assertIn("exited with non-zero status (7)", item["comment"])
        self.assertIn("lock label `state:agent-in-progress` remains in place", item["comment"])

    def test_advance_architect_workflow_on_success_transitions_labels(self):
        item = {
            "type": "issue",
            "number": 2,
            "title": "Architecture complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                with patch("builtins.print") as mock_print:
                    transitioned = handler.advance_architect_workflow_on_success(item)

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call(
                    'gh issue edit 2 --repo owner/repo --remove-label "state:agent-in-progress"'
                ),
                unittest.mock.call(
                    'gh issue edit 2 --repo owner/repo --remove-label "state:ready-for-architecture"'
                ),
                unittest.mock.call(
                    'gh issue edit 2 --repo owner/repo --add-label "state:ready-for-dev"'
                ),
            ],
        )

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Architect workflow completed successfully for issue #2." in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:agent-in-progress" in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:ready-for-architecture" in line for line in printed_lines))
        self.assertTrue(any("Adding label: state:ready-for-dev" in line for line in printed_lines))
        self.assertTrue(any("Workflow advanced to developer stage for issue #2." in line for line in printed_lines))

    def test_advance_systems_architect_workflow_on_success_transitions_to_human_review(self):
        item = {
            "type": "issue",
            "number": 74,
            "title": "Systems architecture complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                with patch("builtins.print") as mock_print:
                    transitioned = handler.advance_systems_architect_workflow_on_success(item)

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call(
                    'gh issue edit 74 --repo owner/repo --remove-label "state:agent-in-progress"'
                ),
                unittest.mock.call(
                    'gh issue edit 74 --repo owner/repo --remove-label "state:ready-for-systems-architecture"'
                ),
                unittest.mock.call(
                    'gh issue edit 74 --repo owner/repo --add-label "state:ready-for-human-review"'
                ),
            ],
        )

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Systems Architect workflow completed successfully for issue #74." in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:agent-in-progress" in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:ready-for-systems-architecture" in line for line in printed_lines))
        self.assertTrue(any("Adding label: state:ready-for-human-review" in line for line in printed_lines))

    def test_advance_systems_architect_workflow_on_success_removes_changes_requested_state_label(self):
        item = {
            "type": "issue",
            "number": 75,
            "title": "Systems architecture revisions complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                with patch("builtins.print") as mock_print:
                    transitioned = handler.advance_systems_architect_workflow_on_success(
                        item,
                        from_state_label="state:systems-architecture-changes-requested",
                    )

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call(
                    'gh issue edit 75 --repo owner/repo --remove-label "state:agent-in-progress"'
                ),
                unittest.mock.call(
                    'gh issue edit 75 --repo owner/repo --remove-label "state:systems-architecture-changes-requested"'
                ),
                unittest.mock.call(
                    'gh issue edit 75 --repo owner/repo --add-label "state:ready-for-human-review"'
                ),
            ],
        )

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Systems Architect workflow completed successfully for issue #75." in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:agent-in-progress" in line for line in printed_lines))
        self.assertTrue(
            any(
                "Removing label: state:systems-architecture-changes-requested" in line
                for line in printed_lines
            )
        )
        self.assertTrue(any("Adding label: state:ready-for-human-review" in line for line in printed_lines))

    def test_advance_implementation_planning_workflow_on_success_transitions_to_plan_review(self):
        item = {
            "type": "issue",
            "number": 143,
            "title": "Implementation planning complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                transitioned = handler.advance_implementation_planning_workflow_on_success(item)

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call(
                    'gh issue edit 143 --repo owner/repo --remove-label "state:agent-in-progress"'
                ),
                unittest.mock.call(
                    'gh issue edit 143 --repo owner/repo --remove-label "state:ready-for-implementation-planning"'
                ),
                unittest.mock.call(
                    'gh issue edit 143 --repo owner/repo --add-label "state:ready-for-implementation-plan-review"'
                ),
            ],
        )

    @patch("Handler.handler.validate_roadmap_updater_open_pull_request")
    @patch("Handler.handler.advance_roadmap_update_workflow_on_success")
    @patch("Handler.handler.subprocess.run")
    def test_roadmap_updater_success_path_validates_pr_and_transitions(
        self, mock_subprocess, mock_advance, mock_validate
    ):
        mock_validate.return_value = True
        mock_advance.return_value = True
        mock_subprocess.return_value = MagicMock(returncode=0)

        item = {
            "type": "issue",
            "number": 20,
            "title": "Roadmap update",
            "labels": [{"name": "state:ready-for-roadmap-update"}],
        }
        launch_brief_path = "launch-brief.md"

        with patch.object(handler, "TARGET_REPO_PATH", "/repo"):
            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "LOCK_LABEL", "state:locked"):
                    with patch.object(handler, "utc_timestamp_now", return_value="2026-06-10T07:54:00Z"):
                        with patch.object(handler, "write_run_result"):
                            with patch.object(handler, "update_run_status"):
                                advanced = handler.launch_agent(
                                    item,
                                    "state:ready-for-roadmap-update",
                                    {"agent": "codex", "mode": "roadmap-updater", "model": "gpt-5.5", "effort": "High"},
                                    "roles/roadmap-updater.md",
                                    launch_brief_path
                                )

        self.assertTrue(advanced)
        mock_validate.assert_called_once_with(item)
        mock_advance.assert_called_once_with(item, from_state_label="state:ready-for-roadmap-update")

    @patch("Handler.handler.advance_roadmap_update_workflow_on_success")
    @patch("Handler.handler.validate_roadmap_updater_open_pull_request")
    @patch("Handler.handler.subprocess.run")
    def test_roadmap_updater_success_path_blocks_transition_when_pr_validation_fails(
        self, mock_subprocess, mock_validate, mock_advance
    ):
        mock_subprocess.return_value = MagicMock(returncode=0)
        mock_validate.return_value = False

        item = {
            "type": "issue",
            "number": 20,
            "title": "Roadmap update",
            "labels": [{"name": "state:ready-for-roadmap-update"}],
        }

        with patch.object(handler, "TARGET_REPO_PATH", "/repo"):
            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "LOCK_LABEL", "state:locked"):
                    with patch.object(handler, "utc_timestamp_now", return_value="2026-06-10T07:54:00Z"):
                        with patch.object(handler, "write_run_result"):
                            with patch.object(handler, "update_run_status") as mock_update_status:
                                advanced = handler.launch_agent(
                                    item,
                                    "state:ready-for-roadmap-update",
                                    {"agent": "codex", "mode": "roadmap-updater", "model": "gpt-5.5", "effort": "High"},
                                    "roles/roadmap-updater.md",
                                    "launch-brief.md"
                                )

        self.assertFalse(advanced)
        mock_advance.assert_not_called()
        self.assertEqual(
            mock_update_status.call_args.kwargs["stop_reason"],
            "roadmap updater PR validation failed",
        )

    def test_validate_roadmap_updater_open_pull_request_requires_working_branch(self):
        item = {
            "type": "issue",
            "number": 25,
            "title": "Roadmap update",
        }

        with patch.object(handler, "LOCK_LABEL", "state:agent-in-progress"):
            with patch.object(handler, "add_comment") as mock_add_comment:
                validated = handler.validate_roadmap_updater_open_pull_request(item)

        self.assertFalse(validated)
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("no working branch was recorded", item["comment"])

    def test_validate_roadmap_updater_open_pull_request_comments_when_pr_missing(self):
        item = {
            "type": "issue",
            "number": 25,
            "title": "Roadmap update",
            "working_branch": "circus/issue-25-roadmap-update",
        }

        with patch.object(handler, "LOCK_LABEL", "state:agent-in-progress"):
            with patch.object(handler, "find_existing_open_pr_for_branch", return_value={"ok": True, "url": None}):
                with patch.object(handler, "add_comment") as mock_add_comment:
                    validated = handler.validate_roadmap_updater_open_pull_request(item)

        self.assertFalse(validated)
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("no open pull request was found", item["comment"])

    def test_validate_roadmap_updater_open_pull_request_succeeds_with_open_pr(self):
        item = {
            "type": "issue",
            "number": 25,
            "title": "Roadmap update",
            "working_branch": "circus/issue-25-roadmap-update",
        }

        with patch.object(
            handler,
            "find_existing_open_pr_for_branch",
            return_value={"ok": True, "url": "https://github.com/owner/repo/pull/24"},
        ):
            with patch.object(handler, "add_comment") as mock_add_comment:
                validated = handler.validate_roadmap_updater_open_pull_request(item)

        self.assertTrue(validated)
        self.assertEqual(item["roadmap_pr"], "https://github.com/owner/repo/pull/24")
        mock_add_comment.assert_not_called()
        
    def test_build_roadmap_updater_pr_title_uses_specific_title_for_issue_20(self):
        item_20 = {"number": 20}
        item_other = {"number": 21, "title": "Other task"}
        
        title_20 = handler.build_roadmap_updater_pr_title(item_20)
        title_other = handler.build_roadmap_updater_pr_title(item_other)
        
        self.assertEqual(title_20, "Issue #20: Add Roadmap Updater workflow for approved strategic recommendations")
        self.assertEqual(title_other, "Issue #21: Other task")

    def test_advance_roadmap_update_workflow_on_success_transitions_labels(self):
        item = {
            "type": "issue",
            "number": 20,
            "title": "Roadmap update complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                with patch("builtins.print") as mock_print:
                    transitioned = handler.advance_roadmap_update_workflow_on_success(item)

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call(
                    'gh issue edit 20 --repo owner/repo --remove-label "state:agent-in-progress"'
                ),
                unittest.mock.call(
                    'gh issue edit 20 --repo owner/repo --remove-label "state:ready-for-roadmap-update"'
                ),
                unittest.mock.call(
                    'gh issue edit 20 --repo owner/repo --add-label "state:ready-for-review"'
                ),
            ],
        )

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Roadmap Updater workflow completed successfully for issue #20." in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:agent-in-progress" in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:ready-for-roadmap-update" in line for line in printed_lines))
        self.assertTrue(any("Adding label: state:ready-for-review" in line for line in printed_lines))
        self.assertTrue(any("Documentation update complete; workflow advanced to review stage for issue #20." in line for line in printed_lines))

    def test_advance_developer_workflow_on_success_transitions_labels(self):
        item = {
            "type": "issue",
            "number": 4,
            "title": "Development complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                with patch("builtins.print") as mock_print:
                    transitioned = handler.advance_developer_workflow_on_success(item)

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call(
                    'gh issue edit 4 --repo owner/repo --remove-label "state:agent-in-progress"'
                ),
                unittest.mock.call(
                    'gh issue edit 4 --repo owner/repo --remove-label "state:ready-for-dev"'
                ),
                unittest.mock.call(
                    'gh issue edit 4 --repo owner/repo --add-label "state:ready-for-review"'
                ),
            ],
        )

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Developer workflow completed successfully for issue #4." in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:agent-in-progress" in line for line in printed_lines))
        self.assertTrue(any("Removing label: state:ready-for-dev" in line for line in printed_lines))
        self.assertTrue(any("Adding label: state:ready-for-review" in line for line in printed_lines))
        self.assertTrue(any("Workflow advanced to review stage for issue #4." in line for line in printed_lines))

    def test_advance_developer_workflow_on_success_from_changes_requested_transitions_labels(self):
        item = {
            "type": "issue",
            "number": 40,
            "title": "Developer follow-up complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                transitioned = handler.advance_developer_workflow_on_success(
                    item,
                    from_state_label="state:changes-requested",
                )

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call(
                    'gh issue edit 40 --repo owner/repo --remove-label "state:agent-in-progress"'
                ),
                unittest.mock.call(
                    'gh issue edit 40 --repo owner/repo --remove-label "state:changes-requested"'
                ),
                unittest.mock.call(
                    'gh issue edit 40 --repo owner/repo --add-label "state:ready-for-review"'
                ),
            ],
        )

    def test_advance_reviewer_workflow_on_approved_transitions_to_architect_review(self):
        item = {
            "type": "issue",
            "number": 11,
            "title": "Review complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                with patch("builtins.print") as mock_print:
                    transitioned = handler.advance_reviewer_workflow_on_approved(item)

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call(
                    'gh issue edit 11 --repo owner/repo --remove-label "state:agent-in-progress"'
                ),
                unittest.mock.call(
                    'gh issue edit 11 --repo owner/repo --remove-label "state:ready-for-review"'
                ),
                unittest.mock.call(
                    'gh issue edit 11 --repo owner/repo --add-label "state:ready-for-architect-review"'
                ),
            ],
        )

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Implementation review passed" in line for line in printed_lines))
        self.assertFalse(any("state:ready-for-human-review" in line for line in printed_lines))

    def test_advance_architect_review_workflow_on_approved_transitions_to_human_review(self):
        item = {
            "type": "issue",
            "number": 18,
            "title": "Architect review complete",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                transitioned = handler.advance_architect_review_workflow_on_approved(item)

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call('gh issue edit 18 --repo owner/repo --remove-label "state:agent-in-progress"'),
                unittest.mock.call(
                    'gh issue edit 18 --repo owner/repo --remove-label "state:ready-for-architect-review"'
                ),
                unittest.mock.call('gh issue edit 18 --repo owner/repo --add-label "state:ready-for-human-review"'),
            ],
        )

    def test_advance_architect_review_workflow_on_changes_requested_transitions_to_changes_requested(self):
        item = {
            "type": "issue",
            "number": 18,
            "title": "Architect review follow-up",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="") as mock_run_command:
                transitioned = handler.advance_architect_review_workflow_on_changes_requested(item)

        self.assertTrue(transitioned)
        self.assertEqual(
            mock_run_command.call_args_list,
            [
                unittest.mock.call('gh issue edit 18 --repo owner/repo --remove-label "state:agent-in-progress"'),
                unittest.mock.call(
                    'gh issue edit 18 --repo owner/repo --remove-label "state:ready-for-architect-review"'
                ),
                unittest.mock.call('gh issue edit 18 --repo owner/repo --add-label "state:changes-requested"'),
            ],
        )

    def test_append_reviewer_feedback_note_does_not_overwrite_architecture_handoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            item_run_root = os.path.join(temp_dir, "issue-11")
            shared_paths = handler.ensure_shared_artifacts(item_run_root)
            architecture_handoff_path = shared_paths["architecture_handoff"]
            running_notes_path = shared_paths["running_notes"]

            original_handoff_contents = "# Architecture Handoff\n\nKeep this guidance.\n"
            with open(architecture_handoff_path, "w", encoding="utf-8") as architecture_handoff_file:
                architecture_handoff_file.write(original_handoff_contents)

            review_result_path = os.path.join(item_run_root, "run-002-reviewer", "review-result.md")
            appended_path = handler.append_reviewer_feedback_note(
                item_run_root,
                review_result_path,
                review_pr_url="https://github.com/owner/repo/pull/101",
            )

            with open(architecture_handoff_path, "r", encoding="utf-8") as architecture_handoff_file:
                current_handoff_contents = architecture_handoff_file.read()

            with open(running_notes_path, "r", encoding="utf-8") as running_notes_file:
                running_notes_contents = running_notes_file.read()

        self.assertEqual(appended_path, running_notes_path)
        self.assertEqual(current_handoff_contents, original_handoff_contents)
        self.assertIn("latest review result", running_notes_contents)
        self.assertIn(handler.normalize_path_for_display(review_result_path), running_notes_contents)
        self.assertIn("https://github.com/owner/repo/pull/101", running_notes_contents)

    def test_append_architect_review_feedback_note_does_not_overwrite_architecture_handoff(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            item_run_root = os.path.join(temp_dir, "issue-19")
            shared_paths = handler.ensure_shared_artifacts(item_run_root)
            architecture_handoff_path = shared_paths["architecture_handoff"]
            running_notes_path = shared_paths["running_notes"]

            original_handoff_contents = "# Architecture Handoff\n\nKeep this guidance.\n"
            with open(architecture_handoff_path, "w", encoding="utf-8") as architecture_handoff_file:
                architecture_handoff_file.write(original_handoff_contents)

            architect_review_result_path = os.path.join(
                item_run_root,
                "run-003-architect-review",
                "architect-review-result.md",
            )
            appended_path = handler.append_architect_review_feedback_note(
                item_run_root,
                architect_review_result_path,
                review_pr_url="https://github.com/owner/repo/pull/201",
            )

            with open(architecture_handoff_path, "r", encoding="utf-8") as architecture_handoff_file:
                current_handoff_contents = architecture_handoff_file.read()

            with open(running_notes_path, "r", encoding="utf-8") as running_notes_file:
                running_notes_contents = running_notes_file.read()

        self.assertEqual(appended_path, running_notes_path)
        self.assertEqual(current_handoff_contents, original_handoff_contents)
        self.assertIn("latest architect review result", running_notes_contents)
        self.assertIn(handler.normalize_path_for_display(architect_review_result_path), running_notes_contents)
        self.assertIn("https://github.com/owner/repo/pull/201", running_notes_contents)

    def test_find_open_review_pr_for_issue_prefers_closes_marker(self):
        payload = json.dumps(
            [
                {
                    "number": 201,
                    "url": "https://github.com/owner/repo/pull/201",
                    "body": "References #9",
                },
                {
                    "number": 202,
                    "url": "https://github.com/owner/repo/pull/202",
                    "body": "Implements feature. Closes #9",
                },
            ]
        )

        with patch.object(handler, "run_command", return_value=payload):
            result = handler.find_open_review_pr_for_issue(9)

        self.assertTrue(result["ok"])
        self.assertEqual(result["match_reason"], "preferred-closes")
        self.assertEqual(result["pr"]["number"], 202)

    def test_find_open_review_pr_for_issue_returns_none_when_no_match_exists(self):
        payload = json.dumps(
            [
                {
                    "number": 301,
                    "url": "https://github.com/owner/repo/pull/301",
                    "body": "No linked issue in body.",
                }
            ]
        )

        with patch.object(handler, "run_command", return_value=payload):
            result = handler.find_open_review_pr_for_issue(14)

        self.assertTrue(result["ok"])
        self.assertIsNone(result["pr"])

    def test_parse_review_result_outcome_accepts_exact_first_non_empty_line_marker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_result_path = os.path.join(temp_dir, "review-result.md")
            with open(review_result_path, "w", encoding="utf-8") as artifact:
                artifact.write("\n\nOutcome: CHANGES_REQUESTED\nAdditional reviewer notes.\n")

            outcome = handler.parse_review_result_outcome(review_result_path)

        self.assertEqual(outcome, "CHANGES_REQUESTED")

    def test_parse_review_result_outcome_rejects_malformed_first_non_empty_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_result_path = os.path.join(temp_dir, "review-result.md")
            with open(review_result_path, "w", encoding="utf-8") as artifact:
                artifact.write("Outcome: APPROVED ✅\nOutcome: APPROVED\n")

            outcome = handler.parse_review_result_outcome(review_result_path)

        self.assertIsNone(outcome)

    def test_parse_review_result_outcome_rejects_missing_marker_on_first_non_empty_line(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            review_result_path = os.path.join(temp_dir, "review-result.md")
            with open(review_result_path, "w", encoding="utf-8") as artifact:
                artifact.write("Reviewer summary without deterministic marker.\nOutcome: APPROVED\n")

            outcome = handler.parse_review_result_outcome(review_result_path)

        self.assertIsNone(outcome)

    def test_parse_implementation_plan_outcome_accepts_ready_marker_in_outcome_section(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            implementation_plan_path = os.path.join(temp_dir, "implementation-plan.md")
            with open(implementation_plan_path, "w", encoding="utf-8") as artifact:
                artifact.write(
                    "## Implementation Plan\n\n"
                    "### Outcome\n"
                    "READY\n\n"
                    "### Source\n"
                    "https://github.com/owner/repo/issues/43\n"
                )

            outcome = handler.parse_implementation_plan_outcome(implementation_plan_path)

        self.assertEqual(outcome, "READY")

    def test_parse_implementation_plan_outcome_accepts_all_supported_exact_outcomes(self):
        for expected_outcome in ("READY", "BLOCKED", "ESCALATION_REQUIRED"):
            with self.subTest(expected_outcome=expected_outcome):
                with tempfile.TemporaryDirectory() as temp_dir:
                    implementation_plan_path = os.path.join(temp_dir, "implementation-plan.md")
                    with open(implementation_plan_path, "w", encoding="utf-8") as artifact:
                        artifact.write(
                            "## Implementation Plan\n\n"
                            "### Outcome\n"
                            f"{expected_outcome}\n\n"
                            "### Source\n"
                            "https://github.com/owner/repo/issues/43\n"
                        )

                    outcome = handler.parse_implementation_plan_outcome(implementation_plan_path)

                self.assertEqual(outcome, expected_outcome)

    def test_parse_implementation_plan_outcome_rejects_missing_outcome_heading(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            implementation_plan_path = os.path.join(temp_dir, "implementation-plan.md")
            with open(implementation_plan_path, "w", encoding="utf-8") as artifact:
                artifact.write("## Implementation Plan\n\n### Source\nno outcome heading\n")

            outcome = handler.parse_implementation_plan_outcome(implementation_plan_path)

        self.assertIsNone(outcome)

    def test_parse_implementation_plan_outcome_rejects_conflicting_outcome_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            implementation_plan_path = os.path.join(temp_dir, "implementation-plan.md")
            with open(implementation_plan_path, "w", encoding="utf-8") as artifact:
                artifact.write(
                    "## Implementation Plan\n\n"
                    "### Outcome\n"
                    "READY\n\n"
                    "### Source\n"
                    "traceability\n\n"
                    "### Outcome\n"
                    "BLOCKED\n"
                )

            outcome = handler.parse_implementation_plan_outcome(implementation_plan_path)

        self.assertIsNone(outcome)

    def test_parse_implementation_plan_outcome_rejects_malformed_outcome_variants(self):
        malformed_outcome_lines = [
            "Outcome: READY",
            "`READY`",
            "READY.",
            "ready",
        ]

        for malformed_line in malformed_outcome_lines:
            with self.subTest(malformed_line=malformed_line):
                with tempfile.TemporaryDirectory() as temp_dir:
                    implementation_plan_path = os.path.join(temp_dir, "implementation-plan.md")
                    with open(implementation_plan_path, "w", encoding="utf-8") as artifact:
                        artifact.write(
                            "## Implementation Plan\n\n"
                            "### Outcome\n"
                            f"{malformed_line}\n\n"
                            "### Source\n"
                            "https://github.com/owner/repo/issues/43\n"
                        )

                    outcome = handler.parse_implementation_plan_outcome(implementation_plan_path)

                self.assertIsNone(outcome)

    def test_parse_planner_result_v1_returns_generated_issues_with_next_state(self):
        body = (
            "Implementation plan ready for approval.\n\n"
            "```yaml\n"
            "planner_result_v1:\n"
            "  outcome: READY\n"
            "  parent_issue: 143\n"
            "  recommendation_comment_id: 50001\n"
            "  roadmap_pr: 90\n"
            "  generated_issues:\n"
            "    - number: 201\n"
            "      initial_state: state:planned\n"
            "      next_state_after_approval: state:ready-for-dev\n"
            "    - number: 202\n"
            "      initial_state: state:planned\n"
            "      next_state_after_approval: state:ready-for-architecture\n"
            "```\n"
        )

        planner_result = handler.parse_planner_result_v1(body)

        self.assertEqual(
            planner_result,
            {
                "outcome": "READY",
                "parent_issue": 143,
                "recommendation_comment_id": 50001,
                "roadmap_pr": 90,
                "generated_issues": [
                    {
                        "issue_number": 201,
                        "initial_state": "state:planned",
                        "next_state_after_approval": "state:ready-for-dev",
                    },
                    {
                        "issue_number": 202,
                        "initial_state": "state:planned",
                        "next_state_after_approval": "state:ready-for-architecture",
                    },
                ],
            },
        )

    def test_parse_planner_result_v1_rejects_missing_generated_issues(self):
        body = "```yaml\nplanner_result_v1:\n  outcome: READY\n```"

        planner_result = handler.parse_planner_result_v1(body)

        self.assertIsNone(planner_result)

    def test_approve_implementation_plan_review_transitions_source_and_generated_issues(self):
        source_issue_number = 143
        planner_comment_id = 9001
        recommendation_comment_id = 4001
        roadmap_pr_number = 88
        plan_body = (
            "```yaml\n"
            "planner_result_v1:\n"
            "  outcome: READY\n"
            "  parent_issue: 143\n"
            "  recommendation_comment_id: 4001\n"
            "  roadmap_pr: 88\n"
            "  generated_issues:\n"
            "    - number: 201\n"
            "      initial_state: state:planned\n"
            "      next_state_after_approval: state:ready-for-dev\n"
            "    - number: 202\n"
            "      initial_state: state:planned\n"
            "      next_state_after_approval: state:ready-for-architecture\n"
            "```"
        )
        source_item = {
            "type": "issue",
            "number": source_issue_number,
            "title": "Implementation planning complete",
            "state": "OPEN",
            "closed": False,
            "locked": False,
            "labels": [
                {"name": "state:ready-for-implementation-plan-review"},
                {"name": "status:triage"},
            ],
            "comments": [
                {"id": recommendation_comment_id, "body": "Recommendation details"},
                {
                    "id": planner_comment_id,
                    "body": plan_body,
                }
            ],
        }
        roadmap_pr_item = {
            "number": roadmap_pr_number,
            "state": "MERGED",
            "mergedAt": "2026-06-23T10:11:12Z",
            "title": "Roadmap update",
            "url": "https://github.com/owner/repo/pull/88",
        }
        generated_issue_201 = {
            "type": "issue",
            "number": 201,
            "title": "Generated issue A",
            "state": "OPEN",
            "closed": False,
            "locked": False,
            "labels": [{"name": "state:planned"}],
            "body": "Parent #143\nRecommendation 4001\nRoadmap #88\nNext state: state:ready-for-dev",
        }
        generated_issue_202 = {
            "type": "issue",
            "number": 202,
            "title": "Generated issue B",
            "state": "OPEN",
            "closed": False,
            "locked": False,
            "labels": [{"name": "state:planned"}],
            "body": "Parent #143\nRecommendation 4001\nRoadmap #88\nNext state: state:ready-for-architecture",
        }
        generated_issue_201_after = {
            "type": "issue",
            "number": 201,
            "state": "OPEN",
            "closed": False,
            "locked": False,
            "labels": [{"name": "state:ready-for-dev"}],
        }
        generated_issue_202_after = {
            "type": "issue",
            "number": 202,
            "state": "OPEN",
            "closed": False,
            "locked": False,
            "labels": [{"name": "state:ready-for-architecture"}],
        }
        source_item_after = {
            "type": "issue",
            "number": source_issue_number,
            "state": "OPEN",
            "closed": False,
            "locked": False,
            "labels": [{"name": "state:ready-for-human-review"}],
        }

        with patch.object(handler.github_client, "get_item") as mock_get_item:
            mock_get_item.side_effect = [
                (source_item, True),
                (roadmap_pr_item, True),
                (generated_issue_201, True),
                (generated_issue_202, True),
                (generated_issue_201_after, True),
                (generated_issue_202_after, True),
                (source_item_after, True),
            ]
            with patch.object(handler.github_client, "replace_label", return_value=True) as mock_replace_label:
                with patch.object(handler, "add_comment") as mock_add_comment:
                    approved = handler.approve_implementation_plan_review(
                        source_issue_number,
                        plan_comment_id=planner_comment_id,
                    )

        self.assertTrue(approved)
        self.assertEqual(mock_get_item.call_count, 7)
        mock_replace_label.assert_has_calls(
            [
                unittest.mock.call(
                    generated_issue_201,
                    remove_label_value="state:planned",
                    add_label_value="state:ready-for-dev",
                    repo=unittest.mock.ANY,
                    run_command_fn=unittest.mock.ANY,
                ),
                unittest.mock.call(
                    generated_issue_202,
                    remove_label_value="state:planned",
                    add_label_value="state:ready-for-architecture",
                    repo=unittest.mock.ANY,
                    run_command_fn=unittest.mock.ANY,
                ),
                unittest.mock.call(
                    source_item,
                    remove_label_value="state:ready-for-implementation-plan-review",
                    add_label_value="state:ready-for-human-review",
                    repo=unittest.mock.ANY,
                    run_command_fn=unittest.mock.ANY,
                ),
            ]
        )
        mock_add_comment.assert_called_once()
        for call in mock_get_item.call_args_list:
            self.assertNotIn("locked", call.kwargs.get("fields", ""))

    def test_approve_implementation_plan_review_reports_partial_transition_on_failure(self):
        source_item = {
            "type": "issue",
            "number": 143,
            "title": "Implementation planning complete",
            "state": "OPEN",
            "closed": False,
            "labels": [{"name": "state:ready-for-implementation-plan-review"}],
            "comments": [
                {"id": 4001, "body": "Recommendation details"},
                {
                    "id": 9001,
                    "body": (
                        "```yaml\n"
                        "planner_result_v1:\n"
                        "  outcome: READY\n"
                        "  parent_issue: 143\n"
                        "  recommendation_comment_id: 4001\n"
                        "  roadmap_pr: 88\n"
                        "  generated_issues:\n"
                        "    - number: 201\n"
                        "      initial_state: state:planned\n"
                        "      next_state_after_approval: state:ready-for-dev\n"
                        "    - number: 202\n"
                        "      initial_state: state:planned\n"
                        "      next_state_after_approval: state:ready-for-architecture\n"
                        "```"
                    ),
                },
            ],
        }
        roadmap_pr_item = {
            "number": 88,
            "state": "MERGED",
            "mergedAt": "2026-06-23T10:11:12Z",
            "title": "Roadmap update",
            "url": "https://github.com/owner/repo/pull/88",
        }
        generated_issue_201 = {
            "type": "issue",
            "number": 201,
            "title": "Generated issue A",
            "state": "OPEN",
            "closed": False,
            "labels": [{"name": "state:planned"}],
            "body": "Parent #143\nRecommendation 4001\nRoadmap #88\nNext state: state:ready-for-dev",
        }
        generated_issue_202 = {
            "type": "issue",
            "number": 202,
            "title": "Generated issue B",
            "state": "OPEN",
            "closed": False,
            "labels": [{"name": "state:planned"}],
            "body": "Parent #143\nRecommendation 4001\nRoadmap #88\nNext state: state:ready-for-architecture",
        }
        generated_issue_201_after = {
            "type": "issue",
            "number": 201,
            "state": "OPEN",
            "closed": False,
            "labels": [{"name": "state:ready-for-dev"}],
        }

        with patch.object(handler.github_client, "get_item") as mock_get_item:
            mock_get_item.side_effect = [
                (source_item, True),
                (roadmap_pr_item, True),
                (generated_issue_201, True),
                (generated_issue_202, True),
                (generated_issue_201_after, True),
            ]
            with patch.object(handler.github_client, "replace_label", side_effect=[True, False]) as mock_replace_label:
                with patch.object(handler, "add_comment", return_value=True) as mock_add_comment:
                    approved = handler.approve_implementation_plan_review(143, plan_comment_id=9001)

        self.assertFalse(approved)
        self.assertEqual(mock_replace_label.call_count, 2)
        self.assertEqual(mock_add_comment.call_count, 1)
        self.assertIn("approval failed", mock_add_comment.call_args.args[0]["comment"].lower())
        self.assertIn("#201", mock_add_comment.call_args.args[0]["comment"])

    def test_approve_implementation_plan_review_dry_run_skips_mutations(self):
        source_item = {
            "type": "issue",
            "number": 143,
            "title": "Implementation planning complete",
            "state": "OPEN",
            "closed": False,
            "locked": False,
            "labels": [{"name": "state:ready-for-implementation-plan-review"}],
            "comments": [
                {"id": 4001, "body": "Recommendation details"},
                {
                    "id": 9001,
                    "body": (
                        "```yaml\n"
                        "planner_result_v1:\n"
                        "  outcome: READY\n"
                        "  parent_issue: 143\n"
                        "  recommendation_comment_id: 4001\n"
                        "  roadmap_pr: 88\n"
                        "  generated_issues:\n"
                        "    - number: 201\n"
                        "      initial_state: state:planned\n"
                        "      next_state_after_approval: state:ready-for-dev\n"
                        "```"
                    ),
                },
            ],
        }
        roadmap_pr_item = {
            "number": 88,
            "state": "MERGED",
            "mergedAt": "2026-06-23T10:11:12Z",
            "title": "Roadmap update",
            "url": "https://github.com/owner/repo/pull/88",
        }
        generated_issue_201 = {
            "type": "issue",
            "number": 201,
            "title": "Generated issue A",
            "state": "OPEN",
            "closed": False,
            "locked": False,
            "labels": [{"name": "state:planned"}],
            "body": "Parent #143\nRecommendation 4001\nRoadmap #88\nNext state: state:ready-for-dev",
        }

        with patch.object(handler.github_client, "get_item") as mock_get_item:
            mock_get_item.side_effect = [
                (source_item, True),
                (roadmap_pr_item, True),
                (generated_issue_201, True),
            ]
            with patch.object(handler.github_client, "replace_label") as mock_replace_label:
                with patch.object(handler, "add_comment") as mock_add_comment:
                    approved = handler.approve_implementation_plan_review(143, plan_comment_id=9001, dry_run=True)

        self.assertTrue(approved)
        mock_replace_label.assert_not_called()
        mock_add_comment.assert_not_called()

    def test_approve_implementation_plan_review_rejects_missing_review_state_label(self):
        source_item = {
            "type": "issue",
            "number": 143,
            "title": "Implementation planning complete",
            "labels": [{"name": "state:ready-for-dev"}],
            "comments": [],
        }

        with patch.object(handler.github_client, "get_item", return_value=(source_item, True)):
            approved = handler.approve_implementation_plan_review(143)

        self.assertFalse(approved)

    def test_launch_agent_codex_reviewer_runs_codex_exec_with_pr_url_and_context(self):
        item = {
            "type": "issue",
            "number": 9,
            "title": "Review changes",
            "url": "https://github.com/owner/repo/issues/9",
            "review_pr": {
                "number": 77,
                "url": "https://github.com/owner/repo/pull/77",
            },
        }
        config = {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-9/run-001-reviewer/launch-brief.md"
        review_result_path = "Watchtower/runs/issue-9/run-001-reviewer/review-result.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-9/run-001-reviewer/launch-brief.md"

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                    with patch.object(handler, "build_reviewer_result_path", return_value=review_result_path):
                        with patch.object(handler.os.path, "exists", return_value=True):
                            with patch.object(handler, "parse_review_result_outcome", return_value="APPROVED"):
                                with patch.object(handler, "advance_reviewer_workflow_on_approved", return_value=True) as mock_transition:
                                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                                        launched = handler.launch_agent(
                                            item,
                                            "state:ready-for-review",
                                            config,
                                            os.path.normpath(os.path.join("TheFarm", "roles", "reviewer.md")),
                                            launch_brief_path,
                                        )

        self.assertTrue(launched)
        mock_subprocess_run.assert_called_once()
        args, kwargs = mock_subprocess_run.call_args
        command = args[0]
        self.assertEqual(command[0], "codex")
        self.assertEqual(command[1], "exec")
        self.assertEqual(command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", command[-1])
        self.assertIn("execute the reviewer workflow", command[-1])
        self.assertIn("Review the linked pull request at https://github.com/owner/repo/pull/77", command[-1])
        self.assertIn(f"Write review-result.md to this exact absolute path: {review_result_path}", command[-1])
        self.assertIn("Leave a review comment on the pull request", command[-1])
        self.assertIn("Do not modify workflow labels directly", command[-1])
        self.assertIn("Do not auto-merge", command[-1])
        self.assertEqual(kwargs["cwd"], "C:/target/repo")
        self.assertEqual(kwargs["env"]["CIRCUS_REVIEW_PR_URL"], "https://github.com/owner/repo/pull/77")
        self.assertEqual(kwargs["env"]["CIRCUS_REVIEW_ISSUE_NUMBER"], "9")
        self.assertEqual(kwargs["env"]["CIRCUS_REVIEW_LAUNCH_BRIEF"], absolute_launch_brief_path)
        self.assertEqual(kwargs["env"]["CIRCUS_REVIEW_RESULT_PATH"], review_result_path)
        mock_transition.assert_called_once_with(item)

    def test_launch_agent_codex_architect_review_runs_codex_exec_with_pr_url_and_context(self):
        item = {
            "type": "issue",
            "number": 12,
            "title": "Architect review changes",
            "url": "https://github.com/owner/repo/issues/12",
            "review_pr": {
                "number": 88,
                "url": "https://github.com/owner/repo/pull/88",
            },
        }
        config = {
            "agent": "codex",
            "mode": "architect-review",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        launch_brief_path = "Watchtower/runs/issue-12/run-001-architect-review/launch-brief.md"
        review_result_path = "Watchtower/runs/issue-12/run-001-reviewer/review-result.md"
        architect_review_result_path = "Watchtower/runs/issue-12/run-001-architect-review/architect-review-result.md"
        absolute_launch_brief_path = "C:/abs/Watchtower/runs/issue-12/run-001-architect-review/launch-brief.md"

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                    with patch.object(handler, "build_reviewer_result_path", return_value=review_result_path):
                        with patch.object(
                            handler,
                            "build_architect_review_result_path",
                            return_value=architect_review_result_path,
                        ):
                            with patch.object(handler.os.path, "exists", return_value=True):
                                with patch.object(handler, "parse_architect_review_result_outcome", return_value="APPROVED"):
                                    with patch.object(
                                        handler,
                                        "advance_architect_review_workflow_on_approved",
                                        return_value=True,
                                    ) as mock_transition:
                                        with patch.object(
                                            handler.subprocess,
                                            "run",
                                            return_value=Mock(returncode=0),
                                        ) as mock_subprocess_run:
                                            launched = handler.launch_agent(
                                                item,
                                                "state:ready-for-architect-review",
                                                config,
                                                os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                                                launch_brief_path,
                                            )

        self.assertTrue(launched)
        mock_subprocess_run.assert_called_once()
        args, kwargs = mock_subprocess_run.call_args
        command = args[0]
        self.assertEqual(command[0], "codex")
        self.assertEqual(command[1], "exec")
        self.assertEqual(command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", command[-1])
        self.assertIn("execute the architect review workflow", command[-1])
        self.assertIn("Review the linked pull request at https://github.com/owner/repo/pull/88", command[-1])
        self.assertIn(
            f"Write architect-review-result.md to this exact absolute path: {architect_review_result_path}",
            command[-1],
        )
        self.assertEqual(kwargs["cwd"], "C:/target/repo")
        self.assertEqual(
            kwargs["env"]["CIRCUS_ARCHITECT_REVIEW_PR_URL"],
            "https://github.com/owner/repo/pull/88",
        )
        self.assertEqual(kwargs["env"]["CIRCUS_ARCHITECT_REVIEW_ISSUE_NUMBER"], "12")
        self.assertEqual(kwargs["env"]["CIRCUS_ARCHITECT_REVIEW_LAUNCH_BRIEF"], absolute_launch_brief_path)
        self.assertEqual(
            kwargs["env"]["CIRCUS_ARCHITECT_REVIEW_RESULT_PATH"],
            architect_review_result_path,
        )
        mock_transition.assert_called_once_with(item)

    def test_launch_agent_codex_architect_review_changes_requested_routes_to_changes_requested_transition(self):
        item = {
            "type": "issue",
            "number": 13,
            "title": "Architect review follow-up",
            "url": "https://github.com/owner/repo/issues/13",
            "review_pr": {
                "number": 89,
                "url": "https://github.com/owner/repo/pull/89",
            },
        }
        config = {
            "agent": "codex",
            "mode": "architect-review",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value="C:/abs/architect-review-launch-brief.md"):
                    with patch.object(
                        handler,
                        "build_reviewer_result_path",
                        return_value="Watchtower/runs/issue-13/run-001-reviewer/review-result.md",
                    ):
                        with patch.object(
                            handler,
                            "build_architect_review_result_path",
                            return_value="Watchtower/runs/issue-13/run-001-architect-review/architect-review-result.md",
                        ):
                            with patch.object(handler.os.path, "exists", return_value=True):
                                with patch.object(handler, "parse_architect_review_result_outcome", return_value="CHANGES_REQUESTED"):
                                    with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                                        with patch.object(
                                            handler,
                                            "append_architect_review_feedback_note",
                                            return_value="Watchtower/runs/issue-13/shared/running-notes.md",
                                        ) as mock_append_feedback:
                                            with patch.object(
                                                handler,
                                                "advance_architect_review_workflow_on_changes_requested",
                                                return_value=True,
                                            ) as mock_transition:
                                                launched = handler.launch_agent(
                                                    item,
                                                    "state:ready-for-architect-review",
                                                    config,
                                                    os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                                                    "Watchtower/runs/issue-13/run-001-architect-review/launch-brief.md",
                                                )

        self.assertTrue(launched)
        mock_append_feedback.assert_called_once()
        mock_transition.assert_called_once_with(item)

    def test_launch_agent_codex_architect_review_missing_result_artifact_does_not_transition(self):
        item = {
            "type": "issue",
            "number": 14,
            "title": "Architect review missing artifact",
            "url": "https://github.com/owner/repo/issues/14",
            "review_pr": {
                "number": 90,
                "url": "https://github.com/owner/repo/pull/90",
            },
        }
        config = {
            "agent": "codex",
            "mode": "architect-review",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler.os.path, "abspath", return_value="C:/abs/architect-review-launch-brief.md"):
                    with patch.object(
                        handler,
                        "build_reviewer_result_path",
                        return_value="Watchtower/runs/issue-14/run-001-reviewer/review-result.md",
                    ):
                        with patch.object(
                            handler,
                            "build_architect_review_result_path",
                            return_value="Watchtower/runs/issue-14/run-001-architect-review/architect-review-result.md",
                        ):
                            with patch.object(handler.os.path, "exists", return_value=False):
                                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                                    with patch.object(handler, "add_comment") as mock_add_comment:
                                        with patch.object(
                                            handler,
                                            "advance_architect_review_workflow_on_approved",
                                        ) as mock_transition:
                                            launched = handler.launch_agent(
                                                item,
                                                "state:ready-for-architect-review",
                                                config,
                                                os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                                                "Watchtower/runs/issue-14/run-001-architect-review/launch-brief.md",
                                            )

        self.assertFalse(launched)
        self.assertTrue(item.get("missing_review_result_artifact"))
        mock_add_comment.assert_called_once()
        mock_transition.assert_not_called()

    def test_launch_agent_codex_reviewer_adds_sandbox_bypass_flag_when_enabled(self):
        item = {
            "type": "issue",
            "number": 9,
            "title": "Review changes",
            "url": "https://github.com/owner/repo/issues/9",
            "review_pr": {
                "number": 77,
                "url": "https://github.com/owner/repo/pull/77",
            },
        }
        config = {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.dict(os.environ, {"CIRCUS_CODEX_BYPASS_SANDBOX": "true"}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler, "build_reviewer_result_path", return_value="Watchtower/runs/issue-9/run-001-reviewer/review-result.md"):
                    with patch.object(handler.os.path, "exists", return_value=True):
                        with patch.object(handler, "parse_review_result_outcome", return_value="APPROVED"):
                            with patch.object(handler, "advance_reviewer_workflow_on_approved", return_value=True):
                                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
                                    with patch("builtins.print") as mock_print:
                                        launched = handler.launch_agent(
                                            item,
                                            "state:ready-for-review",
                                            config,
                                            os.path.normpath(os.path.join("TheFarm", "roles", "reviewer.md")),
                                            "Watchtower/runs/issue-9/run-001-reviewer/launch-brief.md",
                                        )

        self.assertTrue(launched)
        command = mock_subprocess_run.call_args.args[0]
        self.assertEqual(command[0], "codex")
        self.assertEqual(command[1], "exec")
        self.assertEqual(command[2:4], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[4:6], ["--cd", "C:/target/repo"])
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertIn("Review the linked pull request at https://github.com/owner/repo/pull/77", command[-1])

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("WARNING: Codex sandbox bypass ENABLED" in line for line in printed_lines))

    def test_launch_agent_codex_reviewer_ambiguous_output_does_not_transition_labels(self):
        item = {
            "type": "issue",
            "number": 9,
            "title": "Review changes",
            "url": "https://github.com/owner/repo/issues/9",
            "review_pr": {
                "number": 77,
                "url": "https://github.com/owner/repo/pull/77",
            },
        }
        config = {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler, "build_reviewer_result_path", return_value="Watchtower/runs/issue-9/run-001-reviewer/review-result.md"):
                    with patch.object(handler.os.path, "exists", return_value=True):
                        with patch.object(handler, "parse_review_result_outcome", return_value=None):
                            with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                                with patch.object(handler, "advance_reviewer_workflow_on_approved") as mock_approved:
                                    with patch.object(handler, "advance_reviewer_workflow_on_changes_requested") as mock_changes:
                                        with patch.object(handler, "add_comment") as mock_add_comment:
                                            launched = handler.launch_agent(
                                                item,
                                                "state:ready-for-review",
                                                config,
                                                os.path.normpath(os.path.join("TheFarm", "roles", "reviewer.md")),
                                                "Watchtower/runs/issue-9/run-001-reviewer/launch-brief.md",
                                            )

        self.assertTrue(launched)
        mock_approved.assert_not_called()
        mock_changes.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("no unambiguous review outcome marker", item["comment"])

    def test_launch_agent_codex_reviewer_changes_requested_routes_to_changes_requested_transition(self):
        item = {
            "type": "issue",
            "number": 10,
            "title": "Review changes",
            "url": "https://github.com/owner/repo/issues/10",
            "review_pr": {
                "number": 88,
                "url": "https://github.com/owner/repo/pull/88",
            },
        }
        config = {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        review_result_path = "Watchtower/runs/issue-10/run-001-reviewer/review-result.md"

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler, "build_reviewer_result_path", return_value=review_result_path):
                    with patch.object(handler.os.path, "exists", return_value=True):
                        with patch.object(handler, "parse_review_result_outcome", return_value="CHANGES_REQUESTED"):
                            with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                                with patch.object(handler, "advance_reviewer_workflow_on_approved") as mock_approved:
                                    with patch.object(handler, "advance_reviewer_workflow_on_changes_requested", return_value=True) as mock_changes:
                                        with patch.object(handler, "append_reviewer_feedback_note", return_value="Watchtower/runs/issue-10/shared/running-notes.md") as mock_append_feedback:
                                            launched = handler.launch_agent(
                                                item,
                                                "state:ready-for-review",
                                                config,
                                                os.path.normpath(os.path.join("TheFarm", "roles", "reviewer.md")),
                                                "Watchtower/runs/issue-10/run-001-reviewer/launch-brief.md",
                                            )

        self.assertTrue(launched)
        mock_approved.assert_not_called()
        mock_changes.assert_called_once_with(item)
        mock_append_feedback.assert_called_once()
        self.assertEqual(mock_append_feedback.call_args.args[1], review_result_path)
        self.assertEqual(mock_append_feedback.call_args.args[2], "https://github.com/owner/repo/pull/88")

    def test_launch_agent_codex_reviewer_missing_review_result_artifact_does_not_transition(self):
        item = {
            "type": "issue",
            "number": 10,
            "title": "Review changes",
            "url": "https://github.com/owner/repo/issues/10",
            "review_pr": {
                "number": 88,
                "url": "https://github.com/owner/repo/pull/88",
            },
        }
        config = {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            launch_brief_path = os.path.join(temp_dir, "issue-10", "run-001-reviewer", "launch-brief.md")
            os.makedirs(os.path.dirname(launch_brief_path), exist_ok=True)
            with open(launch_brief_path, "w", encoding="utf-8") as launch_brief_file:
                launch_brief_file.write("# Launch Brief\n")

            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                    handler.initialize_run_status(item, "state:ready-for-review", config, launch_brief_path)

                    review_result_path = "C:/abs/Watchtower/runs/issue-10/run-001-reviewer/review-result.md"
                    with patch.dict(os.environ, {}, clear=True):
                        with patch.object(handler, "build_reviewer_result_path", return_value=review_result_path):
                            with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)):
                                with patch.object(handler.os.path, "exists", return_value=False):
                                    with patch.object(handler, "parse_review_result_outcome") as mock_parse_outcome:
                                        with patch.object(handler, "advance_reviewer_workflow_on_approved") as mock_approved:
                                            with patch.object(handler, "advance_reviewer_workflow_on_changes_requested") as mock_changes:
                                                with patch.object(handler, "add_comment") as mock_add_comment:
                                                    launched = handler.launch_agent(
                                                        item,
                                                        "state:ready-for-review",
                                                        config,
                                                        os.path.normpath(os.path.join("TheFarm", "roles", "reviewer.md")),
                                                        launch_brief_path,
                                                    )

            status_path = os.path.join(os.path.dirname(launch_brief_path), "status.json")
            result_path = os.path.join(os.path.dirname(launch_brief_path), "result.md")
            with open(status_path, "r", encoding="utf-8") as status_file:
                status_payload = json.load(status_file)

            self.assertEqual(status_payload["outcome"], "missing result artifact")
            self.assertFalse(status_payload["success"])
            self.assertEqual(status_payload["exit_code"], 0)
            self.assertIn("review_result", status_payload["artifacts"])
            self.assertTrue(os.path.isfile(result_path))

        self.assertFalse(launched)
        mock_parse_outcome.assert_not_called()
        mock_approved.assert_not_called()
        mock_changes.assert_not_called()
        mock_add_comment.assert_called_once_with(item)
        self.assertTrue(item.get("missing_review_result_artifact"))
        self.assertIn("was not created", item["comment"])
        self.assertIn(review_result_path, item["comment"])

    def test_junie_command_generation_is_unchanged(self):
        command = handler.build_junie_command(
            "gpt-5.3-codex",
            "Medium",
            "C:/target/repo",
            "Read launch brief",
        )

        self.assertEqual(command[0], "junie")
        self.assertEqual(command[1:3], ["--project", "C:/target/repo"])
        self.assertEqual(command[3:5], ["--model", "gpt-5.3-codex"])
        self.assertEqual(command[5:7], ["--effort", "medium"])
        self.assertEqual(command[7], "Read launch brief")

    def test_build_launch_brief_path_is_predictable(self):
        item = {"type": "issue", "number": 3}

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(handler, "LAUNCH_ARTIFACT_DIR", temp_dir):
                with patch.object(handler, "REPO", "owner/repo"):
                    path = handler.build_launch_brief_path(item, "developer")

        self.assertEqual(path, f"{temp_dir.replace('\\', '/')}/owner-repo/issue-3/run-001-developer/launch-brief.md")
        self.assertNotIn("\\", path)

    def test_build_launch_brief_path_increments_run_number_for_existing_item(self):
        item = {"type": "issue", "number": 3}

        with tempfile.TemporaryDirectory() as temp_dir:
            item_root = os.path.join(temp_dir, "owner-repo", "issue-3")
            os.makedirs(os.path.join(item_root, "run-001-developer"), exist_ok=True)
            os.makedirs(os.path.join(item_root, "run-002-reviewer"), exist_ok=True)

            with patch.object(handler, "LAUNCH_ARTIFACT_DIR", temp_dir):
                with patch.object(handler, "REPO", "owner/repo"):
                    path = handler.build_launch_brief_path(item, "developer")

        self.assertEqual(path, f"{temp_dir.replace('\\', '/')}/owner-repo/issue-3/run-003-developer/launch-brief.md")
        self.assertNotIn("\\", path)

    def test_build_launch_brief_path_isolated_by_repository_namespace(self):
        item = {"type": "issue", "number": 3}

        with tempfile.TemporaryDirectory() as temp_dir:
            owner_repo_item_root = os.path.join(temp_dir, "owner-repo", "issue-3")
            os.makedirs(os.path.join(owner_repo_item_root, "run-001-developer"), exist_ok=True)

            with patch.object(handler, "LAUNCH_ARTIFACT_DIR", temp_dir):
                with patch.object(handler, "REPO", "other/repo"):
                    path = handler.build_launch_brief_path(item, "developer")

        self.assertEqual(path, f"{temp_dir.replace('\\', '/')}/other-repo/issue-3/run-001-developer/launch-brief.md")
        self.assertNotIn("\\", path)

    def test_build_launch_brief_markdown_includes_required_sections_and_dynamic_references(self):
        item = {
            "type": "issue",
            "number": 3,
            "title": "Implement launch brief",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        normalized_circus_root = handler.normalize_path_for_display(handler.get_circus_runtime_root())
        architecture_handoff_path = f"{normalized_circus_root}/Watchtower/runs/owner-repo/issue-3/shared/architecture-handoff.md"
        running_notes_path = f"{normalized_circus_root}/Watchtower/runs/owner-repo/issue-3/shared/running-notes.md"
        decision_log_path = f"{normalized_circus_root}/Watchtower/runs/owner-repo/issue-3/shared/decision-log.md"

        with patch.object(handler, "REPO", "owner/repo"):
            markdown = handler.build_launch_brief_markdown(
                item,
                "state:ready-for-dev",
                config,
                os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                "2026-05-25T09:06:00",
                "C:\\target\\repo",
                {
                    "architecture_handoff": architecture_handoff_path,
                    "running_notes": running_notes_path,
                    "decision_log": decision_log_path,
                },
            )

        self.assertIn("## Runtime Roots", markdown)
        self.assertIn(f"- circus repo root: `{normalized_circus_root}`", markdown)
        self.assertIn("- target repo root: `C:/target/repo`", markdown)
        self.assertIn("## Assignment", markdown)
        self.assertIn("## Source of Truth", markdown)
        self.assertIn("## Operating Instructions", markdown)
        self.assertIn("## Agent Profile", markdown)
        self.assertIn("## Shared Context", markdown)
        self.assertIn("- repository: `owner/repo`", markdown)
        self.assertIn("- target repo path: `C:/target/repo`", markdown)
        self.assertIn("- item type: `issue`", markdown)
        self.assertIn("- item number: `3`", markdown)
        self.assertIn("- workflow state: `state:ready-for-dev`", markdown)
        self.assertIn("- target agent: `junie`", markdown)
        self.assertIn("- mode: `developer`", markdown)
        self.assertIn("- model: `gpt-5.3-codex`", markdown)
        self.assertIn("- effort: `Medium`", markdown)
        self.assertIn("- generated-by: `Handler`", markdown)
        self.assertIn(f"- architecture handoff: `{architecture_handoff_path}`", markdown)
        self.assertIn(f"- running notes: `{running_notes_path}`", markdown)
        self.assertIn(f"- decision log: `{decision_log_path}`", markdown)
        self.assertIn("GitHub issue/PR metadata is the source of truth", markdown)
        self.assertIn("If local files, git state, or launch metadata conflict with GitHub metadata", markdown)
        self.assertIn(f"- profile source: `{normalized_circus_root}/TheFarm/roles/developer.md`", markdown)
        self.assertNotIn("role/prompt", markdown)
        self.assertNotIn("\\", markdown)
        self.assertNotIn("docs\\doctrine.md", markdown)
        self.assertNotIn("docs\\operations-status.md", markdown)

    def test_build_launch_brief_markdown_includes_discovered_target_repository_guidance(self):
        item = {
            "type": "issue",
            "number": 21,
            "title": "Follow local project instructions",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with tempfile.TemporaryDirectory() as temp_repo:
            os.makedirs(os.path.join(temp_repo, ".circus", "roles"), exist_ok=True)
            os.makedirs(os.path.join(temp_repo, ".circus", "workflows"), exist_ok=True)
            for relative_path in [
                "AGENTS.md",
                os.path.join(".circus", "instructions.md"),
                os.path.join(".circus", "roles", "developer.md"),
                os.path.join(".circus", "workflows", "developer.md"),
            ]:
                absolute_path = os.path.join(temp_repo, relative_path)
                with open(absolute_path, "w", encoding="utf-8") as file_handle:
                    file_handle.write("# local guidance\n")

            with patch.object(handler, "REPO", "owner/repo"):
                markdown = handler.build_launch_brief_markdown(
                    item,
                    "state:ready-for-dev",
                    config,
                    os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                    "2026-05-25T10:00:00",
                    temp_repo,
                )

        normalized_repo_root = temp_repo.replace("\\", "/")
        self.assertIn("## Target Repository Guidance", markdown)
        self.assertIn(f"- `{normalized_repo_root}/AGENTS.md`", markdown)
        self.assertIn(f"- `{normalized_repo_root}/.circus/instructions.md`", markdown)
        self.assertIn(f"- `{normalized_repo_root}/.circus/roles/developer.md`", markdown)
        self.assertIn(f"- `{normalized_repo_root}/.circus/workflows/developer.md`", markdown)

    def test_build_launch_brief_markdown_omits_target_repository_guidance_section_when_absent(self):
        item = {
            "type": "issue",
            "number": 21,
            "title": "Follow local project instructions",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with tempfile.TemporaryDirectory() as temp_repo:
            with patch.object(handler, "REPO", "owner/repo"):
                markdown = handler.build_launch_brief_markdown(
                    item,
                    "state:ready-for-dev",
                    config,
                    os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                    "2026-05-25T10:00:00",
                    temp_repo,
                )

        self.assertNotIn("## Target Repository Guidance", markdown)


    def test_discover_target_instruction_paths_returns_expected_order_for_mode(self):
        with tempfile.TemporaryDirectory() as temp_repo:
            os.makedirs(os.path.join(temp_repo, ".circus", "roles"), exist_ok=True)
            os.makedirs(os.path.join(temp_repo, ".circus", "workflows"), exist_ok=True)

            for relative_path in [
                "AGENTS.md",
                os.path.join(".circus", "instructions.md"),
                os.path.join(".circus", "conventions.md"),
                os.path.join(".circus", "architecture.md"),
                os.path.join(".circus", "testing.md"),
                os.path.join(".circus", "roles", "developer.md"),
                os.path.join(".circus", "workflows", "developer.md"),
            ]:
                absolute_path = os.path.join(temp_repo, relative_path)
                with open(absolute_path, "w", encoding="utf-8") as file_handle:
                    file_handle.write("# guidance\n")

            discovered_paths = target_instructions.discover_target_instruction_paths(temp_repo, "developer")

        normalized_root = temp_repo.replace("\\", "/")
        self.assertEqual(
            discovered_paths,
            [
                f"{normalized_root}/AGENTS.md",
                f"{normalized_root}/.circus/instructions.md",
                f"{normalized_root}/.circus/conventions.md",
                f"{normalized_root}/.circus/architecture.md",
                f"{normalized_root}/.circus/testing.md",
                f"{normalized_root}/.circus/roles/developer.md",
                f"{normalized_root}/.circus/workflows/developer.md",
            ],
        )

    def test_discover_target_instruction_paths_ignores_missing_files(self):
        with tempfile.TemporaryDirectory() as temp_repo:
            os.makedirs(os.path.join(temp_repo, ".circus", "roles"), exist_ok=True)
            with open(os.path.join(temp_repo, "AGENTS.md"), "w", encoding="utf-8") as file_handle:
                file_handle.write("# guidance\n")

            discovered_paths = target_instructions.discover_target_instruction_paths(temp_repo, "developer")

        self.assertEqual(discovered_paths, [f"{temp_repo.replace('\\', '/')}/AGENTS.md"])

    def test_build_launch_brief_markdown_for_reviewer_includes_result_contract_and_absolute_path(self):
        item = {
            "type": "issue",
            "number": 15,
            "title": "Review changes",
        }
        config = {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        review_result_path = "C:/abs/Watchtower/runs/issue-15/run-001-reviewer/review-result.md"

        with patch.object(handler, "REPO", "owner/repo"):
            markdown = handler.build_launch_brief_markdown(
                item,
                "state:ready-for-review",
                config,
                os.path.normpath(os.path.join("TheFarm", "roles", "reviewer.md")),
                "2026-05-25T10:00:00",
                "C:/target/repo",
                review_result_path=review_result_path,
            )

        self.assertIn("## Reviewer Result Contract", markdown)
        self.assertIn(f"- review result artifact absolute path: `{review_result_path}`", markdown)
        self.assertIn("- You must write `review-result.md` to this exact absolute path before exiting.", markdown)
        self.assertIn("  - `Outcome: APPROVED`", markdown)
        self.assertIn("  - `Outcome: CHANGES_REQUESTED`", markdown)
        self.assertIn("  - `Outcome: BLOCKED`", markdown)

    def test_build_launch_brief_markdown_for_implementation_planner_includes_artifact_contract(self):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Draft implementation plan",
        }
        config = {
            "agent": "codex",
            "mode": "implementation-planner",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        implementation_plan_path = "C:/abs/Watchtower/runs/issue-43/run-001-implementation-planner/implementation-plan.md"

        with patch.object(handler, "REPO", "owner/repo"):
            markdown = handler.build_launch_brief_markdown(
                item,
                "state:ready-for-implementation-planning",
                config,
                os.path.normpath(os.path.join("TheFarm", "roles", "implementation-planner.md")),
                "2026-05-25T10:00:00",
                "C:/target/repo",
                implementation_plan_path=implementation_plan_path,
            )

        self.assertIn("## Implementation Planner Result Contract", markdown)
        self.assertIn(f"- implementation plan artifact absolute path: `{implementation_plan_path}`", markdown)
        self.assertIn("- You must write `implementation-plan.md` to this exact absolute path before exiting.", markdown)

    def test_build_launch_brief_markdown_includes_working_branch_when_present(self):
        item = {
            "type": "issue",
            "number": 11,
            "title": "Implement branch support",
            "working_branch": "circus/issue-11-implement-branch-support",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            markdown = handler.build_launch_brief_markdown(
                item,
                "state:ready-for-dev",
                config,
                os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                "2026-05-25T10:00:00",
                "C:/target/repo",
            )

        self.assertIn("- working branch: `circus/issue-11-implement-branch-support`", markdown)

    def test_build_launch_brief_markdown_includes_execution_branch_when_present(self):
        item = {
            "type": "issue",
            "number": 12,
            "title": "Architect branch metadata",
            "execution_branch": "main",
        }
        config = {
            "agent": "codex",
            "mode": "architect",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            markdown = handler.build_launch_brief_markdown(
                item,
                "state:ready-for-architecture",
                config,
                os.path.normpath(os.path.join("TheFarm", "roles", "architect.md")),
                "2026-05-25T10:00:00",
                "C:/target/repo",
            )

        self.assertIn("- execution branch: `main`", markdown)

    def test_build_developer_branch_name_is_deterministic_and_slugified(self):
        item = {
            "number": 2,
            "title": "Define Initial Sandbox Architecture Conventions!!!",
        }

        branch_name = handler.build_developer_branch_name(item)

        self.assertEqual(
            branch_name,
            "circus/issue-2-define-initial-sandbox-architecture-conventions",
        )

    def test_prepare_developer_branch_creates_new_worktree_when_missing(self):
        item = {"number": 7, "title": "Create branch before launch"}
        workspace_path = "C:/worktrees/repo/issue-7"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", side_effect=["main", "circus/issue-7-create-branch-before-launch"]):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "remote-head")) as mock_detect_base:
                        with patch.object(handler, "refresh_local_base_branch", return_value=True) as mock_refresh_base:
                            with patch.object(handler, "resolve_git_ref_commit", return_value="abc123") as mock_resolve_base:
                                with patch.object(handler.os.path, "exists", return_value=False):
                                    with patch.object(handler, "local_branch_exists", return_value=False) as mock_local_branch_exists:
                                        with patch.object(handler, "create_worktree_branch_from_base", return_value=True) as mock_create_worktree:
                                            with patch.object(handler, "is_commit_ancestor_of_branch", return_value=True) as mock_is_fresh:
                                                result = handler.prepare_developer_branch(item, workspace_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["branch"], "circus/issue-7-create-branch-before-launch")
        self.assertEqual(result["workspace_path"], workspace_path)
        mock_detect_base.assert_called_once_with("C:/target/repo")
        mock_refresh_base.assert_called_once_with("C:/target/repo", "main")
        mock_resolve_base.assert_called_once_with("C:/target/repo", "origin/main")
        mock_local_branch_exists.assert_called_once_with("C:/target/repo", "circus/issue-7-create-branch-before-launch")
        mock_create_worktree.assert_called_once_with(
            "C:/target/repo",
            workspace_path,
            "circus/issue-7-create-branch-before-launch",
            "origin/main",
        )
        mock_is_fresh.assert_called_once_with(workspace_path, "abc123", "HEAD")

    def test_prepare_developer_branch_uses_existing_clean_worktree_when_present(self):
        item = {"number": 8, "title": "Reuse existing branch"}
        workspace_path = "C:/worktrees/repo/issue-8"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", side_effect=["main", "circus/issue-8-reuse-existing-branch"]):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "remote-head")) as mock_detect_base:
                        with patch.object(handler, "refresh_local_base_branch", return_value=True) as mock_refresh_base:
                            with patch.object(handler, "resolve_git_ref_commit", return_value="def456") as mock_resolve_base:
                                with patch.object(handler.os.path, "exists", return_value=True):
                                    with patch.object(handler, "is_commit_ancestor_of_branch", return_value=True) as mock_is_fresh:
                                        with patch.object(handler, "create_worktree_branch_from_base") as mock_create_worktree:
                                            result = handler.prepare_developer_branch(item, workspace_path)

        self.assertTrue(result["ok"])
        self.assertEqual(result["branch"], "circus/issue-8-reuse-existing-branch")
        self.assertEqual(result["workspace_path"], workspace_path)
        mock_detect_base.assert_called_once_with("C:/target/repo")
        mock_refresh_base.assert_called_once_with("C:/target/repo", "main")
        mock_resolve_base.assert_called_once_with("C:/target/repo", "origin/main")
        mock_is_fresh.assert_called_once_with(workspace_path, "def456", "HEAD")
        mock_create_worktree.assert_not_called()

    def test_prepare_developer_branch_returns_git_error_when_base_refresh_fails(self):
        item = {"number": 9, "title": "Refresh base branch"}
        workspace_path = "C:/worktrees/repo/issue-9"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", return_value="feature/stale"):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "remote-head")):
                        with patch.object(handler, "refresh_local_base_branch", return_value=False) as mock_refresh_base:
                            result = handler.prepare_developer_branch(item, workspace_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "git-error")
        self.assertEqual(result["error"], "unable to refresh base branch 'main'")
        mock_refresh_base.assert_called_once_with("C:/target/repo", "main")

    def test_prepare_developer_branch_blocks_clean_stale_existing_worktree(self):
        item = {"number": 10, "title": "Block stale existing worktree"}
        workspace_path = "C:/worktrees/repo/issue-10"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", return_value="main"):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "remote-head")):
                        with patch.object(handler, "refresh_local_base_branch", return_value=True):
                            with patch.object(handler, "resolve_git_ref_commit", return_value="fedcba"):
                                with patch.object(handler.os.path, "exists", return_value=True):
                                    with patch.object(handler, "is_commit_ancestor_of_branch", return_value=False):
                                        with patch.object(handler, "create_worktree_branch_from_base") as mock_create_worktree:
                                            result = handler.prepare_developer_branch(item, workspace_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "stale-clean-worktree")
        self.assertEqual(result["branch"], "circus/issue-10-block-stale-existing-worktree")
        self.assertEqual(result["base_ref"], "origin/main")
        self.assertEqual(result["base_commit"], "fedcba")
        self.assertEqual(result["workspace_path"], workspace_path)
        mock_create_worktree.assert_not_called()

    def test_prepare_developer_branch_blocks_existing_issue_branch_without_workspace(self):
        item = {"number": 13, "title": "Block existing issue branch without workspace"}
        workspace_path = "C:/worktrees/repo/issue-13"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", return_value="main"):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "remote-head")):
                        with patch.object(handler, "refresh_local_base_branch", return_value=True):
                            with patch.object(handler, "resolve_git_ref_commit", return_value="bead00"):
                                with patch.object(handler.os.path, "exists", return_value=False):
                                    with patch.object(handler, "local_branch_exists", return_value=True) as mock_local_branch_exists:
                                        with patch.object(handler, "create_worktree_branch_from_base") as mock_create_worktree:
                                            result = handler.prepare_developer_branch(item, workspace_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "git-error")
        self.assertEqual(
            result["error"],
            "issue branch 'circus/issue-13-block-existing-issue-branch-without-workspace' already exists "
            "without expected workspace 'C:/worktrees/repo/issue-13'; refusing to reset branch",
        )
        mock_local_branch_exists.assert_called_once_with(
            "C:/target/repo",
            "circus/issue-13-block-existing-issue-branch-without-workspace",
        )
        mock_create_worktree.assert_not_called()

    def test_prepare_developer_branch_blocks_dirty_stale_existing_worktree(self):
        item = {"number": 12, "title": "Dirty stale worktree"}
        workspace_path = "C:/worktrees/repo/issue-12"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", side_effect=["main", "circus/issue-12-dirty-stale-worktree"]):
                with patch.object(handler, "is_working_tree_clean", side_effect=[True, False]):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "remote-head")):
                        with patch.object(handler, "refresh_local_base_branch", return_value=True):
                            with patch.object(handler, "resolve_git_ref_commit", return_value="fedcba"):
                                with patch.object(handler.os.path, "exists", return_value=True):
                                    with patch.object(handler, "is_commit_ancestor_of_branch", return_value=False):
                                        result = handler.prepare_developer_branch(item, workspace_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "stale-dirty-worktree")
        self.assertEqual(result["branch"], "circus/issue-12-dirty-stale-worktree")
        self.assertEqual(result["current_branch"], "circus/issue-12-dirty-stale-worktree")
        self.assertEqual(result["workspace_path"], workspace_path)

    def test_prepare_developer_branch_blocks_dirty_tree_without_refreshing_base(self):
        item = {"number": 11, "title": "Dirty tree guard"}
        workspace_path = "C:/worktrees/repo/issue-11"

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", return_value="feature/stale"):
                with patch.object(handler, "is_working_tree_clean", return_value=False):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "remote-head")) as mock_detect_base:
                        with patch.object(handler, "refresh_local_base_branch", return_value=True) as mock_refresh_base:
                            result = handler.prepare_developer_branch(item, workspace_path)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "dirty-working-tree")
        self.assertEqual(result["branch"], "circus/issue-11-dirty-tree-guard")
        self.assertEqual(result["current_branch"], "feature/stale")
        mock_detect_base.assert_not_called()
        mock_refresh_base.assert_not_called()

    def test_detect_default_base_branch_prefers_origin_head_symbolic_ref(self):
        with patch.object(
            handler,
            "run_git_command_in_repo",
            return_value=Mock(returncode=0, stdout="origin/main\n", stderr=""),
        ) as mock_git:
            branch_name, source = handler.detect_default_base_branch("C:/target/repo")

        self.assertEqual(branch_name, "main")
        self.assertEqual(source, "remote-head")
        mock_git.assert_called_once_with("C:/target/repo", ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])

    def test_detect_default_base_branch_falls_back_to_main_when_detection_fails(self):
        responses = [
            Mock(returncode=1, stdout="", stderr="no origin head"),
            Mock(returncode=1, stdout="", stderr="remote unavailable"),
        ]

        with patch.object(handler, "run_git_command_in_repo", side_effect=responses):
            branch_name, source = handler.detect_default_base_branch("C:/target/repo")

        self.assertEqual(branch_name, "main")
        self.assertEqual(source, "fallback")

    def test_prepare_architect_execution_branch_checks_out_detected_base_branch(self):
        item = {"type": "issue", "number": 3, "title": "Architect prep"}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", side_effect=["circus/issue-3-work", "main"]):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "remote-head")):
                        with patch.object(handler, "checkout_branch", return_value=True) as mock_checkout:
                            result = handler.prepare_architect_execution_branch(item)

        self.assertTrue(result["ok"])
        self.assertEqual(result["branch"], "main")
        mock_checkout.assert_called_once_with("C:/target/repo", "main")

    def test_prepare_architect_execution_branch_uses_fallback_main_when_detection_fails(self):
        item = {"type": "issue", "number": 4, "title": "Architect fallback"}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", side_effect=["feature/stale", "main"]):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "detect_default_base_branch", return_value=("main", "fallback")):
                        with patch.object(handler, "checkout_branch", return_value=True) as mock_checkout:
                            result = handler.prepare_architect_execution_branch(item)

        self.assertTrue(result["ok"])
        self.assertEqual(result["branch"], "main")
        mock_checkout.assert_called_once_with("C:/target/repo", "main")

    def test_prepare_architect_execution_branch_blocks_when_working_tree_dirty(self):
        item = {"type": "issue", "number": 5, "title": "Architect blocked"}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", return_value="circus/issue-5-dirty"):
                with patch.object(handler, "is_working_tree_clean", return_value=False):
                    with patch.object(handler, "checkout_branch") as mock_checkout:
                        result = handler.prepare_architect_execution_branch(item)

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "dirty-working-tree")
        self.assertEqual(result["current_branch"], "circus/issue-5-dirty")
        mock_checkout.assert_not_called()

    def test_process_one_item_dirty_working_tree_blocks_developer_launch_and_releases_lock(self):
        item = {
            "type": "issue",
            "number": 41,
            "title": "Developer branch blocked by dirty tree",
            "labels": [{"name": "state:ready-for-dev"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(
                    handler,
                    "resolve_item_workspace_metadata",
                    return_value={"workspace_path": "C:/worktrees/repo/issue-41"},
                ) as mock_workspace_metadata:
                    with patch.object(
                        handler,
                        "prepare_developer_branch",
                        return_value={
                            "ok": False,
                            "reason": "dirty-working-tree",
                            "branch": "circus/issue-41-developer-branch-blocked-by-dirty-tree",
                            "current_branch": "main",
                        },
                    ) as mock_prepare_branch:
                        with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                            with patch.object(handler, "add_comment") as mock_add_comment:
                                with patch.object(handler, "write_launch_brief") as mock_write_launch_brief:
                                    dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_workspace_metadata.assert_called_once_with(item)
        mock_prepare_branch.assert_called_once_with(item, "C:/worktrees/repo/issue-41")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        mock_write_launch_brief.assert_called_once()
        self.assertIn("working tree is dirty", item["comment"])
        self.assertIn("lock label `state:agent-in-progress` was released", item["comment"])

    def test_process_one_item_architect_route_prepares_base_branch_and_not_developer_branch(self):
        item = {
            "type": "issue",
            "number": 42,
            "title": "Architect path",
            "labels": [{"name": "state:ready-for-architecture"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(handler, "prepare_developer_branch") as mock_prepare_branch:
                    with patch.object(handler, "prepare_architect_execution_branch", return_value={"ok": True, "branch": "main"}) as mock_prepare_architect:
                        with patch.object(handler, "write_launch_brief", return_value="Watchtower/runs/issue-42/run-001-architect/launch-brief.md"):
                            with patch.object(handler, "launch_agent", return_value=True):
                                dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "success")
        mock_prepare_branch.assert_not_called()
        mock_prepare_architect.assert_called_once_with(item)
        self.assertEqual(item["execution_branch"], "main")

    def test_process_one_item_roadmap_updater_prepares_working_branch_before_launch(self):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Roadmap updater branch prep",
            "labels": [{"name": "state:ready-for-roadmap-update"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(
                    handler,
                    "resolve_item_workspace_metadata",
                    return_value={"workspace_path": "C:/worktrees/repo/issue-43"},
                ) as mock_workspace_metadata:
                    with patch.object(
                        handler,
                        "prepare_developer_branch",
                        return_value={
                            "ok": True,
                            "branch": "circus/issue-43-roadmap-updater-branch-prep",
                            "workspace_path": "C:/worktrees/repo/issue-43",
                        },
                    ) as mock_prepare_branch:
                        with patch.object(handler, "write_launch_brief", return_value="Watchtower/runs/issue-43/run-001-roadmap-updater/launch-brief.md"):
                            with patch.object(handler, "launch_agent", return_value=True):
                                dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "success")
        mock_workspace_metadata.assert_called_once_with(item)
        mock_prepare_branch.assert_called_once_with(item, "C:/worktrees/repo/issue-43")
        self.assertEqual(item["working_branch"], "circus/issue-43-roadmap-updater-branch-prep")
        self.assertEqual(item["workspace_path"], "C:/worktrees/repo/issue-43")

    def test_process_one_item_implementation_planner_prepares_working_branch_before_launch(self):
        item = {
            "type": "issue",
            "number": 143,
            "title": "Implementation planner branch prep",
            "labels": [{"name": "state:ready-for-implementation-planning"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(
                    handler,
                    "resolve_item_workspace_metadata",
                    return_value={"workspace_path": "C:/worktrees/repo/issue-143"},
                ) as mock_workspace_metadata:
                    with patch.object(
                        handler,
                        "prepare_developer_branch",
                        return_value={
                            "ok": True,
                            "branch": "circus/issue-143-implementation-planner-branch-prep",
                            "workspace_path": "C:/worktrees/repo/issue-143",
                        },
                    ) as mock_prepare_branch:
                        with patch.object(
                            handler,
                            "write_launch_brief",
                            return_value="Watchtower/runs/issue-143/run-001-implementation-planner/launch-brief.md",
                        ):
                            with patch.object(handler, "launch_agent", return_value=True):
                                dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "success")
        mock_workspace_metadata.assert_called_once_with(item)
        mock_prepare_branch.assert_called_once_with(item, "C:/worktrees/repo/issue-143")
        self.assertEqual(item["working_branch"], "circus/issue-143-implementation-planner-branch-prep")
        self.assertEqual(item["workspace_path"], "C:/worktrees/repo/issue-143")

    def test_process_one_item_dirty_working_tree_blocks_roadmap_updater_launch_and_releases_lock(self):
        item = {
            "type": "issue",
            "number": 44,
            "title": "Roadmap updater blocked by dirty tree",
            "labels": [{"name": "state:ready-for-roadmap-update"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(
                    handler,
                    "resolve_item_workspace_metadata",
                    return_value={"workspace_path": "C:/worktrees/repo/issue-44"},
                ) as mock_workspace_metadata:
                    with patch.object(
                        handler,
                        "prepare_developer_branch",
                        return_value={
                            "ok": False,
                            "reason": "dirty-working-tree",
                            "branch": "circus/issue-44-roadmap-updater-blocked-by-dirty-tree",
                            "current_branch": "main",
                        },
                    ) as mock_prepare_branch:
                        with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                            with patch.object(handler, "add_comment") as mock_add_comment:
                                with patch.object(handler, "write_launch_brief") as mock_write_launch_brief:
                                    dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_workspace_metadata.assert_called_once_with(item)
        mock_prepare_branch.assert_called_once_with(item, "C:/worktrees/repo/issue-44")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        mock_write_launch_brief.assert_called_once()
        self.assertIn("blocked roadmap updater launch", item["comment"])
        self.assertIn("working tree is dirty", item["comment"])

    def test_process_one_item_ready_for_review_with_missing_pr_skips_launch_and_releases_lock(self):
        item = {
            "type": "issue",
            "number": 42,
            "title": "Reviewer path missing linked PR",
            "labels": [{"name": "state:ready-for-review"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(handler, "find_open_review_pr_for_issue", return_value={"ok": True, "pr": None}):
                    with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                        with patch.object(handler, "add_comment") as mock_add_comment:
                            with patch.object(handler, "write_launch_brief") as mock_write_launch_brief:
                                with patch.object(handler, "launch_agent") as mock_launch_agent:
                                    dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        mock_write_launch_brief.assert_not_called()
        mock_launch_agent.assert_not_called()
        self.assertIn("no linked open PR was discovered", item["comment"])
        self.assertIn("labels were left unchanged", item["comment"])

    def test_process_one_item_stale_reviewer_candidate_releases_lock_and_skips_launch(self):
        item = {
            "type": "issue",
            "number": 44,
            "title": "Reviewer candidate became stale",
            "url": "https://github.com/owner/repo/issues/44",
            "labels": [{"name": "state:ready-for-review"}],
        }
        current_item = {
            "type": "issue",
            "number": 44,
            "title": "Reviewer candidate became stale",
            "url": "https://github.com/owner/repo/issues/44",
            "labels": [
                {"name": "state:changes-requested"},
                {"name": handler.LOCK_LABEL},
            ],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(current_item, True)):
                with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                    with patch.object(handler, "find_open_review_pr_for_issue") as mock_find_review_pr:
                        with patch.object(handler, "write_launch_brief") as mock_write_launch_brief:
                            with patch.object(handler, "launch_agent") as mock_launch_agent:
                                with patch.object(handler, "add_comment") as mock_add_comment:
                                    dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "stale-candidate")
        mock_unlock.assert_called_once_with(item)
        mock_find_review_pr.assert_not_called()
        mock_write_launch_brief.assert_not_called()
        mock_launch_agent.assert_not_called()
        mock_add_comment.assert_not_called()

    def test_process_one_item_candidate_without_url_still_revalidates_after_lock(self):
        item = {
            "type": "issue",
            "number": 144,
            "title": "Candidate without URL became stale",
            "labels": [{"name": "state:ready-for-review"}],
        }
        current_item = {
            "type": "issue",
            "number": 144,
            "title": "Candidate without URL became stale",
            "labels": [
                {"name": "state:changes-requested"},
                {"name": handler.LOCK_LABEL},
            ],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(current_item, True)) as mock_get_current_item:
                with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                    with patch.object(handler, "find_open_review_pr_for_issue") as mock_find_review_pr:
                        with patch.object(handler, "write_launch_brief") as mock_write_launch_brief:
                            with patch.object(handler, "launch_agent") as mock_launch_agent:
                                dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "stale-candidate")
        mock_get_current_item.assert_called_once_with(item)
        mock_unlock.assert_called_once_with(item)
        mock_find_review_pr.assert_not_called()
        mock_write_launch_brief.assert_not_called()
        mock_launch_agent.assert_not_called()

    def test_process_one_item_revalidation_matching_state_continues_reviewer_dispatch(self):
        item = {
            "type": "issue",
            "number": 45,
            "title": "Reviewer candidate still current",
            "url": "https://github.com/owner/repo/issues/45",
            "labels": [{"name": "state:ready-for-review"}],
        }
        current_item = {
            "type": "issue",
            "number": 45,
            "title": "Reviewer candidate still current (fresh)",
            "url": "https://github.com/owner/repo/issues/45",
            "labels": [
                {"name": "state:ready-for-review"},
                {"name": handler.LOCK_LABEL},
            ],
        }
        review_pr = {"number": 90, "url": "https://github.com/owner/repo/pull/90"}

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(current_item, True)):
                with patch.object(
                    handler,
                    "find_open_review_pr_for_issue",
                    return_value={"ok": True, "pr": review_pr, "match_reason": "preferred-closes"},
                ) as mock_find_review_pr:
                    with patch.object(
                        handler,
                        "write_launch_brief",
                        return_value="Watchtower/runs/issue-45/run-001-reviewer/launch-brief.md",
                    ) as mock_write_launch_brief:
                        with patch.object(handler, "launch_agent", return_value=True) as mock_launch_agent:
                            with patch.object(handler, "unlock_item") as mock_unlock:
                                dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "success")
        mock_find_review_pr.assert_called_once_with(45)
        mock_write_launch_brief.assert_called_once()
        mock_launch_agent.assert_called_once()
        mock_unlock.assert_not_called()
        self.assertEqual(item["title"], "Reviewer candidate still current (fresh)")

    def test_process_one_item_revalidation_fetch_failure_releases_lock_comments_and_fails_prelaunch(self):
        item = {
            "type": "issue",
            "number": 46,
            "title": "Revalidation fetch failed",
            "url": "https://github.com/owner/repo/issues/46",
            "labels": [{"name": "state:ready-for-dev"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(None, False)):
                with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                    with patch.object(handler, "add_comment") as mock_add_comment:
                        with patch.object(handler, "write_launch_brief") as mock_write_launch_brief:
                            with patch.object(handler, "launch_agent") as mock_launch_agent:
                                dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        mock_write_launch_brief.assert_not_called()
        mock_launch_agent.assert_not_called()
        self.assertIn("could not re-fetch issue #46", item["comment"])
        self.assertIn("The lock label `state:agent-in-progress` was released", item["comment"])

    def test_process_one_item_dirty_working_tree_blocks_architect_launch_and_releases_lock(self):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Architect blocked by dirty tree",
            "labels": [{"name": "state:ready-for-architecture"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
            with patch.object(handler, "get_current_item", return_value=(item, True)):
                with patch.object(
                    handler,
                    "prepare_architect_execution_branch",
                    return_value={
                        "ok": False,
                        "reason": "dirty-working-tree",
                        "current_branch": "circus/issue-43-dirty",
                    },
                ):
                    with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                        with patch.object(handler, "add_comment") as mock_add_comment:
                            with patch.object(handler, "write_launch_brief") as mock_write_launch_brief:
                                dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        mock_write_launch_brief.assert_called_once()
        self.assertIn("blocked architect launch", item["comment"])
        self.assertIn("working tree is dirty", item["comment"])
        self.assertIn("lock label `state:agent-in-progress` was released", item["comment"])

    def test_build_launch_brief_markdown_marks_missing_role_reference(self):
        item = {
            "type": "issue",
            "number": 4,
            "title": "No role path configured",
        }
        config = {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.object(handler, "REPO", "owner/repo"):
            markdown = handler.build_launch_brief_markdown(
                item,
                "state:ready-for-review",
                config,
                None,
                "2026-05-25T09:22:00",
                "C:/target/repo",
            )

        self.assertIn("## Agent Profile", markdown)
        self.assertIn("- profile source: `<not available>`", markdown)
        self.assertNotIn("docs\\doctrine.md", markdown)
        self.assertNotIn("docs\\operations-status.md", markdown)

    def test_write_launch_brief_creates_markdown_file(self):
        item = {
            "type": "issue",
            "number": 3,
            "title": "Implement launch brief",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(handler, "LAUNCH_ARTIFACT_DIR", temp_dir):
                with patch.object(handler, "REPO", "owner/repo"):
                    with patch.object(handler, "TARGET_REPO_PATH", "C:\\target\\repo"):
                        with patch.dict(os.environ, {}, clear=False):
                            os.environ.pop("CIRCUS_WORKTREE_ROOT", None)
                            with patch.object(
                                handler.watchtower.workspace_diagnostics,
                                "collect_workspace_lifecycle_diagnostic",
                                return_value={
                                    "workspace": "C:/target/repo-worktrees/owner-repo/issue-3",
                                    "state": "planned",
                                    "branch": "circus/issue-3-implement-launch-brief",
                                    "issue": "issue #3",
                                    "pr": "none",
                                    "reasons": [],
                                    "ambiguity_indicators": [],
                                    "recommended_action": "Create or assign the workspace before launch.",
                                },
                            ) as mock_lifecycle_diagnostic:
                                brief_path = handler.write_launch_brief(
                                    item,
                                    "state:ready-for-dev",
                                    config,
                                    os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                                )

            self.assertTrue(os.path.isfile(brief_path))
            with open(brief_path, "r", encoding="utf-8") as generated_file:
                content = generated_file.read()

            shared_dir = os.path.join(temp_dir, "owner-repo", "issue-3", "shared")
            self.assertTrue(os.path.isdir(shared_dir))

            architecture_handoff_path = os.path.join(shared_dir, "architecture-handoff.md")
            running_notes_path = os.path.join(shared_dir, "running-notes.md")
            decision_log_path = os.path.join(shared_dir, "decision-log.md")

            self.assertTrue(os.path.isfile(architecture_handoff_path))
            self.assertTrue(os.path.isfile(running_notes_path))
            self.assertTrue(os.path.isfile(decision_log_path))

            with open(architecture_handoff_path, "r", encoding="utf-8") as architecture_handoff_file:
                architecture_handoff_content = architecture_handoff_file.read()
            with open(running_notes_path, "r", encoding="utf-8") as running_notes_file:
                running_notes_content = running_notes_file.read()
            with open(decision_log_path, "r", encoding="utf-8") as decision_log_file:
                decision_log_content = decision_log_file.read()

            run_dir = os.path.dirname(brief_path)
            status_path = os.path.join(run_dir, "status.json")
            result_path = os.path.join(run_dir, "result.md")
            self.assertTrue(os.path.isfile(status_path))
            self.assertFalse(os.path.exists(result_path))
            with open(status_path, "r", encoding="utf-8") as status_file:
                status_payload = json.load(status_file)

        self.assertIn("# Launch Brief", content)
        self.assertIn("## Runtime Roots", content)
        self.assertIn(
            f"- circus repo root: `{handler.normalize_path_for_display(handler.get_circus_runtime_root())}`",
            content,
        )
        self.assertIn("- target repo root: `C:/target/repo`", content)
        self.assertIn("- target worktree root: `C:/target/repo-worktrees`", content)
        self.assertIn("## Assignment", content)
        self.assertIn("- repository: `owner/repo`", content)
        self.assertIn("- target repo path: `C:/target/repo`", content)
        self.assertIn("- item workspace name: `issue-3`", content)
        self.assertIn("- item workspace path: `C:/target/repo-worktrees/owner-repo/issue-3`", content)
        self.assertIn("- workspace branch: `<not available>`", content)
        self.assertIn("- workspace lifecycle: `planned`", content)
        self.assertIn("- workspace item identity: `issue-3`", content)
        self.assertIn("- worktree root source: `derived-default`", content)
        self.assertIn("## Agent Profile", content)
        self.assertIn(
            f"- profile source: `{handler.normalize_path_for_display(handler.get_circus_runtime_root())}/TheFarm/roles/developer.md`",
            content,
        )
        self.assertIn("## Shared Context", content)
        self.assertIn(
            f"- architecture handoff: `{temp_dir.replace('\\', '/')}/owner-repo/issue-3/shared/architecture-handoff.md`",
            content,
        )
        self.assertIn(
            f"- running notes: `{temp_dir.replace('\\', '/')}/owner-repo/issue-3/shared/running-notes.md`",
            content,
        )
        self.assertIn(
            f"- decision log: `{temp_dir.replace('\\', '/')}/owner-repo/issue-3/shared/decision-log.md`",
            content,
        )
        self.assertIn("- generated-by: `Handler`", content)
        self.assertNotIn("role/prompt", content)
        self.assertNotIn("\\", content)
        self.assertNotIn("docs\\doctrine.md", content)
        self.assertNotIn("docs\\operations-status.md", content)
        self.assertEqual(status_payload["repository"], "owner/repo")
        self.assertEqual(status_payload["item_type"], "issue")
        self.assertEqual(status_payload["item_number"], 3)
        self.assertEqual(status_payload["state_label"], "state:ready-for-dev")
        self.assertEqual(status_payload["agent"], "junie")
        self.assertEqual(status_payload["mode"], "developer")
        self.assertIsNone(status_payload["started_at"])
        self.assertIsNone(status_payload["exit_code"])
        self.assertEqual(status_payload["worktree_root"], "C:/target/repo-worktrees")
        self.assertEqual(status_payload["worktree_root_source"], "derived-default")
        self.assertEqual(status_payload["workspace_name"], "issue-3")
        self.assertEqual(status_payload["workspace_path"], "C:/target/repo-worktrees/owner-repo/issue-3")
        self.assertIsNone(status_payload["workspace_branch"])
        self.assertEqual(status_payload["workspace_lifecycle"], "planned")
        self.assertEqual(
            status_payload["lifecycle_diagnostics"],
            [
                {
                    "workspace": "C:/target/repo-worktrees/owner-repo/issue-3",
                    "state": "planned",
                    "branch": "circus/issue-3-implement-launch-brief",
                    "issue": "issue #3",
                    "pr": "none",
                    "reasons": [],
                    "ambiguity_indicators": [],
                    "recommended_action": "Create or assign the workspace before launch.",
                }
            ],
        )
        self.assertEqual(status_payload["workspace_item_identity"], "issue-3")
        self.assertEqual(status_payload["artifacts"]["workspace"], "C:/target/repo-worktrees/owner-repo/issue-3")
        self.assertEqual(status_payload["artifacts"]["launch_brief"], brief_path.replace("\\", "/"))
        mock_lifecycle_diagnostic.assert_called_once_with(
            repo_path="C:\\target\\repo",
            workspace_path="C:/target/repo-worktrees/owner-repo/issue-3",
            item=item,
        )

        self.assertEqual(
            architecture_handoff_content,
            "# Architecture Handoff\n\nNo architecture handoff has been recorded yet.\n",
        )
        self.assertEqual(
            running_notes_content,
            "# Running Notes\n\nNo running notes have been recorded yet.\n",
        )
        self.assertEqual(
            decision_log_content,
            "# Decision Log\n\nNo decisions have been recorded yet.\n",
        )

    def test_write_run_result_includes_workspace_metadata_fields(self):
        item = {
            "type": "issue",
            "number": 32,
            "title": "Workspace metadata in run result",
            "working_branch": "circus/issue-32-workspace-metadata",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        workspace_metadata = {
            "worktree_root": "C:/target/repo-worktrees",
            "worktree_root_source": "env:CIRCUS_WORKTREE_ROOT",
            "workspace_name": "issue-32",
            "workspace_path": "C:/target/repo-worktrees/owner-repo/issue-32",
            "workspace_branch": "circus/issue-32-workspace-metadata",
            "workspace_lifecycle": "isolated",
            "workspace_item_identity": "issue-32",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            launch_brief_path = os.path.join(temp_dir, "owner-repo", "issue-32", "run-001-developer", "launch-brief.md")
            os.makedirs(os.path.dirname(launch_brief_path), exist_ok=True)
            with open(launch_brief_path, "w", encoding="utf-8") as launch_brief_file:
                launch_brief_file.write("# Launch Brief\n")

            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                    handler.initialize_run_status(
                        item,
                        "state:changes-requested",
                        config,
                        launch_brief_path,
                        workspace_metadata,
                    )
                    handler.update_run_status(
                        item,
                        started_at="2026-06-19T08:00:00Z",
                        completed_at="2026-06-19T08:05:00Z",
                        exit_code=0,
                        success=True,
                        outcome="success",
                        stop_reason=None,
                    )
                    handler.write_run_result(item)

            result_path = os.path.join(os.path.dirname(launch_brief_path), "result.md")
            self.assertTrue(os.path.isfile(result_path))
            with open(result_path, "r", encoding="utf-8") as result_file:
                result_content = result_file.read()

        self.assertIn("- workspace path: `C:/target/repo-worktrees/owner-repo/issue-32`", result_content)
        self.assertIn("- workspace branch: `circus/issue-32-workspace-metadata`", result_content)
        self.assertIn("- workspace lifecycle: `isolated`", result_content)
        self.assertIn("- workspace item identity: `issue-32`", result_content)
        self.assertIn("- worktree root source: `env:CIRCUS_WORKTREE_ROOT`", result_content)

    def test_write_run_result_lists_generated_issue_links_inside_implementation_planner_section(self):
        item = {
            "type": "issue",
            "number": 69,
            "title": "Record planner outcomes",
            "working_branch": "circus/issue-69-record-planner-outcomes",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            launch_brief_path = os.path.join(temp_dir, "owner-repo", "issue-69", "run-001-developer", "launch-brief.md")
            os.makedirs(os.path.dirname(launch_brief_path), exist_ok=True)
            with open(launch_brief_path, "w", encoding="utf-8") as launch_brief_file:
                launch_brief_file.write("# Launch Brief\n")

            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                    handler.initialize_run_status(item, "state:changes-requested", config, launch_brief_path)
                    handler.update_run_status(
                        item,
                        started_at="2026-06-24T08:00:00Z",
                        completed_at="2026-06-24T08:05:00Z",
                        exit_code=0,
                        success=True,
                        outcome="success",
                        stop_reason=None,
                        implementation_planner={
                            "outcome": "READY",
                            "outcome_valid": True,
                            "diagnostic": None,
                            "implementation_plan": "C:/target/repo/Watchtower/runs/issue-69/run-001/implementation-plan.md",
                            "recommended_route": None,
                            "generated_issues": [
                                {
                                    "number": 69,
                                    "url": "https://github.com/owner/repo/issues/69",
                                }
                            ],
                            "source_recommendation_url": None,
                            "source_recommendation_comment_id": None,
                            "roadmap_reference": None,
                        },
                    )
                    handler.write_run_result(item)

            result_path = os.path.join(os.path.dirname(launch_brief_path), "result.md")
            with open(result_path, "r", encoding="utf-8") as result_file:
                result_content = result_file.read()

        implementation_section = result_content.split("## Implementation Planner", 1)[1].split("## Artifacts", 1)[0]
        self.assertIn("- generated issues:", implementation_section)
        self.assertIn("  - #69: `https://github.com/owner/repo/issues/69`", implementation_section)

    def test_write_run_result_includes_workspace_lifecycle_diagnostics(self):
        item = {
            "type": "issue",
            "number": 62,
            "title": "Workspace diagnostics in run result",
            "working_branch": "circus/issue-62-workspace-diagnostics",
        }
        config = {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }
        workspace_metadata = {
            "workspace_path": "C:/target/repo-worktrees/owner-repo/issue-62",
            "workspace_branch": "circus/issue-62-workspace-diagnostics",
            "workspace_lifecycle": "recoverable",
            "workspace_item_identity": "issue-62",
        }
        lifecycle_diagnostics = [
            {
                "workspace": "C:/target/repo-worktrees/owner-repo/issue-62",
                "state": "recoverable",
                "branch": "circus/issue-62-workspace-diagnostics",
                "issue": "issue #62",
                "pr": "PR #71 (open) https://github.com/owner/repo/pull/71",
                "reasons": ["dirty_worktree", "open_pr_exists"],
                "ambiguity_indicators": [],
                "recommended_action": "Recover workspace before reassignment or cleanup.",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            launch_brief_path = os.path.join(temp_dir, "owner-repo", "issue-62", "run-001-developer", "launch-brief.md")
            os.makedirs(os.path.dirname(launch_brief_path), exist_ok=True)
            with open(launch_brief_path, "w", encoding="utf-8") as launch_brief_file:
                launch_brief_file.write("# Launch Brief\n")

            with patch.object(handler, "REPO", "owner/repo"):
                with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                    handler.initialize_run_status(
                        item,
                        "state:ready-for-dev",
                        config,
                        launch_brief_path,
                        workspace_metadata,
                    )
                    handler.update_run_status(
                        item,
                        started_at="2026-06-23T08:00:00Z",
                        completed_at="2026-06-23T08:05:00Z",
                        exit_code=0,
                        success=True,
                        outcome="success",
                        stop_reason=None,
                        lifecycle_diagnostics=lifecycle_diagnostics,
                    )
                    handler.write_run_result(item)

            result_path = os.path.join(os.path.dirname(launch_brief_path), "result.md")
            status_path = os.path.join(os.path.dirname(launch_brief_path), "status.json")
            with open(result_path, "r", encoding="utf-8") as result_file:
                result_content = result_file.read()
            with open(status_path, "r", encoding="utf-8") as status_file:
                status_payload = json.load(status_file)

        self.assertEqual(status_payload["lifecycle_diagnostics"], lifecycle_diagnostics)
        self.assertIn("## Lifecycle Diagnostics", result_content)
        self.assertIn("- workspace: `C:/target/repo-worktrees/owner-repo/issue-62`", result_content)
        self.assertIn("  - state: `recoverable`", result_content)
        self.assertIn("  - branch: `circus/issue-62-workspace-diagnostics`", result_content)
        self.assertIn("  - issue: `issue #62`", result_content)
        self.assertIn("  - PR: `PR #71 (open) https://github.com/owner/repo/pull/71`", result_content)
        self.assertIn("  - recommended action: Recover workspace before reassignment or cleanup.", result_content)

    def test_ensure_shared_artifacts_does_not_overwrite_existing_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            item_run_root = os.path.join(temp_dir, "issue-7")
            shared_dir = os.path.join(item_run_root, "shared")
            os.makedirs(shared_dir, exist_ok=True)

            architecture_handoff_path = os.path.join(shared_dir, "architecture-handoff.md")
            with open(architecture_handoff_path, "w", encoding="utf-8") as architecture_handoff_file:
                architecture_handoff_file.write("# Architecture Handoff\n\nExisting handoff context.\n")

            with patch.object(handler, "LAUNCH_ARTIFACT_DIR", temp_dir):
                shared_context_paths = handler.ensure_shared_artifacts(item_run_root)

            self.assertEqual(
                shared_context_paths["architecture_handoff"],
                f"{temp_dir.replace('\\', '/')}/issue-7/shared/architecture-handoff.md",
            )
            self.assertEqual(
                shared_context_paths["running_notes"],
                f"{temp_dir.replace('\\', '/')}/issue-7/shared/running-notes.md",
            )
            self.assertEqual(
                shared_context_paths["decision_log"],
                f"{temp_dir.replace('\\', '/')}/issue-7/shared/decision-log.md",
            )

            with open(architecture_handoff_path, "r", encoding="utf-8") as architecture_handoff_file:
                self.assertEqual(
                    architecture_handoff_file.read(),
                    "# Architecture Handoff\n\nExisting handoff context.\n",
                )

            self.assertTrue(os.path.isfile(os.path.join(shared_dir, "running-notes.md")))
            self.assertTrue(os.path.isfile(os.path.join(shared_dir, "decision-log.md")))

    def test_get_labeled_items_filters_supported_labels_and_reports_unsupported_states(self):
        issues_payload = (
            "["
            "{\"number\": 11, \"title\": \"ready\", \"labels\": [{\"name\": \"state:ready-for-review\"}]},"
            "{\"number\": 12, \"title\": \"unknown\", \"labels\": [{\"name\": \"state:unknown-state\"}]},"
            "{\"number\": 13, \"title\": \"plain\", \"labels\": [{\"name\": \"bug\"}]}"
            "]"
        )
        prs_payload = (
            "["
            "{\"number\": 21, \"title\": \"multi\", \"labels\": ["
            "{\"name\": \"state:ready-for-dev\"},"
            "{\"name\": \"state:other\"}"
            "]}"
            "]"
        )

        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", side_effect=[issues_payload, prs_payload]):
                with patch("builtins.print") as mock_print:
                    issues, prs, candidates, ok = handler.get_labeled_items()

        self.assertTrue(ok)
        self.assertEqual(len(issues), 3)
        self.assertEqual(len(prs), 1)
        self.assertEqual([item["number"] for item in candidates], [11, 21])

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(
            any(
                "[Poll] issue #12 has unsupported state label(s): ['state:unknown-state']" in line
                for line in printed_lines
            )
        )


if __name__ == "__main__":
    unittest.main()
