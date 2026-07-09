import os

from Handler.workflow_states import (
    ARCHITECT_REVIEW_LABEL,
    ARCHITECTURE_LABEL,
    BLOCKED_LABEL,
    CHANGES_REQUESTED_LABEL,
    DEVELOPER_LABEL,
    HUMAN_REVIEW_LABEL,
    IMPLEMENTATION_PLAN_REVIEW_LABEL,
    IMPLEMENTATION_PLANNING_LABEL,
    LOCK_LABEL,
    PLANNED_LABEL,
    REVIEW_LABEL,
    ROADMAP_UPDATE_LABEL,
    SYSTEMS_ARCHITECTURE_LABEL,
    WORKFLOW_STATES,
)


LABEL_MAP = {
    label: state["dispatch"]
    for label, state in WORKFLOW_STATES.items()
    if state.get("dispatch")
}

SUPPORTED_WORKFLOW_LABELS = tuple(LABEL_MAP.keys())
REVIEW_OUTCOMES = {"APPROVED", "CHANGES_REQUESTED", "BLOCKED"}
REVIEW_OUTCOME_MARKERS = {
    "Outcome: APPROVED": "APPROVED",
    "Outcome: CHANGES_REQUESTED": "CHANGES_REQUESTED",
    "Outcome: BLOCKED": "BLOCKED",
}
TERMINAL_WORKFLOW_STATES = {label for label, state in WORKFLOW_STATES.items() if state.get("terminal")}
HUMAN_OWNED_WORKFLOW_STATES = {label for label, state in WORKFLOW_STATES.items() if state.get("human_owned")}


def get_primary_state_labels(labels):
    return get_dispatchable_state_labels(labels)


def get_state_labels(labels):
    return [label for label in labels if label.startswith("state:")]


def get_known_state_labels(labels):
    return [label for label in get_state_labels(labels) if label in WORKFLOW_STATES]


def get_dispatchable_state_labels(labels):
    return [label for label in labels if label in LABEL_MAP]

def get_is_planned_state_label(labels) -> bool:
    return PLANNED_LABEL in labels

def get_unsupported_state_labels(labels):
    return [label for label in get_state_labels(labels) if label not in WORKFLOW_STATES]


def get_primary_workflow_state_labels(labels):
    return [label for label in get_state_labels(labels) if label != LOCK_LABEL]


def get_known_primary_workflow_state_labels(labels):
    return [label for label in get_primary_workflow_state_labels(labels) if label in WORKFLOW_STATES]


def is_locked(labels):
    return LOCK_LABEL in labels


def is_terminal_state_label(label):
    return label in TERMINAL_WORKFLOW_STATES


def is_human_owned_state_label(label):
    return label in HUMAN_OWNED_WORKFLOW_STATES


def resolve_dispatch_config(item, labels):
    primary_states = get_primary_workflow_state_labels(labels)
    dispatchable_states = get_dispatchable_state_labels(labels)
    unsupported_states = get_unsupported_state_labels(labels)
    is_planned = get_is_planned_state_label(labels)

    if unsupported_states:
        item["comment"] = (
            "Handler skipped this item: unsupported workflow state label(s) were found "
            f"({', '.join(unsupported_states)}). Please remove unsupported labels before dispatch."
        )
        item["skip_reason"] = f"unsupported workflow state label(s): {', '.join(unsupported_states)}"
        return None

    if not primary_states:
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

    if not dispatchable_states and not is_planned:
        item["comment"] = (
            "Handler skipped this item: non-dispatch workflow state label found "
            f"({primary_states[0]}). This state requires human or scheduler action before dispatch."
        )
        item["skip_reason"] = f"non-dispatch workflow state label: {primary_states[0]}"
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
        ("remove", ARCHITECTURE_LABEL),
        ("add", DEVELOPER_LABEL),
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


def advance_systems_architect_workflow_on_success(
    item,
    remove_label_fn,
    add_label_fn,
    update_run_status_fn,
    log=print,
    from_state_label=SYSTEMS_ARCHITECTURE_LABEL,
):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", from_state_label),
        ("add", HUMAN_REVIEW_LABEL),
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


def advance_roadmap_update_workflow_on_success(
    item,
    remove_label_fn,
    add_label_fn,
    update_run_status_fn,
    log=print,
    from_state_label=ROADMAP_UPDATE_LABEL,
):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", from_state_label),
        ("add", REVIEW_LABEL),
    ]

    return execute_label_transition(
        item,
        workflow_name="Roadmap Updater",
        transition_steps=transition_steps,
        success_message="[Dispatch] Documentation update complete; workflow advanced to review stage for issue #{number}.",
        failure_message=(
            "[Dispatch] Roadmap Updater workflow transition encountered label update failures for issue #{number}; "
            "manual inspection is required."
        ),
        remove_label_fn=remove_label_fn,
        add_label_fn=add_label_fn,
        update_run_status_fn=update_run_status_fn,
        log=log,
    )


def advance_implementation_planning_workflow_on_success(
    item,
    remove_label_fn,
    add_label_fn,
    update_run_status_fn,
    log=print,
    from_state_label=IMPLEMENTATION_PLANNING_LABEL,
):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", from_state_label),
        ("add", IMPLEMENTATION_PLAN_REVIEW_LABEL),
    ]

    return execute_label_transition(
        item,
        workflow_name="Implementation Planner",
        transition_steps=transition_steps,
        success_message=(
            "[Dispatch] Implementation plan generated; workflow advanced to implementation-plan review stage for issue #{number}."
        ),
        failure_message=(
            "[Dispatch] Implementation Planner workflow transition encountered label update failures for issue #{number}; "
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
    from_state_label=DEVELOPER_LABEL,
):
    transition_steps = [
        ("remove", LOCK_LABEL),
        ("remove", from_state_label),
        ("add", REVIEW_LABEL),
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
        ("remove", REVIEW_LABEL),
        ("add", ARCHITECT_REVIEW_LABEL),
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
        ("remove", REVIEW_LABEL),
        ("add", CHANGES_REQUESTED_LABEL),
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
        ("remove", ARCHITECT_REVIEW_LABEL),
        ("add", HUMAN_REVIEW_LABEL),
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
        ("remove", ARCHITECT_REVIEW_LABEL),
        ("add", CHANGES_REQUESTED_LABEL),
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