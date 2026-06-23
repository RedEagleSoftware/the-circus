import os

from Handler import git_workspace


WORKSPACE_LIFECYCLE_STATES = {
    "planned",
    "ready",
    "active",
    "suspended",
    "recoverable",
    "stale-clean",
    "retired",
    "cleanup-eligible",
    "blocked-unsafe",
}

DEFAULT_BRANCH_SLUG_LENGTH = 60


def parse_git_worktree_porcelain(output):
    entries = []
    current = {}

    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue

        key, _, value = line.partition(" ")
        value = value.strip() if value else ""

        normalized_key = key.lower()
        if normalized_key == "worktree":
            if current:
                entries.append(current)
                current = {}
            current["worktree"] = value
            continue

        if normalized_key in {"bare", "detached"}:
            current[normalized_key] = True
            continue

        if normalized_key in {"locked", "prunable"}:
            current[normalized_key] = True
            if value:
                current[f"{normalized_key}_reason"] = value
            continue

        if value:
            current[normalized_key] = value

    if current:
        entries.append(current)

    return entries


def _normalize_path(path):
    if path is None:
        return None
    return os.path.normcase(os.path.normpath(path))


def _run_git(path, git_args, run_git_command, log):
    result = run_git_command(path, git_args)
    if result is None:
        log(f"[WorkspaceInventory] Git command returned no result: {' '.join(['git', *git_args])}")
    return result


def _extract_label_names(labels):
    if labels is None:
        return []

    names = []
    for label in labels:
        if isinstance(label, dict):
            name = label.get("name")
        else:
            name = label
        if name:
            names.append(str(name))
    return names


def _derive_expected_branch(item, build_expected_branch_name):
    try:
        return build_expected_branch_name(item)
    except TypeError:
        return build_expected_branch_name(
            item,
            max_branch_slug_length=DEFAULT_BRANCH_SLUG_LENGTH,
            slugify=git_workspace.slugify_branch_title,
        )


def _has_open_pr_relationship(open_pr):
    if not open_pr:
        return False

    if not isinstance(open_pr, dict):
        return True

    state = str(open_pr.get("state") or "").lower()
    if state in {"merged", "closed"}:
        return False
    if state in {"open", "draft"}:
        return True

    if open_pr.get("url"):
        return True

    for key in ("number", "id", "node_id"):
        if open_pr.get(key) is not None:
            return True

    return True


