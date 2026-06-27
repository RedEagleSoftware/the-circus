# The Circus v1 Agent Workflow

## Purpose

The Circus is a lightweight orchestration system for coordinating AI agents through durable artifacts, explicit workflow state, and GitHub-driven execution.

The system is intentionally:
- inspectable
- deterministic
- minimally magical
- artifact-driven
- human-review-centric

The Circus is not intended to be a fully autonomous software factory.

Its purpose is to coordinate focused AI workflow steps while preserving:
- transparency
- operational control
- reproducibility
- architectural continuity

---

# Core Principles

## Durable Context Over Session Memory

The Circus assumes agent sessions are ephemeral.

Durable context should live in:
- GitHub metadata
- markdown artifacts
- shared issue-level context
- repository guidance
- operational doctrine

Agents should not rely on long-lived conversational memory for orchestration correctness.

---

## GitHub As Source Of Truth

GitHub issues and pull requests are the authoritative workflow state machine.

GitHub owns:
- workflow state
- issue discussion
- PR review
- execution visibility

The Circus augments GitHub with orchestration artifacts but does not replace it.

---

## Thin Prompting

Agent prompts should remain thin.

Behavioral guidance belongs in:
- role doctrine
- project guidance
- shared artifacts
- repository conventions

Launch prompts should primarily:
- identify the workflow item
- identify the workspace
- identify the role
- identify durable context artifacts

---

## Human Review First

Human review is a first-class workflow step.

The Circus v1 intentionally avoids:
- auto-merge
- autonomous label transitions
- hidden retries
- silent state mutation

---

## Explicit Over Implicit

The Circus prefers:
- explicit paths
- explicit labels
- explicit artifacts
- explicit logging
- explicit execution boundaries

over hidden inference and automation.

---

# High-Level Workflow

## Planned Workflow States

- `state:ready-for-architecture`
- `state:ready-for-dev`
- `state:review-requested`
- `state:ready-for-architect-review`
- `state:ready-for-systems-architecture`
- `state:systems-architecture-changes-requested`
- `state:ready-for-roadmap-update`
- `state:ready-for-implementation-planning`
- `state:ready-for-implementation-plan-review`
- `state:implementation-planning-changes-requested`
- `state:planned`
- `state:ready-for-human-review`
- `state:dependency-blocked`
- `state:blocked`
- `state:agent-in-progress`

Systems Architect remains a strategic planning role, but now uses explicit GitHub workflow states and human-selected follow-up labels.
The `state:ready-for-roadmap-update` state is a documentation synchronization step for accepted strategy, not an implementation handoff.
The `state:ready-for-implementation-planning` state routes accepted and documented strategy to Implementation Planner.
The `state:ready-for-implementation-plan-review` state holds generated implementation plans for human approval before generated issues become dispatchable.
The `state:implementation-planning-changes-requested` state routes implementation plans back for revision.
The `state:planned` state marks generated issues that are not yet dispatchable.
Planner outcomes are declared in artifacts and comments, not as new `state:*` labels.
The `state:dependency-blocked` state is a scheduler-managed waiting state for issues with declared unsatisfied prerequisites. It is not dispatchable.

---

## Intended Workflow Flow

### 1. Human Creates Issue

A GitHub issue describes:
- requested behavior
- goals
- acceptance criteria
- constraints

The issue becomes the workflow entry point.

---

### 2. Architect Agent Produces Handoff

The architect agent:
- analyzes the issue
- reviews repository conventions
- identifies implementation direction
- produces an architecture handoff artifact

Architect output should reduce ambiguity for implementation agents.

Architects should not overwrite issue bodies.

---

### 3. Developer Agent Implements

The developer agent:
- reads the launch brief
- reads shared issue artifacts
- follows repository guidance
- implements the requested change
- creates commits/PRs
- leaves operational comments

The developer should primarily follow:
- architecture handoff
- repository guidance
- GitHub metadata

rather than improvising from issue discussion alone.

---

### 4. Reviewer Agent Reviews

Reviewer agents may:
- validate implementation correctness
- identify architectural drift
- request changes
- verify tests and workflow expectations

---

### 5. Human Approval

Human review remains authoritative before merge.

---

### 6. Strategic Roadmap Synchronization

When a Systems Architect recommendation is accepted, the human reviewer applies `state:ready-for-roadmap-update`.

The Roadmap Updater then:
- identifies the approved Systems Architect recommendation from the issue discussion
- updates roadmaps, capability trees, and related knowledge artifacts
- creates a documentation-only pull request
- leaves a summary comment linking the issue to the PR

