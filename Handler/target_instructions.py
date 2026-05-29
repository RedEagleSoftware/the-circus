import os


def _normalize_absolute_path(path):
    return os.path.normpath(os.path.abspath(path)).replace("\\", "/")


def discover_target_instruction_paths(target_repo_path, mode):
    if not target_repo_path:
        return []

    if not os.path.isdir(target_repo_path):
        return []

    normalized_target_repo_root = os.path.normpath(target_repo_path)
    candidate_relative_paths = [
        "AGENTS.md",
        os.path.join(".circus", "instructions.md"),
        os.path.join(".circus", "conventions.md"),
        os.path.join(".circus", "architecture.md"),
        os.path.join(".circus", "testing.md"),
    ]
    if mode:
        candidate_relative_paths.extend(
            [
                os.path.join(".circus", "roles", f"{mode}.md"),
                os.path.join(".circus", "workflows", f"{mode}.md"),
            ]
        )

    discovered_paths = []
    for relative_path in candidate_relative_paths:
        candidate_path = os.path.normpath(os.path.join(normalized_target_repo_root, relative_path))
        if not os.path.isfile(candidate_path):
            continue

        discovered_paths.append(_normalize_absolute_path(candidate_path))

    return discovered_paths