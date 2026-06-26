# Implementation Planning Architecture

Issue #37 accepted Implementation Planning as a distinct workflow role and capability.
Issue #64 accepted the formal Planner Outcome Model and architecture escalation workflow.
Issue #59 accepted circular planning and complexity-based routing as workflow governance doctrine before runtime automation.

This document records the approved Systems Architect recommendation for roadmap and implementation planning. It is not a runtime implementation specification.

## Decision

The Circus should use Implementation Planning as a separate workflow role after roadmap synchronization.

Implementation Planning converts accepted strategic intent into an executable, human-reviewed implementation plan when planning is safe. It owns outcome declaration, issue decomposition, initial sequencing, dependency declaration, generated issue creation for successful plans, and plan review artifacts. It does not own dispatch eligibility, workflow label transitions, dependency enforcement, automatic unblocking, or systems-level architecture decisions.

The official planner outcomes are:

- `READY`
- `BLOCKED`
- `ESCALATION_REQUIRED`

No new workflow state labels are introduced for the v1 outcome model. Existing workflow states remain the control points, and the planner outcome becomes an explicit artifact and GitHub comment contract.

## Workflow Position

The accepted high-level flow for `READY` is:

```text
Architecture question
-> Systems Architect recommendation
-> Human approval
-> state:ready-for-roadmap-update
-> Roadmap Updater documentation PR
-> Human review / merge of roadmap docs
-> state:ready-for-implementation-planning
-> Implementation Planner
-> outcome: READY
-> Draft implementation plan + generated GitHub issues + dependency metadata
-> state:ready-for-implementation-plan-review
-> Human approval
-> generated issues become dispatchable through existing workflow states
```

Implementation Planning happens after roadmap updates so the capability tree and roadmap remain the durable strategic anchor before executable backlog work is generated.

When the planner cannot safely produce a valid plan, it must declare either `BLOCKED` or `ESCALATION_REQUIRED` instead of presenting a partial decomposition as an implementation plan.

- `BLOCKED` means required inputs, runtime operations, repository metadata, access, or source-of-truth prerequisites are missing, stale, inaccessible, unsafe, or contradictory, and no new Systems Architect decision is required.
- `ESCALATION_REQUIRED` means the planner has enough context to determine that implementation planning would force systems-level decisions that belong to Systems Architect.

## Ownership Boundaries

Implementation Planner owns:

- declaring exactly one planner outcome
- decomposing one approved strategic recommendation into implementation issues
- proposing the initial execution order
- declaring conservative issue dependencies where ordering matters
- creating generated GitHub issues directly in a non-dispatch review state when the outcome is `READY`
- writing a durable `implementation-plan.md` artifact for Handler advancement or blocker/escalation review
- leaving a structured implementation plan, blocker, or escalation GitHub comment for human review
- preserving source traceability to the approved recommendation and roadmap update

Handler owns:

- dispatch eligibility
- planner launch and workflow routing from declared outcomes
- workflow label transitions
- dependency blocking and automatic unblocking
- approved transitions from planning review into dispatchable workflow states

Watchtower owns observability only:

- recording planning run artifacts
- recording generated issue links
- preserving run history

GitHub issues and comments remain the human review surface and source of truth.

Workflow return paths and advisory classification vocabulary are documented in [Workflow Governance and Routing Doctrine](workflow-governance.md). The planner may use `implementation_complexity`, `safety_risk`, `slice_size`, and `architecture_uncertainty` when those dimensions materially affect decomposition, blocker handling, escalation, or review-depth recommendations, but they are not runtime metadata requirements in v1.

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

`BLOCKED` should leave a blocker comment and should not create generated issues by default. Human or Handler follow-up may use `state:blocked` when manual intervention is required.

`ESCALATION_REQUIRED` should leave an architecture escalation request, create no generated issues, and recommend routing the source issue to `state:systems-architecture-changes-requested`.

Each issue should still have exactly one primary `state:*` label.

## Generated Issue Contract

Generated implementation issues should be created directly in GitHub only when the planner outcome is `READY`, and initially in a non-dispatch state.

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

Generated issue constraints:

- The planner should generate implementation issues only for `READY`.
- The planner should not generate issues during `ESCALATION_REQUIRED`.
- The planner should not generate issues during `BLOCKED`, except to report and quarantine any partial issue creation that occurred before a failure.
- Partial decomposition may appear as non-authoritative analysis in an escalation comment, but it must not be presented as an approved implementation plan or converted into dispatchable work.

## Implementation Plan Artifact

The canonical detailed output contract lives in `TheFarm/roles/implementation-planner.md`.

This document summarizes the required artifact shape for architecture consistency.

When launched through `state:ready-for-implementation-planning`, the planner must:

