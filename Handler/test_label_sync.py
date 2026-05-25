import json
import unittest
from unittest.mock import patch

import Handler.label_sync as label_sync


class LabelSyncTests(unittest.TestCase):
    def test_sync_creates_missing_labels_and_targets_explicit_repo(self):
        commands = []

        def fake_run(cmd):
            commands.append(cmd)
            if cmd[:3] == ["gh", "label", "list"]:
                existing = [{"name": "state:ready-for-dev", "color": "1d76db", "description": "Ready for implementation by developer agent."}]
                return 0, json.dumps(existing), ""

            if cmd[:3] == ["gh", "label", "create"]:
                return 0, "", ""

            return 0, "", ""

        result = label_sync.sync_required_labels("owner/repo", run_command=fake_run)

        self.assertTrue(result)
        self.assertTrue(all("--repo" in command and "owner/repo" in command for command in commands))
        create_commands = [command for command in commands if command[:3] == ["gh", "label", "create"]]
        self.assertGreater(len(create_commands), 0)

    def test_sync_updates_mismatched_labels(self):
        commands = []

        def fake_run(cmd):
            commands.append(cmd)
            if cmd[:3] == ["gh", "label", "list"]:
                existing = [
                    {
                        "name": "state:ready-for-review",
                        "color": "ffffff",
                        "description": "wrong",
                    }
                ]
                return 0, json.dumps(existing), ""

            if cmd[:3] == ["gh", "label", "create"]:
                return 0, "", ""

            if cmd[:3] == ["gh", "label", "edit"]:
                return 0, "", ""

            return 0, "", ""

        result = label_sync.sync_required_labels("owner/repo", run_command=fake_run)

        self.assertTrue(result)
        edit_commands = [command for command in commands if command[:3] == ["gh", "label", "edit"]]
        self.assertEqual(len(edit_commands), 1)
        self.assertEqual(edit_commands[0][3], "state:ready-for-review")

    def test_sync_does_not_delete_unknown_labels(self):
        commands = []

        def fake_run(cmd):
            commands.append(cmd)
            if cmd[:3] == ["gh", "label", "list"]:
                existing = [
                    {
                        "name": "custom:do-not-touch",
                        "color": "cccccc",
                        "description": "custom",
                    }
                ]
                return 0, json.dumps(existing), ""

            if cmd[:3] == ["gh", "label", "create"]:
                return 0, "", ""

            return 0, "", ""

        with patch("builtins.print") as mock_print:
            result = label_sync.sync_required_labels("owner/repo", run_command=fake_run)

        self.assertTrue(result)
        delete_commands = [command for command in commands if command[:3] == ["gh", "label", "delete"]]
        self.assertEqual(delete_commands, [])
        printed_lines = [call.args[0] for call in mock_print.call_args_list]
        self.assertTrue(any("Unknown labels were not modified" in line for line in printed_lines))


if __name__ == "__main__":
    unittest.main()
