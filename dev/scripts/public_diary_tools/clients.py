from __future__ import annotations

import base64
import os
import subprocess
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any

import google.auth.transport.requests
from github import Github
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from googleapiclient.discovery import build

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def gcloud_value(*args: str) -> str:
    return subprocess.check_output(("gcloud", *args), text=True).strip()


def gcloud_token(scopes: list[str]) -> str:
    return gcloud_value("auth", "print-access-token", f"--scopes={','.join(scopes)}")


def gcloud_impersonated_token(service_account: str, scopes: list[str]) -> str:
    return gcloud_value(
        "auth",
        "print-access-token",
        f"--impersonate-service-account={service_account}",
        f"--scopes={','.join(scopes)}",
    )


def active_gcloud_account() -> str:
    return gcloud_value("config", "get-value", "account")


def configured_gcloud_project() -> str:
    return gcloud_value("config", "get-value", "project")


def set_gcloud_project(project_id: str) -> None:
    subprocess.check_call(("gcloud", "config", "set", "project", project_id))


def credentials_from_token(token: str) -> Credentials:
    return Credentials(token=token)


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

    def project_number(self, project_id: str) -> str:
        service = self.service("cloudresourcemanager", "v1")
        response = service.projects().get(projectId=project_id).execute()
        return str(response["projectNumber"])

    def enable_services(self, project_id: str, services: list[str]) -> None:
        service = self.service("serviceusage", "v1")
        for api_name in services:
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

    def add_service_account_binding(self, project_id: str, email: str, role: str, member: str) -> None:
        service = self.service("iam", "v1")
        resource = f"projects/{project_id}/serviceAccounts/{email}"
        policy = service.projects().serviceAccounts().getIamPolicy(resource=resource, body={}).execute()
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
        service = self.service("drive", "v3")
        response = service.drives().list(pageSize=100, fields="drives(id,name),nextPageToken").execute()
        return [(drive["id"], drive["name"]) for drive in response.get("drives", [])]

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
        return (
            service.permissions()
            .create(
                fileId=target_id,
                supportsAllDrives=True,
                sendNotificationEmail=False,
                fields="id,type,role,emailAddress",
                body={"type": "user", "role": role, "emailAddress": email},
            )
            .execute()
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
        try:
            variable = self.repo.get_variable(name)
            variable.edit(value)
        except Exception:  # noqa: BLE001 - PyGithub raises UnknownObjectException for missing vars.
            self.repo.create_variable(name, value)

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
    credentials = ServiceAccountCredentials.from_service_account_file(str(path), scopes=scopes)
    credentials.refresh(google.auth.transport.requests.Request())
    if not credentials.token:
        raise RuntimeError("Service account token refresh did not return a token")
    return credentials.token


def decode_basic_auth(value: str) -> tuple[str, str]:
    decoded = base64.b64decode(value).decode()
    username, password = decoded.split(":", 1)
    return username, password
