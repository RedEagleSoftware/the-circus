import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, UTC
from dotenv import load_dotenv

from Handler import agents
from Handler import config as handler_config
from Handler import developer_flow
from Handler import git_workspace
from Handler import github_client
from Handler import paths as handler_paths
from Handler import review_flow
from Handler import target_instructions
from Handler import watchtower
from Handler import workflow
from Handler.workflow_states import (
    IMPLEMENTATION_PLANNING_CHANGES_REQUESTED_LABEL,
    IMPLEMENTATION_PLANNING_LABEL,
    ROADMAP_UPDATE_LABEL,
    SYSTEMS_ARCHITECTURE_CHANGES_REQUESTED_LABEL,
    SYSTEMS_ARCHITECTURE_LABEL,
)

load_dotenv(override=True)
# Configuration
REPO = os.getenv("CIRCUS_REPO")  # Format: owner/repo
TARGET_REPO_PATH = os.getenv("CIRCUS_TARGET_REPO_PATH")
POLL_INTERVAL = int(os.getenv("CIRCUS_POLL_INTERVAL", 60))  # seconds
DEFAULT_MAX_STEPS_PER_RUN = handler_config.DEFAULT_MAX_STEPS_PER_RUN
MAX_STEPS_PER_RUN_ENV = handler_config.MAX_STEPS_PER_RUN_ENV
MAX_BRANCH_SLUG_LENGTH = 60

# Label to Agent Mapping
LABEL_MAP = workflow.LABEL_MAP

LOCK_LABEL = workflow.LOCK_LABEL
LAUNCH_ARTIFACT_DIR = os.path.join("Watchtower", "runs")
SHARED_ARTIFACT_PLACEHOLDERS = watchtower.SHARED_ARTIFACT_PLACEHOLDERS

REVIEW_RESULT_FILENAME = watchtower.REVIEW_RESULT_FILENAME
ARCHITECT_REVIEW_RESULT_FILENAME = watchtower.ARCHITECT_REVIEW_RESULT_FILENAME
REVIEW_OUTCOMES = workflow.REVIEW_OUTCOMES
REVIEW_OUTCOME_MARKERS = workflow.REVIEW_OUTCOME_MARKERS

AGENT_EXECUTABLE_ENV_OVERRIDES = {
    "junie": "CIRCUS_JUNIE_EXECUTABLE",
    "codex": "CIRCUS_CODEX_EXECUTABLE",
}

EXECUTABLE_PATHS = {}

RUN_STATUS_FILENAME = watchtower.RUN_STATUS_FILENAME
RUN_RESULT_FILENAME = watchtower.RUN_RESULT_FILENAME

RUN_STATUS_FIELDS = watchtower.RUN_STATUS_FIELDS


def utc_timestamp_now():
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_circus_runtime_root():
    return handler_paths.get_circus_runtime_root(__file__, env_getter=os.getenv)


def resolve_circus_runtime_path(path):
    if path is None:
        return None

    return handler_paths.resolve_circus_runtime_path(path, get_runtime_root=get_circus_runtime_root)


def run_command(cmd):
    return github_client.run_command(cmd, repo=REPO, run_subprocess=subprocess.run, log=print)


def add_comment(item):
    github_client.add_comment(item, repo=REPO, run_command_fn=run_command)


def verify_github_repo_access():
    return github_client.verify_github_repo_access(repo=REPO, run_command_fn=run_command, log=print)


def get_required_executables():
    required = [("gh", None), ("git", None)]
    configured_agents = {config.get("agent") for config in LABEL_MAP.values() if config.get("agent")}

    for agent in sorted(configured_agents):
        env_override = AGENT_EXECUTABLE_ENV_OVERRIDES.get(agent)
        required.append((agent, env_override))

    return required


def resolve_executable_path(executable_name, env_override_name=None):
    override_candidate = None
    if env_override_name:
        configured_override = os.getenv(env_override_name)
        if configured_override:
            override_candidate = configured_override.strip()

    if override_candidate:
        resolved_override = shutil.which(override_candidate)
        if resolved_override:
            return resolved_override, ".env"
        return None, "missing-.env"

    resolved_default = shutil.which(executable_name)
    if resolved_default:
        return resolved_default, "path"

    return None, "missing-path"


def validate_required_executables():
    report_python_environment_versions()
    print("[Startup] Validating required executables...")

    resolved_paths = {}
    missing_messages = []

    for executable_name, env_override_name in get_required_executables():
        resolved_path, resolution_source = resolve_executable_path(executable_name, env_override_name)

        if resolved_path:
            if resolution_source == ".env":
                print(
                    f"[Startup] Found executable '{executable_name}' via {env_override_name}: {resolved_path}"
                )
            else:
                print(f"[Startup] Found executable '{executable_name}' at: {resolved_path}")

            resolved_paths[executable_name] = resolved_path
            continue

        if resolution_source == "missing-.env":
            missing_messages.append(
                f"[Startup] Error: {env_override_name} is set, but executable '{executable_name}' was not found "
                f"for value '{os.getenv(env_override_name)}'."
            )
        else:
            missing_messages.append(
                f"[Startup] Error: missing required executable '{executable_name}'. "
                "Install it or add it to PATH."
            )

    if missing_messages:
        for message in missing_messages:
            print(message)

        print("[Startup] Startup aborted: required command-line tools are unavailable.")
        return None

    return resolved_paths


def report_python_environment_versions():
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"[Startup] Python version: {python_version}")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        print(f"[Startup] Warning: Unable to determine pip version: {error}")
        return

    if result.returncode != 0:
        failure_reason = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        print(f"[Startup] Warning: Unable to determine pip version: {failure_reason}")
        return

    pip_output = result.stdout.strip()
    if not pip_output:
        print("[Startup] Warning: Unable to determine pip version: pip returned empty output.")
        return

    first_line = pip_output.splitlines()[0].strip()
    if not first_line:
        print("[Startup] Warning: Unable to determine pip version: pip output was blank.")
        return

    pip_tokens = first_line.split()
    if len(pip_tokens) >= 2 and pip_tokens[0].lower() == "pip":
        print(f"[Startup] Pip version: {pip_tokens[1]}")
        return

    print(f"[Startup] Pip version: {first_line}")


def get_candidates(item_type, list_cmd):
    return github_client.get_candidates(item_type, list_cmd, repo=REPO, run_command_fn=run_command)


def get_current_item(item):
    return github_client.get_item(item["type"], item["number"], repo=REPO, run_command_fn=run_command)


def get_labeled_items():
    issues, issues_ok = get_candidates("issue", "issue list")
    prs, prs_ok = get_candidates("pr", "pr list")

    all_items = []
    all_items.extend(issues)
    all_items.extend(prs)

    candidates = []
    for item in all_items:
        labels = [label["name"] for label in item["labels"]]
        primary_states = get_primary_state_labels(labels)

        if primary_states:
            candidates.append(item)
            continue

        state_labels = get_state_labels(labels)
        if state_labels:
            print(
                f"[Poll] {item['type']} #{item['number']} has unsupported state label(s): {repr(state_labels)}"
            )

    return issues, prs, candidates, issues_ok and prs_ok


def get_primary_state_labels(labels):
    return workflow.get_primary_state_labels(labels)


def get_state_labels(labels):
    return workflow.get_state_labels(labels)


def is_locked(labels):
    return workflow.is_locked(labels)


def lock_item(item):
    return github_client.lock_item(item, repo=REPO, lock_label=LOCK_LABEL, run_command_fn=run_command)


def unlock_item(item):
    return github_client.unlock_item(item, repo=REPO, lock_label=LOCK_LABEL, run_command_fn=run_command)


def remove_label(item, label):
    return github_client.remove_label(item, label, repo=REPO, run_command_fn=run_command)


def add_label(item, label):
    return github_client.add_label(item, label, repo=REPO, run_command_fn=run_command)


def execute_label_transition(item, workflow_name, transition_steps, success_message, failure_message):
    return workflow.execute_label_transition(
        item,
        workflow_name,
        transition_steps,
        success_message,
        failure_message,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
    )


def advance_architect_workflow_on_success(item):
    return workflow.advance_architect_workflow_on_success(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
    )


def advance_systems_architect_workflow_on_success(item, from_state_label=SYSTEMS_ARCHITECTURE_LABEL):
    return workflow.advance_systems_architect_workflow_on_success(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
        from_state_label=from_state_label,
    )


def build_roadmap_updater_pr_title(item):
    return f"Issue #20: Add Roadmap Updater workflow for approved strategic recommendations" if item.get("number") == 20 else build_developer_pr_title(item)


