import os


LABEL_MAP = {
    "state:ready-for-systems-architecture": {
        "agent": "codex",
        "mode": "systems-architect",
        "model": "gpt-5.5",
        "effort": "High",
    },
    "state:ready-for-architecture": {
        "agent": "codex",
        "mode": "architect",
        "model": "gpt-5.5",
        "effort": "High",
    },
    "state:ready-for-system-architecture": {
        "agent": "codex",
        "mode": "systems-architect",
        "model": "gpt-5.3-codex",
        "effort": "Medium",
    },
    "state:ready-for-dev": {
        "agent": "junie",
        "mode": "developer",
        "model": "gpt-5.3-codex",
        "effort": "Medium",
    },
    "state:changes-requested": {
        "agent": "junie",
        "mode": "developer",
        "model": "gpt-5.3-codex",
        "effort": "Medium",
    },
    "state:ready-for-review": {
        "agent": "codex",
        "mode": "reviewer",
        "model": "gpt-5.5",
        "effort": "High",
    },
    "state:ready-for-architect-review": {
        "agent": "codex",
        "mode": "architect-review",
        "model": "gpt-5.5",
        "effort": "High",
    },
}

LOCK_LABEL = "state:agent-in-progress"
SUPPORTED_WORKFLOW_LABELS = tuple(LABEL_MAP.keys())
REVIEW_OUTCOMES = {"APPROVED", "CHANGES_REQUESTED", "BLOCKED"}
REVIEW_OUTCOME_MARKERS = {
    "Outcome: APPROVED": "APPROVED",
    "Outcome: CHANGES_REQUESTED": "CHANGES_REQUESTED",
    "Outcome: BLOCKED": "BLOCKED",
}
TERMINAL_WORKFLOW_STATES = {"state:blocked", "state:ready-for-human-review"}
HUMAN_OWNED_WORKFLOW_STATES = {"state:blocked", "state:ready-for-human-review"}


def get_primary_state_labels(labels):
    return [label for label in labels if label in LABEL_MAP]


def get_state_labels(labels):
    return [label for label in labels if label.startswith("state:")]


def is_locked(labels):
    return LOCK_LABEL in labels


def is_terminal_state_label(label):
    return label in TERMINAL_WORKFLOW_STATES


def is_human_owned_state_label(label):
    return label in HUMAN_OWNED_WORKFLOW_STATES


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


def parse_review_result_outcome(review_result_path):
    if not os.path.exists(review_result_path):
        return None

    try:
        with open(review_result_path, "r", encoding="utf-8") as result_file:
            for raw_line in result_file:
                line_without_newline = raw_line.rstrip("\r\n")
                if not line_without_newline.strip():
                    continue

                return REVIEW_OUTCOME_MARKERS.get(line_without_newline)
    except OSError:
        return None

    return None


def parse_architect_review_result_outcome(architect_review_result_path):
    return parse_review_result_outcome(architect_review_result_path)


def execute_label_transition(
    item,
    workflow_name,
    transition_steps,
    success_message,
    failure_message,
    remove_label_fn,
    add_label_fn,
    update_run_status_fn,
    log=print,
):
    number = item["number"]
    log(f"[Dispatch] {workflow_name} workflow completed successfully for issue #{number}.")

    transition_ok = True
    for operation, label in transition_steps:
        if operation == "remove":
            log(f"[Dispatch] Removing label: {label}")
            if not remove_label_fn(item, label):
                transition_ok = False
                log(f"[Dispatch] Failed to remove label: {label}")
        else:
            log(f"[Dispatch] Adding label: {label}")
            if not add_label_fn(item, label):
                transition_ok = False
                log(f"[Dispatch] Failed to add label: {label}")

    if transition_ok:
        log(success_message.format(number=number))
    else:
        log(failure_message.format(number=number))

    item["last_label_transition"] = {
        "ok": transition_ok,
        "workflow": workflow_name,
        "steps": [{"operation": operation, "label": label} for operation, label in transition_steps],
    }
    update_run_status_fn(item, label_transition=item["last_label_transition"])

    return transition_ok


