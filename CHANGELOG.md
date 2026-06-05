# Changelog

This changelog tracks notable completed work by GitHub issue.

- Entries are organized as `Issue #<number> - <issue title>`.
- Changelog updates should be included in the same PR that implements the issue.
- This file is for issue-aligned change tracking, not release/version management.

## Entry Template

### Issue #<number> - <issue title>

- [concise user-visible or workflow-significant change]
- [optional second concise change]

### Issue #1 - Add target repository initialization command (python main.py --init)

- Added the initial orchestrator implementation and foundational role/doctrine structure.
- Introduced core project documentation, including README and license scaffolding.

### Issue #7 - Add Systems Architect workflow routing

- Added support documentation for `state:ready-for-system-architecture` to describe strategic Systems Architect routing behavior.
- Documented that successful Systems Architect runs transition directly to `state:ready-for-human-review` without auto-routing to development or auto-finalizing PR workflows.