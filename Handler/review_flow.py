import os


def build_reviewer_environment(
    *,
    review_pr_url,
    review_pr_number,
    issue_number,
    absolute_launch_brief_path,
    architecture_handoff_path,
    target_repo_path,
    review_result_path,
):
    reviewer_env = os.environ.copy()
    reviewer_env["CIRCUS_REVIEW_PR_URL"] = str(review_pr_url)
    reviewer_env["CIRCUS_REVIEW_PR_NUMBER"] = str(review_pr_number or "")
    reviewer_env["CIRCUS_REVIEW_ISSUE_NUMBER"] = str(issue_number)
    reviewer_env["CIRCUS_REVIEW_LAUNCH_BRIEF"] = absolute_launch_brief_path
    reviewer_env["CIRCUS_REVIEW_ARCHITECTURE_HANDOFF"] = architecture_handoff_path
    reviewer_env["CIRCUS_REVIEW_TARGET_REPO_PATH"] = target_repo_path or ""
    reviewer_env["CIRCUS_REVIEW_RESULT_PATH"] = review_result_path
    return reviewer_env


def build_architect_review_environment(
    *,
    review_pr_url,
    review_pr_number,
    issue_number,
    absolute_launch_brief_path,
    architecture_handoff_path,
    running_notes_path,
    decision_log_path,
    review_result_path,
    architect_review_result_path,
    target_repo_path,
):
    architect_review_env = os.environ.copy()
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_PR_URL"] = str(review_pr_url)
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_PR_NUMBER"] = str(review_pr_number or "")
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_ISSUE_NUMBER"] = str(issue_number)
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_LAUNCH_BRIEF"] = absolute_launch_brief_path
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_ARCHITECTURE_HANDOFF"] = architecture_handoff_path
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_RUNNING_NOTES"] = running_notes_path
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_DECISION_LOG"] = decision_log_path
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_REVIEW_RESULT_PATH"] = review_result_path
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_RESULT_PATH"] = architect_review_result_path
    architect_review_env["CIRCUS_ARCHITECT_REVIEW_TARGET_REPO_PATH"] = target_repo_path or ""
    return architect_review_env


