REQUIRED_WORKFLOW_LABELS = {
    "state:ready-for-architecture": {
        "description": "Ready for architecture/specification by architect agent.",
        "color": "1D76DB",
    },
    "state:ready-for-dev": {
        "description": "Ready for implementation by developer agent.",
        "color": "1D76DB",
    },
    "state:ready-for-review": {
        "description": "Ready for review by reviewer agent.",
        "color": "1D76DB",
    },
    "state:ready-for-architect-review": {
        "description": "Ready for architect approval after review.",
        "color": "1D76DB",
    },
    "state:ready-for-human-review": {
        "description": "Ready for final human review.",
        "color": "FBCA04",
    },
    "state:changes-requested": {
        "description": "Changes requested; route back to development.",
        "color": "FBCA04",
    },
    "state:blocked": {
        "description": "Blocked pending human intervention.",
        "color": "D73A4A",
    },
    "state:agent-in-progress": {
        "description": "Lock label indicating an agent currently owns this item.",
        "color": "8250DF",
    },
}
