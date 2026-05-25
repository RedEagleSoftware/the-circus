import os
import tempfile
import unittest
from unittest.mock import patch

import main


class MainStartupTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()