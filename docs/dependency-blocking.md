# Issue Dependency Blocking Architecture

Issue #34 accepted explicit dependency blocking as a Handler-owned scheduling capability.

This document records the approved Systems Architect recommendation for roadmap and implementation planning. It is not a runtime implementation specification.

## Decision

The Circus should support first-class issue dependency management before broader parallel execution.

GitHub remains the source of truth for dependency metadata and workflow state. Handler owns dependency eligibility checks, scheduler-managed blocking, and automatic unblocking. Watchtower remains an observability layer that records dependency decisions; it does not become the authority for dependency state.

## Dependency Metadata

Dependencies should be represented in a dedicated machine-readable issue body section:

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

The dependency section is intentionally human-inspectable and machine-readable. Handler should fail closed when the section is missing, malformed, cyclic, inaccessible, or unsafe for automatic evaluation.

## Workflow State

Add a distinct non-dispatch workflow state:

```text
state:dependency-blocked
```

This state is separate from `state:blocked`.

`state:blocked` remains human-owned and terminal for ambiguous or unsafe conditions. `state:dependency-blocked` means an item is intentionally paused by declared prerequisites and may be automatically resumed when all prerequisites are satisfied.

Each issue should still have exactly one primary `state:*` label. A dependency-blocked issue should not keep its prior dispatchable state label. The dependency metadata must carry `resume_state` so Handler can restore the correct single primary state after successful unblocking.

## Eligibility Gate

Before Handler locks and launches any dispatchable item, it should:

1. Parse the `Circus Dependencies` section when present.
2. Fetch the referenced dependency targets from GitHub.
3. Evaluate whether all dependencies are satisfied.
4. Block the item before agent launch when any dependency is unsatisfied.

When an item is dependency-blocked, Handler should remove the current dispatch state, add `state:dependency-blocked`, leave a clear GitHub issue comment listing unsatisfied dependencies, and record the dependency status in Watchtower run/status artifacts.

## Automatic Unblocking

Handler polling should inspect `state:dependency-blocked` issues.

If all declared dependencies are satisfied, Handler should remove `state:dependency-blocked`, restore the declared `resume_state`, leave a GitHub comment explaining the unblock, and record the decision in Watchtower.

If dependency metadata is missing, malformed, cyclic, inaccessible, or unsafe, Handler should move or leave the issue in human-owned blocked state and comment with the blocker instead of silently resuming work.

## Satisfaction Rules

V1 dependency satisfaction should be conservative:

- Referenced issues are satisfied only when closed with a completed state reason.
- Referenced pull requests are satisfied only when merged.
- Closed as not planned, duplicate, rejected, inaccessible, missing, malformed, or unknown targets do not silently unblock downstream work.
- Multiple dependencies require all prerequisites to be satisfied before automatic unblocking.

The schema may later allow explicit accepted outcomes, but the first implementation should bias toward preventing accidental execution.

## Integration Points

The accepted implementation boundary includes:

- `Handler/workflow_states.py`: add `state:dependency-blocked` as non-dispatchable and non-launchable.
- `Handler/workflow_labels.py`: synchronize the canonical dependency-blocked label.
- `Handler/dependencies.py`: parse metadata, validate schema, resolve dependency references, evaluate satisfaction, and detect self or circular dependencies.
- `Handler/github_client.py`: fetch issue and pull request details needed for dependency evaluation.
- `Handler/handler.py`: run dependency validation before locking dispatchable items and run an unblocking pass during polling.
- `Handler/watchtower.py`: record dependency status fields such as `dependencies`, `dependency_status`, `dependency_blockers`, and `resume_state`.

## First Implementation Acceptance Criteria

- A dependency-blocked issue cannot launch even if it previously had a dispatchable ready state.
- A dispatchable issue with unsatisfied dependencies is moved to `state:dependency-blocked` before agent launch.
- Multiple dependencies require all prerequisites to be satisfied before unblocking.
- Closed-not-planned, duplicate, inaccessible, missing, or malformed dependency targets do not unblock downstream work silently.
- Circular dependencies are detected and surfaced to humans.
- Automatic unblocking restores exactly one dispatchable `resume_state` label.
- Every block and unblock decision leaves a GitHub issue comment and Watchtower status entry.

## Recommended Follow-up Sequence

1. Document the dependency model and lifecycle.
2. Add canonical `state:dependency-blocked` label support.
3. Implement dependency metadata parsing and validation.
4. Add Handler pre-dispatch dependency gating.
5. Add automatic unblocking during polling.
6. Add Watchtower dependency observability fields.
7. Extend Roadmap Updater and Systems Architect guidance so future roadmap-generated issue trees can include dependency sections at issue creation time.
