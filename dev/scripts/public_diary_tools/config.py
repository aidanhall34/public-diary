from __future__ import annotations

import os
from dataclasses import dataclass

from public_diary_tools.clients import GoogleApis, active_gcloud_account, configured_gcloud_project, set_gcloud_project
from public_diary_tools.envfiles import clean_existing, read_env_file
from public_diary_tools.paths import act_var_file
from public_diary_tools.prompting import prompt_value, select_option


@dataclass
class ActVars:
    gcp_workload_identity_provider: str
    gcp_service_account: str
    google_drive_root_folder_id: str
    google_drive_shared_drive_id: str
    google_workspace_user: str
    google_drive_path: str

    def as_env(self) -> dict[str, str]:
        return {
            "GCP_WORKLOAD_IDENTITY_PROVIDER": self.gcp_workload_identity_provider,
            "GCP_SERVICE_ACCOUNT": self.gcp_service_account,
            "GOOGLE_DRIVE_ROOT_FOLDER_ID": self.google_drive_root_folder_id,
            "GOOGLE_DRIVE_SHARED_DRIVE_ID": self.google_drive_shared_drive_id,
            "GOOGLE_WORKSPACE_USER": self.google_workspace_user,
            "GOOGLE_DRIVE_PATH": self.google_drive_path,
        }


def env_or_existing(name: str, existing: dict[str, str]) -> str:
    return os.environ.get(name, existing.get(name, ""))


def select_project(google: GoogleApis, input_fn=input) -> str:
    explicit = os.environ.get("GCP_PROJECT_ID")
    if explicit:
        return explicit

    configured = configured_gcloud_project()
    if configured:
        return configured

    projects = [(project_id, project_id) for project_id in google.list_projects()]
    project_id = select_option("Google Cloud project", projects, input_fn=input_fn)
    if not project_id:
        project_id = prompt_value("GCP_PROJECT_ID", input_fn=input_fn)
    set_gcloud_project(project_id)
    return project_id


def build_act_vars(google: GoogleApis, input_fn=input) -> ActVars:
    existing = clean_existing(read_env_file(act_var_file()))
    project_id = select_project(google, input_fn=input_fn)
    project_number = google.project_number(project_id)
    service_account_id = os.environ.get("SERVICE_ACCOUNT_ID", "public-diary-deploy")
    wif_pool_id = os.environ.get("WIF_POOL_ID", "github")
    wif_provider_id = os.environ.get("WIF_PROVIDER_ID", "public-diary")

    default_provider = (
        f"projects/{project_number}/locations/global/workloadIdentityPools/{wif_pool_id}/providers/{wif_provider_id}"
    )
    default_service_account = f"{service_account_id}@{project_id}.iam.gserviceaccount.com"

    shared_drive_id = env_or_existing("GOOGLE_DRIVE_SHARED_DRIVE_ID", existing)
    if not shared_drive_id:
        shared_drive_id = select_option("Google Shared Drive", google.list_shared_drives(), input_fn=input_fn)
    if not shared_drive_id:
        shared_drive_id = prompt_value("GOOGLE_DRIVE_SHARED_DRIVE_ID", input_fn=input_fn)

    root_folder_id = env_or_existing("GOOGLE_DRIVE_ROOT_FOLDER_ID", existing)
    if not root_folder_id and shared_drive_id:
        folders = google.list_top_level_folders(shared_drive_id)
        if folders:
            root_folder_id = select_option(
                "root folder, or press Enter for Shared Drive root",
                [("", "Shared Drive root"), *folders],
                input_fn=input_fn,
            )

    return ActVars(
        gcp_workload_identity_provider=prompt_value(
            "GCP_WORKLOAD_IDENTITY_PROVIDER",
            env_or_existing("GCP_WORKLOAD_IDENTITY_PROVIDER", existing) or default_provider,
            input_fn=input_fn,
        ),
        gcp_service_account=prompt_value(
            "GCP_SERVICE_ACCOUNT",
            env_or_existing("GCP_SERVICE_ACCOUNT", existing) or default_service_account,
            input_fn=input_fn,
        ),
        google_drive_root_folder_id=root_folder_id,
        google_drive_shared_drive_id=shared_drive_id,
        google_workspace_user=prompt_value(
            "GOOGLE_WORKSPACE_USER",
            env_or_existing("GOOGLE_WORKSPACE_USER", existing),
            input_fn=input_fn,
        ),
        google_drive_path=prompt_value(
            "GOOGLE_DRIVE_PATH",
            env_or_existing("GOOGLE_DRIVE_PATH", existing) or "obs-notes/obs-notes",
            input_fn=input_fn,
        ),
    )


def active_user_member() -> str:
    return f"user:{active_gcloud_account()}"
