import unittest
import tempfile
import os
from unittest.mock import patch

import Handler.handler as handler


class HandlerObservabilityTests(unittest.TestCase):
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

    def test_poll_cycle_observability_when_idle(self):
        with patch.object(handler, "REPO", "owner/repo"):
            with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
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
                "C:/target/repo",
            )

        self.assertIn("## Assignment", markdown)
        self.assertIn("## Source of Truth", markdown)
        self.assertIn("## Operating Instructions", markdown)
        self.assertIn("## References", markdown)
        self.assertIn("- repository: `owner/repo`", markdown)
        self.assertIn("- target repo path: `C:/target/repo`", markdown)
        self.assertIn("- item type: `issue`", markdown)
        self.assertIn("- item number: `3`", markdown)
        self.assertIn("- workflow state: `state:ready-for-dev`", markdown)
        self.assertIn("- target agent: `junie`", markdown)
        self.assertIn("- mode: `developer`", markdown)
        self.assertIn("- model: `gpt-5.3-codex`", markdown)
        self.assertIn("- effort: `Medium`", markdown)
        self.assertIn("- generated-by: `Generated by Handler`", markdown)
        self.assertIn("GitHub issue/PR metadata is the source of truth", markdown)
        self.assertIn("If local files, git state, or launch metadata conflict with GitHub metadata", markdown)
        self.assertIn("- role/prompt file: `TheFarm\\roles\\developer.md`", markdown)
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

        self.assertIn("## References", markdown)
        self.assertIn("- no role reference configured", markdown)
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
                    with patch.object(handler, "TARGET_REPO_PATH", "C:/target/repo"):
                        brief_path = handler.write_launch_brief(
                            item,
                            "state:ready-for-dev",
                            config,
                            os.path.normpath(os.path.join("TheFarm", "roles", "developer.md")),
                        )

            self.assertTrue(os.path.isfile(brief_path))
            with open(brief_path, "r", encoding="utf-8") as generated_file:
                content = generated_file.read()

        self.assertIn("# Launch Brief", content)
        self.assertIn("## Assignment", content)
        self.assertIn("- repository: `owner/repo`", content)
        self.assertIn("- target repo path: `C:/target/repo`", content)
        self.assertIn("- role/prompt file: `TheFarm\\roles\\developer.md`", content)
        self.assertNotIn("docs\\doctrine.md", content)
        self.assertNotIn("docs\\operations-status.md", content)

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
