import json
import os
from collections import defaultdict
from datetime import datetime

from Handler.paths import get_circus_runtime_root, sanitize_filename_part


STATUS_FILENAME = "status.json"
REVIEW_RESULT_FILENAME = "review-result.md"
ARCHITECT_REVIEW_RESULT_FILENAME = "architect-review-result.md"
OUTPUT_JSON_FILENAME = "organizational-metrics.json"
OUTPUT_MARKDOWN_FILENAME = "organizational-metrics.md"
SCHEMA_VERSION = "1.0"
MAX_EXAMPLES_PER_BUCKET = 3
REQUIRED_STATUS_FIELDS = ["repository", "item_number", "mode", "outcome", "success", "state_label"]


def _normalize_bucket(value):
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else "unknown"
    return str(value)


def _normalize_repository_identifier(value):
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    normalized = value.strip().lower()
    return normalized or None


def _increment(counter, key, amount=1):
    normalized_key = _normalize_bucket(key)
    counter[normalized_key] = counter.get(normalized_key, 0) + amount


def _append_example(example_store, key, example):
    bucket = example_store.setdefault(key, [])
    if len(bucket) < MAX_EXAMPLES_PER_BUCKET:
        bucket.append(example)


def _sorted_counts(counter):
    return {key: counter[key] for key in sorted(counter)}


def _sorted_examples(example_store):
    return {key: example_store[key] for key in sorted(example_store)}


def discover_status_files(runtime_root):
    discovered = []
    for directory, _subdirectories, filenames in os.walk(runtime_root):
        if STATUS_FILENAME in filenames:
            discovered.append(os.path.join(directory, STATUS_FILENAME))
    discovered.sort()
    return discovered


def _read_json_file(path):
    with open(path, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _read_first_non_empty_line(path):
    if not os.path.isfile(path):
        return None

    with open(path, "r", encoding="utf-8") as file_handle:
        for line in file_handle:
            stripped = line.strip()
            if stripped:
                return stripped
    return None


def _parse_result_contract_outcome(path):
    first_line = _read_first_non_empty_line(path)
    if not first_line:
        return "missing"

    if not first_line.lower().startswith("outcome:"):
        return "unknown"

    return _normalize_bucket(first_line.split(":", 1)[1].strip().upper())


def _status_sort_key(record):
    repository = _normalize_bucket(record.get("repository"))
    item_type = _normalize_bucket(record.get("item_type"))
    item_number = _normalize_bucket(record.get("item_number"))
    run_dir = _normalize_bucket(record.get("run_dir"))
    return repository, item_type, item_number, run_dir


def _initialize_report(runtime_root, repository_filter, generated_at):
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "repository_filter": repository_filter,
        "sources": {
            "runtime_root": runtime_root,
            "status_files_discovered": 0,
            "status_files_included": 0,
        },
        "run_outcomes": {
            "success": {},
            "exit_code": {},
            "outcome": {},
            "mode": {},
            "state_label": {},
        },
        "blockers": {
            "counts": {},
            "examples": {},
        },
        "recovery_events": {
            "recovery_decision": {},
            "recovery_reason": {},
            "recovery_non_destructive": {},
            "dependency_status": {},
        },
        "review_churn": {
            "review_result_outcomes": {},
            "architect_review_result_outcomes": {},
            "review_run_outcomes": {},
            "developer_after_review_cycles": 0,
        },
        "implementation_plan_churn": {
            "planner_outcome": {},
            "invalid_or_missing_planner_outcome": 0,
            "generated_issue_count": {},
            "stale_check_status": {},
        },
        "traceability": {
            "recommendation_available": {},
            "accepted_decision_status": {},
            "generated_issue_availability": {},
            "reference_mismatch_diagnostics": {},
            "missing_traceability_records": 0,
        },
        "data_quality": {
            "malformed_status_files": 0,
            "missing_fields": {},
            "skipped_files": 0,
            "partial_records": 0,
            "notes": [
                "Missing and partial data is reported explicitly and was not inferred.",
            ],
        },
        "guardrails": {
            "control_signals_enabled": False,
        },
    }


def _record_missing_fields(report, status_payload):
    missing_any = False
    missing_counts = report["data_quality"]["missing_fields"]
    for field in REQUIRED_STATUS_FIELDS:
        value = status_payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing_any = True
            _increment(missing_counts, field)
    if missing_any:
        report["data_quality"]["partial_records"] += 1


