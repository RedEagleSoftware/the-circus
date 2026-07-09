# Changelog

This changelog tracks notable completed work by GitHub issue.

- Entries are organized as `Issue #<number> - <issue title>`.
- Changelog updates should be included in the same PR that implements the issue.
- This file is for issue-aligned change tracking, not release/version management.

## Entry Template

### Issue #<number> - <issue title>

- [concise user-visible or workflow-significant change]
- [optional second concise change]

### Issue #91 - Ensure implementation planner decision artifacts preserve approval traceability

- Updated planner-result parsing so generated issue transition targets are consistently propagated into `human_decision_ledger_v1` defaults, including markdown `### Generated Issues` compact bullets such as `- #201 — state:ready-for-dev`.
- Expanded ledger normalization compatibility so nested `human_decision_v1` payloads can supply canonical flat decision fields without breaking existing approval-gate contracts.
- Aligned approval-gate regression coverage for markdown-section parsing so validation fails at ledger availability before downstream transition checks when no explicit human decision is provided.

### Issue #89 - [Generated] Complete accepted-decision traceability artifacts

- Added a versioned `accepted_decision_traceability` snapshot to Handler run status artifacts, with explicit diagnostics for missing, ambiguous, and reference-mismatch decision links.
- Updated run result rendering and tests so decision provenance captures accepted recommendation, roadmap reference, planner outcome/artifact, generated issue mappings, and outcome-state consistency signals.

### Issue #64 - Planner Outcome Model and Architecture Escalation Workflow

- Documented the `READY`, `BLOCKED`, and `ESCALATION_REQUIRED` Implementation Planner outcome model.
- Updated roadmap, capability tree, README, and role guidance so planner escalation is distinct from blocked planning and generated issues are created only for `READY`.

### Issue #51 - Design Worktree and Branch Lifecycle Management

- Documented the accepted worktree and branch lifecycle state model, recovery workflow, and cleanup safety boundary.
- Updated roadmap, capability tree, operations status, and worktree isolation references to align follow-on implementation planning with the approved lifecycle design.

### Issue #39 - Document Implementation Planner Role and Workflow States

- Documented Implementation Planner workflow states in doctrine guidance, including ownership and review transition expectations.

### Issue #30 - Design Git Worktree-Based Issue Workspaces

- Added worktree-isolation architecture documentation that defines per-issue Git worktrees, branch ownership rules, and lifecycle expectations for concurrent agent workflows.
- Updated roadmap and operations documentation to track Issue #30 planning/status and align follow-on workflow implementation with the approved design.

### Issue #19 - Reassess Circus strategic direction after Systems Architect maturation

- Updated strategic roadmap and capability-tree documentation to keep `Self Hosting` as the active frontier before `Provider Routing` and `Skills`.
- Reconciled operations status with the matured Systems Architect and Roadmap Updater workflows, including the next self-hosting reliability sequence.

### Issue #20 - Add Roadmap Updater workflow for approved strategic recommendations

- Added Roadmap Updater role and workflow to synchronize documentation and knowledge artifacts based on approved strategic recommendations.
- Implemented `state:ready-for-roadmap-update` dispatch to Codex Roadmap Updater, enabling documentation-only PR creation and issue-discussion grounding.
- Added workflow state transition logic to advance from successful roadmap update to `state:ready-for-review`.
- Integrated Roadmap Updater into the handler's branch and PR management plumbing.

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
