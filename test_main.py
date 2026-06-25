import os
import tempfile
import unittest
from unittest.mock import patch

import main


class MainStartupTests(unittest.TestCase):
    def test_validate_init_target_path_requires_target_repo_path(self):
        with patch.dict(os.environ, {"CIRCUS_TARGET_REPO_PATH": ""}, clear=False):
            with patch("builtins.print") as mock_print:
                target_path = main.validate_init_target_path()

        self.assertIsNone(target_path)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("CIRCUS_TARGET_REPO_PATH is required" in line for line in printed_lines))

    def test_validate_init_target_path_requires_existing_directory(self):
        with patch.dict(os.environ, {"CIRCUS_TARGET_REPO_PATH": "C:\\does-not-exist"}, clear=False):
            with patch("builtins.print") as mock_print:
                target_path = main.validate_init_target_path()

        self.assertIsNone(target_path)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("does not exist" in line for line in printed_lines))

    def test_validate_init_target_path_requires_directory(self):
        with tempfile.NamedTemporaryFile() as temp_file:
            with patch.dict(os.environ, {"CIRCUS_TARGET_REPO_PATH": temp_file.name}, clear=False):
                with patch("builtins.print") as mock_print:
                    target_path = main.validate_init_target_path()

        self.assertIsNone(target_path)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("is not a directory" in line for line in printed_lines))

    def test_validate_startup_config_requires_repo(self):
        with patch.dict(os.environ, {"CIRCUS_REPO": "", "CIRCUS_TARGET_REPO_PATH": ""}, clear=False):
            with patch("builtins.print") as mock_print:
                config = main.validate_startup_config()

        self.assertIsNone(config)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("CIRCUS_REPO is required" in line for line in printed_lines))

    def test_validate_startup_config_requires_target_repo_path(self):
        with patch.dict(os.environ, {"CIRCUS_REPO": "owner/repo", "CIRCUS_TARGET_REPO_PATH": ""}, clear=False):
            with patch("builtins.print") as mock_print:
                config = main.validate_startup_config()

        self.assertIsNone(config)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("CIRCUS_TARGET_REPO_PATH is required" in line for line in printed_lines))

    def test_validate_startup_config_requires_existing_directory(self):
        with patch.dict(
            os.environ,
            {"CIRCUS_REPO": "owner/repo", "CIRCUS_TARGET_REPO_PATH": "C:\\does-not-exist"},
            clear=False,
        ):
            with patch("builtins.print") as mock_print:
                config = main.validate_startup_config()

        self.assertIsNone(config)
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("does not exist" in line for line in printed_lines))

    def test_validate_startup_config_returns_repo_and_target_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                os.environ,
                {"CIRCUS_REPO": "owner/repo", "CIRCUS_TARGET_REPO_PATH": temp_dir},
                clear=False,
            ):
                config = main.validate_startup_config()

        self.assertEqual(config, ("owner/repo", temp_dir))

    def test_main_sync_labels_runs_manual_sync_and_skips_polling(self):
        with patch.object(main, "run_label_sync", return_value=True) as mock_sync:
            with patch.object(main, "launch_handler_polling") as mock_poll:
                with patch.dict(os.environ, {"CIRCUS_REPO": "owner/repo"}, clear=False):
                    main.main(["--sync-labels"])

        mock_sync.assert_called_once_with("owner/repo")
        mock_poll.assert_not_called()

    def test_main_approve_implementation_plan_runs_approval_and_skips_polling(self):
        with patch.object(main, "run_implementation_plan_approval", return_value=True) as mock_approve:
            with patch.object(main, "launch_handler_polling") as mock_poll:
                with patch.dict(os.environ, {"CIRCUS_REPO": "owner/repo"}, clear=False):
                    main.main(["--approve-implementation-plan", "143"])

        mock_approve.assert_called_once_with("owner/repo", 143)
        mock_poll.assert_not_called()

    def test_main_approve_implementation_plan_requires_circus_repo(self):
        with patch.object(main, "run_implementation_plan_approval") as mock_approve:
            with patch.object(main, "launch_handler_polling") as mock_poll:
                with patch.dict(os.environ, {"CIRCUS_REPO": ""}, clear=False):
                    main.main(["--approve-implementation-plan", "143"])

        mock_approve.assert_not_called()
        mock_poll.assert_not_called()

    def test_main_default_path_does_not_run_label_sync(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(main, "run_label_sync") as mock_sync:
                with patch.object(main, "launch_handler_polling") as mock_poll:
                    with patch.dict(
                        os.environ,
                        {"CIRCUS_REPO": "owner/repo", "CIRCUS_TARGET_REPO_PATH": temp_dir},
                        clear=False,
                    ):
                        main.main([])

        mock_sync.assert_not_called()
        mock_poll.assert_called_once_with("owner/repo", temp_dir)

    def test_main_init_runs_init_and_skips_polling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(main, "run_target_repo_init", return_value=True) as mock_init:
                with patch.object(main, "run_label_sync") as mock_sync:
                    with patch.object(main, "launch_handler_polling") as mock_poll:
                        with patch.dict(
                            os.environ,
                            {
                                "CIRCUS_REPO": "owner/repo",
                                "CIRCUS_TARGET_REPO_PATH": temp_dir,
                            },
                            clear=False,
                        ):
                            main.main(["--init"])

        mock_init.assert_called_once_with(temp_dir)
        mock_sync.assert_not_called()
        mock_poll.assert_not_called()

    def test_main_init_does_not_require_circus_repo(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(main, "run_target_repo_init", return_value=True) as mock_init:
                with patch.dict(
                    os.environ,
                    {
                        "CIRCUS_REPO": "",
                        "CIRCUS_TARGET_REPO_PATH": temp_dir,
                    },
                    clear=False,
                ):
                    main.main(["--init"])

        mock_init.assert_called_once_with(temp_dir)

    def test_main_init_creates_all_scaffold_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"CIRCUS_TARGET_REPO_PATH": temp_dir}, clear=False):
                main.main(["--init"])

            for relative_path, _template in main.INIT_SCAFFOLD_FILES:
                absolute_path = os.path.join(temp_dir, relative_path)
                self.assertTrue(os.path.isfile(absolute_path), f"Expected scaffold file: {relative_path}")

    def test_main_init_skips_existing_files_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            existing_relative_path = "AGENTS.md"
            existing_absolute_path = os.path.join(temp_dir, existing_relative_path)
            os.makedirs(os.path.dirname(existing_absolute_path), exist_ok=True)
            with open(existing_absolute_path, "w", encoding="utf-8") as file_handle:
                file_handle.write("custom content\n")

            with patch.dict(os.environ, {"CIRCUS_TARGET_REPO_PATH": temp_dir}, clear=False):
                with patch("builtins.print") as mock_print:
                    main.main(["--init"])

            with open(existing_absolute_path, "r", encoding="utf-8") as file_handle:
                self.assertEqual(file_handle.read(), "custom content\n")

            printed_lines = [call.args[0] for call in mock_print.call_args_list]
            self.assertTrue(any("skipped: AGENTS.md" in line for line in printed_lines))

    def test_main_init_second_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"CIRCUS_TARGET_REPO_PATH": temp_dir}, clear=False):
                main.main(["--init"])
                with patch("builtins.print") as mock_print:
                    main.main(["--init"])

        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Summary: created 0" in line for line in printed_lines))


if __name__ == "__main__":
    unittest.main()