def _collect_blockers(report, status_payload, status_path):
    blocker_counts = report["blockers"]["counts"]
    blocker_examples = report["blockers"]["examples"]

    stop_reason = status_payload.get("stop_reason")
    if stop_reason:
        key = f"stop_reason:{_normalize_bucket(stop_reason)}"
        _increment(blocker_counts, key)
        _append_example(blocker_examples, key, {"path": status_path})

    dependency_resolution = status_payload.get("dependency_resolution")
    if isinstance(dependency_resolution, dict):
        dependency_status = dependency_resolution.get("status")
        dependency_diagnostic = dependency_resolution.get("diagnostic")
        if dependency_status:
            key = f"dependency_status:{_normalize_bucket(dependency_status)}"
            _increment(blocker_counts, key)
            _append_example(blocker_examples, key, {"path": status_path})
        if dependency_diagnostic:
            key = f"dependency_diagnostic:{_normalize_bucket(dependency_diagnostic)}"
            _increment(blocker_counts, key)

    lifecycle_diagnostics = status_payload.get("lifecycle_diagnostics")
    if isinstance(lifecycle_diagnostics, dict):
        if lifecycle_diagnostics.get("ambiguous"):
            key = "lifecycle_ambiguous"
            _increment(blocker_counts, key)
            _append_example(blocker_examples, key, {"path": status_path})
        reasons = lifecycle_diagnostics.get("reasons")
        if isinstance(reasons, list):
            for reason in reasons:
                key = f"lifecycle_reason:{_normalize_bucket(reason)}"
                _increment(blocker_counts, key)

    accepted_traceability = status_payload.get("accepted_decision_traceability")
    if isinstance(accepted_traceability, dict):
        diagnostic = accepted_traceability.get("diagnostic")
        if diagnostic:
            key = f"accepted_traceability_diagnostic:{_normalize_bucket(diagnostic)}"
            _increment(blocker_counts, key)

    human_ledger = status_payload.get("human_decision_ledger_v1")
    if isinstance(human_ledger, dict):
        diagnostic = human_ledger.get("diagnostic")
        if diagnostic:
            key = f"human_ledger_diagnostic:{_normalize_bucket(diagnostic)}"
            _increment(blocker_counts, key)

    workflow_classification = status_payload.get("workflow_classification")
    if isinstance(workflow_classification, dict):
        diagnostics = workflow_classification.get("diagnostics")
        if isinstance(diagnostics, list):
            for diagnostic in diagnostics:
                key = f"workflow_classification_diagnostic:{_normalize_bucket(diagnostic)}"
                _increment(blocker_counts, key)


def _collect_recovery_events(report, status_payload):
    recovery_events = report["recovery_events"]
    _increment(recovery_events["recovery_decision"], status_payload.get("recovery_decision"))
    _increment(recovery_events["recovery_reason"], status_payload.get("recovery_reason"))
    _increment(recovery_events["recovery_non_destructive"], status_payload.get("recovery_non_destructive"))

    dependency_resolution = status_payload.get("dependency_resolution")
    dependency_status = None
    if isinstance(dependency_resolution, dict):
        dependency_status = dependency_resolution.get("status")
    _increment(recovery_events["dependency_status"], dependency_status)


def _collect_implementation_plan_churn(report, status_payload):
    planner_section = report["implementation_plan_churn"]
    implementation_planner = status_payload.get("implementation_planner")
    planner_outcome = None
    planner_outcome_valid = None
    if isinstance(implementation_planner, dict):
        planner_outcome = implementation_planner.get("outcome")
        planner_outcome_valid = implementation_planner.get("outcome_valid")

    _increment(planner_section["planner_outcome"], planner_outcome)
    if planner_outcome is None or planner_outcome_valid is False:
        planner_section["invalid_or_missing_planner_outcome"] += 1

    accepted_traceability = status_payload.get("accepted_decision_traceability")
    generated_issue_count = 0
    if isinstance(accepted_traceability, dict):
        generated_issue_numbers = accepted_traceability.get("generated_issue_numbers")
        if isinstance(generated_issue_numbers, list):
            generated_issue_count = len(generated_issue_numbers)
    _increment(planner_section["generated_issue_count"], generated_issue_count)

    stale_status = None
    human_ledger = status_payload.get("human_decision_ledger_v1")
    if isinstance(human_ledger, dict):
        stale_check = human_ledger.get("stale_check")
        if isinstance(stale_check, dict):
            stale_status = stale_check.get("status")
    _increment(planner_section["stale_check_status"], stale_status)


