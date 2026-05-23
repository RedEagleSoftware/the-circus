import unittest
from unittest.mock import patch

import Handler.handler as handler


class HandlerObservabilityTests(unittest.TestCase):
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
        mock_run.assert_called_once_with("gh issue list --repo owner/repo --json number,labels,title")

    def test_get_labeled_items_filters_supported_labels_and_reports_unsupported_states(self):
        issues_payload = (
            "["
            "{\"number\": 11, \"title\": \"ready\", \"labels\": [{\"name\": \"state:review-requested\"}]},"
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
