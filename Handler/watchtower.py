import json
import os
import re
from datetime import datetime

from Handler import human_decision_ledger
from Handler import target_instructions
from Handler import workspace_diagnostics


SHARED_ARTIFACT_PLACEHOLDERS = {
    "architecture-handoff.md": "# Architecture Handoff\n\nNo architecture handoff has been recorded yet.",
    "running-notes.md": "# Running Notes\n\nNo running notes have been recorded yet.",
    "decision-log.md": "# Decision Log\n\nNo decisions have been recorded yet.",
}

REVIEW_RESULT_FILENAME = "review-result.md"
ARCHITECT_REVIEW_RESULT_FILENAME = "architect-review-result.md"
IMPLEMENTATION_PLAN_FILENAME = "implementation-plan.md"
RUN_STATUS_FILENAME = "status.json"
RUN_RESULT_FILENAME = "result.md"
ISSUE_URL_PATTERN = re.compile(r"https://github\.com/[^\s)]+/issues/(\d+)(?:#[^\s)]+)?", re.IGNORECASE)
ISSUE_REFERENCE_PATTERN = re.compile(r"(?<![A-Za-z0-9_])#(\d+)\b")
ISSUE_COMMENT_URL_PATTERN = re.compile(
    r"https://github\.com/[^\s)]+/issues/\d+#issuecomment-(\d+)",
    re.IGNORECASE,
)
PULL_REQUEST_URL_PATTERN = re.compile(r"https://github\.com/[^\s)]+/pull/\d+", re.IGNORECASE)

RUN_STATUS_FIELDS = [
    "repository",
    "item_type",
    "item_number",
    "item_title",
    "state_label",
    "agent",
    "mode",
    "model",
    "effort",
    "target_repo_path",
    "worktree_root",
    "worktree_root_source",
    "workspace_name",
    "workspace_path",
    "workspace_branch",
    "workspace_lifecycle",
    "lifecycle_diagnostics",
    "workspace_item_identity",
    "run_dir",
    "launch_brief_path",
    "started_at",
    "completed_at",
    "exit_code",
    "success",
    "outcome",
    "stop_reason",
    "linked_pr",
    "working_branch",
    "label_transition",
    "artifacts",
    "implementation_planner",
    "workflow_classification",
    "recommendation_traceability",
    "accepted_decision_traceability",
    "human_decision_ledger_v1",
    "recovery_decision",
    "recovery_reason",
    "recovery_recommendation",
    "recovery_blockers",
    "recovery_non_destructive",
    "recovery_comment_posted",
    "recovery_comment_signature",
    "dependency_resolution",
]


def _trim_trailing_markdown_punctuation(value):
    return value.rstrip(")].,;:!?")


def _extract_markdown_section_lines(markdown_text, section_heading):
    lines = markdown_text.splitlines()
    in_target_section = False
    heading_prefix = "### "
    normalized_target_heading = f"{heading_prefix}{section_heading}".strip().lower()
    collected_lines = []

    for raw_line in lines:
        stripped_line = raw_line.strip()
        normalized_line = stripped_line.lower()

        if normalized_line == normalized_target_heading:
            in_target_section = True
            continue

        if in_target_section and (stripped_line.startswith("### ") or stripped_line.startswith("## ")):
            break

        if in_target_section:
            collected_lines.append(raw_line)

    return collected_lines


def _parse_generated_issue_references(generated_issue_section_lines):
    generated_issue_blocks = _parse_generated_issue_blocks(generated_issue_section_lines)
    ordered_issue_numbers = []
    generated_issues_by_number = {}

    for generated_issue in generated_issue_blocks:
        issue_number = generated_issue["number"]
        existing_issue = generated_issues_by_number.get(issue_number)
        if existing_issue is None:
            generated_issues_by_number[issue_number] = {
                "number": issue_number,
                "url": generated_issue.get("url"),
            }
            ordered_issue_numbers.append(issue_number)
            continue

        if not existing_issue.get("url") and generated_issue.get("url"):
            existing_issue["url"] = generated_issue.get("url")

    return [generated_issues_by_number[number] for number in ordered_issue_numbers]


def _parse_generated_issue_blocks(generated_issue_section_lines):
    generated_issue_blocks = []
    current_block = None

    for section_line in generated_issue_section_lines:
        raw_line = section_line.rstrip()
        normalized_line = _trim_trailing_markdown_punctuation(raw_line.strip())
        if not raw_line.strip():
            continue

        line_indentation = len(raw_line) - len(raw_line.lstrip())
        stripped_line = raw_line.lstrip()
        bullet_prefix_match = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.*)$", stripped_line)

        heading_payload = None
        if line_indentation == 0 and bullet_prefix_match:
            heading_payload = bullet_prefix_match.group(1).strip()
        elif line_indentation == 0 and current_block is None:
            heading_payload = normalized_line

        issue_reference = _extract_first_issue_reference(heading_payload) if heading_payload else None

        if issue_reference is not None:
            current_block = {
                "number": issue_reference["number"],
                "url": issue_reference.get("url"),
                "lines": [normalized_line],
            }
            generated_issue_blocks.append(current_block)
            continue

        if current_block is not None:
            current_block["lines"].append(normalized_line)

    return generated_issue_blocks


def _extract_first_issue_reference(line):
    issue_url_match = ISSUE_URL_PATTERN.search(line)
    if issue_url_match:
        return {
            "number": int(issue_url_match.group(1)),
            "url": _trim_trailing_markdown_punctuation(issue_url_match.group(0)),
        }

    issue_reference_match = ISSUE_REFERENCE_PATTERN.search(line)
    if issue_reference_match:
        return {
            "number": int(issue_reference_match.group(1)),
            "url": None,
        }

    return None


def _extract_source_traceability_fields(source_section_lines):
    source_recommendation_url = None
    source_recommendation_comment_id = None
    roadmap_reference = None

    for source_line in source_section_lines:
        normalized_line = _trim_trailing_markdown_punctuation(source_line.strip())
        if not normalized_line:
            continue

        if source_recommendation_url is None:
            issue_comment_match = ISSUE_COMMENT_URL_PATTERN.search(normalized_line)
            if issue_comment_match:
                source_recommendation_url = _trim_trailing_markdown_punctuation(issue_comment_match.group(0))
                source_recommendation_comment_id = int(issue_comment_match.group(1))

        if roadmap_reference is None:
            pull_request_match = PULL_REQUEST_URL_PATTERN.search(normalized_line)
            if pull_request_match:
                roadmap_reference = _trim_trailing_markdown_punctuation(pull_request_match.group(0))

        if source_recommendation_url and roadmap_reference:
            break

    return {
        "source_recommendation_url": source_recommendation_url,
        "source_recommendation_comment_id": source_recommendation_comment_id,
        "roadmap_reference": roadmap_reference,
    }


def _extract_issue_comment_id_from_url(value):
    if not isinstance(value, str):
        return None

    issue_comment_match = ISSUE_COMMENT_URL_PATTERN.search(value)
    if issue_comment_match:
        return int(issue_comment_match.group(1))

    return None


def _extract_pull_request_number_from_url(value):
    if not isinstance(value, str):
        return None

    pull_request_match = PULL_REQUEST_URL_PATTERN.search(value)
    if pull_request_match:
        pull_request_number_match = re.search(r"/pull/(\d+)", pull_request_match.group(0), re.IGNORECASE)
        if pull_request_number_match:
            return int(pull_request_number_match.group(1))

    return None


