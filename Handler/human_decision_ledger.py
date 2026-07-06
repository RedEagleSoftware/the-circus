def _coerce_positive_int(value):
    if isinstance(value, int) and value > 0:
        return value

    if isinstance(value, str):
        stripped_value = value.strip()
        if stripped_value.isdigit():
            parsed_value = int(stripped_value)
            if parsed_value > 0:
                return parsed_value

    return None


def _normalize_positive_int_list(value, diagnostics, *, field_name):
    if value is None:
        return []

    if not isinstance(value, list):
        diagnostics.append(f"{field_name} must be a list of positive integers")
        return None

    normalized_values = []
    seen_values = set()
    for candidate in value:
        normalized_candidate = _coerce_positive_int(candidate)
        if normalized_candidate is None:
            diagnostics.append(f"{field_name} contains an invalid entry")
            return None
        if normalized_candidate in seen_values:
            continue
        seen_values.add(normalized_candidate)
        normalized_values.append(normalized_candidate)

    return normalized_values


def _normalize_non_empty_string(value, diagnostics, *, field_name):
    if value is None:
        return None

    if not isinstance(value, str):
        diagnostics.append(f"{field_name} must be a non-empty string")
        return None

    stripped_value = value.strip()
    if not stripped_value:
        diagnostics.append(f"{field_name} must be a non-empty string")
        return None

    return stripped_value


def _normalize_string_list(value, diagnostics, *, field_name, allowed_values=None):
    if value is None:
        return []

    if not isinstance(value, list):
        diagnostics.append(f"{field_name} must be a list of non-empty strings")
        return None

    normalized_values = []
    seen_values = set()
    for candidate in value:
        normalized_candidate = _normalize_non_empty_string(candidate, diagnostics, field_name=field_name)
        if normalized_candidate is None:
            return None

        if allowed_values is not None and normalized_candidate not in allowed_values:
            diagnostics.append(f"{field_name} contains an unsupported entry")
            return None

        if normalized_candidate in seen_values:
            continue
        seen_values.add(normalized_candidate)
        normalized_values.append(normalized_candidate)

    return normalized_values


def _normalize_recommendation_comment_ids(raw_human_decision_ledger, diagnostics):
    recommendation_comment_ids = _normalize_positive_int_list(
        raw_human_decision_ledger.get("recommendation_comment_ids"),
        diagnostics,
        field_name="recommendation_comment_ids",
    )
    if recommendation_comment_ids is not None:
        return recommendation_comment_ids

    fallback_recommendation_comment_ids = _normalize_positive_int_list(
        raw_human_decision_ledger.get("based_on_recommendation_comment_ids"),
        diagnostics,
        field_name="based_on_recommendation_comment_ids",
    )
    if fallback_recommendation_comment_ids is not None and fallback_recommendation_comment_ids:
        diagnostics.append("recommendation_comment_ids defaulted from based_on_recommendation_comment_ids")
    return fallback_recommendation_comment_ids


