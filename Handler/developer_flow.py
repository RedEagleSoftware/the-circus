import os
import re


def build_developer_commit_message(item):
    return f"Implement issue #{item['number']}: {item.get('title', '').strip()}"


def build_developer_pr_title(item):
    return f"Issue #{item['number']}: {item.get('title', '').strip()}"


def build_developer_pr_body(
    item,
    launch_brief_path,
    *,
    repo,
    normalize_path_for_display_fn,
    get_item_run_root_fn,
    build_shared_context_paths_fn,
    path_exists_fn=os.path.exists,
):
    number = item["number"]
    issue_url = item.get("url") or f"https://github.com/{repo}/issues/{number}"
    launch_brief_display_path = normalize_path_for_display_fn(launch_brief_path)
    item_run_root = get_item_run_root_fn(item)
    shared_context_paths = build_shared_context_paths_fn(item_run_root)
    architecture_handoff_path = shared_context_paths["architecture_handoff"]

    body_lines = [
        f"Closes #{number}",
        "",
        "## Linked Issue",
        f"- {issue_url}",
        "",
        "## Summary",
        f"- Implemented changes for issue #{number} (`{item.get('title', '').strip()}`).",
        "",
        "## Validation Notes",
        "- Validation notes were not provided by the agent run.",
        "",
        "## Artifacts",
        f"- Launch brief: `{launch_brief_display_path}`",
    ]

    if path_exists_fn(architecture_handoff_path):
        body_lines.append(
            f"- Architecture handoff: `{normalize_path_for_display_fn(architecture_handoff_path)}`"
        )

    return "\n".join(body_lines)


def add_developer_pr_failure_comment(item, details, *, lock_label, add_comment_fn):
    item["comment"] = (
        f"Handler failed to prepare a pull request after successful developer execution for "
        f"{item['type']} #{item['number']} ({details}). The lock label `{lock_label}` remains in place "
        "for human inspection."
    )
    add_comment_fn(item)