def handle_reviewer_result(
    *,
    item,
    issue_number,
    result_returncode,
    item_run_root,
    review_pr_url,
    review_result_path,
    lock_label,
    add_comment_fn,
    update_run_status_fn,
    write_run_result_fn,
    parse_review_result_outcome_fn,
    normalize_path_for_display_fn,
    append_reviewer_feedback_note_fn,
    append_retry_shared_note_fn,
    advance_reviewer_workflow_on_approved_fn,
    advance_reviewer_workflow_on_changes_requested_fn,
    move_workflow_to_retry_fn,
    source_state_label,
    utc_timestamp_now_fn,
    path_exists_fn=os.path.exists,
    log=print,
):
    if not path_exists_fn(review_result_path):
        log(
            "[Dispatch] Review result handling: expected review-result artifact is missing; "
            f"expected path={review_result_path}; exists=False; "
            "workflow progression stopped with no label transition and lock remains in place."
        )
        retry_context = {
            "source_state_label": source_state_label,
            "source_run_status_path": item.get("run_status_path"),
            "source_working_branch": item.get("working_branch"),
            "source_result_artifact": item.get("result_artifact"),
            "source_review_result_artifact": review_result_path,
            "source_agent": "codex",
            "source_mode": "reviewer",
            "source_exit_code": result_returncode,
            "reason": "missing reviewer result artifact",
        }
        running_notes_path = append_retry_shared_note_fn(item_run_root, retry_context)
        advanced = move_workflow_to_retry_fn(item, source_state_label)
        if not advanced:
            item["comment"] = (
                f"Codex reviewer completed for issue #{issue_number}, but expected review result artifact "
                f"`{review_result_path}` was not created. Retry transition failed, and lock label `{lock_label}` "
                "may remain in place for human inspection."
            )
            add_comment_fn(item)
        item["missing_review_result_artifact"] = True
        update_run_status_fn(
            item,
            completed_at=utc_timestamp_now_fn(),
            exit_code=result_returncode,
            success=advanced,
            outcome="missing result artifact",
            stop_reason=(
                f"missing reviewer result artifact at {normalize_path_for_display_fn(review_result_path)}"
                if advanced
                else (
                    f"missing reviewer result artifact at {normalize_path_for_display_fn(review_result_path)}; "
                    "retry transition failed"
                )
            ),
            artifacts={
                "review_result": normalize_path_for_display_fn(review_result_path),
                "running_notes": normalize_path_for_display_fn(running_notes_path),
            },
        )
        write_run_result_fn(item)
        return advanced

    review_outcome = parse_review_result_outcome_fn(review_result_path)
    update_run_status_fn(item, artifacts={"review_result": normalize_path_for_display_fn(review_result_path)})
    if review_outcome == "APPROVED":
        log("[Dispatch] Review result handling: APPROVED.")
        advanced = advance_reviewer_workflow_on_approved_fn(item)
        update_run_status_fn(
            item,
            completed_at=utc_timestamp_now_fn(),
            exit_code=result_returncode,
            success=advanced,
            outcome="reviewer approved",
            stop_reason=None if advanced else "label transition failed",
        )
        write_run_result_fn(item)
        return advanced

    if review_outcome == "CHANGES_REQUESTED":
        log("[Dispatch] Review result handling: CHANGES_REQUESTED.")
        running_notes_path = append_reviewer_feedback_note_fn(item_run_root, review_result_path, review_pr_url)
        log(f"[Dispatch] Reviewer feedback context appended to running notes: {running_notes_path}")
        advanced = advance_reviewer_workflow_on_changes_requested_fn(item)
        update_run_status_fn(
            item,
            completed_at=utc_timestamp_now_fn(),
            exit_code=result_returncode,
            success=advanced,
            outcome="reviewer changes requested",
            stop_reason=None if advanced else "label transition failed",
            artifacts={"running_notes": normalize_path_for_display_fn(running_notes_path)},
        )
        write_run_result_fn(item)
        return advanced

    if review_outcome == "BLOCKED":
        log(
            "[Dispatch] Review result handling: BLOCKED (no automatic label transition); "
            "human inspection required and lock remains in place."
        )
        item["comment"] = (
            f"Codex reviewer reported `BLOCKED` for issue #{issue_number}. "
            f"Workflow labels were not transitioned automatically; the lock label `{lock_label}` remains in place "
            "for human inspection."
        )
        add_comment_fn(item)
        update_run_status_fn(
            item,
            completed_at=utc_timestamp_now_fn(),
            exit_code=result_returncode,
            success=True,
            outcome="blocked",
            stop_reason="reviewer reported BLOCKED",
        )
        write_run_result_fn(item)
        return True

    log(
        "[Dispatch] Review result handling: no unambiguous review outcome marker found; "
        "labels were not transitioned automatically."
    )
    retry_context = {
        "source_state_label": source_state_label,
        "source_run_status_path": item.get("run_status_path"),
        "source_working_branch": item.get("working_branch"),
        "source_result_artifact": item.get("result_artifact"),
        "source_review_result_artifact": review_result_path,
        "source_agent": "codex",
        "source_mode": "reviewer",
        "source_exit_code": result_returncode,
        "reason": "reviewer outcome ambiguous",
    }
    running_notes_path = append_retry_shared_note_fn(item_run_root, retry_context)
    advanced = move_workflow_to_retry_fn(item, source_state_label)
    if not advanced:
        item["comment"] = (
            f"Codex reviewer completed for issue #{issue_number}, but no unambiguous review outcome marker "
            f"(`APPROVED`, `CHANGES_REQUESTED`, or `BLOCKED`) was found in `{review_result_path}`. "
            "Retry transition failed and human review of reviewer output is required."
        )
        add_comment_fn(item)
    update_run_status_fn(
        item,
        completed_at=utc_timestamp_now_fn(),
        exit_code=result_returncode,
        success=advanced,
        outcome="reviewer outcome ambiguous",
        stop_reason=(
            "no unambiguous review outcome marker found"
            if advanced
            else "no unambiguous review outcome marker found; retry transition failed"
        ),
        artifacts={"running_notes": normalize_path_for_display_fn(running_notes_path)},
    )
    write_run_result_fn(item)
    return advanced


