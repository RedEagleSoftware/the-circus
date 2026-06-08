import json
import os
import re
from datetime import datetime

from Handler import target_instructions


SHARED_ARTIFACT_PLACEHOLDERS = {
    "architecture-handoff.md": "# Architecture Handoff\n\nNo architecture handoff has been recorded yet.",
    "running-notes.md": "# Running Notes\n\nNo running notes have been recorded yet.",
    "decision-log.md": "# Decision Log\n\nNo decisions have been recorded yet.",
}

REVIEW_RESULT_FILENAME = "review-result.md"
ARCHITECT_REVIEW_RESULT_FILENAME = "architect-review-result.md"
RUN_STATUS_FILENAME = "status.json"
RUN_RESULT_FILENAME = "result.md"

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
    "retry_context",
    "artifacts",
]


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


def append_retry_shared_note(
    item_run_root,
    retry_context,
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
        f"## Agent Retry Context ({timestamp})",
        f"- source state: `{retry_context.get('source_state_label') or '<unknown>'}`",
        f"- source mode: `{retry_context.get('source_mode') or '<unknown>'}`",
        f"- source run dir: `{retry_context.get('source_run_dir') or '<unknown>'}`",
        f"- source launch brief: `{retry_context.get('source_launch_brief_path') or '<unknown>'}`",
        f"- retry reason: {retry_context.get('reason') or '<not provided>'}",
    ]

    source_branch = retry_context.get("source_working_branch")
    if source_branch:
        note_lines.append(f"- source working branch: `{source_branch}`")

    artifact_path = retry_context.get("source_result_artifact")
    if artifact_path:
        note_lines.append(f"- source result artifact: `{normalize_path_for_display_fn(artifact_path)}`")

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


def initialize_run_status(
    item,
    state_label,
    config,
    launch_brief_path,
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
        "retry_context": None,
        "artifacts": {
            "launch_brief": normalized_brief_path,
            "status": normalized_status_path,
            "result": normalized_result_path,
        },
    }

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
    return status_payload


def write_run_status(run_state, status_payload):
    with open(run_state["status_path"], "w", encoding="utf-8") as status_file:
        json.dump(status_payload, status_file, indent=2)
        status_file.write("\n")


def find_latest_retry_context(
    item,
    *,
    get_item_run_root_fn,
    normalize_path_for_display_fn,
    run_status_filename=RUN_STATUS_FILENAME,
):
    item_run_root = get_item_run_root_fn(item)
    if not item_run_root or not os.path.isdir(item_run_root):
        return None

    run_dirs = []
    for entry in os.listdir(item_run_root):
        entry_path = os.path.join(item_run_root, entry)
        if not os.path.isdir(entry_path):
            continue
        match = re.match(r"^run-(\d+)-", entry)
        if not match:
            continue
        run_dirs.append((int(match.group(1)), entry_path))

    for _, run_dir in sorted(run_dirs, key=lambda item_pair: item_pair[0], reverse=True):
        status_path = os.path.join(run_dir, run_status_filename)
        if not os.path.exists(status_path):
            continue
        try:
            with open(status_path, "r", encoding="utf-8") as status_file:
                status_payload = json.load(status_file)
        except (OSError, json.JSONDecodeError):
            continue

        retry_context = status_payload.get("retry_context")
        if not isinstance(retry_context, dict):
            continue

        source_state_label = retry_context.get("source_state_label")
        source_mode = retry_context.get("source_mode")
        source_run_dir = retry_context.get("source_run_dir")
        if not source_state_label or not source_mode or not source_run_dir:
            continue

        return {
            "source_state_label": source_state_label,
            "source_mode": source_mode,
            "source_run_dir": source_run_dir,
            "source_launch_brief_path": retry_context.get("source_launch_brief_path"),
            "source_working_branch": retry_context.get("source_working_branch"),
            "source_result_artifact": retry_context.get("source_result_artifact"),
            "reason": retry_context.get("reason"),
            "source_run_status_path": normalize_path_for_display_fn(status_path),
        }

    return None


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

    status_payload["linked_pr"] = item.get("review_pr", {}).get("url") or status_payload.get("linked_pr")
    status_payload["working_branch"] = item.get("working_branch") or status_payload.get("working_branch")
    if item.get("last_label_transition") is not None:
        status_payload["label_transition"] = item.get("last_label_transition")

    write_run_status_fn(run_state, status_payload)