def _collect_traceability(report, status_payload):
    traceability = report["traceability"]
    recommendation = status_payload.get("recommendation_traceability")
    accepted = status_payload.get("accepted_decision_traceability")

    recommendation_available = None
    if isinstance(recommendation, dict):
        recommendation_available = recommendation.get("available")
    _increment(traceability["recommendation_available"], recommendation_available)

    accepted_status = None
    diagnostic = None
    generated_issue_numbers = None
    if isinstance(accepted, dict):
        accepted_status = accepted.get("status")
        diagnostic = accepted.get("diagnostic")
        generated_issue_numbers = accepted.get("generated_issue_numbers")
    _increment(traceability["accepted_decision_status"], accepted_status)

    generated_issue_available = False
    if isinstance(generated_issue_numbers, list) and generated_issue_numbers:
        generated_issue_available = True
    _increment(traceability["generated_issue_availability"], generated_issue_available)

    if diagnostic:
        _increment(traceability["reference_mismatch_diagnostics"], diagnostic)
    elif accepted_status == "reference_mismatch":
        _increment(traceability["reference_mismatch_diagnostics"], "reference_mismatch")

    recommendation_missing = recommendation_available in {None, False}
    accepted_missing = accepted_status in {None, "missing", "unknown"}
    if recommendation_missing and accepted_missing:
        traceability["missing_traceability_records"] += 1


def _collect_run_outcomes(report, status_payload):
    run_outcomes = report["run_outcomes"]
    _increment(run_outcomes["success"], status_payload.get("success"))
    _increment(run_outcomes["exit_code"], status_payload.get("exit_code"))
    _increment(run_outcomes["outcome"], status_payload.get("outcome"))
    _increment(run_outcomes["mode"], status_payload.get("mode"))
    _increment(run_outcomes["state_label"], status_payload.get("state_label"))


def _collect_review_outcomes(report, status_payload, status_path):
    run_directory = os.path.dirname(status_path)
    review_churn = report["review_churn"]

    review_result_path = os.path.join(run_directory, REVIEW_RESULT_FILENAME)
    review_outcome = _parse_result_contract_outcome(review_result_path)
    _increment(review_churn["review_result_outcomes"], review_outcome)

    architect_review_result_path = os.path.join(run_directory, ARCHITECT_REVIEW_RESULT_FILENAME)
    architect_review_outcome = _parse_result_contract_outcome(architect_review_result_path)
    _increment(review_churn["architect_review_result_outcomes"], architect_review_outcome)

    mode = _normalize_bucket(status_payload.get("mode"))
    if mode in {"reviewer", "architect-review"}:
        key = f"{mode}:{_normalize_bucket(status_payload.get('outcome'))}"
        _increment(review_churn["review_run_outcomes"], key)


def _finalize_item_cycle_metrics(report, status_records):
    item_modes = defaultdict(list)
    for status_payload in sorted(status_records, key=_status_sort_key):
        item_key = (
            _normalize_bucket(status_payload.get("repository")),
            _normalize_bucket(status_payload.get("item_type")),
            _normalize_bucket(status_payload.get("item_number")),
        )
        item_modes[item_key].append(_normalize_bucket(status_payload.get("mode")))

    cycle_count = 0
    for modes in item_modes.values():
        previous_mode = None
        for mode in modes:
            if mode == "developer" and previous_mode in {"reviewer", "architect-review"}:
                cycle_count += 1
            previous_mode = mode
    report["review_churn"]["developer_after_review_cycles"] = cycle_count


def _finalize_report(report):
    for key in ["success", "exit_code", "outcome", "mode", "state_label"]:
        report["run_outcomes"][key] = _sorted_counts(report["run_outcomes"][key])

    report["blockers"]["counts"] = _sorted_counts(report["blockers"]["counts"])
    report["blockers"]["examples"] = _sorted_examples(report["blockers"]["examples"])

    for key in ["recovery_decision", "recovery_reason", "recovery_non_destructive", "dependency_status"]:
        report["recovery_events"][key] = _sorted_counts(report["recovery_events"][key])

    for key in [
        "review_result_outcomes",
        "architect_review_result_outcomes",
        "review_run_outcomes",
    ]:
        report["review_churn"][key] = _sorted_counts(report["review_churn"][key])

    for key in ["planner_outcome", "generated_issue_count", "stale_check_status"]:
        report["implementation_plan_churn"][key] = _sorted_counts(report["implementation_plan_churn"][key])

    for key in [
        "recommendation_available",
        "accepted_decision_status",
        "generated_issue_availability",
        "reference_mismatch_diagnostics",
    ]:
        report["traceability"][key] = _sorted_counts(report["traceability"][key])

    report["data_quality"]["missing_fields"] = _sorted_counts(report["data_quality"]["missing_fields"])


