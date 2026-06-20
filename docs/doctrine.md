# The Circus Operational Doctrine

## Control Document Rules

- `docs/doctrine.md` is operator-owned.
- `docs/operations-status.md` is operator-owned.
- Implementation agents may read these files for context.
- Implementation agents must not directly edit these files unless the prompt explicitly authorizes it.
- Agents may propose changes to operator-owned documents in a separate proposal artifact.
- Usage instructions should live in README or dedicated docs, not in operational status unless explicitly requested.

## Principles

- **Prompts should be thin**: Agent identity and behavior live in markdown files.
- **GitHub labels drive state**: GitHub is the state machine/source of truth.
- **Transparency**: Agents should be transparent when metadata or context is unavailable.
- **Gradual Automation**: Start manual/sei-manual first, then automate.
- **No Auto-merge**: Human review is critical.
- **Locking**: Use `state:agent-in-progress` to prevent duplicate work.

## Learning Principles

- Agents may append issue-specific running notes.
- Agents may propose updates to role or project guidance.
- Agents must not silently modify their own role definitions.
- Durable learning should be reviewed before becoming doctrine.
- Prefer explicit proposed updates over hidden behavioral drift.

## Workspace Principles

- Handler is launched from The Circus repository.
- The target repository is configured explicitly.
- `CIRCUS_REPO` identifies the GitHub repository.
- `CIRCUS_TARGET_REPO_PATH` identifies the local working copy.
- Agents should operate from the target repository path, not from The Circus repository.
- Handler should not infer target workspace from its own current working directory.

## Execution Principles

- Handler must not rely on the current working directory for repository context.
- All GitHub operations should explicitly specify the target repository.
- `CIRCUS_REPO` is the authoritative orchestration target.
- Orchestration behavior should be deterministic and inspectable.
- Prefer explicit command arguments over implicit environment inference.
- Prefer a fresh agent session for each distinct workflow task.
- Durable markdown artifacts and GitHub metadata should carry context between sessions.
- Agents should not rely on long-lived conversational memory for orchestration correctness.

## Observability Principles

- Orchestration behavior should be visible and inspectable.
- Workflow transitions should leave durable operational artifacts.
- Prefer transparent logs and artifacts over hidden automation state.
- Watchtower exists to observe before it controls.

## Handoff Artifact Principles

- Agents should not overwrite GitHub issue bodies as part of normal handoff.
- The GitHub issue remains the original work request and workflow discussion.
- Agent-produced guidance for later agents should be written as issue-level shared artifacts.
- Single-run logs/results belong inside that run’s folder.
- Shared handoff artifacts should be referenced by later launch briefs.

## Workflow States

- `state:ready-for-architecture` -> Codex Architect
- `state:ready-for-dev` -> Junie Developer
- `state:ready-for-review` -> Codex PR Reviewer
- `state:ready-for-architect-review` -> Codex Architect Approval
- `state:ready-for-systems-architecture` -> Codex Systems Architect
- `state:systems-architecture-changes-requested` -> Codex Systems Architect follow-up
- `state:ready-for-roadmap-update` -> Codex Roadmap Updater
- `state:ready-for-implementation-planning` -> Codex Implementation Planner
- `state:ready-for-implementation-plan-review` -> Human implementation plan review
- `state:implementation-planning-changes-requested` -> Codex Implementation Planner follow-up
- `state:planned` -> Non-dispatch generated implementation issue state
- `state:dependency-blocked` -> Handler-managed dependency wait state
- `state:ready-for-human-review` -> Human Review

## Tool Stack

- GitHub Repo/Issues/PRs/Labels
- `gh` CLI
- Codex CLI
- Junie CLI

## Engineering Biases

- Prefer boring, inspectable implementation over clever automation.
- Prefer polling before webhooks.
- Prefer local files before databases.
- Prefer explicit labels before inferred state.
- Prefer readable subprocess calls before SDK abstractions.
- Prefer comments/logs over hidden behavior.
- Avoid background daemons until the manual workflow is proven.

## Agent Boundaries

- Handler dispatches work; it does not decide product direction.
- Each agent invocation should own exactly one workflow transition.
- Agents must not auto-merge.
- Agents must not silently change workflow labels except through documented transitions.
- Agents must leave GitHub comments explaining what they did.
- Agents must stop and report missing metadata instead of guessing.

## Concurrency Principles

- Multiple agents must not operate in the same workspace simultaneously.
- Concurrency should be intentionally bounded.
- Prefer operational clarity over maximum throughput.

## State Rules

- Each issue/PR should have exactly one primary `state:*` label.
- `state:agent-in-progress` is a lock label and may coexist with one primary state.
- `state:blocked` is terminal until a human removes it.
- `state:dependency-blocked` is non-dispatchable and may be automatically replaced with its declared `resume_state` only when Handler verifies all declared dependencies are satisfied.
- `state:ready-for-human-review` is human-owned and should not be dispatched automatically.
- `state:changes-requested` routes back to development.
