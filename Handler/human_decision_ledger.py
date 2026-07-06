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

    recommendation_comment_ids = _normalize_recommendation_comment_ids(raw_human_decision_ledger, diagnostics)
    selected_generated_issue_numbers = _normalize_positive_int_list(
        raw_human_decision_ledger.get("selected_generated_issue_numbers"),
        diagnostics,
        field_name="selected_generated_issue_numbers",
    )
    decision_type = _normalize_non_empty_string(
        raw_human_decision_ledger.get("decision_type"),
        diagnostics,
        field_name="decision_type",
    )
    approved_by = _normalize_non_empty_string(
        raw_human_decision_ledger.get("approved_by"),
        diagnostics,
        field_name="approved_by",
    )
    decision_summary = _normalize_non_empty_string(
        raw_human_decision_ledger.get("decision_summary"),
        diagnostics,
        field_name="decision_summary",
    )
    if decision_summary is None:
        decision_summary = _normalize_non_empty_string(
            raw_human_decision_ledger.get("rationale_summary"),
            diagnostics,
            field_name="rationale_summary",
        )
        if decision_summary is not None:
            diagnostics.append("decision_summary defaulted from rationale_summary")

    selected_generated_issue_urls = _normalize_string_list(
        raw_human_decision_ledger.get("selected_generated_issue_urls"),
        diagnostics,
        field_name="selected_generated_issue_urls",
    )
    applied_transition_targets = _normalize_string_list(
        raw_human_decision_ledger.get("applied_transition_targets"),
        diagnostics,
        field_name="applied_transition_targets",
    )

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

    if approved_by is None:
        diagnostics.append("approved_by missing")

    if decision_summary is None:
        diagnostics.append("decision_summary missing")

    if status != "invalid":
        has_all_required_fields = bool(
            recommendation_comment_ids
            and selected_generated_issue_numbers
            and applied_transition_targets
            and decision_type
            and approved_by
            and decision_summary
        )
        if has_all_required_fields:
            status = "available"
        elif (
            recommendation_comment_ids
            or selected_generated_issue_numbers
            or decision_summary
            or selected_generated_issue_urls
            or applied_transition_targets
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

    lines.append("```")
    return lines