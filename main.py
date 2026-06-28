import argparse
import os

from dotenv import load_dotenv


INIT_SCAFFOLD_FILES = [
    (
        "AGENTS.md",
        "# Agent Instructions\n\n"
        "Add repository-specific agent instructions here.\n",
    ),
    (
        os.path.join(".circus", "instructions.md"),
        "# Instructions\n\n"
        "Document task-specific operating instructions for agents.\n",
    ),
    (
        os.path.join(".circus", "conventions.md"),
        "# Conventions\n\n"
        "Capture coding and review conventions for this repository.\n",
    ),
    (
        os.path.join(".circus", "architecture.md"),
        "# Architecture\n\n"
        "Describe architecture context and constraints relevant to agent work.\n",
    ),
    (
        os.path.join(".circus", "testing.md"),
        "# Testing\n\n"
        "Describe required test commands and quality gates.\n",
    ),
    (
        os.path.join(".circus", "roles", "architect.md"),
        "# Architect Role\n\n"
        "Define architect responsibilities and boundaries for this repository.\n",
    ),
    (
        os.path.join(".circus", "roles", "developer.md"),
        "# Developer Role\n\n"
        "Define developer responsibilities and implementation standards.\n",
    ),
    (
        os.path.join(".circus", "roles", "reviewer.md"),
        "# Reviewer Role\n\n"
        "Define reviewer responsibilities and acceptance criteria.\n",
    ),
    (
        os.path.join(".circus", "roles", "architect-review.md"),
        "# Architect Review Role\n\n"
        "Define architecture-focused review expectations.\n",
    ),
    (
        os.path.join(".circus", "workflows", "architect.md"),
        "# Architect Workflow\n\n"
        "Document step-by-step architect workflow for this repository.\n",
    ),
    (
        os.path.join(".circus", "workflows", "developer.md"),
        "# Developer Workflow\n\n"
        "Document step-by-step developer workflow for this repository.\n",
    ),
    (
        os.path.join(".circus", "workflows", "reviewer.md"),
        "# Reviewer Workflow\n\n"
        "Document step-by-step reviewer workflow for this repository.\n",
    ),
    (
        os.path.join(".circus", "workflows", "architect-review.md"),
        "# Architect Review Workflow\n\n"
        "Document architecture review workflow and approval checkpoints.\n",
    ),
]


def print_startup_banner(repo, target_repo_path):
    print("=" * 36)
    print("        The Circus Orchestrator")
    print("=" * 36)
    print(f"[Startup] Configured repository: {repo}")
    print(f"[Startup] Configured target repo path: {target_repo_path}")


def validate_startup_config():
    repo = os.getenv("CIRCUS_REPO")
    if not repo:
        print("[Startup] Error: CIRCUS_REPO is required (expected format: owner/repo).")
        print("[Startup] Startup aborted: set CIRCUS_REPO and try again.")
        return None

    target_repo_path = os.getenv("CIRCUS_TARGET_REPO_PATH")
    if not target_repo_path:
        print("[Startup] Error: CIRCUS_TARGET_REPO_PATH is required.")
        print("[Startup] Startup aborted: set CIRCUS_TARGET_REPO_PATH to a target repository working copy.")
        return None

    if not os.path.exists(target_repo_path):
        print(f"[Startup] Error: CIRCUS_TARGET_REPO_PATH does not exist: {target_repo_path}")
        print("[Startup] Startup aborted: configure a valid existing target repository path.")
        return None

    if not os.path.isdir(target_repo_path):
        print(f"[Startup] Error: CIRCUS_TARGET_REPO_PATH is not a directory: {target_repo_path}")
        print("[Startup] Startup aborted: configure CIRCUS_TARGET_REPO_PATH to a repository directory.")
        return None

    return repo, target_repo_path


def launch_handler_polling(repo, target_repo_path):
    import Handler.handler as handler

    # Keep Handler as the orchestration engine module. The launcher owns user-facing startup.
    handler.REPO = repo
    handler.TARGET_REPO_PATH = target_repo_path
    print("[Startup] Launching Handler polling...")
    handler.poll()


def validate_repo_config():
    repo = os.getenv("CIRCUS_REPO")
    if not repo:
        print("[Startup] Error: CIRCUS_REPO is required (expected format: owner/repo).")
        print("[Startup] Startup aborted: set CIRCUS_REPO and try again.")
        return None
    return repo


def run_label_sync(repo):
    import Handler.label_sync as label_sync

    print_startup_banner(repo, "<not required for label sync>")
    print("[Startup] Running manual workflow label synchronization...")
    return label_sync.sync_required_labels(repo)