def _normalize_human_decision_source(source_value, diagnostics):
    default_source = {
        "repo": None,
        "issue_number": None,
        "accepted_recommendation_url": None,
        "accepted_recommendation_comment_id": None,
        "roadmap_pr": None,
        "planner_issue_number": None,
        "planner_result_comment_id": None,
        "implementation_plan_artifact": None,
    }

    if source_value is None:
        return default_source

    if not isinstance(source_value, dict):
        diagnostics.append("source must be an object")
        return default_source

    source_repo = _normalize_non_empty_string(source_value.get("repo"), diagnostics, field_name="source.repo")
    source_issue_number = _coerce_positive_int(source_value.get("issue_number"))
    if source_issue_number is None:
        source_issue_number = _coerce_positive_int(source_value.get("number"))

    if source_value.get("issue_number") is not None and _coerce_positive_int(source_value.get("issue_number")) is None:
        diagnostics.append("source.issue_number must be a positive integer")
    elif source_value.get("number") is not None and _coerce_positive_int(source_value.get("number")) is None:
        diagnostics.append("source.number must be a positive integer")

    accepted_recommendation_url = _normalize_non_empty_string(
        source_value.get("accepted_recommendation_url"),
        diagnostics,
        field_name="source.accepted_recommendation_url",
    )
    if accepted_recommendation_url is None:
        accepted_recommendation_url = _normalize_non_empty_string(
            source_value.get("url"),
            diagnostics,
            field_name="source.url",
        )

    accepted_recommendation_comment_id = _coerce_positive_int(source_value.get("accepted_recommendation_comment_id"))
    if (
        source_value.get("accepted_recommendation_comment_id") is not None
        and accepted_recommendation_comment_id is None
    ):
        diagnostics.append("source.accepted_recommendation_comment_id must be a positive integer")

    roadmap_pr = _coerce_positive_int(source_value.get("roadmap_pr"))
    if source_value.get("roadmap_pr") is not None and roadmap_pr is None:
        diagnostics.append("source.roadmap_pr must be a positive integer")

    planner_issue_number = _coerce_positive_int(source_value.get("planner_issue_number"))
    if source_value.get("planner_issue_number") is not None and planner_issue_number is None:
        diagnostics.append("source.planner_issue_number must be a positive integer")

    planner_result_comment_id = _coerce_positive_int(source_value.get("planner_result_comment_id"))
    if source_value.get("planner_result_comment_id") is not None and planner_result_comment_id is None:
        diagnostics.append("source.planner_result_comment_id must be a positive integer")

    implementation_plan_artifact = _normalize_non_empty_string(
        source_value.get("implementation_plan_artifact"),
        diagnostics,
        field_name="source.implementation_plan_artifact",
    )

    return {
        "repo": source_repo,
        "issue_number": source_issue_number,
        "accepted_recommendation_url": accepted_recommendation_url,
        "accepted_recommendation_comment_id": accepted_recommendation_comment_id,
        "roadmap_pr": roadmap_pr,
        "planner_issue_number": planner_issue_number,
        "planner_result_comment_id": planner_result_comment_id,
        "implementation_plan_artifact": implementation_plan_artifact,
    }


def _normalize_human_decision_accepted_recommendation(recommendation_value, diagnostics):
    if recommendation_value is None:
        return {
            "comment_ids": [],
            "comment_urls": [],
        }

    if not isinstance(recommendation_value, dict):
        diagnostics.append("accepted_recommendation must be an object")
        return {
            "comment_ids": [],
            "comment_urls": [],
        }

    normalized_comment_ids = _normalize_positive_int_list(
        recommendation_value.get("comment_ids"),
        diagnostics,
        field_name="accepted_recommendation.comment_ids",
    )
    normalized_comment_urls = _normalize_string_list(
        recommendation_value.get("comment_urls"),
        diagnostics,
        field_name="accepted_recommendation.comment_urls",
    )
    return {
        "comment_ids": normalized_comment_ids or [],
        "comment_urls": normalized_comment_urls or [],
    }


def _normalize_human_decision_selection(selection_value, diagnostics):
    if selection_value is None:
        return {
            "generated_issues": [],
        }

    if not isinstance(selection_value, dict):
        diagnostics.append("selection must be an object")
        return {
            "generated_issues": [],
        }

    generated_issues = selection_value.get("generated_issues")
    if generated_issues is None:
        return {
            "generated_issues": [],
        }

    if not isinstance(generated_issues, list):
        diagnostics.append("selection.generated_issues must be a list")
        return {
            "generated_issues": [],
        }

    normalized_generated_issues = []
    seen_issue_numbers = set()
    for generated_issue in generated_issues:
        if not isinstance(generated_issue, dict):
            diagnostics.append("selection.generated_issues contains an invalid entry")
            return {
                "generated_issues": [],
            }

        issue_number = _coerce_positive_int(generated_issue.get("issue_number"))
        if issue_number is None:
            issue_number = _coerce_positive_int(generated_issue.get("number"))
        if issue_number is None:
            diagnostics.append("selection.generated_issues contains an invalid issue number")
            return {
                "generated_issues": [],
            }

        issue_url = _normalize_non_empty_string(
            generated_issue.get("issue_url"),
            diagnostics,
            field_name="selection.generated_issues.issue_url",
        )
        if issue_url is None:
            issue_url = _normalize_non_empty_string(
                generated_issue.get("url"),
                diagnostics,
                field_name="selection.generated_issues.url",
            )

        transition_target = _normalize_non_empty_string(
            generated_issue.get("next_state_after_approval"),
            diagnostics,
            field_name="selection.generated_issues.next_state_after_approval",
        )
        if transition_target is not None:
            transition_target = transition_target.lower()

        if issue_number in seen_issue_numbers:
            continue

        seen_issue_numbers.add(issue_number)
        normalized_generated_issues.append(
            {
                "issue_number": issue_number,
                "issue_url": issue_url,
                "next_state_after_approval": transition_target,
            }
        )

    return {
        "generated_issues": normalized_generated_issues,
    }


