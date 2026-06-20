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
- `state:ready-for-human-review`
- `state:dependency-blocked`
- `state:blocked`
- `state:agent-in-progress`

Systems Architect remains a strategic planning role, but now uses explicit GitHub workflow states and human-selected follow-up labels.
The `state:ready-for-roadmap-update` state is a documentation synchronization step for accepted strategy, not an implementation handoff.
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

---

# Current Strategic Frontier

Issue #19 confirms that the broad capability order remains:

`Workflow Foundation` -> `Self Hosting` -> `Provider Routing` -> `Skills`

The next active frontier is **self-hosting reliability and strategic memory**.

Within that frontier, the intended sequence is:

1. Repository onboarding.
2. Workspace isolation.
3. Durable polling.
4. Dependency blocking and automatic unblocking.
5. Stale-lock and run recovery.
6. Persistent Watchtower visibility.
7. Strategic memory that records accepted recommendations without making Watchtower the primary review surface.

Provider Routing and Skills remain valid future work, but both should stay behind self-hosting reliability so provider complexity and role specialization are added only after the runtime can observe, recover, and preserve context across repeated runs.

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
- fail closed on missing, malformed, inaccessible, unsafe, or cyclic dependency metadata

The roadmap sequence for this capability is:

1. Document the dependency model and lifecycle.
2. Add canonical `state:dependency-blocked` label support.
3. Implement dependency metadata parsing and validation.
4. Add Handler pre-dispatch dependency gating.
5. Add automatic unblocking during polling.
6. Add Watchtower dependency observability fields.
7. Extend Roadmap Updater and Systems Architect guidance so future roadmap-generated issue trees can include dependency sections at issue creation time.

Detailed architecture: [Issue Dependency Blocking](../dependency-blocking.md).

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
