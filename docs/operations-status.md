# The Circus Operations Log

## Current State

### Handler
- Polling loop operational
- Explicit repo targeting working
- Local label filtering working
- Lock acquisition working
- One-dispatch-then-exit behavior operational
- Startup observability added

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
- state:ready-for-dev
- state:ready-for-review
- state:ready-for-architect-review
- state:ready-for-human-review
- state:changes-requested
- state:blocked
- state:agent-in-progress

## Current Known Gaps
- Codex launch prompt/context not implemented
- No subprocess execution yet
- No worktree isolation
- No artifact contract system
- No persistent Watchtower visibility

## Current Architectural Decisions
- GitHub labels are source of truth
- Explicit repo targeting required
- Thin prompts; thick doctrine
- One workflow step per launch
- Human review mandatory
- No auto-merge
- No DB
- No webhook/event bus yet

## Maintenance Rules

- Move completed items from "Next Likely Tasks" into "Last Completed Work".
- Keep "Last Completed Work" focused on recent operational history (~5 items).
- When "Next Likely Tasks" drops below ~2 items, schedule a new planning/review session.
- Prefer updating existing operational context over creating excessive historical records.

## Last Completed Work

- Ensure architect runs inspect the target repo base branch
- Create pull requests automatically.
- Set up review flow.
- Set up architect review flow.
- Add per-run result/status artifacts to Watchtower runs.
- Refactor Handler into focused modules.
- Add target-repo instruction discovery and context-loading conventions.
 
## Current Task


## Next Likely Tasks

- Add durable per-issue workflow step tracking for long-running polling.
- Add target repo initialization command (`python main.py --init`).
- Add configurable agent provider routing.
- Explore converting role doctrine/reusable workflows into skills.
- Refactor Handler into focused modules. (round 2)

## Future Roadmap Ideas

- Parallel/multi-issue dispatch.
- Stale lock detection and recovery.
- Human review / merge-complete workflow automation.
- Provider capability detection.
- Watchtower dashboard.