def validate_roadmap_updater_open_pull_request(item):
    working_branch = item.get("working_branch")
    if not working_branch:
        item["comment"] = (
            f"Roadmap Updater completed for {item['type']} #{item['number']} but Handler could not validate an open "
            "pull request because no working branch was recorded before launch. "
            f"The lock label `{LOCK_LABEL}` remains in place for human inspection."
        )
        add_comment(item)
        return False

    existing_pr = find_existing_open_pr_for_branch(working_branch)
    if not existing_pr.get("ok"):
        error = existing_pr.get("error", "unable to query open pull requests")
        item["comment"] = (
            f"Roadmap Updater completed for {item['type']} #{item['number']} but Handler could not validate an open "
            f"pull request for branch `{working_branch}` ({error}). "
            f"The lock label `{LOCK_LABEL}` remains in place for human inspection."
        )
        add_comment(item)
        return False

    pr_url = existing_pr.get("url")
    if not pr_url:
        item["comment"] = (
            f"Roadmap Updater completed for {item['type']} #{item['number']} but no open pull request was found for "
            f"branch `{working_branch}`. The lock label `{LOCK_LABEL}` remains in place for human inspection."
        )
        add_comment(item)
        return False

    item["roadmap_pr"] = pr_url
    return True


def advance_roadmap_update_workflow_on_success(item, from_state_label=ROADMAP_UPDATE_LABEL):
    return workflow.advance_roadmap_update_workflow_on_success(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
        from_state_label=from_state_label,
    )


def advance_implementation_planning_workflow_on_success(item, from_state_label=IMPLEMENTATION_PLANNING_LABEL):
    return workflow.advance_implementation_planning_workflow_on_success(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
        from_state_label=from_state_label,
    )


def advance_developer_workflow_on_success(item, from_state_label="state:ready-for-dev"):
    return workflow.advance_developer_workflow_on_success(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
        from_state_label=from_state_label,
    )


def advance_reviewer_workflow_on_approved(item):
    return workflow.advance_reviewer_workflow_on_approved(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
    )


def advance_reviewer_workflow_on_changes_requested(item):
    return workflow.advance_reviewer_workflow_on_changes_requested(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
    )


def advance_architect_review_workflow_on_approved(item):
    return workflow.advance_architect_review_workflow_on_approved(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
    )


def advance_architect_review_workflow_on_changes_requested(item):
    return workflow.advance_architect_review_workflow_on_changes_requested(
        item,
        remove_label_fn=remove_label,
        add_label_fn=add_label,
        update_run_status_fn=update_run_status,
        log=print,
    )


def append_reviewer_feedback_note(item_run_root, review_result_path, review_pr_url=None):
    return watchtower.append_reviewer_feedback_note(
        item_run_root,
        review_result_path,
        review_pr_url=review_pr_url,
        build_shared_context_paths_fn=build_shared_context_paths,
        normalize_path_for_display_fn=normalize_path_for_display,
        timestamp_now_fn=lambda: datetime.now().isoformat(timespec="seconds"),
    )


def append_architect_review_feedback_note(item_run_root, architect_review_result_path, review_pr_url=None):
    return watchtower.append_architect_review_feedback_note(
        item_run_root,
        architect_review_result_path,
        review_pr_url=review_pr_url,
        build_shared_context_paths_fn=build_shared_context_paths,
        normalize_path_for_display_fn=normalize_path_for_display,
        timestamp_now_fn=lambda: datetime.now().isoformat(timespec="seconds"),
    )


def build_developer_commit_message(item):
    return developer_flow.build_developer_commit_message(item)


def build_developer_pr_title(item):
    return developer_flow.build_developer_pr_title(item)


def build_developer_pr_body(item, launch_brief_path):
    return developer_flow.build_developer_pr_body(
        item,
        launch_brief_path,
        repo=REPO,
        normalize_path_for_display_fn=normalize_path_for_display,
        get_item_run_root_fn=get_item_run_root,
        build_shared_context_paths_fn=build_shared_context_paths,
    )


def find_existing_open_pr_for_branch(branch_name):
    return github_client.find_existing_open_pr_for_branch(branch_name, repo=REPO, run_command_fn=run_command)


def find_open_review_pr_for_issue(issue_number):
    return github_client.find_open_review_pr_for_issue(issue_number, repo=REPO, run_command_fn=run_command)


def add_developer_pr_failure_comment(item, details):
    developer_flow.add_developer_pr_failure_comment(
        item,
        details,
        lock_label=LOCK_LABEL,
        add_comment_fn=add_comment,
    )


def create_pull_request_with_body_file(branch_name, pr_title, pr_body):
    return github_client.create_pull_request_with_body_file(
        branch_name,
        pr_title,
        pr_body,
        repo=REPO,
        run_command_fn=run_command,
        log=print,
    )


def finalize_developer_success_with_pull_request(item, launch_brief_path, from_state_label="state:ready-for-dev"):
    return developer_flow.finalize_developer_success_with_pull_request(
        item,
        launch_brief_path,
        from_state_label=from_state_label,
        repo=REPO,
        target_repo_path=TARGET_REPO_PATH,
        lock_label=LOCK_LABEL,
        run_git_command_in_repo_fn=run_git_command_in_repo,
        get_current_git_branch_fn=get_current_git_branch,
        find_existing_open_pr_for_branch_fn=find_existing_open_pr_for_branch,
        create_pull_request_with_body_file_fn=create_pull_request_with_body_file,
        advance_developer_workflow_on_success_fn=advance_developer_workflow_on_success,
        add_comment_fn=add_comment,
        normalize_path_for_display_fn=normalize_path_for_display,
        build_shared_context_paths_fn=build_shared_context_paths,
        get_item_run_root_fn=get_item_run_root,
    )


def get_max_steps_per_run():
    return handler_config.get_max_steps_per_run(
        max_steps_env=MAX_STEPS_PER_RUN_ENV,
        default_max_steps=DEFAULT_MAX_STEPS_PER_RUN,
        env_getter=os.getenv,
        log=print,
    )


def add_prelaunch_setup_failure_comment(item, error, lock_released):
    lock_result = "released" if lock_released else "could not be released"
    item["comment"] = (
        "Handler failed before launch brief generation completed "
        f"({error}). The lock label `{LOCK_LABEL}` was {lock_result}."
    )