def build_recommendation_traceability_snapshot(
    *,
    recommendation_url=None,
    recommendation_comment_id=None,
    source_issue=None,
    roadmap_reference=None,
    source=None,
    diagnostic=None,
):
    normalized_recommendation_url = recommendation_url if isinstance(recommendation_url, str) else None
    normalized_comment_id = recommendation_comment_id if isinstance(recommendation_comment_id, int) else None

    if normalized_comment_id is None and normalized_recommendation_url:
        issue_comment_match = ISSUE_COMMENT_URL_PATTERN.search(normalized_recommendation_url)
        if issue_comment_match:
            normalized_comment_id = int(issue_comment_match.group(1))

    available = bool(normalized_recommendation_url and normalized_comment_id)
    normalized_diagnostic = diagnostic
    if not available and normalized_diagnostic is None:
        normalized_diagnostic = "not provided"

    return {
        "available": available,
        "recommendation_url": normalized_recommendation_url if available else None,
        "recommendation_comment_id": normalized_comment_id if available else None,
        "source_issue": source_issue,
        "roadmap_reference": roadmap_reference,
        "source": source,
        "diagnostic": normalized_diagnostic,
    }


def build_unavailable_recommendation_traceability_snapshot(
    *,
    source_issue=None,
    roadmap_reference=None,
    source=None,
    diagnostic="not provided",
):
    return build_recommendation_traceability_snapshot(
        recommendation_url=None,
        recommendation_comment_id=None,
        source_issue=source_issue,
        roadmap_reference=roadmap_reference,
        source=source,
        diagnostic=diagnostic,
    )


def _extract_comment_url(comment):
    if not isinstance(comment, dict):
        return None

    for candidate_key in ("html_url", "url"):
        candidate_value = comment.get(candidate_key)
        if not isinstance(candidate_value, str):
            continue

        issue_comment_match = ISSUE_COMMENT_URL_PATTERN.search(candidate_value)
        if issue_comment_match:
            return _trim_trailing_markdown_punctuation(issue_comment_match.group(0))

    comment_body = comment.get("body")
    if isinstance(comment_body, str):
        issue_comment_match = ISSUE_COMMENT_URL_PATTERN.search(comment_body)
        if issue_comment_match:
            return _trim_trailing_markdown_punctuation(issue_comment_match.group(0))

    return None


def _extract_comment_id(comment):
    if not isinstance(comment, dict):
        return None

    for candidate_key in ("id", "databaseId"):
        candidate_value = comment.get(candidate_key)
        if isinstance(candidate_value, int):
            return candidate_value
        if isinstance(candidate_value, str) and candidate_value.strip().isdigit():
            return int(candidate_value.strip())

    comment_url = _extract_comment_url(comment)
    if not comment_url:
        return None

    issue_comment_match = ISSUE_COMMENT_URL_PATTERN.search(comment_url)
    if issue_comment_match:
        return int(issue_comment_match.group(1))

    return None


def extract_issue_comment_recommendation_traceability(
    comments,
    *,
    source_issue=None,
    roadmap_reference=None,
    source="roadmap-updater",
):
    if not isinstance(comments, list):
        return build_unavailable_recommendation_traceability_snapshot(
            source_issue=source_issue,
            roadmap_reference=roadmap_reference,
            source=source,
            diagnostic="accepted recommendation unavailable",
        )

    recommendation_candidates = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue

        comment_body = comment.get("body")
        if not isinstance(comment_body, str):
            continue

        if "## systems architect recommendation" not in comment_body.lower():
            continue

        recommendation_url = _extract_comment_url(comment)
        recommendation_comment_id = _extract_comment_id(comment)
        if recommendation_url and recommendation_comment_id:
            recommendation_candidates.append(
                {
                    "recommendation_url": recommendation_url,
                    "recommendation_comment_id": recommendation_comment_id,
                }
            )

    if len(recommendation_candidates) == 1:
        recommendation_candidate = recommendation_candidates[0]
        return build_recommendation_traceability_snapshot(
            recommendation_url=recommendation_candidate["recommendation_url"],
            recommendation_comment_id=recommendation_candidate["recommendation_comment_id"],
            source_issue=source_issue,
            roadmap_reference=roadmap_reference,
            source=source,
            diagnostic=None,
        )

    diagnostic = "accepted recommendation unavailable"
    if len(recommendation_candidates) > 1:
        diagnostic = "accepted recommendation ambiguous"

    return build_unavailable_recommendation_traceability_snapshot(
        source_issue=source_issue,
        roadmap_reference=roadmap_reference,
        source=source,
        diagnostic=diagnostic,
    )


def build_implementation_planner_recommendation_traceability_snapshot(
    implementation_planner_snapshot,
    *,
    source_issue=None,
):
    if not isinstance(implementation_planner_snapshot, dict):
        return build_unavailable_recommendation_traceability_snapshot(
            source_issue=source_issue,
            source="implementation-planner",
            diagnostic="not provided",
        )

    return build_recommendation_traceability_snapshot(
        recommendation_url=implementation_planner_snapshot.get("source_recommendation_url"),
        recommendation_comment_id=implementation_planner_snapshot.get("source_recommendation_comment_id"),
        source_issue=source_issue,
        roadmap_reference=implementation_planner_snapshot.get("roadmap_reference"),
        source="implementation-planner",
        diagnostic="not provided",
    )


