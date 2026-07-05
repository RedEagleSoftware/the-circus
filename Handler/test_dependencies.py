import unittest
from unittest.mock import Mock

from Handler import dependencies


class DependencyParsingTests(unittest.TestCase):
    def test_parse_declared_dependencies_reads_issue_refs_and_urls(self):
        body = """
## Circus Dependencies
- [ ] #12
- [ ] https://github.com/OtherOrg/OtherRepo/issues/34
- [x] https://github.com/OtherOrg/OtherRepo/pull/56

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
                },
                {
                    "type": "issue",
                    "repo": "OtherOrg/OtherRepo",
                    "number": 34,
                    "url": "https://github.com/OtherOrg/OtherRepo/issues/34",
                },
                {
                    "type": "pull_request",
                    "repo": "OtherOrg/OtherRepo",
                    "number": 56,
                    "url": "https://github.com/OtherOrg/OtherRepo/pull/56",
                },
            ],
        )

    def test_evaluate_dependencies_blocks_dispatchable_dependency(self):
        body = """
## Circus Dependencies
- [ ] #99
"""

        get_item_fn = Mock(
            return_value=(
                {
                    "number": 99,
                    "title": "Needs implementation",
                    "state": "OPEN",
                    "closed": False,
                    "labels": [{"name": "state:ready-for-dev"}],
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


if __name__ == "__main__":
    unittest.main()