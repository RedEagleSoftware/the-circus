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
- `state:ready-for-human-review`
- `state:blocked`
- `state:agent-in-progress`

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
- richer Watchtower UI
- live orchestration dashboards
- replayable execution history
- proposal/recommendation workflows
- automatic artifact indexing
- deeper GitHub integration
- project-specific custom agent profiles
- autonomous retry/recovery flows
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