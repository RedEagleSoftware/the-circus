import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuration
REPO = os.getenv("CIRCUS_REPO")  # Format: owner/repo
TARGET_REPO_PATH = os.getenv("CIRCUS_TARGET_REPO_PATH")
POLL_INTERVAL = 60  # seconds
DEFAULT_MAX_STEPS_PER_RUN = 1
MAX_STEPS_PER_RUN_ENV = "CIRCUS_MAX_STEPS_PER_RUN"
MAX_BRANCH_SLUG_LENGTH = 60

# Label to Agent Mapping
LABEL_MAP = {
    "state:ready-for-architecture": {
        "agent": "codex",
        "mode": "architect",
        "model": "gpt-5.3-codex",
        "effort": "Medium",
    },
    "state:ready-for-dev": {
        "agent": "junie",
        "mode": "developer",
        "model": "gpt-5.3-codex",
        "effort": "Medium",
    },
    "state:ready-for-review": {
        "agent": "codex",
        "mode": "reviewer",
        "model": "gpt-5.3-codex",
        "effort": "Medium",
    },
    "state:ready-for-architect": {
        "agent": "codex",
        "mode": "architect-approval",
        "model": "gpt-5.3-codex",
        "effort": "Medium",
    },
}

LOCK_LABEL = "state:agent-in-progress"
LAUNCH_ARTIFACT_DIR = os.path.join("Watchtower", "runs")
SHARED_ARTIFACT_PLACEHOLDERS = {
    "architecture-handoff.md": "# Architecture Handoff\n\nNo architecture handoff has been recorded yet.",
    "running-notes.md": "# Running Notes\n\nNo running notes have been recorded yet.",
    "decision-log.md": "# Decision Log\n\nNo decisions have been recorded yet.",
}

AGENT_EXECUTABLE_ENV_OVERRIDES = {
    "junie": "CIRCUS_JUNIE_EXECUTABLE",
    "codex": "CIRCUS_CODEX_EXECUTABLE",
}

EXECUTABLE_PATHS = {}


def get_circus_runtime_root():
    handler_module_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(handler_module_dir, os.pardir))


def resolve_circus_runtime_path(path):
    if path is None:
        return None

    if os.path.isabs(path):
        return os.path.normpath(path)

    return os.path.normpath(os.path.join(get_circus_runtime_root(), path))


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        print(f"[GitHub] Error executing command for repo '{REPO}': {cmd}")
        print(f"[GitHub] Stderr: {result.stderr}")
        return None
    return result.stdout.strip()


def add_comment(item):
    target = item["type"]
    number = item["number"]
    body = item["comment"]

    cmd = f"gh {target} comment {number} --repo {REPO} --body {json.dumps(body)}"
    run_command(cmd)


def verify_github_repo_access():
    print(f"[GitHub] Validating access to repo '{REPO}'...")
    # Note: gh subcommands use different explicit repo-targeting syntax (`gh repo view <repo>` vs `gh issue/pr ... --repo <repo>`).
    payload = run_command(f"gh repo view {REPO} --json nameWithOwner")
    if payload is None:
        print(f"[GitHub] Failed to connect to target repo '{REPO}'.")
        return False

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        print(f"[GitHub] Unexpected response while validating repo '{REPO}'.")
        return False

    repo_name = data.get("nameWithOwner")
    if repo_name != REPO:
        print(f"[GitHub] Repo check returned '{repo_name}' (expected '{REPO}').")
        return False

    print(f"[GitHub] Repo access confirmed: {repo_name}")
    return True


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
            return resolved_override, "env"
        return None, "missing-env"

    resolved_default = shutil.which(executable_name)
    if resolved_default:
        return resolved_default, "path"

    return None, "missing-path"


def validate_required_executables():
    print("[Startup] Validating required executables...")

    resolved_paths = {}
    missing_messages = []

    for executable_name, env_override_name in get_required_executables():
        resolved_path, resolution_source = resolve_executable_path(executable_name, env_override_name)

        if resolved_path:
            if resolution_source == "env":
                print(
                    f"[Startup] Found executable '{executable_name}' via {env_override_name}: {resolved_path}"
                )
            else:
                print(f"[Startup] Found executable '{executable_name}' at: {resolved_path}")

            resolved_paths[executable_name] = resolved_path
            continue

        if resolution_source == "missing-env":
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


def get_candidates(item_type, list_cmd):
    cmd = f"gh {list_cmd} --repo {REPO} --json number,labels,title,url"
    payload = run_command(cmd)
    if payload is None:
        return [], False

    if not payload:
        return [], True

    raw_items = json.loads(payload)
    items = []
    for item in raw_items:
        item["type"] = item_type
        items.append(item)
    return items, True


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
    return [label for label in labels if label in LABEL_MAP]


def get_state_labels(labels):
    return [label for label in labels if label.startswith("state:")]


