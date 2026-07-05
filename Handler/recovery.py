def classify_locked_item_recovery(*, workspace_lifecycle, dependency_resolution):
    lifecycle_state = None
    ambiguous = False
    if isinstance(workspace_lifecycle, dict):
        lifecycle_state = workspace_lifecycle.get("lifecycle_classification")
        ambiguous = bool(workspace_lifecycle.get("ambiguous"))

    dependency_status = None
    if isinstance(dependency_resolution, dict):
        dependency_status = dependency_resolution.get("status")

    if ambiguous:
        return {
            "recovery_decision": "skip",
            "recovery_reason": "workspace lifecycle is ambiguous",
            "should_unlock": False,
            "should_dependency_block": False,
        }

    if lifecycle_state in {"active", "suspended"}:
        return {
            "recovery_decision": "skip",
            "recovery_reason": f"workspace lifecycle is {lifecycle_state}",
            "should_unlock": False,
            "should_dependency_block": False,
        }

    if dependency_status == "blocked":
        return {
            "recovery_decision": "dependency-blocked",
            "recovery_reason": "declared dependencies are unresolved",
            "should_unlock": True,
            "should_dependency_block": True,
        }

    if lifecycle_state in {"cleanup-eligible", "stale-clean", "recoverable", "retired", "ready", "planned"}:
        return {
            "recovery_decision": "unlock",
            "recovery_reason": f"workspace lifecycle is {lifecycle_state}",
            "should_unlock": True,
            "should_dependency_block": False,
        }

    return {
        "recovery_decision": "skip",
        "recovery_reason": "workspace lifecycle is inconclusive",
        "should_unlock": False,
        "should_dependency_block": False,
    }