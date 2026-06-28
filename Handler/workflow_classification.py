import re


WORKFLOW_CLASSIFICATION_FENCED_BLOCK_PATTERN = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
WORKFLOW_CLASSIFICATION_ROOT_KEY = "workflow_classification"
WORKFLOW_CLASSIFICATION_ROOT_PATTERN = re.compile(
    rf"^{WORKFLOW_CLASSIFICATION_ROOT_KEY}\s*:(.*)$"
)
WORKFLOW_CLASSIFICATION_ALLOWED_VALUES = {
    "implementation_complexity": {"low", "medium", "high"},
    "safety_risk": {"low", "medium", "high"},
    "slice_size": {"single_slice", "broad", "multi_slice"},
    "architecture_uncertainty": {"none", "minor", "significant"},
    "routing_recommendation": {"continue", "split", "block", "escalate"},
}
WORKFLOW_CLASSIFICATION_REQUIRED_FIELDS = tuple(WORKFLOW_CLASSIFICATION_ALLOWED_VALUES.keys())


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


def _build_workflow_classification_result(status, *, classification=None, diagnostic=None):
    normalized_classification = classification if isinstance(classification, dict) else None
    result = {
        "status": status,
        "classification": normalized_classification,
        "diagnostic": diagnostic,
    }

    for field_name in WORKFLOW_CLASSIFICATION_REQUIRED_FIELDS:
        result[field_name] = (
            normalized_classification.get(field_name) if normalized_classification is not None else None
        )

    return result


def _extract_workflow_classification_from_block(block_text):
    if not isinstance(block_text, str) or not block_text:
        return None

    lines = block_text.splitlines()
    root_index = None
    root_indent = 0
    for index, line in enumerate(lines):
        stripped_line = line.strip()
        if not stripped_line:
            continue

        root_match = WORKFLOW_CLASSIFICATION_ROOT_PATTERN.match(line.rstrip())
        if root_match:
            root_suffix = root_match.group(1).strip()
            if root_suffix:
                return {
                    "classification": None,
                    "diagnostic": "workflow_classification root must be a nested mapping",
                }

            root_index = index
            root_indent = len(line) - len(line.lstrip(" "))
            break

    if root_index is None:
        return None

    classification_fields = {}
    in_classification_block = True
    for line in lines[root_index + 1 :]:
        stripped_line = line.strip()
        if not stripped_line:
            continue

        current_indent = len(line) - len(line.lstrip(" "))
        if current_indent == root_indent and WORKFLOW_CLASSIFICATION_ROOT_PATTERN.match(line.rstrip()):
            return {
                "classification": None,
                "diagnostic": (
                    "multiple workflow_classification blocks found; expected at most one"
                ),
            }

        if not in_classification_block:
            continue

        if "\t" in line:
            return {
                "classification": None,
                "diagnostic": "workflow_classification block has malformed indentation",
            }

        if current_indent <= root_indent:
            in_classification_block = False
            continue

        if current_indent != root_indent + 2:
            return {
                "classification": None,
                "diagnostic": "workflow_classification block has malformed indentation",
            }

        if ":" not in stripped_line:
            return {
                "classification": None,
                "diagnostic": "workflow_classification block must contain only field: value entries",
            }

        field_name, field_value = stripped_line.split(":", 1)
        field_name = field_name.strip()
        if not field_name:
            return {
                "classification": None,
                "diagnostic": "workflow_classification block contains an empty field name",
            }

        if field_name in classification_fields:
            return {
                "classification": None,
                "diagnostic": f"workflow_classification field `{field_name}` is duplicated",
            }

        parsed_value = _parse_yaml_scalar_value(field_value)
        if parsed_value is None or not parsed_value:
            return {
                "classification": None,
                "diagnostic": f"workflow_classification field `{field_name}` must be a non-empty scalar",
            }

        if parsed_value.startswith("[") or parsed_value.startswith("{") or parsed_value in {"|", ">"}:
            return {
                "classification": None,
                "diagnostic": f"workflow_classification field `{field_name}` must be a flat scalar value",
            }

        classification_fields[field_name] = parsed_value

    return {"classification": classification_fields, "diagnostic": None}


def validate_workflow_classification(markdown_text, *, valid_routes):
    del valid_routes

    matches = []
    for match in WORKFLOW_CLASSIFICATION_FENCED_BLOCK_PATTERN.finditer(markdown_text or ""):
        language = (match.group(1) or "").strip().lower()
        if language not in {"", "yaml", "yml"}:
            continue

        parsed_block = _extract_workflow_classification_from_block(match.group(2))
        if parsed_block is None:
            continue

        matches.append(parsed_block)

    if not matches:
        return _build_workflow_classification_result("absent")

    if len(matches) > 1:
        return _build_workflow_classification_result(
            "malformed",
            diagnostic="multiple workflow_classification blocks found; expected at most one",
        )

    parsed_match = matches[0]
    classification = parsed_match.get("classification")
    if parsed_match.get("diagnostic"):
        return _build_workflow_classification_result(
            "malformed",
            classification=classification,
            diagnostic=parsed_match.get("diagnostic"),
        )

    if not isinstance(classification, dict):
        return _build_workflow_classification_result(
            "malformed",
            diagnostic="workflow_classification block must map to flat field: value entries",
        )

    unsupported_fields = sorted(set(classification.keys()) - set(WORKFLOW_CLASSIFICATION_REQUIRED_FIELDS))
    if unsupported_fields:
        return _build_workflow_classification_result(
            "malformed",
            classification=classification,
            diagnostic=(
                "unsupported workflow_classification field(s): "
                + ", ".join(f"`{field}`" for field in unsupported_fields)
            ),
        )

    missing_fields = [field for field in WORKFLOW_CLASSIFICATION_REQUIRED_FIELDS if field not in classification]
    if missing_fields:
        return _build_workflow_classification_result(
            "malformed",
            classification=classification,
            diagnostic=(
                "missing required workflow_classification field(s): "
                + ", ".join(f"`{field}`" for field in missing_fields)
            ),
        )

    for field_name, allowed_values in WORKFLOW_CLASSIFICATION_ALLOWED_VALUES.items():
        raw_value = classification.get(field_name)
        normalized_value = raw_value.lower() if isinstance(raw_value, str) else raw_value
        if normalized_value not in allowed_values:
            expected = ", ".join(sorted(allowed_values))
            return _build_workflow_classification_result(
                "malformed",
                classification=classification,
                diagnostic=(
                    f"unsupported value for `{field_name}`: `{raw_value}` "
                    f"(expected one of: {expected})"
                ),
            )

        classification[field_name] = normalized_value

    return _build_workflow_classification_result("valid", classification=classification)


def validate_workflow_classification_file(markdown_path, *, valid_routes):
    if not markdown_path:
        return _build_workflow_classification_result(
            "absent", diagnostic="workflow classification source path not provided"
        )

    if not isinstance(markdown_path, str):
        return _build_workflow_classification_result(
            "absent", diagnostic="workflow classification source path is not a string"
        )

    if not re.search(r"\.md$", markdown_path, re.IGNORECASE):
        return _build_workflow_classification_result(
            "absent", diagnostic="workflow classification source is not a markdown artifact"
        )

    try:
        with open(markdown_path, "r", encoding="utf-8") as markdown_file:
            markdown_text = markdown_file.read()
    except OSError:
        return _build_workflow_classification_result(
            "absent", diagnostic="workflow classification source artifact unavailable"
        )

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