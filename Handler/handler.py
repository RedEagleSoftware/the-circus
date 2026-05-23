import json
import os
import subprocess
import time
from dotenv import load_dotenv

load_dotenv()

# Configuration
REPO = os.getenv("CIRCUS_REPO")  # Format: owner/repo
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
    "state:review-requested": {
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


def build_junie_command(number, model, effort):
    return f"junie --issue {number} --model {model} --effort {effort}"


def resolve_role_prompt_path(mode):
    candidates = [os.path.join("TheFarm", "roles", f"{mode}.md")]
    if mode.endswith("-approval"):
        base_mode = mode[: -len("-approval")]
        candidates.append(os.path.join("TheFarm", "roles", f"{base_mode}.md"))

    for path in candidates:
        if os.path.isfile(path):
            return os.path.normpath(path)

    return None


def build_thin_prompt(item, state_label, mode, role_prompt_path):
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
            f"- role/prompt markdown file path: {role_prompt_path or '<not available>'}",
            "- instruction: Use GitHub metadata as the source of truth.",
        ]
    )

    return "\n".join(prompt_lines)


def build_codex_command(model):
    # TODO: Confirm Codex CLI non-interactive prompt/input mechanism in this environment, then pass thin prompt directly.
    return f"codex --model {model}"


def launch_agent(item, state_label, config):
    agent = config["agent"]
    mode = config["mode"]
    model = config["model"]
    effort = config["effort"]
    number = item["number"]
    role_prompt_path = resolve_role_prompt_path(mode)
    thin_prompt = build_thin_prompt(item, state_label, mode, role_prompt_path)

    print(f"[Dispatch] Launching {agent} in {mode} mode with model={model}, effort={effort}")
    print(f"[Dispatch] Target item: {item['type']} #{number} - {item['title']}")
    print("[Dispatch] Generated thin prompt:")
    print(thin_prompt)

    if agent == "junie":
        cmd = build_junie_command(number, model, effort)
    elif agent == "codex":
        print(f"[Dispatch] Codex routing metadata: mode={mode}, effort={effort}")
        print("[Dispatch] TODO: Pass this thin prompt as Codex initial input once the supported CLI mechanism is verified.")
        cmd = build_codex_command(model)
    else:
        print(f"[Dispatch] Unknown agent: {agent}")
        return False

    # One workflow step per agent invocation: dispatch once and stop.
    # TODO: Add a shared prompt-template handoff once role files are fully standardized.
    print(f"[Dispatch] Executing: {cmd}")
    return True


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

        if launch_agent(item, state_label, config):
            return True

    return False


def poll():
    if not REPO:
        print("[Handler] Error: CIRCUS_REPO environment variable is required but not set. Expected format: owner/repo.")
        print("[Handler] Handler cannot continue without an explicit repository target.")
        return

    print("[Handler] Starting Handler...")
    print(f"[Handler] Configured repository: {REPO}")

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
