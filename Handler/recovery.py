def _normalize_lifecycle_reasons(workspace_lifecycle):
    if not isinstance(workspace_lifecycle, dict):
        return []

    reasons = workspace_lifecycle.get("reasons")
    if not isinstance(reasons, list):
        return []

    normalized = []
    for reason in reasons:
        if isinstance(reason, str) and reason.strip():
            normalized.append(reason.strip())
    return normalized


def classify_locked_item_recovery(*, workspace_lifecycle, dependency_resolution):
    lifecycle_state = None
    ambiguous = False
    blockers = []
    if isinstance(workspace_lifecycle, dict):
        lifecycle_state = workspace_lifecycle.get("lifecycle_classification")
        ambiguous = bool(workspace_lifecycle.get("ambiguous"))
        blockers.extend(_normalize_lifecycle_reasons(workspace_lifecycle))

    dependency_declared = False
    dependency_status = None
    dependency_diagnostic = None
    if isinstance(dependency_resolution, dict):
        dependency_declared = bool(dependency_resolution.get("declared"))
        dependency_status = dependency_resolution.get("status")
        dependency_diagnostic = dependency_resolution.get("diagnostic")

    if ambiguous:
        return {
            "decision": "blocked_unsafe",
            "recommended_action": "Do not resume. Review workspace lifecycle ambiguities and reconcile local state manually.",
            "reason": "workspace lifecycle is ambiguous",
            "blockers": blockers or ["workspace lifecycle is ambiguous"],
            "non_destructive": True,
        }

    if dependency_status == "blocked":
        dependency_blockers = ["declared dependencies are unresolved"]
        if isinstance(dependency_diagnostic, str) and dependency_diagnostic.strip():
            dependency_blockers.append(dependency_diagnostic.strip())
        return {
            "decision": "dependency_resume_blocked",
            "recommended_action": "Do not resume. Resolve declared dependencies and confirm the expected resume state before relabeling.",
            "reason": "declared dependencies are unresolved",
            "blockers": dependency_blockers,
            "non_destructive": True,
        }

    if lifecycle_state in {"active", "suspended"}:
        return {
            "decision": "interrupted_run_blocked",
            "recommended_action": "Do not resume automatically. Inspect latest run status and workspace before any manual recovery action.",
            "reason": f"workspace lifecycle is {lifecycle_state}",
            "blockers": blockers or [f"workspace lifecycle is {lifecycle_state}"],
            "non_destructive": True,
        }

    if lifecycle_state in {"ready", "planned", "recoverable", "cleanup-eligible", "stale-clean"}:
        return {
            "decision": "safe_resume",
            "recommended_action": "Safe resume candidate identified. Human operator may restore an appropriate dispatchable state and rerun Handler.",
            "reason": f"workspace lifecycle is {lifecycle_state}",
            "blockers": [],
            "non_destructive": True,
        }

    if dependency_declared and dependency_status == "resolved":
        return {
            "decision": "stale_lock_needs_human",
            "recommended_action": "Dependencies are satisfied but workspace facts are incomplete. Perform a manual verification before any unlock or relabel.",
            "reason": "dependency metadata is resolved but workspace lifecycle is inconclusive",
            "blockers": blockers or ["workspace lifecycle is inconclusive"],
            "non_destructive": True,
        }

    if lifecycle_state == "retired":
        return {
            "decision": "no_recovery_needed",
            "recommended_action": "No recovery action is required for a retired workspace.",
            "reason": "workspace lifecycle is retired",
            "blockers": [],
            "non_destructive": True,
        }

    return {
        "decision": "blocked_unsafe",
        "recommended_action": "Do not resume. Gather additional workspace and run diagnostics, then perform a manual review.",
        "reason": "workspace lifecycle is inconclusive",
        "blockers": blockers or ["workspace lifecycle is inconclusive"],
        "non_destructive": True,
    }