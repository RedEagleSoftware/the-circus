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
- Worktree isolation architecture accepted for mutation-capable agent execution; implementation not yet started
- Worktree and branch lifecycle architecture accepted for conservative inventory, recovery, and cleanup safety; implementation not yet started
- Workspace inventory and lifecycle classification accepted as the first read-only lifecycle implementation slice; implementation not yet started
- Implementation Planning architecture accepted as a review-gated bridge from roadmap updates to generated implementation issues; implementation not yet started
- Organizational maturity frontier accepted for workflow governance parity, accepted-decision traceability, recovery baseline, human decision management, and lightweight organizational metrics; implementation not yet started

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
- Worktree isolation is documented but not implemented for repeated self-hosted runs.
- Worktree and branch lifecycle classification is documented and accepted as a read-only inventory/classification service, but not implemented.
- Durable polling and stale-lock/run recovery need to be hardened.
- Accepted workflow states, roadmap documentation, canonical labels, and Handler state support need an explicit parity contract and enforcement path.
- No artifact contract that records the accepted GitHub Systems Architect recommendation comment URL/ID in Watchtower run history.
- No persistent Watchtower visibility beyond local run artifacts.
- Implementation Planner workflow, canonical labels, generated issue validation, and plan-review transition are documented but not implemented.
- Human-owned workflow states do not yet have a consistent decision artifact contract, source reference, next-state options, or stale-decision detection.
- No lightweight organizational metrics loop yet for run outcomes, blocker classes, review churn, recovery events, or planning-to-implementation traceability.

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
- The active self-hosting frontier should be treated as an organizational maturity program before provider routing, skills, broad parallel dispatch, or model/resource optimization.
- Workflow governance parity should reconcile accepted doctrine, roadmap state lists, canonical labels, Handler dispatchability, human-owned states, and unsupported-state handling.
- Strategic memory should preserve accepted recommendation, roadmap PR, planner issue, generated issue, and outcome references without making Watchtower the source of truth.
- Organizational metrics should begin as inspectable visibility and review data, not automatic routing or control signals.

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

- Synchronize roadmap and capability documentation with the accepted organizational maturity frontier from issue #84.
- Then decompose workflow governance parity, accepted-decision traceability, recovery baseline, human decision ledger, and organizational metrics seed into independently valuable implementation slices.


## Next Likely Tasks

- Add target repo initialization command (`python main.py --init`).
- Add Developer and Roadmap Updater execution from item worktrees.
- Document and enforce workflow governance parity between accepted workflow states, label sync, Handler dispatchability, human-owned states, and unsupported-state handling.
- Harden durable polling and stale-lock/run recovery.
- Add lifecycle inventory and stale worktree detection/reporting as part of stale-lock/run recovery after the read-only classification service exists.
- Add dry-run cleanup reporting for retired and stale-clean workspaces only.
- Add persistent Watchtower visibility for active and recent runs.
- Record accepted GitHub Systems Architect recommendation comment URLs/IDs in Watchtower run history for traceability.
- Add Implementation Planner dispatch, generated issue creation in `state:planned`, and plan-review transitions.
- Add a human decision artifact contract for roadmap acceptance, implementation-plan approval, generated issue dispatch approval, stale plans, and change-request loops.
- Add lightweight organizational metrics for run outcomes, blockers, recovery events, review changes requested, and plan churn.

## Future Roadmap Ideas

- Parallel/multi-issue dispatch.
- Human review / merge-complete workflow automation.
- Provider capability detection.
- Configurable agent provider routing after self-hosting reliability improves.
- Convert role doctrine/reusable workflows into skills after reliable execution and provider routing are stable.
- Watchtower dashboard.
