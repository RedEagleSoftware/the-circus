# Implementation Planning Architecture

Issue #37 accepted Implementation Planning as a distinct workflow role and capability.

This document records the approved Systems Architect recommendation for roadmap and implementation planning. It is not a runtime implementation specification.

## Decision

The Circus should add Implementation Planning as a separate workflow role after roadmap synchronization.

Implementation Planning converts accepted strategic intent into an executable, human-reviewed implementation plan. It owns issue decomposition, initial sequencing, dependency declaration, generated issue creation, and plan review artifacts. It does not own dispatch eligibility, workflow label transitions, dependency enforcement, or automatic unblocking.

## Workflow Position

The accepted high-level flow is:

```text
Architecture question
-> Systems Architect recommendation
-> Human approval
-> state:ready-for-roadmap-update
-> Roadmap Updater documentation PR
-> Human review / merge of roadmap docs
-> state:ready-for-implementation-planning
-> Implementation Planner
-> Draft implementation plan + generated GitHub issues + dependency metadata
-> state:ready-for-implementation-plan-review
-> Human approval
-> generated issues become dispatchable through existing workflow states
```

Implementation Planning happens after roadmap updates so the capability tree and roadmap remain the durable strategic anchor before executable backlog work is generated.

## Ownership Boundaries

Implementation Planner owns:

- decomposing one approved strategic recommendation into implementation issues
- proposing the initial execution order
- declaring conservative issue dependencies where ordering matters
- creating generated GitHub issues directly in a non-dispatch review state
- leaving a structured implementation plan comment or artifact
- preserving source traceability to the approved recommendation and roadmap update

Handler owns:

- dispatch eligibility
- planner launch and workflow routing
- workflow label transitions
- dependency blocking and automatic unblocking
- approved transitions from planning review into dispatchable workflow states

Watchtower owns observability only:

- recording planning run artifacts
- recording generated issue links
- preserving run history

GitHub issues and comments remain the human review surface and source of truth.

## Workflow States

Add planning lifecycle states:

```text
state:ready-for-implementation-planning
state:ready-for-implementation-plan-review
state:implementation-planning-changes-requested
state:planned
```

`state:ready-for-implementation-planning` is dispatchable to Implementation Planner.

`state:ready-for-implementation-plan-review` is a human review state for the source planning issue after the planner creates or proposes the implementation plan.

`state:implementation-planning-changes-requested` routes a planning issue back to Implementation Planner when the generated plan needs revision.

`state:planned` is a non-dispatch generated issue state. Generated implementation issues should not become executable until a human approves the plan and Handler or a dedicated approved transition moves them to dispatchable states such as `state:ready-for-architecture` or `state:ready-for-dev`.

Each issue should still have exactly one primary `state:*` label.

## Generated Issue Contract

Generated implementation issues should be created directly in GitHub, but initially in a non-dispatch state.

Each generated issue should include:

- source Systems Architect recommendation URL or issue comment ID
- source roadmap documentation PR or merged documentation reference
- implementation scope
- acceptance criteria
- suggested next workflow state after human approval
- plan traceability back to the parent planning issue
- optional `## Circus Dependencies` metadata when ordering matters

Dependency metadata should use the accepted dependency-blocking format:

````md
## Circus Dependencies
<!-- circus:dependencies v1 -->
```yaml
resume_state: state:ready-for-dev
blocked_by:
  - type: issue
    repo: RedEagleSoftware/the-circus
    number: 101
    satisfies_on: closed_completed
```
````

The planner should declare dependencies conservatively and only where ordering materially affects correctness.

## Implementation Plan Artifact

The planner should leave a structured GitHub issue comment or durable artifact that lists:

- generated issue links
- intended execution order
- dependency graph
- dispatch readiness
- generated issue states
- human review options
- source recommendation and roadmap references

The plan artifact should make stale plans easy to detect. If the source recommendation or roadmap docs change before approval, the issue should return to `state:implementation-planning-changes-requested` rather than silently dispatching generated work.

## First Implementation Boundary

The first implementation should build the smallest useful Implementation Planner workflow:

1. Read one approved Systems Architect recommendation and the updated roadmap docs.
2. Produce one structured implementation plan comment.
3. Create generated GitHub issues in a non-dispatch review state.
4. Include acceptance criteria and suggested next workflow state in generated issues.
5. Include `## Circus Dependencies` metadata when generated issue ordering matters.
6. Record generated issue numbers and planning artifacts in Watchtower run history only.

Automatic dependency unblocking may be deferred to the accepted dependency-blocking implementation if runtime support is not complete.

## Risks And Guardrails

- Direct issue creation can create backlog noise. Generated issues must start in a non-dispatch review state.
- A separate role adds workflow complexity. The boundary is justified because issue decomposition and backlog generation are distinct from strategy, roadmap synchronization, and implementation.
- Dependency generation can overfit early assumptions. The planner should only declare conservative dependencies.
- Generated issues can become stale. Plan review must cite the source recommendation and roadmap update, and changes should route back through `state:implementation-planning-changes-requested`.
- V1 should process one approved recommendation at a time rather than expanding broad roadmap initiatives automatically.

## Recommended Follow-up Sequence

1. Document the Implementation Planner role, workflow states, generated issue contract, and review gate.
2. Add canonical label support for the planning states.
3. Add Handler dispatch support for `state:ready-for-implementation-planning`.
4. Implement the planner workflow that reads approved recommendations and merged roadmap docs.
5. Add generated issue creation in `state:planned` or another non-dispatch review state.
6. Add the structured plan comment and Watchtower generated-issue observability.
7. Add the approved transition from plan review into existing dispatchable workflow states.
