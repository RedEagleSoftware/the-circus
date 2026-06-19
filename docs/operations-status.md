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
- Durable polling and stale-lock/run recovery need to be hardened.
- No artifact contract that records the accepted GitHub Systems Architect recommendation comment URL/ID in Watchtower run history.
- No persistent Watchtower visibility beyond local run artifacts.

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
- Git worktrees are the accepted isolation mechanism for Developer and Roadmap Updater execution, with per-item worktrees as the first implementation unit

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

- Implement workspace path resolution and Watchtower/launch-brief recording for issue-owned worktrees.


## Next Likely Tasks

- Add target repo initialization command (`python main.py --init`).
- Add Developer and Roadmap Updater execution from item worktrees.
- Harden durable polling and stale-lock/run recovery.
- Add stale worktree detection/reporting as part of stale-lock/run recovery.
- Add persistent Watchtower visibility for active and recent runs.
- Record accepted GitHub Systems Architect recommendation comment URLs/IDs in Watchtower run history for traceability.

## Future Roadmap Ideas

- Parallel/multi-issue dispatch.
- Human review / merge-complete workflow automation.
- Provider capability detection.
- Configurable agent provider routing after self-hosting reliability improves.
- Convert role doctrine/reusable workflows into skills after reliable execution and provider routing are stable.
- Watchtower dashboard.
