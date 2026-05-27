import unittest
import tempfile
import os
import json
import re
from unittest.mock import Mock, patch

import Handler.handler as handler


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
            with patch.object(handler.shutil, "which", side_effect=which_side_effect):
                with patch("builtins.print") as mock_print:
                    resolved = handler.validate_required_executables()

        self.assertEqual(resolved["junie"], "C:/custom/junie.exe")
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("via CIRCUS_JUNIE_EXECUTABLE" in line for line in printed_lines))

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
        self.assertIn("failed to start Junie before execution began", item["comment"])
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
        self.assertIn("failed to start Junie before execution began", item["comment"])
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
                                        with patch("builtins.print") as mock_print:
                                            handler.poll()

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Handler] Max workflow steps this run: 1" in line for line in printed_lines))
        self.assertTrue(any("[Poll] Starting cycle #1..." in line for line in printed_lines))
        self.assertTrue(any("[Poll] Retrieved issues=0, prs=0, candidates=0." in line for line in printed_lines))
        self.assertTrue(any("[Poll] No candidate items matched workflow labels this cycle." in line for line in printed_lines))
        self.assertTrue(any("[Handler] No eligible workflow step found. Exiting." in line for line in printed_lines))

    def test_get_max_steps_per_run_defaults_to_one_when_env_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(handler.get_max_steps_per_run(), 1)

    def test_get_max_steps_per_run_uses_configured_value(self):
        with patch.dict(os.environ, {"CIRCUS_MAX_STEPS_PER_RUN": "2"}, clear=True):
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
                                    ],
                                ) as mock_get_labeled_items:
                                    with patch.object(handler, "process_one_item", side_effect=["success", "success"]) as mock_process:
                                        with patch("builtins.print") as mock_print:
                                            handler.poll()

        self.assertEqual(mock_get_labeled_items.call_count, 2)
        self.assertEqual(mock_process.call_count, 2)

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Handler] Completed workflow step 1 of 2." in line for line in printed_lines))
        self.assertTrue(any("[Handler] Re-polling for next eligible workflow step." in line for line in printed_lines))
        self.assertTrue(any("[Handler] Completed workflow step 2 of 2." in line for line in printed_lines))
        self.assertTrue(any("[Handler] Max workflow steps reached. Exiting." in line for line in printed_lines))

    def test_get_candidates_fetches_without_label_filter(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="[]") as mock_run:
                items, ok = handler.get_candidates("issue", "issue list")

        self.assertEqual(items, [])
        self.assertTrue(ok)
        mock_run.assert_called_once_with("gh issue list --repo owner/repo --json number,labels,title,url")

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
        mock_finalize.assert_called_once_with(item, launch_brief_path)

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
        mock_advance.assert_called_once_with(item)
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
        mock_advance.assert_called_once_with(item)

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

    def test_build_codex_architect_task_text_includes_handoff_and_comment_requirements(self):
        task_text = handler.build_codex_architect_task_text("C:/abs/Watchtower/runs/issue-9/run-001-architect/launch-brief.md")

        self.assertIn(
            "Read the launch brief at C:/abs/Watchtower/runs/issue-9/run-001-architect/launch-brief.md",
            task_text,
        )
        self.assertIn("execute the architect workflow", task_text)
        self.assertIn("Produce or update the architecture handoff artifact", task_text)
        self.assertIn("leave a GitHub comment summarizing the handoff or blocker", task_text)

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
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", command[6])
        self.assertIn("execute the architect workflow", command[6])
        self.assertIn("Produce or update the architecture handoff artifact", command[6])
        self.assertIn("leave a GitHub comment summarizing the handoff or blocker", command[6])

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

    def test_launch_agent_codex_non_architect_mode_remains_non_executing_placeholder(self):
        item = {
            "type": "issue",
            "number": 9,
            "title": "Review changes",
            "url": "https://github.com/owner/repo/issues/9",
        }
        config = {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        }

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.subprocess, "run") as mock_subprocess_run:
                with patch("builtins.print") as mock_print:
                    launched = handler.launch_agent(
                        item,
                        "state:ready-for-review",
                        config,
                        os.path.normpath(os.path.join("TheFarm", "roles", "reviewer.md")),
                        "Watchtower/runs/issue-9/run-001-reviewer/launch-brief.md",
                    )

        self.assertTrue(launched)
        mock_subprocess_run.assert_not_called()
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Codex execution flow currently enabled only for architect mode" in line for line in printed_lines))

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
                path = handler.build_launch_brief_path(item, "developer")

        self.assertEqual(path, f"{temp_dir.replace('\\', '/')}/issue-3/run-001-developer/launch-brief.md")
        self.assertNotIn("\\", path)

    def test_build_launch_brief_path_increments_run_number_for_existing_item(self):
        item = {"type": "issue", "number": 3}

        with tempfile.TemporaryDirectory() as temp_dir:
            item_root = os.path.join(temp_dir, "issue-3")
            os.makedirs(os.path.join(item_root, "run-001-developer"), exist_ok=True)
            os.makedirs(os.path.join(item_root, "run-002-reviewer"), exist_ok=True)

            with patch.object(handler, "LAUNCH_ARTIFACT_DIR", temp_dir):
                path = handler.build_launch_brief_path(item, "developer")

        self.assertEqual(path, f"{temp_dir.replace('\\', '/')}/issue-3/run-003-developer/launch-brief.md")
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
        architecture_handoff_path = f"{normalized_circus_root}/Watchtower/runs/issue-3/shared/architecture-handoff.md"
        running_notes_path = f"{normalized_circus_root}/Watchtower/runs/issue-3/shared/running-notes.md"
        decision_log_path = f"{normalized_circus_root}/Watchtower/runs/issue-3/shared/decision-log.md"

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

    def test_prepare_developer_branch_creates_new_branch_when_missing(self):
        item = {"number": 7, "title": "Create branch before launch"}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", side_effect=["main", "circus/issue-7-create-branch-before-launch"]):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "local_branch_exists", return_value=False):
                        with patch.object(handler, "checkout_or_create_local_branch", return_value=True) as mock_checkout:
                            result = handler.prepare_developer_branch(item)

        self.assertTrue(result["ok"])
        self.assertEqual(result["branch"], "circus/issue-7-create-branch-before-launch")
        mock_checkout.assert_called_once_with("C:/target/repo", "circus/issue-7-create-branch-before-launch", False)

    def test_prepare_developer_branch_uses_existing_branch_when_present(self):
        item = {"number": 8, "title": "Reuse existing branch"}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler, "get_current_git_branch", side_effect=["main", "circus/issue-8-reuse-existing-branch"]):
                with patch.object(handler, "is_working_tree_clean", return_value=True):
                    with patch.object(handler, "local_branch_exists", return_value=True):
                        with patch.object(handler, "checkout_or_create_local_branch", return_value=True) as mock_checkout:
                            result = handler.prepare_developer_branch(item)

        self.assertTrue(result["ok"])
        self.assertEqual(result["branch"], "circus/issue-8-reuse-existing-branch")
        mock_checkout.assert_called_once_with("C:/target/repo", "circus/issue-8-reuse-existing-branch", True)

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
            with patch.object(
                handler,
                "prepare_developer_branch",
                return_value={
                    "ok": False,
                    "reason": "dirty-working-tree",
                    "branch": "circus/issue-41-developer-branch-blocked-by-dirty-tree",
                    "current_branch": "main",
                },
            ):
                with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                    with patch.object(handler, "add_comment") as mock_add_comment:
                        with patch.object(handler, "write_launch_brief") as mock_write_launch_brief:
                            dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "prelaunch-failed")
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        mock_write_launch_brief.assert_not_called()
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
            with patch.object(handler, "prepare_developer_branch") as mock_prepare_branch:
                with patch.object(handler, "prepare_architect_execution_branch", return_value={"ok": True, "branch": "main"}) as mock_prepare_architect:
                    with patch.object(handler, "write_launch_brief", return_value="Watchtower/runs/issue-42/run-001-architect/launch-brief.md"):
                        with patch.object(handler, "launch_agent", return_value=True):
                            dispatched = handler.process_one_item([item])

        self.assertEqual(dispatched, "success")
        mock_prepare_branch.assert_not_called()
        mock_prepare_architect.assert_called_once_with(item)
        self.assertEqual(item["execution_branch"], "main")

    def test_process_one_item_dirty_working_tree_blocks_architect_launch_and_releases_lock(self):
        item = {
            "type": "issue",
            "number": 43,
            "title": "Architect blocked by dirty tree",
            "labels": [{"name": "state:ready-for-architecture"}],
        }

        with patch.object(handler, "lock_item", return_value=True):
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
        mock_write_launch_brief.assert_not_called()
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
                        brief_path = handler.write_launch_brief(
                            item,
                            "state:ready-for-dev",
                            config,
                            os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                        )

            self.assertTrue(os.path.isfile(brief_path))
            with open(brief_path, "r", encoding="utf-8") as generated_file:
                content = generated_file.read()

            shared_dir = os.path.join(temp_dir, "issue-3", "shared")
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

        self.assertIn("# Launch Brief", content)
        self.assertIn("## Runtime Roots", content)
        self.assertIn(
            f"- circus repo root: `{handler.normalize_path_for_display(handler.get_circus_runtime_root())}`",
            content,
        )
        self.assertIn("- target repo root: `C:/target/repo`", content)
        self.assertIn("## Assignment", content)
        self.assertIn("- repository: `owner/repo`", content)
        self.assertIn("- target repo path: `C:/target/repo`", content)
        self.assertIn("## Agent Profile", content)
        self.assertIn(
            f"- profile source: `{handler.normalize_path_for_display(handler.get_circus_runtime_root())}/TheFarm/roles/developer.md`",
            content,
        )
        self.assertIn("## Shared Context", content)
        self.assertIn(
            f"- architecture handoff: `{temp_dir.replace('\\', '/')}/issue-3/shared/architecture-handoff.md`",
            content,
        )
        self.assertIn(
            f"- running notes: `{temp_dir.replace('\\', '/')}/issue-3/shared/running-notes.md`",
            content,
        )
        self.assertIn(
            f"- decision log: `{temp_dir.replace('\\', '/')}/issue-3/shared/decision-log.md`",
            content,
        )
        self.assertIn("- generated-by: `Handler`", content)
        self.assertNotIn("role/prompt", content)
        self.assertNotIn("\\", content)
        self.assertNotIn("docs\\doctrine.md", content)
        self.assertNotIn("docs\\operations-status.md", content)

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
