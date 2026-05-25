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
- state:ready-for-architect
- state:ready-for-randy
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
- Added explicit `--repo` handling
- Added startup observability
- Replaced gh label filtering with Python filtering
- Added model/effort routing metadata
- Refactor main.py into real entrypoint

## Next Likely Tasks

1. Create launch brief artifact generation.
2. Pass launch brief artifact path to developer agent.
3. Expand developer role doctrine.
4. Add configurable workspace root.
5. Explore subprocess execution.