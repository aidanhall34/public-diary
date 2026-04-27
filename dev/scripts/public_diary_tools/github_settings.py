from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import requests
from requests import HTTPError

from public_diary_tools.progress import track_web_request

DEFAULT_SETTINGS_FILE = Path(".github/config/repository-permissions.json")


class GitHubSettingsApi(Protocol):
    def default_branch(self) -> str: ...

    def branch_exists(self, branch: str) -> bool: ...

    def patch_repository(self, settings: dict[str, Any]) -> None: ...

    def put_branch_protection(self, branch: str, settings: dict[str, Any]) -> None: ...

    def list_rulesets(self) -> list[dict[str, Any]]: ...

    def create_ruleset(self, settings: dict[str, Any]) -> None: ...

    def update_ruleset(self, ruleset_id: int, settings: dict[str, Any]) -> None: ...

    def delete_ruleset(self, ruleset_id: int) -> None: ...


@dataclass
class GitHubSettingsClient:
    repository: str
    token: str
    base_url: str = "https://api.github.com"

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        with track_web_request():
            response = requests.request(
                method,
                f"{self.base_url}/repos/{self.repository}{path}",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                json=payload,
                timeout=30,
            )
        try:
            response.raise_for_status()
        except HTTPError as exc:
            if response.status_code == 404:
                raise RuntimeError(
                    "GitHub returned 404 while applying repository settings. "
                    "Confirm the repository exists, the branch exists, and your GitHub token has repository "
                    "administration permission. Run `gh auth refresh -s repo -s workflow` and ensure your user "
                    "can administer the repository.",
                ) from exc
            raise
        try:
            return response.json()
        except ValueError:
            return {}

    def default_branch(self) -> str:
        response = cast(dict[str, Any], self._request("GET", ""))
        return str(response.get("default_branch", "main"))

    def branch_exists(self, branch: str) -> bool:
        try:
            self._request("GET", f"/branches/{branch}")
        except RuntimeError:
            return False
        return True

    def patch_repository(self, settings: dict[str, Any]) -> None:
        self._request("PATCH", "", settings)

    def put_branch_protection(self, branch: str, settings: dict[str, Any]) -> None:
        self._request("PUT", f"/branches/{branch}/protection", settings)

    def list_rulesets(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._request("GET", "/rulesets"))

    def create_ruleset(self, settings: dict[str, Any]) -> None:
        self._request("POST", "/rulesets", settings)

    def update_ruleset(self, ruleset_id: int, settings: dict[str, Any]) -> None:
        self._request("PUT", f"/rulesets/{ruleset_id}", settings)

    def delete_ruleset(self, ruleset_id: int) -> None:
        self._request("DELETE", f"/rulesets/{ruleset_id}")


def load_github_settings(path: Path = DEFAULT_SETTINGS_FILE) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text()))


def apply_github_settings(settings: dict[str, Any], client: GitHubSettingsApi) -> list[str]:
    applied = []
    repository_settings = settings.get("repository", {})
    if not isinstance(repository_settings, dict):
        raise TypeError("repository settings must be an object")
    if repository_settings:
        client.patch_repository(repository_settings)
        applied.append("repository")

    branch_settings = settings.get("branches", {})
    if not isinstance(branch_settings, dict):
        raise TypeError("branches settings must be an object")
    for branch, protection in branch_settings.items():
        if not isinstance(branch, str) or not isinstance(protection, dict):
            raise TypeError("branch protection settings must be keyed objects")
        if branch == "$default":
            branch = client.default_branch()
        if not client.branch_exists(branch):
            raise RuntimeError(
                f"GitHub branch not found: {branch}. Push the branch before applying protection, "
                "or use `$default` in .github/config/repository-permissions.json.",
            )
        client.put_branch_protection(branch, protection)
        applied.append(f"branch:{branch}")

    rulesets = settings.get("rulesets", [])
    if not isinstance(rulesets, list):
        raise TypeError("rulesets settings must be an array")
    if rulesets:
        existing_rulesets = {
            str(ruleset["name"]): int(ruleset["id"])
            for ruleset in client.list_rulesets()
            if isinstance(ruleset.get("name"), str) and isinstance(ruleset.get("id"), int)
        }
        for ruleset in rulesets:
            if not isinstance(ruleset, dict) or not isinstance(ruleset.get("name"), str):
                raise TypeError("rulesets settings must be named objects")
            ruleset_name = str(ruleset["name"])
            if ruleset_name in existing_rulesets:
                client.update_ruleset(existing_rulesets[ruleset_name], ruleset)
            else:
                client.create_ruleset(ruleset)
            applied.append(f"ruleset:{ruleset_name}")

    delete_rulesets = settings.get("delete_rulesets", [])
    if not isinstance(delete_rulesets, list):
        raise TypeError("delete_rulesets settings must be an array")
    if delete_rulesets:
        rulesets_by_name = {
            str(ruleset["name"]): int(ruleset["id"])
            for ruleset in client.list_rulesets()
            if isinstance(ruleset.get("name"), str) and isinstance(ruleset.get("id"), int)
        }
        for ruleset_name in delete_rulesets:
            if not isinstance(ruleset_name, str):
                raise TypeError("delete_rulesets settings must contain names")
            ruleset_id = rulesets_by_name.get(ruleset_name)
            if ruleset_id is not None:
                client.delete_ruleset(ruleset_id)
                applied.append(f"delete-ruleset:{ruleset_name}")
    return applied
