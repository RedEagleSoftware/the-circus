import json
import os
import re
import subprocess
import tempfile


def run_command(cmd, repo, run_subprocess=subprocess.run, log=print):
    result = run_subprocess(cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        log(f"[GitHub] Error executing command for repo '{repo}': {cmd}")
        log(f"[GitHub] Stderr: {result.stderr}")
        return None
    return result.stdout.strip()


def add_comment(item, repo, run_command_fn):
    target = item["type"]
    number = item["number"]
    body = item["comment"]

    cmd = f"gh {target} comment {number} --repo {repo} --body {json.dumps(body)}"
    run_command_fn(cmd)


def verify_github_repo_access(repo, run_command_fn, log=print):
    log(f"[GitHub] Validating access to repo '{repo}'...")
    # Note: gh subcommands use different explicit repo-targeting syntax (`gh repo view <repo>` vs `gh issue/pr ... --repo <repo>`).
    payload = run_command_fn(f"gh repo view {repo} --json nameWithOwner")
    if payload is None:
        log(f"[GitHub] Failed to connect to target repo '{repo}'.")
        return False

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        log(f"[GitHub] Unexpected response while validating repo '{repo}'.")
        return False

    repo_name = data.get("nameWithOwner")
    if repo_name != repo:
        log(f"[GitHub] Repo check returned '{repo_name}' (expected '{repo}').")
        return False

    log(f"[GitHub] Repo access confirmed: {repo_name}")
    return True


def get_candidates(item_type, list_cmd, repo, run_command_fn):
    cmd = f"gh {list_cmd} --repo {repo} --json number,labels,title,url"
    payload = run_command_fn(cmd)
    if payload is None:
        return [], False

    if not payload:
        return [], True

    raw_items = json.loads(payload)
    items = []
    for item in raw_items:
        item["type"] = item_type
        items.append(item)
    return items, True


def get_item(item_type, number, repo, run_command_fn):
    cmd = f"gh {item_type} view {number} --repo {repo} --json number,labels,title,url"
    payload = run_command_fn(cmd)
    if payload is None:
        return None, False

    if not payload:
        return None, False

    try:
        item = json.loads(payload)
    except json.JSONDecodeError:
        return None, False

    item["type"] = item_type
    return item, True


def get_issue_comments(number, repo, run_command_fn):
    cmd = f"gh issue view {number} --repo {repo} --json comments"
    payload = run_command_fn(cmd)
    if payload is None:
        return {
            "ok": False,
            "error": "unable to query issue comments",
            "comments": [],
        }

    if not payload:
        return {
            "ok": True,
            "comments": [],
        }

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "unable to parse issue comments response",
            "comments": [],
        }

    comments = data.get("comments")
    if not isinstance(comments, list):
        comments = []

    return {
        "ok": True,
        "comments": comments,
    }


def lock_item(item, repo, lock_label, run_command_fn):
    cmd = f"gh {item['type']} edit {item['number']} --repo {repo} --add-label \"{lock_label}\""
    return run_command_fn(cmd) is not None


def unlock_item(item, repo, lock_label, run_command_fn):
    cmd = f"gh {item['type']} edit {item['number']} --repo {repo} --remove-label \"{lock_label}\""
    return run_command_fn(cmd) is not None


def remove_label(item, label, repo, run_command_fn):
    cmd = f"gh {item['type']} edit {item['number']} --repo {repo} --remove-label \"{label}\""
    return run_command_fn(cmd) is not None


def add_label(item, label, repo, run_command_fn):
    cmd = f"gh {item['type']} edit {item['number']} --repo {repo} --add-label \"{label}\""
    return run_command_fn(cmd) is not None


def find_existing_open_pr_for_branch(branch_name, repo, run_command_fn):
    cmd = (
        f"gh pr list --repo {repo} --head {json.dumps(branch_name)} "
        "--state open --json url --limit 1"
    )
    payload = run_command_fn(cmd)
    if payload is None:
        return {
            "ok": False,
            "error": "unable to query existing pull requests",
        }

    try:
        prs = json.loads(payload)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "unable to parse pull request listing response",
        }

    if not prs:
        return {
            "ok": True,
            "url": None,
        }

    return {
        "ok": True,
        "url": prs[0].get("url"),
    }


def find_open_review_pr_for_issue(issue_number, repo, run_command_fn):
    cmd = "gh pr list --repo {repo} --state open --json number,url,body --limit 100".format(repo=repo)
    payload = run_command_fn(cmd)
    if payload is None:
        return {
            "ok": False,
            "error": "unable to query open pull requests",
            "pr": None,
        }

    try:
        prs = json.loads(payload)
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "unable to parse pull request listing response",
            "pr": None,
        }

    preferred_pattern = re.compile(rf"\bcloses\s*#{issue_number}\b", re.IGNORECASE)
    fallback_pattern = re.compile(rf"#{issue_number}\b")
    preferred_match = None
    fallback_match = None

    for pr in prs:
        body = pr.get("body") or ""
        if preferred_pattern.search(body):
            preferred_match = pr
            break

        if fallback_match is None and fallback_pattern.search(body):
            fallback_match = pr

    selected_pr = preferred_match or fallback_match
    return {
        "ok": True,
        "pr": selected_pr,
        "match_reason": "preferred-closes" if preferred_match else ("fallback-issue-reference" if fallback_match else None),
    }


def create_pull_request_with_body_file(branch_name, pr_title, pr_body, repo, run_command_fn, log=print):
    temp_body_file_path = None

    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".md", delete=False) as body_file:
            body_file.write(pr_body)
            temp_body_file_path = body_file.name

        create_pr_cmd = (
            f"gh pr create --repo {repo} --head {json.dumps(branch_name)} "
            f"--title {json.dumps(pr_title)} --body-file {json.dumps(temp_body_file_path)}"
        )
        return run_command_fn(create_pr_cmd)
    finally:
        if temp_body_file_path and os.path.exists(temp_body_file_path):
            try:
                os.remove(temp_body_file_path)
            except OSError as error:
                log(
                    f"[Dispatch] Warning: unable to remove temporary PR body file "
                    f"'{temp_body_file_path}': {error}"
                )