def is_locked(labels):
    return LOCK_LABEL in labels


def lock_item(item):
    cmd = f"gh {item['type']} edit {item['number']} --repo {REPO} --add-label \"{LOCK_LABEL}\""
    return run_command(cmd) is not None


def unlock_item(item):
    cmd = f"gh {item['type']} edit {item['number']} --repo {REPO} --remove-label \"{LOCK_LABEL}\""
    return run_command(cmd) is not None


def remove_label(item, label):
    cmd = f"gh {item['type']} edit {item['number']} --repo {REPO} --remove-label \"{label}\""
    return run_command(cmd) is not None


def add_label(item, label):
    cmd = f"gh {item['type']} edit {item['number']} --repo {REPO} --add-label \"{label}\""
    return run_command(cmd) is not None


def execute_label_transition(item, workflow_name, transition_steps, success_message, failure_message):
    number = item["number"]
    print(f"[Dispatch] {workflow_name} workflow completed successfully for issue #{number}.")

    transition_ok = True
    for operation, label in transition_steps:
        if operation == "remove":
            print(f"[Dispatch] Removing label: {label}")
            if not remove_label(item, label):
                transition_ok = False
                print(f"[Dispatch] Failed to remove label: {label}")
        else:
            print(f"[Dispatch] Adding label: {label}")
            if not add_label(item, label):
                transition_ok = False
                print(f"[Dispatch] Failed to add label: {label}")

    if transition_ok:
        print(success_message.format(number=number))
    else:
        print(failure_message.format(number=number))

    return transition_ok


def advance_architect_workflow_on_success(item):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", "state:ready-for-architecture"),
        ("add", "state:ready-for-dev"),
    ]

    return execute_label_transition(
        item,
        workflow_name="Architect",
        transition_steps=transition_steps,
        success_message="[Dispatch] Workflow advanced to developer stage for issue #{number}.",
        failure_message=(
            "[Dispatch] Architect workflow transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
    )


def advance_developer_workflow_on_success(item):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", "state:ready-for-dev"),
        ("add", "state:ready-for-review"),
    ]

    return execute_label_transition(
        item,
        workflow_name="Developer",
        transition_steps=transition_steps,
        success_message="[Dispatch] Workflow advanced to review stage for issue #{number}.",
        failure_message=(
            "[Dispatch] Developer workflow transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
    )


def build_developer_commit_message(item):
    return f"Implement issue #{item['number']}: {item.get('title', '').strip()}"


def build_developer_pr_title(item):
    return f"Issue #{item['number']}: {item.get('title', '').strip()}"


def build_developer_pr_body(item, launch_brief_path):
    number = item["number"]
    issue_url = item.get("url") or f"https://github.com/{REPO}/issues/{number}"
    launch_brief_display_path = normalize_path_for_display(launch_brief_path)
    item_run_root = get_item_run_root(item)
    shared_context_paths = build_shared_context_paths(item_run_root)
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

    if os.path.exists(architecture_handoff_path):
        body_lines.append(
            f"- Architecture handoff: `{normalize_path_for_display(architecture_handoff_path)}`"
        )

    return "\n".join(body_lines)


def find_existing_open_pr_for_branch(branch_name):
    cmd = (
        f"gh pr list --repo {REPO} --head {json.dumps(branch_name)} "
        "--state open --json url --limit 1"
    )
    payload = run_command(cmd)
    if payload is None:
        return {
            "ok": False,
            "error": "unable to query existing pull requests",
        }

    try:
        prs = json.loads(payload)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "unable to parse pull request listing response",
        }

    if not prs:
        return {
            "ok": True,
            "url": None,
        }

    return {
        "ok": True,
        "url": prs[0].get("url"),
    }


def add_developer_pr_failure_comment(item, details):
    item["comment"] = (
        f"Handler failed to prepare a pull request after successful developer execution for "
        f"{item['type']} #{item['number']} ({details}). The lock label `{LOCK_LABEL}` remains in place "
        "for human inspection."
    )
    add_comment(item)


def create_pull_request_with_body_file(branch_name, pr_title, pr_body):
    temp_body_file_path = None

    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".md", delete=False) as body_file:
            body_file.write(pr_body)
            temp_body_file_path = body_file.name

        create_pr_cmd = (
            f"gh pr create --repo {REPO} --head {json.dumps(branch_name)} "
            f"--title {json.dumps(pr_title)} --body-file {json.dumps(temp_body_file_path)}"
        )
        return run_command(create_pr_cmd)
    finally:
        if temp_body_file_path and os.path.exists(temp_body_file_path):
            try:
                os.remove(temp_body_file_path)
            except OSError as error:
                print(
                    f"[Dispatch] Warning: unable to remove temporary PR body file "
                    f"'{temp_body_file_path}': {error}"
                )


