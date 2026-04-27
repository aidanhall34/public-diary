from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from public_diary_tools.clients import (
    active_gcloud_account,
    configured_gcloud_project,
    repository_from_gh,
    set_gcloud_project,
)
from public_diary_tools.envfiles import clean_existing, read_env_file
from public_diary_tools.paths import act_var_file
from public_diary_tools.prompting import bail_note, info, prompt_setting, prompt_yes_no, success


class GoogleConfigApi(Protocol):
    def list_projects(self) -> list[str]: ...

    def create_project(self, project_id: str, name: str) -> None: ...

    def project_number(self, project_id: str) -> str: ...

    def list_shared_drives(self) -> list[tuple[str, str]]: ...

    def list_my_drive_top_level_folders(self) -> list[tuple[str, str]]: ...

    def list_child_folders(self, parent_id: str, shared_drive_id: str = "") -> list[tuple[str, str]]: ...

    def folder_info(self, folder_id: str) -> tuple[str, str]: ...

    def list_top_level_folders(self, shared_drive_id: str) -> list[tuple[str, str]]: ...


@dataclass
class ActVars:
    gcp_workload_identity_provider: str
    gcp_service_account: str
    google_drive_root_folder_id: str
    google_drive_shared_drive_id: str
    google_workspace_delegation_enabled: str
    google_workspace_user: str
    google_drive_path: str

    def as_env(self) -> dict[str, str]:
        return {
            "GCP_WORKLOAD_IDENTITY_PROVIDER": self.gcp_workload_identity_provider,
            "GCP_SERVICE_ACCOUNT": self.gcp_service_account,
            "GOOGLE_DRIVE_ROOT_FOLDER_ID": self.google_drive_root_folder_id,
            "GOOGLE_DRIVE_SHARED_DRIVE_ID": self.google_drive_shared_drive_id,
            "GOOGLE_WORKSPACE_DELEGATION_ENABLED": self.google_workspace_delegation_enabled,
            "GOOGLE_WORKSPACE_USER": self.google_workspace_user,
            "GOOGLE_DRIVE_PATH": self.google_drive_path,
        }


@dataclass(frozen=True)
class DrivePathSelection:
    root_folder_id: str
    path: str


def env_or_existing(name: str, existing: dict[str, str]) -> str:
    return os.environ.get(name, existing.get(name, ""))


def _is_set(value: str) -> bool:
    return bool(value and value != "(unset)")


def _can_use_workspace_delegation(user: str) -> bool:
    domain = user.rsplit("@", 1)[-1].lower()
    return domain not in {"gmail.com", "googlemail.com"}


def _drive_path_suggestions(root_folder_id: str) -> list[tuple[str, str]]:
    if not root_folder_id:
        return [
            ("obs-notes/obs-notes", "Default Obsidian vault path"),
            ("", "Use the selected Drive root directly"),
        ]
    return [("", "Use the selected Drive root folder directly")]


def _folder_info_or_default(google: GoogleConfigApi, folder_id: str, default_name: str = "") -> tuple[str, str]:
    try:
        return google.folder_info(folder_id)
    except Exception:  # noqa: BLE001 - Drive IDs can be shared drive IDs, which are not files.
        return default_name or folder_id, ""