def _normalize_human_decision_applied_transitions(applied_transitions_value, diagnostics):
    if applied_transitions_value is None:
        return {
            "targets": [],
        }

    if not isinstance(applied_transitions_value, dict):
        diagnostics.append("applied_transitions must be an object")
        return {
            "targets": [],
        }

    normalized_targets = _normalize_string_list(
        applied_transitions_value.get("targets"),
        diagnostics,
        field_name="applied_transitions.targets",
    )
    return {
        "targets": normalized_targets or [],
    }


def _normalize_human_decision_decision(decision_value, diagnostics):
    default_decision = {
        "selected_next_state": None,
        "next_state_options": [],
        "generated_issues": [],
    }

    if decision_value is None:
        return default_decision

    if not isinstance(decision_value, dict):
        diagnostics.append("decision must be an object")
        return default_decision

    selected_next_state = _normalize_non_empty_string(
        decision_value.get("selected_next_state"),
        diagnostics,
        field_name="decision.selected_next_state",
    )
    if isinstance(selected_next_state, str):
        selected_next_state = selected_next_state.lower()

    next_state_options = _normalize_string_list(
        decision_value.get("next_state_options"),
        diagnostics,
        field_name="decision.next_state_options",
    )
    if next_state_options is None:
        next_state_options = []
    else:
        next_state_options = [next_state_option.lower() for next_state_option in next_state_options]

    generated_issues_value = decision_value.get("generated_issues")
    normalized_generated_issues = []
    if generated_issues_value is not None:
        if not isinstance(generated_issues_value, list):
            diagnostics.append("decision.generated_issues must be a list")
        else:
            seen_issue_numbers = set()
            for generated_issue in generated_issues_value:
                if not isinstance(generated_issue, dict):
                    diagnostics.append("decision.generated_issues contains an invalid entry")
                    continue

                issue_number = _coerce_positive_int(generated_issue.get("number"))
                if issue_number is None:
                    issue_number = _coerce_positive_int(generated_issue.get("issue_number"))
                if issue_number is None:
                    diagnostics.append("decision.generated_issues contains an invalid issue number")
                    continue

                if issue_number in seen_issue_numbers:
                    continue

                initial_state = _normalize_non_empty_string(
                    generated_issue.get("initial_state"),
                    diagnostics,
                    field_name="decision.generated_issues.initial_state",
                )
                next_state_after_approval = _normalize_non_empty_string(
                    generated_issue.get("next_state_after_approval"),
                    diagnostics,
                    field_name="decision.generated_issues.next_state_after_approval",
                )
                if isinstance(next_state_after_approval, str):
                    next_state_after_approval = next_state_after_approval.lower()

                seen_issue_numbers.add(issue_number)
                normalized_generated_issues.append(
                    {
                        "number": issue_number,
                        "initial_state": initial_state,
                        "next_state_after_approval": next_state_after_approval,
                    }
                )

    return {
        "selected_next_state": selected_next_state,
        "next_state_options": next_state_options,
        "generated_issues": normalized_generated_issues,
    }