def build_implementation_planner_snapshot(
    implementation_plan_path,
    *,
    outcome,
    outcome_valid,
    diagnostic=None,
    recommended_route=None,
    planner_result_comment_id=None,
    planner_result_comment_url=None,
    parent_issue=None,
    recommendation_comment_id=None,
    roadmap_pr_number=None,
    roadmap_reference_merged=None,
    generated_issues=None,
    human_decision_ledger_v1=None,
):
    generated_issue_links = []
    source_recommendation_url = None
    source_recommendation_comment_id = None
    roadmap_reference = None

    if implementation_plan_path and os.path.exists(implementation_plan_path):
        try:
            with open(implementation_plan_path, "r", encoding="utf-8") as implementation_plan_file:
                implementation_plan_markdown = implementation_plan_file.read()
            generated_issue_section_lines = _extract_markdown_section_lines(implementation_plan_markdown, "generated issues")
            generated_issue_links = _parse_generated_issue_references(generated_issue_section_lines)
            source_section_lines = _extract_markdown_section_lines(implementation_plan_markdown, "source")
            source_traceability_fields = _extract_source_traceability_fields(source_section_lines)
            source_recommendation_url = source_traceability_fields["source_recommendation_url"]
            source_recommendation_comment_id = source_traceability_fields["source_recommendation_comment_id"]
            roadmap_reference = source_traceability_fields["roadmap_reference"]
        except OSError:
            pass

    merged_generated_issues = []
    generated_issues_by_number = {}
    for generated_issue_link in generated_issue_links:
        issue_number = generated_issue_link.get("number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            continue
        normalized_generated_issue = {
            "number": issue_number,
            "url": generated_issue_link.get("url") if isinstance(generated_issue_link.get("url"), str) else None,
            "initial_state": None,
            "next_state_after_approval": None,
            "dependencies": None,
        }
        generated_issues_by_number[issue_number] = normalized_generated_issue
        merged_generated_issues.append(normalized_generated_issue)

    if isinstance(generated_issues, list):
        for generated_issue in generated_issues:
            if not isinstance(generated_issue, dict):
                continue

            issue_number = generated_issue.get("issue_number")
            if issue_number is None:
                issue_number = generated_issue.get("number")
            if not isinstance(issue_number, int) or issue_number <= 0:
                continue

            normalized_generated_issue = generated_issues_by_number.get(issue_number)
            if normalized_generated_issue is None:
                normalized_generated_issue = {
                    "number": issue_number,
                    "url": generated_issue.get("url") if isinstance(generated_issue.get("url"), str) else None,
                    "initial_state": None,
                    "next_state_after_approval": None,
                    "dependencies": None,
                }
                generated_issues_by_number[issue_number] = normalized_generated_issue
                merged_generated_issues.append(normalized_generated_issue)

            initial_state = generated_issue.get("initial_state")
            if isinstance(initial_state, str) and initial_state:
                normalized_generated_issue["initial_state"] = initial_state

            next_state_after_approval = generated_issue.get("next_state_after_approval")
            if isinstance(next_state_after_approval, str) and next_state_after_approval:
                normalized_generated_issue["next_state_after_approval"] = next_state_after_approval

            dependencies = generated_issue.get("dependencies")
            if isinstance(dependencies, list):
                normalized_generated_issue["dependencies"] = dependencies

    snapshot = {
        "outcome": outcome,
        "outcome_valid": bool(outcome_valid),
        "diagnostic": diagnostic,
        "implementation_plan": implementation_plan_path,
        "generated_issues": merged_generated_issues,
        "source_recommendation_url": source_recommendation_url,
        "source_recommendation_comment_id": source_recommendation_comment_id,
        "roadmap_reference": roadmap_reference,
        "recommended_route": recommended_route,
        "planner_result_comment_id": planner_result_comment_id,
        "planner_result_comment_url": planner_result_comment_url,
        "parent_issue": parent_issue,
        "recommendation_comment_id": recommendation_comment_id,
        "roadmap_pr_number": roadmap_pr_number,
        "roadmap_reference_merged": roadmap_reference_merged,
        "human_decision_ledger_v1": human_decision_ledger_v1,
    }

    snapshot["recommendation_traceability"] = build_implementation_planner_recommendation_traceability_snapshot(snapshot)
    return snapshot


def _normalize_traceability_generated_issue(generated_issue, repository):
    if not isinstance(generated_issue, dict):
        return None

    issue_number = generated_issue.get("number")
    if not isinstance(issue_number, int):
        issue_number = generated_issue.get("issue_number")
    if not isinstance(issue_number, int) or issue_number <= 0:
        return None

    normalized_generated_issue = {
        "repo": repository,
        "number": issue_number,
        "url": generated_issue.get("url") if isinstance(generated_issue.get("url"), str) else None,
        "initial_state": generated_issue.get("initial_state") if isinstance(generated_issue.get("initial_state"), str) else None,
        "suggested_next_state": (
            generated_issue.get("next_state_after_approval")
            if isinstance(generated_issue.get("next_state_after_approval"), str)
            else None
        ),
        "dependencies": generated_issue.get("dependencies") if isinstance(generated_issue.get("dependencies"), list) else None,
    }
    return normalized_generated_issue


def build_accepted_decision_traceability_snapshot(
    *,
    repository,
    source_issue,
    recommendation_traceability=None,
    implementation_planner=None,
):
    diagnostics = []
    status = "missing"

    recommendation_traceability = recommendation_traceability if isinstance(recommendation_traceability, dict) else {}
    implementation_planner = implementation_planner if isinstance(implementation_planner, dict) else {}

    recommendation_url = recommendation_traceability.get("recommendation_url")
    recommendation_comment_id = recommendation_traceability.get("recommendation_comment_id")
    recommendation_source_issue = recommendation_traceability.get("source_issue")
    recommendation_diagnostic = recommendation_traceability.get("diagnostic")
    roadmap_reference = recommendation_traceability.get("roadmap_reference")

    planner_source_issue = implementation_planner.get("parent_issue")
    if not isinstance(planner_source_issue, int) or planner_source_issue <= 0:
        planner_source_issue = source_issue if isinstance(source_issue, int) and source_issue > 0 else None

    planner_recommendation_comment_id = implementation_planner.get("recommendation_comment_id")
    if not isinstance(planner_recommendation_comment_id, int) or planner_recommendation_comment_id <= 0:
        planner_recommendation_comment_id = None

    planner_roadmap_pr = implementation_planner.get("roadmap_pr_number")
    if not isinstance(planner_roadmap_pr, int) or planner_roadmap_pr <= 0:
        planner_roadmap_pr = None

    if not isinstance(recommendation_url, str) or not recommendation_url:
        recommendation_url = implementation_planner.get("source_recommendation_url")
    if not isinstance(recommendation_comment_id, int):
        recommendation_comment_id = implementation_planner.get("source_recommendation_comment_id")
    if not isinstance(roadmap_reference, str) or not roadmap_reference:
        roadmap_reference = implementation_planner.get("roadmap_reference")

    if not isinstance(recommendation_comment_id, int) or recommendation_comment_id <= 0:
        recommendation_comment_id = _extract_issue_comment_id_from_url(recommendation_url)

    observed_roadmap_pr = _extract_pull_request_number_from_url(roadmap_reference)
    roadmap_pr_number = implementation_planner.get("roadmap_pr_number")
    if not isinstance(roadmap_pr_number, int) or roadmap_pr_number <= 0:
        roadmap_pr_number = observed_roadmap_pr

    roadmap_reference_merged = implementation_planner.get("roadmap_reference_merged")
    if not isinstance(roadmap_reference_merged, bool):
        roadmap_reference_merged = None

    planner_result_comment_id = implementation_planner.get("planner_result_comment_id")
    if not isinstance(planner_result_comment_id, int) or planner_result_comment_id <= 0:
        planner_result_comment_id = _extract_issue_comment_id_from_url(
            implementation_planner.get("planner_result_comment_url")
        )

    recommendation_available = bool(
        isinstance(recommendation_url, str)
        and recommendation_url
        and isinstance(recommendation_comment_id, int)
        and recommendation_comment_id > 0
    )
    if recommendation_available:
        status = "partial"
    elif isinstance(recommendation_diagnostic, str) and "ambiguous" in recommendation_diagnostic.lower():
        status = "ambiguous"
        diagnostics.append("accepted recommendation ambiguous")
    elif recommendation_url or recommendation_comment_id:
        status = "partial"
        diagnostics.append("accepted recommendation reference incomplete")
    else:
        diagnostics.append("accepted recommendation missing")

    if not roadmap_reference:
        diagnostics.append("roadmap reference missing")
    else:
        status = "partial" if status == "missing" else status

    if isinstance(recommendation_source_issue, int) and recommendation_source_issue > 0:
        if planner_source_issue is not None and recommendation_source_issue != planner_source_issue:
            diagnostics.append("source issue reference mismatches planner metadata")
            status = "reference_mismatch"

    if recommendation_available and planner_recommendation_comment_id is not None:
        if recommendation_comment_id != planner_recommendation_comment_id:
            diagnostics.append("accepted recommendation reference mismatches planner metadata")
            status = "reference_mismatch"

    if observed_roadmap_pr is not None and planner_roadmap_pr is not None:
        if observed_roadmap_pr != planner_roadmap_pr:
            diagnostics.append("roadmap reference mismatches planner metadata")
            status = "reference_mismatch"

    if roadmap_reference_merged is False:
        diagnostics.append("roadmap reference is stale (not merged)")
        status = "reference_mismatch"

    generated_issues = []
    generated_issues_raw = implementation_planner.get("generated_issues")
    if isinstance(generated_issues_raw, list):
        for generated_issue in generated_issues_raw:
            normalized_generated_issue = _normalize_traceability_generated_issue(generated_issue, repository)
            if normalized_generated_issue is not None:
                generated_issues.append(normalized_generated_issue)

    if not generated_issues:
        diagnostics.append("generated issues missing")
    else:
        status = "partial" if status == "missing" else status

    planner_outcome = implementation_planner.get("outcome") if isinstance(implementation_planner.get("outcome"), str) else None
    if not planner_outcome:
        diagnostics.append("planner outcome missing")
    else:
        status = "partial" if status == "missing" else status

    planner_artifact = implementation_planner.get("implementation_plan")
    if not isinstance(planner_artifact, str):
        planner_artifact = None

    outcome_states = [
        generated_issue.get("suggested_next_state")
        for generated_issue in generated_issues
        if isinstance(generated_issue.get("suggested_next_state"), str)
    ]
    unique_outcome_states = sorted(set(outcome_states))
    if len(unique_outcome_states) == 1:
        outcome_state = unique_outcome_states[0]
    elif len(unique_outcome_states) > 1:
        outcome_state = None
        diagnostics.append("generated issue next-state references are inconsistent")
        status = "reference_mismatch"
    else:
        outcome_state = None
        diagnostics.append("generated issue next-state references missing")

    if (
        status not in {"ambiguous", "reference_mismatch"}
        and recommendation_available
        and roadmap_reference
        and planner_outcome
        and generated_issues
        and outcome_state
    ):
        status = "available"

    if isinstance(recommendation_diagnostic, str) and recommendation_diagnostic and recommendation_diagnostic not in {
        "not provided",
        "accepted recommendation unavailable",
    }:
        diagnostics.append(recommendation_diagnostic)

    unique_diagnostics = []
    for diagnostic in diagnostics:
        if diagnostic not in unique_diagnostics:
            unique_diagnostics.append(diagnostic)

    return {
        "version": 1,
        "status": status,
        "source_issue": {
            "repo": repository,
            "number": planner_source_issue,
            "url": (
                f"https://github.com/{repository}/issues/{planner_source_issue}"
                if isinstance(repository, str)
                and repository
                and isinstance(planner_source_issue, int)
                and planner_source_issue > 0
                else None
            ),
        },
        "accepted_recommendation": {
            "url": recommendation_url if recommendation_available else None,
            "comment_id": recommendation_comment_id if recommendation_available else None,
        },
        "roadmap_reference": {
            "url": roadmap_reference,
            "pr_number": roadmap_pr_number,
            "merged": roadmap_reference_merged,
        },
        "planner": {
            "issue_number": planner_source_issue,
            "result_comment_id": planner_result_comment_id,
            "outcome": planner_outcome,
            "artifact": planner_artifact,
        },
        "generated_issues": generated_issues,
        "outcome_state": outcome_state,
        "diagnostics": unique_diagnostics,
    }


def append_reviewer_feedback_note(
    item_run_root,
    review_result_path,
    review_pr_url=None,
    *,
    build_shared_context_paths_fn,
    normalize_path_for_display_fn,
    timestamp_now_fn=None,
):
    shared_context_paths = build_shared_context_paths_fn(item_run_root)
    running_notes_path = shared_context_paths["running_notes"]
    timestamp_now = timestamp_now_fn or (lambda: datetime.now().isoformat(timespec="seconds"))
    timestamp = timestamp_now()
    note_lines = [
        "",
        f"## Reviewer Follow-up ({timestamp})",
        f"- latest review result: `{normalize_path_for_display_fn(review_result_path)}`",
    ]

    if review_pr_url:
        note_lines.append(f"- review discussion: {review_pr_url}")

    note_lines.append("- status: reviewer requested implementation changes; use this artifact during follow-up development.")

    with open(running_notes_path, "a", encoding="utf-8") as running_notes_file:
        running_notes_file.write("\n".join(note_lines) + "\n")

    return running_notes_path


def append_architect_review_feedback_note(
    item_run_root,
    architect_review_result_path,
    review_pr_url=None,
    *,
    build_shared_context_paths_fn,
    normalize_path_for_display_fn,
    timestamp_now_fn=None,
):
    shared_context_paths = build_shared_context_paths_fn(item_run_root)
    running_notes_path = shared_context_paths["running_notes"]
    timestamp_now = timestamp_now_fn or (lambda: datetime.now().isoformat(timespec="seconds"))
    timestamp = timestamp_now()
    note_lines = [
        "",
        f"## Architect Review Follow-up ({timestamp})",
        f"- latest architect review result: `{normalize_path_for_display_fn(architect_review_result_path)}`",
    ]

    if review_pr_url:
        note_lines.append(f"- review discussion: {review_pr_url}")

    note_lines.append(
        "- status: architect review requested architectural corrections; use this artifact during follow-up development."
    )

    with open(running_notes_path, "a", encoding="utf-8") as running_notes_file:
        running_notes_file.write("\n".join(note_lines) + "\n")

    return running_notes_path


def build_reviewer_result_path(
    launch_brief_path,
    *,
    normalize_path_for_display_fn,
    review_result_filename=REVIEW_RESULT_FILENAME,
):
    absolute_path = os.path.abspath(os.path.join(os.path.dirname(launch_brief_path), review_result_filename))
    return normalize_path_for_display_fn(absolute_path)


def build_architect_review_result_path(
    launch_brief_path,
    *,
    normalize_path_for_display_fn,
    architect_review_result_filename=ARCHITECT_REVIEW_RESULT_FILENAME,
):
    absolute_path = os.path.abspath(os.path.join(os.path.dirname(launch_brief_path), architect_review_result_filename))
    return normalize_path_for_display_fn(absolute_path)


def build_implementation_plan_path(
    launch_brief_path,
    *,
    normalize_path_for_display_fn,
    implementation_plan_filename=IMPLEMENTATION_PLAN_FILENAME,
):
    absolute_path = os.path.abspath(os.path.join(os.path.dirname(launch_brief_path), implementation_plan_filename))
    return normalize_path_for_display_fn(absolute_path)


def initialize_run_status(
    item,
    state_label,
    config,
    launch_brief_path,
    workspace_metadata=None,
    *,
    repo,
    target_repo_path,
    normalize_path_for_display_fn,
    run_status_filename=RUN_STATUS_FILENAME,
    run_result_filename=RUN_RESULT_FILENAME,
    run_status_fields=RUN_STATUS_FIELDS,
):
    run_dir = os.path.normpath(os.path.dirname(launch_brief_path))
    status_path = os.path.join(run_dir, run_status_filename)
    result_path = os.path.join(run_dir, run_result_filename)
    normalized_run_dir = normalize_path_for_display_fn(run_dir)
    normalized_brief_path = normalize_path_for_display_fn(launch_brief_path)
    normalized_status_path = normalize_path_for_display_fn(status_path)
    normalized_result_path = normalize_path_for_display_fn(result_path)
    workspace_metadata = workspace_metadata or {}

    status_payload = {
        "repository": repo,
        "item_type": item.get("type"),
        "item_number": item.get("number"),
        "item_title": item.get("title"),
        "state_label": state_label,
        "agent": config.get("agent"),
        "mode": config.get("mode"),
        "model": config.get("model"),
        "effort": config.get("effort"),
        "target_repo_path": normalize_path_for_display_fn(target_repo_path),
        "worktree_root": workspace_metadata.get("worktree_root"),
        "worktree_root_source": workspace_metadata.get("worktree_root_source"),
        "workspace_name": workspace_metadata.get("workspace_name"),
        "workspace_path": workspace_metadata.get("workspace_path"),
        "workspace_branch": workspace_metadata.get("workspace_branch"),
        "workspace_lifecycle": workspace_metadata.get("workspace_lifecycle"),
        "lifecycle_diagnostics": None,
        "workspace_item_identity": workspace_metadata.get("workspace_item_identity"),
        "run_dir": normalized_run_dir,
        "launch_brief_path": normalized_brief_path,
        "started_at": None,
        "completed_at": None,
        "exit_code": None,
        "success": None,
        "outcome": None,
        "stop_reason": None,
        "linked_pr": item.get("review_pr", {}).get("url"),
        "working_branch": item.get("working_branch"),
        "label_transition": None,
        "artifacts": {
            "launch_brief": normalized_brief_path,
            "status": normalized_status_path,
            "result": normalized_result_path,
        },
        "recommendation_traceability": build_unavailable_recommendation_traceability_snapshot(),
    }
    status_payload["accepted_decision_traceability"] = build_accepted_decision_traceability_snapshot(
        repository=status_payload.get("repository"),
        source_issue=status_payload.get("item_number"),
        recommendation_traceability=status_payload.get("recommendation_traceability"),
        implementation_planner=status_payload.get("implementation_planner"),
    )
    status_payload["human_decision_ledger_v1"] = human_decision_ledger.normalize_human_decision_ledger(None)

    for field in run_status_fields:
        status_payload.setdefault(field, None)

    with open(status_path, "w", encoding="utf-8") as status_file:
        json.dump(status_payload, status_file, indent=2)
        status_file.write("\n")

    run_state = {
        "run_dir": run_dir,
        "status_path": status_path,
        "result_path": result_path,
        "launch_brief_path": launch_brief_path,
    }

    item["_run_state"] = run_state
    return run_state


def read_run_status(run_state, *, run_status_fields=RUN_STATUS_FIELDS, normalize_path_for_display_fn):
    status_path = run_state["status_path"]
    try:
        with open(status_path, "r", encoding="utf-8") as status_file:
            status_payload = json.load(status_file)
    except (FileNotFoundError, json.JSONDecodeError):
        status_payload = {field: None for field in run_status_fields}

    for field in run_status_fields:
        status_payload.setdefault(field, None)

    artifacts = status_payload.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
        status_payload["artifacts"] = artifacts

    artifacts.setdefault("status", normalize_path_for_display_fn(run_state["status_path"]))
    artifacts.setdefault("result", normalize_path_for_display_fn(run_state["result_path"]))
    artifacts.setdefault("launch_brief", normalize_path_for_display_fn(run_state["launch_brief_path"]))

    recommendation_traceability = status_payload.get("recommendation_traceability")
    if not isinstance(recommendation_traceability, dict):
        recommendation_traceability = build_unavailable_recommendation_traceability_snapshot()
        status_payload["recommendation_traceability"] = recommendation_traceability

    accepted_decision_traceability = status_payload.get("accepted_decision_traceability")
    if not isinstance(accepted_decision_traceability, dict):
        accepted_decision_traceability = build_accepted_decision_traceability_snapshot(
            repository=status_payload.get("repository"),
            source_issue=status_payload.get("item_number"),
            recommendation_traceability=recommendation_traceability,
            implementation_planner=status_payload.get("implementation_planner"),
        )
        status_payload["accepted_decision_traceability"] = accepted_decision_traceability

    normalized_human_decision_ledger = human_decision_ledger.normalize_human_decision_ledger(
        status_payload.get("human_decision_ledger_v1"),
        recommendation_comment_id=(status_payload.get("implementation_planner") or {}).get("recommendation_comment_id"),
        generated_issue_numbers=[
            generated_issue.get("number")
            for generated_issue in ((status_payload.get("implementation_planner") or {}).get("generated_issues") or [])
            if isinstance(generated_issue, dict)
        ],
    )
    status_payload["human_decision_ledger_v1"] = normalized_human_decision_ledger

    return status_payload


def write_run_status(run_state, status_payload):
    with open(run_state["status_path"], "w", encoding="utf-8") as status_file:
        json.dump(status_payload, status_file, indent=2)
        status_file.write("\n")


def update_run_status(item, *, get_run_state_fn, read_run_status_fn, write_run_status_fn, updates):
    run_state = get_run_state_fn(item)
    if not run_state:
        return

    status_payload = read_run_status_fn(run_state)
    for key, value in updates.items():
        if key == "artifacts" and isinstance(value, dict):
            status_payload["artifacts"].update(value)
            continue
        status_payload[key] = value

    if "workspace_lifecycle" in updates and "lifecycle_diagnostics" not in updates:
        workspace_lifecycle = status_payload.get("workspace_lifecycle")
        if isinstance(workspace_lifecycle, dict):
            status_payload["lifecycle_diagnostics"] = [workspace_lifecycle]

    status_payload["linked_pr"] = item.get("review_pr", {}).get("url") or status_payload.get("linked_pr")
    status_payload["working_branch"] = item.get("working_branch") or status_payload.get("working_branch")
    if item.get("last_label_transition") is not None:
        status_payload["label_transition"] = item.get("last_label_transition")

    status_payload["accepted_decision_traceability"] = build_accepted_decision_traceability_snapshot(
        repository=status_payload.get("repository"),
        source_issue=status_payload.get("item_number"),
        recommendation_traceability=status_payload.get("recommendation_traceability"),
        implementation_planner=status_payload.get("implementation_planner"),
    )
    status_payload["human_decision_ledger_v1"] = human_decision_ledger.normalize_human_decision_ledger(
        status_payload.get("human_decision_ledger_v1"),
        recommendation_comment_id=(status_payload.get("implementation_planner") or {}).get("recommendation_comment_id"),
        generated_issue_numbers=[
            generated_issue.get("number")
            for generated_issue in ((status_payload.get("implementation_planner") or {}).get("generated_issues") or [])
            if isinstance(generated_issue, dict)
        ],
    )

    write_run_status_fn(run_state, status_payload)


def write_run_result(item, *, get_run_state_fn, read_run_status_fn):
    run_state = get_run_state_fn(item)
    if not run_state:
        return

    status_payload = read_run_status_fn(run_state)
    artifacts = status_payload.get("artifacts") or {}
    implementation_planner = status_payload.get("implementation_planner") or {}
    workflow_classification = status_payload.get("workflow_classification") or {}
    recommendation_traceability = status_payload.get("recommendation_traceability") or {}
    accepted_decision_traceability = status_payload.get("accepted_decision_traceability") or {}
    human_decision_ledger_v1 = status_payload.get("human_decision_ledger_v1") or {}
    label_transition = status_payload.get("label_transition")
    lifecycle_diagnostics = status_payload.get("lifecycle_diagnostics")
    if not lifecycle_diagnostics:
        workspace_lifecycle = status_payload.get("workspace_lifecycle")
        if isinstance(workspace_lifecycle, dict):
            lifecycle_diagnostics = [workspace_lifecycle]

    lines = [
        "# Run Result",
        "",
        "## Summary",
        f"- outcome: `{status_payload.get('outcome')}`",
        f"- success: `{status_payload.get('success')}`",
        f"- exit code: `{status_payload.get('exit_code')}`",
        "",
        "## Assignment",
        f"- repository: `{status_payload.get('repository')}`",
        f"- item: `{status_payload.get('item_type')} #{status_payload.get('item_number')}`",
        f"- title: `{status_payload.get('item_title')}`",
        f"- state label: `{status_payload.get('state_label')}`",
        f"- agent/mode: `{status_payload.get('agent')} / {status_payload.get('mode')}`",
        f"- model/effort: `{status_payload.get('model')} / {status_payload.get('effort')}`",
        "",
        "## Execution",
        f"- started at: `{status_payload.get('started_at')}`",
        f"- completed at: `{status_payload.get('completed_at')}`",
        f"- stop reason: `{status_payload.get('stop_reason')}`",
        f"- target repo path: `{status_payload.get('target_repo_path')}`",
        f"- worktree root: `{status_payload.get('worktree_root')}`",
        f"- worktree root source: `{status_payload.get('worktree_root_source')}`",
        f"- workspace name: `{status_payload.get('workspace_name')}`",
        f"- workspace path: `{status_payload.get('workspace_path')}`",
        f"- workspace branch: `{status_payload.get('workspace_branch')}`",
        f"- workspace lifecycle: `{status_payload.get('workspace_lifecycle')}`",
        f"- workspace item identity: `{status_payload.get('workspace_item_identity')}`",
        f"- recovery decision: `{status_payload.get('recovery_decision')}`",
        f"- recovery reason: `{status_payload.get('recovery_reason')}`",
        f"- run dir: `{status_payload.get('run_dir')}`",
        "",
        "## Lifecycle Diagnostics",
    ]

    lines.extend(workspace_diagnostics.render_workspace_lifecycle_report(lifecycle_diagnostics).splitlines())
    lines.extend(
        [
            "",
            "## Recovery",
            f"- decision: `{status_payload.get('recovery_decision')}`",
            f"- reason: `{status_payload.get('recovery_reason')}`",
            f"- recommendation: `{status_payload.get('recovery_recommendation')}`",
            f"- blockers: `{'; '.join(status_payload.get('recovery_blockers')) if isinstance(status_payload.get('recovery_blockers'), list) else status_payload.get('recovery_blockers')}`",
            f"- non-destructive: `{status_payload.get('recovery_non_destructive')}`",
            f"- comment posted: `{status_payload.get('recovery_comment_posted')}`",
            f"- locked by run id: `{(status_payload.get('workspace_lifecycle') if isinstance(status_payload.get('workspace_lifecycle'), dict) else {}).get('locked_by_run_id')}`",
            f"- dependency resolution status: `{(status_payload.get('dependency_resolution') if isinstance(status_payload.get('dependency_resolution'), dict) else {}).get('status')}`",
            f"- dependency diagnostic: `{(status_payload.get('dependency_resolution') if isinstance(status_payload.get('dependency_resolution'), dict) else {}).get('diagnostic')}`",
            "",
            "## Outcome",
            f"- linked PR: `{status_payload.get('linked_pr')}`",
            f"- working branch: `{status_payload.get('working_branch')}`",
            "",
            "## Recommendation Traceability",
            f"- available: `{recommendation_traceability.get('available')}`",
            f"- recommendation URL: `{recommendation_traceability.get('recommendation_url')}`",
            f"- recommendation comment ID: `{recommendation_traceability.get('recommendation_comment_id')}`",
            f"- source issue: `{recommendation_traceability.get('source_issue')}`",
            f"- roadmap reference: `{recommendation_traceability.get('roadmap_reference')}`",
            f"- source: `{recommendation_traceability.get('source')}`",
            f"- diagnostic: `{recommendation_traceability.get('diagnostic')}`",
            "",
            "## Accepted Decision Traceability",
            f"- version: `{accepted_decision_traceability.get('version')}`",
            f"- status: `{accepted_decision_traceability.get('status')}`",
            f"- source issue repo: `{(accepted_decision_traceability.get('source_issue') or {}).get('repo')}`",
            f"- source issue number: `{(accepted_decision_traceability.get('source_issue') or {}).get('number')}`",
            f"- source issue url: `{(accepted_decision_traceability.get('source_issue') or {}).get('url')}`",
            f"- recommendation url: `{(accepted_decision_traceability.get('accepted_recommendation') or {}).get('url')}`",
            f"- recommendation comment ID: `{(accepted_decision_traceability.get('accepted_recommendation') or {}).get('comment_id')}`",
            f"- roadmap reference: `{(accepted_decision_traceability.get('roadmap_reference') or {}).get('url')}`",
            f"- planner outcome: `{(accepted_decision_traceability.get('planner') or {}).get('outcome')}`",
            f"- planner artifact: `{(accepted_decision_traceability.get('planner') or {}).get('artifact')}`",
            f"- outcome state: `{accepted_decision_traceability.get('outcome_state')}`",
            "- diagnostics:",
            "",
            "## Human Decision Ledger",
            f"- version: `{human_decision_ledger_v1.get('version')}`",
            f"- status: `{human_decision_ledger_v1.get('status')}`",
            f"- based_on_recommendation_comment_ids: `{human_decision_ledger_v1.get('based_on_recommendation_comment_ids')}`",
            f"- selected_generated_issue_numbers: `{human_decision_ledger_v1.get('selected_generated_issue_numbers')}`",
            f"- rationale_summary: `{human_decision_ledger_v1.get('rationale_summary')}`",
            "- diagnostics:",
        ]
    )

    accepted_decision_diagnostics = accepted_decision_traceability.get("diagnostics")
    if isinstance(accepted_decision_diagnostics, list) and accepted_decision_diagnostics:
        for accepted_decision_diagnostic in accepted_decision_diagnostics:
            lines.append(f"  - {accepted_decision_diagnostic}")
    else:
        lines.append("  - none")

    human_decision_ledger_diagnostics = human_decision_ledger_v1.get("diagnostics")
    if isinstance(human_decision_ledger_diagnostics, list) and human_decision_ledger_diagnostics:
        for human_decision_ledger_diagnostic in human_decision_ledger_diagnostics:
            lines.append(f"  - {human_decision_ledger_diagnostic}")
    else:
        lines.append("  - none")

    lines.extend(
        [
            "",
            "## Implementation Planner",
            f"- outcome: `{implementation_planner.get('outcome')}`",
            f"- outcome valid: `{implementation_planner.get('outcome_valid')}`",
            f"- diagnostic: `{implementation_planner.get('diagnostic')}`",
            f"- implementation plan: `{implementation_planner.get('implementation_plan')}`",
            f"- recommended route: `{implementation_planner.get('recommended_route')}`",
            f"- source recommendation URL: `{implementation_planner.get('source_recommendation_url')}`",
            f"- source recommendation comment ID: `{implementation_planner.get('source_recommendation_comment_id')}`",
            f"- roadmap reference: `{implementation_planner.get('roadmap_reference')}`",
            "- generated issues:",
        ]
    )

    generated_issues = implementation_planner.get("generated_issues")
    if isinstance(generated_issues, list) and generated_issues:
        for generated_issue in generated_issues:
            issue_number = generated_issue.get("number") if isinstance(generated_issue, dict) else None
            issue_url = generated_issue.get("url") if isinstance(generated_issue, dict) else None
            if issue_number is None:
                continue
            if issue_url:
                lines.append(f"  - #{issue_number}: `{issue_url}`")
            else:
                lines.append(f"  - #{issue_number}")
    else:
        lines.append("  - none")

    lines.extend(
        [
            "",
            "## Workflow Classification",
            f"- status: `{workflow_classification.get('status')}`",
            f"- implementation_complexity: `{workflow_classification.get('implementation_complexity')}`",
            f"- safety_risk: `{workflow_classification.get('safety_risk')}`",
            f"- slice_size: `{workflow_classification.get('slice_size')}`",
            f"- architecture_uncertainty: `{workflow_classification.get('architecture_uncertainty')}`",
            f"- routing_recommendation: `{workflow_classification.get('routing_recommendation')}`",
            f"- source: `{workflow_classification.get('source')}`",
            f"- diagnostic: `{workflow_classification.get('diagnostic')}`",
        ]
    )

    lines.extend(
        [
            "",
            "## Artifacts",
        ]
    )

    for key in sorted(artifacts.keys()):
        lines.append(f"- {key}: `{artifacts.get(key)}`")

    lines.extend(["", "## Label Transition"])

    if isinstance(label_transition, dict):
        lines.append(f"- ok: `{label_transition.get('ok')}`")
        lines.append(f"- workflow: `{label_transition.get('workflow')}`")
        lines.append(f"- steps: `{label_transition.get('steps')}`")
    else:
        lines.append("- no transition recorded")

    lines.extend(["", "## Notes / Blockers"])
    if item.get("comment"):
        lines.append(f"- {item.get('comment')}")
    elif status_payload.get("stop_reason"):
        lines.append(f"- {status_payload.get('stop_reason')}")
    else:
        lines.append("- none")

    with open(run_state["result_path"], "w", encoding="utf-8") as result_file:
        result_file.write("\n".join(lines))
        result_file.write("\n")


def get_next_run_number(item_run_root):
    next_run_number = 1

    if not os.path.isdir(item_run_root):
        return next_run_number

    for entry in os.listdir(item_run_root):
        match = re.match(r"^run-(\d+)-", entry)
        if not match:
            continue

        run_number = int(match.group(1))
        if run_number >= next_run_number:
            next_run_number = run_number + 1

    return next_run_number


def get_item_run_root(item, *, launch_artifact_dir, repo, sanitize_filename_part_fn, resolve_circus_runtime_path_fn):
    repo_dir = sanitize_filename_part_fn(repo)
    item_dir = f"{sanitize_filename_part_fn(item['type'])}-{item['number']}"
    launch_artifact_root = resolve_circus_runtime_path_fn(launch_artifact_dir)
    return os.path.normpath(os.path.join(launch_artifact_root, repo_dir, item_dir))


def build_shared_context_paths(item_run_root, *, normalize_path_for_display_fn):
    shared_dir = os.path.normpath(os.path.join(item_run_root, "shared"))
    return {
        "architecture_handoff": normalize_path_for_display_fn(os.path.join(shared_dir, "architecture-handoff.md")),
        "running_notes": normalize_path_for_display_fn(os.path.join(shared_dir, "running-notes.md")),
        "decision_log": normalize_path_for_display_fn(os.path.join(shared_dir, "decision-log.md")),
    }


def ensure_shared_artifacts(
    item_run_root,
    *,
    shared_artifact_placeholders=SHARED_ARTIFACT_PLACEHOLDERS,
    build_shared_context_paths_fn,
):
    shared_dir = os.path.normpath(os.path.join(item_run_root, "shared"))
    os.makedirs(shared_dir, exist_ok=True)

    for filename, placeholder in shared_artifact_placeholders.items():
        artifact_path = os.path.join(shared_dir, filename)
        if os.path.exists(artifact_path):
            continue

        with open(artifact_path, "x", encoding="utf-8") as artifact_file:
            artifact_file.write(f"{placeholder}\n")

    return build_shared_context_paths_fn(item_run_root)


def build_launch_brief_path(
    item,
    mode,
    *,
    get_item_run_root_fn,
    get_next_run_number_fn,
    sanitize_filename_part_fn,
    normalize_path_for_display_fn,
):
    item_run_root = get_item_run_root_fn(item)
    run_number = get_next_run_number_fn(item_run_root)
    run_dir = f"run-{run_number:03d}-{sanitize_filename_part_fn(mode)}"
    brief_path = os.path.normpath(os.path.join(item_run_root, run_dir, "launch-brief.md"))
    return normalize_path_for_display_fn(brief_path)


def build_launch_brief_markdown(
    item,
    state_label,
    config,
    role_prompt_path,
    timestamp,
    target_repo_path,
    *,
    repo,
    resolve_profile_source_fn,
    normalize_path_for_display_fn,
    get_circus_runtime_root_fn,
    shared_context_paths=None,
    review_result_path=None,
    implementation_plan_path=None,
    workspace_metadata=None,
):
    profile_source = resolve_profile_source_fn(role_prompt_path)
    normalized_target_repo_path = normalize_path_for_display_fn(target_repo_path)
    normalized_circus_runtime_root = normalize_path_for_display_fn(get_circus_runtime_root_fn())
    discovered_target_instruction_paths = target_instructions.discover_target_instruction_paths(
        target_repo_path,
        config.get("mode"),
    )
    workspace_metadata = workspace_metadata or {}
    workspace_name = workspace_metadata.get("workspace_name")
    workspace_path = workspace_metadata.get("workspace_path")
    workspace_branch = workspace_metadata.get("workspace_branch")
    workspace_lifecycle = workspace_metadata.get("workspace_lifecycle")
    workspace_item_identity = workspace_metadata.get("workspace_item_identity")
    worktree_root = workspace_metadata.get("worktree_root")
    worktree_root_source = workspace_metadata.get("worktree_root_source")

    lines = [
        "# Launch Brief",
        "",
        "## Runtime Roots",
        f"- circus repo root: `{normalized_circus_runtime_root}`",
        f"- target repo root: `{normalized_target_repo_path}`",
        f"- target worktree root: `{worktree_root or '<not available>'}`",
        "",
        "## Assignment",
        f"- repository: `{repo}`",
        f"- target repo path: `{normalized_target_repo_path}`",
        f"- item workspace name: `{workspace_name or '<not available>'}`",
        f"- item workspace path: `{workspace_path or '<not available>'}`",
        f"- workspace branch: `{workspace_branch or '<not available>'}`",
        f"- workspace lifecycle: `{workspace_lifecycle or '<not available>'}`",
        f"- workspace item identity: `{workspace_item_identity or '<not available>'}`",
        f"- worktree root source: `{worktree_root_source or '<not available>'}`",
    ]

    if item.get("working_branch"):
        lines.append(f"- working branch: `{item['working_branch']}`")

    if item.get("execution_branch"):
        lines.append(f"- execution branch: `{item['execution_branch']}`")

    lines.extend(
        [
            f"- item type: `{item['type']}`",
            f"- item number: `{item['number']}`",
            f"- title: `{item['title']}`",
            f"- workflow state: `{state_label}`",
            f"- target agent: `{config['agent']}`",
            f"- mode: `{config['mode']}`",
            f"- model: `{config['model']}`",
            f"- effort: `{config['effort']}`",
            f"- timestamp: `{timestamp}`",
            "- generated-by: `Handler`",
            "",
            "## Source of Truth",
            "- GitHub issue/PR metadata is the source of truth.",
            "- If local files, git state, or launch metadata conflict with GitHub metadata, stop and report the mismatch.",
            "",
            "## Operating Instructions",
            "- Perform only this workflow step.",
            "- Follow the referenced agent profile.",
            "- Do not auto-merge.",
            "- Do not change unrelated workflow labels.",
            "- Leave a clear GitHub comment when finished or blocked.",
            "- If required metadata or repository context is unavailable, stop and report what is missing.",
            "",
            "## Agent Profile",
            f"- profile source: `{profile_source or '<not available>'}`",
        ]
    )

    if shared_context_paths:
        lines.extend(
            [
                "",
                "## Shared Context",
                f"- architecture handoff: `{shared_context_paths['architecture_handoff']}`",
                f"- running notes: `{shared_context_paths['running_notes']}`",
                f"- decision log: `{shared_context_paths['decision_log']}`",
            ]
        )

    if discovered_target_instruction_paths:
        lines.extend(
            [
                "",
                "## Target Repository Guidance",
            ]
            + [f"- `{instruction_path}`" for instruction_path in discovered_target_instruction_paths]
        )

    if config.get("mode") == "reviewer":
        lines.extend(
            [
                "",
                "## Reviewer Result Contract",
                f"- review result artifact absolute path: `{review_result_path or '<not available>'}`",
                "- You must write `review-result.md` to this exact absolute path before exiting.",
                "- The first non-empty line must be exactly one of:",
                "  - `Outcome: APPROVED`",
                "  - `Outcome: CHANGES_REQUESTED`",
                "  - `Outcome: BLOCKED`",
                "- If you cannot write the artifact file, set the first non-empty line to `Outcome: BLOCKED` and explain why.",
            ]
        )

    if config.get("mode") == "architect-review":
        lines.extend(
            [
                "",
                "## Architect Review Result Contract",
                f"- architect review result artifact absolute path: `{review_result_path or '<not available>'}`",
                "- You must write `architect-review-result.md` to this exact absolute path before exiting.",
                "- The first non-empty line must be exactly one of:",
                "  - `Outcome: APPROVED`",
                "  - `Outcome: CHANGES_REQUESTED`",
                "  - `Outcome: BLOCKED`",
                "- If you cannot write the artifact file, set the first non-empty line to `Outcome: BLOCKED` and explain why.",
            ]
        )

    if config.get("mode") == "implementation-planner":
        lines.extend(
            [
                "",
                "## Implementation Planner Result Contract",
                f"- implementation plan artifact absolute path: `{implementation_plan_path or '<not available>'}`",
                "- You must write `implementation-plan.md` to this exact absolute path before exiting.",
                "- The artifact should contain the structured implementation plan described by `TheFarm/roles/implementation-planner.md`.",
                "- If blocked, write the artifact with a blocker summary and leave the required GitHub blocker comment.",
            ]
        )

    return "\n".join(lines)


def write_launch_brief(
    item,
    state_label,
    config,
    role_prompt_path,
    *,
    target_repo_path,
    build_launch_brief_markdown_fn,
    get_item_run_root_fn,
    ensure_shared_artifacts_fn,
    build_launch_brief_path_fn,
    build_reviewer_result_path_fn,
    build_architect_review_result_path_fn,
    build_implementation_plan_path_fn,
    initialize_run_status_fn,
    update_run_status_fn,
    resolve_workspace_metadata_fn,
    normalize_path_for_display_fn,
    collect_workspace_lifecycle_diagnostic_fn=None,
    timestamp_now_fn=None,
    log=print,
):
    timestamp_now = timestamp_now_fn or (lambda: datetime.now().isoformat(timespec="seconds"))
    collect_workspace_lifecycle_diagnostic_fn = (
        collect_workspace_lifecycle_diagnostic_fn or workspace_diagnostics.collect_workspace_lifecycle_diagnostic
    )
    timestamp = timestamp_now()
    item_run_root = get_item_run_root_fn(item)
    shared_context_paths = ensure_shared_artifacts_fn(item_run_root)
    workspace_metadata = resolve_workspace_metadata_fn(item)
    brief_path = build_launch_brief_path_fn(item, config["mode"])
    review_result_path = None
    implementation_plan_path = None
    if config.get("mode") == "reviewer":
        review_result_path = build_reviewer_result_path_fn(brief_path)
    if config.get("mode") == "architect-review":
        review_result_path = build_architect_review_result_path_fn(brief_path)
    if config.get("mode") == "implementation-planner":
        implementation_plan_path = build_implementation_plan_path_fn(brief_path)

    brief_content = build_launch_brief_markdown_fn(
        item,
        state_label,
        config,
        role_prompt_path,
        timestamp,
        target_repo_path or "<not configured>",
        shared_context_paths,
        review_result_path,
        implementation_plan_path,
        workspace_metadata,
    )
    os.makedirs(os.path.dirname(brief_path), exist_ok=True)

    with open(brief_path, "w", encoding="utf-8") as brief_file:
        brief_file.write(f"{brief_content}\n")

    initialize_run_status_fn(item, state_label, config, brief_path, workspace_metadata=workspace_metadata)
    artifact_updates = {
        "architecture_handoff": shared_context_paths["architecture_handoff"],
        "running_notes": shared_context_paths["running_notes"],
        "decision_log": shared_context_paths["decision_log"],
    }

    if review_result_path:
        artifact_updates["result_contract"] = normalize_path_for_display_fn(review_result_path)

    if implementation_plan_path:
        artifact_updates["implementation_plan"] = normalize_path_for_display_fn(implementation_plan_path)

    if workspace_metadata.get("workspace_path"):
        artifact_updates["workspace"] = workspace_metadata.get("workspace_path")

    lifecycle_diagnostics = None
    if workspace_metadata.get("workspace_path"):
        lifecycle_diagnostics = [
            collect_workspace_lifecycle_diagnostic_fn(
                repo_path=target_repo_path,
                workspace_path=workspace_metadata.get("workspace_path"),
                item=item,
            )
        ]

    update_run_status_fn(
        item,
        launch_brief_path=normalize_path_for_display_fn(brief_path),
        artifacts=artifact_updates,
        lifecycle_diagnostics=lifecycle_diagnostics,
    )

    log(f"[Dispatch] Shared artifact path (architecture handoff): {shared_context_paths['architecture_handoff']}")
    log(f"[Dispatch] Shared artifact path (running notes): {shared_context_paths['running_notes']}")
    log(f"[Dispatch] Shared artifact path (decision log): {shared_context_paths['decision_log']}")
    log(f"[Dispatch] Workspace root: {workspace_metadata.get('worktree_root') or '<not available>'}")
    log(f"[Dispatch] Workspace path: {workspace_metadata.get('workspace_path') or '<not available>'}")

    return brief_path