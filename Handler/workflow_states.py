SYSTEMS_ARCHITECTURE_LABEL = "state:ready-for-systems-architecture"
SYSTEMS_ARCHITECTURE_CHANGES_REQUESTED_LABEL = "state:systems-architecture-changes-requested"
ROADMAP_UPDATE_LABEL = "state:ready-for-roadmap-update"
IMPLEMENTATION_PLANNING_LABEL = "state:ready-for-implementation-planning"
IMPLEMENTATION_PLANNING_CHANGES_REQUESTED_LABEL = "state:implementation-planning-changes-requested"
IMPLEMENTATION_PLAN_REVIEW_LABEL = "state:ready-for-implementation-plan-review"
PLANNED_LABEL = "state:planned"
ARCHITECTURE_LABEL = "state:ready-for-architecture"
DEVELOPER_LABEL = "state:ready-for-dev"
CHANGES_REQUESTED_LABEL = "state:changes-requested"
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
        "description": "Ready for Roadmap Updater agent to synchronize documentation/roadmap artifacts.",
        "color": "1D76DB",
        "dispatch": {
            "agent": "codex",
            "mode": "roadmap-updater",
            "model": "gpt-5.5",
            "effort": "High",
        },
    },
    IMPLEMENTATION_PLANNING_LABEL: {
        "description": "Ready for implementation planner agent to produce an implementation plan.",
        "color": "1D76DB",
        "dispatch": {
            "agent": "codex",
            "mode": "implementation-planner",
            "model": "gpt-5.5",
            "effort": "High",
        },
    },
    IMPLEMENTATION_PLANNING_CHANGES_REQUESTED_LABEL: {
        "description": "Implementation planning changes requested; route back to implementation planner.",
        "color": "FBCA04",
        "dispatch": {
            "agent": "codex",
            "mode": "implementation-planner",
            "model": "gpt-5.5",
            "effort": "High",
        },
    },
    IMPLEMENTATION_PLAN_REVIEW_LABEL: {
        "description": "Implementation plan ready for human review and approval before coding dispatch.",
        "color": "FBCA04",
        "human_owned": True,
        "terminal": True,
    },
    PLANNED_LABEL: {
        "description": "Generated implementation issue pending human plan approval; not dispatchable.",
        "color": "0E8A16",
        "human_owned": True,
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
