from __future__ import annotations

import base64
import logging
import os
import subprocess
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, cast

import google.auth.transport.requests
from github import Github
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
LOGGER = logging.getLogger(__name__)


def gcloud_value(*args: str) -> str:
    return subprocess.check_output(("gcloud", *args), text=True).strip()


def gcloud_token(scopes: list[str]) -> str:
    return gcloud_value("auth", "print-access-token", f"--scopes={','.join(scopes)}")


def gcloud_impersonated_token(service_account: str) -> str:
    return gcloud_value(
        "auth",
        "print-access-token",
        f"--impersonate-service-account={service_account}",
    )


def active_gcloud_account() -> str:
    return gcloud_value("config", "get-value", "account")


def configured_gcloud_project() -> str:
    return gcloud_value("config", "get-value", "project")


def set_gcloud_project(project_id: str) -> None:
    subprocess.check_call(("gcloud", "config", "set", "project", project_id))


def credentials_from_token(token: str) -> Credentials:
    return Credentials(token=token)  # type: ignore[no-untyped-call]


@dataclass
class GoogleApis:
    token: str | None = None

    @cached_property
    def credentials(self) -> Credentials:
        return credentials_from_token(self.token or gcloud_token([CLOUD_PLATFORM_SCOPE, DRIVE_SCOPE]))

    def service(self, name: str, version: str) -> Any:
        return build(name, version, credentials=self.credentials, cache_discovery=False)

    def list_projects(self) -> list[str]:
        service = self.service("cloudresourcemanager", "v1")
        response = service.projects().list().execute()
        return [project["projectId"] for project in response.get("projects", [])]

    def create_project(self, project_id: str, name: str) -> None:
        service = self.service("cloudresourcemanager", "v1")
        service.projects().create(body={"projectId": project_id, "name": name}).execute()

    def project_number(self, project_id: str) -> str:
        service = self.service("cloudresourcemanager", "v1")
        response = service.projects().get(projectId=project_id).execute()
        return str(response["projectNumber"])

    def enable_services(self, project_id: str, services: list[str]) -> None:
        service = self.service("serviceusage", "v1")
        for api_name in services:
            LOGGER.debug("enabling google api %s for project %s", api_name, project_id)
            service.services().enable(name=f"projects/{project_id}/services/{api_name}").execute()

    def service_account_exists(self, project_id: str, email: str) -> bool:
        service = self.service("iam", "v1")
        try:
            service.projects().serviceAccounts().get(name=f"projects/{project_id}/serviceAccounts/{email}").execute()
        except Exception:  # noqa: BLE001 - Google client raises varied HTTP exceptions.
            return False
        return True

    def create_service_account(self, project_id: str, account_id: str, display_name: str) -> None:
        service = self.service("iam", "v1")
        service.projects().serviceAccounts().create(
            name=f"projects/{project_id}",
            body={"accountId": account_id, "serviceAccount": {"displayName": display_name}},
        ).execute()

    def workload_identity_pool_exists(self, project_number: str, pool_id: str) -> bool:
        service = self.service("iam", "v1")
        name = f"projects/{project_number}/locations/global/workloadIdentityPools/{pool_id}"
        try:
            service.projects().locations().workloadIdentityPools().get(name=name).execute()
        except Exception:  # noqa: BLE001 - Google client raises varied HTTP exceptions.
            return False
        return True

    def create_workload_identity_pool(self, project_number: str, pool_id: str, display_name: str) -> None:
        service = self.service("iam", "v1")
        service.projects().locations().workloadIdentityPools().create(
            parent=f"projects/{project_number}/locations/global",
            workloadIdentityPoolId=pool_id,
            body={"displayName": display_name},
        ).execute()

    def workload_identity_provider_exists(self, project_number: str, pool_id: str, provider_id: str) -> bool:
        service = self.service("iam", "v1")
        name = (
            f"projects/{project_number}/locations/global/workloadIdentityPools/{pool_id}/providers/{provider_id}"
        )
        try:
            service.projects().locations().workloadIdentityPools().providers().get(name=name).execute()
        except Exception:  # noqa: BLE001 - Google client raises varied HTTP exceptions.
            return False
        return True

    def create_workload_identity_provider(
        self,
        project_number: str,
        pool_id: str,
        provider_id: str,
        repo: str,
        display_name: str,
    ) -> None:
        service = self.service("iam", "v1")
        service.projects().locations().workloadIdentityPools().providers().create(
            parent=f"projects/{project_number}/locations/global/workloadIdentityPools/{pool_id}",
            workloadIdentityPoolProviderId=provider_id,
            body={
                "displayName": display_name,
                "attributeMapping": {
                    "google.subject": "assertion.sub",
                    "attribute.repository": "assertion.repository",
                    "attribute.repository_owner": "assertion.repository_owner",
                },
                "attributeCondition": f"assertion.repository=='{repo}'",
                "oidc": {"issuerUri": "https://token.actions.githubusercontent.com"},
            },
        ).execute()

    def add_service_account_binding(self, project_id: str, email: str, role: str, member: str) -> None:
        LOGGER.debug("adding service account binding role=%s member=%s", role, member)
        service = self.service("iam", "v1")
        resource = f"projects/{project_id}/serviceAccounts/{email}"
        policy = service.projects().serviceAccounts().getIamPolicy(resource=resource).execute()
        bindings = policy.setdefault("bindings", [])
        for binding in bindings:
            if binding["role"] == role:
                members = binding.setdefault("members", [])
                if member not in members:
                    members.append(member)
                break
        else:
            bindings.append({"role": role, "members": [member]})
        service.projects().serviceAccounts().setIamPolicy(resource=resource, body={"policy": policy}).execute()

    def list_shared_drives(self) -> list[tuple[str, str]]:
        LOGGER.debug("listing shared drives")
        service = self.service("drive", "v3")
        drives: list[tuple[str, str]] = []
        page_token = None
        while True:
            response = (
                service.drives()
                .list(pageSize=100, pageToken=page_token, fields="drives(id,name),nextPageToken")
                .execute()
            )
            drives.extend((drive["id"], drive["name"]) for drive in response.get("drives", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return drives

    def list_my_drive_top_level_folders(self) -> list[tuple[str, str]]:
        service = self.service("drive", "v3")
        response = (
            service.files()
            .list(
                corpora="user",
                pageSize=100,
                fields="files(id,name)",
                q=(
                    "'root' in parents "
                    "and mimeType = 'application/vnd.google-apps.folder' "
                    "and trashed = false"
                ),
            )
            .execute()
        )
        return [(folder["id"], folder["name"]) for folder in response.get("files", [])]

    def list_child_folders(self, parent_id: str, shared_drive_id: str = "") -> list[tuple[str, str]]:
        LOGGER.debug("listing child folders parent_id=%s shared_drive_id=%s", parent_id, shared_drive_id)
        service = self.service("drive", "v3")
        request = {
            "pageSize": 100,
            "fields": "files(id,name)",
            "q": (
                f"'{parent_id}' in parents "
                "and mimeType = 'application/vnd.google-apps.folder' "
                "and trashed = false"
            ),
        }
        if shared_drive_id:
            request.update(
                {
                    "corpora": "drive",
                    "driveId": shared_drive_id,
                    "includeItemsFromAllDrives": True,
                    "supportsAllDrives": True,
                },
            )
        response = service.files().list(**request).execute()
        return [(folder["id"], folder["name"]) for folder in response.get("files", [])]

    def folder_info(self, folder_id: str) -> tuple[str, str]:
        service = self.service("drive", "v3")
        response = (
            service.files()
            .get(fileId=folder_id, supportsAllDrives=True, fields="id,name,parents")
            .execute()
        )
        parents = response.get("parents", [])
        return str(response.get("name", folder_id)), str(parents[0]) if parents else ""

    def list_top_level_folders(self, shared_drive_id: str) -> list[tuple[str, str]]:
        service = self.service("drive", "v3")
        response = (
            service.files()
            .list(
                corpora="drive",
                driveId=shared_drive_id,
                includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                pageSize=100,
                fields="files(id,name)",
                q=(
                    f"'{shared_drive_id}' in parents "
                    "and mimeType = 'application/vnd.google-apps.folder' "
                    "and trashed = false"
                ),
            )
            .execute()
        )
        return [(folder["id"], folder["name"]) for folder in response.get("files", [])]

    def grant_drive_permission(self, target_id: str, email: str, role: str) -> dict[str, str]:
        service = self.service("drive", "v3")
        return cast(
            dict[str, str],
            service.permissions()
            .create(
                fileId=target_id,
                supportsAllDrives=True,
                sendNotificationEmail=False,
                fields="id,type,role,emailAddress",
                body={"type": "user", "role": role, "emailAddress": email},
            )
            .execute(),
        )


@dataclass
class GithubClient:
    repository: str
    token: str | None = None

    @cached_property
    def repo(self) -> Any:
        token = self.token or os.environ.get("GITHUB_TOKEN") or gcloud_fallback_error("GITHUB_TOKEN")
        return Github(token).get_repo(self.repository)

    def set_variable(self, name: str, value: str) -> None:
        if not value:
            self.delete_variable(name)
            return
        try:
            variable = self.repo.get_variable(name)
            variable.edit(value)
        except Exception:  # noqa: BLE001 - PyGithub raises UnknownObjectException for missing vars.
            self.repo.create_variable(name, value)

    def delete_variable(self, name: str) -> None:
        try:
            variable = self.repo.get_variable(name)
        except Exception:  # noqa: BLE001 - Missing optional empty variables are already in the desired state.
            LOGGER.debug("github variable %s is already absent", name)
            return
        delete = getattr(variable, "delete", None)
        if callable(delete):
            delete()
            return
        repo_delete = getattr(self.repo, "delete_variable", None)
        if callable(repo_delete):
            repo_delete(name)
            return
        raise RuntimeError(f"PyGithub does not expose a delete operation for variable {name}.")

    def set_secret(self, name: str, value: str) -> None:
        self.repo.create_secret(name, value)


def gcloud_fallback_error(name: str) -> str:
    raise RuntimeError(f"{name} is required")


def repository_from_gh() -> str:
    return subprocess.check_output(
        ("gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"),
        text=True,
    ).strip()


def github_token_from_gh() -> str:
    return subprocess.check_output(("gh", "auth", "token"), text=True).strip()


def token_from_service_account_key(path: Path, scopes: list[str]) -> str:
    credentials = cast(
        ServiceAccountCredentials,
        ServiceAccountCredentials.from_service_account_file(str(path), scopes=scopes),  # type: ignore[no-untyped-call]
    )
    credentials.refresh(google.auth.transport.requests.Request())  # type: ignore[no-untyped-call]
    if not credentials.token:
        raise RuntimeError("Service account token refresh did not return a token")
    return str(credentials.token)


def decode_basic_auth(value: str) -> tuple[str, str]:
    decoded = base64.b64decode(value).decode()
    username, password = decoded.split(":", 1)
    return username, password