def collect_workspace_inventory(
    repo_path,
    workspace_path,
    item=None,
    *,
    expected_branch=None,
    workflow_labels=None,
    github_item=None,
    open_pr=None,
    watchtower_run=None,
    run_git_command=git_workspace.run_git_command_in_repo,
    build_expected_branch_name=git_workspace.build_developer_branch_name,
    path_exists=os.path.exists,
    log=print,
):
    metadata_available = True

    if expected_branch is None and isinstance(item, dict):
        item_type = str(item.get("type") or "").lower()
        if item_type == "issue" and item.get("number") is not None:
            expected_branch = _derive_expected_branch(item, build_expected_branch_name)

    worktree_result = _run_git(repo_path, ["worktree", "list", "--porcelain"], run_git_command, log)
    if worktree_result is None or worktree_result.returncode != 0:
        metadata_available = False
        registered_worktrees = []
    else:
        registered_worktrees = parse_git_worktree_porcelain(worktree_result.stdout)

    normalized_workspace_path = _normalize_path(workspace_path)
    registered_entry = None
    for entry in registered_worktrees:
        if _normalize_path(entry.get("worktree")) == normalized_workspace_path:
            registered_entry = entry
            break

    workspace_path_exists = None
    if workspace_path:
        try:
            workspace_path_exists = bool(path_exists(workspace_path))
        except OSError:
            metadata_available = False

    should_probe_workspace_git = registered_entry is not None

    branch_result = None
    if should_probe_workspace_git:
        branch_result = _run_git(workspace_path, ["rev-parse", "--abbrev-ref", "HEAD"], run_git_command, log)
    if branch_result is None and should_probe_workspace_git:
        current_branch = None
        detached_head = None
        metadata_available = False
    elif should_probe_workspace_git and branch_result.returncode != 0:
        current_branch = None
        detached_head = None
        metadata_available = False
    else:
        if should_probe_workspace_git:
            branch_name = (branch_result.stdout or "").strip() or None
            current_branch = None if branch_name == "HEAD" else branch_name
            detached_head = branch_name == "HEAD"
        else:
            current_branch = None
            detached_head = None

    status_result = None
    if should_probe_workspace_git:
        status_result = _run_git(workspace_path, ["status", "--porcelain"], run_git_command, log)
    if status_result is None and should_probe_workspace_git:
        workspace_clean = None
        metadata_available = False
    elif should_probe_workspace_git and status_result.returncode != 0:
        workspace_clean = None
        metadata_available = False
    else:
        workspace_clean = (status_result.stdout or "").strip() == "" if should_probe_workspace_git else None

    local_branch_exists = None
    if expected_branch:
        local_branch_result = _run_git(repo_path, ["branch", "--list", expected_branch], run_git_command, log)
        if local_branch_result is None or local_branch_result.returncode != 0:
            metadata_available = False
        else:
            local_branch_exists = bool((local_branch_result.stdout or "").strip())

    remote_branch_exists = None
    if expected_branch:
        remote_branch_result = _run_git(
            repo_path,
            ["ls-remote", "--heads", "origin", expected_branch],
            run_git_command,
            log,
        )
        if remote_branch_result is None or remote_branch_result.returncode != 0:
            metadata_available = False
        else:
            remote_branch_exists = bool((remote_branch_result.stdout or "").strip())

    upstream_branch = None
    missing_upstream_tracking = None
    ambiguous_upstream = False
    if should_probe_workspace_git:
        upstream_result = _run_git(
            workspace_path,
            ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
            run_git_command,
            log,
        )
        if upstream_result is None:
            metadata_available = False
        elif upstream_result.returncode != 0:
            stderr = (upstream_result.stderr or "").lower()
            missing_upstream_tracking = "no upstream" in stderr or "upstream" in stderr
            ambiguous_upstream = "ambiguous" in stderr
            if not missing_upstream_tracking and not ambiguous_upstream:
                metadata_available = False
        else:
            upstream_branch = (upstream_result.stdout or "").strip() or None
            missing_upstream_tracking = False

    labels = workflow_labels
    if labels is None and isinstance(github_item, dict):
        labels = github_item.get("labels")

    facts = {
        "repo_path": repo_path,
        "workspace_path": workspace_path,
        "item": item,
        "item_identity": {
            "type": item.get("type") if isinstance(item, dict) else None,
            "number": item.get("number") if isinstance(item, dict) else None,
            "title": item.get("title") if isinstance(item, dict) else None,
        },
        "expected_branch": expected_branch,
        "registered_worktrees": registered_worktrees,
        "registered_workspace_entry": registered_entry,
        "workspace_path_exists": workspace_path_exists,
        "current_branch": current_branch,
        "detached_head": detached_head,
        "workspace_clean": workspace_clean,
        "local_branch_exists": local_branch_exists,
        "remote_branch_exists": remote_branch_exists,
        "upstream_branch": upstream_branch,
        "missing_upstream_tracking": missing_upstream_tracking,
        "ambiguous_upstream": ambiguous_upstream,
        "open_pr": open_pr,
        "workflow_labels": _extract_label_names(labels),
        "watchtower_run": watchtower_run,
        "github_item": github_item,
        "metadata_available": metadata_available,
    }

    return facts