def finalize_developer_success_with_pull_request(
    item,
    launch_brief_path,
    *,
    from_state_label="state:ready-for-dev",
    repo,
    target_repo_path,
    lock_label,
    run_git_command_in_repo_fn,
    get_current_git_branch_fn,
    find_existing_open_pr_for_branch_fn,
    create_pull_request_with_body_file_fn,
    advance_developer_workflow_on_success_fn,
    append_retry_shared_note_fn,
    move_workflow_to_retry_fn,
    add_comment_fn,
    normalize_path_for_display_fn,
    build_shared_context_paths_fn,
    get_item_run_root_fn,
):
    repo_path = target_repo_path
    if not repo_path:
        print("[Dispatch] Cannot finalize developer success: CIRCUS_TARGET_REPO_PATH is not configured.")
        add_developer_pr_failure_comment(
            item,
            "target repository path is not configured",
            lock_label=lock_label,
            add_comment_fn=add_comment_fn,
        )
        return False

    developer_branch = item.get("working_branch") or get_current_git_branch_fn(repo_path)
    if not developer_branch:
        print("[Dispatch] Cannot determine developer branch after successful run.")
        add_developer_pr_failure_comment(
            item,
            "unable to determine developer branch",
            lock_label=lock_label,
            add_comment_fn=add_comment_fn,
        )
        return False

    print(f"[Dispatch] Developer branch detected for post-run PR flow: {developer_branch}")

    status_result = run_git_command_in_repo_fn(repo_path, ["status", "--porcelain"])
    if status_result is None or status_result.returncode != 0:
        stderr = status_result.stderr.strip() if status_result and status_result.stderr else "unknown error"
        print(f"[Dispatch] Unable to collect git status for PR flow: {stderr}")
        add_developer_pr_failure_comment(
            item,
            "unable to inspect git status",
            lock_label=lock_label,
            add_comment_fn=add_comment_fn,
        )
        return False

    git_status = status_result.stdout.strip()
    print(f"[Dispatch] Git status for developer branch '{developer_branch}':")
    if git_status:
        print(git_status)
    else:
        print("[Dispatch] <clean>")

    if not git_status:
        retry_context = {
            "source_state_label": from_state_label,
            "source_run_status_path": item.get("run_status_path"),
            "source_working_branch": developer_branch,
            "source_result_artifact": item.get("result_artifact"),
            "source_agent": "junie",
            "source_mode": "developer",
            "source_exit_code": 0,
            "reason": "developer run produced no repository changes",
        }
        item_run_root = get_item_run_root_fn(item)
        append_retry_shared_note_fn(item_run_root, retry_context)
        advanced = move_workflow_to_retry_fn(item, from_state_label)
        if not advanced:
            item["comment"] = (
                f"Handler detected no changes after successful developer execution for {item['type']} "
                f"#{item['number']} on branch `{developer_branch}`. Retry transition failed and "
                f"the lock label `{lock_label}` may remain for human inspection."
            )
            add_comment_fn(item)
        print(
            "[Dispatch] No local changes detected after developer success; workflow moved to retry state."
            if advanced
            else "[Dispatch] No local changes detected after developer success; retry transition failed."
        )
        return advanced

    stage_result = run_git_command_in_repo_fn(repo_path, ["add", "-A"])
    if stage_result is None or stage_result.returncode != 0:
        stderr = stage_result.stderr.strip() if stage_result and stage_result.stderr else "unknown error"
        print(f"[Dispatch] Failed to stage developer changes: {stderr}")
        add_developer_pr_failure_comment(
            item,
            "unable to stage developer changes",
            lock_label=lock_label,
            add_comment_fn=add_comment_fn,
        )
        return False

    commit_message = build_developer_commit_message(item)
    print(f"[Dispatch] Developer commit message: {commit_message}")
    commit_result = run_git_command_in_repo_fn(repo_path, ["commit", "-m", commit_message])
    if commit_result is None or commit_result.returncode != 0:
        stderr = commit_result.stderr.strip() if commit_result and commit_result.stderr else "unknown error"
        print(f"[Dispatch] Failed to create developer commit: {stderr}")
        add_developer_pr_failure_comment(
            item,
            "unable to create commit",
            lock_label=lock_label,
            add_comment_fn=add_comment_fn,
        )
        return False

    print(f"[Dispatch] Commit created on branch '{developer_branch}'.")

    push_result = run_git_command_in_repo_fn(repo_path, ["push", "-u", "origin", developer_branch])
    if push_result is None or push_result.returncode != 0:
        stderr = push_result.stderr.strip() if push_result and push_result.stderr else "unknown error"
        print(f"[Dispatch] Failed to push developer branch '{developer_branch}': {stderr}")
        add_developer_pr_failure_comment(
            item,
            "unable to push developer branch",
            lock_label=lock_label,
            add_comment_fn=add_comment_fn,
        )
        return False

    print(f"[Dispatch] Push succeeded for branch '{developer_branch}'.")

    existing_pr = find_existing_open_pr_for_branch_fn(developer_branch)
    if not existing_pr.get("ok"):
        print(
            f"[Dispatch] Pull request lookup failed for branch '{developer_branch}': "
            f"{existing_pr.get('error', 'unknown error')}"
        )
        add_developer_pr_failure_comment(
            item,
            existing_pr.get("error", "unable to query pull requests"),
            lock_label=lock_label,
            add_comment_fn=add_comment_fn,
        )
        return False

    existing_pr_url = existing_pr.get("url")
    if existing_pr_url:
        print(f"[Dispatch] Existing pull request found for branch '{developer_branch}': {existing_pr_url}")
        transition_ok = advance_developer_workflow_on_success_fn(item, from_state_label=from_state_label)
        print(f"[Dispatch] Label transition result after confirming existing PR: {transition_ok}")
        return transition_ok

    pr_title = build_developer_pr_title(item)
    pr_body = build_developer_pr_body(
        item,
        launch_brief_path,
        repo=repo,
        normalize_path_for_display_fn=normalize_path_for_display_fn,
        get_item_run_root_fn=get_item_run_root_fn,
        build_shared_context_paths_fn=build_shared_context_paths_fn,
    )
    print(f"[Dispatch] Creating pull request with title: {pr_title}")
    create_result = create_pull_request_with_body_file_fn(developer_branch, pr_title, pr_body)
    if create_result is None:
        print(f"[Dispatch] Failed to create pull request for branch '{developer_branch}'.")
        add_developer_pr_failure_comment(
            item,
            "unable to create pull request",
            lock_label=lock_label,
            add_comment_fn=add_comment_fn,
        )
        return False

    pr_url_match = re.search(r"https?://\S+", create_result)
    pr_url = pr_url_match.group(0) if pr_url_match else create_result.strip()
    print(f"[Dispatch] Pull request ready for branch '{developer_branch}': {pr_url}")

    transition_ok = advance_developer_workflow_on_success_fn(item, from_state_label=from_state_label)
    print(f"[Dispatch] Label transition result after PR creation: {transition_ok}")
    return transition_ok