# Changelog

This changelog tracks notable completed work by GitHub issue.

- Entries are organized as `Issue #<number> - <issue title>`.
- Changelog updates should be included in the same PR that implements the issue.
- This file is for issue-aligned change tracking, not release/version management.

## Entry Template

### Issue #<number> - <issue title>

- [concise user-visible or workflow-significant change]
- [optional second concise change]

### Issue #17 - Require repository-context validation for Systems Architect recommendations

- Added Systems Architect repository-context validation guidance so strategic recommendations identify reviewed repository strategy and disclose missing context.
- Updated role documentation to distinguish repository-grounded strategic recommendations from general architectural judgment.

### Issue #1 - Add target repository initialization command (python main.py --init)

- Added the initial orchestrator implementation and foundational role/doctrine structure.
- Introduced core project documentation, including README and license scaffolding.

### Issue #7 - Add Systems Architect workflow routing

- Added support documentation for `state:ready-for-systems-architecture` to describe strategic Systems Architect routing behavior.
- Documented that successful Systems Architect runs transition directly to `state:ready-for-human-review` without auto-routing to development or auto-finalizing PR workflows.

### Issue #9 - Create canonical workflow state definitions

- Added a shared workflow state constants module and aligned Handler workflow/dispatch logic to consume canonical state definitions.
- Standardized Systems Architect state routing to `state:ready-for-systems-architecture` and removed remaining singular label usage from active code/tests/docs.

### Issue #5 - Add Systems Architect role support

- Added TheFarm role index and a contributor-facing role selection guide to clarify when to use Systems Architect, Feature Architect, Reviewer, and Architect Review.
- Linked role guidance from repository entry points and roadmap docs, including explicit capability-tree stewardship and v1 workflow scope notes for Systems Architect.
