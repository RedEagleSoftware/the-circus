import json
import os
import tempfile
import unittest

from Handler import metrics


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2)
        file_handle.write("\n")


class OrganizationalMetricsTests(unittest.TestCase):
    def test_generate_organizational_metrics_aggregates_status_and_review_data(self):
        with tempfile.TemporaryDirectory() as runtime_root:
            base_run_root = os.path.join(runtime_root, "Watchtower", "runs", "owner-repo", "issue-92")

            developer_run = os.path.join(base_run_root, "run-001-developer")
            reviewer_run = os.path.join(base_run_root, "run-002-reviewer")
            followup_developer_run = os.path.join(base_run_root, "run-003-developer")

            _write_json(
                os.path.join(developer_run, "status.json"),
                {
                    "repository": "owner/repo",
                    "item_type": "issue",
                    "item_number": 92,
                    "run_dir": developer_run,
                    "mode": "developer",
                    "state_label": "state:ready-for-dev",
                    "outcome": "completed",
                    "success": True,
                    "exit_code": 0,
                    "stop_reason": "none",
                    "recovery_decision": "safe_resume",
                    "recovery_reason": "workspace lifecycle is planned",
                    "recovery_non_destructive": True,
                    "dependency_resolution": {
                        "status": "resolved",
                        "diagnostic": "dependency chain clear",
                    },
                    "implementation_planner": {
                        "outcome": "READY",
                        "outcome_valid": True,
                    },
                    "recommendation_traceability": {
                        "available": True,
                    },
                    "accepted_decision_traceability": {
                        "status": "available",
                        "generated_issue_numbers": [201, 202],
                    },
                    "human_decision_ledger_v1": {
                        "stale_check": {
                            "status": "fresh",
                        }
                    },
                    "workflow_classification": {
                        "diagnostics": ["classification complete"],
                    },
                },
            )

            _write_json(
                os.path.join(reviewer_run, "status.json"),
                {
                    "repository": "owner/repo",
                    "item_type": "issue",
                    "item_number": 92,
                    "run_dir": reviewer_run,
                    "mode": "reviewer",
                    "state_label": "state:in-review",
                    "outcome": "completed",
                    "success": False,
                    "exit_code": 1,
                    "stop_reason": "changes requested",
                    "recovery_decision": "dependency_resume_blocked",
                    "recovery_reason": "declared dependencies are unresolved",
                    "recovery_non_destructive": True,
                    "dependency_resolution": {
                        "status": "blocked",
                        "diagnostic": "dependency issue #90 still open",
                    },
                    "implementation_planner": {
                        "outcome": "BLOCKED",
                        "outcome_valid": True,
                    },
                    "recommendation_traceability": {
                        "available": False,
                    },
                    "accepted_decision_traceability": {
                        "status": "reference_mismatch",
                        "diagnostic": "roadmap reference mismatch",
                        "generated_issue_numbers": [],
                    },
                    "human_decision_ledger_v1": {
                        "diagnostic": "decision context missing",
                        "stale_check": {
                            "status": "stale",
                        },
                    },
                    "lifecycle_diagnostics": {
                        "ambiguous": True,
                        "reasons": ["multiple candidate workspaces"],
                    },
                },
            )
            with open(os.path.join(reviewer_run, "review-result.md"), "w", encoding="utf-8") as file_handle:
                file_handle.write("Outcome: CHANGES_REQUESTED\n\nNeeds updates.\n")

            _write_json(
                os.path.join(followup_developer_run, "status.json"),
                {
                    "repository": "owner/repo",
                    "item_type": "issue",
                    "item_number": 92,
                    "run_dir": followup_developer_run,
                    "mode": "developer",
                    "state_label": "state:ready-for-dev",
                    "outcome": "completed",
                    "success": True,
                    "exit_code": 0,
                },
            )

            output_dir = os.path.join(runtime_root, "custom-output")
            generation = metrics.generate_organizational_metrics(
                repo="owner/repo",
                output_dir=output_dir,
                runtime_root=runtime_root,
                generated_at="2026-07-09T07:00:00",
            )

            report = generation["report"]
            self.assertEqual(report["schema_version"], "1.0")
            self.assertEqual(report["generated_at"], "2026-07-09T07:00:00")
            self.assertEqual(report["sources"]["status_files_discovered"], 3)
            self.assertEqual(report["sources"]["status_files_included"], 3)

            self.assertEqual(report["run_outcomes"]["mode"]["developer"], 2)
            self.assertEqual(report["run_outcomes"]["mode"]["reviewer"], 1)
            self.assertEqual(report["run_outcomes"]["success"]["true"], 2)
            self.assertEqual(report["run_outcomes"]["success"]["false"], 1)

            self.assertEqual(report["blockers"]["counts"]["dependency_status:blocked"], 1)
            self.assertEqual(report["blockers"]["counts"]["lifecycle_ambiguous"], 1)

            self.assertEqual(report["recovery_events"]["recovery_decision"]["safe_resume"], 1)
            self.assertEqual(report["recovery_events"]["recovery_decision"]["dependency_resume_blocked"], 1)

            self.assertEqual(report["review_churn"]["review_result_outcomes"]["CHANGES_REQUESTED"], 1)
            self.assertEqual(report["review_churn"]["developer_after_review_cycles"], 1)

            self.assertEqual(report["implementation_plan_churn"]["planner_outcome"]["READY"], 1)
            self.assertEqual(report["implementation_plan_churn"]["planner_outcome"]["BLOCKED"], 1)
            self.assertEqual(report["traceability"]["accepted_decision_status"]["reference_mismatch"], 1)
            self.assertEqual(report["traceability"]["generated_issue_availability"]["true"], 1)

            self.assertFalse(report["guardrails"]["control_signals_enabled"])

            self.assertTrue(os.path.isfile(generation["json_path"]))
            self.assertTrue(os.path.isfile(generation["markdown_path"]))

    def test_generate_organizational_metrics_reports_malformed_partial_and_skipped_data(self):
        with tempfile.TemporaryDirectory() as runtime_root:
            target_repo_run = os.path.join(runtime_root, "Watchtower", "runs", "owner-repo", "issue-93", "run-001-developer")
            other_repo_run = os.path.join(runtime_root, "Watchtower", "runs", "other-repo", "issue-7", "run-001-developer")
            malformed_run = os.path.join(runtime_root, "Watchtower", "runs", "owner-repo", "issue-93", "run-002-reviewer")

            _write_json(
                os.path.join(target_repo_run, "status.json"),
                {
                    "repository": "owner/repo",
                    "item_type": "issue",
                    "item_number": 93,
                    "run_dir": target_repo_run,
                    "mode": "developer",
                    "state_label": "state:ready-for-dev",
                    "success": True,
                },
            )
            _write_json(
                os.path.join(other_repo_run, "status.json"),
                {
                    "repository": "other/repo",
                    "item_type": "issue",
                    "item_number": 7,
                    "run_dir": other_repo_run,
                    "mode": "developer",
                    "state_label": "state:ready-for-dev",
                    "outcome": "completed",
                    "success": True,
                },
            )

            os.makedirs(malformed_run, exist_ok=True)
            with open(os.path.join(malformed_run, "status.json"), "w", encoding="utf-8") as file_handle:
                file_handle.write("{ this is not valid json }\n")

            generation = metrics.generate_organizational_metrics(
                repo="owner/repo",
                runtime_root=runtime_root,
                generated_at="2026-07-09T07:05:00",
            )
            report = generation["report"]

            self.assertEqual(report["sources"]["status_files_discovered"], 3)
            self.assertEqual(report["sources"]["status_files_included"], 1)
            self.assertEqual(report["data_quality"]["malformed_status_files"], 1)
            self.assertEqual(report["data_quality"]["skipped_files"], 1)
            self.assertEqual(report["data_quality"]["partial_records"], 1)
            self.assertEqual(report["data_quality"]["missing_fields"]["outcome"], 1)

            self.assertEqual(report["run_outcomes"]["outcome"]["unknown"], 1)
            self.assertFalse(report["guardrails"]["control_signals_enabled"])


if __name__ == "__main__":
    unittest.main()
