# Role Selection Guide

Use this guide to choose the right role for the type of work you are doing.

## Systems Architect

Use the [Systems Architect](../TheFarm/roles/systems-architect.md) for:

- strategic planning and long-term architecture direction
- capability evolution and capability-tree stewardship
- cross-issue sequencing and dependency planning
- identifying cross-cutting concerns across workflows and repositories

The Systems Architect focuses on what the system should become over time.

When dispatched via workflow labels, Systems Architect recommendations should be published as a structured GitHub issue comment and handed to humans for decision on follow-up state.

## Feature Architect

Use the [Architect Agent](../TheFarm/roles/architect.md) as the Feature Architect for:

- translating a specific GitHub issue into an implementation-ready handoff
- clarifying issue-level constraints and acceptance expectations
- giving developers concrete implementation direction for the current workflow item

The Feature Architect focuses on how to implement one issue safely and clearly.

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

## Quick Distinction

- Systems Architect: capability planning and long-term system evolution across issues.
- Feature Architect: issue-level implementation planning and handoff creation.
- Reviewer: implementation correctness and quality validation.
- Architect Review: final architectural validation of the implementation before human approval.