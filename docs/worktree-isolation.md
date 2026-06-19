# Worktree Isolation Architecture

Issue #30 accepted Git worktrees as the primary isolation mechanism for normal mutation-capable agent execution in The Circus.

This document records the approved Systems Architect recommendation for roadmap and implementation planning. It is not an implementation specification for every future workflow mode.

## Decision

The Circus should stop treating `CIRCUS_TARGET_REPO_PATH` as the shared execution workspace for developer-style runs.

`CIRCUS_TARGET_REPO_PATH` remains the canonical local repository for startup validation and as the source repository for worktree creation. Agent runs that can mutate repository files should receive an explicit resolved workspace path and execute from that path.

## Workspace Layout

The accepted workspace model is:

```text
<CIRCUS_TARGET_REPO_PATH>                         # canonical repository and worktree source
<CIRCUS_WORKTREE_ROOT>/<repo-slug>/issue-30/      # issue-owned mutable workspace
<CIRCUS_WORKTREE_ROOT>/<repo-slug>/pr-30/         # PR-owned review/follow-up workspace when needed
```

`CIRCUS_WORKTREE_ROOT` should be configurable. If omitted, it should default to a sibling directory of the target repository, for example:

```text
<target-parent>/<target-repo-name>-worktrees
```

The repository slug should be sanitized from `owner-repo`, lowercased, and restricted to ASCII letters, digits, hyphen, and underscore. Item workspace names should be deterministic, using `issue-<number>` or `pr-<number>`.

## Workspace Unit

The first architectural unit is per issue or per pull request.

The Circus should not create separate worktrees per role or per workflow run in the first implementation. Current workflow locking already limits one active workflow step per item, and per-run worktrees would add cleanup and branch-management complexity before stale-run recovery exists.

Role-level or run-level worktrees can be considered later if same-item parallelism becomes a real workflow requirement.

## Lifecycle Rules

Worktree lifecycle should be explicit and inspectable:

- Create: resolve the base branch, create or reuse the Circus branch, then add a worktree at the deterministic workspace path.
- Reuse: allow only when `git worktree list --porcelain` shows a registered worktree at the expected path, on the expected branch, with a clean working tree.
- Reset: do not silently reset dirty worktrees in v1.
- Remove: remove only clean, registered worktrees through an explicit cleanup path.
- Block: dirty or unregistered directories should require human inspection.
- Record: Watchtower status and launch briefs should record workspace path, workspace branch, item identity, run directory, and lifecycle outcome.

## Initial Workflow Scope

The first implementation should cover Developer and Roadmap Updater launches.

Those modes are the highest-risk shared-workspace users because they create branches, write files, commit, push, and open pull requests. They should execute from item worktrees instead of directly from `CIRCUS_TARGET_REPO_PATH`.

Architect, Systems Architect, Reviewer, and Architect Review modes may continue using the main target repository briefly if they remain read-oriented. However, all launch paths should route through the same workspace resolver so these modes can later move to resolver-managed base or read-only workspaces without another boundary change.

Architect base-branch checkout remains a follow-up candidate because it can still mutate shared checkout state.

## Integration Points

The first implementation is expected to touch these areas:

- `Handler/git_workspace.py`: evolve branch-preparation helpers into a workspace service that resolves roots, sanitizes path parts, inspects registered worktrees, creates or reuses worktrees, blocks unsafe states, and returns structured workspace results.
- `Handler/handler.py`: store the resolved workspace path and branch on the workflow item, write them to launch briefs, pass them to agent command builders and subprocess working directories, and preserve them through finalization.
- `Handler/developer_flow.py`: finalize commits and pull requests from the resolved workspace path.
- `Handler/watchtower.py`: include `workspace_path`, `workspace_branch`, and `workspace_lifecycle` in run status and result artifacts.
- `Handler/paths.py`: reuse or extend existing path sanitization instead of adding ad hoc naming rules.
- `main.py`: validate the target repository as the worktree source, validate or create the configured worktree root, and log the resolved root clearly.

## First Implementation Acceptance Criteria

- `CIRCUS_WORKTREE_ROOT` is configurable, with a deterministic default.
- Developer and Roadmap Updater runs execute in item worktrees rather than directly in `CIRCUS_TARGET_REPO_PATH`.
- Launch briefs and Watchtower status include the resolved workspace path and branch.
- Existing Circus branch naming remains compatible with current PR creation behavior.
- Dirty-worktree blocking semantics are preserved.
- The main target repository branch is not switched during Developer or Roadmap Updater prelaunch.
- Tests cover path sanitization, create/reuse decisions, dirty blocking, and PR finalization from the resolved workspace.

## Deferred Work

Cleanup automation is intentionally deferred until stale-lock and run recovery are designed.

Later work should add stale worktree detection/reporting by comparing Watchtower metadata with `git worktree list --porcelain`, GitHub workflow lock state, and run outcomes.