def advance_architect_workflow_on_success(item, remove_label_fn, add_label_fn, update_run_status_fn, log=print):
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
        remove_label_fn=remove_label_fn,
        add_label_fn=add_label_fn,
        update_run_status_fn=update_run_status_fn,
        log=log,
    )


def advance_systems_architect_workflow_on_success(item, remove_label_fn, add_label_fn, update_run_status_fn, log=print):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", "state:ready-for-system-architecture"),
        ("add", "state:ready-for-human-review"),
    ]

    return execute_label_transition(
        item,
        workflow_name="Systems Architect",
        transition_steps=transition_steps,
        success_message="[Dispatch] Workflow advanced to human review stage for issue #{number}.",
        failure_message=(
            "[Dispatch] Systems Architect workflow transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
        remove_label_fn=remove_label_fn,
        add_label_fn=add_label_fn,
        update_run_status_fn=update_run_status_fn,
        log=log,
    )


def advance_developer_workflow_on_success(
    item,
    remove_label_fn,
    add_label_fn,
    update_run_status_fn,
    log=print,
    from_state_label="state:ready-for-dev",
):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", from_state_label),
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
        remove_label_fn=remove_label_fn,
        add_label_fn=add_label_fn,
        update_run_status_fn=update_run_status_fn,
        log=log,
    )


def advance_reviewer_workflow_on_approved(item, remove_label_fn, add_label_fn, update_run_status_fn, log=print):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", "state:ready-for-review"),
        ("add", "state:ready-for-architect-review"),
    ]

    return execute_label_transition(
        item,
        workflow_name="Reviewer",
        transition_steps=transition_steps,
        success_message=(
            "[Dispatch] Implementation review passed; workflow advanced to architect review stage for issue #{number}."
        ),
        failure_message=(
            "[Dispatch] Reviewer workflow transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
        remove_label_fn=remove_label_fn,
        add_label_fn=add_label_fn,
        update_run_status_fn=update_run_status_fn,
        log=log,
    )


def advance_reviewer_workflow_on_changes_requested(
    item,
    remove_label_fn,
    add_label_fn,
    update_run_status_fn,
    log=print,
):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", "state:ready-for-review"),
        ("add", "state:changes-requested"),
    ]

    return execute_label_transition(
        item,
        workflow_name="Reviewer",
        transition_steps=transition_steps,
        success_message="[Dispatch] Workflow routed back to development for issue #{number}.",
        failure_message=(
            "[Dispatch] Reviewer workflow transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
        remove_label_fn=remove_label_fn,
        add_label_fn=add_label_fn,
        update_run_status_fn=update_run_status_fn,
        log=log,
    )


def advance_architect_review_workflow_on_approved(
    item,
    remove_label_fn,
    add_label_fn,
    update_run_status_fn,
    log=print,
):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", "state:ready-for-architect-review"),
        ("add", "state:ready-for-human-review"),
    ]

    return execute_label_transition(
        item,
        workflow_name="Architect review",
        transition_steps=transition_steps,
        success_message="[Dispatch] Workflow advanced to human review stage for issue #{number}.",
        failure_message=(
            "[Dispatch] Architect review workflow transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
        remove_label_fn=remove_label_fn,
        add_label_fn=add_label_fn,
        update_run_status_fn=update_run_status_fn,
        log=log,
    )


def advance_architect_review_workflow_on_changes_requested(
    item,
    remove_label_fn,
    add_label_fn,
    update_run_status_fn,
    log=print,
):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", "state:ready-for-architect-review"),
        ("add", "state:changes-requested"),
    ]

    return execute_label_transition(
        item,
        workflow_name="Architect review",
        transition_steps=transition_steps,
        success_message="[Dispatch] Architect review routed workflow back to development for issue #{number}.",
        failure_message=(
            "[Dispatch] Architect review workflow transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
        remove_label_fn=remove_label_fn,
        add_label_fn=add_label_fn,
        update_run_status_fn=update_run_status_fn,
        log=log,
    )