Roadmap updates should not mutate workflow labels directly, auto-merge, or produce runtime implementation changes.

Workflow ownership contract for roadmap updates:

- Roadmap Updater owns documentation changes, commits, branch push, PR creation, and the issue summary comment.
- Handler owns launch orchestration, working-branch preparation, post-run validation that an open PR exists, run-status recording, and `state:*` label transitions.
- Developer workflow finalization remains Handler-owned and is intentionally separate from roadmap updater ownership.

Future workflow contract rule:

- each workflow role should explicitly document PR ownership and handoff boundaries
- Handler remains the single authority for workflow label mutation

### 7. Implementation Planning

After roadmap documentation is reviewed and merged, the human reviewer may apply `state:ready-for-implementation-planning`.

The Implementation Planner then:

- reads the approved Systems Architect recommendation
- reads the updated roadmap and capability-tree documentation
- declares exactly one outcome: `READY`, `BLOCKED`, or `ESCALATION_REQUIRED`
- for `READY`, decomposes the accepted strategy into generated GitHub issues
- for `READY`, proposes initial issue ordering
- for `READY`, declares conservative `## Circus Dependencies` metadata where ordering matters
- for `READY`, creates generated issues in a non-dispatch state such as `state:planned`
- leaves a structured implementation plan, blocker, or escalation comment with human review options

Generated implementation issues do not become dispatchable automatically, and they are created only for `READY`.

If the outcome is `BLOCKED`, the planner leaves a blocker comment, creates no generated issues by default, and identifies whether planning should resume from `state:ready-for-implementation-planning` or `state:implementation-planning-changes-requested` after the blocker is resolved.

If the outcome is `ESCALATION_REQUIRED`, the planner leaves an architecture escalation request, creates no generated issues, explains why issue generation would be unsafe, and recommends human routing to `state:systems-architecture-changes-requested`.

For `READY`, human reviewers approve the plan before Handler or a dedicated approved transition moves eligible generated issues into dispatchable states such as `state:ready-for-architecture` or `state:ready-for-dev`.

Workflow ownership contract for implementation planning:

- Implementation Planner owns outcome declaration, issue decomposition for `READY`, generated issue content, proposed ordering, dependency declarations, and the plan/blocker/escalation artifact.
- Handler owns planner dispatch, workflow label transitions, dependency enforcement, automatic unblocking, and transitions from plan review into dispatchable states.
- Roadmap Updater owns strategic documentation before implementation planning begins.
- Watchtower records generated issue numbers and planning artifacts for run history only.

---

# Current Strategic Frontier

Issue #19 confirms that the broad capability order remains:

`Workflow Foundation` -> `Self Hosting` -> `Provider Routing` -> `Skills`

Issue #84 keeps that order in place and sharpens the next active frontier from broad **self-hosting reliability and strategic memory** into an organizational maturity program for self-hosted execution.

Within that frontier, the intended sequence is:

1. Repository onboarding.
2. Workspace isolation.
3. Durable polling.
4. Dependency blocking and automatic unblocking.
5. Worktree and branch lifecycle management.
6. Stale-lock and run recovery.
7. Persistent Watchtower visibility.
8. Strategic memory that records accepted recommendations without making Watchtower the primary review surface.
9. Implementation planning that converts accepted strategy into review-gated generated implementation issues, or explicitly blocks/escalates when safe planning cannot continue.
10. Workflow governance parity across doctrine, roadmap documentation, canonical labels, and executable Handler state support.
11. Human decision management and lightweight organizational metrics that make pending decisions, stale decisions, blocker classes, recovery events, review churn, and planning-to-implementation traceability inspectable.

Provider Routing and Skills remain valid future work, but both should stay behind self-hosting reliability so provider complexity and role specialization are added only after the runtime can observe, recover, and preserve context across repeated runs.

## Accepted Organizational Maturity Direction

Issue #84 approved an organizational maturity refinement under the existing Self Hosting reliability and Strategic Memory frontier.

The accepted direction is:

- keep the current strategic frontier, but treat organizational closure as the limiting capability before provider routing, skills, broad parallel dispatch, or model/resource optimization
- reconcile workflow doctrine, roadmap documentation, canonical labels, and runtime state support into one auditable workflow governance contract
- build an organizational memory ledger for accepted recommendations, roadmap updates, generated plans, resulting implementation issues, and outcome state, with GitHub remaining the review surface and Watchtower remaining observability
- finish operational recovery as a first-class capability covering stale locks, interrupted runs, workspace lifecycle classification, dependency blocking, and safe resume or blocked behavior
- add a lightweight metrics and decision-review loop that records run outcomes, blocker classes, review churn, recovery events, and planning-to-implementation traceability
- mature human decision management so every human-owned state has an explicit decision artifact, accepted source reference, next-state options, and stale-decision detection

