# Role Selection Guide

Use this guide to choose the right role for the type of work you are doing.

## Systems Architect

Use the [Systems Architect](../TheFarm/roles/systems-architect.md) for:

- strategic planning and long-term architecture direction
- capability evolution and capability-tree stewardship
- cross-issue sequencing and dependency planning
- identifying cross-cutting concerns across workflows and repositories

Systems Architect strategic recommendations should identify the repository under review and cite or name discovered strategic context where available (for example roadmap, capability-tree, strategy, or prior Systems Architect artifacts).

When repository strategy context is incomplete, recommendations should explicitly note the gap and distinguish repository-grounded direction from general architectural judgment.

The Systems Architect focuses on what the system should become over time.

When dispatched via workflow labels, Systems Architect recommendations should be published as a structured GitHub issue comment and handed to humans for decision on follow-up state.

## Feature Architect

Use the [Architect Agent](../TheFarm/roles/architect.md) as the Feature Architect for:

- translating a specific GitHub issue into an implementation-ready handoff
- clarifying issue-level constraints and acceptance expectations
- giving developers concrete implementation direction for the current workflow item

The Feature Architect focuses on how to implement one issue safely and clearly.

If the issue is too broad, too risky, blocked, under-specified, or actually requires implementation planning first, the Feature Architect should leave a structured routing recommendation for human/Handler action rather than changing workflow labels directly.

## Reviewer

Use the [Reviewer](../TheFarm/roles/reviewer.md) for:

- validating implementation correctness and test coverage
- checking maintainability and architectural consistency
- verifying implementation scope matches the issue and architecture handoff

The Reviewer focuses on implementation quality and workflow safety.

## Architect Review

Use Architect Review for:

- post-review architectural approval of a PR
- confirming the implementation still aligns with the handoff and broader architecture
- deciding whether architectural tradeoffs remain acceptable before human review

Architect Review is a workflow step; it validates architecture after implementation and review.

## Roadmap Updater

Use the [Roadmap Updater](../TheFarm/roles/roadmap-updater.md) for:

- synchronizing documentation and knowledge artifacts after strategic decisions
- updating roadmaps and capability trees based on approved recommendations
- ensuring documentation reflects current architectural intent

The Roadmap Updater creates documentation PRs based on human-approved Systems Architect recommendations.

Ownership boundary for this workflow:

- Roadmap Updater owns documentation updates, commits, branch push, PR creation, and the issue summary comment linking to the PR.
- Handler owns orchestration, post-run PR validation, run-status recording, and workflow `state:*` label transitions.
- Developer workflow PR finalization remains Handler-owned unless changed by a dedicated workflow-contract issue.

## Implementation Planner

Use the [Implementation Planner](../TheFarm/roles/implementation-planner.md) for:

- declaring whether one approved and documented strategic recommendation is `READY`, `BLOCKED`, or `ESCALATION_REQUIRED`
- converting approved strategic recommendations and merged roadmap docs into executable implementation plans
- decomposing accepted capabilities into generated GitHub issues
- proposing initial issue ordering
- declaring conservative issue dependencies where ordering matters
- creating generated issues in a non-dispatch review state when the outcome is `READY`
- leaving a structured implementation plan, blocker, or architecture escalation result for human approval

The Implementation Planner focuses on turning accepted strategy into review-gated backlog when safe, not on defining strategy or implementing code.

Planner outcome boundaries:

- `READY` produces a reviewable implementation plan and generated issues in a non-dispatch state.
- `BLOCKED` identifies missing, stale, inaccessible, unsafe, or contradictory planning prerequisites without requesting a new systems architecture decision.
- `ESCALATION_REQUIRED` identifies systems-level decisions that belong to Systems Architect and recommends `state:systems-architecture-changes-requested`.

Ownership boundary for this workflow:

- Implementation Planner owns outcome declaration, issue decomposition for `READY`, generated issue content, proposed ordering, dependency declaration, and the plan/blocker/escalation review artifact.
- Roadmap Updater owns durable strategic documentation before planning starts.
- Handler owns dispatch eligibility, workflow label transitions, dependency blocking, automatic unblocking, and approved transitions from plan review into dispatchable workflow states.
- Feature Architect and Developer workflows remain responsible for one approved implementation issue at a time after human plan approval.

When planning would require unresolved systems-level decisions, the Implementation Planner should declare `ESCALATION_REQUIRED` and recommend `state:systems-architecture-changes-requested` instead of generating issues. When a plan needs revision without a new systems decision, it should recommend `state:implementation-planning-changes-requested`.

## Workflow Governance

Use [Workflow Governance and Routing Doctrine](workflow-governance.md) for circular planning, return paths, ownership boundaries, and advisory classification vocabulary.

Roles may recommend routing changes, blockers, decomposition, or extra review in comments and artifacts. Handler remains the workflow state authority.

## Quick Distinction

- Systems Architect: capability planning and long-term system evolution across issues.
- Roadmap Updater: synchronizing documentation with approved strategic decisions.
- Implementation Planner: generating human-reviewed implementation issue trees from accepted strategy, or blocking/escalating when planning cannot safely continue.
- Feature Architect: issue-level implementation planning and handoff creation.
- Reviewer: implementation correctness and quality validation.
- Architect Review: final architectural validation of the implementation before human approval.
