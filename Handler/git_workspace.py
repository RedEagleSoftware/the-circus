import re
import subprocess


def resolve_worktree_root(repo_path, run_git_command, *, normpath, log=print):
    if not repo_path:
        return None, "missing-target-repo"

    result = run_git_command(repo_path, ["rev-parse", "--show-toplevel"])
    if result is not None and result.returncode == 0:
        resolved_root = result.stdout.strip()
        if resolved_root:
            return normpath(resolved_root), "git-rev-parse"

    if result is not None and result.returncode != 0:
        stderr = result.stderr.strip() if result.stderr else "unknown error"
        log(f"[Workspace] Warning: Unable to resolve git worktree root via rev-parse: {stderr}")
    elif result is None:
        log("[Workspace] Warning: Unable to resolve git worktree root via rev-parse: git command failed to start")

    return normpath(repo_path), "target-repo-fallback"


def resolve_item_workspace_metadata(
    item,
    target_repo_path,
    *,
    resolve_worktree_root_fn,
    sanitize_filename_part_fn,
    join_path,
    normpath,
    normalize_path_for_display_fn,
):
    worktree_root, root_source = resolve_worktree_root_fn(target_repo_path)

    workspace_suffix = "unknown-unknown"
    if isinstance(item, dict):
        workspace_suffix = (
            f"{sanitize_filename_part_fn(item.get('type'))}-{sanitize_filename_part_fn(item.get('number'))}"
        )

    workspace_name = f"workspace-{workspace_suffix}"
    workspace_path = normpath(join_path(worktree_root, workspace_name)) if worktree_root else None

    return {
        "worktree_root": normalize_path_for_display_fn(worktree_root),
        "worktree_root_source": root_source,
        "workspace_name": workspace_name,
        "workspace_path": normalize_path_for_display_fn(workspace_path),
    }


def extract_github_repo_slug(value):
    if not value:
        return None

    normalized = str(value).strip().replace("\\", "/")
    if normalized.endswith(".git"):
        normalized = normalized[: -len(".git")]

    if "github.com/" in normalized:
        return normalized.split("github.com/", 1)[1].strip("/").lower()

    if "github.com:" in normalized:
        return normalized.split("github.com:", 1)[1].strip("/").lower()

    if re.match(r"^[^/]+/[^/]+$", normalized):
        return normalized.lower()

    return None


def get_git_remote_origin_url(repo_path, run_subprocess=subprocess.run, log=print):
    try:
        result = run_subprocess(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            shell=False,
        )
    except (OSError, ValueError) as error:
        log(f"[Startup] Warning: Unable to inspect git remote for '{repo_path}': {error}")
        return None

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if stderr:
            log(f"[Startup] Warning: Unable to read git remote.origin.url for '{repo_path}': {stderr}")
        else:
            log(f"[Startup] Warning: Unable to read git remote.origin.url for '{repo_path}'.")
        return None

    remote_url = result.stdout.strip()
    return remote_url or None


def validate_target_repo_workspace(
    target_repo_path,
    expected_repo,
    *,
    path_exists,
    is_dir,
    join_path,
    extract_repo_slug,
    get_remote_origin_url,
    log=print,
):
    if not target_repo_path:
        log("[Startup] Error: CIRCUS_TARGET_REPO_PATH is required.")
        log("[Startup] Startup aborted: set CIRCUS_TARGET_REPO_PATH to a local target repository working copy.")
        return False

    if not path_exists(target_repo_path):
        log(f"[Startup] Error: CIRCUS_TARGET_REPO_PATH does not exist: {target_repo_path}")
        log("[Startup] Startup aborted: configure a valid existing target repository path.")
        return False

    if not is_dir(target_repo_path):
        log(f"[Startup] Error: CIRCUS_TARGET_REPO_PATH is not a directory: {target_repo_path}")
        log("[Startup] Startup aborted: configure CIRCUS_TARGET_REPO_PATH to a repository directory.")
        return False

    git_dir = join_path(target_repo_path, ".git")
    if not path_exists(git_dir):
        log(f"[Startup] Error: CIRCUS_TARGET_REPO_PATH does not appear to be a git repository: {target_repo_path}")
        log("[Startup] Startup aborted: expected a .git directory or file in the target repository path.")
        return False

    expected_slug = extract_repo_slug(expected_repo)
    remote_url = get_remote_origin_url(target_repo_path)
    remote_slug = extract_repo_slug(remote_url)
    if expected_slug and remote_slug and expected_slug != remote_slug:
        log(
            f"[Startup] Warning: target repo remote appears to mismatch CIRCUS_REPO "
            f"(expected '{expected_repo}', remote '{remote_url}')."
        )

    return True


