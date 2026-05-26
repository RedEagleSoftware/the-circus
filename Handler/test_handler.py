import unittest
import tempfile
import os
from unittest.mock import Mock, patch

import Handler.handler as handler


class HandlerObservabilityTests(unittest.TestCase):
    def setUp(self):
        handler.EXECUTABLE_PATHS.clear()

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

        self.assertFalse(dispatched)
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
            with patch.object(handler, "write_launch_brief", side_effect=OSError("disk full")):
                with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                    with patch.object(handler, "add_comment") as mock_add_comment:
                        with patch.object(handler, "launch_agent") as mock_launch_agent:
                            with patch("builtins.print") as mock_print:
                                dispatched = handler.process_one_item([item])

        self.assertFalse(dispatched)
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
            with patch.object(handler, "write_launch_brief", return_value="Watchtower/runs/issue-23/run-001-developer/launch-brief.md"):
                with patch.object(handler, "launch_agent", return_value=True):
                    with patch.object(handler, "unlock_item") as mock_unlock:
                        with patch.object(handler, "add_comment") as mock_add_comment:
                            dispatched = handler.process_one_item([item])

        self.assertTrue(dispatched)
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
                with patch.object(handler, "write_launch_brief", return_value=launch_brief_path):
                    with patch.object(handler.subprocess, "run", side_effect=FileNotFoundError("junie not found")):
                        with patch.object(handler, "unlock_item", return_value=True) as mock_unlock:
                            with patch.object(handler, "add_comment") as mock_add_comment:
                                with patch("builtins.print") as mock_print:
                                    dispatched = handler.process_one_item([item])

        self.assertFalse(dispatched)
        mock_unlock.assert_called_once_with(item)
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("failed to start Junie before execution began", item["comment"])
        self.assertIn("The lock label `state:agent-in-progress` was released", item["comment"])
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Junie failed to launch before execution started" in line for line in printed_lines))

    def test_poll_cycle_observability_when_idle(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                with patch.object(handler, "validate_required_executables", return_value={"gh": "gh", "git": "git", "junie": "junie", "codex": "codex"}):
                    with patch.object(handler, "validate_target_repo_workspace", return_value=True):
                        with patch.object(handler, "verify_github_repo_access", return_value=True):
                            with patch.object(handler, "get_labeled_items", return_value=([], [], [], True)):
                                with patch.object(handler, "process_one_item", return_value=False):
                                    with patch("time.sleep", side_effect=SystemExit):
                                        with patch("builtins.print") as mock_print:
                                            with self.assertRaises(SystemExit):
                                                handler.poll()

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Poll] Starting cycle #1..." in line for line in printed_lines))
        self.assertTrue(any("[Poll] Retrieved issues=0, prs=0, candidates=0." in line for line in printed_lines))
        self.assertTrue(any("[Poll] No candidate items matched workflow labels this cycle." in line for line in printed_lines))

    def test_get_candidates_fetches_without_label_filter(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "run_command", return_value="[]") as mock_run:
                items, ok = handler.get_candidates("issue", "issue list")

        self.assertEqual(items, [])
        self.assertTrue(ok)
        mock_run.assert_called_once_with("gh issue list --repo owner/repo --json number,labels,title,url")

    def test_build_thin_prompt_includes_target_repo_and_launch_brief_path(self):
        item = {"type": "issue", "number": 3, "title": "Implement launch brief", "url": "https://github.com/owner/repo/issues/3"}

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            prompt = handler.build_thin_prompt(
                item,
                "state:ready-for-dev",
                "developer",
                os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                "Watchtower/runs/issue-3/run-001-developer/launch-brief.md",
            )

        self.assertIn("- target repo path: C:/target/repo", prompt)
        self.assertIn("- agent profile source path: TheFarm/roles/developer.md", prompt)
        self.assertIn(
            "- launch brief artifact path: Watchtower/runs/issue-3/run-001-developer/launch-brief.md",
            prompt,
        )

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

        self.assertTrue(launched)
        mock_add_comment.assert_called_once_with(item)
        self.assertIn("exited with non-zero status (7)", item["comment"])
        self.assertIn("lock label `state:agent-in-progress` remains", item["comment"])
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("[Dispatch] Junie exit code: 7" in line for line in printed_lines))
        self.assertTrue(any("human inspection is required" in line for line in printed_lines))

    def test_build_codex_architect_task_text_includes_handoff_and_comment_requirements(self):
        task_text = handler.build_codex_architect_task_text("C:/abs/Watchtower/runs/issue-9/run-001-architect/launch-brief.md")

        self.assertIn(
            "Read the launch brief at C:/abs/Watchtower/runs/issue-9/run-001-architect/launch-brief.md",
            task_text,
        )
        self.assertIn("execute the architect workflow", task_text)
        self.assertIn("Produce or update the architecture handoff artifact", task_text)
        self.assertIn("leave a GitHub comment summarizing the handoff or blocker", task_text)

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

        with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
            with patch.object(handler.os.path, "abspath", return_value=absolute_launch_brief_path):
                with patch.object(handler.subprocess, "run", return_value=Mock(returncode=0)) as mock_subprocess_run:
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

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any(f"[Dispatch] Launch brief display path: {launch_brief_path}" in line for line in printed_lines))
        self.assertTrue(
            any(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}" in line for line in printed_lines)
        )
        self.assertTrue(any("[Dispatch] Codex target repo path: C:/target/repo" in line for line in printed_lines))
        self.assertTrue(any("Codex handoff path: passing short positional prompt argument" in line for line in printed_lines))
        self.assertTrue(any("[Dispatch] Codex execution cwd: C:/target/repo" in line for line in printed_lines))
        self.assertTrue(any("[Dispatch] Codex exit code: 0" in line for line in printed_lines))

        executing_lines = [line for line in printed_lines if line.startswith("[Dispatch] Executing: ")]
        self.assertEqual(len(executing_lines), 1)
        self.assertIn("codex exec --model gpt-5.3-codex --cd C:/target/repo", executing_lines[0])
        self.assertIn(f"Read the launch brief at {absolute_launch_brief_path}", executing_lines[0])

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

        with patch.object(handler, "REPO", "owner/repo"):
            markdown = handler.build_launch_brief_markdown(
                item,
                "state:ready-for-dev",
                config,
                os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                "2026-05-25T09:06:00",
                "C:\\target\\repo",
                {
                    "architecture_handoff": "Watchtower/runs/issue-3/shared/architecture-handoff.md",
                    "running_notes": "Watchtower/runs/issue-3/shared/running-notes.md",
                    "decision_log": "Watchtower/runs/issue-3/shared/decision-log.md",
                },
            )

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
        self.assertIn("- architecture handoff: `Watchtower/runs/issue-3/shared/architecture-handoff.md`", markdown)
        self.assertIn("- running notes: `Watchtower/runs/issue-3/shared/running-notes.md`", markdown)
        self.assertIn("- decision log: `Watchtower/runs/issue-3/shared/decision-log.md`", markdown)
        self.assertIn("GitHub issue/PR metadata is the source of truth", markdown)
        self.assertIn("If local files, git state, or launch metadata conflict with GitHub metadata", markdown)
        self.assertIn("- profile source: `TheFarm/roles/developer.md`", markdown)
        self.assertNotIn("role/prompt", markdown)
        self.assertNotIn("\\", markdown)
        self.assertNotIn("docs\\doctrine.md", markdown)
        self.assertNotIn("docs\\operations-status.md", markdown)

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
        self.assertIn("## Assignment", content)
        self.assertIn("- repository: `owner/repo`", content)
        self.assertIn("- target repo path: `C:/target/repo`", content)
        self.assertIn("## Agent Profile", content)
        self.assertIn("- profile source: `TheFarm/roles/developer.md`", content)
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
