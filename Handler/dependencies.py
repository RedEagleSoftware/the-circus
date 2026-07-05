import re

from Handler import github_client
from Handler import workflow


DEPENDENCY_SECTION_PATTERN = re.compile(r"^##\s+Circus\s+Dependencies\s*$", re.IGNORECASE)
DEPENDENCY_METADATA_MARKER = "<!-- circus:dependencies v1 -->"
CHECKBOX_LINE_PATTERN = re.compile(r"^\s*-\s*\[[ xX]\]\s*(.+?)\s*$")
ISSUE_URL_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/issues/(?P<number>\d+)",
    re.IGNORECASE,
)
PULL_URL_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>\d+)",
    re.IGNORECASE,
)
ISSUE_REFERENCE_PATTERN = re.compile(r"(?<![A-Za-z0-9_])#(?P<number>\d+)\b")
RESUME_STATE_PATTERN = re.compile(r"^resume_state\s*:\s*(?P<value>[^#].+?)\s*$", re.IGNORECASE)
BLOCKED_BY_PATTERN = re.compile(r"^blocked_by\s*:\s*$", re.IGNORECASE)
LIST_ITEM_PATTERN = re.compile(r"^-\s*(?P<key>[A-Za-z_]+)\s*:\s*(?P<value>.+?)\s*$")
FIELD_PATTERN = re.compile(r"^(?P<key>[A-Za-z_]+)\s*:\s*(?P<value>.+?)\s*$")


def _extract_dependency_section_lines(body):
    if not isinstance(body, str) or not body.strip():
        return []

    lines = body.splitlines()
    in_section = False
    section_lines = []

    for line in lines:
        stripped = line.strip()
        if not in_section:
            if DEPENDENCY_SECTION_PATTERN.match(stripped):
                in_section = True
            continue

        if stripped.startswith("## "):
            break

        section_lines.append(line)

    return section_lines


def _extract_references_from_checkbox_line(line, default_repo):
    matches = []
    seen = set()

    for url_match in ISSUE_URL_PATTERN.finditer(line):
        owner = url_match.group("owner")
        repo = url_match.group("repo")
        number = int(url_match.group("number"))
        dependency = {
            "type": "issue",
            "repo": f"{owner}/{repo}",
            "number": number,
            "url": url_match.group(0),
        }
        dependency_key = (dependency["type"], dependency["repo"], dependency["number"])
        if dependency_key not in seen:
            seen.add(dependency_key)
            matches.append(dependency)

    for url_match in PULL_URL_PATTERN.finditer(line):
        owner = url_match.group("owner")
        repo = url_match.group("repo")
        number = int(url_match.group("number"))
        dependency = {
            "type": "pull_request",
            "repo": f"{owner}/{repo}",
            "number": number,
            "url": url_match.group(0),
        }
        dependency_key = (dependency["type"], dependency["repo"], dependency["number"])
        if dependency_key not in seen:
            seen.add(dependency_key)
            matches.append(dependency)

    for reference_match in ISSUE_REFERENCE_PATTERN.finditer(line):
        number = int(reference_match.group("number"))
        dependency = {
            "type": "issue",
            "repo": default_repo,
            "number": number,
            "url": f"https://github.com/{default_repo}/issues/{number}",
        }
        dependency_key = (dependency["type"], dependency["repo"], dependency["number"])
        if dependency_key not in seen:
            seen.add(dependency_key)
            matches.append(dependency)

    return matches


def _normalize_yaml_scalar(raw_value):
    value = raw_value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        value = value[1:-1]
    return value.strip()


def _extract_v1_fenced_yaml(section_lines):
    marker_index = -1
    for index, raw_line in enumerate(section_lines):
        if raw_line.strip().lower() == DEPENDENCY_METADATA_MARKER:
            marker_index = index
            break

    if marker_index < 0:
        return None, None

    fence_start = None
    for index in range(marker_index + 1, len(section_lines)):
        stripped = section_lines[index].strip().lower()
        if stripped.startswith("```"):
            fence_start = index
            break

    if fence_start is None:
        return None, "dependency metadata marker is present but YAML block is missing"

    yaml_lines = []
    for index in range(fence_start + 1, len(section_lines)):
        stripped = section_lines[index].strip()
        if stripped.startswith("```"):
            return yaml_lines, None
        yaml_lines.append(section_lines[index])

    return None, "dependency metadata YAML block is not closed"


