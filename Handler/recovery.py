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


def classify_locked_item_recovery(*, workspace_lifecycle, dependency_resolution, workflow_state=None):
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

    primary_state_labels = []
    unsupported_state_labels = []
    if isinstance(workflow_state, dict):
        raw_primary_states = workflow_state.get("primary_state_labels")
        if isinstance(raw_primary_states, list):
            primary_state_labels = [label for label in raw_primary_states if isinstance(label, str) and label.strip()]

        raw_unsupported_states = workflow_state.get("unsupported_state_labels")
        if isinstance(raw_unsupported_states, list):
            unsupported_state_labels = [
                label for label in raw_unsupported_states if isinstance(label, str) and label.strip()
            ]

    if unsupported_state_labels:
        return {
            "decision": "blocked_unsafe",
            "recommended_action": "Do not resume. Remove unsupported workflow state labels before any unlock or relabel.",
            "reason": "unsupported workflow state labels are present",
            "blockers": [
                f"unsupported workflow state label(s): {', '.join(unsupported_state_labels)}"
            ],
            "non_destructive": True,
        }

    if len(primary_state_labels) != 1:
        if primary_state_labels:
            reason = "multiple primary workflow state labels are present"
            blocker = f"ambiguous workflow state label(s): {', '.join(primary_state_labels)}"
        else:
            reason = "no primary workflow state label is present"
            blocker = "no primary workflow state label"

        return {
            "decision": "blocked_unsafe",
            "recommended_action": "Do not resume. Ensure exactly one primary workflow state label is set before relabeling.",
            "reason": reason,
            "blockers": [blocker],
            "non_destructive": True,
        }

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

    if lifecycle_state in {"ready", "planned"}:
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