def finalize_developer_success_with_pull_request(item, launch_brief_path):
    repo_path = TARGET_REPO_PATH
    if not repo_path:
        print("[Dispatch] Cannot finalize developer success: CIRCUS_TARGET_REPO_PATH is not configured.")
        add_developer_pr_failure_comment(item, "target repository path is not configured")
        return False

    developer_branch = item.get("working_branch") or get_current_git_branch(repo_path)
    if not developer_branch:
        print("[Dispatch] Cannot determine developer branch after successful run.")
        add_developer_pr_failure_comment(item, "unable to determine developer branch")
        return False

    print(f"[Dispatch] Developer branch detected for post-run PR flow: {developer_branch}")

    status_result = run_git_command_in_repo(repo_path, ["status", "--porcelain"])
    if status_result is None or status_result.returncode != 0:
        stderr = status_result.stderr.strip() if status_result and status_result.stderr else "unknown error"
        print(f"[Dispatch] Unable to collect git status for PR flow: {stderr}")
        add_developer_pr_failure_comment(item, "unable to inspect git status")
        return False

    git_status = status_result.stdout.strip()
    print(f"[Dispatch] Git status for developer branch '{developer_branch}':")
    if git_status:
        print(git_status)
    else:
        print("[Dispatch] <clean>")

    if not git_status:
        item["comment"] = (
            f"Handler detected no changes after successful developer execution for {item['type']} "
            f"#{item['number']} on branch `{developer_branch}`. No pull request was created. "
            f"The lock label `{LOCK_LABEL}` remains for human inspection."
        )
        add_comment(item)
        print("[Dispatch] No local changes detected after developer success; PR creation skipped.")
        return False

    stage_result = run_git_command_in_repo(repo_path, ["add", "-A"])
    if stage_result is None or stage_result.returncode != 0:
        stderr = stage_result.stderr.strip() if stage_result and stage_result.stderr else "unknown error"
        print(f"[Dispatch] Failed to stage developer changes: {stderr}")
        add_developer_pr_failure_comment(item, "unable to stage developer changes")
        return False

    commit_message = build_developer_commit_message(item)
    print(f"[Dispatch] Developer commit message: {commit_message}")
    commit_result = run_git_command_in_repo(repo_path, ["commit", "-m", commit_message])
    if commit_result is None or commit_result.returncode != 0:
        stderr = commit_result.stderr.strip() if commit_result and commit_result.stderr else "unknown error"
        print(f"[Dispatch] Failed to create developer commit: {stderr}")
        add_developer_pr_failure_comment(item, "unable to create commit")
        return False

    print(f"[Dispatch] Commit created on branch '{developer_branch}'.")

    push_result = run_git_command_in_repo(repo_path, ["push", "-u", "origin", developer_branch])
    if push_result is None or push_result.returncode != 0:
        stderr = push_result.stderr.strip() if push_result and push_result.stderr else "unknown error"
        print(f"[Dispatch] Failed to push developer branch '{developer_branch}': {stderr}")
        add_developer_pr_failure_comment(item, "unable to push developer branch")
        return False

    print(f"[Dispatch] Push succeeded for branch '{developer_branch}'.")

    existing_pr = find_existing_open_pr_for_branch(developer_branch)
    if not existing_pr.get("ok"):
        print(
            f"[Dispatch] Pull request lookup failed for branch '{developer_branch}': "
            f"{existing_pr.get('error', 'unknown error')}"
        )
        add_developer_pr_failure_comment(item, existing_pr.get("error", "unable to query pull requests"))
        return False

    existing_pr_url = existing_pr.get("url")
    if existing_pr_url:
        print(f"[Dispatch] Existing pull request found for branch '{developer_branch}': {existing_pr_url}")
        transition_ok = advance_developer_workflow_on_success(item)
        print(f"[Dispatch] Label transition result after confirming existing PR: {transition_ok}")
        return transition_ok

    pr_title = build_developer_pr_title(item)
    pr_body = build_developer_pr_body(item, launch_brief_path)
    print(f"[Dispatch] Creating pull request with title: {pr_title}")
    create_result = create_pull_request_with_body_file(developer_branch, pr_title, pr_body)
    if create_result is None:
        print(f"[Dispatch] Failed to create pull request for branch '{developer_branch}'.")
        add_developer_pr_failure_comment(item, "unable to create pull request")
        return False

    pr_url_match = re.search(r"https?://\S+", create_result)
    pr_url = pr_url_match.group(0) if pr_url_match else create_result.strip()
    print(f"[Dispatch] Pull request ready for branch '{developer_branch}': {pr_url}")

    transition_ok = advance_developer_workflow_on_success(item)
    print(f"[Dispatch] Label transition result after PR creation: {transition_ok}")
    return transition_ok


