from Handler.workflow_states import (
    ARCHITECT_REVIEW_LABEL,
    ARCHITECTURE_LABEL,
    BLOCKED_LABEL,
    CHANGES_REQUESTED_LABEL,
    DEVELOPER_LABEL,
    HUMAN_REVIEW_LABEL,
    LOCK_LABEL,
    REVIEW_LABEL,
    SYSTEMS_ARCHITECTURE_LABEL,
)


REQUIRED_WORKFLOW_LABELS = {
    ARCHITECTURE_LABEL: {
        "description": "Ready for architecture/specification by architect agent.",
        "color": "1D76DB",
    },
    SYSTEMS_ARCHITECTURE_LABEL: {
        "description": "Ready for strategic systems architecture by systems architect agent.",
        "color": "1D76DB",
    },
    DEVELOPER_LABEL: {
        "description": "Ready for implementation by developer agent.",
        "color": "1D76DB",
    },
    REVIEW_LABEL: {
        "description": "Ready for review by reviewer agent.",
        "color": "1D76DB",
    },
    ARCHITECT_REVIEW_LABEL: {
        "description": "Ready for architect approval after review.",
        "color": "1D76DB",
    },
    HUMAN_REVIEW_LABEL: {
        "description": "Ready for final human review.",
        "color": "FBCA04",
    },
    CHANGES_REQUESTED_LABEL: {
        "description": "Changes requested; route back to development.",
        "color": "FBCA04",
    },
    BLOCKED_LABEL: {
        "description": "Blocked pending human intervention.",
        "color": "D73A4A",
    },
    LOCK_LABEL: {
        "description": "Lock label indicating an agent currently owns this item.",
        "color": "8250DF",
    },
}
