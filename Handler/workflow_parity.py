import os
import re

from Handler.workflow import LABEL_MAP
from Handler.workflow_labels import REQUIRED_WORKFLOW_LABELS
from Handler.workflow_states import LOCK_LABEL, WORKFLOW_STATES

STATE_LABEL_PATTERN = re.compile(r"\bstate:[a-z0-9-]+\b")
DEFAULT_DOCUMENTATION_PATHS = (
    "README.md",
    "docs/doctrine.md",
    "docs/workflow-governance.md",
    "docs/operations-status.md",
    "docs/capability-tree.md",
    "docs/roadmaps/v1-agent-workflow.md",
)
REQUIRED_DISPATCH_KEYS = ("agent", "mode", "model", "effort")


def collect_documented_workflow_states(repo_root, documentation_paths=None):
    doc_paths = documentation_paths or DEFAULT_DOCUMENTATION_PATHS
    states = set()
    files_checked = []
    missing_files = []

    for relative_path in doc_paths:
        absolute_path = os.path.join(repo_root, relative_path)
        files_checked.append(relative_path)
        if not os.path.isfile(absolute_path):
            missing_files.append(relative_path)
            continue

        try:
            with open(absolute_path, "r", encoding="utf-8") as document_file:
                document_text = document_file.read()
        except OSError:
            missing_files.append(relative_path)
            continue

        states.update(STATE_LABEL_PATTERN.findall(document_text))

    return {
        "states": sorted(states),
        "files_checked": files_checked,
        "missing_files": sorted(missing_files),
    }


def evaluate_workflow_governance_parity(repo_root, documentation_paths=None):
    canonical_states = sorted(WORKFLOW_STATES.keys())
    canonical_state_set = set(canonical_states)
    documented = collect_documented_workflow_states(repo_root, documentation_paths=documentation_paths)
    documented_state_set = set(documented["states"])

    missing_label_metadata = sorted(canonical_state_set - set(REQUIRED_WORKFLOW_LABELS.keys()))
    extra_label_metadata = sorted(set(REQUIRED_WORKFLOW_LABELS.keys()) - canonical_state_set)

    contradictory_dispatch_human_owned = []
    contradictory_dispatch_terminal = []
    missing_dispatch_fields = {}

    for label, state in WORKFLOW_STATES.items():
        dispatch = state.get("dispatch")
        if state.get("human_owned") and dispatch:
            contradictory_dispatch_human_owned.append(label)
        if state.get("terminal") and dispatch:
            contradictory_dispatch_terminal.append(label)
        if dispatch:
            missing_keys = [key for key in REQUIRED_DISPATCH_KEYS if not dispatch.get(key)]
            if missing_keys:
                missing_dispatch_fields[label] = missing_keys

    unsupported_documented_states = sorted(documented_state_set - canonical_state_set)
    undocumented_canonical_states = sorted(canonical_state_set - documented_state_set)

    errors = []
    if missing_label_metadata:
        errors.append(
            "required label metadata missing for canonical state(s): "
            + ", ".join(missing_label_metadata)
        )
    if extra_label_metadata:
        errors.append(
            "required label metadata includes non-canonical state(s): "
            + ", ".join(extra_label_metadata)
        )
    if contradictory_dispatch_human_owned:
        errors.append(
            "state(s) are both human-owned and dispatchable: "
            + ", ".join(contradictory_dispatch_human_owned)
        )
    if contradictory_dispatch_terminal:
        errors.append(
            "state(s) are both terminal and dispatchable: "
            + ", ".join(contradictory_dispatch_terminal)
        )
    if LOCK_LABEL in LABEL_MAP:
        errors.append(f"lock label must not be dispatchable: {LOCK_LABEL}")
    if missing_dispatch_fields:
        missing_parts = [
            f"{label} missing {', '.join(fields)}"
            for label, fields in sorted(missing_dispatch_fields.items())
        ]
        errors.append("dispatch configuration is incomplete: " + "; ".join(missing_parts))
    if unsupported_documented_states:
        errors.append(
            "documented state(s) are unsupported by canonical workflow inventory: "
            + ", ".join(unsupported_documented_states)
        )

    warnings = []
    if documented["missing_files"]:
        warnings.append(
            "documentation file(s) could not be checked: " + ", ".join(documented["missing_files"])
        )
    if undocumented_canonical_states:
        warnings.append(
            "canonical state(s) are not mentioned in the checked docs: "
            + ", ".join(undocumented_canonical_states)
        )

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "details": {
            "canonical_states": canonical_states,
            "documented_states": documented["states"],
            "unsupported_documented_states": unsupported_documented_states,
            "undocumented_canonical_states": undocumented_canonical_states,
            "missing_label_metadata": missing_label_metadata,
            "extra_label_metadata": extra_label_metadata,
            "contradictory_dispatch_human_owned": sorted(contradictory_dispatch_human_owned),
            "contradictory_dispatch_terminal": sorted(contradictory_dispatch_terminal),
            "missing_dispatch_fields": missing_dispatch_fields,
            "checked_documentation_files": documented["files_checked"],
            "missing_documentation_files": documented["missing_files"],
        },
    }


def format_workflow_parity_report(parity_result):
    lines = ["[WorkflowParity] Workflow governance parity report"]

    for error in parity_result["errors"]:
        lines.append(f"[WorkflowParity] ERROR: {error}")
    for warning in parity_result["warnings"]:
        lines.append(f"[WorkflowParity] WARNING: {warning}")

    if parity_result["ok"]:
        lines.append("[WorkflowParity] RESULT: PASS")
    else:
        lines.append("[WorkflowParity] RESULT: FAIL")

    return "\n".join(lines)