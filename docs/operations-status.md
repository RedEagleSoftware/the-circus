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

- Added explicit target repository workspace configuration.
- Synchronized required workflow labels to target repositories.
- Define issue-level shared handoff artifacts.
- Pass launch brief and handoff context to developer agent
- Create v1 orchestration proposal/specification document.
- Expand architect role doctrine.
- 
## Current Task

- Enable architect execution flow.


## Next Likely Tasks

1. Generate architecture handoff artifacts from architect runs.
2. Route developer implementation context through architecture handoffs.
3. Add agent result/status artifacts to Watchtower runs.
4. Add target-repo instruction discovery conventions.
5. Explore broader subprocess execution patterns.