def aggregate_organizational_metrics(status_files, *, repository_filter=None, runtime_root=None, generated_at=None):
    timestamp = generated_at or datetime.now().isoformat(timespec="seconds")
    report = _initialize_report(runtime_root, repository_filter, timestamp)
    normalized_repository_filter = _normalize_repository_identifier(repository_filter)

    report["sources"]["status_files_discovered"] = len(status_files)
    included_records = []

    for status_path in status_files:
        try:
            status_payload = _read_json_file(status_path)
        except (OSError, json.JSONDecodeError):
            report["data_quality"]["malformed_status_files"] += 1
            continue

        if not isinstance(status_payload, dict):
            report["data_quality"]["malformed_status_files"] += 1
            continue

        status_repository = status_payload.get("repository")
        normalized_status_repository = _normalize_repository_identifier(status_repository)
        if normalized_repository_filter and normalized_status_repository != normalized_repository_filter:
            report["data_quality"]["skipped_files"] += 1
            continue

        report["sources"]["status_files_included"] += 1
        included_records.append(status_payload)

        _record_missing_fields(report, status_payload)
        _collect_run_outcomes(report, status_payload)
        _collect_blockers(report, status_payload, status_path)
        _collect_recovery_events(report, status_payload)
        _collect_review_outcomes(report, status_payload, status_path)
        _collect_implementation_plan_churn(report, status_payload)
        _collect_traceability(report, status_payload)

    _finalize_item_cycle_metrics(report, included_records)
    _finalize_report(report)
    return report


def render_metrics_markdown(report):
    lines = [
        "# Organizational Metrics",
        "",
        f"- schema_version: `{report.get('schema_version')}`",
        f"- generated_at: `{report.get('generated_at')}`",
        f"- repository_filter: `{report.get('repository_filter')}`",
        f"- status_files_discovered: `{(report.get('sources') or {}).get('status_files_discovered')}`",
        f"- status_files_included: `{(report.get('sources') or {}).get('status_files_included')}`",
        "",
        "## Guardrails",
        f"- control_signals_enabled: `{(report.get('guardrails') or {}).get('control_signals_enabled')}`",
        "",
        "## Run Outcomes",
    ]

    run_outcomes = report.get("run_outcomes") or {}
    for section_name in ["success", "exit_code", "outcome", "mode", "state_label"]:
        lines.append(f"- {section_name}:")
        values = run_outcomes.get(section_name) or {}
        if values:
            for key in sorted(values):
                lines.append(f"  - {key}: {values[key]}")
        else:
            lines.append("  - none")

    blockers = report.get("blockers") or {}
    lines.extend(["", "## Blockers"])
    blocker_counts = blockers.get("counts") or {}
    if blocker_counts:
        for key in sorted(blocker_counts):
            lines.append(f"- {key}: {blocker_counts[key]}")
    else:
        lines.append("- none")

    lines.extend(["", "## Data Quality"])
    data_quality = report.get("data_quality") or {}
    lines.append(f"- malformed_status_files: {(data_quality.get('malformed_status_files'))}")
    lines.append(f"- partial_records: {(data_quality.get('partial_records'))}")
    lines.append(f"- skipped_files: {(data_quality.get('skipped_files'))}")

    return "\n".join(lines) + "\n"


def resolve_default_output_dir(runtime_root, repository_filter):
    repository_slug = sanitize_filename_part(repository_filter or "all-repositories")
    return os.path.join(runtime_root, "Watchtower", "metrics", repository_slug)


def write_metrics_artifacts(report, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, OUTPUT_JSON_FILENAME)
    markdown_path = os.path.join(output_dir, OUTPUT_MARKDOWN_FILENAME)

    with open(json_path, "w", encoding="utf-8") as json_handle:
        json.dump(report, json_handle, indent=2)
        json_handle.write("\n")

    markdown_content = render_metrics_markdown(report)
    with open(markdown_path, "w", encoding="utf-8") as markdown_handle:
        markdown_handle.write(markdown_content)

    return {
        "json_path": json_path,
        "markdown_path": markdown_path,
    }


def generate_organizational_metrics(*, repo=None, output_dir=None, runtime_root=None, generated_at=None):
    runtime_root = runtime_root or get_circus_runtime_root(__file__)
    repository_filter = repo if repo is not None else os.getenv("CIRCUS_REPO")
    status_files = discover_status_files(runtime_root)

    report = aggregate_organizational_metrics(
        status_files,
        repository_filter=repository_filter,
        runtime_root=runtime_root,
        generated_at=generated_at,
    )

    resolved_output_dir = output_dir or resolve_default_output_dir(runtime_root, repository_filter)
    artifact_paths = write_metrics_artifacts(report, resolved_output_dir)
    return {
        "report": report,
        "output_dir": resolved_output_dir,
        **artifact_paths,
    }
