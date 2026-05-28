import os


def get_circus_runtime_root(module_file, env_getter=os.getenv):
    configured_root = env_getter("CIRCUS_RUNTIME_ROOT")
    if configured_root:
        return os.path.normpath(configured_root)

    handler_directory = os.path.dirname(os.path.abspath(module_file))
    return os.path.normpath(os.path.join(handler_directory, ".."))


def resolve_circus_runtime_path(path, get_runtime_root):
    if os.path.isabs(path):
        return os.path.normpath(path)

    return os.path.normpath(os.path.join(get_runtime_root(), path))


def sanitize_filename_part(value):
    safe = []
    for char in str(value).lower():
        if char.isalnum() or char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("-")

    normalized = "".join(safe).strip("-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")

    return normalized or "unknown"


def normalize_path_for_display(path):
    if path is None:
        return None

    return path.replace("\\", "/")