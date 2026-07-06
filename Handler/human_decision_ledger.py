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


def _normalize_rationale_summary(value, diagnostics):
    if value is None:
        return None

    if not isinstance(value, str):
        diagnostics.append("rationale_summary must be a non-empty string")
        return None

    stripped_value = value.strip()
    if not stripped_value:
        diagnostics.append("rationale_summary must be a non-empty string")
        return None

    return stripped_value


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
    rationale_summary = _normalize_rationale_summary(raw_human_decision_ledger.get("rationale_summary"), diagnostics)

    if recommendation_comment_ids is None or selected_generated_issue_numbers is None:
        status = "invalid"
        recommendation_comment_ids = recommendation_comment_ids or []
        selected_generated_issue_numbers = selected_generated_issue_numbers or []

    if not recommendation_comment_ids and fallback_recommendation_comment_id is not None:
        recommendation_comment_ids = [fallback_recommendation_comment_id]
        diagnostics.append("recommendation_comment_ids defaulted from recommendation_comment_id")

    if not selected_generated_issue_numbers and fallback_generated_issue_numbers:
        selected_generated_issue_numbers = fallback_generated_issue_numbers
        diagnostics.append("selected_generated_issue_numbers defaulted from generated_issues")

    if rationale_summary is None:
        diagnostics.append("rationale_summary missing")

    if status != "invalid":
        has_all_required_fields = bool(
            recommendation_comment_ids and selected_generated_issue_numbers and rationale_summary
        )
        if has_all_required_fields:
            status = "available"
        elif recommendation_comment_ids or selected_generated_issue_numbers or rationale_summary:
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
        "recommendation_comment_ids": recommendation_comment_ids,
        "based_on_recommendation_comment_ids": recommendation_comment_ids,
        "selected_generated_issue_numbers": selected_generated_issue_numbers,
        "rationale_summary": rationale_summary,
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

    rationale_summary = human_decision_ledger.get("rationale_summary")
    if isinstance(rationale_summary, str):
        lines.append(f"  rationale_summary: {rationale_summary!r}")
    else:
        lines.append("  rationale_summary:")

    lines.append("```")
    return lines