# Workflow Governance and Routing Doctrine

Issue #59 accepted circular planning and complexity-based routing as workflow governance doctrine before runtime automation.

This document records how roles should identify upstream or downstream routing needs while preserving Handler-owned workflow state control. It is not a runtime implementation specification.

## Decision

The Circus should support circular planning through explicit recommendations, artifacts, and human/Handler-mediated workflow transitions.

Roles may identify that work belongs upstream, downstream, or in a revised planning pass. They must express that finding in structured GitHub comments or durable artifacts rather than mutating workflow labels directly. Handler remains the only workflow state authority.

Complexity-based routing should begin as a shared vocabulary for comments and artifacts. Automatic model selection, effort changes, reviewer-depth changes, and extra review-stage insertion are deferred until self-hosting reliability, implementation planning, and Watchtower traceability are mature enough to preserve and recover those decisions.

## Ownership Boundaries

Systems Architect owns:

- strategic direction
- unresolved system-level decisions
- capability sequencing and cross-issue governance recommendations

Roadmap Updater owns:

- durable documentation synchronization after accepted strategy
- roadmap, capability-tree, role-guide, and high-level documentation updates
- documentation-only pull requests for accepted strategic recommendations

Implementation Planner owns:

- decomposition of accepted and documented strategy into generated implementation issues
- planner outcome declaration using `READY`, `BLOCKED`, or `ESCALATION_REQUIRED`
- initial sequencing, dependency metadata, and generated issue content for `READY`

Feature Architect owns:

- implementation handoff for one sufficiently scoped issue
- identification of issue-level implementation risks, blockers, missing context, and oversize scope

Handler owns:

- workflow label mutation
- dispatch eligibility
- locking
- dependency gating
- automatic workflow transitions
- preservation of exactly one primary `state:*` label per issue

## Return and Escalation Paths

Systems Architect to Roadmap Updater:

- Triggered when a human accepts a Systems Architect recommendation by applying `state:ready-for-roadmap-update`.
- Roadmap Updater synchronizes documentation and creates a documentation-only pull request.

Roadmap Updater to Implementation Planner:

- Triggered only after accepted documentation is reviewed and merged.
- A human may apply `state:ready-for-implementation-planning` to route documented strategy into planning.

Implementation Planner to Systems Architect:

- Used when planning would force unresolved systems-level decisions.
- Planner declares `ESCALATION_REQUIRED`, creates no generated issues by default, and recommends human routing to `state:systems-architecture-changes-requested`.

Implementation Planner to Implementation Planner follow-up:

- Used when a generated plan needs revision but no new systems architecture decision is required.
- Planner or human review should recommend `state:implementation-planning-changes-requested`.

Feature Architect to human/Handler routing:

- Used when one issue is too broad, too risky, blocked, under-specified, or actually requires implementation planning before implementation architecture.
- Feature Architect should leave a structured recommendation for human/Handler routing instead of changing labels directly.

## Classification Vocabulary

Use these fields as advisory language in comments and artifacts before any runtime behavior depends on them.

`implementation_complexity`: technical difficulty and expected reasoning or coding effort.

`safety_risk`: likelihood and impact of harmful changes, data loss, source-of-truth corruption, unsafe automation, or difficult rollback.

`slice_size`: breadth of scope and whether the work contains multiple independently valuable implementation units.

`architecture_uncertainty`: whether execution would force systems-level decisions not yet accepted.

These dimensions are intentionally separate. A change can be low implementation complexity and high safety risk, or technically moderate but too broad for one implementation slice.

## Advisory Classification Block

When classification materially affects routing, decomposition, or review depth, agents may include a concise block like this in comments or artifacts:

```yaml
workflow_classification:
  implementation_complexity: low | medium | high
  safety_risk: low | medium | high
  slice_size: single_slice | broad | multi_slice
  architecture_uncertainty: none | minor | significant
  routing_recommendation: continue | split | block | escalate
```

This block is optional guidance, not a dispatch contract. Handler should not depend on it until a later approved runtime capability validates and preserves it.

## Deferred Routing Automation

Future automation may add:

- optional structured classification blocks in architecture and planning artifacts
- Handler validation of classification blocks
- model, effort, and reviewer-depth routing based on observed reliability
- additional review gates only after the manual doctrine proves useful
- Watchtower traceability for accepted recommendation comment URLs and routing decisions

Automation should remain deferred until the runtime can reliably observe, inspect, recover, and preserve the decisions that would drive routing.

## Guardrails

- Do not introduce hidden routing behavior before it is documented and approved.
- Do not add workflow labels solely to represent planner outcomes or classification fields.
- Do not let agents bounce issues between roles without human-visible recommendations.
- Keep return paths human-reviewed and Handler-mediated.
- Prefer explicit blocker, escalation, or routing comments over implicit workflow inference.

