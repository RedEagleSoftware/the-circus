import os

from dotenv import load_dotenv


def print_startup_banner(repo):
    print("=" * 36)
    print("        The Circus Orchestrator")
    print("=" * 36)
    print(f"[Startup] Configured repository: {repo}")


def validate_startup_config():
    repo = os.getenv("CIRCUS_REPO")
    if not repo:
        print("[Startup] Error: CIRCUS_REPO is required (expected format: owner/repo).")
        print("[Startup] Startup aborted: set CIRCUS_REPO and try again.")
        return None

    return repo


def launch_handler_polling(repo):
    import Handler.handler as handler

    # Keep Handler as the orchestration engine module. The launcher owns user-facing startup.
    handler.REPO = repo
    print("[Startup] Launching Handler polling...")
    handler.poll()


def main():
    load_dotenv()
    repo = validate_startup_config()
    if not repo:
        return

    print_startup_banner(repo)
    launch_handler_polling(repo)


# TODO: Consider replacing direct script execution with a package entrypoint (`python -m circus`).
if __name__ == "__main__":
    main()