def revalidate_candidate_after_lock(item, expected_state_label):
    current_item, current_item_ok = get_current_item(item)
    if not current_item_ok or not current_item:
        print(
            f"[Dispatch] Failed to re-fetch {item['type']} #{item['number']} after lock acquisition; "
            "stopping pre-launch dispatch."
        )
        print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} after revalidation fetch failure...")
        lock_released = unlock_item(item)
        if lock_released:
            print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
        else:
            print(f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; manual cleanup may be required.")

        lock_result = "released" if lock_released else "could not be released"
        item["comment"] = (
            f"Handler could not re-fetch {item['type']} #{item['number']} after acquiring `{LOCK_LABEL}`. "
            f"The lock label `{LOCK_LABEL}` was {lock_result}. Dispatch was stopped before launch."
        )
        add_comment(item)
        return None, "prelaunch-failed"

    current_labels = [label["name"] for label in current_item.get("labels", [])]
    current_primary_states = get_primary_state_labels(current_labels)
    still_matches = len(current_primary_states) == 1 and current_primary_states[0] == expected_state_label
    if still_matches:
        item.update(current_item)
        return item, None

    print(
        f"[Dispatch] Candidate {item['type']} #{item['number']} changed state after lock acquisition; "
        f"expected `{expected_state_label}`, now {repr(current_primary_states)}."
    )
    print(f"[Dispatch] Releasing lock for stale candidate {item['type']} #{item['number']}...")
    lock_released = unlock_item(item)
    if lock_released:
        print(f"[Dispatch] Lock cleanup succeeded for stale candidate {item['type']} #{item['number']}.")
    else:
        print(
            f"[Dispatch] Lock cleanup failed for stale candidate {item['type']} #{item['number']}; "
            "manual cleanup may be required."
        )

    if lock_released:
        return None, "stale-candidate"

    item["comment"] = (
        f"Handler detected stale dispatch state for {item['type']} #{item['number']}, but lock cleanup failed for "
        f"`{LOCK_LABEL}`. Please remove the lock label manually before re-dispatching."
    )
    add_comment(item)
    return None, "prelaunch-failed"


def resolve_dispatch_config(item, labels):
    return workflow.resolve_dispatch_config(item, labels)


def build_junie_command(model, effort, project_path, task_text):
    return agents.build_junie_command(
        model,
        effort,
        project_path,
        task_text,
        executable_paths=EXECUTABLE_PATHS,
    )


def build_junie_task_text(absolute_launch_brief_path):
    return agents.build_junie_task_text(absolute_launch_brief_path)


def build_codex_architect_task_text(absolute_launch_brief_path):
    return agents.build_codex_architect_task_text(absolute_launch_brief_path)


def build_codex_systems_architect_task_text(absolute_launch_brief_path):
    return agents.build_codex_systems_architect_task_text(absolute_launch_brief_path)


def build_codex_roadmap_updater_task_text(absolute_launch_brief_path):
    return agents.build_codex_roadmap_updater_task_text(absolute_launch_brief_path)


def build_codex_implementation_planner_task_text(absolute_launch_brief_path):
    return agents.build_codex_implementation_planner_task_text(absolute_launch_brief_path)


def build_codex_reviewer_task_text(absolute_launch_brief_path, review_pr_url, review_result_path):
    return agents.build_codex_reviewer_task_text(
        absolute_launch_brief_path,
        review_pr_url,
        review_result_path,
    )


def build_codex_architect_review_task_text(absolute_launch_brief_path, review_pr_url, architect_review_result_path):
    return agents.build_codex_architect_review_task_text(
        absolute_launch_brief_path,
        review_pr_url,
        architect_review_result_path,
    )


def resolve_role_prompt_path(mode):
    candidates = [os.path.join("TheFarm", "roles", f"{mode}.md")]
    if mode.endswith("-approval"):
        base_mode = mode[: -len("-approval")]
        candidates.append(os.path.join("TheFarm", "roles", f"{base_mode}.md"))
    if mode.endswith("-review"):
        base_mode = mode[: -len("-review")]
        candidates.append(os.path.join("TheFarm", "roles", f"{base_mode}.md"))

    for path in candidates:
        runtime_resolved_path = resolve_circus_runtime_path(path)
        if os.path.isfile(runtime_resolved_path):
            return runtime_resolved_path

    return None


def resolve_profile_source(role_prompt_path):
    if not role_prompt_path:
        return None

    return normalize_path_for_display(resolve_circus_runtime_path(role_prompt_path))


def build_thin_prompt(item, state_label, mode, role_prompt_path, launch_brief_path=None, review_result_path=None):
    profile_source = resolve_profile_source(role_prompt_path)
    discovered_target_instruction_paths = target_instructions.discover_target_instruction_paths(TARGET_REPO_PATH, mode)

    prompt_lines = [
        "Agent launch context:",
        f"- selected item type: {item['type']}",
        f"- issue/PR number: {item['number']}",
        f"- title: {item['title']}",
    ]

    if item.get("url"):
        prompt_lines.append(f"- URL: {item['url']}")

    if item.get("working_branch"):
        prompt_lines.append(f"- working branch: {item['working_branch']}")

    if item.get("execution_branch"):
        prompt_lines.append(f"- execution branch: {item['execution_branch']}")

    prompt_lines.extend(
        [
            f"- resolved state label: {state_label}",
            f"- agent mode: {mode}",
            f"- target repo path: {TARGET_REPO_PATH or '<not configured>'}",
            f"- agent profile source path: {profile_source or '<not available>'}",
            f"- launch brief artifact path: {launch_brief_path or '<not available>'}",
            "- instruction: Use GitHub metadata as the source of truth.",
        ]
    )

    if discovered_target_instruction_paths:
        prompt_lines.append("- target repository guidance: available in launch brief")

    if mode == "reviewer":
        prompt_lines.extend(
            [
                "- reviewer artifact contract: You must write `review-result.md` before exiting.",
                f"- reviewer result artifact absolute path: {review_result_path or '<not available>'}",
                "- reviewer outcome first non-empty line must be exactly one of:",
                "  - Outcome: APPROVED",
                "  - Outcome: CHANGES_REQUESTED",
                "  - Outcome: BLOCKED",
                "- reviewer failure fallback: if you cannot write the file, use `Outcome: BLOCKED` and explain why.",
            ]
        )

    if mode == "architect-review":
        prompt_lines.extend(
            [
                "- architect review artifact contract: You must write `architect-review-result.md` before exiting.",
                f"- architect review result artifact absolute path: {review_result_path or '<not available>'}",
                "- architect review outcome first non-empty line must be exactly one of:",
                "  - Outcome: APPROVED",
                "  - Outcome: CHANGES_REQUESTED",
                "  - Outcome: BLOCKED",
                "- architect review failure fallback: if you cannot write the file, use `Outcome: BLOCKED` and explain why.",
            ]
        )

    return "\n".join(prompt_lines)


def build_codex_command(model, project_path, task_text):
    return agents.build_codex_command(
        model,
        project_path,
        task_text,
        executable_paths=EXECUTABLE_PATHS,
    )


def is_codex_sandbox_bypass_enabled():
    return agents.is_codex_sandbox_bypass_enabled(
        env_getter=os.getenv,
    )


def build_codex_command_with_optional_sandbox_bypass(model, project_path, task_text, bypass_sandbox=False):
    return agents.build_codex_command_with_optional_sandbox_bypass(
        model,
        project_path,
        task_text,
        bypass_sandbox,
        executable_paths=EXECUTABLE_PATHS,
    )


def build_reviewer_result_path(launch_brief_path):
    return watchtower.build_reviewer_result_path(
        launch_brief_path,
        normalize_path_for_display_fn=normalize_path_for_display,
        review_result_filename=REVIEW_RESULT_FILENAME,
    )


def build_architect_review_result_path(launch_brief_path):
    return watchtower.build_architect_review_result_path(
        launch_brief_path,
        normalize_path_for_display_fn=normalize_path_for_display,
        architect_review_result_filename=ARCHITECT_REVIEW_RESULT_FILENAME,
    )


def parse_review_result_outcome(review_result_path):
    return workflow.parse_review_result_outcome(review_result_path)


def parse_architect_review_result_outcome(architect_review_result_path):
    return workflow.parse_architect_review_result_outcome(architect_review_result_path)


def extract_github_repo_slug(value):
    return git_workspace.extract_github_repo_slug(value)


def get_git_remote_origin_url(repo_path):
    return git_workspace.get_git_remote_origin_url(
        repo_path,
        run_subprocess=subprocess.run,
        log=print,
    )


def validate_target_repo_workspace(target_repo_path, expected_repo):
    return git_workspace.validate_target_repo_workspace(
        target_repo_path,
        expected_repo,
        path_exists=os.path.exists,
        is_dir=os.path.isdir,
        join_path=os.path.join,
        extract_repo_slug=extract_github_repo_slug,
        get_remote_origin_url=get_git_remote_origin_url,
        log=print,
    )


def resolve_worktree_root(target_repo_path, repo_slug, env_getter=os.getenv):
    return git_workspace.resolve_worktree_root(
        target_repo_path,
        repo_slug,
        env_getter,
        dirname=os.path.dirname,
        join_path=os.path.join,
        normpath=os.path.normpath,
    )


def resolve_item_workspace_metadata(item):
    return git_workspace.resolve_item_workspace_metadata(
        item,
        TARGET_REPO_PATH,
        REPO,
        os.getenv,
        resolve_worktree_root_fn=resolve_worktree_root,
        sanitize_filename_part_fn=sanitize_filename_part,
        join_path=os.path.join,
        normpath=os.path.normpath,
        normalize_path_for_display_fn=normalize_path_for_display,
    )


def slugify_branch_title(value, max_length=MAX_BRANCH_SLUG_LENGTH):
    return git_workspace.slugify_branch_title(value, max_length=max_length)


def build_developer_branch_name(item):
    return git_workspace.build_developer_branch_name(
        item,
        max_branch_slug_length=MAX_BRANCH_SLUG_LENGTH,
        slugify=slugify_branch_title,
    )


def run_git_command_in_repo(repo_path, git_args):
    return git_workspace.run_git_command_in_repo(
        repo_path,
        git_args,
        run_subprocess=subprocess.run,
        log=print,
    )


def get_current_git_branch(repo_path):
    return git_workspace.get_current_git_branch(
        repo_path,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def is_working_tree_clean(repo_path):
    return git_workspace.is_working_tree_clean(
        repo_path,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def local_branch_exists(repo_path, branch_name):
    return git_workspace.local_branch_exists(
        repo_path,
        branch_name,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def checkout_or_create_local_branch(repo_path, branch_name, branch_exists):
    return git_workspace.checkout_or_create_local_branch(
        repo_path,
        branch_name,
        branch_exists,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def refresh_local_base_branch(repo_path, branch_name):
    return git_workspace.refresh_local_base_branch(
        repo_path,
        branch_name,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def resolve_git_ref_commit(repo_path, ref_name):
    return git_workspace.resolve_git_ref_commit(
        repo_path,
        ref_name,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def is_commit_ancestor_of_branch(repo_path, ancestor_commit, branch_name):
    return git_workspace.is_commit_ancestor_of_branch(
        repo_path,
        ancestor_commit,
        branch_name,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def create_worktree_branch_from_base(repo_path, workspace_path, branch_name, base_ref):
    return git_workspace.create_worktree_branch_from_base(
        repo_path,
        workspace_path,
        branch_name,
        base_ref,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def prepare_developer_branch(item, workspace_path):
    return git_workspace.prepare_developer_branch(
        item,
        TARGET_REPO_PATH,
        workspace_path,
        build_branch_name=build_developer_branch_name,
        get_current_branch=get_current_git_branch,
        check_working_tree_clean=is_working_tree_clean,
        detect_default_branch=detect_default_base_branch,
        refresh_base_branch=refresh_local_base_branch,
        resolve_ref_commit=resolve_git_ref_commit,
        check_commit_ancestor=is_commit_ancestor_of_branch,
        check_local_branch_exists=local_branch_exists,
        create_worktree_branch_from_base=create_worktree_branch_from_base,
        path_exists=os.path.exists,
        log=print,
    )


def detect_default_base_branch(repo_path):
    return git_workspace.detect_default_base_branch(
        repo_path,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def checkout_branch(repo_path, branch_name):
    return git_workspace.checkout_branch(
        repo_path,
        branch_name,
        run_git_command=run_git_command_in_repo,
        log=print,
    )


def prepare_architect_execution_branch(item):
    return git_workspace.prepare_architect_execution_branch(
        item,
        TARGET_REPO_PATH,
        get_current_branch=get_current_git_branch,
        check_working_tree_clean=is_working_tree_clean,
        detect_default_branch=detect_default_base_branch,
        checkout_repo_branch=checkout_branch,
        log=print,
    )


def sanitize_filename_part(value):
    return handler_paths.sanitize_filename_part(value)


def normalize_path_for_display(path):
    return handler_paths.normalize_path_for_display(path)


def initialize_run_status(item, state_label, config, launch_brief_path, workspace_metadata=None):
    return watchtower.initialize_run_status(
        item,
        state_label,
        config,
        launch_brief_path,
        workspace_metadata=workspace_metadata,
        repo=REPO,
        target_repo_path=TARGET_REPO_PATH,
        normalize_path_for_display_fn=normalize_path_for_display,
        run_status_filename=RUN_STATUS_FILENAME,
        run_result_filename=RUN_RESULT_FILENAME,
        run_status_fields=RUN_STATUS_FIELDS,
    )


def get_run_state(item):
    return item.get("_run_state")


def read_run_status(run_state):
    return watchtower.read_run_status(
        run_state,
        run_status_fields=RUN_STATUS_FIELDS,
        normalize_path_for_display_fn=normalize_path_for_display,
    )


def write_run_status(run_state, status_payload):
    watchtower.write_run_status(run_state, status_payload)


def update_run_status(item, **updates):
    watchtower.update_run_status(
        item,
        get_run_state_fn=get_run_state,
        read_run_status_fn=read_run_status,
        write_run_status_fn=write_run_status,
        updates=updates,
    )


def write_run_result(item):
    watchtower.write_run_result(
        item,
        get_run_state_fn=get_run_state,
        read_run_status_fn=read_run_status,
    )


def get_next_run_number(item_run_root):
    return watchtower.get_next_run_number(item_run_root)


def get_item_run_root(item):
    return watchtower.get_item_run_root(
        item,
        launch_artifact_dir=LAUNCH_ARTIFACT_DIR,
        repo=REPO,
        sanitize_filename_part_fn=sanitize_filename_part,
        resolve_circus_runtime_path_fn=resolve_circus_runtime_path,
    )


def build_shared_context_paths(item_run_root):
    return watchtower.build_shared_context_paths(
        item_run_root,
        normalize_path_for_display_fn=normalize_path_for_display,
    )


def ensure_shared_artifacts(item_run_root):
    return watchtower.ensure_shared_artifacts(
        item_run_root,
        shared_artifact_placeholders=SHARED_ARTIFACT_PLACEHOLDERS,
        build_shared_context_paths_fn=build_shared_context_paths,
    )


def build_launch_brief_path(item, mode):
    return watchtower.build_launch_brief_path(
        item,
        mode,
        get_item_run_root_fn=get_item_run_root,
        get_next_run_number_fn=get_next_run_number,
        sanitize_filename_part_fn=sanitize_filename_part,
        normalize_path_for_display_fn=normalize_path_for_display,
    )


def build_launch_brief_markdown(
    item,
    state_label,
    config,
    role_prompt_path,
    timestamp,
    target_repo_path,
    shared_context_paths=None,
    review_result_path=None,
    workspace_metadata=None,
):
    return watchtower.build_launch_brief_markdown(
        item,
        state_label,
        config,
        role_prompt_path,
        timestamp,
        target_repo_path,
        repo=REPO,
        resolve_profile_source_fn=resolve_profile_source,
        normalize_path_for_display_fn=normalize_path_for_display,
        get_circus_runtime_root_fn=get_circus_runtime_root,
        shared_context_paths=shared_context_paths,
        review_result_path=review_result_path,
        workspace_metadata=workspace_metadata,
    )


def write_launch_brief(item, state_label, config, role_prompt_path):
    return watchtower.write_launch_brief(
        item,
        state_label,
        config,
        role_prompt_path,
        target_repo_path=TARGET_REPO_PATH,
        build_launch_brief_markdown_fn=build_launch_brief_markdown,
        get_item_run_root_fn=get_item_run_root,
        ensure_shared_artifacts_fn=ensure_shared_artifacts,
        build_launch_brief_path_fn=build_launch_brief_path,
        build_reviewer_result_path_fn=build_reviewer_result_path,
        build_architect_review_result_path_fn=build_architect_review_result_path,
        initialize_run_status_fn=initialize_run_status,
        update_run_status_fn=update_run_status,
        resolve_workspace_metadata_fn=resolve_item_workspace_metadata,
        normalize_path_for_display_fn=normalize_path_for_display,
        timestamp_now_fn=lambda: datetime.now().isoformat(timespec="seconds"),
        log=print,
    )


def launch_agent(item, state_label, config, role_prompt_path, launch_brief_path):
    agent = config["agent"]
    mode = config["mode"]
    model = config["model"]
    effort = config["effort"]
    number = item["number"]
    reviewer_result_path_for_prompt = None
    if mode == "reviewer":
        reviewer_result_path_for_prompt = build_reviewer_result_path(launch_brief_path)
    if mode == "architect-review":
        reviewer_result_path_for_prompt = build_architect_review_result_path(launch_brief_path)
    thin_prompt = build_thin_prompt(
        item,
        state_label,
        mode,
        role_prompt_path,
        launch_brief_path,
        review_result_path=reviewer_result_path_for_prompt,
    )

    print(f"[Dispatch] Launching {agent} in {mode} mode with model={model}, effort={effort}")
    print(f"[Dispatch] Target item: {item['type']} #{number} - {item['title']}")
    print(f"[Dispatch] Target repo path: {TARGET_REPO_PATH}")
    print(f"[Dispatch] Launch brief: {launch_brief_path}")
    print("[Dispatch] Generated thin prompt:")
    print(thin_prompt)

    update_run_status(
        item,
        started_at=utc_timestamp_now(),
        completed_at=None,
        exit_code=None,
        success=None,
        outcome="running",
        stop_reason=None,
        agent=agent,
        mode=mode,
        model=model,
        effort=effort,
        state_label=state_label,
        launch_brief_path=normalize_path_for_display(launch_brief_path),
    )

    systems_architect_state_labels = {
        SYSTEMS_ARCHITECTURE_LABEL,
        SYSTEMS_ARCHITECTURE_CHANGES_REQUESTED_LABEL,
    }
    implementation_planner_state_labels = {
        IMPLEMENTATION_PLANNING_LABEL,
        IMPLEMENTATION_PLANNING_CHANGES_REQUESTED_LABEL,
    }

    workspace_path = item.get("workspace_path")
    developer_execution_path = workspace_path or TARGET_REPO_PATH

    if agent == "junie":
        absolute_launch_brief_path = os.path.abspath(launch_brief_path)
        junie_task_text = build_junie_task_text(absolute_launch_brief_path)
        cmd = build_junie_command(model, effort, developer_execution_path or "", junie_task_text)
        normalized_target_repo_path = (
            normalize_path_for_display(developer_execution_path) if developer_execution_path else "<not configured>"
        )
        command_shape = (
            f"{cmd[0]} --project {cmd[2]} --model {cmd[4]} --effort {cmd[6]} "
            f"\"{cmd[7]}\""
        )

        print(f"[Dispatch] Launch brief display path: {launch_brief_path}")
        print(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}")
        print(f"[Dispatch] Junie target repo path: {normalized_target_repo_path}")
        print("[Dispatch] Junie handoff path: passing short positional task argument.")
        print(f"[Dispatch] Executing: {command_shape}")
        print(f"[Dispatch] Junie execution cwd: {developer_execution_path}")

        try:
            result = subprocess.run(cmd, cwd=developer_execution_path, text=True)
        except OSError as error:
            item["prelaunch_error"] = str(error)
            print(f"[Dispatch] Junie failed to launch before execution started: {error}")
            update_run_status(
                item,
                completed_at=utc_timestamp_now(),
                exit_code=None,
                success=False,
                outcome="failed pre-launch",
                stop_reason=str(error),
            )
            write_run_result(item)
            return False

        print(f"[Dispatch] Junie exit code: {result.returncode}")

        if result.returncode != 0:
            item["comment"] = (
                f"Junie launched for {item['type']} #{number} and exited with non-zero status "
                f"({result.returncode}). The lock label `{LOCK_LABEL}` remains in place for human inspection."
            )
            print(
                f"[Dispatch] Junie exited non-zero for {item['type']} #{number}; "
                "lock remains and human inspection is required."
            )
            add_comment(item)
            item["agent_exit_non_zero"] = True
            update_run_status(
                item,
                completed_at=utc_timestamp_now(),
                exit_code=result.returncode,
                success=False,
                outcome="failed agent execution",
                stop_reason=f"agent exited with code {result.returncode}",
            )
            write_run_result(item)
            return False
        else:
            item.pop("agent_exit_non_zero", None)
            if mode == "developer" and state_label in {"state:ready-for-dev", "state:changes-requested"}:
                launch_ok = finalize_developer_success_with_pull_request(
                    item,
                    launch_brief_path,
                    from_state_label=state_label,
                )
                outcome_value = "developer PR created" if launch_ok else "no changes detected"
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=0,
                    success=launch_ok,
                    outcome=outcome_value,
                    stop_reason=None if launch_ok else "developer post-run PR finalization did not complete",
                )
                write_run_result(item)
                return launch_ok

            print(f"[Dispatch] Junie completed with exit code 0 for {item['type']} #{number}; lock remains in place.")
            update_run_status(
                item,
                completed_at=utc_timestamp_now(),
                exit_code=0,
                success=True,
                outcome="completed",
                stop_reason=None,
            )
            write_run_result(item)
            return True
    elif agent == "codex":
        print(f"[Dispatch] Codex routing metadata: mode={mode}, effort={effort}")
        codex_bypass_sandbox = is_codex_sandbox_bypass_enabled()

        if codex_bypass_sandbox:
            print(
                "[Dispatch] WARNING: Codex sandbox bypass ENABLED via CIRCUS_CODEX_BYPASS_SANDBOX=true; "
                "running with --dangerously-bypass-approvals-and-sandbox (HIGH RISK)."
            )
        else:
            print(
                "[Dispatch] Codex sandbox bypass disabled (default-safe mode); "
                "set CIRCUS_CODEX_BYPASS_SANDBOX=true to enable HIGH-RISK bypass."
            )

        if mode == "reviewer":
            review_pr = item.get("review_pr") or {}
            review_pr_url = review_pr.get("url")
            review_pr_number = review_pr.get("number")
            if not review_pr_url:
                item["prelaunch_error"] = "missing linked pull request metadata"
                print("[Dispatch] Reviewer launch aborted: linked pull request metadata is missing.")
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason="missing linked pull request metadata",
                )
                write_run_result(item)
                return False

            absolute_launch_brief_path = os.path.abspath(launch_brief_path)
            item_run_root = get_item_run_root(item)
            shared_context_paths = build_shared_context_paths(item_run_root)
            architecture_handoff_path = shared_context_paths["architecture_handoff"]
            review_result_path = build_reviewer_result_path(launch_brief_path)
            reviewer_task_text = build_codex_reviewer_task_text(
                absolute_launch_brief_path,
                review_pr_url,
                review_result_path,
            )
            cmd = build_codex_command_with_optional_sandbox_bypass(
                model,
                TARGET_REPO_PATH or "",
                reviewer_task_text,
                bypass_sandbox=codex_bypass_sandbox,
            )
            command_arguments = cmd[1:-1]
            command_shape = f"{cmd[0]} {' '.join(command_arguments)} \"{cmd[-1]}\""

            reviewer_env = review_flow.build_reviewer_environment(
                review_pr_url=review_pr_url,
                review_pr_number=review_pr_number,
                issue_number=number,
                absolute_launch_brief_path=absolute_launch_brief_path,
                architecture_handoff_path=architecture_handoff_path,
                target_repo_path=TARGET_REPO_PATH,
                review_result_path=review_result_path,
            )

            print(f"[Dispatch] Review target issue: #{number}")
            print(f"[Dispatch] Review target PR: #{review_pr_number} ({review_pr_url})")
            print(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}")
            print(f"[Dispatch] Architecture handoff path: {architecture_handoff_path}")
            print(f"[Dispatch] Review result artifact path: {review_result_path}")
            print("[Dispatch] Reviewer command: codex exec")
            print(f"[Dispatch] Executing: {command_shape}")
            print(f"[Dispatch] Codex reviewer execution cwd: {TARGET_REPO_PATH}")

            try:
                result = subprocess.run(cmd, cwd=TARGET_REPO_PATH, text=True, env=reviewer_env)
            except OSError as error:
                item["prelaunch_error"] = str(error)
                print(f"[Dispatch] Codex reviewer failed to launch before execution started: {error}")
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason=str(error),
                )
                write_run_result(item)
                return False

            print(f"[Dispatch] Codex reviewer exit code: {result.returncode}")
            if result.returncode != 0:
                item["comment"] = (
                    f"Codex reviewer launched for {item['type']} #{number} and exited with non-zero status "
                    f"({result.returncode}). The lock label `{LOCK_LABEL}` remains in place for human inspection."
                )
                add_comment(item)
                item["agent_exit_non_zero"] = True
                print(
                    f"[Dispatch] Codex reviewer exited non-zero for {item['type']} #{number}; "
                    "lock remains and human inspection is required."
                )
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=result.returncode,
                    success=False,
                    outcome="failed agent execution",
                    stop_reason=f"agent exited with code {result.returncode}",
                )
                write_run_result(item)
                return False

            item.pop("agent_exit_non_zero", None)
            return review_flow.handle_reviewer_result(
                item=item,
                issue_number=number,
                result_returncode=result.returncode,
                item_run_root=item_run_root,
                review_pr_url=review_pr_url,
                review_result_path=review_result_path,
                lock_label=LOCK_LABEL,
                add_comment_fn=add_comment,
                update_run_status_fn=update_run_status,
                write_run_result_fn=write_run_result,
                parse_review_result_outcome_fn=parse_review_result_outcome,
                normalize_path_for_display_fn=normalize_path_for_display,
                append_reviewer_feedback_note_fn=append_reviewer_feedback_note,
                advance_reviewer_workflow_on_approved_fn=advance_reviewer_workflow_on_approved,
                advance_reviewer_workflow_on_changes_requested_fn=advance_reviewer_workflow_on_changes_requested,
                utc_timestamp_now_fn=utc_timestamp_now,
                path_exists_fn=os.path.exists,
                log=print,
            )

        if mode == "architect-review":
            review_pr = item.get("review_pr") or {}
            review_pr_url = review_pr.get("url")
            review_pr_number = review_pr.get("number")
            if not review_pr_url:
                item["prelaunch_error"] = "missing linked pull request metadata"
                print("[Dispatch] Architect review launch aborted: linked pull request metadata is missing.")
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason="missing linked pull request metadata",
                )
                write_run_result(item)
                return False

            absolute_launch_brief_path = os.path.abspath(launch_brief_path)
            item_run_root = get_item_run_root(item)
            shared_context_paths = build_shared_context_paths(item_run_root)
            architecture_handoff_path = shared_context_paths["architecture_handoff"]
            running_notes_path = shared_context_paths["running_notes"]
            decision_log_path = shared_context_paths["decision_log"]
            review_result_path = build_reviewer_result_path(launch_brief_path)
            architect_review_result_path = build_architect_review_result_path(launch_brief_path)
            architect_review_task_text = build_codex_architect_review_task_text(
                absolute_launch_brief_path,
                review_pr_url,
                architect_review_result_path,
            )
            cmd = build_codex_command_with_optional_sandbox_bypass(
                model,
                TARGET_REPO_PATH or "",
                architect_review_task_text,
                bypass_sandbox=codex_bypass_sandbox,
            )
            command_arguments = cmd[1:-1]
            command_shape = f"{cmd[0]} {' '.join(command_arguments)} \"{cmd[-1]}\""

            architect_review_env = review_flow.build_architect_review_environment(
                review_pr_url=review_pr_url,
                review_pr_number=review_pr_number,
                issue_number=number,
                absolute_launch_brief_path=absolute_launch_brief_path,
                architecture_handoff_path=architecture_handoff_path,
                running_notes_path=running_notes_path,
                decision_log_path=decision_log_path,
                review_result_path=review_result_path,
                architect_review_result_path=architect_review_result_path,
                target_repo_path=TARGET_REPO_PATH,
            )

            print(f"[Dispatch] Architect review target issue: #{number}")
            print(f"[Dispatch] Architect review target PR: #{review_pr_number} ({review_pr_url})")
            print(f"[Dispatch] Architect review launch brief absolute path: {absolute_launch_brief_path}")
            print(f"[Dispatch] Architecture handoff path: {architecture_handoff_path}")
            print(f"[Dispatch] Reviewer result artifact path: {review_result_path}")
            print(f"[Dispatch] Architect review result artifact path: {architect_review_result_path}")
            print("[Dispatch] Architect reviewer command: codex exec")
            print(f"[Dispatch] Executing: {command_shape}")
            print(f"[Dispatch] Codex architect review execution cwd: {TARGET_REPO_PATH}")

            try:
                result = subprocess.run(cmd, cwd=TARGET_REPO_PATH, text=True, env=architect_review_env)
            except OSError as error:
                item["prelaunch_error"] = str(error)
                print(f"[Dispatch] Codex architect review failed to launch before execution started: {error}")
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason=str(error),
                )
                write_run_result(item)
                return False

            print(f"[Dispatch] Codex architect review exit code: {result.returncode}")
            if result.returncode != 0:
                item["comment"] = (
                    f"Codex architect review launched for {item['type']} #{number} and exited with non-zero status "
                    f"({result.returncode}). The lock label `{LOCK_LABEL}` remains in place for human inspection."
                )
                add_comment(item)
                item["agent_exit_non_zero"] = True
                print(
                    f"[Dispatch] Codex architect review exited non-zero for {item['type']} #{number}; "
                    "lock remains and human inspection is required."
                )
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=result.returncode,
                    success=False,
                    outcome="failed agent execution",
                    stop_reason=f"agent exited with code {result.returncode}",
                )
                write_run_result(item)
                return False

            item.pop("agent_exit_non_zero", None)
            return review_flow.handle_architect_review_result(
                item=item,
                issue_number=number,
                result_returncode=result.returncode,
                item_run_root=item_run_root,
                review_pr_url=review_pr_url,
                architect_review_result_path=architect_review_result_path,
                lock_label=LOCK_LABEL,
                add_comment_fn=add_comment,
                update_run_status_fn=update_run_status,
                write_run_result_fn=write_run_result,
                parse_architect_review_result_outcome_fn=parse_architect_review_result_outcome,
                normalize_path_for_display_fn=normalize_path_for_display,
                append_architect_review_feedback_note_fn=append_architect_review_feedback_note,
                advance_architect_review_workflow_on_approved_fn=advance_architect_review_workflow_on_approved,
                advance_architect_review_workflow_on_changes_requested_fn=advance_architect_review_workflow_on_changes_requested,
                utc_timestamp_now_fn=utc_timestamp_now,
                path_exists_fn=os.path.exists,
                log=print,
            )

        if mode not in {"architect", "systems-architect", "roadmap-updater", "implementation-planner"}:
            print("[Dispatch] TODO: Codex execution flow currently enabled only for architect/reviewer/roadmap-updater modes.")
            update_run_status(
                item,
                completed_at=utc_timestamp_now(),
                exit_code=0,
                success=True,
                outcome="completed",
                stop_reason="codex mode not implemented for this workflow path",
            )
            write_run_result(item)
            return True

        absolute_launch_brief_path = os.path.abspath(launch_brief_path)
        if mode == "systems-architect" and state_label in systems_architect_state_labels:
            codex_task_text = build_codex_systems_architect_task_text(absolute_launch_brief_path)
        elif mode == "implementation-planner" and state_label in implementation_planner_state_labels:
            codex_task_text = build_codex_implementation_planner_task_text(absolute_launch_brief_path)
        elif mode == "roadmap-updater":
            codex_task_text = build_codex_roadmap_updater_task_text(absolute_launch_brief_path)
        else:
            codex_task_text = build_codex_architect_task_text(absolute_launch_brief_path)
        codex_execution_path = developer_execution_path if mode == "roadmap-updater" else TARGET_REPO_PATH
        cmd = build_codex_command_with_optional_sandbox_bypass(
            model,
            codex_execution_path or "",
            codex_task_text,
            bypass_sandbox=codex_bypass_sandbox,
        )
        normalized_target_repo_path = normalize_path_for_display(codex_execution_path) if codex_execution_path else "<not configured>"
        command_arguments = cmd[1:-1]
        command_shape = f"{cmd[0]} {' '.join(command_arguments)} \"{cmd[-1]}\""

        print(f"[Dispatch] Launch brief display path: {launch_brief_path}")
        print(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}")
        print(f"[Dispatch] Codex target repo path: {normalized_target_repo_path}")
        print("[Dispatch] Codex handoff path: passing short positional prompt argument.")
        print(f"[Dispatch] Executing: {command_shape}")
        print(f"[Dispatch] Codex execution cwd: {codex_execution_path}")

        try:
            result = subprocess.run(cmd, cwd=codex_execution_path, text=True)
        except OSError as error:
            item["prelaunch_error"] = str(error)
            print(f"[Dispatch] Codex failed to launch before execution started: {error}")
            update_run_status(
                item,
                completed_at=utc_timestamp_now(),
                exit_code=None,
                success=False,
                outcome="failed pre-launch",
                stop_reason=str(error),
            )
            write_run_result(item)
            return False

        print(f"[Dispatch] Codex exit code: {result.returncode}")

        if result.returncode != 0:
            item["comment"] = (
                f"Codex launched for {item['type']} #{number} and exited with non-zero status "
                f"({result.returncode}). The lock label `{LOCK_LABEL}` remains in place for human inspection."
            )
            print(
                f"[Dispatch] Codex exited non-zero for {item['type']} #{number}; "
                "lock remains and human inspection is required."
            )
            add_comment(item)
            item["agent_exit_non_zero"] = True
            update_run_status(
                item,
                completed_at=utc_timestamp_now(),
                exit_code=result.returncode,
                success=False,
                outcome="failed agent execution",
                stop_reason=f"agent exited with code {result.returncode}",
            )
            write_run_result(item)
            return False
        else:
            item.pop("agent_exit_non_zero", None)
            if mode == "architect" and state_label == "state:ready-for-architecture":
                advanced = advance_architect_workflow_on_success(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=0,
                    success=advanced,
                    outcome="architect handoff generated",
                    stop_reason=None if advanced else "label transition failed",
                )
                write_run_result(item)
                return advanced
            elif mode == "systems-architect" and state_label in systems_architect_state_labels:
                advanced = advance_systems_architect_workflow_on_success(item, from_state_label=state_label)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=0,
                    success=advanced,
                    outcome="systems architecture recommendation generated",
                    stop_reason=None if advanced else "label transition failed",
                )
                write_run_result(item)
                return advanced
            elif mode == "roadmap-updater":
                validated = validate_roadmap_updater_open_pull_request(item)
                advanced = validated
                if validated:
                    advanced = advance_roadmap_update_workflow_on_success(item, from_state_label=state_label)

                if advanced:
                    outcome = "roadmap documentation PR ready"
                    stop_reason = None
                elif validated:
                    outcome = "roadmap documentation update complete"
                    stop_reason = "label transition failed"
                else:
                    outcome = "roadmap documentation PR validation failed"
                    stop_reason = "roadmap updater PR validation failed"

                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=0,
                    success=advanced,
                    outcome=outcome,
                    stop_reason=stop_reason,
                )
                write_run_result(item)
                return advanced
            elif mode == "implementation-planner" and state_label in implementation_planner_state_labels:
                advanced = advance_implementation_planning_workflow_on_success(item, from_state_label=state_label)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=0,
                    success=advanced,
                    outcome="implementation plan generated",
                    stop_reason=None if advanced else "label transition failed",
                )
                write_run_result(item)
                return advanced
            else:
                print(f"[Dispatch] Codex completed with exit code 0 for {item['type']} #{number}; lock remains in place.")
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=0,
                    success=True,
                    outcome="completed",
                    stop_reason=None,
                )
                write_run_result(item)
                return True
    else:
        print(f"[Dispatch] Unknown agent: {agent}")
        update_run_status(
            item,
            completed_at=utc_timestamp_now(),
            exit_code=None,
            success=False,
            outcome="failed pre-launch",
            stop_reason=f"unknown agent: {agent}",
        )
        write_run_result(item)
        return False