def _parse_v1_yaml_dependencies(yaml_lines, default_repo):
    resume_state = None
    blocked_by_seen = False
    blocked_by_entries = []
    current_entry = None

    for raw_line in yaml_lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if resume_state is None:
            resume_match = RESUME_STATE_PATTERN.match(stripped)
            if resume_match:
                resume_state = _normalize_yaml_scalar(resume_match.group("value"))
                continue

        if BLOCKED_BY_PATTERN.match(stripped):
            blocked_by_seen = True
            continue

        if not blocked_by_seen:
            continue

        if line.startswith("  -"):
            list_match = LIST_ITEM_PATTERN.match(stripped)
            if not list_match:
                return None, "dependency metadata list item is malformed"

            if current_entry:
                blocked_by_entries.append(current_entry)
            current_entry = {
                list_match.group("key").lower(): _normalize_yaml_scalar(list_match.group("value"))
            }
            continue

        if current_entry and line.startswith("    "):
            field_match = FIELD_PATTERN.match(stripped)
            if not field_match:
                return None, "dependency metadata field is malformed"
            current_entry[field_match.group("key").lower()] = _normalize_yaml_scalar(field_match.group("value"))

    if current_entry:
        blocked_by_entries.append(current_entry)

    if not resume_state or not blocked_by_seen:
        return None, "dependency metadata must include resume_state and blocked_by"

    if not blocked_by_entries:
        return None, "dependency metadata blocked_by must include at least one dependency"

    dependencies = []
    seen = set()
    for raw_dependency in blocked_by_entries:
        dependency_type = str(raw_dependency.get("type") or "").strip().lower()
        if dependency_type == "pull-request":
            dependency_type = "pull_request"
        if dependency_type not in {"issue", "pull_request"}:
            return None, "dependency metadata type must be issue or pull_request"

        dependency_repo = str(raw_dependency.get("repo") or default_repo).strip()
        if not dependency_repo or "/" not in dependency_repo:
            return None, "dependency metadata repo must be owner/repo"

        try:
            dependency_number = int(raw_dependency.get("number"))
        except (TypeError, ValueError):
            return None, "dependency metadata number must be an integer"
        if dependency_number <= 0:
            return None, "dependency metadata number must be positive"

        satisfies_on = str(raw_dependency.get("satisfies_on") or "").strip().lower()
        allowed_satisfaction = {
            "issue": "closed_completed",
            "pull_request": "merged",
        }
        if satisfies_on != allowed_satisfaction[dependency_type]:
            return None, f"dependency metadata satisfies_on must be {allowed_satisfaction[dependency_type]} for {dependency_type}"

        dependency_key = (dependency_type, dependency_repo, dependency_number)
        if dependency_key in seen:
            continue
        seen.add(dependency_key)

        target_path = "issues" if dependency_type == "issue" else "pull"
        dependencies.append(
            {
                "type": dependency_type,
                "repo": dependency_repo,
                "number": dependency_number,
                "url": f"https://github.com/{dependency_repo}/{target_path}/{dependency_number}",
                "satisfies_on": satisfies_on,
            }
        )

    return {"resume_state": resume_state, "dependencies": dependencies}, None


def parse_dependency_metadata(body, *, default_repo):
    section_lines = _extract_dependency_section_lines(body)
    if not section_lines:
        return {
            "declared": False,
            "version": None,
            "dependencies": [],
            "resume_state": None,
            "malformed": False,
            "diagnostic": "no dependencies declared",
        }

    yaml_lines, yaml_error = _extract_v1_fenced_yaml(section_lines)
    if yaml_lines is not None or yaml_error is not None:
        if yaml_error:
            return {
                "declared": True,
                "version": "v1",
                "dependencies": [],
                "resume_state": None,
                "malformed": True,
                "diagnostic": yaml_error,
            }

        parsed_metadata, parse_error = _parse_v1_yaml_dependencies(yaml_lines, default_repo)
        if parse_error:
            return {
                "declared": True,
                "version": "v1",
                "dependencies": [],
                "resume_state": None,
                "malformed": True,
                "diagnostic": parse_error,
            }

        return {
            "declared": True,
            "version": "v1",
            "dependencies": parsed_metadata["dependencies"],
            "resume_state": parsed_metadata["resume_state"],
            "malformed": False,
            "diagnostic": None,
        }

    dependencies = []
    seen = set()
    for line in section_lines:
        checkbox_match = CHECKBOX_LINE_PATTERN.match(line)
        if not checkbox_match:
            continue

        for dependency in _extract_references_from_checkbox_line(checkbox_match.group(1), default_repo):
            dependency_key = (dependency["type"], dependency["repo"], dependency["number"])
            if dependency_key in seen:
                continue
            seen.add(dependency_key)
            dependency.setdefault("satisfies_on", "closed_completed" if dependency["type"] == "issue" else "merged")
            dependencies.append(dependency)

    if not dependencies:
        return {
            "declared": True,
            "version": "legacy",
            "dependencies": [],
            "resume_state": None,
            "malformed": True,
            "diagnostic": "dependency metadata section exists but no valid dependencies were found",
        }

    return {
        "declared": True,
        "version": "legacy",
        "dependencies": dependencies,
        "resume_state": None,
        "malformed": False,
        "diagnostic": None,
    }


