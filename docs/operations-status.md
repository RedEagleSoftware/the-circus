# The Circus Operations Log

## Current State

### Handler
- Polling loop operational
- Explicit repo targeting working
- Local label filtering working
- Lock acquisition working
- One-dispatch-then-exit behavior operational
- Startup observability added
- Codex launch prompt/context generation operational for Systems Architect, Roadmap Updater, Reviewer, and Architect Review modes
- Per-run Watchtower status/result artifacts operational
- Roadmap Updater workflow available for documentation-only synchronization after accepted Systems Architect recommendations
- Worktree isolation for mutation-capable execution is partially implemented with deterministic workspace root/path resolution, launch/status metadata capture, and fresh-base worktree branch preparation
- Worktree-aware execution/finalization is in place for mutation-capable flows (including Developer, Roadmap Updater, and Implementation Planner), with broader read-only adoption and cleanup/recovery integration still pending
- Workspace inventory and lifecycle classification are implemented as a read-only service with conservative `blocked-unsafe` handling, dirty workspace detection, and upstream/PR relationship signals
- Lifecycle diagnostics reporting is implemented for human/operator visibility and remains reporting-only (not yet a recovery or cleanup command)
- Implementation Planning is partially implemented as a review-gated workflow with canonical states/labels, planner dispatch, artifact handling, outcome parsing/validation (`READY`, `BLOCKED`, `ESCALATION_REQUIRED`), and plan-review advancement for `READY`
- Planner-generated issue linkage and recommendation traceability are partially surfaced in Watchtower artifacts

### Organizational Maturity
- Organizational maturity frontier from issue #84 is accepted strategy: workflow-governance parity, accepted-decision traceability, recovery baseline, human decision ledger, and lightweight metrics
- Runtime support is partial; governance parity and full enforcement across doctrine/labels/dispatch/human-owned states remain implementation work

## Future Watchtower Concept

- Local UI for observing active and recent agent runs.
- Initial mental model is a four-pane operations view.
- Each pane shows one agent role’s active run, logs, status, and current GitHub item.
- Could be implemented as:
  - local web app
  - terminal UI
  - native desktop app
  - Zellij/tmux layout as an interim version
- Purpose is observability, not autonomous control.

### Current Workflow Labels
- state:ready-for-architecture
- state:ready-for-systems-architecture
- state:systems-architecture-changes-requested
- state:ready-for-roadmap-update
- state:ready-for-implementation-planning
- state:ready-for-implementation-plan-review
- state:implementation-planning-changes-requested
- state:planned
- state:ready-for-dev
- state:ready-for-review
- state:ready-for-architect-review
- state:ready-for-human-review
- state:changes-requested
- state:blocked
- state:agent-in-progress

## Current Known Gaps
- Repository onboarding is still manual; no target repo initialization command yet.
- Durable polling and stale-lock/run recovery need to be hardened.
- Worktree lifecycle recovery/cleanup integration is not complete; current lifecycle implementation is inventory/diagnostics-first and conservative.
- Recommendation traceability exists in part, but a consistent artifact contract for accepted decision references is still incomplete.
- No persistent Watchtower visibility beyond local run artifacts.
- Implementation Planner still has gaps around deeper generated-issue validation, dependency enforcement, and end-to-end generated issue creation when not already present in approved plans.
- Workflow-governance parity across doctrine, labels, Handler dispatchability, and unsupported-state handling remains an accepted maturity gap.
- Human decision ledger artifacts and lightweight organizational metrics are accepted but not yet fully implemented.

## Current Architectural Decisions
- GitHub labels are source of truth
- Explicit repo targeting required
- Thin prompts; thick doctrine
- One workflow step per launch
- Human review mandatory
- No auto-merge
- No DB
- No webhook/event bus yet
- Systems Architect recommendations are reviewed in GitHub issue comments
- Roadmap Updater synchronizes documentation only after human-approved strategy
- Implementation Planner converts accepted documented strategy into generated issues only after roadmap synchronization and human review gating
- Git worktrees are the accepted isolation mechanism for Developer and Roadmap Updater execution, with per-item worktrees as the first implementation unit
- Worktree and branch lifecycle management should be inventory-first, non-destructive by default, and human-approved before cleanup
- The lifecycle inventory service should separate raw fact collection from classification policy, return explicit reasons and ambiguity signals, and treat uncertainty as `blocked-unsafe`
- Organizational maturity work follows the issue #84 frontier: governance parity, accepted-decision traceability, recovery baseline, human decision ledger, and lightweight metrics
- Metrics are visibility/review inputs only, not autonomous control signals

## Maintenance Rules

- Move completed items from "Next Likely Tasks" into "Last Completed Work".
- Keep "Last Completed Work" focused on recent operational history (~5 items).
- When "Next Likely Tasks" drops below ~2 items, schedule a new planning/review session.
- Prefer updating existing operational context over creating excessive historical records.

## Last Completed Work

- Add Roadmap Updater workflow for approved strategic recommendations.
- Require repository-context validation for Systems Architect recommendations.
- Ensure architect runs inspect the target repo base branch
- Create pull requests automatically.
- Set up review flow.
- Set up architect review flow.
 
## Current Task

- Reconcile this operations status document with currently implemented runtime capabilities and accepted issue #84 strategy.
- Decompose next implementation slices across governance parity, accepted-decision traceability completion, recovery baseline, human decision ledger, metrics seed, and remaining lifecycle recovery integration.


## Next Likely Tasks

- Implement workflow-governance parity checks across doctrine, labels, Handler dispatchability, human-owned states, and unsupported-state handling.
- Complete accepted-decision traceability artifact contract for Watchtower run history.
- Implement a conservative recovery baseline for stale locks/runs using existing lifecycle inventory/classification diagnostics.
- Define and implement a lightweight human decision ledger artifact contract.
- Seed lightweight organizational metrics for visibility/review (non-control).
- Add target repo initialization command (`python main.py --init`).
- Add lifecycle inventory and stale worktree detection/reporting as part of stale-lock/run recovery after the read-only classification service exists.
- Add dry-run cleanup reporting for retired and stale-clean workspaces only.
- Add persistent Watchtower visibility for active and recent runs.
- Add deeper implementation planner validation and dependency enforcement for generated implementation issues.

## Future Roadmap Ideas

- Parallel/multi-issue dispatch.
- Human review / merge-complete workflow automation.
- Provider capability detection.
- Configurable agent provider routing after self-hosting reliability improves.
- Convert role doctrine/reusable workflows into skills after reliable execution and provider routing are stable.
- Watchtower dashboard.
