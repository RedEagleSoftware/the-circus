import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, UTC
from dotenv import load_dotenv

from Handler import agents
from Handler import config as handler_config
from Handler import dependencies
from Handler import developer_flow
from Handler import git_workspace
from Handler import github_client
from Handler import human_decision_ledger
from Handler import paths as handler_paths
from Handler import recovery
from Handler import review_flow
from Handler import target_instructions
from Handler import watchtower
from Handler import workflow
from Handler import workflow_classification
from Handler import workspace_diagnostics
from Handler.workflow_states import (
    HUMAN_REVIEW_LABEL,
    IMPLEMENTATION_PLAN_REVIEW_LABEL,
    IMPLEMENTATION_PLANNING_CHANGES_REQUESTED_LABEL,
    IMPLEMENTATION_PLANNING_LABEL,
    PLANNED_LABEL,
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
IMPLEMENTATION_PLAN_FILENAME = watchtower.IMPLEMENTATION_PLAN_FILENAME
REVIEW_OUTCOMES = workflow.REVIEW_OUTCOMES
REVIEW_OUTCOME_MARKERS = workflow.REVIEW_OUTCOME_MARKERS
IMPLEMENTATION_PLAN_OUTCOMES = {"READY", "BLOCKED", "ESCALATION_REQUIRED"}
IMPLEMENTATION_PLAN_APPROVAL_DECISION_TYPES = {
    "implementation_plan_review_approval",
    "generated_issue_dispatch_approval",
}
PLANNER_RESULT_V1_JSON_BLOCK_PATTERN = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
PLANNER_RESULT_V1_FENCED_BLOCK_PATTERN = re.compile(r"```(?:yaml|yml|json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
STATE_LABEL_PATTERN = re.compile(r"\b(state:[A-Za-z0-9][A-Za-z0-9-]*)\b")

AGENT_EXECUTABLE_ENV_OVERRIDES = {
    "junie": "CIRCUS_JUNIE_EXECUTABLE",
    "codex": "CIRCUS_CODEX_EXECUTABLE",
}

EXECUTABLE_PATHS = {}

RUN_STATUS_FILENAME = watchtower.RUN_STATUS_FILENAME
RUN_RESULT_FILENAME = watchtower.RUN_RESULT_FILENAME
RECOVERY_DIAGNOSTIC_FILENAME = "recovery-diagnostic.json"

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
    return github_client.add_comment(item, repo=REPO, run_command_fn=run_command)


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


def get_current_item(item, fields="number,labels,title,url"):
    return github_client.get_item(item["type"], item["number"], repo=REPO, run_command_fn=run_command, fields=fields)


def get_labeled_items():
    issues, issues_ok = get_candidates("issue", "issue list")
    prs, prs_ok = get_candidates("pr", "pr list")

    all_items = []
    all_items.extend(issues)
    all_items.extend(prs)

    candidates = []
    for item in all_items:
        labels = [label["name"] for label in item["labels"]]
        primary_states = get_known_primary_workflow_state_labels(labels)

        if primary_states:
            candidates.append(item)
            continue

        unsupported_state_labels = get_unsupported_state_labels(labels)
        if unsupported_state_labels:
            print(
                f"[Poll] {item['type']} #{item['number']} has unsupported state label(s): {repr(unsupported_state_labels)}"
            )

    return issues, prs, candidates, issues_ok and prs_ok


def get_primary_state_labels(labels):
    return workflow.get_primary_state_labels(labels)


def get_known_primary_workflow_state_labels(labels):
    return workflow.get_known_primary_workflow_state_labels(labels)


def get_state_labels(labels):
    return workflow.get_state_labels(labels)


def get_unsupported_state_labels(labels):
    return workflow.get_unsupported_state_labels(labels)


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


def evaluate_item_dependencies(item):
    return dependencies.evaluate_dependencies(
        item.get("body"),
        default_repo=REPO,
        run_command_fn=run_command,
    )


def apply_dependency_block_transition(item, labels):
    dispatchable_states = workflow.get_dispatchable_state_labels(labels)
    transition_steps = [("remove", LOCK_LABEL)]
    if dispatchable_states:
        transition_steps.append(("remove", dispatchable_states[0]))
    transition_steps.append(("add", "state:dependency-blocked"))

    transition_ok = execute_label_transition(
        item,
        workflow_name="Dependency Recovery",
        transition_steps=transition_steps,
        success_message="[Dispatch] Item #{number} moved to dependency-blocked after stale-run recovery.",
        failure_message=(
            "[Dispatch] Dependency recovery transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
    )

    return transition_ok


def _normalize_watchtower_run_state(status_payload):
    if not isinstance(status_payload, dict):
        return None

    status_value = status_payload.get("status")
    if isinstance(status_value, str) and status_value.strip():
        return {
            "status": status_value.strip(),
            "outcome": status_payload.get("outcome"),
            "stop_reason": status_payload.get("stop_reason"),
            "success": status_payload.get("success"),
        }

    outcome_value = status_payload.get("outcome")
    if isinstance(outcome_value, str) and outcome_value.strip():
        return {
            "status": outcome_value.strip(),
            "outcome": outcome_value.strip(),
            "stop_reason": status_payload.get("stop_reason"),
            "success": status_payload.get("success"),
        }

    return None


def _load_latest_watchtower_run_for_item(item):
    run_state = get_run_state(item)
    if isinstance(run_state, dict) and run_state.get("status_path"):
        try:
            status_payload = read_run_status(run_state)
        except (OSError, TypeError, ValueError):
            status_payload = None

        normalized_state = _normalize_watchtower_run_state(status_payload)
        if normalized_state is not None:
            return normalized_state

    try:
        item_run_root = get_item_run_root(item)
    except (OSError, TypeError, ValueError):
        return None

    try:
        run_directories = sorted(
            [
                entry
                for entry in os.listdir(item_run_root)
                if os.path.isdir(os.path.join(item_run_root, entry)) and entry.startswith("run-")
            ],
            reverse=True,
        )
    except OSError:
        return None

    for run_directory in run_directories:
        status_path = os.path.join(item_run_root, run_directory, RUN_STATUS_FILENAME)
        try:
            with open(status_path, "r", encoding="utf-8") as status_file:
                status_payload = json.load(status_file)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue

        normalized_state = _normalize_watchtower_run_state(status_payload)
        if normalized_state is not None:
            return normalized_state

    return None


def _build_workspace_lifecycle_item_for_recovery(item):
    labels = item.get("labels") if isinstance(item, dict) else None
    if not isinstance(labels, list):
        return item

    normalized_labels = []
    for label in labels:
        if isinstance(label, dict):
            label_name = str(label.get("name") or "").strip().lower()
            if label_name == LOCK_LABEL:
                continue
        elif str(label).strip().lower() == LOCK_LABEL:
            continue
        normalized_labels.append(label)

    normalized_item = dict(item)
    normalized_item["labels"] = normalized_labels
    return normalized_item


def collect_workspace_lifecycle_for_item(item, *, for_recovery=False):
    metadata = resolve_item_workspace_metadata(item)
    workspace_path = metadata.get("workspace_path")
    if not workspace_path:
        return None

    inventory_item = _build_workspace_lifecycle_item_for_recovery(item) if for_recovery else item
    watchtower_run = _load_latest_watchtower_run_for_item(item) if for_recovery else None

    return workspace_diagnostics.collect_workspace_lifecycle_diagnostic(
        repo_path=TARGET_REPO_PATH,
        workspace_path=workspace_path,
        item=inventory_item,
        watchtower_run=watchtower_run,
        allow_cleanup=False,
        dry_run=True,
    )


def _build_recovery_comment(item, recovery_resolution, *, condition_label="locked-item"):
    decision = recovery_resolution.get("decision")
    reason = recovery_resolution.get("reason")
    recommended_action = recovery_resolution.get("recommended_action")
    blockers = recovery_resolution.get("blockers") or []

    lines = [
        f"⚠️ Handler detected a {condition_label} recovery condition and stopped automatic recovery actions.",
        "",
        f"- decision: `{decision}`",
        f"- reason: `{reason}`",
        f"- non-destructive: `{recovery_resolution.get('non_destructive')}`",
    ]

    if blockers:
        lines.append("- blockers:")
        for blocker in blockers:
            lines.append(f"  - {blocker}")

    if isinstance(recommended_action, str) and recommended_action.strip():
        lines.extend(["", "Recommended human action:", recommended_action.strip()])

    lines.extend(["", "No lock labels or workflow labels were changed by Handler."])
    return "\n".join(lines)


def _build_recovery_comment_signature(recovery_resolution):
    decision = recovery_resolution.get("decision")
    reason = recovery_resolution.get("reason")
    blockers = recovery_resolution.get("blockers") or []
    normalized_blockers = [str(blocker).strip() for blocker in blockers if isinstance(blocker, str) and blocker.strip()]
    return "|".join([str(decision), str(reason), "::".join(normalized_blockers)])


def _is_duplicate_recovery_comment(item, signature):
    run_state = get_run_state(item)
    if run_state:
        status_payload = read_run_status(run_state)
        if status_payload.get("recovery_comment_signature") == signature:
            return True

    try:
        item_run_root = get_item_run_root(item)
        artifact_path = os.path.join(item_run_root, RECOVERY_DIAGNOSTIC_FILENAME)
        with open(artifact_path, "r", encoding="utf-8") as artifact_file:
            artifact_payload = json.load(artifact_file)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return False

    return artifact_payload.get("comment_signature") == signature


def _persist_locked_recovery_diagnostic_artifact(
    item,
    *,
    workspace_lifecycle,
    dependency_resolution,
    recovery_resolution,
    comment_posted,
    comment_signature,
):
    try:
        item_run_root = get_item_run_root(item)
        ensure_shared_artifacts(item_run_root)
        os.makedirs(item_run_root, exist_ok=True)
    except Exception as exc:
        print(
            f"[Watchtower] Warning: failed to prepare recovery diagnostic artifact path for "
            f"{item.get('type')} #{item.get('number')}: {exc}"
        )
        return None

    artifact_path = os.path.join(item_run_root, RECOVERY_DIAGNOSTIC_FILENAME)
    artifact_payload = {
        "recorded_at": utc_timestamp_now(),
        "item_type": item.get("type"),
        "item_number": item.get("number"),
        "item_title": item.get("title"),
        "recovery_decision": recovery_resolution.get("decision"),
        "recovery_reason": recovery_resolution.get("reason"),
        "recovery_recommendation": recovery_resolution.get("recommended_action"),
        "recovery_blockers": recovery_resolution.get("blockers") or [],
        "recovery_non_destructive": bool(recovery_resolution.get("non_destructive", True)),
        "workspace_lifecycle": workspace_lifecycle,
        "dependency_resolution": dependency_resolution,
        "comment_posted": bool(comment_posted),
        "comment_signature": comment_signature,
    }

    try:
        with open(artifact_path, "w", encoding="utf-8") as artifact_file:
            json.dump(artifact_payload, artifact_file, indent=2)
            artifact_file.write("\n")
    except OSError as exc:
        print(
            f"[Watchtower] Warning: failed to write recovery diagnostic artifact for "
            f"{item.get('type')} #{item.get('number')}: {exc}"
        )
        return None

    artifact_path_for_display = normalize_path_for_display(artifact_path)
    item["recovery_diagnostic_artifact_path"] = artifact_path_for_display
    update_run_status(item, artifacts={"recovery_diagnostic": artifact_path_for_display})
    return artifact_path_for_display


def _ensure_locked_recovery_run_artifacts(item, labels):
    if get_run_state(item):
        return

    state_labels = workflow.get_primary_workflow_state_labels(labels)
    if len(state_labels) == 1:
        state_label = state_labels[0]
    elif state_labels:
        state_label = state_labels[0]
    else:
        state_label = "state:unknown"

    config = {
        "agent": "handler",
        "mode": "diagnostic",
        "model": "n/a",
        "effort": "low",
    }

    try:
        launch_brief_path = build_launch_brief_path(item, "developer")
        launch_brief_dir = os.path.dirname(launch_brief_path)
        os.makedirs(launch_brief_dir, exist_ok=True)
        if not os.path.exists(launch_brief_path):
            with open(launch_brief_path, "w", encoding="utf-8") as launch_brief_file:
                launch_brief_file.write(
                    "# Recovery Diagnostic Launch Brief\n\n"
                    "This run was generated by Handler to persist lock recovery diagnostics.\n"
                )
        initialize_run_status(item, state_label, config, launch_brief_path)
    except OSError as exc:
        print(
            f"[Watchtower] Warning: failed to initialize recovery run artifacts for "
            f"{item.get('type')} #{item.get('number')}: {exc}"
        )


def _ensure_prelaunch_dependency_run_artifacts(item, state_label, config):
    if get_run_state(item):
        return

    try:
        launch_brief_path = build_launch_brief_path(item, config.get("mode", "developer"))
        launch_brief_dir = os.path.dirname(launch_brief_path)
        os.makedirs(launch_brief_dir, exist_ok=True)
        if not os.path.exists(launch_brief_path):
            with open(launch_brief_path, "w", encoding="utf-8") as launch_brief_file:
                launch_brief_file.write(
                    "# Dependency Recovery Diagnostic Launch Brief\n\n"
                    "This run was generated by Handler to persist dependency-blocked diagnostics.\n"
                )
        initialize_run_status(item, state_label, config, launch_brief_path)
    except OSError as exc:
        print(
            f"[Watchtower] Warning: failed to initialize dependency recovery run artifacts for "
            f"{item.get('type')} #{item.get('number')}: {exc}"
        )


def perform_locked_item_recovery(item, labels):
    current_item, current_item_ok = get_current_item(item, fields="number,labels,title,url,body")
    if not current_item_ok or not isinstance(current_item, dict):
        print(f"[Poll] Skipping {item['type']} #{item['number']}: lock label '{LOCK_LABEL}' already present.")
        return

    item.update(current_item)
    current_labels = [label["name"] for label in item.get("labels", [])]
    if not is_locked(current_labels):
        return

    workspace_lifecycle = collect_workspace_lifecycle_for_item(item, for_recovery=True)
    dependency_resolution = evaluate_item_dependencies(item)
    workflow_state = {
        "primary_state_labels": workflow.get_primary_workflow_state_labels(current_labels),
        "unsupported_state_labels": workflow.get_unsupported_state_labels(current_labels),
    }
    recovery_resolution = recovery.classify_locked_item_recovery(
        workspace_lifecycle=workspace_lifecycle,
        dependency_resolution=dependency_resolution,
        workflow_state=workflow_state,
    )
    recovery_decision = recovery_resolution["decision"]
    recovery_reason = recovery_resolution["reason"]
    recovery_recommendation = recovery_resolution.get("recommended_action")
    recovery_blockers = recovery_resolution.get("blockers") or []
    recovery_non_destructive = bool(recovery_resolution.get("non_destructive", True))

    item["workspace_lifecycle"] = workspace_lifecycle
    item["dependency_resolution"] = dependency_resolution
    item["recovery_decision"] = recovery_decision
    item["recovery_reason"] = recovery_reason
    _ensure_locked_recovery_run_artifacts(item, current_labels)
    update_run_status(
        item,
        workspace_lifecycle=workspace_lifecycle,
        dependency_resolution=dependency_resolution,
        recovery_decision=recovery_decision,
        recovery_reason=recovery_reason,
        recovery_recommendation=recovery_recommendation,
        recovery_blockers=recovery_blockers,
        recovery_non_destructive=recovery_non_destructive,
    )
    comment_required_decisions = {
        "blocked_unsafe",
        "interrupted_run_blocked",
        "dependency_resume_blocked",
        "stale_lock_needs_human",
    }
    recovery_comment_signature = _build_recovery_comment_signature(recovery_resolution)
    should_post_comment = (
        recovery_decision in comment_required_decisions
        and not _is_duplicate_recovery_comment(item, recovery_comment_signature)
    )

    if should_post_comment:
        item["comment"] = _build_recovery_comment(item, recovery_resolution)
        add_comment(item)

    update_run_status(
        item,
        recovery_comment_posted=should_post_comment,
        recovery_comment_signature=recovery_comment_signature,
    )

    _persist_locked_recovery_diagnostic_artifact(
        item,
        workspace_lifecycle=workspace_lifecycle,
        dependency_resolution=dependency_resolution,
        recovery_resolution=recovery_resolution,
        comment_posted=should_post_comment,
        comment_signature=recovery_comment_signature,
    )
    run_state = get_run_state(item)
    if isinstance(run_state, dict) and all(
        run_state.get(field) for field in ("status_path", "result_path", "launch_brief_path")
    ):
        write_run_result(item)

    print(
        f"[Poll] Skipping {item['type']} #{item['number']}: lock label '{LOCK_LABEL}' already present "
        f"({recovery_reason}); no labels were modified by recovery logic."
    )
    return


def perform_dependency_blocked_item_recovery(item, labels):
    current_item, current_item_ok = get_current_item(item, fields="number,labels,title,url,body")
    if not current_item_ok or not isinstance(current_item, dict):
        return False

    item.update(current_item)
    current_labels = [label["name"] for label in item.get("labels", [])]
    if "state:dependency-blocked" not in current_labels:
        return False

    workspace_lifecycle = collect_workspace_lifecycle_for_item(item, for_recovery=True)
    dependency_resolution = evaluate_item_dependencies(item)
    workflow_state = {
        "primary_state_labels": workflow.get_primary_workflow_state_labels(current_labels),
        "unsupported_state_labels": workflow.get_unsupported_state_labels(current_labels),
    }
    recovery_resolution = recovery.classify_locked_item_recovery(
        workspace_lifecycle=workspace_lifecycle,
        dependency_resolution=dependency_resolution,
        workflow_state=workflow_state,
    )
    recovery_decision = recovery_resolution["decision"]
    recovery_reason = recovery_resolution["reason"]
    recovery_recommendation = recovery_resolution.get("recommended_action")
    recovery_blockers = recovery_resolution.get("blockers") or []
    recovery_non_destructive = bool(recovery_resolution.get("non_destructive", True))

    item["workspace_lifecycle"] = workspace_lifecycle
    item["dependency_resolution"] = dependency_resolution
    item["recovery_decision"] = recovery_decision
    item["recovery_reason"] = recovery_reason
    diagnostic_config = {
        "agent": "handler",
        "mode": "diagnostic",
        "model": "n/a",
        "effort": "n/a",
    }
    _ensure_prelaunch_dependency_run_artifacts(item, "state:dependency-blocked", diagnostic_config)
    update_run_status(
        item,
        workspace_lifecycle=workspace_lifecycle,
        dependency_resolution=dependency_resolution,
        recovery_decision=recovery_decision,
        recovery_reason=recovery_reason,
        recovery_recommendation=recovery_recommendation,
        recovery_blockers=recovery_blockers,
        recovery_non_destructive=recovery_non_destructive,
        completed_at=utc_timestamp_now(),
        exit_code=None,
        success=False,
        outcome="dependency-blocked",
        stop_reason=recovery_reason,
    )
    comment_required_decisions = {
        "blocked_unsafe",
        "interrupted_run_blocked",
        "dependency_resume_blocked",
        "stale_lock_needs_human",
        "safe_resume",
    }
    recovery_comment_signature = _build_recovery_comment_signature(recovery_resolution)
    should_post_comment = (
        recovery_decision in comment_required_decisions
        and not _is_duplicate_recovery_comment(item, recovery_comment_signature)
    )

    if should_post_comment:
        item["comment"] = _build_recovery_comment(
            item,
            recovery_resolution,
            condition_label="dependency-blocked-item",
        )
        add_comment(item)

    update_run_status(
        item,
        recovery_comment_posted=should_post_comment,
        recovery_comment_signature=recovery_comment_signature,
    )

    _persist_locked_recovery_diagnostic_artifact(
        item,
        workspace_lifecycle=workspace_lifecycle,
        dependency_resolution=dependency_resolution,
        recovery_resolution=recovery_resolution,
        comment_posted=should_post_comment,
        comment_signature=recovery_comment_signature,
    )
    run_state = get_run_state(item)
    if isinstance(run_state, dict) and all(
        run_state.get(field) for field in ("status_path", "result_path", "launch_brief_path")
    ):
        write_run_result(item)

    print(
        f"[Poll] Skipping {item['type']} #{item['number']}: state:dependency-blocked "
        f"({recovery_reason}); no labels were modified by recovery logic."
    )
    return True


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
    dispatch_resolution = resolve_dispatch_config(current_item, current_labels)
    if dispatch_resolution and dispatch_resolution[0] == expected_state_label:
        item.update(current_item)
        return item, None

    if dispatch_resolution:
        current_state_description = repr([dispatch_resolution[0]])
    else:
        current_state_description = current_item.get("skip_reason", "unsupported workflow state")

    print(
        f"[Dispatch] Candidate {item['type']} #{item['number']} changed state after lock acquisition; "
        f"expected `{expected_state_label}`, now {current_state_description}."
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


def build_codex_implementation_planner_task_text(absolute_launch_brief_path, implementation_plan_path):
    return agents.build_codex_implementation_planner_task_text(
        absolute_launch_brief_path,
        implementation_plan_path,
    )


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


def build_thin_prompt(
    item,
    state_label,
    mode,
    role_prompt_path,
    launch_brief_path=None,
    review_result_path=None,
    implementation_plan_path=None,
):
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

    if mode == "implementation-planner":
        prompt_lines.extend(
            [
                "- implementation planner result contract: You must write `implementation-plan.md` before exiting.",
                f"- implementation plan artifact absolute path: {implementation_plan_path or '<not available>'}",
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


def build_implementation_plan_path(launch_brief_path):
    return watchtower.build_implementation_plan_path(
        launch_brief_path,
        normalize_path_for_display_fn=normalize_path_for_display,
        implementation_plan_filename=IMPLEMENTATION_PLAN_FILENAME,
    )


def parse_review_result_outcome(review_result_path):
    return workflow.parse_review_result_outcome(review_result_path)


def parse_architect_review_result_outcome(architect_review_result_path):
    return workflow.parse_architect_review_result_outcome(architect_review_result_path)


def parse_implementation_plan_outcome(implementation_plan_path):
    return workflow_classification.parse_implementation_plan_outcome(
        implementation_plan_path,
        allowed_outcomes=IMPLEMENTATION_PLAN_OUTCOMES,
    )


def validate_workflow_classification_from_markdown(markdown_path):
    classification = workflow_classification.validate_workflow_classification_file(
        markdown_path,
        valid_routes=set(LABEL_MAP.keys()),
    )
    classification["source"] = normalize_path_for_display(markdown_path) if markdown_path else None
    return classification


def parse_planner_result_v1(body):
    if not isinstance(body, str) or not body:
        return None

    for match in PLANNER_RESULT_V1_JSON_BLOCK_PATTERN.finditer(body):
        payload_text = match.group(1)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            continue

        planner_result = payload.get("planner_result_v1")
        if not isinstance(planner_result, dict):
            continue

        generated_issues = planner_result.get("generated_issues")
        if not isinstance(generated_issues, list) or not generated_issues:
            continue

        normalized_generated_issues = []
        for generated_issue in generated_issues:
            if not isinstance(generated_issue, dict):
                return None

            issue_number = generated_issue.get("issue_number")
            next_state_after_approval = generated_issue.get("next_state_after_approval")

            if not isinstance(issue_number, int) or issue_number <= 0:
                return None

            if not isinstance(next_state_after_approval, str) or not next_state_after_approval.startswith("state:"):
                return None

            if next_state_after_approval not in LABEL_MAP:
                return None

            normalized_generated_issues.append(
                {
                    "issue_number": issue_number,
                    "next_state_after_approval": next_state_after_approval,
                }
            )

        recommendation_comment_id = planner_result.get("recommendation_comment_id")
        if not isinstance(recommendation_comment_id, int) or recommendation_comment_id <= 0:
            recommendation_comment_id = None

        normalized_human_decision_ledger = human_decision_ledger.normalize_human_decision_ledger(
            planner_result.get("human_decision_ledger_v1"),
            recommendation_comment_id=recommendation_comment_id,
            generated_issue_numbers=[issue.get("issue_number") for issue in normalized_generated_issues],
            generated_issue_transition_targets=[
                issue.get("next_state_after_approval") for issue in normalized_generated_issues
            ],
        )

        return {
            "outcome": planner_result.get("outcome"),
            "parent_issue": planner_result.get("parent_issue"),
            "recommendation_comment_id": recommendation_comment_id,
            "roadmap_pr": planner_result.get("roadmap_pr"),
            "generated_issues": normalized_generated_issues,
            "human_decision_ledger_v1": normalized_human_decision_ledger,
        }

    for match in PLANNER_RESULT_V1_FENCED_BLOCK_PATTERN.finditer(body):
        planner_result = parse_planner_result_v1_yaml_block(match.group(1))
        if planner_result is not None:
            return planner_result

    return None


def parse_planner_result_from_markdown_sections(body):
    if not isinstance(body, str) or not body:
        return None

    outcome = None
    outcome_lines = watchtower._extract_markdown_section_lines(body, "outcome")
    for outcome_line in outcome_lines:
        normalized_outcome = outcome_line.strip().upper()
        if normalized_outcome in IMPLEMENTATION_PLAN_OUTCOMES:
            outcome = normalized_outcome
            break

    source_lines = watchtower._extract_markdown_section_lines(body, "source")
    source_fields = watchtower._extract_source_traceability_fields(source_lines)
    recommendation_comment_id = source_fields.get("source_recommendation_comment_id")
    roadmap_pr = watchtower._extract_pull_request_number_from_url(source_fields.get("roadmap_reference"))

    parent_issue = None
    for source_line in source_lines:
        normalized_source_line = source_line.strip()
        if not normalized_source_line:
            continue

        issue_url_match = watchtower.ISSUE_URL_PATTERN.search(normalized_source_line)
        if issue_url_match:
            parent_issue = int(issue_url_match.group(1))
            break

        issue_reference_match = watchtower.ISSUE_REFERENCE_PATTERN.search(normalized_source_line)
        if issue_reference_match:
            parent_issue = int(issue_reference_match.group(1))
            break

    generated_issue_lines = watchtower._extract_markdown_section_lines(body, "generated issues")
    generated_issue_blocks = watchtower._parse_generated_issue_blocks(generated_issue_lines)

    normalized_generated_issues = []
    for generated_issue_block in generated_issue_blocks:
        issue_number = generated_issue_block.get("number")
        if not isinstance(issue_number, int) or issue_number <= 0:
            continue

        next_state_after_approval = None
        for generated_issue_line in generated_issue_block.get("lines", []):
            normalized_generated_issue_line = generated_issue_line.strip().lower()
            has_explicit_next_state_marker = (
                "next workflow state after human approval" in normalized_generated_issue_line
                or "suggested next workflow state after human approval" in normalized_generated_issue_line
            )
            has_compact_next_state_format = bool(
                re.search(r"^[-*+]?\s*#?\d+\s*[—-]\s*state:[a-z0-9-]+", normalized_generated_issue_line)
            )
            if not has_explicit_next_state_marker and not has_compact_next_state_format:
                continue

            next_state_match = STATE_LABEL_PATTERN.search(generated_issue_line)
            if not next_state_match:
                continue

            candidate_next_state_after_approval = next_state_match.group(1).lower()
            if candidate_next_state_after_approval not in LABEL_MAP:
                continue

            next_state_after_approval = candidate_next_state_after_approval
            break

        if not isinstance(next_state_after_approval, str):
            continue

        normalized_generated_issues.append(
            {
                "issue_number": issue_number,
                "next_state_after_approval": next_state_after_approval,
            }
        )

    if (
        outcome is None
        and parent_issue is None
        and recommendation_comment_id is None
        and roadmap_pr is None
        and not normalized_generated_issues
    ):
        return None

    return {
        "outcome": outcome,
        "parent_issue": parent_issue,
        "recommendation_comment_id": recommendation_comment_id,
        "roadmap_pr": roadmap_pr,
        "generated_issues": normalized_generated_issues,
        "human_decision_ledger_v1": human_decision_ledger.normalize_human_decision_ledger(
            None,
            recommendation_comment_id=recommendation_comment_id,
            generated_issue_numbers=[issue.get("issue_number") for issue in normalized_generated_issues],
            generated_issue_transition_targets=[
                issue.get("next_state_after_approval") for issue in normalized_generated_issues
            ],
        ),
    }


def _parse_yaml_scalar_value(raw_value):
    if raw_value is None:
        return None

    stripped_value = raw_value.strip()
    if not stripped_value:
        return ""

    if (
        len(stripped_value) >= 2
        and stripped_value[0] == stripped_value[-1]
        and stripped_value[0] in {'"', "'"}
    ):
        stripped_value = stripped_value[1:-1]

    if re.fullmatch(r"-?\d+", stripped_value):
        return int(stripped_value)

    return stripped_value


def _is_yaml_inline_mapping(value):
    if not isinstance(value, str):
        return False

    stripped_value = value.strip()
    return (
        re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:\s", stripped_value) is not None
        or re.match(r"^[A-Za-z0-9_][A-Za-z0-9_-]*\s*:$", stripped_value) is not None
    )


def _next_yaml_non_empty_line(lines, index):
    while index < len(lines):
        candidate = lines[index]
        if candidate.strip():
            return index, candidate
        index += 1

    return None, None


def _parse_yaml_nested_list(lines, *, start_index, parent_indent):
    values = []
    index = start_index

    while index < len(lines):
        item_index, item_line = _next_yaml_non_empty_line(lines, index)
        if item_index is None:
            return values, len(lines)

        item_indent = len(item_line) - len(item_line.lstrip(" "))
        if item_indent <= parent_indent:
            return values, item_index

        stripped_item_line = item_line.strip()
        if not stripped_item_line.startswith("-"):
            return None, None

        item_payload = stripped_item_line[1:].strip()
        index = item_index + 1

        if not item_payload:
            nested_value, next_index = _parse_yaml_nested_value(lines, start_index=index, parent_indent=item_indent)
            if nested_value is None:
                values.append("")
                continue

            values.append(nested_value)
            index = next_index
            continue

        if _is_yaml_inline_mapping(item_payload):
            nested_key, nested_value = item_payload.split(":", 1)
            item_mapping = {nested_key.strip(): _parse_yaml_scalar_value(nested_value)}

            while index < len(lines):
                field_index, field_line = _next_yaml_non_empty_line(lines, index)
                if field_index is None:
                    values.append(item_mapping)
                    return values, len(lines)

                field_indent = len(field_line) - len(field_line.lstrip(" "))
                if field_indent <= item_indent:
                    break

                stripped_field_line = field_line.strip()
                if ":" not in stripped_field_line:
                    return None, None

                field_key, field_value = stripped_field_line.split(":", 1)
                normalized_field_key = field_key.strip()
                if field_value.strip():
                    item_mapping[normalized_field_key] = _parse_yaml_scalar_value(field_value)
                    index = field_index + 1
                    continue

                nested_field_value, next_index = _parse_yaml_nested_value(
                    lines,
                    start_index=field_index + 1,
                    parent_indent=field_indent,
                )
                item_mapping[normalized_field_key] = nested_field_value if nested_field_value is not None else []
                index = next_index if next_index is not None else field_index + 1

            values.append(item_mapping)
            continue

        values.append(_parse_yaml_scalar_value(item_payload))

    return values, index


def _parse_yaml_nested_value(lines, *, start_index, parent_indent):
    next_index, next_line = _next_yaml_non_empty_line(lines, start_index)
    if next_index is None:
        return None, len(lines)

    next_indent = len(next_line) - len(next_line.lstrip(" "))
    if next_indent <= parent_indent:
        return None, next_index

    if next_line.strip().startswith("-"):
        return _parse_yaml_nested_list(lines, start_index=next_index, parent_indent=parent_indent)

    return _parse_yaml_nested_mapping(lines, start_index=next_index, parent_indent=parent_indent)


def _parse_yaml_nested_mapping(lines, *, start_index, parent_indent):
    nested_fields = {}
    index = start_index

    while index < len(lines):
        nested_index, nested_line = _next_yaml_non_empty_line(lines, index)
        if nested_index is None:
            return nested_fields, len(lines)

        stripped_nested_line = nested_line.strip()
        nested_indent = len(nested_line) - len(nested_line.lstrip(" "))
        if nested_indent <= parent_indent:
            return nested_fields, nested_index

        if ":" not in stripped_nested_line:
            return None, None

        nested_key, nested_value = stripped_nested_line.split(":", 1)
        normalized_nested_key = nested_key.strip()
        if nested_value.strip():
            nested_fields[normalized_nested_key] = _parse_yaml_scalar_value(nested_value)
            index = nested_index + 1
            continue

        nested_fields_value, next_index = _parse_yaml_nested_value(
            lines,
            start_index=nested_index + 1,
            parent_indent=nested_indent,
        )
        nested_fields[normalized_nested_key] = nested_fields_value if nested_fields_value is not None else []
        index = next_index if next_index is not None else nested_index + 1

    return nested_fields, len(lines)


def parse_planner_result_v1_yaml_block(block_text):
    if not isinstance(block_text, str) or not block_text:
        return None

    lines = block_text.splitlines()
    root_index = None
    root_indent = 0
    for index, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue

        if stripped_line == "planner_result_v1:":
            root_index = index
            root_indent = len(line) - len(line.lstrip(" "))
            break

    if root_index is None:
        return None

    planner_fields = {}
    generated_issues = []
    index = root_index + 1
    while index < len(lines):
        line = lines[index]
        stripped_line = line.strip()
        if not stripped_line:
            index += 1
            continue

        indent = len(line) - len(line.lstrip(" "))
        if indent <= root_indent:
            break

        if stripped_line == "generated_issues:":
            index += 1
            while index < len(lines):
                issue_line = lines[index]
                issue_stripped_line = issue_line.strip()
                if not issue_stripped_line:
                    index += 1
                    continue

                issue_indent = len(issue_line) - len(issue_line.lstrip(" "))
                if issue_indent <= indent:
                    break

                if not issue_stripped_line.startswith("- "):
                    return None

                issue_entry = {}
                issue_payload = issue_stripped_line[2:].strip()
                if issue_payload:
                    if ":" not in issue_payload:
                        return None
                    first_key, first_value = issue_payload.split(":", 1)
                    issue_entry[first_key.strip()] = _parse_yaml_scalar_value(first_value)

                index += 1
                while index < len(lines):
                    issue_field_line = lines[index]
                    issue_field_stripped_line = issue_field_line.strip()
                    if not issue_field_stripped_line:
                        index += 1
                        continue

                    issue_field_indent = len(issue_field_line) - len(issue_field_line.lstrip(" "))
                    if issue_field_indent <= issue_indent:
                        break

                    if ":" not in issue_field_stripped_line:
                        return None

                    issue_key, issue_value = issue_field_stripped_line.split(":", 1)
                    issue_entry[issue_key.strip()] = _parse_yaml_scalar_value(issue_value)
                    index += 1

                generated_issues.append(issue_entry)

            continue

        if ":" not in stripped_line:
            return None

        field_key, field_value = stripped_line.split(":", 1)
        normalized_field_key = field_key.strip()
        if normalized_field_key == "human_decision_ledger_v1" and not field_value.strip():
            nested_fields, next_index = _parse_yaml_nested_mapping(lines, start_index=index + 1, parent_indent=indent)
            if nested_fields is None:
                return None

            planner_fields[normalized_field_key] = nested_fields
            index = next_index
            continue

        planner_fields[normalized_field_key] = _parse_yaml_scalar_value(field_value)
        index += 1

    if not generated_issues:
        return None

    normalized_generated_issues = []
    for generated_issue in generated_issues:
        if not isinstance(generated_issue, dict):
            return None

        issue_number = generated_issue.get("issue_number")
        if issue_number is None:
            issue_number = generated_issue.get("number")

        initial_state = generated_issue.get("initial_state")
        next_state_after_approval = generated_issue.get("next_state_after_approval")

        if not isinstance(issue_number, int) or issue_number <= 0:
            return None

        if not isinstance(next_state_after_approval, str) or not next_state_after_approval.startswith("state:"):
            return None

        if next_state_after_approval not in LABEL_MAP:
            return None

        normalized_generated_issues.append(
            {
                "issue_number": issue_number,
                "initial_state": initial_state,
                "next_state_after_approval": next_state_after_approval,
            }
        )

    return {
        "outcome": planner_fields.get("outcome"),
        "parent_issue": planner_fields.get("parent_issue"),
        "recommendation_comment_id": planner_fields.get("recommendation_comment_id"),
        "roadmap_pr": planner_fields.get("roadmap_pr"),
        "generated_issues": normalized_generated_issues,
        "human_decision_ledger_v1": human_decision_ledger.normalize_human_decision_ledger(
            planner_fields.get("human_decision_ledger_v1"),
            recommendation_comment_id=planner_fields.get("recommendation_comment_id"),
            generated_issue_numbers=[issue.get("issue_number") for issue in normalized_generated_issues],
            generated_issue_transition_targets=[
                issue.get("next_state_after_approval") for issue in normalized_generated_issues
            ],
        ),
    }


def _extract_comment_id(comment):
    if not isinstance(comment, dict):
        return None

    for candidate_key in ("id", "databaseId"):
        candidate_value = comment.get(candidate_key)
        if isinstance(candidate_value, int):
            return candidate_value
        if isinstance(candidate_value, str) and candidate_value.strip().isdigit():
            return int(candidate_value.strip())

    for candidate_key in ("url", "html_url"):
        candidate_value = comment.get(candidate_key)
        if not isinstance(candidate_value, str):
            continue

        match = re.search(r"#issuecomment-(\d+)(?:$|\D)", candidate_value)
        if match is not None:
            return int(match.group(1))

    return None


def extract_latest_planner_result_v1_metadata(comments):
    if not isinstance(comments, list):
        return None

    candidate_results = []
    for comment in comments:
        if not isinstance(comment, dict):
            continue

        comment_body = comment.get("body")
        planner_result = parse_planner_result_v1(comment_body)
        if planner_result is None:
            planner_result = parse_planner_result_from_markdown_sections(comment_body)
        if planner_result is None:
            continue

        candidate_results.append(
            {
                "planner_result": planner_result,
                "planner_result_comment_id": _extract_comment_id(comment),
                "planner_result_comment_url": comment.get("url") if isinstance(comment.get("url"), str) else None,
            }
        )

    if not candidate_results:
        return None

    return candidate_results[-1]


def _label_names(item):
    return [label.get("name") for label in item.get("labels", []) if isinstance(label, dict)]


def _validate_single_primary_state(item, expected_state, item_kind):
    label_names = _label_names(item)
    state_labels = workflow.get_state_labels(label_names)
    if len(state_labels) != 1:
        print(
            f"[Approval] {item_kind} #{item['number']} must have exactly one primary workflow state label; "
            f"found {len(state_labels)}."
        )
        return False

    if state_labels[0] != expected_state:
        print(
            f"[Approval] {item_kind} #{item['number']} must be in '{expected_state}' before approval "
            f"(found '{state_labels[0]}')."
        )
        return False

    return True


def _is_open_unlocked(item):
    if item.get("closed") is True:
        return False

    state_value = item.get("state")
    if isinstance(state_value, str) and state_value.lower() != "open":
        return False

    label_names = _label_names(item)
    if workflow.is_locked(label_names):
        return False

    return True


def _contains_traceability(body_text, source_issue_number, recommendation_comment_id, roadmap_pr, next_state):
    if not isinstance(body_text, str) or not body_text:
        return False

    if f"#{source_issue_number}" not in body_text:
        return False

    if str(recommendation_comment_id) not in body_text:
        return False

    if f"#{roadmap_pr}" not in body_text:
        return False

    if next_state not in body_text:
        return False

    return True


def _add_source_audit_comment(source_issue_number, audit_lines):
    return add_comment(
        {
            "type": "issue",
            "number": source_issue_number,
            "comment": "\n".join(audit_lines),
        }
    )


def _report_approval_failure(source_issue_number, reason, transitioned_issue_numbers):
    audit_lines = [
        "Implementation-plan approval failed.",
        f"- Source issue: #{source_issue_number}",
        f"- Reason: {reason}",
    ]

    if transitioned_issue_numbers:
        audit_lines.append(
            "- Generated issues transitioned before failure: "
            + ", ".join(f"#{issue_number}" for issue_number in transitioned_issue_numbers)
        )

    if not _add_source_audit_comment(source_issue_number, audit_lines):
        print(f"[Approval] Failed to record failure audit comment on source issue #{source_issue_number}.")


def approve_implementation_plan_review(source_issue_number, plan_comment_id=None, dry_run=False):
    if plan_comment_id is not None and (not isinstance(plan_comment_id, int) or plan_comment_id <= 0):
        print("[Approval] The --approve-implementation-plan-comment-id value must be a positive integer.")
        return False

    source_item, source_ok = github_client.get_item(
        "issue",
        source_issue_number,
        repo=REPO,
        run_command_fn=run_command,
        fields="number,labels,title,url,comments,state,closed",
    )
    if not source_ok or source_item is None:
        print(f"[Approval] Failed to load source issue #{source_issue_number}.")
        return False

    source_item["type"] = "issue"
    if not _is_open_unlocked(source_item):
        print(f"[Approval] Source issue #{source_issue_number} must be open and unlocked before approval.")
        return False

    if not _validate_single_primary_state(source_item, IMPLEMENTATION_PLAN_REVIEW_LABEL, "Source issue"):
        return False

    candidate_results = []
    for comment in source_item.get("comments", []):
        if not isinstance(comment, dict):
            continue

        comment_identifier = _extract_comment_id(comment)
        if plan_comment_id is not None and comment_identifier != plan_comment_id:
            continue

        comment_body = comment.get("body")
        planner_result = parse_planner_result_v1(comment_body)
        if planner_result is None:
            planner_result = parse_planner_result_from_markdown_sections(comment_body)
        if planner_result is None:
            continue

        candidate_results.append((comment_identifier, planner_result))

    if not candidate_results:
        if plan_comment_id is None:
            print(f"[Approval] Issue #{source_issue_number} is missing valid planner metadata.")
        else:
            print(
                f"[Approval] Issue #{source_issue_number} is missing valid planner metadata in "
                f"comment id {plan_comment_id}."
            )
        return False

    if plan_comment_id is None and len(candidate_results) > 1:
        print(
            f"[Approval] Issue #{source_issue_number} has multiple planner metadata candidates; "
            "specify --approve-implementation-plan-comment-id explicitly."
        )
        return False

    selected_comment_id, planner_result = candidate_results[-1]
    outcome = planner_result.get("outcome")
    parent_issue = planner_result.get("parent_issue")
    recommendation_comment_id = planner_result.get("recommendation_comment_id")
    roadmap_pr = planner_result.get("roadmap_pr")
    normalized_human_decision_ledger = human_decision_ledger.normalize_human_decision_ledger(
        planner_result.get("human_decision_ledger_v1"),
        recommendation_comment_id=recommendation_comment_id,
        generated_issue_numbers=[
            generated_issue.get("issue_number")
            for generated_issue in planner_result.get("generated_issues", [])
            if isinstance(generated_issue, dict)
        ],
        generated_issue_transition_targets=[
            generated_issue.get("next_state_after_approval")
            for generated_issue in planner_result.get("generated_issues", [])
            if isinstance(generated_issue, dict)
        ],
    )

    if normalized_human_decision_ledger.get("status") != "available":
        print(
            "[Approval] planner_result_v1 human_decision_ledger_v1 must be available before approval "
            f"(found: {normalized_human_decision_ledger.get('status')!r})."
        )
        return False

    decision_type = normalized_human_decision_ledger.get("decision_type")
    if decision_type not in IMPLEMENTATION_PLAN_APPROVAL_DECISION_TYPES:
        print(
            "[Approval] planner_result_v1 human_decision_ledger_v1 decision_type must be one of "
            f"{sorted(IMPLEMENTATION_PLAN_APPROVAL_DECISION_TYPES)!r} before approval "
            f"(found: {decision_type!r})."
        )
        return False

    stale_check_status = normalized_human_decision_ledger.get("stale_check", {}).get("status")
    if not human_decision_ledger.is_dispatch_approval_stale_check_fresh(
        normalized_human_decision_ledger,
        recommendation_comment_id=recommendation_comment_id,
        roadmap_pr=roadmap_pr,
    ):
        print(
            "[Approval] planner_result_v1 human_decision_ledger_v1 stale_check.status must be "
            f"'fresh' before approval (found: {stale_check_status!r})."
        )
        return False

    if outcome != "READY":
        print(f"[Approval] planner_result_v1 outcome must be READY before approval (found: {outcome!r}).")
        return False

    if parent_issue != source_issue_number:
        print(
            f"[Approval] planner_result_v1 parent_issue must equal source issue #{source_issue_number} "
            f"(found: {parent_issue!r})."
        )
        return False

    if not isinstance(recommendation_comment_id, int) or recommendation_comment_id <= 0:
        print("[Approval] planner_result_v1 recommendation_comment_id must be a positive integer.")
        return False

    if not isinstance(roadmap_pr, int) or roadmap_pr <= 0:
        print("[Approval] planner_result_v1 roadmap_pr must be a positive integer.")
        return False

    recommendation_comment_found = any(
        _extract_comment_id(comment) == recommendation_comment_id
        for comment in source_item.get("comments", [])
        if isinstance(comment, dict)
    )
    if not recommendation_comment_found:
        print(
            f"[Approval] recommendation_comment_id {recommendation_comment_id} was not found on source issue "
            f"#{source_issue_number}."
        )
        return False

    roadmap_item, roadmap_ok = github_client.get_item(
        "pr",
        roadmap_pr,
        repo=REPO,
        run_command_fn=run_command,
        fields="number,state,mergedAt,title,url",
    )
    if not roadmap_ok or roadmap_item is None:
        print(f"[Approval] Failed to load roadmap PR #{roadmap_pr}.")
        return False

    if not roadmap_item.get("mergedAt"):
        print(f"[Approval] Roadmap PR #{roadmap_pr} must be merged before approval.")
        return False

    transitioned_issue_numbers = []

    def _fail(reason):
        print(reason)
        if not dry_run:
            _report_approval_failure(source_issue_number, reason, transitioned_issue_numbers)
        return False

    planner_generated_issues = planner_result.get("generated_issues")
    if not isinstance(planner_generated_issues, list) or not planner_generated_issues:
        print("[Approval] planner_result_v1 generated_issues must contain at least one issue for READY approval.")
        return False

    generated_issues = []
    for generated_issue in planner_generated_issues:
        generated_issue_number = generated_issue["issue_number"]
        initial_state = generated_issue.get("initial_state")
        target_state = generated_issue["next_state_after_approval"]

        if initial_state is not None and initial_state != PLANNED_LABEL:
            print(
                f"[Approval] Generated issue #{generated_issue_number} has unsupported initial_state "
                f"{initial_state!r}; expected '{PLANNED_LABEL}'."
            )
            return False

        if workflow.is_human_owned_state_label(target_state):
            print(
                f"[Approval] Generated issue #{generated_issue_number} target state '{target_state}' is human-owned "
                "and not dispatchable."
            )
            return False

        if target_state not in LABEL_MAP:
            print(
                f"[Approval] Generated issue #{generated_issue_number} target state '{target_state}' is not "
                "a supported dispatch workflow state."
            )
            return False

        generated_item, generated_ok = github_client.get_item(
            "issue",
            generated_issue_number,
            repo=REPO,
            run_command_fn=run_command,
            fields="number,labels,title,url,state,closed,body",
        )
        if not generated_ok or generated_item is None:
            return _fail(f"[Approval] Failed to load generated issue #{generated_issue_number}.")

        generated_item["type"] = "issue"
        if not _is_open_unlocked(generated_item):
            return _fail(
                f"[Approval] Generated issue #{generated_issue_number} must be open and unlocked before approval."
            )

        if not _validate_single_primary_state(generated_item, PLANNED_LABEL, "Generated issue"):
            return _fail(
                f"[Approval] Generated issue #{generated_issue_number} must be in '{PLANNED_LABEL}' with exactly "
                "one primary state label before approval."
            )

        if not _contains_traceability(
            generated_item.get("body"),
            source_issue_number,
            recommendation_comment_id,
            roadmap_pr,
            target_state,
        ):
            return _fail(
                f"[Approval] Generated issue #{generated_issue_number} is missing required traceability markers "
                "(source issue, recommendation comment id, roadmap PR, and next state)."
            )

        generated_issues.append((generated_item, target_state))

    if dry_run:
        print(f"[Approval] Dry run: validation succeeded for source issue #{source_issue_number}.")
        return True

    for generated_item, target_state in generated_issues:
        generated_issue_number = generated_item["number"]
        if not github_client.replace_label(
            generated_item,
            remove_label_value=PLANNED_LABEL,
            add_label_value=target_state,
            repo=REPO,
            run_command_fn=run_command,
        ):
            return _fail(
                f"[Approval] Failed to transition generated issue #{generated_issue_number} to '{target_state}'."
            )

        refreshed_generated_item, refreshed_generated_ok = github_client.get_item(
            "issue",
            generated_issue_number,
            repo=REPO,
            run_command_fn=run_command,
            fields="number,labels,state,closed",
        )
        if not refreshed_generated_ok or refreshed_generated_item is None:
            return _fail(
                f"[Approval] Failed to reload generated issue #{generated_issue_number} after transition."
            )

        refreshed_generated_item["type"] = "issue"
        if not _validate_single_primary_state(refreshed_generated_item, target_state, "Generated issue"):
            return _fail(
                f"[Approval] Generated issue #{generated_issue_number} did not keep exactly one primary state "
                f"'{target_state}' after transition."
            )

        transitioned_issue_numbers.append(generated_issue_number)

    audit_lines = [
        "Implementation-plan approval executed.",
        f"- Source issue: #{source_issue_number}",
        f"- Planner result comment id: {selected_comment_id}",
        f"- Recommendation comment id: {recommendation_comment_id}",
        f"- Roadmap PR: #{roadmap_pr}",
        f"- Transitioned generated issues: {', '.join(f'#{issue_number}' for issue_number in transitioned_issue_numbers)}",
        "",
        "Human decision ledger artifact:",
    ]
    audit_lines.extend(
        human_decision_ledger.render_human_decision_ledger_markdown_block(normalized_human_decision_ledger)
    )
    if not _add_source_audit_comment(source_issue_number, audit_lines):
        print(f"[Approval] Failed to record approval audit comment on source issue #{source_issue_number}.")
        return False

    if not github_client.replace_label(
        source_item,
        remove_label_value=IMPLEMENTATION_PLAN_REVIEW_LABEL,
        add_label_value=HUMAN_REVIEW_LABEL,
        repo=REPO,
        run_command_fn=run_command,
    ):
        return _fail(
            f"[Approval] Failed to transition source issue #{source_issue_number} to '{HUMAN_REVIEW_LABEL}'."
        )

    refreshed_source_item, refreshed_source_ok = github_client.get_item(
        "issue",
        source_issue_number,
        repo=REPO,
        run_command_fn=run_command,
        fields="number,labels,state,closed",
    )
    if not refreshed_source_ok or refreshed_source_item is None:
        return _fail(f"[Approval] Failed to reload source issue #{source_issue_number} after transition.")

    refreshed_source_item["type"] = "issue"
    if not _validate_single_primary_state(refreshed_source_item, HUMAN_REVIEW_LABEL, "Source issue"):
        return _fail(
            f"[Approval] Source issue #{source_issue_number} did not keep exactly one primary state "
            f"'{HUMAN_REVIEW_LABEL}' after transition."
        )

    print(f"[Approval] Source issue #{source_issue_number} transitioned to '{HUMAN_REVIEW_LABEL}'.")
    return True


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
    implementation_plan_path=None,
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
        implementation_plan_path=implementation_plan_path,
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
        build_implementation_plan_path_fn=build_implementation_plan_path,
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
    implementation_plan_path_for_prompt = None
    if mode == "reviewer":
        reviewer_result_path_for_prompt = build_reviewer_result_path(launch_brief_path)
    if mode == "architect-review":
        reviewer_result_path_for_prompt = build_architect_review_result_path(launch_brief_path)
    if mode == "implementation-planner":
        implementation_plan_path_for_prompt = build_implementation_plan_path(launch_brief_path)
    thin_prompt = build_thin_prompt(
        item,
        state_label,
        mode,
        role_prompt_path,
        launch_brief_path,
        review_result_path=reviewer_result_path_for_prompt,
        implementation_plan_path=implementation_plan_path_for_prompt,
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
            codex_task_text = build_codex_implementation_planner_task_text(
                absolute_launch_brief_path,
                implementation_plan_path_for_prompt or "<not available>",
            )
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
                launch_run_dir = os.path.dirname(launch_brief_path)
                item_run_root = os.path.dirname(launch_run_dir)
                architecture_handoff_path = normalize_path_for_display(
                    os.path.join(item_run_root, "shared", "architecture-handoff.md")
                )
                workflow_classification_snapshot = validate_workflow_classification_from_markdown(architecture_handoff_path)
                if workflow_classification_snapshot.get("status") == "malformed":
                    item["comment"] = (
                        "⚠️ Optional `workflow_classification` block in architecture handoff was malformed.\n\n"
                        f"Artifact: `{normalize_path_for_display(architecture_handoff_path)}`\n\n"
                        "Routing and label transitions were not changed. "
                        f"Diagnostic: {workflow_classification_snapshot.get('diagnostic')}"
                    )
                    add_comment(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=0,
                    success=advanced,
                    outcome="architect handoff generated",
                    stop_reason=None if advanced else "label transition failed",
                    artifacts={"architecture_handoff": normalize_path_for_display(architecture_handoff_path)},
                    workflow_classification=workflow_classification_snapshot,
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
                    recommendation_traceability=watchtower.build_unavailable_recommendation_traceability_snapshot(
                        source_issue=item.get("number"),
                        source="systems-architect",
                        diagnostic="not yet accepted",
                    ),
                )
                write_run_result(item)
                return advanced
            elif mode == "roadmap-updater":
                validated = validate_roadmap_updater_open_pull_request(item)
                advanced = validated
                if validated:
                    advanced = advance_roadmap_update_workflow_on_success(item, from_state_label=state_label)

                recommendation_traceability = watchtower.build_unavailable_recommendation_traceability_snapshot(
                    source_issue=item.get("number"),
                    roadmap_reference=item.get("roadmap_pr"),
                    source="roadmap-updater",
                    diagnostic="accepted recommendation unavailable",
                )
                current_issue, current_issue_ok = get_current_item(item, fields="number,comments")
                if current_issue_ok and isinstance(current_issue, dict):
                    recommendation_traceability = watchtower.extract_issue_comment_recommendation_traceability(
                        current_issue.get("comments"),
                        source_issue=item.get("number"),
                        roadmap_reference=item.get("roadmap_pr"),
                        source="roadmap-updater",
                    )

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
                    recommendation_traceability=recommendation_traceability,
                )
                write_run_result(item)
                return advanced
            elif mode == "implementation-planner" and state_label in implementation_planner_state_labels:
                implementation_plan_path = build_implementation_plan_path(launch_brief_path)
                workflow_classification_snapshot = validate_workflow_classification_from_markdown(implementation_plan_path)
                planner_comments = item.get("comments") if isinstance(item.get("comments"), list) else None
                try:
                    current_issue, current_issue_ok = get_current_item(item, fields="number,comments")
                except Exception as refresh_error:
                    current_issue = None
                    current_issue_ok = False
                    print(
                        "[Dispatch] Warning: unable to refresh implementation planner comments for "
                        f"{item['type']} #{number}: {refresh_error}"
                    )

                if current_issue_ok and isinstance(current_issue, dict):
                    current_issue_comments = current_issue.get("comments")
                    if isinstance(current_issue_comments, list):
                        planner_comments = current_issue_comments
                        item["comments"] = current_issue_comments

                planner_result_metadata = extract_latest_planner_result_v1_metadata(planner_comments)
                planner_result = (
                    planner_result_metadata.get("planner_result")
                    if isinstance(planner_result_metadata, dict)
                    else None
                )
                planner_result_generated_issues = (
                    planner_result.get("generated_issues")
                    if isinstance(planner_result, dict) and isinstance(planner_result.get("generated_issues"), list)
                    else None
                )
                planner_result_parent_issue = (
                    planner_result.get("parent_issue")
                    if isinstance(planner_result, dict) and isinstance(planner_result.get("parent_issue"), int)
                    else None
                )
                planner_result_recommendation_comment_id = (
                    planner_result.get("recommendation_comment_id")
                    if isinstance(planner_result, dict)
                    and isinstance(planner_result.get("recommendation_comment_id"), int)
                    else None
                )
                planner_result_roadmap_pr = (
                    planner_result.get("roadmap_pr")
                    if isinstance(planner_result, dict) and isinstance(planner_result.get("roadmap_pr"), int)
                    else None
                )
                planner_result_human_decision_ledger = (
                    planner_result.get("human_decision_ledger_v1") if isinstance(planner_result, dict) else None
                )
                planner_result_comment_id = (
                    planner_result_metadata.get("planner_result_comment_id")
                    if isinstance(planner_result_metadata, dict)
                    and isinstance(planner_result_metadata.get("planner_result_comment_id"), int)
                    else None
                )
                planner_result_comment_url = (
                    planner_result_metadata.get("planner_result_comment_url")
                    if isinstance(planner_result_metadata, dict)
                    and isinstance(planner_result_metadata.get("planner_result_comment_url"), str)
                    else None
                )
                roadmap_reference_merged = None
                if isinstance(planner_result_roadmap_pr, int) and planner_result_roadmap_pr > 0:
                    roadmap_item, roadmap_ok = github_client.get_item(
                        "pr",
                        planner_result_roadmap_pr,
                        repo=REPO,
                        run_command_fn=run_command,
                        fields="number,mergedAt",
                    )
                    if roadmap_ok and isinstance(roadmap_item, dict):
                        roadmap_reference_merged = bool(roadmap_item.get("mergedAt"))

                if not os.path.isfile(implementation_plan_path):
                    normalized_implementation_plan_path = normalize_path_for_display(implementation_plan_path)
                    print(
                        f"[Dispatch] Codex exited 0 but missing required implementation plan artifact at "
                        f"{normalized_implementation_plan_path}."
                    )
                    item["comment"] = (
                        "⚠️ Implementation planner run completed but the required artifact was not produced.\n\n"
                        f"Expected file: `{normalized_implementation_plan_path}`\n\n"
                        "Please rerun implementation planning and ensure `implementation-plan.md` is written "
                        "before advancing the workflow."
                    )
                    item["missing_implementation_plan_artifact"] = True
                    add_comment(item)
                    missing_artifact_snapshot = watchtower.build_implementation_planner_snapshot(
                        normalized_implementation_plan_path,
                        outcome=None,
                        outcome_valid=False,
                        diagnostic=(
                            f"missing implementation plan artifact at {normalized_implementation_plan_path}"
                        ),
                        planner_result_comment_id=planner_result_comment_id,
                        planner_result_comment_url=planner_result_comment_url,
                        parent_issue=planner_result_parent_issue,
                        recommendation_comment_id=planner_result_recommendation_comment_id,
                        roadmap_pr_number=planner_result_roadmap_pr,
                        roadmap_reference_merged=roadmap_reference_merged,
                        generated_issues=planner_result_generated_issues,
                        human_decision_ledger_v1=planner_result_human_decision_ledger,
                    )
                    update_run_status(
                        item,
                        completed_at=utc_timestamp_now(),
                        exit_code=0,
                        success=False,
                        outcome="missing result artifact",
                        stop_reason=f"missing implementation plan artifact at {normalized_implementation_plan_path}",
                        artifacts={"implementation_plan": normalized_implementation_plan_path},
                        implementation_planner=missing_artifact_snapshot,
                        workflow_classification=workflow_classification_snapshot,
                        recommendation_traceability=watchtower.build_implementation_planner_recommendation_traceability_snapshot(
                            missing_artifact_snapshot,
                            source_issue=item.get("number"),
                        ),
                    )
                    write_run_result(item)
                    return False

                implementation_plan_outcome = parse_implementation_plan_outcome(implementation_plan_path)
                if implementation_plan_outcome != "READY":
                    normalized_implementation_plan_path = normalize_path_for_display(implementation_plan_path)
                    outcome_name = "not ready for advancement"
                    stop_reason = (
                        f"implementation plan outcome `{implementation_plan_outcome}` does not permit advancement"
                    )
                    artifacts = {
                        "implementation_plan": normalized_implementation_plan_path,
                        "implementation_plan_outcome": implementation_plan_outcome,
                    }
                    implementation_planner_diagnostic = None
                    recommended_route = None
                    classification_diagnostic_comment = None
                    if workflow_classification_snapshot.get("status") == "malformed":
                        classification_diagnostic_comment = (
                            "⚠️ Optional `workflow_classification` block in `implementation-plan.md` was malformed.\n\n"
                            "Routing and label transitions were not changed. "
                            f"Diagnostic: {workflow_classification_snapshot.get('diagnostic')}"
                        )

                    if implementation_plan_outcome is None:
                        outcome_name = "invalid result artifact"
                        stop_reason = (
                            "implementation plan outcome missing or invalid; expected exactly one "
                            "`### Outcome` marker with READY, BLOCKED, or ESCALATION_REQUIRED"
                        )
                        implementation_planner_diagnostic = stop_reason
                        print(
                            "[Dispatch] Implementation planner outcome was missing or invalid; "
                            "workflow will not advance."
                        )
                        item["comment"] = (
                            "⚠️ Implementation planner run completed but `implementation-plan.md` did not include "
                            "a valid outcome declaration.\n\n"
                            f"Expected file: `{normalized_implementation_plan_path}`\n\n"
                            "The `### Outcome` section must declare exactly one of `READY`, `BLOCKED`, or "
                            "`ESCALATION_REQUIRED`. The workflow remains in implementation planning."
                        )
                        item["invalid_implementation_plan_outcome"] = True
                    elif implementation_plan_outcome == "BLOCKED":
                        outcome_name = "blocked planning outcome"
                        stop_reason = "implementation planner reported BLOCKED outcome"
                        print(
                            "[Dispatch] Implementation planner reported BLOCKED outcome; "
                            "workflow remains in implementation planning."
                        )
                        item["comment"] = (
                            "⚠️ Implementation planner run completed with a blocked outcome.\n\n"
                            f"Outcome: `{implementation_plan_outcome}`\n"
                            f"Artifact: `{normalized_implementation_plan_path}`\n\n"
                            "Handler did not advance labels because blocked planning outcomes require human "
                            "follow-up before implementation-plan review can proceed."
                        )
                        item.pop("invalid_implementation_plan_outcome", None)
                    elif implementation_plan_outcome == "ESCALATION_REQUIRED":
                        outcome_name = "escalation required"
                        stop_reason = (
                            "implementation planner reported ESCALATION_REQUIRED outcome; "
                            "recommended route: state:systems-architecture-changes-requested"
                        )
                        artifacts["recommended_route"] = "state:systems-architecture-changes-requested"
                        recommended_route = "state:systems-architecture-changes-requested"
                        print(
                            "[Dispatch] Implementation planner reported ESCALATION_REQUIRED outcome; "
                            "recommended human route: state:systems-architecture-changes-requested."
                        )
                        item["comment"] = (
                            "⚠️ Implementation planner run completed with `ESCALATION_REQUIRED`.\n\n"
                            f"Outcome: `{implementation_plan_outcome}`\n"
                            f"Artifact: `{normalized_implementation_plan_path}`\n\n"
                            "Handler did not advance labels. Recommended human route: "
                            "`state:systems-architecture-changes-requested`."
                        )
                        item.pop("invalid_implementation_plan_outcome", None)
                    else:
                        print(
                            "[Dispatch] Implementation planner reported non-READY outcome "
                            f"`{implementation_plan_outcome}`; workflow will not advance."
                        )
                        item["comment"] = (
                            "ℹ️ Implementation planner run completed with a non-ready outcome.\n\n"
                            f"Outcome: `{implementation_plan_outcome}`\n"
                            f"Artifact: `{normalized_implementation_plan_path}`\n\n"
                            "Handler did not advance labels because only `READY` outcomes may transition to "
                            "implementation-plan review."
                        )
                        item.pop("invalid_implementation_plan_outcome", None)

                    if classification_diagnostic_comment:
                        item["comment"] = (
                            f"{item['comment']}\n\n{classification_diagnostic_comment}"
                        )

                    item.pop("missing_implementation_plan_artifact", None)
                    add_comment(item)
                    non_ready_snapshot = watchtower.build_implementation_planner_snapshot(
                        normalized_implementation_plan_path,
                        outcome=implementation_plan_outcome,
                        outcome_valid=implementation_plan_outcome is not None,
                        diagnostic=implementation_planner_diagnostic,
                        recommended_route=recommended_route,
                        planner_result_comment_id=planner_result_comment_id,
                        planner_result_comment_url=planner_result_comment_url,
                        parent_issue=planner_result_parent_issue,
                        recommendation_comment_id=planner_result_recommendation_comment_id,
                        roadmap_pr_number=planner_result_roadmap_pr,
                        roadmap_reference_merged=roadmap_reference_merged,
                        generated_issues=planner_result_generated_issues,
                        human_decision_ledger_v1=planner_result_human_decision_ledger,
                    )
                    update_run_status(
                        item,
                        completed_at=utc_timestamp_now(),
                        exit_code=0,
                        success=False,
                        outcome=outcome_name,
                        stop_reason=stop_reason,
                        artifacts=artifacts,
                        implementation_planner=non_ready_snapshot,
                        workflow_classification=workflow_classification_snapshot,
                        recommendation_traceability=watchtower.build_implementation_planner_recommendation_traceability_snapshot(
                            non_ready_snapshot,
                            source_issue=item.get("number"),
                        ),
                    )
                    write_run_result(item)
                    return False

                item.pop("missing_implementation_plan_artifact", None)
                item.pop("invalid_implementation_plan_outcome", None)
                advanced = advance_implementation_planning_workflow_on_success(item, from_state_label=state_label)
                normalized_implementation_plan_path = normalize_path_for_display(implementation_plan_path)
                if workflow_classification_snapshot.get("status") == "malformed":
                    item["comment"] = (
                        "⚠️ Optional `workflow_classification` block in `implementation-plan.md` was malformed.\n\n"
                        "Routing and label transitions were not changed. "
                        f"Diagnostic: {workflow_classification_snapshot.get('diagnostic')}"
                    )
                    add_comment(item)
                ready_snapshot = watchtower.build_implementation_planner_snapshot(
                    normalized_implementation_plan_path,
                    outcome=implementation_plan_outcome,
                    outcome_valid=True,
                    planner_result_comment_id=planner_result_comment_id,
                    planner_result_comment_url=planner_result_comment_url,
                    parent_issue=planner_result_parent_issue,
                    recommendation_comment_id=planner_result_recommendation_comment_id,
                    roadmap_pr_number=planner_result_roadmap_pr,
                    roadmap_reference_merged=roadmap_reference_merged,
                    generated_issues=planner_result_generated_issues,
                    human_decision_ledger_v1=planner_result_human_decision_ledger,
                )
                if not ready_snapshot.get("generated_issues"):
                    ready_snapshot["diagnostic"] = (
                        "implementation plan outcome READY but generated issues section did not include issue links"
                    )
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=0,
                    success=advanced,
                    outcome="implementation plan generated",
                    stop_reason=None if advanced else "label transition failed",
                    artifacts={
                        "implementation_plan": normalized_implementation_plan_path,
                        "implementation_plan_outcome": implementation_plan_outcome,
                    },
                    implementation_planner=ready_snapshot,
                    workflow_classification=workflow_classification_snapshot,
                    recommendation_traceability=watchtower.build_implementation_planner_recommendation_traceability_snapshot(
                        ready_snapshot,
                        source_issue=item.get("number"),
                    ),
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
            perform_locked_item_recovery(item, labels)
            continue

        if "state:dependency-blocked" in labels:
            if perform_dependency_blocked_item_recovery(item, labels):
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

        dependency_resolution = evaluate_item_dependencies(item)
        item["dependency_resolution"] = dependency_resolution
        if dependency_resolution.get("status") == "blocked":
            _ensure_prelaunch_dependency_run_artifacts(item, state_label, config)
            update_run_status(
                item,
                dependency_resolution=dependency_resolution,
                completed_at=utc_timestamp_now(),
                exit_code=None,
                success=False,
                outcome="dependency-blocked",
                stop_reason="unresolved dependencies declared in issue body",
            )
            write_run_result(item)
            print(
                f"[Poll] Skipping {item['type']} #{item['number']}: unresolved dependencies declared in issue body."
            )
            apply_dependency_block_transition(item, [label["name"] for label in item.get("labels", [])])
            return "dependency-blocked"

        update_run_status(item, dependency_resolution=dependency_resolution)

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

        if config["agent"] == "codex" and config["mode"] in {"roadmap-updater", "implementation-planner"}:
            mode_display_name = "roadmap updater" if config["mode"] == "roadmap-updater" else "implementation planner"
            workspace_metadata = resolve_item_workspace_metadata(item)
            workspace_path = workspace_metadata.get("workspace_path")
            item["workspace_path"] = workspace_path
            branch_setup = prepare_developer_branch(item, workspace_path)
            if not branch_setup.get("ok"):
                if branch_setup.get("reason") == "dirty-working-tree":
                    failure_launch_brief_path = write_launch_brief(item, state_label, config, resolve_role_prompt_path(config["mode"]))
                    print(
                        f"[Dispatch] Blocking {mode_display_name} launch for {item['type']} #{item['number']}: "
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
                        f"Handler blocked {mode_display_name} launch for {item['type']} #{item['number']} because "
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
                    f"[Dispatch] {mode_display_name.capitalize()} branch setup failed for {item['type']} #{item['number']}: "
                    f"{branch_setup.get('error', 'unknown error')}"
                )
                print(f"[Dispatch] Releasing lock for {item['type']} #{item['number']} due to pre-launch setup failure...")
                lock_released = unlock_item(item)

                if lock_released:
                    print(f"[Dispatch] Lock cleanup succeeded for {item['type']} #{item['number']}.")
                else:
                    print(f"[Dispatch] Lock cleanup failed for {item['type']} #{item['number']}; manual cleanup may be required.")

                add_prelaunch_setup_failure_comment(item, branch_setup.get("error", f"{mode_display_name} branch setup failed"), lock_released)
                add_comment(item)
                update_run_status(
                    item,
                    completed_at=utc_timestamp_now(),
                    exit_code=None,
                    success=False,
                    outcome="failed pre-launch",
                    stop_reason=branch_setup.get("error", f"{mode_display_name} branch setup failed"),
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