def parse_declared_dependencies(body, *, default_repo):
    metadata = parse_dependency_metadata(body, default_repo=default_repo)
    return metadata["dependencies"]


def _build_dependency_resolution_entry(dependency, dependency_item):
    state_reason = dependency_item.get("stateReason") or dependency_item.get("state_reason")
    if dependency["type"] == "issue":
        state = str(dependency_item.get("state") or "").upper()
        closed = bool(dependency_item.get("closed"))
        state_reason_upper = str(state_reason or "").upper()
        dependency_blocking = not (state == "CLOSED" and closed and state_reason_upper == "COMPLETED")
        if dependency_blocking:
            resolution_reason = "issue dependency is not closed with COMPLETED"
        else:
            resolution_reason = "issue dependency is closed with COMPLETED"
    else:
        merged = bool(dependency_item.get("merged"))
        dependency_blocking = not merged
        if dependency_blocking:
            resolution_reason = "pull request dependency is not merged"
        else:
            resolution_reason = "pull request dependency is merged"

    return {
        "type": dependency["type"],
        "repo": dependency["repo"],
        "number": dependency["number"],
        "url": dependency.get("url"),
        "satisfies_on": dependency.get("satisfies_on"),
        "title": dependency_item.get("title"),
        "state": dependency_item.get("state"),
        "closed": dependency_item.get("closed"),
        "state_reason": state_reason,
        "merged": dependency_item.get("merged"),
        "blocking": dependency_blocking,
        "resolution_reason": resolution_reason,
    }


def evaluate_dependencies(body, *, default_repo, run_command_fn, get_item_fn=github_client.get_item):
    metadata = parse_dependency_metadata(body, default_repo=default_repo)
    dependencies = metadata["dependencies"]
    if not metadata["declared"]:
        return {
            "declared": False,
            "status": "not-declared",
            "dependencies": [],
            "unresolved": [],
            "diagnostic": "no dependencies declared",
            "resume_state": None,
        }

    if metadata["malformed"]:
        return {
            "declared": True,
            "status": "blocked",
            "dependencies": [],
            "unresolved": ["metadata"],
            "diagnostic": f"dependency metadata malformed: {metadata['diagnostic']}",
            "resume_state": metadata["resume_state"],
        }

    resume_state = metadata.get("resume_state")
    if metadata.get("version") == "v1":
        if not isinstance(resume_state, str) or not resume_state.strip():
            return {
                "declared": True,
                "status": "blocked",
                "dependencies": [],
                "unresolved": ["resume_state"],
                "diagnostic": "dependency metadata malformed: resume_state must be a supported dispatchable state label",
                "resume_state": resume_state,
            }

        normalized_resume_state = resume_state.strip()
        if normalized_resume_state not in workflow.WORKFLOW_STATES:
            return {
                "declared": True,
                "status": "blocked",
                "dependencies": [],
                "unresolved": ["resume_state"],
                "diagnostic": f"dependency metadata malformed: unsupported resume_state '{normalized_resume_state}'",
                "resume_state": resume_state,
            }

        if normalized_resume_state not in workflow.LABEL_MAP:
            return {
                "declared": True,
                "status": "blocked",
                "dependencies": [],
                "unresolved": ["resume_state"],
                "diagnostic": (
                    "dependency metadata malformed: "
                    f"resume_state '{normalized_resume_state}' is not dispatchable"
                ),
                "resume_state": resume_state,
            }

    resolution_entries = []
    unresolved = []

    for dependency in dependencies:
        dependency_item, dependency_ok = get_item_fn(
            dependency["type"],
            dependency["number"],
            repo=dependency["repo"],
            run_command_fn=run_command_fn,
            fields="number,title,url,state,closed,stateReason,merged",
        )
        if not dependency_ok or not isinstance(dependency_item, dict):
            unresolved.append(dependency["url"])
            resolution_entries.append(
                {
                    "type": dependency["type"],
                    "repo": dependency["repo"],
                    "number": dependency["number"],
                    "url": dependency.get("url"),
                    "blocking": True,
                    "resolution_reason": "dependency lookup failed",
                }
            )
            continue

        entry = _build_dependency_resolution_entry(dependency, dependency_item)
        resolution_entries.append(entry)
        if entry["blocking"]:
            unresolved.append(dependency["url"])

    if unresolved:
        status = "blocked"
        diagnostic = "one or more dependencies are not yet resolved"
    else:
        status = "resolved"
        diagnostic = "all declared dependencies are in non-dispatch states"

    return {
        "declared": True,
        "status": status,
        "dependencies": resolution_entries,
        "unresolved": unresolved,
        "diagnostic": diagnostic,
        "resume_state": metadata["resume_state"],
}