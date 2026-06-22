# Worktree and Branch Lifecycle Management

Issue #51 accepted Worktree and Branch Lifecycle Management as the next Self Hosting reliability capability.

This document records the approved Systems Architect recommendation for roadmap synchronization and follow-on implementation planning. It defines the lifecycle vocabulary and safety boundaries that future Handler, Watchtower, and operator tooling should use when inspecting or recovering Circus workspaces.

## Decision

The Circus should formalize worktree and branch lifecycle management around one conservative invariant:

```text
one GitHub item -> one deterministic workspace -> one expected Circus branch -> zero or one open PR
```

GitHub remains the source of truth for workflow state and human decisions. Git remains the source of truth for repository, worktree, and branch facts. Watchtower records run history, workspace metadata, lifecycle classifications, and recovery diagnostics, but it must not become the authority for lifecycle state or cleanup decisions.

The first implementation should prioritize detection, classification, reporting, and narrow non-destructive repair. It should not automate destructive cleanup.

## Lifecycle States

Workspaces should be classified with explicit, inspectable states:

- `planned`: Handler has resolved the deterministic workspace identity, but no worktree is required yet.
- `ready`: the expected registered worktree exists, is on the expected branch, contains the latest required base, and is clean.
- `active`: the GitHub item has `state:agent-in-progress`; automatic cleanup and branch mutation are prohibited.
- `suspended`: the agent exited non-zero, launch failed after lock acquisition, credits were exhausted, or Handler stopped before finalization completed. Preserve the workspace and branch exactly.
- `recoverable`: the workspace contains committed-but-unpushed changes, uncommitted changes, missing upstream tracking, or an open PR relationship that can be repaired without deleting data.
- `stale-clean`: the workspace is clean, no lock is active, no open PR depends on the branch, and the branch or worktree is behind the current base or no longer belongs to an active workflow.
- `retired`: the linked PR is merged or the issue is closed completed, and local workspace state is clean.
- `cleanup-eligible`: a `retired` or `stale-clean` workspace after an explicit inventory pass and dry-run report.
- `blocked-unsafe`: an unregistered directory, unexpected branch, dirty stale worktree, ambiguous upstream, inaccessible GitHub metadata, or any state where deletion or reset could lose work.

The state model is intentionally conservative. Dirty, ambiguous, unpushed, PR-linked, and active workspaces are not cleanup targets.

## Branch Lifecycle

Branch handling should remain explicit and predictable:

- Create issue branches from the latest resolved remote base ref.
- Preserve the existing `circus/issue-<number>-<title-slug>` branch pattern.
- Set or repair upstream tracking only when the local branch name exactly matches the expected issue branch and the remote branch is absent or points to compatible history.
- Treat committed-but-unpushed work as `recoverable`, not stale.
- Treat open PR branches as protected from cleanup even when the worktree is clean.
- Reuse a branch and worktree only when workspace path, registered worktree metadata, current branch, cleanliness, base freshness, and item identity all agree.
- Never reset, delete, or recreate a dirty or ambiguous workspace automatically in the first implementation.

## Inventory-First Recovery

Recovery should start by building a workspace inventory from:

- `git worktree list --porcelain`
- local branch state
- remote branch state
- `git status --porcelain`
- upstream tracking
- open PR relationships
- current GitHub workflow labels
- recent Watchtower run status

Every workspace should be classified using the lifecycle states before any repair or cleanup decision is made.

The diagnostic output should be human-readable and should identify the facts that led to each classification. Automatic repair is allowed only for narrow, non-destructive cases such as missing upstream tracking where branch identity and history are unambiguous.

Human approval is required for any action that deletes, resets, force-pushes, rebases, removes a branch, removes a worktree, or otherwise risks losing work.

## Recovery Scenarios

The lifecycle model should cover these scenarios:

- Agent interrupted during execution: classify as `suspended` or `recoverable` depending on run outcome and workspace state; preserve files and branch.
- Agent exits unexpectedly: preserve workspace, record diagnostics, and require inventory classification before relaunch or cleanup.
- Credit exhaustion: classify as `suspended`; preserve the exact workspace and branch for continuation or inspection.
- Handler restart: rebuild inventory from Git, GitHub, and Watchtower facts before relaunching work.
- Existing uncommitted changes: classify as `recoverable` or `blocked-unsafe`; do not reset automatically.
- Existing committed-but-unpushed changes: classify as `recoverable`; do not treat as stale.
- Missing upstream tracking: allow narrow repair only when expected branch identity and compatible history are unambiguous.
- Existing open PR: protect the branch and worktree from cleanup until the PR relationship is resolved.
- Unregistered or unexpected directory: classify as `blocked-unsafe`; require human inspection.

## Cleanup Safety Boundary

V1 may automate lifecycle detection, diagnostics, and reporting. V1 should not automate destructive cleanup.

Cleanup should begin as:

1. An explicit inventory command.
2. A dry-run cleanup report.
3. A reviewed manual cleanup command path for clean registered worktrees only.

Cleanup must be prohibited for:

- active items
- dirty worktrees
- committed-but-unpushed work
- ambiguous upstreams
- unexpected branches
- unregistered directories
- inaccessible GitHub metadata
- branches with open PRs
- any state classified as `recoverable`, `suspended`, or `blocked-unsafe`

## Responsibility Boundaries

Handler owns workflow dispatch, lock acquisition, workspace preparation, workflow label transitions, post-run validation, and any future lifecycle classification that affects dispatch eligibility.

Watchtower records lifecycle facts, diagnostics, recommendation links, run history, and operator-visible reports. Watchtower remains observational and does not become the cleanup authority.

Human operators approve cleanup and any destructive or history-rewriting action.

Roadmap Updater records accepted strategic decisions in documentation only. It must not mutate workflow labels, runtime behavior, or cleanup state.

## Follow-On Implementation Sequence

1. Document the lifecycle state model and safety rules in this dedicated lifecycle document.
2. Add a workspace inventory and classification service that combines Git worktree metadata, branch and upstream state, open PR state, workflow labels, and Watchtower run status.
3. Add an operator-facing lifecycle diagnostic command or report with no mutations.
4. Add non-destructive recovery helpers for missing upstream tracking and clear interrupted-run diagnostics.
5. Add stale-lock and run recovery integration that classifies `suspended` and `recoverable` workspaces before relaunch.
6. Add a dry-run cleanup command for `retired` and `stale-clean` workspaces only.
7. Add a reviewed cleanup execution path for clean registered worktrees, with no dirty or ambiguous deletion.
8. Record accepted Systems Architect recommendation comment URLs and IDs in Watchtower run history for traceability.

## Relationship To Worktree Isolation

[Worktree Isolation](worktree-isolation.md) defines deterministic per-item workspaces and the first mutation-capable execution boundary.

This lifecycle model defines how those workspaces and their branches should be classified, recovered, retired, and eventually cleaned up without losing agent-generated work.
