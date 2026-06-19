import os


DEFAULT_MAX_STEPS_PER_RUN = 1
MAX_STEPS_PER_RUN_ENV = "CIRCUS_MAX_WORKFLOW_STEPS_PER_ISSUE"
CIRCUS_CODEX_BYPASS_SANDBOX_ENV = "CIRCUS_CODEX_BYPASS_SANDBOX"


def get_max_steps_per_run(
    max_steps_env=MAX_STEPS_PER_RUN_ENV,
    default_max_steps=DEFAULT_MAX_STEPS_PER_RUN,
    env_getter=os.getenv,
    log=print,
):
    raw_value = env_getter(max_steps_env)
    if raw_value is None:
        log(f"[Handler] {max_steps_env} is not set; using default {default_max_steps}.")
        return default_max_steps

    stripped_value = raw_value.strip()
    if not stripped_value:
        log(f"[Handler] {max_steps_env} is blank; using default {default_max_steps}.")
        return default_max_steps

    try:
        parsed_value = int(stripped_value)
    except ValueError:
        log(
            f"[Handler] Invalid {max_steps_env} value '{raw_value}'; "
            f"using default {default_max_steps}."
        )
        return default_max_steps

    if parsed_value < 1:
        log(
            f"[Handler] {max_steps_env} must be >= 1; "
            f"using default {default_max_steps}."
        )
        return default_max_steps

    return parsed_value


def is_codex_sandbox_bypass_enabled(
    env_name=CIRCUS_CODEX_BYPASS_SANDBOX_ENV,
    env_getter=os.getenv,
):
    bypass_value = env_getter(env_name, "")
    return str(bypass_value).strip().lower() == "true"