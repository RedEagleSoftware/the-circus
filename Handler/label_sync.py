import json
import subprocess

from Handler.workflow_labels import REQUIRED_WORKFLOW_LABELS


def run_gh_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def sync_required_labels(repo, run_command=run_gh_command):
    if not repo:
        print("[LabelSync] Error: CIRCUS_REPO is required for label synchronization.")
        return False

    print(f"[LabelSync] Loading labels from '{repo}'...")
    list_cmd = ["gh", "label", "list", "--repo", repo, "--limit", "500", "--json", "name,color,description"]
    exit_code, stdout, stderr = run_command(list_cmd)
    if exit_code != 0:
        print(f"[LabelSync] Failed to list labels for '{repo}'.")
        if stderr:
            print(f"[LabelSync] gh stderr: {stderr}")
        return False

    try:
        existing_labels = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        print("[LabelSync] Failed to parse `gh label list` output as JSON.")
        return False

    existing_by_name = {label["name"]: label for label in existing_labels}

    created = 0
    updated = 0
    warnings = 0

    for name, spec in REQUIRED_WORKFLOW_LABELS.items():
        desired_color = spec["color"]
        desired_description = spec["description"]
        existing = existing_by_name.get(name)

        if existing is None:
            print(f"[LabelSync] Missing label '{name}'; creating.")
            create_cmd = [
                "gh",
                "label",
                "create",
                name,
                "--repo",
                repo,
                "--color",
                desired_color,
                "--description",
                desired_description,
            ]
            create_code, _, create_stderr = run_command(create_cmd)
            if create_code == 0:
                created += 1
                continue

            create_error = (create_stderr or "").lower()
            if "already exists" in create_error:
                print(
                    f"[LabelSync] Label '{name}' already exists during create attempt; continuing to reconcile settings."
                )
                existing = {"name": name, "color": "", "description": ""}
                warnings += 1
            else:
                print(f"[LabelSync] Warning: failed to create label '{name}'.")
                if create_stderr:
                    print(f"[LabelSync] gh stderr: {create_stderr}")
                warnings += 1
                continue

        current_color = (existing.get("color") or "").lower()
        current_description = existing.get("description") or ""
        color_mismatch = current_color != desired_color.lower()
        description_mismatch = current_description != desired_description

        if color_mismatch or description_mismatch:
            print(
                f"[LabelSync] Updating label '{name}': "
                f"color '{current_color or '<empty>'}' -> '{desired_color.lower()}', "
                f"description mismatch={description_mismatch}."
            )
            edit_cmd = [
                "gh",
                "label",
                "edit",
                name,
                "--repo",
                repo,
                "--color",
                desired_color,
                "--description",
                desired_description,
            ]
            edit_code, _, edit_stderr = run_command(edit_cmd)
            if edit_code == 0:
                updated += 1
            else:
                print(f"[LabelSync] Warning: failed to update label '{name}'.")
                if edit_stderr:
                    print(f"[LabelSync] gh stderr: {edit_stderr}")
                warnings += 1
        else:
            print(f"[LabelSync] Label '{name}' already matches expected configuration.")

    print(
        f"[LabelSync] Done for '{repo}'. Managed labels={len(REQUIRED_WORKFLOW_LABELS)}, "
        f"created={created}, updated={updated}, warnings={warnings}."
    )
    print("[LabelSync] Unknown labels were not modified.")
    return warnings == 0
