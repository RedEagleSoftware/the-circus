import re

from Handler import github_client
from Handler import workflow


DEPENDENCY_SECTION_PATTERN = re.compile(
    r"^##\s+Circus\s+Dependencies\s*$",
    re.IGNORECASE,
)
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


def parse_declared_dependencies(body, *, default_repo):
    section_lines = _extract_dependency_section_lines(body)
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
            dependencies.append(dependency)

    return dependencies


def _build_dependency_resolution_entry(dependency, dependency_item):
    labels = [label.get("name") for label in dependency_item.get("labels", []) if isinstance(label, dict)]
    primary_states = workflow.get_known_primary_workflow_state_labels(labels)
    dispatchable_states = workflow.get_dispatchable_state_labels(labels)
    unsupported_states = workflow.get_unsupported_state_labels(labels)
    terminal_or_human_states = [
        state for state in primary_states if workflow.is_terminal_state_label(state) or workflow.is_human_owned_state_label(state)
    ]

    if not primary_states and not unsupported_states:
        resolution_reason = "dependency has no workflow state labels"
        dependency_blocking = True
    elif unsupported_states:
        resolution_reason = f"dependency has unsupported workflow state labels: {', '.join(sorted(unsupported_states))}"
        dependency_blocking = True
    elif dispatchable_states:
        resolution_reason = f"dependency is still dispatchable: {', '.join(sorted(dispatchable_states))}"
        dependency_blocking = True
    elif terminal_or_human_states:
        resolution_reason = f"dependency reached non-dispatch state: {', '.join(sorted(terminal_or_human_states))}"
        dependency_blocking = False
    else:
        resolution_reason = "dependency state is not dispatchable and not terminal/human-owned"
        dependency_blocking = True

    return {
        "type": dependency["type"],
        "repo": dependency["repo"],
        "number": dependency["number"],
        "url": dependency.get("url"),
        "title": dependency_item.get("title"),
        "state": dependency_item.get("state"),
        "closed": dependency_item.get("closed"),
        "workflow_states": primary_states,
        "dispatchable_states": dispatchable_states,
        "unsupported_states": unsupported_states,
        "blocking": dependency_blocking,
        "resolution_reason": resolution_reason,
    }


def evaluate_dependencies(body, *, default_repo, run_command_fn, get_item_fn=github_client.get_item):
    dependencies = parse_declared_dependencies(body, default_repo=default_repo)
    if not dependencies:
        return {
            "declared": False,
            "status": "not-declared",
            "dependencies": [],
            "unresolved": [],
            "diagnostic": "no dependencies declared",
        }

    resolution_entries = []
    unresolved = []

    for dependency in dependencies:
        dependency_item, dependency_ok = get_item_fn(
            dependency["type"],
            dependency["number"],
            repo=dependency["repo"],
            run_command_fn=run_command_fn,
            fields="number,labels,title,url,state,closed",
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
    }