def _normalize_human_decision_stale_check(stale_check_value, diagnostics):
    default_stale_check = {
        "status": None,
        "compared_recommendation_comment_id": None,
        "compared_roadmap_pr": None,
        "diagnostics": [],
    }

    if stale_check_value is None:
        return default_stale_check

    if not isinstance(stale_check_value, dict):
        diagnostics.append("stale_check must be an object")
        return default_stale_check

    stale_check_status = _normalize_non_empty_string(
        stale_check_value.get("status"),
        diagnostics,
        field_name="stale_check.status",
    )
    if isinstance(stale_check_status, str):
        stale_check_status = stale_check_status.lower()

    compared_recommendation_comment_id = _coerce_positive_int(stale_check_value.get("compared_recommendation_comment_id"))
    if (
        stale_check_value.get("compared_recommendation_comment_id") is not None
        and compared_recommendation_comment_id is None
    ):
        diagnostics.append("stale_check.compared_recommendation_comment_id must be a positive integer")

    compared_roadmap_pr = _coerce_positive_int(stale_check_value.get("compared_roadmap_pr"))
    if stale_check_value.get("compared_roadmap_pr") is not None and compared_roadmap_pr is None:
        diagnostics.append("stale_check.compared_roadmap_pr must be a positive integer")

    stale_check_diagnostics = _normalize_string_list(
        stale_check_value.get("diagnostics"),
        diagnostics,
        field_name="stale_check.diagnostics",
    )

    return {
        "status": stale_check_status,
        "compared_recommendation_comment_id": compared_recommendation_comment_id,
        "compared_roadmap_pr": compared_roadmap_pr,
        "diagnostics": stale_check_diagnostics or [],
    }


def _normalize_human_decision_evidence(evidence_value, diagnostics):
    default_evidence = {
        "github_comment_url": None,
        "github_comment_id": None,
        "watchtower_run_status": None,
    }

    if evidence_value is None:
        return default_evidence

    if not isinstance(evidence_value, dict):
        diagnostics.append("evidence must be an object")
        return default_evidence

    github_comment_url = _normalize_non_empty_string(
        evidence_value.get("github_comment_url"),
        diagnostics,
        field_name="evidence.github_comment_url",
    )

    github_comment_id = _coerce_positive_int(evidence_value.get("github_comment_id"))
    if evidence_value.get("github_comment_id") is not None and github_comment_id is None:
        diagnostics.append("evidence.github_comment_id must be a positive integer")

    watchtower_run_status = _normalize_non_empty_string(
        evidence_value.get("watchtower_run_status"),
        diagnostics,
        field_name="evidence.watchtower_run_status",
    )

    return {
        "github_comment_url": github_comment_url,
        "github_comment_id": github_comment_id,
        "watchtower_run_status": watchtower_run_status,
    }


def _has_handoff_source_identity(source):
    if not isinstance(source, dict):
        return False

    return bool(
        source.get("repo")
        or source.get("issue_number") is not None
        or source.get("accepted_recommendation_url")
        or source.get("accepted_recommendation_comment_id") is not None
        or source.get("roadmap_pr") is not None
        or source.get("planner_issue_number") is not None
        or source.get("planner_result_comment_id") is not None
        or source.get("implementation_plan_artifact")
    )


def _has_handoff_decision_details(decision):
    if not isinstance(decision, dict):
        return False

    return bool(
        decision.get("selected_next_state")
        or decision.get("next_state_options")
        or decision.get("generated_issues")
    )


