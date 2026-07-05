import unittest
from unittest.mock import Mock

from Handler import dependencies


class DependencyParsingTests(unittest.TestCase):
    def test_parse_declared_dependencies_reads_v1_yaml_metadata(self):
        body = """
## Circus Dependencies
<!-- circus:dependencies v1 -->
```yaml
resume_state: state:ready-for-architecture
blocked_by:
  - type: issue
    repo: RedEagleSoftware/the-circus
    number: 12
    satisfies_on: closed_completed
  - type: pull_request
    repo: OtherOrg/OtherRepo
    number: 56
    satisfies_on: merged
```

## Notes
- done
"""

        parsed = dependencies.parse_declared_dependencies(body, default_repo="RedEagleSoftware/the-circus")

        self.assertEqual(
            parsed,
            [
                {
                    "type": "issue",
                    "repo": "RedEagleSoftware/the-circus",
                    "number": 12,
                    "url": "https://github.com/RedEagleSoftware/the-circus/issues/12",
                    "satisfies_on": "closed_completed",
                },
                {
                    "type": "pull_request",
                    "repo": "OtherOrg/OtherRepo",
                    "number": 56,
                    "url": "https://github.com/OtherOrg/OtherRepo/pull/56",
                    "satisfies_on": "merged",
                },
            ],
        )

    def test_evaluate_dependencies_requires_closed_completed_issues(self):
        body = """
## Circus Dependencies
<!-- circus:dependencies v1 -->
```yaml
resume_state: state:ready-for-architecture
blocked_by:
  - type: issue
    repo: RedEagleSoftware/the-circus
    number: 99
    satisfies_on: closed_completed
```
"""

        get_item_fn = Mock(
            return_value=(
                {
                    "number": 99,
                    "title": "Needs implementation",
                    "state": "CLOSED",
                    "closed": True,
                    "stateReason": "COMPLETED",
                },
                True,
            )
        )

        resolution = dependencies.evaluate_dependencies(
            body,
            default_repo="RedEagleSoftware/the-circus",
            run_command_fn=Mock(),
            get_item_fn=get_item_fn,
        )

        self.assertEqual(resolution["status"], "resolved")
        self.assertFalse(resolution["unresolved"])

    def test_evaluate_dependencies_blocks_closed_not_completed_issue(self):
        body = """
## Circus Dependencies
<!-- circus:dependencies v1 -->
```yaml
resume_state: state:ready-for-architecture
blocked_by:
  - type: issue
    repo: RedEagleSoftware/the-circus
    number: 99
    satisfies_on: closed_completed
```
"""

        get_item_fn = Mock(
            return_value=(
                {
                    "number": 99,
                    "title": "Closed as not planned",
                    "state": "CLOSED",
                    "closed": True,
                    "stateReason": "NOT_PLANNED",
                },
                True,
            )
        )

        resolution = dependencies.evaluate_dependencies(
            body,
            default_repo="RedEagleSoftware/the-circus",
            run_command_fn=Mock(),
            get_item_fn=get_item_fn,
        )

        self.assertEqual(resolution["status"], "blocked")
        self.assertTrue(resolution["unresolved"])
        self.assertTrue(resolution["dependencies"][0]["blocking"])

    def test_evaluate_dependencies_requires_merged_pull_requests(self):
        body = """
## Circus Dependencies
<!-- circus:dependencies v1 -->
```yaml
resume_state: state:ready-for-architecture
blocked_by:
  - type: pull_request
    repo: RedEagleSoftware/the-circus
    number: 100
    satisfies_on: merged
```
"""

        get_item_fn = Mock(
            return_value=(
                {
                    "number": 100,
                    "title": "Review in progress",
                    "state": "OPEN",
                    "closed": False,
                    "merged": False,
                },
                True,
            )
        )

        resolution = dependencies.evaluate_dependencies(
            body,
            default_repo="RedEagleSoftware/the-circus",
            run_command_fn=Mock(),
            get_item_fn=get_item_fn,
        )

        self.assertEqual(resolution["status"], "blocked")
        self.assertTrue(resolution["dependencies"][0]["blocking"])

    def test_evaluate_dependencies_blocks_malformed_v1_metadata(self):
        body = """
## Circus Dependencies
<!-- circus:dependencies v1 -->
```yaml
blocked_by:
  - type: issue
    repo: RedEagleSoftware/the-circus
    number: 99
```
"""

        resolution = dependencies.evaluate_dependencies(
            body,
            default_repo="RedEagleSoftware/the-circus",
            run_command_fn=Mock(),
            get_item_fn=Mock(),
        )

        self.assertEqual(resolution["status"], "blocked")
        self.assertEqual(resolution["declared"], True)
        self.assertIn("metadata", resolution["diagnostic"])


if __name__ == "__main__":
    unittest.main()