The roadmap sequence for this program is:

1. Workflow governance parity: document and then enforce parity between accepted workflow states, label sync, Handler dispatchability, human-owned states, and unsupported-state handling.
2. Accepted-decision traceability: record Systems Architect recommendation URL/comment ID, roadmap PR, planner issue, generated issue IDs, and outcome state in Watchtower run history while preserving GitHub as authority.
3. Recovery baseline: complete stale-lock/run recovery, workspace lifecycle classification, and dependency-blocked resume behavior before expanding parallelism or provider routing.
4. Human decision ledger: standardize artifacts for roadmap acceptance, implementation-plan approval, generated issue dispatch approval, and stale-plan/change-request loops.
5. Organizational metrics seed: start with simple, inspectable counts and categories for run outcomes, blockers, recovery events, review changes requested, and plan churn.

These initiatives should become independently valuable implementation slices after roadmap synchronization. Metrics are visibility and review inputs in v1; they should not become automatic routing or control signals until later approved runtime capabilities validate that behavior.

## Accepted Workspace Isolation Direction

Issue #30 approved Git worktrees as the primary isolation mechanism for normal mutation-capable agent execution.

The accepted direction is:

- keep `CIRCUS_TARGET_REPO_PATH` as the canonical local repository and worktree source
- introduce a workspace resolver that returns a deterministic per-item workspace path
- record the resolved workspace path and branch in launch briefs and Watchtower status
- execute Developer and Roadmap Updater runs from item worktrees first
- preserve existing Circus branch naming for PR creation compatibility
- block on dirty or unexpected worktrees rather than resetting automatically

The roadmap sequence for this capability is:

1. Document the accepted worktree architecture and first implementation boundary.
2. Implement workspace path resolution and Watchtower/launch-brief recording.
3. Add worktree create/reuse for Developer and Roadmap Updater execution.
4. Switch Developer PR finalization to the resolved workspace path.
5. Add stale worktree detection/reporting as part of stale-lock/run recovery.
6. Move Architect and Reviewer modes onto resolver-managed base/read-only workspaces once the mutation-capable path is proven.

Detailed architecture: [Worktree Isolation](../worktree-isolation.md).

## Accepted Worktree and Branch Lifecycle Direction

Issue #51 approved Worktree and Branch Lifecycle Management as the next Self Hosting reliability capability.
Issue #54 approved the workspace inventory and lifecycle classification service as the first implementation slice for that capability.

The accepted direction is:

- keep the lifecycle invariant explicit: one GitHub item maps to one deterministic workspace, one expected Circus branch, and zero or one open PR
- use GitHub as the source of truth for workflow state and human decisions
- use Git as the source of truth for repository, worktree, branch, upstream, and cleanliness facts
- keep Watchtower observational, recording lifecycle classifications, diagnostics, run history, and recommendation traceability without becoming the cleanup authority
- classify workspaces as `planned`, `ready`, `active`, `suspended`, `recoverable`, `stale-clean`, `retired`, `cleanup-eligible`, or `blocked-unsafe`
- start recovery with an inventory that correlates worktree metadata, branch/upstream state, cleanliness, open PRs, workflow labels, and recent Watchtower run status
- split inventory collection from classification policy so raw Git, GitHub, and Watchtower facts are gathered before lifecycle decisions are made
- return structured classification results with explicit facts, reasons, and confidence or ambiguity signals
- treat uncertainty, inaccessible metadata, and ambiguous relationships as `blocked-unsafe`
- keep the issue #54 service read-only and classification-only; diagnostics are in scope, but repair and cleanup actions are follow-on work
- require human approval before cleanup or any action that deletes, resets, force-pushes, rebases, removes branches, or removes worktrees

The roadmap sequence for this capability is:

1. Document the lifecycle state model and safety rules.
2. Add a read-only workspace inventory and classification service.
3. Add an operator-facing lifecycle diagnostic command or report with no mutations.
4. Add non-destructive recovery helpers for missing upstream tracking and interrupted-run diagnostics.
5. Integrate lifecycle classification into stale-lock and run recovery before relaunch.
6. Add dry-run cleanup reporting for `retired` and `stale-clean` workspaces only.
7. Add a reviewed cleanup execution path for clean registered worktrees.
8. Record accepted Systems Architect recommendation comment URLs and IDs in Watchtower run history.

