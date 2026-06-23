from Handler import workspace_inventory


AMBIGUITY_REASON_CODES = {
    "ambiguous_upstream",
    "detached_head",
    "metadata_unavailable",
    "unexpected_branch",
    "unregistered_workspace",
}

RECOMMENDED_ACTIONS = {
    "active": "Let the active agent run or inspect the active lock before reassignment.",
    "blocked-unsafe": "Inspect workspace manually before automation continues; do not clean up automatically.",
    "cleanup-eligible": "Cleanup may proceed if the operator requested dry-run-approved cleanup.",
    "planned": "Create or assign the workspace before launch.",
    "ready": "Workspace is ready for assignment.",
    "recoverable": "Recover workspace before reassignment or cleanup.",
    "retired": "Archive or remove the workspace after confirming no follow-up is needed.",
    "stale-clean": "Review whether the clean workspace can be reassigned or retired.",
    "suspended": "Review the interrupted Watchtower run before relaunching.",
}


def _unknown_if_missing(value):
    if value is None or value == "":
        return "<unknown>"

    return str(value)


def _format_item_identity(facts):
    github_item = facts.get("github_item") or {}
    item_identity = facts.get("item_identity") or {}
    item_type = github_item.get("type") or item_identity.get("type") or facts.get("item_type")
    item_number = github_item.get("number") or item_identity.get("number") or facts.get("item_number")

    if item_type and item_number:
        return f"{item_type} #{item_number}"

    if item_number:
        return f"item #{item_number}"

    return "<unknown>"


def _format_pr_identity(facts):
    open_pr = facts.get("open_pr")
    if not isinstance(open_pr, dict) or not open_pr:
        return "none"

    number = open_pr.get("number")
    state = open_pr.get("state")
    url = open_pr.get("url")

    if number and state and url:
        return f"PR #{number} ({state}) {url}"
    if number and state:
        return f"PR #{number} ({state})"
    if number and url:
        return f"PR #{number} {url}"
    if number:
        return f"PR #{number}"
    if url:
        return str(url)

    return "present"


def _format_reasons(reasons):
    return [str(reason) for reason in (reasons or [])]


def _ambiguity_indicators(classification_result):
    reasons = set(_format_reasons(classification_result.get("reasons")))
    indicators = reasons.intersection(AMBIGUITY_REASON_CODES)
    facts = classification_result.get("facts") or {}

    if facts.get("ambiguous_upstream"):
        indicators.add("ambiguous_upstream")
    if facts.get("detached_head"):
        indicators.add("detached_head")
    if facts.get("metadata_available") is False:
        indicators.add("metadata_unavailable")

    return sorted(indicators)


def _recommended_action(classification_result):
    state = classification_result.get("lifecycle_state") or "blocked-unsafe"
    if classification_result.get("ambiguous"):
        return RECOMMENDED_ACTIONS["blocked-unsafe"]

    return RECOMMENDED_ACTIONS.get(state, RECOMMENDED_ACTIONS["blocked-unsafe"])


def build_workspace_lifecycle_diagnostic(classification_result):
    facts = classification_result.get("facts") or {}
    state = classification_result.get("lifecycle_state") or "blocked-unsafe"
    branch = facts.get("current_branch") or facts.get("expected_branch")

    return {
        "workspace": _unknown_if_missing(facts.get("workspace_path")),
        "state": state,
        "branch": _unknown_if_missing(branch),
        "issue": _format_item_identity(facts),
        "pr": _format_pr_identity(facts),
        "reasons": _format_reasons(classification_result.get("reasons")),
        "ambiguity_indicators": _ambiguity_indicators(classification_result),
        "recommended_action": _recommended_action(classification_result),
    }


def collect_workspace_lifecycle_diagnostic(
    *,
    repo_path,
    workspace_path,
    item,
    allow_cleanup=False,
    dry_run=False,
    collect_workspace_inventory_fn=workspace_inventory.collect_workspace_inventory,
    classify_workspace_fn=workspace_inventory.classify_workspace,
):
    facts = collect_workspace_inventory_fn(repo_path, workspace_path, item=item)
    classification_result = classify_workspace_fn(facts, allow_cleanup=allow_cleanup, dry_run=dry_run)
    return build_workspace_lifecycle_diagnostic(classification_result)


def _format_list(values):
    if not values:
        return "none"

    return ", ".join(f"`{value}`" for value in values)


def render_workspace_lifecycle_report(lifecycle_diagnostics):
    if not lifecycle_diagnostics:
        return "- none"

    lines = []
    for diagnostic in lifecycle_diagnostics:
        lines.append(f"- workspace: `{diagnostic.get('workspace', '<unknown>')}`")
        lines.append(f"  - state: `{diagnostic.get('state', '<unknown>')}`")
        lines.append(f"  - branch: `{diagnostic.get('branch', '<unknown>')}`")
        lines.append(f"  - issue: `{diagnostic.get('issue', '<unknown>')}`")
        lines.append(f"  - PR: `{diagnostic.get('pr', 'none')}`")
        lines.append(f"  - reasons: {_format_list(diagnostic.get('reasons'))}")
        lines.append(f"  - ambiguity indicators: {_format_list(diagnostic.get('ambiguity_indicators'))}")
        lines.append(
            f"  - recommended action: {diagnostic.get('recommended_action', RECOMMENDED_ACTIONS['blocked-unsafe'])}"
        )

    return "\n".join(lines)