def browse_drive_path(
    google: GoogleConfigApi,
    shared_drive_id: str,
    root_folder_id: str,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> DrivePathSelection:
    start_folder_id = root_folder_id or shared_drive_id
    if not start_folder_id:
        return DrivePathSelection(
            root_folder_id="",
            path=prompt_setting(
                "GOOGLE_DRIVE_PATH",
                suggestions=_drive_path_suggestions(root_folder_id),
                input_fn=input_fn,
                output_fn=output_fn,
                custom_label="Custom Drive path",
            ),
        )

    start_name, start_parent_id = _folder_info_or_default(
        google,
        start_folder_id,
        "Shared Drive root" if not root_folder_id and shared_drive_id else "Selected root",
    )
    folder_stack: list[tuple[str, str, str]] = [(start_folder_id, start_name, start_parent_id)]
    while True:
        current_id, current_name, current_parent_id = folder_stack[-1]
        current_path = "/".join(name for _, name, _ in folder_stack[1:])
        current_display = current_path or f". ({current_name})"
        info(f"Current Google Drive folder: {current_display}", output_fn=output_fn)
        child_folders = google.list_child_folders(current_id, shared_drive_id)
        suggestions = [(".", f"Select current folder: {current_display}")]
        if len(folder_stack) > 1 or current_parent_id:
            suggestions.append(("..", "Move up one folder"))
        suggestions.extend(child_folders)
        selected = prompt_setting(
            "GOOGLE_DRIVE_PATH",
            suggestions=suggestions,
            input_fn=input_fn,
            output_fn=output_fn,
            custom_label="Enter path manually",
        )
        if selected == ".":
            selected_root = "" if not root_folder_id and folder_stack[0][0] == shared_drive_id else folder_stack[0][0]
            return DrivePathSelection(root_folder_id=selected_root, path=current_path)
        if selected == "..":
            if len(folder_stack) > 1:
                folder_stack.pop()
                continue
            parent_name, parent_parent_id = _folder_info_or_default(google, current_parent_id)
            folder_stack = [(current_parent_id, parent_name, parent_parent_id)]
            continue
        child_names = dict(child_folders)
        if selected in child_names:
            _, child_parent_id = _folder_info_or_default(google, selected, child_names[selected])
            folder_stack.append((selected, child_names[selected], child_parent_id))
            continue
        selected_root = "" if not root_folder_id and folder_stack[0][0] == shared_drive_id else folder_stack[0][0]
        return DrivePathSelection(root_folder_id=selected_root, path=selected)


def select_project(
    google: GoogleConfigApi,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> str:
    explicit = os.environ.get("GCP_PROJECT_ID")
    if explicit:
        success(f"Using GCP_PROJECT_ID: {explicit}", output_fn=output_fn)
        return explicit

    configured = configured_gcloud_project()
    if _is_set(configured):
        success(f"Using gcloud configured project: {configured}", output_fn=output_fn)
        return configured

    existing_projects = google.list_projects()
    project_id = prompt_setting(
        "GCP_PROJECT_ID",
        suggestions=[(project_id, project_id) for project_id in existing_projects],
        input_fn=input_fn,
        output_fn=output_fn,
        required=True,
        custom_label="Custom project ID",
    )
    if project_id not in existing_projects:
        google.create_project(project_id, os.environ.get("GCP_PROJECT_NAME", "Obsidian publishing"))
    set_gcloud_project(project_id)
    return project_id


def select_repository(input_fn: Callable[[str], str] = input, output_fn: Callable[[str], None] = print) -> str:
    explicit = os.environ.get("GITHUB_REPOSITORY")
    if explicit:
        success(f"Using GITHUB_REPOSITORY: {explicit}", output_fn=output_fn)
        return explicit
    try:
        default = repository_from_gh()
    except Exception:  # noqa: BLE001 - gh can fail outside a GitHub repository.
        default = ""
    return prompt_setting(
        "GITHUB_REPOSITORY",
        suggestions=[(default, "Current repository")] if default else [],
        input_fn=input_fn,
        output_fn=output_fn,
        required=True,
        custom_label="Custom OWNER/REPO",
    )


def prompt_wif_defaults(
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> None:
    defaults = {
        "SERVICE_ACCOUNT_ID": os.environ.get("SERVICE_ACCOUNT_ID", "public-diary-deploy"),
        "WIF_POOL_ID": os.environ.get("WIF_POOL_ID", "github"),
        "WIF_PROVIDER_ID": os.environ.get("WIF_PROVIDER_ID", "public-diary"),
    }
    info("Default Workload Identity settings:", output_fn=output_fn)
    for name, value in defaults.items():
        output_fn(f"  {name}={value}")
    bail_note(output_fn=output_fn)
    if prompt_yes_no("Use these defaults?", input_fn=input_fn, output_fn=output_fn):
        return
    os.environ["SERVICE_ACCOUNT_ID"] = prompt_setting(
        "SERVICE_ACCOUNT_ID",
        suggestions=[(defaults["SERVICE_ACCOUNT_ID"], "Default service account ID")],
        input_fn=input_fn,
        output_fn=output_fn,
        required=True,
    )
    os.environ["WIF_POOL_ID"] = prompt_setting(
        "WIF_POOL_ID",
        suggestions=[(defaults["WIF_POOL_ID"], "Default pool ID")],
        input_fn=input_fn,
        output_fn=output_fn,
        required=True,
    )
    os.environ["WIF_PROVIDER_ID"] = prompt_setting(
        "WIF_PROVIDER_ID",
        suggestions=[(defaults["WIF_PROVIDER_ID"], "Default provider ID")],
        input_fn=input_fn,
        output_fn=output_fn,
        required=True,
    )


def build_act_vars(
    google: GoogleConfigApi,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> ActVars:
    existing = clean_existing(read_env_file(act_var_file()))
    project_id = select_project(google, input_fn=input_fn, output_fn=output_fn)
    project_number = google.project_number(project_id)
    prompt_wif_defaults(input_fn=input_fn, output_fn=output_fn)
    service_account_id = os.environ.get("SERVICE_ACCOUNT_ID", "public-diary-deploy")
    wif_pool_id = os.environ.get("WIF_POOL_ID", "github")
    wif_provider_id = os.environ.get("WIF_PROVIDER_ID", "public-diary")

    default_provider = (
        f"projects/{project_number}/locations/global/workloadIdentityPools/{wif_pool_id}/providers/{wif_provider_id}"
    )
    default_service_account = f"{service_account_id}@{project_id}.iam.gserviceaccount.com"

    shared_drive_id = env_or_existing("GOOGLE_DRIVE_SHARED_DRIVE_ID", existing)
    if shared_drive_id:
        success(f"Using GOOGLE_DRIVE_SHARED_DRIVE_ID: {shared_drive_id}", output_fn=output_fn)
    else:
        shared_drives = google.list_shared_drives()
        if shared_drives:
            shared_drive_id = prompt_setting(
                "GOOGLE_DRIVE_SHARED_DRIVE_ID",
                suggestions=[*shared_drives, ("", "No Shared Drive / use My Drive")],
                input_fn=input_fn,
                output_fn=output_fn,
                custom_label="Custom Shared Drive ID",
            )
        else:
            info(
                "No Shared Drives were visible to the authenticated Google account; using My Drive folder discovery.",
                output_fn=output_fn,
            )

    folder_suggestions = (
        [("", "Shared Drive root"), *google.list_top_level_folders(shared_drive_id)]
        if shared_drive_id
        else google.list_my_drive_top_level_folders()
    )
    root_folder_id = prompt_setting(
        "GOOGLE_DRIVE_ROOT_FOLDER_ID",
        current=env_or_existing("GOOGLE_DRIVE_ROOT_FOLDER_ID", existing),
        suggestions=folder_suggestions,
        input_fn=input_fn,
        output_fn=output_fn,
        required=not shared_drive_id,
        custom_label="Custom folder ID",
    )
    drive_path = env_or_existing("GOOGLE_DRIVE_PATH", existing)
    if drive_path:
        success(f"Using GOOGLE_DRIVE_PATH: {drive_path}", output_fn=output_fn)
    else:
        drive_selection = browse_drive_path(
            google,
            shared_drive_id,
            root_folder_id,
            input_fn=input_fn,
            output_fn=output_fn,
        )
        root_folder_id = drive_selection.root_folder_id
        drive_path = drive_selection.path

    if shared_drive_id:
        google_workspace_user = ""
        google_workspace_delegation_enabled = ""
        if env_or_existing("GOOGLE_WORKSPACE_USER", existing):
            info(
                "Ignoring GOOGLE_WORKSPACE_USER because GOOGLE_DRIVE_SHARED_DRIVE_ID is set.",
                output_fn=output_fn,
            )
    else:
        google_workspace_user = prompt_setting(
            "GOOGLE_WORKSPACE_USER",
            current=env_or_existing("GOOGLE_WORKSPACE_USER", existing),
            suggestions=[
                ("", "No Workspace subject"),
                (active_gcloud_account(), "Logged-in gcloud user"),
            ],
            input_fn=input_fn,
            output_fn=output_fn,
            custom_label="Custom Workspace user",
        )
        existing_delegation_enabled = env_or_existing("GOOGLE_WORKSPACE_DELEGATION_ENABLED", existing) == "true"
        can_use_workspace_delegation = _can_use_workspace_delegation(google_workspace_user)
        google_workspace_delegation_enabled = (
            "true" if google_workspace_user and existing_delegation_enabled and can_use_workspace_delegation else ""
        )
        if google_workspace_user and not existing_delegation_enabled:
            info(
                "Leaving GOOGLE_WORKSPACE_DELEGATION_ENABLED disabled. Enable it only after configuring "
                "domain-wide delegation in Google Workspace Admin Console.",
                output_fn=output_fn,
            )
        if google_workspace_user and not can_use_workspace_delegation:
            info(
                "Ignoring GOOGLE_WORKSPACE_DELEGATION_ENABLED because consumer Gmail accounts do not support "
                "domain-wide delegation. Share the Drive folder with the service account instead.",
                output_fn=output_fn,
            )

    return ActVars(
        gcp_workload_identity_provider=prompt_setting(
            "GCP_WORKLOAD_IDENTITY_PROVIDER",
            current=env_or_existing("GCP_WORKLOAD_IDENTITY_PROVIDER", existing),
            suggestions=[(default_provider, "Default Workload Identity provider")],
            input_fn=input_fn,
            output_fn=output_fn,
            required=True,
            custom_label="Custom provider resource name",
        ),
        gcp_service_account=prompt_setting(
            "GCP_SERVICE_ACCOUNT",
            current=env_or_existing("GCP_SERVICE_ACCOUNT", existing),
            suggestions=[(default_service_account, "Default deploy service account")],
            input_fn=input_fn,
            output_fn=output_fn,
            required=True,
            custom_label="Custom service account email",
        ),
        google_drive_root_folder_id=root_folder_id,
        google_drive_shared_drive_id=shared_drive_id,
        google_workspace_delegation_enabled=google_workspace_delegation_enabled,
        google_workspace_user=google_workspace_user,
        google_drive_path=drive_path,
    )


def active_user_member() -> str:
    return f"user:{active_gcloud_account()}"