def run_implementation_plan_approval(repo, issue_number, plan_comment_id=None, dry_run=False):
    import Handler.handler as handler

    print_startup_banner(repo, "<not required for implementation plan approval>")
    print(f"[Startup] Approving implementation plan review for issue #{issue_number}...")
    handler.REPO = repo
    return handler.approve_implementation_plan_review(
        issue_number,
        plan_comment_id=plan_comment_id,
        dry_run=dry_run,
    )


def validate_init_target_path():
    target_repo_path = os.getenv("CIRCUS_TARGET_REPO_PATH")
    if not target_repo_path:
        print("[Init] Error: CIRCUS_TARGET_REPO_PATH is required.")
        print("[Init] Initialization aborted: set CIRCUS_TARGET_REPO_PATH to a target repository working copy.")
        return None

    if not os.path.exists(target_repo_path):
        print(f"[Init] Error: CIRCUS_TARGET_REPO_PATH does not exist: {target_repo_path}")
        print("[Init] Initialization aborted: configure a valid existing target repository path.")
        return None

    if not os.path.isdir(target_repo_path):
        print(f"[Init] Error: CIRCUS_TARGET_REPO_PATH is not a directory: {target_repo_path}")
        print("[Init] Initialization aborted: configure CIRCUS_TARGET_REPO_PATH to a repository directory.")
        return None

    return target_repo_path


def initialize_target_repository(target_repo_path):
    created_count = 0
    skipped_count = 0
    normalized_target_repo_path = os.path.normpath(target_repo_path)

    for relative_path, template_content in INIT_SCAFFOLD_FILES:
        absolute_path = os.path.normpath(os.path.join(normalized_target_repo_path, relative_path))
        if os.path.isfile(absolute_path):
            print(f"[Init] skipped: {relative_path}")
            skipped_count += 1
            continue

        if os.path.exists(absolute_path):
            raise OSError(f"cannot create file because path exists and is not a file: {absolute_path}")

        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        with open(absolute_path, "x", encoding="utf-8") as file_handle:
            file_handle.write(template_content)
        print(f"[Init] created: {relative_path}")
        created_count += 1

    print(f"[Init] Summary: created {created_count}, skipped {skipped_count}.")


def run_target_repo_init(target_repo_path):
    print(f"[Init] Initializing target repository instructions at: {target_repo_path}")
    try:
        initialize_target_repository(target_repo_path)
    except OSError as error:
        print(f"[Init] Error: failed while writing scaffold files: {error}")
        return False
    return True


def run_workflow_governance_parity_check():
    from Handler.workflow_parity import evaluate_workflow_governance_parity, format_workflow_parity_report

    parity_result = evaluate_workflow_governance_parity(repo_root=os.getcwd())
    print(format_workflow_parity_report(parity_result))
    return parity_result["ok"]


def main(argv=None):
    parser = argparse.ArgumentParser(description="The Circus orchestrator launcher")
    parser.add_argument(
        "--sync-labels",
        action="store_true",
        help="Synchronize required workflow labels to CIRCUS_REPO and exit.",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize target repository instruction scaffolding under CIRCUS_TARGET_REPO_PATH and exit.",
    )
    parser.add_argument(
        "--check-workflow-governance",
        action="store_true",
        help="Run workflow governance parity checks and exit.",
    )
    parser.add_argument(
        "--approve-implementation-plan",
        type=int,
        metavar="ISSUE_NUMBER",
        help="Approve implementation-plan review and dispatch generated issues according to planner_result_v1.",
    )
    parser.add_argument(
        "--approve-implementation-plan-comment-id",
        type=int,
        metavar="COMMENT_ID",
        help=(
            "Comment id containing planner_result_v1 to approve. Required when multiple candidate payloads "
            "exist on the source issue."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate implementation-plan approval inputs without mutating labels or posting audit comments.",
    )
    args = parser.parse_args(argv)

    load_dotenv()

    if args.sync_labels:
        repo = validate_repo_config()
        if not repo:
            return
        run_label_sync(repo)
        return

    if args.check_workflow_governance:
        run_workflow_governance_parity_check()
        return

    if args.approve_implementation_plan is not None:
        repo = validate_repo_config()
        if not repo:
            return
        run_implementation_plan_approval(
            repo,
            args.approve_implementation_plan,
            plan_comment_id=args.approve_implementation_plan_comment_id,
            dry_run=args.dry_run,
        )
        return

    if args.init:
        target_repo_path = validate_init_target_path()
        if not target_repo_path:
            return
        run_target_repo_init(target_repo_path)
        return

    startup_config = validate_startup_config()
    if not startup_config:
        return

    repo, target_repo_path = startup_config

    print_startup_banner(repo, target_repo_path)
    launch_handler_polling(repo, target_repo_path)


# TODO: Consider replacing direct script execution with a package entrypoint (`python -m circus`).
if __name__ == "__main__":
    main()
