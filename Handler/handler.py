import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configuration
REPO = os.getenv("CIRCUS_REPO")  # Format: owner/repo
TARGET_REPO_PATH = os.getenv("CIRCUS_TARGET_REPO_PATH")
POLL_INTERVAL = 60  # seconds

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
        if os.path.isfile(path):
            return os.path.normpath(path)

    return None


def resolve_profile_source(role_prompt_path):
    if not role_prompt_path:
        return None

    return normalize_path_for_display(role_prompt_path)


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
    return os.path.normpath(os.path.join(LAUNCH_ARTIFACT_DIR, item_dir))


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

    lines = [
        "# Launch Brief",
        "",
        "## Assignment",
        f"- repository: `{REPO}`",
        f"- target repo path: `{normalized_target_repo_path}`",
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
        else:
            print(f"[Dispatch] Junie completed with exit code 0 for {item['type']} #{number}; lock remains in place.")

        return True
    elif agent == "codex":
        print(f"[Dispatch] Codex routing metadata: mode={mode}, effort={effort}")
        if mode != "architect":
            print("[Dispatch] TODO: Codex execution flow currently enabled only for architect mode.")
            return True

        absolute_launch_brief_path = os.path.abspath(launch_brief_path)
        codex_task_text = build_codex_architect_task_text(absolute_launch_brief_path)
        cmd = build_codex_command(model, TARGET_REPO_PATH or "", codex_task_text)
        normalized_target_repo_path = normalize_path_for_display(TARGET_REPO_PATH) if TARGET_REPO_PATH else "<not configured>"
        command_shape = f"{cmd[0]} {cmd[1]} {cmd[2]} {cmd[3]} {cmd[4]} {cmd[5]} \"{cmd[6]}\""

        print(f"[Dispatch] Launch brief display path: {launch_brief_path}")
        print(f"[Dispatch] Launch brief absolute path: {absolute_launch_brief_path}")
        print(f"[Dispatch] Codex target repo path: {normalized_target_repo_path}")
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
            print(f"[Dispatch] Lock acquisition failed for {item['type']} #{item['number']}; skipping.")
            continue

        print(f"[Dispatch] Lock acquired for {item['type']} #{item['number']}.")

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
            continue

        print(f"[Dispatch] Launch brief generated: {launch_brief_path}")

        if launch_agent(item, state_label, config, role_prompt_path, launch_brief_path):
            return True

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
            continue

    return False


def poll():
    global EXECUTABLE_PATHS

    if not REPO:
        print("[Handler] Error: CIRCUS_REPO environment variable is required but not set. Expected format: owner/repo.")
        print("[Handler] Handler cannot continue without an explicit repository target.")
        return

    print("[Handler] Starting Handler...")
    print(f"[Handler] Configured repository: {REPO}")
    print(f"[Handler] Configured target repo path: {TARGET_REPO_PATH}")

    resolved_executables = validate_required_executables()
    if resolved_executables is None:
        return

    EXECUTABLE_PATHS = resolved_executables

    if not validate_target_repo_workspace(TARGET_REPO_PATH, REPO):
        return

    if not verify_github_repo_access():
        print("[Handler] Startup check failed. Exiting.")
        return

    startup_retrieval_confirmed = False
    cycle_number = 1

    while True:
        print(f"[Poll] Starting cycle #{cycle_number}...")
        issues, prs, items, retrieval_ok = get_labeled_items()

        if retrieval_ok:
            print(f"[Poll] Retrieved issues={len(issues)}, prs={len(prs)}, candidates={len(items)}.")
            if not startup_retrieval_confirmed:
                print("[GitHub] Startup retrieval check succeeded for issues and PRs.")
                startup_retrieval_confirmed = True
        else:
            print("[GitHub] Failed to retrieve issues/PRs this cycle; Handler will retry.")

        if not items:
            print("[Poll] No candidate items matched workflow labels this cycle.")

        dispatched = process_one_item(items)
        if dispatched:
            print("[Handler] Dispatched one workflow step. Exiting for manual control.")
            return

        print(f"[Poll] No dispatch in cycle #{cycle_number}. Sleeping for {POLL_INTERVAL} seconds.")
        cycle_number += 1

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    poll()