- write `implementation-plan.md` as the durable run artifact used by Handler advancement gating
- leave a structured GitHub issue comment as the human review surface

For `READY`, the durable artifact and the GitHub comment should use this heading structure:

- `## Implementation Plan`
- `### Outcome`
- `### Source`
- `### Planning Summary`
- `### Generated Issues`
- `### Proposed Order`
- `### Dependencies`
- `### Dispatch Readiness`
- `### Human Review Options`

Optional sections may be included when needed:

- `### Automation Notes`
- `### Risks And Open Questions`
- `### Deferred Work`

If the planner cannot produce a valid plan, it should still write `implementation-plan.md` with blocker or escalation context, but the GitHub comment should not use `## Implementation Plan` as if a valid plan exists.

For `BLOCKED`, the planner should publish a clearly titled blocker comment, such as `## Implementation Planning Blocked`, and include:

- `### Outcome` with `BLOCKED`
- source traceability
- the missing, stale, inaccessible, unsafe, or contradictory prerequisite
- confirmation that no generated implementation issues were created by default
- expected resume state, usually `state:ready-for-implementation-planning` or `state:implementation-planning-changes-requested`
- human review options

For `ESCALATION_REQUIRED`, the planner should publish a clearly titled escalation comment, such as `## Architecture Escalation Required`, and include:

- `### Outcome` with `ESCALATION_REQUIRED`
- source traceability
- the systems-level decision required
- why issue generation would be unsafe
- proposed Systems Architect questions to answer next
- confirmation that no generated implementation issues were created
- human review option recommending `state:systems-architecture-changes-requested`

The plan artifact should make stale plans easy to detect. If the source recommendation or roadmap docs change before approval, the issue should return to `state:implementation-planning-changes-requested` rather than silently dispatching generated work.

## First Implementation Boundary

The first implementation should build the smallest useful Implementation Planner workflow:

1. Read one approved Systems Architect recommendation and the updated roadmap docs.
2. Declare exactly one planner outcome.
3. Produce one structured implementation plan, blocker, or escalation artifact and matching GitHub comment.
4. Create generated GitHub issues in a non-dispatch review state only for `READY`.
5. For `BLOCKED`, leave a blocker comment and do not create generated issues by default.
6. For `ESCALATION_REQUIRED`, leave an architecture escalation request and do not create generated issues.
7. For `READY`, include acceptance criteria and suggested next workflow state in generated issues.
8. For `READY`, include `## Circus Dependencies` metadata when generated issue ordering matters.
9. Record generated issue numbers, outcome, and planning artifacts in Watchtower run history only.

Runtime follow-on work after documentation merge should:

1. Require planner result artifacts to declare exactly one outcome.
2. Transition `READY` to `state:ready-for-implementation-plan-review`.
3. Prevent advancement on `BLOCKED` or `ESCALATION_REQUIRED`.
4. Optionally route declared escalation to `state:systems-architecture-changes-requested` after human-approved automation exists.
5. Correct runtime label-description wording for `state:planned` so generated issues are not described as approved or dispatch-ready.

Automatic dependency unblocking may be deferred to the accepted dependency-blocking implementation if runtime support is not complete.

## Risks And Guardrails

- Direct issue creation can create backlog noise. Generated issues must start in a non-dispatch review state.
- A separate role adds workflow complexity. The boundary is justified because issue decomposition and backlog generation are distinct from strategy, roadmap synchronization, and implementation.
- Dependency generation can overfit early assumptions. The planner should only declare conservative dependencies.
- Generated issues can become stale. Plan review must cite the source recommendation and roadmap update, and changes should route back through `state:implementation-planning-changes-requested`.
- V1 should process one approved recommendation at a time rather than expanding broad roadmap initiatives automatically.
- Reusing existing workflow states avoids label sprawl, but it makes the outcome artifact contract important. Handler should eventually validate the declared outcome before applying transitions.
- Preventing generated issues during escalation may delay useful scaffolding, but it avoids backlog items that encode unresolved architecture decisions.
- If partial issue creation happens before a late blocker or escalation finding, the planner must list those issues and mark them unsafe for dispatch.

## Recommended Follow-up Sequence

1. Document the Implementation Planner role, workflow states, generated issue contract, and review gate.
2. Add canonical label support for the planning states.
3. Add Handler dispatch support for `state:ready-for-implementation-planning`.
4. Implement the planner workflow that reads approved recommendations and merged roadmap docs.
5. Add generated issue creation in `state:planned` or another non-dispatch review state for `READY`.
6. Add the structured plan comment and Watchtower generated-issue observability.
7. Add the approved transition from plan review into existing dispatchable workflow states.
8. Add planner outcome validation and escalation/blocker routing safeguards.