def write_run_result(item, *, get_run_state_fn, read_run_status_fn):
    run_state = get_run_state_fn(item)
    if not run_state:
        return

    status_payload = read_run_status_fn(run_state)
    artifacts = status_payload.get("artifacts") or {}
    label_transition = status_payload.get("label_transition")

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
        f"- run dir: `{status_payload.get('run_dir')}`",
        "",
        "## Outcome",
        f"- linked PR: `{status_payload.get('linked_pr')}`",
        f"- working branch: `{status_payload.get('working_branch')}`",
        "",
        "## Artifacts",
    ]

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
    retry_context=None,
):
    profile_source = resolve_profile_source_fn(role_prompt_path)
    normalized_target_repo_path = normalize_path_for_display_fn(target_repo_path)
    normalized_circus_runtime_root = normalize_path_for_display_fn(get_circus_runtime_root_fn())
    discovered_target_instruction_paths = target_instructions.discover_target_instruction_paths(
        target_repo_path,
        config.get("mode"),
    )

    lines = [
        "# Launch Brief",
        "",
        "## Runtime Roots",
        f"- circus repo root: `{normalized_circus_runtime_root}`",
        f"- target repo root: `{normalized_target_repo_path}`",
        "",
        "## Assignment",
        f"- repository: `{repo}`",
        f"- target repo path: `{normalized_target_repo_path}`",
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

    if retry_context:
        lines.extend(
            [
                "",
                "## Previous Attempt",
                f"- source state: `{retry_context.get('source_state_label') or '<unknown>'}`",
                f"- source mode: `{retry_context.get('source_mode') or '<unknown>'}`",
                f"- source run dir: `{retry_context.get('source_run_dir') or '<unknown>'}`",
                f"- source launch brief: `{retry_context.get('source_launch_brief_path') or '<unknown>'}`",
                f"- source working branch: `{retry_context.get('source_working_branch') or '<unknown>'}`",
                f"- source result artifact: `{retry_context.get('source_result_artifact') or '<unknown>'}`",
                f"- source run status: `{retry_context.get('source_run_status_path') or '<unknown>'}`",
                "",
                "## Retry Instructions",
                "- Resume from the previous attempt context above instead of starting from scratch.",
                "- Preserve the original intent and branch context unless the source artifact proves it is invalid.",
                "- If required source artifacts are missing or contradictory, stop and report the exact blocker.",
            ]
        )

        reason = retry_context.get("reason")
        if reason:
            lines.append(f"- retry reason: {reason}")

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
    initialize_run_status_fn,
    update_run_status_fn,
    normalize_path_for_display_fn,
    timestamp_now_fn=None,
    log=print,
):
    timestamp_now = timestamp_now_fn or (lambda: datetime.now().isoformat(timespec="seconds"))
    timestamp = timestamp_now()
    item_run_root = get_item_run_root_fn(item)
    shared_context_paths = ensure_shared_artifacts_fn(item_run_root)
    retry_context = item.get("retry_context") if state_label == "state:needs-agent-retry" else None
    brief_path = build_launch_brief_path_fn(item, config["mode"])
    review_result_path = None
    if config.get("mode") == "reviewer":
        review_result_path = build_reviewer_result_path_fn(brief_path)
    if config.get("mode") == "architect-review":
        review_result_path = build_architect_review_result_path_fn(brief_path)

    brief_content = build_launch_brief_markdown_fn(
        item,
        state_label,
        config,
        role_prompt_path,
        timestamp,
        target_repo_path or "<not configured>",
        shared_context_paths,
        review_result_path,
        retry_context,
    )
    os.makedirs(os.path.dirname(brief_path), exist_ok=True)

    with open(brief_path, "w", encoding="utf-8") as brief_file:
        brief_file.write(f"{brief_content}\n")

    initialize_run_status_fn(item, state_label, config, brief_path)
    artifact_updates = {
        "architecture_handoff": shared_context_paths["architecture_handoff"],
        "running_notes": shared_context_paths["running_notes"],
        "decision_log": shared_context_paths["decision_log"],
    }

    if review_result_path:
        artifact_updates["result_contract"] = normalize_path_for_display_fn(review_result_path)

    update_run_status_fn(item, launch_brief_path=normalize_path_for_display_fn(brief_path), artifacts=artifact_updates)

    log(f"[Dispatch] Shared artifact path (architecture handoff): {shared_context_paths['architecture_handoff']}")
    log(f"[Dispatch] Shared artifact path (running notes): {shared_context_paths['running_notes']}")
    log(f"[Dispatch] Shared artifact path (decision log): {shared_context_paths['decision_log']}")

    return brief_path