def slugify_branch_title(value, max_length):
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")
    if max_length > 0:
        normalized = normalized[:max_length].strip("-")

    return normalized or "untitled"


def build_developer_branch_name(item, max_branch_slug_length, slugify):
    item_number = item.get("number")
    title_slug = slugify(item.get("title", ""), max_length=max_branch_slug_length)
    return f"circus/issue-{item_number}-{title_slug}"


def run_git_command_in_repo(repo_path, git_args, run_subprocess=subprocess.run, log=print):
    try:
        return run_subprocess(
            ["git", *git_args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            shell=False,
        )
    except (OSError, ValueError) as error:
        log(f"[Dispatch] Git command failed to start in '{repo_path}': {' '.join(['git', *git_args])}")
        log(f"[Dispatch] Git launch error: {error}")
        return None


def get_current_git_branch(repo_path, run_git_command, log=print):
    result = run_git_command(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"])
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        log(f"[Dispatch] Unable to determine current git branch: {stderr}")
        return None

    branch_name = result.stdout.strip()
    return branch_name or None


def is_working_tree_clean(repo_path, run_git_command, log=print):
    result = run_git_command(repo_path, ["status", "--porcelain"])
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        log(f"[Dispatch] Unable to inspect working tree status: {stderr}")
        return None

    return result.stdout.strip() == ""


def local_branch_exists(repo_path, branch_name, run_git_command, log=print):
    result = run_git_command(repo_path, ["branch", "--list", branch_name])
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        log(f"[Dispatch] Unable to check local branch '{branch_name}': {stderr}")
        return None

    return bool(result.stdout.strip())


def checkout_or_create_local_branch(repo_path, branch_name, branch_exists, run_git_command, log=print):
    if branch_exists:
        checkout_command = ["checkout", branch_name]
    else:
        checkout_command = ["checkout", "-b", branch_name]

    result = run_git_command(repo_path, checkout_command)
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        log(f"[Dispatch] Failed to switch to branch '{branch_name}': {stderr}")
        return False

    return True


def prepare_developer_branch(
    item,
    repo_path,
    *,
    build_branch_name,
    get_current_branch,
    check_working_tree_clean,
    check_local_branch_exists,
    checkout_or_create_branch,
    log=print,
):
    if not repo_path:
        return {
            "ok": False,
            "reason": "git-error",
            "error": "CIRCUS_TARGET_REPO_PATH is not configured",
        }

    selected_branch = build_branch_name(item)

    log(f"[Dispatch] Selected developer working branch: {selected_branch}")

    current_branch = get_current_branch(repo_path)
    log(f"[Dispatch] Current branch before switch: {current_branch or '<unknown>'}")

    clean_working_tree = check_working_tree_clean(repo_path)
    if clean_working_tree is None:
        return {
            "ok": False,
            "reason": "git-error",
            "error": "unable to determine working tree status",
        }

    status_label = "clean" if clean_working_tree else "dirty"
    log(f"[Dispatch] Working tree status before developer launch: {status_label}")

    if not clean_working_tree:
        return {
            "ok": False,
            "reason": "dirty-working-tree",
            "branch": selected_branch,
            "current_branch": current_branch,
        }

    branch_exists = check_local_branch_exists(repo_path, selected_branch)
    if branch_exists is None:
        return {
            "ok": False,
            "reason": "git-error",
            "error": f"unable to verify local branch '{selected_branch}'",
        }

    if not checkout_or_create_branch(repo_path, selected_branch, branch_exists):
        return {
            "ok": False,
            "reason": "git-error",
            "error": f"unable to switch to branch '{selected_branch}'",
        }

    if branch_exists:
        log(f"[Dispatch] Checked out existing branch: {selected_branch}")
    else:
        log(f"[Dispatch] Created and checked out branch: {selected_branch}")

    final_branch = get_current_branch(repo_path)
    log(f"[Dispatch] Final branch before launching Junie: {final_branch or '<unknown>'}")

    return {
        "ok": True,
        "branch": selected_branch,
    }


def detect_default_base_branch(repo_path, run_git_command, log=print):
    remote_head = run_git_command(repo_path, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if remote_head is not None and remote_head.returncode == 0:
        remote_ref = remote_head.stdout.strip()
        if remote_ref and "/" in remote_ref:
            return remote_ref.split("/", 1)[1], "remote-head"

    if remote_head is not None and remote_head.returncode != 0:
        stderr = remote_head.stderr.strip() if remote_head.stderr else "unknown error"
        log(f"[Dispatch] Unable to resolve origin/HEAD symbolic ref: {stderr}")

    remote_show = run_git_command(repo_path, ["remote", "show", "origin"])
    if remote_show is not None and remote_show.returncode == 0:
        for line in remote_show.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("HEAD branch:"):
                detected_branch = stripped.split(":", 1)[1].strip()
                if detected_branch:
                    return detected_branch, "remote-show"

    if remote_show is not None and remote_show.returncode != 0:
        stderr = remote_show.stderr.strip() if remote_show.stderr else "unknown error"
        log(f"[Dispatch] Unable to inspect remote origin metadata for default branch: {stderr}")

    return "main", "fallback"


def checkout_branch(repo_path, branch_name, run_git_command, log=print):
    result = run_git_command(repo_path, ["checkout", branch_name])
    if result is None or result.returncode != 0:
        stderr = result.stderr.strip() if result and result.stderr else "unknown error"
        log(f"[Dispatch] Failed to checkout branch '{branch_name}': {stderr}")
        return False

    return True


def prepare_architect_execution_branch(
    item,
    repo_path,
    *,
    get_current_branch,
    check_working_tree_clean,
    detect_default_branch,
    checkout_repo_branch,
    log=print,
):
    if not repo_path:
        return {
            "ok": False,
            "reason": "git-error",
            "error": "CIRCUS_TARGET_REPO_PATH is not configured",
        }

    log("[Dispatch] Preparing architect repository context...")
    current_branch = get_current_branch(repo_path)
    log(f"[Dispatch] Current branch: {current_branch or '<unknown>'}")

    clean_working_tree = check_working_tree_clean(repo_path)
    if clean_working_tree is None:
        return {
            "ok": False,
            "reason": "git-error",
            "error": "unable to determine working tree status",
        }

    status_label = "clean" if clean_working_tree else "dirty"
    log(f"[Dispatch] Working tree status before architect launch: {status_label}")

    if not clean_working_tree:
        return {
            "ok": False,
            "reason": "dirty-working-tree",
            "current_branch": current_branch,
        }

    base_branch, detection_source = detect_default_branch(repo_path)
    if detection_source == "fallback":
        log("[Dispatch] Default branch detection failed; falling back to base branch: main")
    else:
        log(f"[Dispatch] Detected base branch: {base_branch}")

    if current_branch != base_branch:
        log("[Dispatch] Checking out base branch for architect execution...")
        if not checkout_repo_branch(repo_path, base_branch):
            return {
                "ok": False,
                "reason": "git-error",
                "error": f"unable to checkout base branch '{base_branch}'",
            }
    else:
        log("[Dispatch] Checkout not required; already on base branch.")

    final_branch = get_current_branch(repo_path)
    log(f"[Dispatch] Architect execution branch: {final_branch or '<unknown>'}")
    if final_branch != base_branch:
        return {
            "ok": False,
            "reason": "git-error",
            "error": f"base branch checkout verification failed (expected '{base_branch}', got '{final_branch or '<unknown>'}')",
        }

    return {
        "ok": True,
        "branch": final_branch,
    }