def handle_architect_review_result(
    *,
    item,
    issue_number,
    result_returncode,
    item_run_root,
    review_pr_url,
    architect_review_result_path,
    lock_label,
    add_comment_fn,
    update_run_status_fn,
    write_run_result_fn,
    parse_architect_review_result_outcome_fn,
    normalize_path_for_display_fn,
    append_architect_review_feedback_note_fn,
    append_retry_shared_note_fn,
    advance_architect_review_workflow_on_approved_fn,
    advance_architect_review_workflow_on_changes_requested_fn,
    move_workflow_to_retry_fn,
    source_state_label,
    utc_timestamp_now_fn,
    path_exists_fn=os.path.exists,
    log=print,
):
    if not path_exists_fn(architect_review_result_path):
        log(
            "[Dispatch] Architect review result handling: expected architect-review-result artifact is missing; "
            f"expected path={architect_review_result_path}; exists=False; "
            "workflow progression stopped with no label transition and lock remains in place."
        )
        retry_context = {
            "source_state_label": source_state_label,
            "source_run_status_path": item.get("run_status_path"),
            "source_working_branch": item.get("working_branch"),
            "source_result_artifact": item.get("result_artifact"),
            "source_architect_review_result_artifact": architect_review_result_path,
            "source_agent": "codex",
            "source_mode": "architect-review",
            "source_exit_code": result_returncode,
            "reason": "missing architect review result artifact",
        }
        running_notes_path = append_retry_shared_note_fn(item_run_root, retry_context)
        advanced = move_workflow_to_retry_fn(item, source_state_label)
        if not advanced:
            item["comment"] = (
                f"Codex architect review completed for issue #{issue_number}, but expected architect review result "
                f"artifact `{architect_review_result_path}` was not created. Retry transition failed, and lock label "
                f"`{lock_label}` may remain in place for human inspection."
            )
            add_comment_fn(item)
        item["missing_review_result_artifact"] = True
        update_run_status_fn(
            item,
            completed_at=utc_timestamp_now_fn(),
            exit_code=result_returncode,
            success=advanced,
            outcome="missing result artifact",
            stop_reason=(
                "missing architect review result artifact at "
                f"{normalize_path_for_display_fn(architect_review_result_path)}"
                if advanced
                else (
                    "missing architect review result artifact at "
                    f"{normalize_path_for_display_fn(architect_review_result_path)}; retry transition failed"
                )
            ),
            artifacts={
                "architect_review_result": normalize_path_for_display_fn(architect_review_result_path),
                "running_notes": normalize_path_for_display_fn(running_notes_path),
            },
        )
        write_run_result_fn(item)
        return advanced

    review_outcome = parse_architect_review_result_outcome_fn(architect_review_result_path)
    update_run_status_fn(
        item,
        artifacts={"architect_review_result": normalize_path_for_display_fn(architect_review_result_path)},
    )
    log(f"[Dispatch] Architect review outcome: {review_outcome or 'NO_UNAMBIGUOUS_OUTCOME'}.")
    if review_outcome == "APPROVED":
        log("[Dispatch] Architect review passed; implementation is ready for human review.")
        advanced = advance_architect_review_workflow_on_approved_fn(item)
        update_run_status_fn(
            item,
            completed_at=utc_timestamp_now_fn(),
            exit_code=result_returncode,
            success=advanced,
            outcome="architect review approved",
            stop_reason=None if advanced else "label transition failed",
        )
        write_run_result_fn(item)
        return advanced

    if review_outcome == "CHANGES_REQUESTED":
        log("[Dispatch] Architect review result handling: CHANGES_REQUESTED.")
        running_notes_feedback_path = append_architect_review_feedback_note_fn(
            item_run_root,
            architect_review_result_path,
            review_pr_url,
        )
        log(f"[Dispatch] Architect review feedback context appended to running notes: {running_notes_feedback_path}")
        advanced = advance_architect_review_workflow_on_changes_requested_fn(item)
        update_run_status_fn(
            item,
            completed_at=utc_timestamp_now_fn(),
            exit_code=result_returncode,
            success=advanced,
            outcome="reviewer changes requested",
            stop_reason=None if advanced else "label transition failed",
            artifacts={"running_notes": normalize_path_for_display_fn(running_notes_feedback_path)},
        )
        write_run_result_fn(item)
        return advanced

    if review_outcome == "BLOCKED":
        log(
            "[Dispatch] Architect review result handling: BLOCKED (no automatic label transition); "
            "human inspection required and lock remains in place."
        )
        item["comment"] = (
            f"Codex architect review reported `BLOCKED` for issue #{issue_number}. "
            f"Workflow labels were not transitioned automatically; the lock label `{lock_label}` remains in place "
            "for human inspection."
        )
        add_comment_fn(item)
        update_run_status_fn(
            item,
            completed_at=utc_timestamp_now_fn(),
            exit_code=result_returncode,
            success=True,
            outcome="blocked",
            stop_reason="architect reviewer reported BLOCKED",
        )
        write_run_result_fn(item)
        return True

    log(
        "[Dispatch] Architect review result handling: no unambiguous review outcome marker found; "
        "labels were not transitioned automatically."
    )
    retry_context = {
        "source_state_label": source_state_label,
        "source_run_status_path": item.get("run_status_path"),
        "source_working_branch": item.get("working_branch"),
        "source_result_artifact": item.get("result_artifact"),
        "source_architect_review_result_artifact": architect_review_result_path,
        "source_agent": "codex",
        "source_mode": "architect-review",
        "source_exit_code": result_returncode,
        "reason": "architect review outcome ambiguous",
    }
    running_notes_path = append_retry_shared_note_fn(item_run_root, retry_context)
    advanced = move_workflow_to_retry_fn(item, source_state_label)
    if not advanced:
        item["comment"] = (
            f"Codex architect review completed for issue #{issue_number}, but no unambiguous review outcome marker "
            f"(`APPROVED`, `CHANGES_REQUESTED`, or `BLOCKED`) was found in `{architect_review_result_path}`. "
            "Retry transition failed and human review of architect review output is required."
        )
        add_comment_fn(item)
    update_run_status_fn(
        item,
        completed_at=utc_timestamp_now_fn(),
        exit_code=result_returncode,
        success=advanced,
        outcome="reviewer outcome ambiguous",
        stop_reason=(
            "no unambiguous architect review outcome marker found"
            if advanced
            else "no unambiguous architect review outcome marker found; retry transition failed"
        ),
        artifacts={"running_notes": normalize_path_for_display_fn(running_notes_path)},
    )
    write_run_result_fn(item)
    return advanced