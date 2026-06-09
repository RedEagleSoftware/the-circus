SYSTEMS_ARCHITECTURE_LABEL = "state:ready-for-systems-architecture"
SYSTEMS_ARCHITECTURE_CHANGES_REQUESTED_LABEL = "state:systems-architecture-changes-requested"
ROADMAP_UPDATE_LABEL = "state:ready-for-roadmap-update"
ARCHITECTURE_LABEL = "state:ready-for-architecture"
DEVELOPER_LABEL = "state:ready-for-dev"
CHANGES_REQUESTED_LABEL = "state:changes-requested"
NEEDS_AGENT_RETRY_LABEL = "state:needs-agent-retry"
REVIEW_LABEL = "state:ready-for-review"
ARCHITECT_REVIEW_LABEL = "state:ready-for-architect-review"
HUMAN_REVIEW_LABEL = "state:ready-for-human-review"
BLOCKED_LABEL = "state:blocked"
LOCK_LABEL = "state:agent-in-progress"

WORKFLOW_STATES = {
    SYSTEMS_ARCHITECTURE_LABEL: {
        "description": "Ready for strategic systems architecture by systems architect agent.",
        "color": "1D76DB",
        "dispatch": {
            "agent": "codex",
            "mode": "systems-architect",
            "model": "gpt-5.5",
            "effort": "High",
        },
    },
    SYSTEMS_ARCHITECTURE_CHANGES_REQUESTED_LABEL: {
        "description": "Systems architecture changes requested; route back to systems architect.",
        "color": "FBCA04",
        "dispatch": {
            "agent": "codex",
            "mode": "systems-architect",
            "model": "gpt-5.5",
            "effort": "High",
        },
    },
    ROADMAP_UPDATE_LABEL: {
        "description": "Ready for human roadmap/capability-tree update.",
        "color": "FBCA04",
        "human_owned": True,
        "terminal": True,
    },
    ARCHITECTURE_LABEL: {
        "description": "Ready for architecture/specification by architect agent.",
        "color": "1D76DB",
        "dispatch": {
            "agent": "codex",
            "mode": "architect",
            "model": "gpt-5.5",
            "effort": "High",
        },
    },
    DEVELOPER_LABEL: {
        "description": "Ready for implementation by developer agent.",
        "color": "1D76DB",
        "dispatch": {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        },
    },
    CHANGES_REQUESTED_LABEL: {
        "description": "Changes requested; route back to development.",
        "color": "FBCA04",
        "dispatch": {
            "agent": "junie",
            "mode": "developer",
            "model": "gpt-5.3-codex",
            "effort": "Medium",
        },
    },
    NEEDS_AGENT_RETRY_LABEL: {
        "description": "Retry required due to missing or invalid agent output artifacts.",
        "color": "FBCA04",
    },
    REVIEW_LABEL: {
        "description": "Ready for review by reviewer agent.",
        "color": "1D76DB",
        "dispatch": {
            "agent": "codex",
            "mode": "reviewer",
            "model": "gpt-5.5",
            "effort": "High",
        },
    },
    ARCHITECT_REVIEW_LABEL: {
        "description": "Ready for architect approval after review.",
        "color": "1D76DB",
        "dispatch": {
            "agent": "codex",
            "mode": "architect-review",
            "model": "gpt-5.5",
            "effort": "High",
        },
    },
    HUMAN_REVIEW_LABEL: {
        "description": "Ready for final human review.",
        "color": "FBCA04",
        "human_owned": True,
        "terminal": True,
    },
    BLOCKED_LABEL: {
        "description": "Blocked pending human intervention.",
        "color": "D73A4A",
        "human_owned": True,
        "terminal": True,
    },
    LOCK_LABEL: {
        "description": "Lock label indicating an agent currently owns this item.",
        "color": "8250DF",
    },
}

WORKFLOW_STATE_LABELS = tuple(WORKFLOW_STATES.keys())