def classify_workspace(facts, *, allow_cleanup=False, dry_run=False):
    reasons = []
    ambiguous = False

    metadata_available = facts.get("metadata_available")
    labels = {str(label).lower() for label in (facts.get("workflow_labels") or [])}
    open_pr = facts.get("open_pr")
    open_pr_exists = _has_open_pr_relationship(open_pr)
    watchtower_run = facts.get("watchtower_run") or {}
    watchtower_state = str(watchtower_run.get("status") or "").lower()
    workspace_clean = facts.get("workspace_clean")
    expected_branch = facts.get("expected_branch")
    current_branch = facts.get("current_branch")
    detached_head = facts.get("detached_head")
    registered_workspace_entry = facts.get("registered_workspace_entry")
    workspace_path_exists = facts.get("workspace_path_exists")
    missing_upstream_tracking = facts.get("missing_upstream_tracking")
    ambiguous_upstream = bool(facts.get("ambiguous_upstream"))

    if metadata_available is False:
        reasons.append("metadata_unavailable")

    if expected_branch and current_branch and expected_branch != current_branch:
        reasons.append("unexpected_branch")
        ambiguous = True

    if detached_head:
        reasons.append("detached_head")
        ambiguous = True

    if ambiguous_upstream:
        reasons.append("ambiguous_upstream")
        ambiguous = True

    if workspace_clean is False:
        reasons.append("dirty_worktree")

    if missing_upstream_tracking:
        reasons.append("missing_upstream_tracking")

    if open_pr_exists:
        reasons.append("open_pr_exists")

    if "state:agent-in-progress" in labels:
        reasons.append("active_lock_label")

    if watchtower_state in {"failed", "interrupted", "incomplete", "launch-failed", "crashed", "cancelled"}:
        reasons.append("watchtower_run_incomplete")

    if registered_workspace_entry is None and workspace_path_exists:
        reasons.append("unregistered_workspace")

    github_item = facts.get("github_item") or {}
    github_item_state = str(github_item.get("state") or "").lower()
    open_pr_state = str((open_pr or {}).get("state") or "").lower()

    if (
        "metadata_unavailable" in reasons
        or "unexpected_branch" in reasons
        or "detached_head" in reasons
        or "ambiguous_upstream" in reasons
        or "unregistered_workspace" in reasons
        or (registered_workspace_entry is None and workspace_clean is False)
    ):
        lifecycle_state = "blocked-unsafe"
    elif "active_lock_label" in reasons:
        lifecycle_state = "active"
    elif "watchtower_run_incomplete" in reasons:
        lifecycle_state = "suspended"
    elif "dirty_worktree" in reasons or "missing_upstream_tracking" in reasons or "open_pr_exists" in reasons:
        lifecycle_state = "recoverable"
    elif (github_item_state == "closed" or open_pr_state == "merged") and workspace_clean is True:
        lifecycle_state = "retired"
    elif registered_workspace_entry is None and workspace_path_exists is False:
        lifecycle_state = "planned"
    elif workspace_clean is True and expected_branch and current_branch == expected_branch:
        lifecycle_state = "ready"
    elif workspace_clean is True and not open_pr_exists:
        lifecycle_state = "stale-clean"
    else:
        lifecycle_state = "blocked-unsafe"

    if allow_cleanup and dry_run and lifecycle_state in {"retired", "stale-clean"}:
        lifecycle_state = "cleanup-eligible"

    if lifecycle_state not in WORKSPACE_LIFECYCLE_STATES:
        lifecycle_state = "blocked-unsafe"
        if "metadata_unavailable" not in reasons:
            reasons.append("metadata_unavailable")

    return {
        "lifecycle_state": lifecycle_state,
        "reasons": sorted(set(reasons)),
        "ambiguous": ambiguous,
        "facts": facts,
    }


def format_workspace_diagnostic(result):
    state = result.get("lifecycle_state", "blocked-unsafe")
    reasons = result.get("reasons") or []
    reasons_text = ", ".join(reasons) if reasons else "none"
    ambiguity = "yes" if result.get("ambiguous") else "no"

    facts = result.get("facts") or {}
    expected_branch = facts.get("expected_branch") or "<unknown>"
    current_branch = facts.get("current_branch") or "<unknown>"
    workspace_path = facts.get("workspace_path") or "<unknown>"

    return (
        f"workspace={workspace_path} state={state} reasons={reasons_text} "
        f"ambiguous={ambiguity} expected_branch={expected_branch} current_branch={current_branch}"
    )