def get_max_steps_per_run():
    raw_value = os.getenv(MAX_STEPS_PER_RUN_ENV)
    if raw_value is None:
        return DEFAULT_MAX_STEPS_PER_RUN

    stripped_value = raw_value.strip()
    if not stripped_value:
        print(
            f"[Handler] {MAX_STEPS_PER_RUN_ENV} is blank; using default {DEFAULT_MAX_STEPS_PER_RUN}."
        )
        return DEFAULT_MAX_STEPS_PER_RUN

    try:
        parsed_value = int(stripped_value)
    except ValueError:
        print(
            f"[Handler] Invalid {MAX_STEPS_PER_RUN_ENV} value '{raw_value}'; "
            f"using default {DEFAULT_MAX_STEPS_PER_RUN}."
        )
        return DEFAULT_MAX_STEPS_PER_RUN

    if parsed_value < 1:
        print(
            f"[Handler] {MAX_STEPS_PER_RUN_ENV} must be >= 1; "
            f"using default {DEFAULT_MAX_STEPS_PER_RUN}."
        )
        return DEFAULT_MAX_STEPS_PER_RUN

    return parsed_value


def add_prelaunch_setup_failure_comment(item, error, lock_released):
    lock_result = "released" if lock_released else "could not be released"
    item["comment"] = (
        "Handler failed before launch brief generation completed "
        f"({error}). The lock label `{LOCK_LABEL}` was {lock_result}."
    )


def resolve_dispatch_config(item, labels):
    primary_states = get_primary_state_labels(labels)
    state_labels = get_state_labels(labels)

    if not primary_states:
        if state_labels:
            item["comment"] = (
                "Handler skipped this item: unsupported workflow state label(s) were found "
                f"({', '.join(state_labels)}). Please use one supported state label from the doctrine."
            )
            item["skip_reason"] = f"unsupported workflow state label(s): {', '.join(state_labels)}"
        else:
            item["comment"] = (
                "Handler skipped this item: no supported workflow state label was found. "
                "Please add exactly one primary `state:*` label to continue."
            )
            item["skip_reason"] = "no supported workflow state label"
        return None

    if len(primary_states) > 1:
        item["comment"] = (
            "Handler skipped this item: multiple workflow state labels were found "
            f"({', '.join(primary_states)}). Please keep exactly one primary `state:*` label."
        )
        item["skip_reason"] = f"ambiguous workflow state labels: {', '.join(primary_states)}"
        return None

    return primary_states[0], LABEL_MAP[primary_states[0]]


def build_junie_command(model, effort, project_path, task_text):
    junie_executable = EXECUTABLE_PATHS.get("junie", "junie")
    normalized_effort = str(effort).lower()
    return [
        junie_executable,
        "--project",
        str(project_path),
        "--model",
        str(model),
        "--effort",
        normalized_effort,
        str(task_text),
    ]


def build_junie_task_text(absolute_launch_brief_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} "
        "and execute the assigned workflow."
    )


def build_codex_architect_task_text(absolute_launch_brief_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} and execute the architect workflow. "
        "Produce or update the architecture handoff artifact referenced by the launch brief. "
        "Then leave a GitHub comment summarizing the handoff or blocker."
    )


def resolve_role_prompt_path(mode):
    candidates = [os.path.join("TheFarm", "roles", f"{mode}.md")]
    if mode.endswith("-approval"):
        base_mode = mode[: -len("-approval")]
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


def build_thin_prompt(item, state_label, mode, role_prompt_path, launch_brief_path=None):
    profile_source = resolve_profile_source(role_prompt_path)

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

    return "\n".join(prompt_lines)


def build_codex_command(model, project_path, task_text):
    codex_executable = EXECUTABLE_PATHS.get("codex", "codex")
    return [
        codex_executable,
        "exec",
        "--model",
        str(model),
        "--cd",
        str(project_path),
        str(task_text),
    ]


def is_codex_sandbox_bypass_enabled():
    bypass_value = os.getenv("CIRCUS_CODEX_BYPASS_SANDBOX", "")
    return str(bypass_value).strip().lower() == "true"


def build_codex_command_with_optional_sandbox_bypass(model, project_path, task_text, bypass_sandbox=False):
    command = build_codex_command(model, project_path, task_text)

    if bypass_sandbox:
        command.insert(-1, "--dangerously-bypass-approvals-and-sandbox")

    return command


def extract_github_repo_slug(value):
    if not value:
        return None

    normalized = str(value).strip().replace("\\", "/")
    if normalized.endswith(".git"):
        normalized = normalized[: -len(".git")]

    if "github.com/" in normalized:
        return normalized.split("github.com/", 1)[1].strip("/").lower()

    if "github.com:" in normalized:
        return normalized.split("github.com:", 1)[1].strip("/").lower()

    if re.match(r"^[^/]+/[^/]+$", normalized):
        return normalized.lower()

    return None


