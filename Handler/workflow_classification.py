import json
import re


WORKFLOW_CLASSIFICATION_V1_FENCED_BLOCK_PATTERN = re.compile(
    r"```(?:json|yaml|yml)?\s*(.*?)```",
    re.DOTALL | re.IGNORECASE,
)

WORKFLOW_CLASSIFICATION_V1_ROOT_KEY = "workflow_classification_v1"
WORKFLOW_CLASSIFICATION_CONFIDENCE_LEVELS = {"low", "medium", "high"}


def _parse_yaml_scalar_value(raw_value):
    if raw_value is None:
        return None

    stripped_value = raw_value.strip()
    if not stripped_value:
        return ""

    if (
        len(stripped_value) >= 2
        and stripped_value[0] == stripped_value[-1]
        and stripped_value[0] in {'"', "'"}
    ):
        stripped_value = stripped_value[1:-1]

    return stripped_value


def _parse_workflow_classification_yaml_block(block_text):
    if not isinstance(block_text, str) or not block_text:
        return None

    lines = block_text.splitlines()
    root_index = None
    root_indent = 0
    for index, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue

        if stripped_line == f"{WORKFLOW_CLASSIFICATION_V1_ROOT_KEY}:":
            root_index = index
            root_indent = len(line) - len(line.lstrip(" "))
            break

    if root_index is None:
        return None

    classification_fields = {}
    for line in lines[root_index + 1 :]:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        current_indent = len(line) - len(line.lstrip(" "))
        if current_indent <= root_indent:
            break

        if ":" not in stripped_line:
            continue

        field_name, field_value = stripped_line.split(":", 1)
        field_name = field_name.strip()
        classification_fields[field_name] = _parse_yaml_scalar_value(field_value)

    return {
        WORKFLOW_CLASSIFICATION_V1_ROOT_KEY: classification_fields,
    }


def _parse_workflow_classification_payload(markdown_text):
    for match in WORKFLOW_CLASSIFICATION_V1_FENCED_BLOCK_PATTERN.finditer(markdown_text or ""):
        payload_text = match.group(1)
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = _parse_workflow_classification_yaml_block(payload_text)

        if not isinstance(payload, dict):
            continue

        if WORKFLOW_CLASSIFICATION_V1_ROOT_KEY in payload:
            return payload

    return None


def validate_workflow_classification(markdown_text, *, valid_routes):
    payload = _parse_workflow_classification_payload(markdown_text)
    if payload is None:
        return {
            "status": "absent",
            "route": None,
            "confidence": None,
            "rationale": None,
            "diagnostic": "workflow classification block not provided",
        }

    classification = payload.get(WORKFLOW_CLASSIFICATION_V1_ROOT_KEY)
    if not isinstance(classification, dict):
        return {
            "status": "malformed",
            "route": None,
            "confidence": None,
            "rationale": None,
            "diagnostic": "workflow classification block must map to an object",
        }

    route = classification.get("route")
    confidence = classification.get("confidence")
    rationale = classification.get("rationale")

    errors = []
    if not isinstance(route, str) or not route:
        errors.append("route must be a non-empty string")
    elif route not in valid_routes:
        errors.append("route must reference a known workflow state label")

    if not isinstance(confidence, str) or not confidence:
        errors.append("confidence must be a non-empty string")
    elif confidence.lower() not in WORKFLOW_CLASSIFICATION_CONFIDENCE_LEVELS:
        errors.append("confidence must be one of low, medium, or high")

    if not isinstance(rationale, str) or not rationale.strip():
        errors.append("rationale must be a non-empty string")

    if errors:
        return {
            "status": "malformed",
            "route": route if isinstance(route, str) and route else None,
            "confidence": confidence if isinstance(confidence, str) and confidence else None,
            "rationale": rationale if isinstance(rationale, str) and rationale else None,
            "diagnostic": "; ".join(errors),
        }

    return {
        "status": "valid",
        "route": route,
        "confidence": confidence.lower(),
        "rationale": rationale,
        "diagnostic": None,
    }


def validate_workflow_classification_file(markdown_path, *, valid_routes):
    if not markdown_path:
        return {
            "status": "absent",
            "route": None,
            "confidence": None,
            "rationale": None,
            "diagnostic": "workflow classification source path not provided",
        }

    if not isinstance(markdown_path, str):
        return {
            "status": "absent",
            "route": None,
            "confidence": None,
            "rationale": None,
            "diagnostic": "workflow classification source path is not a string",
        }

    if not re.search(r"\.md$", markdown_path, re.IGNORECASE):
        return {
            "status": "absent",
            "route": None,
            "confidence": None,
            "rationale": None,
            "diagnostic": "workflow classification source is not a markdown artifact",
        }

    try:
        with open(markdown_path, "r", encoding="utf-8") as markdown_file:
            markdown_text = markdown_file.read()
    except OSError:
        return {
            "status": "absent",
            "route": None,
            "confidence": None,
            "rationale": None,
            "diagnostic": "workflow classification source artifact unavailable",
        }

    return validate_workflow_classification(markdown_text, valid_routes=valid_routes)


def parse_implementation_plan_outcome(implementation_plan_path, *, allowed_outcomes):
    if not implementation_plan_path or not isinstance(implementation_plan_path, str):
        return None

    try:
        with open(implementation_plan_path, "r", encoding="utf-8") as result_file:
            found_outcome_section = False
            in_outcome_section = False
            outcome = None

            for raw_line in result_file:
                line_without_newline = raw_line.rstrip("\r\n")
                stripped_line = line_without_newline.strip()
                normalized_heading = stripped_line.lower()

                if normalized_heading == "### outcome":
                    if found_outcome_section:
                        return None

                    found_outcome_section = True
                    in_outcome_section = True
                    continue

                if not in_outcome_section:
                    continue

                if stripped_line.startswith("### ") or stripped_line.startswith("## "):
                    in_outcome_section = False
                    continue

                if not stripped_line:
                    continue

                candidate_outcome = stripped_line
                if candidate_outcome in allowed_outcomes:
                    if outcome is not None:
                        return None

                    outcome = candidate_outcome
                    continue

                if outcome is None:
                    return None

            if not found_outcome_section:
                return None

            return outcome
    except OSError:
        return None