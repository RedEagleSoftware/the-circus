import argparse
import os

from dotenv import load_dotenv


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


def main(argv=None):
    parser = argparse.ArgumentParser(description="The Circus orchestrator launcher")
    parser.add_argument(
        "--sync-labels",
        action="store_true",
        help="Synchronize required workflow labels to CIRCUS_REPO and exit.",
    )
    args = parser.parse_args(argv)

    load_dotenv()

    if args.sync_labels:
        repo = validate_repo_config()
        if not repo:
            return
        run_label_sync(repo)
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