def get_git_remote_origin_url(repo_path):
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            shell=False,
        )
    except (OSError, ValueError) as error:
        print(f"[Startup] Warning: Unable to inspect git remote for '{repo_path}': {error}")
        return None

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            print(f"[Startup] Warning: Unable to read git remote.origin.url for '{repo_path}': {stderr}")
        else:
            print(f"[Startup] Warning: Unable to read git remote.origin.url for '{repo_path}'.")
        return None

    remote_url = result.stdout.strip()
    return remote_url or None


def validate_target_repo_workspace(target_repo_path, expected_repo):
    if not target_repo_path:
        print("[Startup] Error: CIRCUS_TARGET_REPO_PATH is required.")
        print("[Startup] Startup aborted: set CIRCUS_TARGET_REPO_PATH to a local target repository working copy.")
        return False

    if not os.path.exists(target_repo_path):
        print(f"[Startup] Error: CIRCUS_TARGET_REPO_PATH does not exist: {target_repo_path}")
        print("[Startup] Startup aborted: configure a valid existing target repository path.")
        return False

    if not os.path.isdir(target_repo_path):
        print(f"[Startup] Error: CIRCUS_TARGET_REPO_PATH is not a directory: {target_repo_path}")
        print("[Startup] Startup aborted: configure CIRCUS_TARGET_REPO_PATH to a repository directory.")
        return False

    git_dir = os.path.join(target_repo_path, ".git")
    if not os.path.exists(git_dir):
        print(f"[Startup] Error: CIRCUS_TARGET_REPO_PATH does not appear to be a git repository: {target_repo_path}")
        print("[Startup] Startup aborted: expected a .git directory or file in the target repository path.")
        return False

    expected_slug = extract_github_repo_slug(expected_repo)
    remote_url = get_git_remote_origin_url(target_repo_path)
    remote_slug = extract_github_repo_slug(remote_url)
    if expected_slug and remote_slug and expected_slug != remote_slug:
        print(
            f"[Startup] Warning: target repo remote appears to mismatch CIRCUS_REPO "
            f"(expected '{expected_repo}', remote '{remote_url}')."
        )

    return True


def slugify_branch_title(value, max_length=MAX_BRANCH_SLUG_LENGTH):
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    if max_length > 0:
        normalized = normalized[:max_length].strip("-")

    return normalized or "untitled"


def build_developer_branch_name(item):
    item_number = item.get("number")
    title_slug = slugify_branch_title(item.get("title", ""))
    return f"circus/issue-{item_number}-{title_slug}"


