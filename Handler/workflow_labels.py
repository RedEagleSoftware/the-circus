from Handler.workflow_states import (
    WORKFLOW_STATES,
)


REQUIRED_WORKFLOW_LABELS = {
    label: {
        "description": state["description"],
        "color": state["color"],
    }
    for label, state in WORKFLOW_STATES.items()
}
