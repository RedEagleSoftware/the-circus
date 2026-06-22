import os


DEFAULT_CODEX_BYPASS_SANDBOX_ENV = "CIRCUS_CODEX_BYPASS_SANDBOX"


def build_junie_command(model, effort, project_path, task_text, *, executable_paths=None):
    resolved_executable_paths = executable_paths or {}
    junie_executable = resolved_executable_paths.get("junie", "junie")
    normalized_effort = str(effort).lower()
    return [
        junie_executable,
        "--project",
        str(project_path),
        "--model",
        str(model),
        "--effort",
        normalized_effort,
        str(task_text),
    ]


def build_junie_task_text(absolute_launch_brief_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} "
        "and execute the assigned workflow."
    )


def build_codex_architect_task_text(absolute_launch_brief_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} and execute the architect workflow. "
        "Produce or update the architecture handoff artifact referenced by the launch brief. "
        "Then leave a GitHub comment summarizing the handoff or blocker."
    )


def build_codex_systems_architect_task_text(absolute_launch_brief_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} and execute the systems architect workflow. "
        "Publish a structured GitHub issue comment as the primary human review artifact using this contract: "
        "## Systems Architect Recommendation; "
        "### Recommendation; "
        "### Rationale; "
        "### Proposed Follow-up; "
        "### Risks / Tradeoffs; "
        "### Human Review Options with both label choices: "
        "state:ready-for-roadmap-update and state:systems-architecture-changes-requested. "
        "Keep Watchtower artifacts for run history and observability, not as the primary review surface. "
        "If blocked, leave a GitHub comment that clearly describes the blocker."
    )


def build_codex_roadmap_updater_task_text(absolute_launch_brief_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} and execute the roadmap updater workflow. "
        "Identify the human-approved Systems Architect recommendation from the issue discussion. "
        "If approval is ambiguous, block and leave a comment. "
        "Update documentation and knowledge artifacts (roadmaps, capability tree, etc.) based on the recommendation. "
        "Create a documentation PR with your changes. "
        "Leave a summary comment on the issue linking to the PR. "
        "Do not modify runtime code. "
        "Do not modify workflow labels directly. "
        "Do not auto-merge."
    )


def build_codex_implementation_planner_task_text(absolute_launch_brief_path, implementation_plan_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} and execute the implementation planner workflow. "
        "Review the architecture handoff and systems architecture recommendation artifacts referenced by the brief. "
        "Publish a structured implementation plan as a GitHub issue comment with scope, phases, risks, and review checklist. "
        f"Write implementation-plan.md to this exact absolute path: {implementation_plan_path} before exiting. "
        "Do not modify runtime code. "
        "Do not modify workflow labels directly."
    )


def build_codex_reviewer_task_text(absolute_launch_brief_path, review_pr_url, review_result_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} and execute the reviewer workflow. "
        f"Review the linked pull request at {review_pr_url}. "
        f"Write review-result.md to this exact absolute path: {review_result_path}. "
        "The first non-empty line of review-result.md must be exactly one of: "
        "Outcome: APPROVED, Outcome: CHANGES_REQUESTED, or Outcome: BLOCKED. "
        "Use the strict review-result.md outcome contract. "
        "Leave a review comment on the pull request. "
        "Do not modify workflow labels directly. "
        "Do not auto-merge."
    )


def build_codex_architect_review_task_text(absolute_launch_brief_path, review_pr_url, architect_review_result_path):
    return (
        f"Read the launch brief at {absolute_launch_brief_path} and execute the architect review workflow. "
        f"Review the linked pull request at {review_pr_url}. "
        f"Write architect-review-result.md to this exact absolute path: {architect_review_result_path}. "
        "The first non-empty line of architect-review-result.md must be exactly one of: "
        "Outcome: APPROVED, Outcome: CHANGES_REQUESTED, or Outcome: BLOCKED. "
        "Use the strict architect-review-result.md outcome contract. "
        "Comment on the pull request with architectural review findings. "
        "Do not modify workflow labels directly. "
        "Do not auto-merge."
    )


def build_codex_command(model, project_path, task_text, *, executable_paths=None):
    resolved_executable_paths = executable_paths or {}
    codex_executable = resolved_executable_paths.get("codex", "codex")
    return [
        codex_executable,
        "exec",
        "--model",
        str(model),
        "--cd",
        str(project_path),
        str(task_text),
    ]


def is_codex_sandbox_bypass_enabled(
    env_name=DEFAULT_CODEX_BYPASS_SANDBOX_ENV,
    env_getter=os.getenv,
):
    bypass_value = env_getter(env_name, "")
    return str(bypass_value).strip().lower() == "true"


def build_codex_command_with_optional_sandbox_bypass(
    model,
    project_path,
    task_text,
    bypass_sandbox=False,
    *,
    executable_paths=None,
):
    command = build_codex_command(
        model,
        project_path,
        task_text,
        executable_paths=executable_paths,
    )

    if bypass_sandbox:
        command.insert(-1, "--dangerously-bypass-approvals-and-sandbox")

    return command