def _format_yaml_scalar(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return repr(value)


def normalize_human_decision_ledger(
    raw_human_decision_ledger,
    *,
    recommendation_comment_id=None,
    generated_issue_numbers=None,
    generated_issue_transition_targets=None,
): 
    diagnostics = []
    status = "missing"

    fallback_recommendation_comment_id = _coerce_positive_int(recommendation_comment_id)
    fallback_generated_issue_numbers = []
    if isinstance(generated_issue_numbers, list):
        seen_issue_numbers = set()
        for generated_issue_number in generated_issue_numbers:
            normalized_issue_number = _coerce_positive_int(generated_issue_number)
            if normalized_issue_number is None or normalized_issue_number in seen_issue_numbers:
                continue
            seen_issue_numbers.add(normalized_issue_number)
            fallback_generated_issue_numbers.append(normalized_issue_number)

    fallback_generated_issue_transition_targets = []
    if isinstance(generated_issue_transition_targets, list):
        seen_transition_targets = set()
        for generated_issue_transition_target in generated_issue_transition_targets:
            if not isinstance(generated_issue_transition_target, str):
                continue
            normalized_transition_target = generated_issue_transition_target.strip().lower()
            if not normalized_transition_target or normalized_transition_target in seen_transition_targets:
                continue
            seen_transition_targets.add(normalized_transition_target)
            fallback_generated_issue_transition_targets.append(normalized_transition_target)

    if raw_human_decision_ledger is None:
        diagnostics.append("human decision ledger missing")
        raw_human_decision_ledger = {}
    elif not isinstance(raw_human_decision_ledger, dict):
        diagnostics.append("human decision ledger is malformed")
        raw_human_decision_ledger = {}
        status = "invalid"

    version = raw_human_decision_ledger.get("version")
    normalized_version = version if version is not None else 1
    if not isinstance(normalized_version, int):
        diagnostics.append("human decision ledger version must be an integer")
        status = "invalid"
    elif normalized_version != 1:
        diagnostics.append("unsupported human decision ledger version")
        status = "invalid"

    raw_human_decision_payload = raw_human_decision_ledger
    if isinstance(raw_human_decision_ledger.get("human_decision_v1"), dict):
        raw_human_decision_payload = raw_human_decision_ledger.get("human_decision_v1")

    source = _normalize_human_decision_source(raw_human_decision_payload.get("source"), diagnostics)
    decision = _normalize_human_decision_decision(raw_human_decision_payload.get("decision"), diagnostics)
    stale_check = _normalize_human_decision_stale_check(raw_human_decision_payload.get("stale_check"), diagnostics)
    evidence = _normalize_human_decision_evidence(raw_human_decision_payload.get("evidence"), diagnostics)
    accepted_recommendation = _normalize_human_decision_accepted_recommendation(
        raw_human_decision_payload.get("accepted_recommendation"),
        diagnostics,
    )
    selection = _normalize_human_decision_selection(raw_human_decision_payload.get("selection"), diagnostics)
    applied_transitions = _normalize_human_decision_applied_transitions(
        raw_human_decision_payload.get("applied_transitions"),
        diagnostics,
    )

    approval_payload = raw_human_decision_payload.get("approval")
    if approval_payload is not None and not isinstance(approval_payload, dict):
        diagnostics.append("approval must be an object")
        approval_payload = {}
    if approval_payload is None:
        approval_payload = {}

    recommendation_comment_ids = _normalize_recommendation_comment_ids(raw_human_decision_payload, diagnostics)
    if not recommendation_comment_ids:
        recommendation_comment_ids = accepted_recommendation.get("comment_ids", [])
        if recommendation_comment_ids:
            diagnostics.append("recommendation_comment_ids defaulted from accepted_recommendation.comment_ids")
    if not recommendation_comment_ids and source.get("accepted_recommendation_comment_id") is not None:
        recommendation_comment_ids = [source.get("accepted_recommendation_comment_id")]
        diagnostics.append("recommendation_comment_ids defaulted from source.accepted_recommendation_comment_id")

    selected_generated_issue_numbers = _normalize_positive_int_list(
        raw_human_decision_payload.get("selected_generated_issue_numbers"),
        diagnostics,
        field_name="selected_generated_issue_numbers",
    )
    if not selected_generated_issue_numbers:
        selected_generated_issue_numbers = [
            generated_issue.get("issue_number")
            for generated_issue in selection.get("generated_issues", [])
            if isinstance(generated_issue, dict) and generated_issue.get("issue_number") is not None
        ]
        if selected_generated_issue_numbers:
            diagnostics.append("selected_generated_issue_numbers defaulted from selection.generated_issues")
    if not selected_generated_issue_numbers:
        selected_generated_issue_numbers = [
            generated_issue.get("number")
            for generated_issue in decision.get("generated_issues", [])
            if isinstance(generated_issue, dict) and generated_issue.get("number") is not None
        ]
        if selected_generated_issue_numbers:
            diagnostics.append("selected_generated_issue_numbers defaulted from decision.generated_issues")

    decision_type = _normalize_non_empty_string(
        raw_human_decision_payload.get("decision_type"),
        diagnostics,
        field_name="decision_type",
    )
    approved_by = _normalize_non_empty_string(
        raw_human_decision_payload.get("approved_by") or approval_payload.get("approved_by"),
        diagnostics,
        field_name="approved_by",
    )
    decision_summary = _normalize_non_empty_string(
        raw_human_decision_payload.get("decision_summary") or approval_payload.get("decision_summary"),
        diagnostics,
        field_name="decision_summary",
    )
    if decision_summary is None:
        decision_summary = _normalize_non_empty_string(
            raw_human_decision_payload.get("rationale_summary") or approval_payload.get("rationale_summary"),
            diagnostics,
            field_name="rationale_summary",
        )
        if decision_summary is not None:
            diagnostics.append("decision_summary defaulted from rationale_summary")

    selected_generated_issue_urls = _normalize_string_list(
        raw_human_decision_payload.get("selected_generated_issue_urls"),
        diagnostics,
        field_name="selected_generated_issue_urls",
    )
    if not selected_generated_issue_urls:
        selected_generated_issue_urls = [
            generated_issue.get("issue_url")
            for generated_issue in selection.get("generated_issues", [])
            if isinstance(generated_issue, dict) and generated_issue.get("issue_url")
        ]
        if selected_generated_issue_urls:
            diagnostics.append("selected_generated_issue_urls defaulted from selection.generated_issues")

    applied_transition_targets = _normalize_string_list(
        raw_human_decision_payload.get("applied_transition_targets"),
        diagnostics,
        field_name="applied_transition_targets",
    )
    if not applied_transition_targets:
        applied_transition_targets = applied_transitions.get("targets", [])
        if applied_transition_targets:
            diagnostics.append("applied_transition_targets defaulted from applied_transitions.targets")
    if not applied_transition_targets:
        applied_transition_targets = [
            generated_issue.get("next_state_after_approval")
            for generated_issue in selection.get("generated_issues", [])
            if isinstance(generated_issue, dict) and generated_issue.get("next_state_after_approval")
        ]
        if applied_transition_targets:
            diagnostics.append("applied_transition_targets defaulted from selection.generated_issues")
    if not applied_transition_targets and decision.get("selected_next_state"):
        applied_transition_targets = [decision.get("selected_next_state")]
        diagnostics.append("applied_transition_targets defaulted from decision.selected_next_state")
    if not applied_transition_targets and decision.get("next_state_options"):
        applied_transition_targets = decision.get("next_state_options")
        diagnostics.append("applied_transition_targets defaulted from decision.next_state_options")
    if not applied_transition_targets:
        applied_transition_targets = [
            generated_issue.get("next_state_after_approval")
            for generated_issue in decision.get("generated_issues", [])
            if isinstance(generated_issue, dict) and generated_issue.get("next_state_after_approval")
        ]
        if applied_transition_targets:
            diagnostics.append("applied_transition_targets defaulted from decision.generated_issues")

    if (
        recommendation_comment_ids is None
        or selected_generated_issue_numbers is None
        or selected_generated_issue_urls is None
        or applied_transition_targets is None
    ):
        status = "invalid"
        recommendation_comment_ids = recommendation_comment_ids or []
        selected_generated_issue_numbers = selected_generated_issue_numbers or []
        selected_generated_issue_urls = selected_generated_issue_urls or []
        applied_transition_targets = applied_transition_targets or []

    if not recommendation_comment_ids and fallback_recommendation_comment_id is not None:
        recommendation_comment_ids = [fallback_recommendation_comment_id]
        diagnostics.append("recommendation_comment_ids defaulted from recommendation_comment_id")

    if not selected_generated_issue_numbers and fallback_generated_issue_numbers:
        selected_generated_issue_numbers = fallback_generated_issue_numbers
        diagnostics.append("selected_generated_issue_numbers defaulted from generated_issues")

    if not applied_transition_targets and fallback_generated_issue_transition_targets:
        applied_transition_targets = fallback_generated_issue_transition_targets
        diagnostics.append("applied_transition_targets defaulted from generated_issues")

    if decision_type is None:
        decision_type = "implementation_plan_review_approval"
        diagnostics.append("decision_type defaulted from workflow")

    handoff_shape_present = bool(
        isinstance(raw_human_decision_payload, dict)
        and any(
            field in raw_human_decision_payload
            for field in ("source", "decision", "stale_check", "evidence")
        )
    )

    if approved_by is None and not handoff_shape_present:
        diagnostics.append("approved_by missing")

    if decision_summary is None and not handoff_shape_present:
        diagnostics.append("decision_summary missing")

    if status != "invalid":
        has_legacy_required_fields = bool(
            recommendation_comment_ids
            and selected_generated_issue_numbers
            and applied_transition_targets
            and decision_type
            and approved_by
            and decision_summary
        )
        has_handoff_required_fields = bool(
            recommendation_comment_ids
            and selected_generated_issue_numbers
            and applied_transition_targets
            and decision_type
            and _has_handoff_source_identity(source)
            and _has_handoff_decision_details(decision)
            and stale_check.get("status") is not None
            and ("evidence" in raw_human_decision_payload or any(evidence.values()))
        )

        if has_legacy_required_fields or has_handoff_required_fields:
            status = "available"
        elif (
            recommendation_comment_ids
            or selected_generated_issue_numbers
            or decision_summary
            or selected_generated_issue_urls
            or applied_transition_targets
            or source.get("accepted_recommendation_comment_id") is not None
            or decision.get("selected_next_state")
            or stale_check.get("status")
            or evidence.get("github_comment_url")
        ):
            status = "partial"
        else:
            status = "missing"

    normalized_diagnostics = []
    seen_diagnostics = set()
    for diagnostic in diagnostics:
        if not isinstance(diagnostic, str):
            continue
        normalized_diagnostic = diagnostic.strip()
        if not normalized_diagnostic or normalized_diagnostic in seen_diagnostics:
            continue
        seen_diagnostics.add(normalized_diagnostic)
        normalized_diagnostics.append(normalized_diagnostic)

    return {
        "version": 1,
        "status": status,
        "decision_type": decision_type,
        "approved_by": approved_by,
        "decision_summary": decision_summary,
        "recommendation_comment_ids": recommendation_comment_ids,
        "based_on_recommendation_comment_ids": recommendation_comment_ids,
        "selected_generated_issue_numbers": selected_generated_issue_numbers,
        "selected_generated_issue_urls": selected_generated_issue_urls,
        "applied_transition_targets": applied_transition_targets,
        "rationale_summary": decision_summary,
        "source": source,
        "decision": decision,
        "stale_check": stale_check,
        "evidence": evidence,
        "diagnostics": normalized_diagnostics,
    }


def render_human_decision_ledger_markdown_block(human_decision_ledger):
    if not isinstance(human_decision_ledger, dict):
        human_decision_ledger = normalize_human_decision_ledger(None)

    lines = [
        "```yaml",
        "human_decision_ledger_v1:",
        f"  version: {human_decision_ledger.get('version')}",
        f"  status: {human_decision_ledger.get('status')}",
        f"  decision_type: {human_decision_ledger.get('decision_type')!r}",
        f"  approved_by: {human_decision_ledger.get('approved_by')!r}",
        f"  decision_summary: {human_decision_ledger.get('decision_summary')!r}",
        "  recommendation_comment_ids:",
    ]

    recommendation_comment_ids = human_decision_ledger.get("recommendation_comment_ids")
    if isinstance(recommendation_comment_ids, list) and recommendation_comment_ids:
        for recommendation_comment_id in recommendation_comment_ids:
            lines.append(f"    - {recommendation_comment_id}")
    else:
        lines.append("    -")

    lines.append("  selected_generated_issue_numbers:")
    selected_generated_issue_numbers = human_decision_ledger.get("selected_generated_issue_numbers")
    if isinstance(selected_generated_issue_numbers, list) and selected_generated_issue_numbers:
        for issue_number in selected_generated_issue_numbers:
            lines.append(f"    - {issue_number}")
    else:
        lines.append("    -")

    lines.append("  selected_generated_issue_urls:")
    selected_generated_issue_urls = human_decision_ledger.get("selected_generated_issue_urls")
    if isinstance(selected_generated_issue_urls, list) and selected_generated_issue_urls:
        for selected_generated_issue_url in selected_generated_issue_urls:
            lines.append(f"    - {selected_generated_issue_url!r}")
    else:
        lines.append("    -")

    lines.append("  applied_transition_targets:")
    applied_transition_targets = human_decision_ledger.get("applied_transition_targets")
    if isinstance(applied_transition_targets, list) and applied_transition_targets:
        for applied_transition_target in applied_transition_targets:
            lines.append(f"    - {applied_transition_target!r}")
    else:
        lines.append("    -")

    decision_summary = human_decision_ledger.get("decision_summary")
    if isinstance(decision_summary, str):
        lines.append(f"  rationale_summary: {decision_summary!r}")
    else:
        lines.append("  rationale_summary:")

    source = human_decision_ledger.get("source")
    if not isinstance(source, dict):
        source = {}

    decision = human_decision_ledger.get("decision")
    if not isinstance(decision, dict):
        decision = {}

    stale_check = human_decision_ledger.get("stale_check")
    if not isinstance(stale_check, dict):
        stale_check = {}

    evidence = human_decision_ledger.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}

    lines.extend(
        [
            "  human_decision_v1:",
            f"    decision_type: {_format_yaml_scalar(human_decision_ledger.get('decision_type'))}",
            "    source:",
            f"      repo: {_format_yaml_scalar(source.get('repo'))}",
            f"      issue_number: {_format_yaml_scalar(source.get('issue_number'))}",
            f"      accepted_recommendation_url: {_format_yaml_scalar(source.get('accepted_recommendation_url'))}",
            "      accepted_recommendation_comment_id: "
            f"{_format_yaml_scalar(source.get('accepted_recommendation_comment_id'))}",
            f"      roadmap_pr: {_format_yaml_scalar(source.get('roadmap_pr'))}",
            f"      planner_issue_number: {_format_yaml_scalar(source.get('planner_issue_number'))}",
            f"      planner_result_comment_id: {_format_yaml_scalar(source.get('planner_result_comment_id'))}",
            f"      implementation_plan_artifact: {_format_yaml_scalar(source.get('implementation_plan_artifact'))}",
            "    decision:",
            f"      selected_next_state: {_format_yaml_scalar(decision.get('selected_next_state'))}",
            "      next_state_options:",
        ]
    )

    next_state_options = decision.get("next_state_options")
    if isinstance(next_state_options, list) and next_state_options:
        for next_state_option in next_state_options:
            lines.append(f"        - {_format_yaml_scalar(next_state_option)}")
    else:
        lines.append("        -")

    lines.append("      generated_issues:")
    generated_issues = decision.get("generated_issues")
    if isinstance(generated_issues, list) and generated_issues:
        for generated_issue in generated_issues:
            if not isinstance(generated_issue, dict):
                continue
            lines.append("        -")
            lines.append(f"          number: {_format_yaml_scalar(generated_issue.get('number'))}")
            lines.append(f"          initial_state: {_format_yaml_scalar(generated_issue.get('initial_state'))}")
            lines.append(
                "          next_state_after_approval: "
                f"{_format_yaml_scalar(generated_issue.get('next_state_after_approval'))}"
            )
    else:
        lines.append("        -")

    lines.extend(
        [
            "    stale_check:",
            f"      status: {_format_yaml_scalar(stale_check.get('status'))}",
            "      compared_recommendation_comment_id: "
            f"{_format_yaml_scalar(stale_check.get('compared_recommendation_comment_id'))}",
            f"      compared_roadmap_pr: {_format_yaml_scalar(stale_check.get('compared_roadmap_pr'))}",
            "      diagnostics:",
        ]
    )

    stale_check_diagnostics = stale_check.get("diagnostics")
    if isinstance(stale_check_diagnostics, list) and stale_check_diagnostics:
        for stale_check_diagnostic in stale_check_diagnostics:
            lines.append(f"        - {_format_yaml_scalar(stale_check_diagnostic)}")
    else:
        lines.append("        -")

    lines.extend(
        [
            "    evidence:",
            f"      github_comment_url: {_format_yaml_scalar(evidence.get('github_comment_url'))}",
            f"      github_comment_id: {_format_yaml_scalar(evidence.get('github_comment_id'))}",
            f"      watchtower_run_status: {_format_yaml_scalar(evidence.get('watchtower_run_status'))}",
        ]
    )

    lines.append("  diagnostics:")
    diagnostics = human_decision_ledger.get("diagnostics")
    if isinstance(diagnostics, list) and diagnostics:
        for diagnostic in diagnostics:
            lines.append(f"    - {_format_yaml_scalar(diagnostic)}")
    else:
        lines.append("    -")

    lines.append("```")
    return lines