def run_git_command_in_repo(repo_path, git_args):
    try:
        return subprocess.run(
            ["git", *git_args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            shell=False,
        )
    except (OSError, ValueError) as error:
        print(f"[Dispatch] Git command failed to start in '{repo_path}': {' '.join(['git', *git_args])}")
        print(f"[Dispatch] Git launch error: {error}")
        return None


def get_current_git_branch(repo_path):
    result = run_git_command_in_repo(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        print(f"[Dispatch] Unable to determine current git branch: {stderr}")
        return None

    branch_name = result.stdout.strip()
    return branch_name or None


def is_working_tree_clean(repo_path):
    result = run_git_command_in_repo(repo_path, ["status", "--porcelain"])
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        print(f"[Dispatch] Unable to inspect working tree status: {stderr}")
        return None

    return result.stdout.strip() == ""


def local_branch_exists(repo_path, branch_name):
    result = run_git_command_in_repo(repo_path, ["branch", "--list", branch_name])
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        print(f"[Dispatch] Unable to check local branch '{branch_name}': {stderr}")
        return None

    return bool(result.stdout.strip())


def checkout_or_create_local_branch(repo_path, branch_name, branch_exists):
    if branch_exists:
        checkout_command = ["checkout", branch_name]
    else:
        checkout_command = ["checkout", "-b", branch_name]

    result = run_git_command_in_repo(repo_path, checkout_command)
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        print(f"[Dispatch] Failed to switch to branch '{branch_name}': {stderr}")
        return False

    return True


def prepare_developer_branch(item):
    repo_path = TARGET_REPO_PATH
    if not repo_path:
        return {
            "ok": False,
            "reason": "git-error",
            "error": "CIRCUS_TARGET_REPO_PATH is not configured",
        }

    selected_branch = build_developer_branch_name(item)

    print(f"[Dispatch] Selected developer working branch: {selected_branch}")

    current_branch = get_current_git_branch(repo_path)
    print(f"[Dispatch] Current branch before switch: {current_branch or '<unknown>'}")

    clean_working_tree = is_working_tree_clean(repo_path)
    if clean_working_tree is None:
        return {
            "ok": False,
            "reason": "git-error",
            "error": "unable to determine working tree status",
        }

    status_label = "clean" if clean_working_tree else "dirty"
    print(f"[Dispatch] Working tree status before developer launch: {status_label}")

    if not clean_working_tree:
        return {
            "ok": False,
            "reason": "dirty-working-tree",
            "branch": selected_branch,
            "current_branch": current_branch,
        }

    branch_exists = local_branch_exists(repo_path, selected_branch)
    if branch_exists is None:
        return {
            "ok": False,
            "reason": "git-error",
            "error": f"unable to verify local branch '{selected_branch}'",
        }

    if not checkout_or_create_local_branch(repo_path, selected_branch, branch_exists):
        return {
            "ok": False,
            "reason": "git-error",
            "error": f"unable to switch to branch '{selected_branch}'",
        }

    if branch_exists:
        print(f"[Dispatch] Checked out existing branch: {selected_branch}")
    else:
        print(f"[Dispatch] Created and checked out branch: {selected_branch}")

    final_branch = get_current_git_branch(repo_path)
    print(f"[Dispatch] Final branch before launching Junie: {final_branch or '<unknown>'}")

    return {
        "ok": True,
        "branch": selected_branch,
    }


def detect_default_base_branch(repo_path):
    remote_head = run_git_command_in_repo(repo_path, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if remote_head is not None and remote_head.returncode == 0:
        remote_ref = remote_head.stdout.strip()
        if remote_ref and "/" in remote_ref:
            return remote_ref.split("/", 1)[1], "remote-head"

    if remote_head is not None and remote_head.returncode != 0:
        stderr = remote_head.stderr.strip() if remote_head.stderr else "unknown error"
        print(f"[Dispatch] Unable to resolve origin/HEAD symbolic ref: {stderr}")

    remote_show = run_git_command_in_repo(repo_path, ["remote", "show", "origin"])
    if remote_show is not None and remote_show.returncode == 0:
        for line in remote_show.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("HEAD branch:"):
                detected_branch = stripped.split(":", 1)[1].strip()
                if detected_branch:
                    return detected_branch, "remote-show"

    if remote_show is not None and remote_show.returncode != 0:
        stderr = remote_show.stderr.strip() if remote_show.stderr else "unknown error"
        print(f"[Dispatch] Unable to inspect remote origin metadata for default branch: {stderr}")

    return "main", "fallback"


def checkout_branch(repo_path, branch_name):
    result = run_git_command_in_repo(repo_path, ["checkout", branch_name])
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        print(f"[Dispatch] Failed to checkout branch '{branch_name}': {stderr}")
        return False

    return True


def prepare_architect_execution_branch(item):
    repo_path = TARGET_REPO_PATH
    if not repo_path:
        return {
            "ok": False,
            "reason": "git-error",
            "error": "CIRCUS_TARGET_REPO_PATH is not configured",
        }

    print("[Dispatch] Preparing architect repository context...")
    current_branch = get_current_git_branch(repo_path)
    print(f"[Dispatch] Current branch: {current_branch or '<unknown>'}")

    clean_working_tree = is_working_tree_clean(repo_path)
    if clean_working_tree is None:
        return {
            "ok": False,
            "reason": "git-error",
            "error": "unable to determine working tree status",
        }

    status_label = "clean" if clean_working_tree else "dirty"
    print(f"[Dispatch] Working tree status before architect launch: {status_label}")

    if not clean_working_tree:
        return {
            "ok": False,
            "reason": "dirty-working-tree",
            "current_branch": current_branch,
        }

    base_branch, detection_source = detect_default_base_branch(repo_path)
    if detection_source == "fallback":
        print("[Dispatch] Default branch detection failed; falling back to base branch: main")
    else:
        print(f"[Dispatch] Detected base branch: {base_branch}")

    if current_branch != base_branch:
        print("[Dispatch] Checking out base branch for architect execution...")
        if not checkout_branch(repo_path, base_branch):
            return {
                "ok": False,
                "reason": "git-error",
                "error": f"unable to checkout base branch '{base_branch}'",
            }
    else:
        print("[Dispatch] Checkout not required; already on base branch.")

    final_branch = get_current_git_branch(repo_path)
    print(f"[Dispatch] Architect execution branch: {final_branch or '<unknown>'}")
    if final_branch != base_branch:
        return {
            "ok": False,
            "reason": "git-error",
            "error": f"base branch checkout verification failed (expected '{base_branch}', got '{final_branch or '<unknown>'}')",
        }

    return {
        "ok": True,
        "branch": final_branch,
    }


def sanitize_filename_part(value):
    safe = []
    for char in str(value).lower():
        if char.isalnum() or char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("-")

    normalized = "".join(safe).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")

    return normalized or "unknown"


def normalize_path_for_display(path):
    if path is None:
        return None

    return path.replace("\\", "/")


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


def get_item_run_root(item):
    item_dir = f"{sanitize_filename_part(item['type'])}-{item['number']}"
    launch_artifact_root = resolve_circus_runtime_path(LAUNCH_ARTIFACT_DIR)
    return os.path.normpath(os.path.join(launch_artifact_root, item_dir))


def build_shared_context_paths(item_run_root):
    shared_dir = os.path.normpath(os.path.join(item_run_root, "shared"))
    return {
        "architecture_handoff": normalize_path_for_display(os.path.join(shared_dir, "architecture-handoff.md")),
        "running_notes": normalize_path_for_display(os.path.join(shared_dir, "running-notes.md")),
        "decision_log": normalize_path_for_display(os.path.join(shared_dir, "decision-log.md")),
    }


def ensure_shared_artifacts(item_run_root):
    shared_dir = os.path.normpath(os.path.join(item_run_root, "shared"))
    os.makedirs(shared_dir, exist_ok=True)

    for filename, placeholder in SHARED_ARTIFACT_PLACEHOLDERS.items():
        artifact_path = os.path.join(shared_dir, filename)
        if os.path.exists(artifact_path):
            continue

        with open(artifact_path, "x", encoding="utf-8") as artifact_file:
            artifact_file.write(f"{placeholder}\n")

    return build_shared_context_paths(item_run_root)


def build_launch_brief_path(item, mode):
    item_run_root = get_item_run_root(item)
    run_number = get_next_run_number(item_run_root)
    run_dir = f"run-{run_number:03d}-{sanitize_filename_part(mode)}"
    brief_path = os.path.normpath(os.path.join(item_run_root, run_dir, "launch-brief.md"))
    return normalize_path_for_display(brief_path)


def build_launch_brief_markdown(item, state_label, config, role_prompt_path, timestamp, target_repo_path, shared_context_paths=None):
    # TODO: Discover target-repo agent instructions by convention (AGENTS.md,
    # .circus/roles/<mode>.md, .circus/workflows/<mode>.md) once routing contracts are finalized.
    profile_source = resolve_profile_source(role_prompt_path)
    normalized_target_repo_path = normalize_path_for_display(target_repo_path)
    normalized_circus_runtime_root = normalize_path_for_display(get_circus_runtime_root())

    lines = [
        "# Launch Brief",
        "",
        "## Runtime Roots",
        f"- circus repo root: `{normalized_circus_runtime_root}`",
        f"- target repo root: `{normalized_target_repo_path}`",
        "",
        "## Assignment",
        f"- repository: `{REPO}`",
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

    return "\n".join(lines)


def write_launch_brief(item, state_label, config, role_prompt_path):
    timestamp = datetime.now().isoformat(timespec="seconds")
    item_run_root = get_item_run_root(item)
    shared_context_paths = ensure_shared_artifacts(item_run_root)
    brief_path = build_launch_brief_path(item, config["mode"])
    brief_content = build_launch_brief_markdown(
        item,
        state_label,
        config,
        role_prompt_path,
        timestamp,
        TARGET_REPO_PATH or "<not configured>",
        shared_context_paths,
    )
    os.makedirs(os.path.dirname(brief_path), exist_ok=True)

    with open(brief_path, "w", encoding="utf-8") as brief_file:
        brief_file.write(f"{brief_content}\n")

    print(f"[Dispatch] Shared artifact path (architecture handoff): {shared_context_paths['architecture_handoff']}")
    print(f"[Dispatch] Shared artifact path (running notes): {shared_context_paths['running_notes']}")
    print(f"[Dispatch] Shared artifact path (decision log): {shared_context_paths['decision_log']}")

    return brief_path


def launch_agent(item, state_label, config, role_prompt_path, launch_brief_path):
    agent = config["agent"]
    mode = config["mode"]
    model = config["model"]
    effort = config["effort"]
    number = item["number"]
    thin_prompt = build_thin_prompt(item, state_label, mode, role_prompt_path, launch_brief_path)

    print(f"[Dispatch] Launching {agent} in {mode} mode with model={model}, effort={effort}")
    print(f"[Dispatch] Target item: {item['type']} #{number} - {item['title']}")
    print(f"[Dispatch] Target repo path: {TARGET_REPO_PATH}")
    print(f"[Dispatch] Launch brief: {launch_brief_path}")
    print("[Dispatch] Generated thin prompt:")
    print(thin_prompt)

    if agent == "junie":
        absolute_launch_brief_path = os.path.abspath(launch_brief_path)
        junie_task_text = build_junie_task_text(absolute_launch_brief_path)
        cmd = build_junie_command(model, effort, TARGET_REPO_PATH or "", junie_task_text)
        normalized_target_repo_path = normalize_path_for_display(TARGET_REPO_PATH) if TARGET_REPO_PATH else "<not configured>"
        command_shape = (
            f"{cmd[0]} --project {cmd[2]} --model {cmd[4]} --effort {cmd[6]} "
            f"\"{cmd[7]}\""
        )

        print(f"[Dispatch] Launch brief display path: {launch_brief_path}")
        print(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}")
        print(f"[Dispatch] Junie target repo path: {normalized_target_repo_path}")
        print("[Dispatch] Junie handoff path: passing short positional task argument.")
        print(f"[Dispatch] Executing: {command_shape}")
        print(f"[Dispatch] Junie execution cwd: {TARGET_REPO_PATH}")

        try:
            result = subprocess.run(cmd, cwd=TARGET_REPO_PATH, text=True)
        except OSError as error:
            item["prelaunch_error"] = str(error)
            print(f"[Dispatch] Junie failed to launch before execution started: {error}")
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
            return False
        else:
            item.pop("agent_exit_non_zero", None)
            if mode == "developer" and state_label == "state:ready-for-dev":
                return finalize_developer_success_with_pull_request(item, launch_brief_path)

            print(f"[Dispatch] Junie completed with exit code 0 for {item['type']} #{number}; lock remains in place.")
            return True
    elif agent == "codex":
        print(f"[Dispatch] Codex routing metadata: mode={mode}, effort={effort}")
        if mode != "architect":
            print("[Dispatch] TODO: Codex execution flow currently enabled only for architect mode.")
            return True

        absolute_launch_brief_path = os.path.abspath(launch_brief_path)
        codex_task_text = build_codex_architect_task_text(absolute_launch_brief_path)
        codex_bypass_sandbox = is_codex_sandbox_bypass_enabled()
        cmd = build_codex_command_with_optional_sandbox_bypass(
            model,
            TARGET_REPO_PATH or "",
            codex_task_text,
            bypass_sandbox=codex_bypass_sandbox,
        )
        normalized_target_repo_path = normalize_path_for_display(TARGET_REPO_PATH) if TARGET_REPO_PATH else "<not configured>"
        command_arguments = cmd[1:-1]
        command_shape = f"{cmd[0]} {' '.join(command_arguments)} \"{cmd[-1]}\""

        print(f"[Dispatch] Launch brief display path: {launch_brief_path}")
        print(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}")
        print(f"[Dispatch] Codex target repo path: {normalized_target_repo_path}")
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
        print("[Dispatch] Codex handoff path: passing short positional prompt argument.")
        print(f"[Dispatch] Executing: {command_shape}")
        print(f"[Dispatch] Codex execution cwd: {TARGET_REPO_PATH}")

        try:
            result = subprocess.run(cmd, cwd=TARGET_REPO_PATH, text=True)
        except OSError as error:
            item["prelaunch_error"] = str(error)
            print(f"[Dispatch] Codex failed to launch before execution started: {error}")
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
            return False
        else:
            item.pop("agent_exit_non_zero", None)
            if mode == "architect" and state_label == "state:ready-for-architecture":
                return advance_architect_workflow_on_success(item)
            else:
                print(f"[Dispatch] Codex completed with exit code 0 for {item['type']} #{number}; lock remains in place.")
                return True
    else:
        print(f"[Dispatch] Unknown agent: {agent}")
        return False


def process_one_item(items):
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

        item.pop("working_branch", None)
        item.pop("execution_branch", None)
        if config["agent"] == "junie" and config["mode"] == "developer":
            branch_setup = prepare_developer_branch(item)
            if not branch_setup.get("ok"):
                if branch_setup.get("reason") == "dirty-working-tree":
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
                return "prelaunch-failed"

            item["working_branch"] = branch_setup["branch"]

        if config["agent"] == "codex" and config["mode"] == "architect":
            branch_setup = prepare_architect_execution_branch(item)
            if not branch_setup.get("ok"):
                if branch_setup.get("reason") == "dirty-working-tree":
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
                return "prelaunch-failed"

            item["execution_branch"] = branch_setup["branch"]

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
                "Handler failed to start Junie before execution began "
                f"({prelaunch_error}). The lock label `{LOCK_LABEL}` was {lock_result}."
            )
            add_comment(item)
            item.pop("prelaunch_error", None)
            return "prelaunch-failed"

        if item.get("agent_exit_non_zero"):
            item.pop("agent_exit_non_zero", None)
            return "agent-non-zero"

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
    print(f"[Handler] Max workflow steps this run: {max_steps_per_run}")

    startup_retrieval_confirmed = False
    completed_steps = 0

    while completed_steps < max_steps_per_run:
        cycle_number = completed_steps + 1
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
            print("[Handler] No eligible workflow step found. Exiting.")
            return

        dispatch_result = process_one_item(items)
        if dispatch_result == "success":
            completed_steps += 1
            print(f"[Handler] Completed workflow step {completed_steps} of {max_steps_per_run}.")

            if completed_steps >= max_steps_per_run:
                print("[Handler] Max workflow steps reached. Exiting.")
                return

            print("[Handler] Re-polling for next eligible workflow step.")
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
        if dispatch_result == "no-dispatch":
            print("[Handler] No dispatch completed this cycle. Exiting.")
            return

    print("[Handler] Max workflow steps reached. Exiting.")

if __name__ == "__main__":
    poll()