def get_item_key(item):
    return f"{item['type']}-{item['number']}"


def log_issue_step_limit_reached(item, state_label, steps_completed_this_run, max_steps_per_run):
    print(
        f"[Handler] {item['type']} #{item['number']} reached max workflow steps for this Handler run "
        f"({steps_completed_this_run}/{max_steps_per_run})."
    )
    print(
        f"[Handler] Current state label for {item['type']} #{item['number']}: {state_label}."
    )
    print(
        "[Handler] Human decision required: restart Handler to allow more steps, "
        f"increase {MAX_STEPS_PER_RUN_ENV}, or mark the issue blocked if it should not continue."
    )


def process_one_item(
    items,
    issue_steps_this_run=None,
    max_steps_per_run=None,
    capped_issue_keys=None,
    on_dispatch_success=None,
):
    if issue_steps_this_run is None:
        issue_steps_this_run = {}

    if capped_issue_keys is None:
        capped_issue_keys = set()

    for item in items:
        labels = [label["name"] for label in item["labels"]]

        if is_locked(labels):
            print(f"[Poll] Skipping {item['type']} #{item['number']}: lock label '{LOCK_LABEL}' already present.")
            continue

        dispatch_resolution = resolve_dispatch_config(item, labels)
        if not dispatch_resolution:
            skip_reason = item.get("skip_reason", "missing workflow context")
            print(f"[Poll] Skipping {item['type']} #{item['number']}: {skip_reason}.")
            add_comment(item)
            continue

        state_label, config = dispatch_resolution
        item_key = get_item_key(item)
        if max_steps_per_run is not None and issue_steps_this_run.get(item_key, 0) >= max_steps_per_run:
            if item_key not in capped_issue_keys:
                capped_issue_keys.add(item_key)
                log_issue_step_limit_reached(
                    item,
                    state_label,
                    issue_steps_this_run.get(item_key, 0),
                    max_steps_per_run,
                )
            continue

        print(
            f"[Dispatch] Candidate selected: type={item['type']} number={item['number']} "
            f"title={json.dumps(item['title'])}"
        )
        print(
            f"[Dispatch] Routing: state={state_label} agent={config['agent']} "
            f"model={config['model']} effort={config['effort']}"
        )

        print(f"[Dispatch] Acquiring lock for {item['type']} #{item['number']}...")

        if not lock_item(item):
            print(f"[Dispatch] Lock acquisition failed for {item['type']} #{item['number']}; stopping dispatch.")
            return "lock-failed"

        print(f"[Dispatch] Lock acquired for {item['type']} #{item['number']}.")

        current_item, revalidation_result = revalidate_candidate_after_lock(item, state_label)
        if revalidation_result:
            return revalidation_result
        item = current_item

        item.pop("working_branch", None)
        item.pop("execution_branch", None)
        item.pop("review_pr", None)
        if config["agent"] == "junie" and config["mode"] == "developer":
            workspace_metadata = resolve_item_workspace_metadata(item)
            workspace_path = workspace_metadata.get("workspace_path")
            item["workspace_path"] = workspace_path
            branch_setup = prepare_developer_branch(item, workspace_path)
            if not branch_setup.get("ok"):
                if branch_setup.get("reason") == "dirty-working-tree":
                    failure_launch_brief_path = write_launch_brief(item, state_label, config, resolve_role_prompt_path(config["mode"]))
                    print(
                        f"[Dispatch] Blocking developer launch for {item['type']} #{item['number']}: "
                        "target repository working tree is dirty."
                    )
                    print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to pre-launch setup failure...")
                    lock_released = unlock_item(item)

                    if lock_released:
                        print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
                    else:
                        print(
                            f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; "
                            "manual cleanup may be required."
                        )

                    lock_result = "released" if lock_released else "could not be released"
                    current_branch = branch_setup.get("current_branch") or "<unknown>"
                    item["comment"] = (
                        f"Handler blocked developer launch for {item['type']} #{item['number']} because "
                        f"the target repository working tree is dirty on branch `{current_branch}`. "
                        f"The lock label `{LOCK_LABEL}` was {lock_result}. "
                        "Please clean the workspace and retry dispatch."
                    )
                    add_comment(item)
                    update_run_status(
                        item,
                        completed_at=utc_timestamp_now(),
                        exit_code=None,
                        success=False,
                        outcome="failed pre-launch",
                        stop_reason="target repository working tree is dirty",
                        launch_brief_path=normalize_path_for_display(failure_launch_brief_path),
                    )
                    write_run_result(item)
                    return "prelaunch-failed"

                print(
                    f"[Dispatch] Developer branch setup failed for {item['type']} #{item['number']}: "
                    f"{branch_setup.get('error', 'unknown error')}"
                )
                print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to pre-launch setup failure...")
                lock_released = unlock_item(item)

                if lock_released:
                    print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
                else:
                    print(f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; manual cleanup may be required.")

                add_prelaunch_setup_failure_comment(item, branch_setup.get("error", "developer branch setup failed"), lock_released)
                add_comment(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason=branch_setup.get("error", "developer branch setup failed"),
                )
                write_run_result(item)
                return "prelaunch-failed"

            item["working_branch"] = branch_setup["branch"]
            item["workspace_path"] = branch_setup.get("workspace_path", workspace_path)

        if config["agent"] == "codex" and config["mode"] == "roadmap-updater":
            workspace_metadata = resolve_item_workspace_metadata(item)
            workspace_path = workspace_metadata.get("workspace_path")
            item["workspace_path"] = workspace_path
            branch_setup = prepare_developer_branch(item, workspace_path)
            if not branch_setup.get("ok"):
                if branch_setup.get("reason") == "dirty-working-tree":
                    failure_launch_brief_path = write_launch_brief(item, state_label, config, resolve_role_prompt_path(config["mode"]))
                    print(
                        f"[Dispatch] Blocking roadmap updater launch for {item['type']} #{item['number']}: "
                        "target repository working tree is dirty."
                    )
                    print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to pre-launch setup failure...")
                    lock_released = unlock_item(item)

                    if lock_released:
                        print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
                    else:
                        print(
                            f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; "
                            "manual cleanup may be required."
                        )

                    lock_result = "released" if lock_released else "could not be released"
                    current_branch = branch_setup.get("current_branch") or "<unknown>"
                    item["comment"] = (
                        f"Handler blocked roadmap updater launch for {item['type']} #{item['number']} because "
                        f"the target repository working tree is dirty on branch `{current_branch}`. "
                        f"The lock label `{LOCK_LABEL}` was {lock_result}. "
                        "Please clean the workspace and retry dispatch."
                    )
                    add_comment(item)
                    update_run_status(
                        item,
                        completed_at=utc_timestamp_now(),
                        exit_code=None,
                        success=False,
                        outcome="failed pre-launch",
                        stop_reason="target repository working tree is dirty",
                        launch_brief_path=normalize_path_for_display(failure_launch_brief_path),
                    )
                    write_run_result(item)
                    return "prelaunch-failed"

                print(
                    f"[Dispatch] Roadmap updater branch setup failed for {item['type']} #{item['number']}: "
                    f"{branch_setup.get('error', 'unknown error')}"
                )
                print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to pre-launch setup failure...")
                lock_released = unlock_item(item)

                if lock_released:
                    print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
                else:
                    print(f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; manual cleanup may be required.")

                add_prelaunch_setup_failure_comment(item, branch_setup.get("error", "roadmap updater branch setup failed"), lock_released)
                add_comment(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason=branch_setup.get("error", "roadmap updater branch setup failed"),
                )
                write_run_result(item)
                return "prelaunch-failed"

            item["working_branch"] = branch_setup["branch"]
            item["workspace_path"] = branch_setup.get("workspace_path", workspace_path)

        if config["agent"] == "codex" and config["mode"] == "architect":
            branch_setup = prepare_architect_execution_branch(item)
            if not branch_setup.get("ok"):
                if branch_setup.get("reason") == "dirty-working-tree":
                    failure_launch_brief_path = write_launch_brief(item, state_label, config, resolve_role_prompt_path(config["mode"]))
                    print(
                        f"[Dispatch] Blocking architect launch for {item['type']} #{item['number']}: "
                        "target repository working tree is dirty."
                    )
                    print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to pre-launch setup failure...")
                    lock_released = unlock_item(item)

                    if lock_released:
                        print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
                    else:
                        print(
                            f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; "
                            "manual cleanup may be required."
                        )

                    lock_result = "released" if lock_released else "could not be released"
                    current_branch = branch_setup.get("current_branch") or "<unknown>"
                    item["comment"] = (
                        f"Handler blocked architect launch for {item['type']} #{item['number']} because "
                        f"the target repository working tree is dirty on branch `{current_branch}`. "
                        f"The lock label `{LOCK_LABEL}` was {lock_result}. "
                        "Please clean the workspace and retry dispatch."
                    )
                    add_comment(item)
                    update_run_status(
                        item,
                        completed_at=utc_timestamp_now(),
                        exit_code=None,
                        success=False,
                        outcome="failed pre-launch",
                        stop_reason="target repository working tree is dirty",
                        launch_brief_path=normalize_path_for_display(failure_launch_brief_path),
                    )
                    write_run_result(item)
                    return "prelaunch-failed"

                print(
                    f"[Dispatch] Architect branch setup failed for {item['type']} #{item['number']}: "
                    f"{branch_setup.get('error', 'unknown error')}"
                )
                print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to pre-launch setup failure...")
                lock_released = unlock_item(item)

                if lock_released:
                    print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
                else:
                    print(f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; manual cleanup may be required.")

                add_prelaunch_setup_failure_comment(item, branch_setup.get("error", "architect branch setup failed"), lock_released)
                add_comment(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason=branch_setup.get("error", "architect branch setup failed"),
                )
                write_run_result(item)
                return "prelaunch-failed"

            item["execution_branch"] = branch_setup["branch"]

        if config["agent"] == "codex" and config["mode"] in {"reviewer", "architect-review"}:
            if item["type"] != "issue":
                review_mode_name = "architect review" if config["mode"] == "architect-review" else "review"
                print(
                    f"[Dispatch] Skipping {review_mode_name} launch for {item['type']} #{item['number']}: "
                    "review dispatch is issue-driven in v1."
                )
                lock_released = unlock_item(item)
                lock_result = "released" if lock_released else "could not be released"
                item["comment"] = (
                    "Handler skipped review dispatch because workflow review states are issue-owned in v1. "
                    f"Expected an issue, but got `{item['type']}` #{item['number']}. "
                    f"The lock label `{LOCK_LABEL}` was {lock_result}."
                )
                add_comment(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason="review dispatch expected issue item type",
                )
                write_run_result(item)
                return "prelaunch-failed"

            review_mode_name = "architect review" if config["mode"] == "architect-review" else "review"
            print(
                f"[Dispatch] {review_mode_name.capitalize()} candidate selected for issue #{item['number']}; "
                "discovering linked open PR..."
            )
            review_pr_lookup = find_open_review_pr_for_issue(item["number"])
            if not review_pr_lookup.get("ok"):
                print(
                    f"[Dispatch] {review_mode_name.capitalize()} PR discovery failed for issue #{item['number']}: "
                    f"{review_pr_lookup.get('error', 'unknown error')}"
                )
                lock_released = unlock_item(item)
                lock_result = "released" if lock_released else "could not be released"
                item["comment"] = (
                    f"Handler could not discover a linked open pull request for issue #{item['number']} "
                    f"({review_pr_lookup.get('error', 'unknown error')}). {review_mode_name.capitalize()} launch was skipped and "
                    f"workflow labels were left unchanged. The lock label `{LOCK_LABEL}` was {lock_result}."
                )
                add_comment(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason=review_pr_lookup.get("error", "review PR discovery failed"),
                )
                write_run_result(item)
                return "prelaunch-failed"

            review_pr = review_pr_lookup.get("pr")
            if not review_pr:
                print(
                    f"[Dispatch] No linked open PR discovered for issue #{item['number']}; "
                    "reviewer launch skipped and labels left unchanged."
                )
                lock_released = unlock_item(item)
                lock_result = "released" if lock_released else "could not be released"
                item["comment"] = (
                    f"Handler found issue #{item['number']} in `{state_label}`, but no linked open PR "
                    f"was discovered. {review_mode_name.capitalize()} launch was skipped and workflow labels were left unchanged. "
                    f"The lock label `{LOCK_LABEL}` was {lock_result}."
                )
                add_comment(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason="no linked open PR discovered for review dispatch",
                )
                write_run_result(item)
                return "prelaunch-failed"

            item["review_pr"] = {
                "number": review_pr.get("number"),
                "url": review_pr.get("url"),
            }
            print(
                f"[Dispatch] Linked PR discovered for issue #{item['number']}: "
                f"#{review_pr.get('number')} ({review_pr.get('url')}) "
                f"[{review_pr_lookup.get('match_reason', 'unspecified-match')}]."
            )

        role_prompt_path = resolve_role_prompt_path(config["mode"])

        try:
            launch_brief_path = write_launch_brief(item, state_label, config, role_prompt_path)
        except OSError as error:
            print(f"[Dispatch] Failed to write launch brief for {item['type']} #{item['number']}: {error}")
            print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to pre-launch setup failure...")
            lock_released = unlock_item(item)

            if lock_released:
                print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
            else:
                print(f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; manual cleanup may be required.")

            add_prelaunch_setup_failure_comment(item, error, lock_released)
            add_comment(item)
            return "prelaunch-failed"

        print(f"[Dispatch] Launch brief generated: {launch_brief_path}")

        if launch_agent(item, state_label, config, role_prompt_path, launch_brief_path):
            if on_dispatch_success:
                on_dispatch_success(item, state_label)
            return "success"

        prelaunch_error = item.get("prelaunch_error")
        if prelaunch_error:
            print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to launch failure...")
            lock_released = unlock_item(item)

            if lock_released:
                print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
            else:
                print(f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; manual cleanup may be required.")

            lock_result = "released" if lock_released else "could not be released"
            item["comment"] = (
                f"Handler failed to start {config['agent']} before execution began "
                f"({prelaunch_error}). The lock label `{LOCK_LABEL}` was {lock_result}."
            )
            add_comment(item)
            item.pop("prelaunch_error", None)
            return "prelaunch-failed"

        if item.get("agent_exit_non_zero"):
            item.pop("agent_exit_non_zero", None)
            return "agent-non-zero"

        if item.get("missing_review_result_artifact"):
            item.pop("missing_review_result_artifact", None)
            return "review-result-missing"

        return "dispatch-failed"

    return "no-dispatch"


def poll():
    global EXECUTABLE_PATHS

    if not REPO:
        print("[Handler] Error: CIRCUS_REPO environment variable is required but not set. Expected format: owner/repo.")
        print("[Handler] Handler cannot continue without an explicit repository target.")
        return

    print("[Handler] Starting Handler...")
    print(f"[Handler] Configured repository: {REPO}")
    print(f"[Handler] Resolved Circus runtime root: {normalize_path_for_display(get_circus_runtime_root())}")
    print(f"[Handler] Resolved target repo root: {normalize_path_for_display(TARGET_REPO_PATH) if TARGET_REPO_PATH else '<not configured>'}")

    workspace_repo_slug = sanitize_filename_part(extract_github_repo_slug(REPO) or "unknown-repo")
    worktree_root, worktree_root_source = resolve_worktree_root(TARGET_REPO_PATH, workspace_repo_slug)
    print(f"[Handler] Resolved target worktree root: {normalize_path_for_display(worktree_root) if worktree_root else '<not configured>'}")
    print(f"[Handler] Worktree root source: {worktree_root_source}")

    resolved_executables = validate_required_executables()
    if resolved_executables is None:
        return

    EXECUTABLE_PATHS = resolved_executables

    if not validate_target_repo_workspace(TARGET_REPO_PATH, REPO):
        return

    if not verify_github_repo_access():
        print("[Handler] Startup check failed. Exiting.")
        return

    max_steps_per_run = get_max_steps_per_run()
    print(f"[Handler] Max workflow steps per issue this run: {max_steps_per_run}")

    startup_retrieval_confirmed = False
    cycle_number = 0
    issue_steps_this_run = {}
    capped_issue_keys = set()

    while True:
        cycle_number += 1
        print(f"[Poll] Starting cycle #{cycle_number}...")
        issues, prs, items, retrieval_ok = get_labeled_items()

        if retrieval_ok:
            print(f"[Poll] Retrieved issues={len(issues)}, prs={len(prs)}, candidates={len(items)}.")
            if not startup_retrieval_confirmed:
                print("[GitHub] Startup retrieval check succeeded for issues and PRs.")
                startup_retrieval_confirmed = True
        else:
            print("[GitHub] Failed to retrieve issues/PRs this cycle; stopping current run.")
            return

        if not items:
            print("[Poll] No candidate items matched workflow labels this cycle.")
            print(f"[Handler] No eligible workflow step found. Sleeping {POLL_INTERVAL} seconds before re-polling.")
            time.sleep(POLL_INTERVAL)
            continue

        def record_dispatch_success(item, state_label):
            item_key = get_item_key(item)
            updated_count = issue_steps_this_run.get(item_key, 0) + 1
            issue_steps_this_run[item_key] = updated_count
            print(
                f"[Handler] Completed workflow step {updated_count} of {max_steps_per_run} "
                f"for {item['type']} #{item['number']} ({state_label})."
            )

            if updated_count < max_steps_per_run:
                return

            if item_key not in capped_issue_keys:
                capped_issue_keys.add(item_key)
            log_issue_step_limit_reached(item, state_label, updated_count, max_steps_per_run)

            run_state = get_run_state(item)
            if not run_state:
                return

            update_run_status(
                item,
                stop_reason=f"max steps reached this handler run ({updated_count}/{max_steps_per_run})",
            )
            write_run_result(item)

        dispatch_result = process_one_item(
            items,
            issue_steps_this_run=issue_steps_this_run,
            max_steps_per_run=max_steps_per_run,
            capped_issue_keys=capped_issue_keys,
            on_dispatch_success=record_dispatch_success,
        )
        if dispatch_result == "success":
            print("[Handler] Re-polling for next eligible workflow step.")
            continue
        if dispatch_result == "stale-candidate":
            print("[Handler] Re-polling: candidate changed workflow state after lock acquisition.")
            continue

        if dispatch_result == "lock-failed":
            print("[Handler] Stopping run: lock could not be acquired.")
            return
        if dispatch_result == "agent-non-zero":
            print("[Handler] Stopping run: agent exited non-zero and requires human inspection.")
            return
        if dispatch_result == "prelaunch-failed":
            print("[Handler] Stopping run: pre-launch failure encountered.")
            return
        if dispatch_result == "dispatch-failed":
            print("[Handler] Stopping run: dispatch failed.")
            return
        if dispatch_result == "review-result-missing":
            print("[Handler] Stopping run: reviewer completed without review-result artifact.")
            return
        if dispatch_result == "no-dispatch":
            print(f"[Handler] No dispatch completed this cycle. Sleeping {POLL_INTERVAL} seconds before re-polling.")
            time.sleep(POLL_INTERVAL)
            continue

if __name__ == "__main__":
    poll()
