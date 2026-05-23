import json
import os
import subprocess
import time

# Configuration
REPO = os.getenv("CIRCUS_REPO")  # Format: owner/repo
POLL_INTERVAL = 60  # seconds

# Label to Agent Mapping
LABEL_MAP = {
    "state:ready-for-architecture": {"agent": "codex", "mode": "architect"},
    "state:ready-for-dev": {"agent": "junie", "mode": "developer"},
    "state:ready-for-review": {"agent": "codex", "mode": "reviewer"},
    "state:ready-for-architect": {"agent": "codex", "mode": "architect-approval"},
}

LOCK_LABEL = "state:agent-in-progress"


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        print(f"Error executing command: {cmd}")
        print(f"Stderr: {result.stderr}")
        return None
    return result.stdout.strip()


def add_comment(item):
    target = item["type"]
    number = item["number"]
    body = item["comment"]

    cmd = f"gh {target} comment {number} --body {json.dumps(body)}"
    run_command(cmd)


def get_candidates(item_type, list_cmd):
    labels = ",".join(LABEL_MAP.keys())
    cmd = f"gh {list_cmd} --label \"{labels}\" --json number,labels,title"
    payload = run_command(cmd)
    if not payload:
        return []

    raw_items = json.loads(payload)
    items = []
    for item in raw_items:
        item["type"] = item_type
        items.append(item)
    return items


def get_labeled_items():
    items = []
    items.extend(get_candidates("issue", "issue list"))
    items.extend(get_candidates("pr", "pr list"))
    return items


def get_primary_state_labels(labels):
    return [label for label in labels if label in LABEL_MAP]


def is_locked(labels):
    return LOCK_LABEL in labels


def lock_item(item):
    cmd = f"gh {item['type']} edit {item['number']} --add-label \"{LOCK_LABEL}\""
    return run_command(cmd) is not None


def resolve_dispatch_config(item, labels):
    primary_states = get_primary_state_labels(labels)

    if not primary_states:
        item["comment"] = (
            "Handler skipped this item: no supported workflow state label was found. "
            "Please add exactly one primary `state:*` label to continue."
        )
        return None

    if len(primary_states) > 1:
        item["comment"] = (
            "Handler skipped this item: multiple workflow state labels were found "
            f"({', '.join(primary_states)}). Please keep exactly one primary `state:*` label."
        )
        return None

    return LABEL_MAP[primary_states[0]]


def launch_agent(item, config):
    agent = config["agent"]
    mode = config["mode"]
    number = item["number"]

    print(f"Launching {agent} in {mode} mode for {item['type']} #{number}: {item['title']}")

    if agent == "junie":
        cmd = f"junie --issue {number}"
    elif agent == "codex":
        cmd = f"codex --issue {number} --mode {mode}"
    else:
        print(f"Unknown agent: {agent}")
        return False

    # One workflow step per agent invocation: dispatch once and stop.
    # TODO: Add a shared prompt-template handoff once role files are fully standardized.
    print(f"Executing: {cmd}")
    return True


def process_one_item(items):
    for item in items:
        labels = [label["name"] for label in item["labels"]]

        if is_locked(labels):
            continue

        config = resolve_dispatch_config(item, labels)
        if not config:
            print(f"Skipping {item['type']} #{item['number']}: missing/ambiguous workflow context.")
            add_comment(item)
            continue

        if not lock_item(item):
            print(f"Failed to lock {item['type']} #{item['number']}; skipping.")
            continue

        if launch_agent(item, config):
            return True

    return False


def poll():
    if not REPO:
        print("Error: CIRCUS_REPO environment variable not set.")
        return

    print(f"Starting Handler for {REPO}...")
    while True:
        items = get_labeled_items()
        dispatched = process_one_item(items)
        if dispatched:
            print("Dispatched one workflow step. Exiting for manual control.")
            return

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    poll()