Detailed architecture: [Worktree and Branch Lifecycle Management](../worktree-lifecycle.md).

## Accepted Dependency Blocking Direction

Issue #34 approved explicit dependency blocking as a Handler-owned scheduling capability.

The accepted direction is:

- represent dependencies in a dedicated machine-readable `## Circus Dependencies` issue body section
- include `resume_state` in dependency metadata so automatic unblocking restores exactly one primary workflow state
- add `state:dependency-blocked` as a non-dispatch state separate from human-owned `state:blocked`
- run dependency validation before Handler locks and launches any dispatchable item
- automatically unblock dependency-blocked items during Handler polling when all prerequisites are satisfied
- treat dependency satisfaction conservatively, with issues satisfied only by closed-completed outcomes and pull requests satisfied only by merge
- record every block and unblock decision in both GitHub comments and Watchtower status artifacts
- treat issues without a `## Circus Dependencies` section as having no declared dependencies under normal workflow rules
- fail closed on missing, malformed, inaccessible, unsafe, or cyclic dependency metadata when dependency intent is declared or unblocking metadata cannot be safely evaluated

The roadmap sequence for this capability is:

1. Document the dependency model and lifecycle.
2. Add canonical `state:dependency-blocked` label support.
3. Implement dependency metadata parsing and validation.
4. Add Handler pre-dispatch dependency gating.
5. Add automatic unblocking during polling.
6. Add Watchtower dependency observability fields.
7. Extend Roadmap Updater and Systems Architect guidance so future roadmap-generated issue trees can include dependency sections at issue creation time.

Detailed architecture: [Issue Dependency Blocking](../dependency-blocking.md).

## Accepted Implementation Planning Direction

Issue #37 approved Implementation Planning as a distinct role and capability.
Issue #64 approved the Planner Outcome Model and architecture escalation workflow.

The accepted direction is:

- add Implementation Planner as a separate role after Roadmap Updater
- keep roadmap and capability-tree docs as the durable strategic anchor before planning starts
- require every planner result to declare exactly one outcome: `READY`, `BLOCKED`, or `ESCALATION_REQUIRED`
- reuse existing workflow states instead of adding outcome labels for v1
- let the planner own issue decomposition, proposed sequencing, dependency declaration, generated issue creation, and plan review artifacts
- create generated issues directly in GitHub only for `READY`, and in a non-dispatch review state
- use `BLOCKED` for missing, stale, inaccessible, unsafe, or contradictory planning prerequisites that do not require a new Systems Architect decision
- use `ESCALATION_REQUIRED` when implementation planning would force systems-level decisions that belong to Systems Architect
- require source traceability from generated issues back to the recommendation and roadmap update
- require human approval before generated issues become dispatchable
- keep Handler responsible for label transitions, dispatch eligibility, dependency enforcement, and automatic unblocking
- keep Watchtower as observability and run history, not the authority for generated work

The roadmap sequence for this capability is:

1. Document the Implementation Planner role, workflow states, generated issue contract, and review gate.
2. Add canonical label support for `state:ready-for-implementation-planning`, `state:ready-for-implementation-plan-review`, `state:implementation-planning-changes-requested`, and `state:planned`.
3. Add Handler dispatch support for `state:ready-for-implementation-planning`.
4. Implement the planner workflow that reads one approved recommendation and merged roadmap docs.
5. Add planner outcome validation with a required `### Outcome` section.
6. Add generated GitHub issue creation in a non-dispatch review state for `READY` only.
7. Add structured plan, blocker, and escalation comments with Watchtower outcome observability.
8. Add the human-approved transition from plan review into existing dispatchable workflow states.
9. Add safeguards that prevent advancement on `BLOCKED` or `ESCALATION_REQUIRED`, with optional escalation routing only after human-approved automation exists.

Detailed architecture: [Implementation Planning](../implementation-planning.md).

## Accepted Workflow Governance Direction

Issue #59 approved circular planning and complexity-based routing as workflow governance doctrine before runtime automation.

The accepted direction is:

