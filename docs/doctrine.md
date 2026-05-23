# The Circus Operational Doctrine

## Principles
- **Prompts should be thin**: Agent identity and behavior live in markdown files.
- **GitHub labels drive state**: GitHub is the state machine/source of truth.
- **Transparency**: Agents should be transparent when metadata or context is unavailable.
- **Gradual Automation**: Start manual/semi-manual first, then automate.
- **No Auto-merge**: Human review is critical.
- **Locking**: Use `state:agent-in-progress` to prevent duplicate work.

## Execution Principles

- Handler must not rely on the current working directory for repository context.
- All GitHub operations should explicitly specify the target repository.
- `CIRCUS_REPO` is the authoritative orchestration target.
- Orchestration behavior should be deterministic and inspectable.
- Prefer explicit command arguments over implicit environment inference.

## Workflow States
- `state:ready-for-architecture` -> Codex Architect
- `state:ready-for-dev` -> Junie Developer
- `state:ready-for-review` -> Codex PR Reviewer
- `state:ready-for-architect` -> Codex Architect Approval
- `state:ready-for-randy` -> Human Review

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
- Agents execute one workflow step at a time.
- Agents must not auto-merge.
- Agents must not silently change workflow labels except through documented transitions.
- Agents must leave GitHub comments explaining what they did.
- Agents must stop and report missing metadata instead of guessing.

## State Rules

- Each issue/PR should have exactly one primary `state:*` label.
- `state:agent-in-progress` is a lock label and may coexist with one primary state.
- `state:blocked` is terminal until a human removes it.
- `state:ready-for-randy` is human-owned and should not be dispatched automatically.
- `state:changes-requested` routes back to development.