- keep Handler as the only workflow state authority
- allow roles to recommend returns, blockers, escalations, decomposition changes, or follow-up routing through GitHub comments and durable artifacts
- route accepted Systems Architect recommendations to Roadmap Updater through human-applied `state:ready-for-roadmap-update`
- route accepted and merged roadmap documentation to Implementation Planner through human-applied `state:ready-for-implementation-planning`
- route unresolved systems-level planning decisions back to Systems Architect through `ESCALATION_REQUIRED` and a recommendation for `state:systems-architecture-changes-requested`
- route implementation plan revisions through `state:implementation-planning-changes-requested`
- let Feature Architect flag issues that are too broad, too risky, blocked, under-specified, or in need of implementation planning, while leaving label mutation to humans or Handler
- use `implementation_complexity`, `safety_risk`, `slice_size`, and `architecture_uncertainty` as advisory classification vocabulary in comments and artifacts
- defer automatic model selection, effort routing, reviewer-depth changes, and extra review gates until reliability and traceability are mature enough

The roadmap sequence for this capability is:

1. Document workflow governance, ownership boundaries, return paths, and advisory classification vocabulary.
2. Encourage Systems Architect, Implementation Planner, and Feature Architect artifacts to use the vocabulary when it materially affects routing or review depth.
3. Add optional structured classification blocks to architecture and planning artifacts.
4. Record accepted Systems Architect recommendation comment URLs and IDs in Watchtower run history.
5. Add Handler validation for classification blocks only after their manual use proves stable.
6. Consider model, effort, reviewer-depth, and extra-gate routing after the runtime can preserve and recover routing decisions reliably.

Detailed architecture: [Workflow Governance and Routing Doctrine](../workflow-governance.md).

---

# Artifact Model

## Launch Briefs

Launch briefs are runtime orchestration handoff artifacts.

They contain:
- workflow metadata
- target repo path
- role profile references
- shared artifact references
- operational instructions

Launch briefs are not intended to become the product specification.

---

## Shared Issue-Level Artifacts

Shared artifacts preserve durable context between fresh agent sessions.

Example structure:

    Watchtower/runs/issue-3/shared/
    ├── architecture-handoff.md
    ├── running-notes.md
    └── decision-log.md

These artifacts:
- persist across runs
- survive fresh sessions
- provide operational continuity

---

## Run-Level Artifacts

Each execution attempt gets its own run folder.

Example:

    Watchtower/runs/issue-3/run-002-developer/

Run artifacts may include:
- launch briefs
- logs
- result summaries
- execution metadata

Run artifacts represent:
- what happened during one execution attempt

not:
- durable project memory

Strategic recommendation comments in GitHub remain the human review surface.
Watchtower may record recommendation comment URLs or IDs for traceability, but it should not replace the issue discussion as the source of truth.

---

# Repository Guidance Model

The Circus distinguishes between:

## Generic Role Doctrine

Stored in The Circus repository.

Examples:
- `TheFarm/roles/developer.md`
- `TheFarm/roles/architect.md`

These define:
- behavioral expectations
- workflow discipline
- operational standards

---

## Project-Specific Guidance

Stored in the target repository.

Examples:
- `AGENTS.md`
- `.circus/`
- architecture standards
- implementation conventions

Target repository guidance overrides generic role doctrine where conflicts exist.

---

# Execution Philosophy

## Fresh Session Bias

The Circus prefers:
- one workflow task
- one fresh agent session

Durable artifacts should carry context between runs.

---

## Manual-Safe v1

The Circus v1 prioritizes:
- observability
- deterministic behavior
- safe execution
- inspectable orchestration

before:
- concurrency
- autonomy
- optimization
- hidden automation

---

## Controlled Agent Scope

Agents should:
- perform one workflow step
- avoid unrelated changes
- preserve transparency
- stop on ambiguity

Agents should not:
- silently redefine scope
- auto-merge
- mutate orchestration doctrine
- invent missing context

---

# Deferred v1+ Ideas

Potential future exploration areas:

- multi-agent concurrency
- provider routing after self-hosting reliability improves
- role skills and specialization after provider and execution reliability are stable
- richer Watchtower UI for persistent visibility
- live orchestration dashboards
- replayable execution history
- proposal/recommendation workflows
- automatic artifact indexing
- deeper GitHub integration
- project-specific custom agent profiles
- autonomous retry/recovery flows after stale-lock/run recovery is observable and reviewable
- execution metrics and analytics

These are intentionally deferred until the core workflow model is stable.

---

# Non-Goals

The Circus v1 is not attempting to:
- replace human engineering judgment
- create fully autonomous software development
- eliminate code review
- centralize hidden AI memory
- obscure execution behavior
- auto-resolve ambiguity

The Circus is intended to coordinate AI workflow steps transparently and safely.
