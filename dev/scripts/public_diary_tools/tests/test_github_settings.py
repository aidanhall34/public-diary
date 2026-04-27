from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from public_diary_tools.github_settings import (
    GitHubSettingsClient,
    apply_github_settings,
    load_github_settings,
)


class FakeGitHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def default_branch(self) -> str:
        return "main"

    def branch_exists(self, branch: str) -> bool:
        return branch == "main"

    def patch_repository(self, settings: dict[str, Any]) -> None:
        self.calls.append(("repo", "", settings))

    def put_branch_protection(self, branch: str, settings: dict[str, Any]) -> None:
        self.calls.append(("branch", branch, settings))


def test_load_github_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"repository": {"delete_branch_on_merge": true}}\n')

    assert load_github_settings(path) == {"repository": {"delete_branch_on_merge": True}}


def test_apply_github_settings() -> None:
    client = FakeGitHub()
    settings = {
        "repository": {"delete_branch_on_merge": True},
        "branches": {"main": {"enforce_admins": True}},
    }

    assert apply_github_settings(settings, client) == ["repository", "branch:main"]
    assert client.calls == [
        ("repo", "", {"delete_branch_on_merge": True}),
        ("branch", "main", {"enforce_admins": True}),
    ]


def test_github_settings_client_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, str], dict[str, Any] | None, int] | tuple[str]] = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            calls.append(("raise_for_status",))

        def json(self) -> dict[str, str]:
            return {"default_branch": "main"}

    def fake_request(
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any] | None,
        timeout: int,
    ) -> FakeResponse:
        calls.append((method, url, headers, json, timeout))
        return FakeResponse()

    monkeypatch.setattr("public_diary_tools.github_settings.requests.request", fake_request)

    client = GitHubSettingsClient(
        repository="owner/repo",
        token="github-token",
        base_url="https://api.example.test",
    )
    client.patch_repository({"delete_branch_on_merge": True})
    client.put_branch_protection("main", {"enforce_admins": True})
    assert client.default_branch() == "main"
    assert client.branch_exists("main")

    assert calls == [
        (
            "PATCH",
            "https://api.example.test/repos/owner/repo",
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer github-token",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            {"delete_branch_on_merge": True},
            30,
        ),
        ("raise_for_status",),
        (
            "PUT",
            "https://api.example.test/repos/owner/repo/branches/main/protection",
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer github-token",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            {"enforce_admins": True},
            30,
        ),
        ("raise_for_status",),
        (
            "GET",
            "https://api.example.test/repos/owner/repo",
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer github-token",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            None,
            30,
        ),
        ("raise_for_status",),
        (
            "GET",
            "https://api.example.test/repos/owner/repo/branches/main",
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer github-token",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            None,
            30,
        ),
        ("raise_for_status",),
    ]


def test_apply_github_settings_rejects_invalid_shapes() -> None:
    client = FakeGitHub()
    with pytest.raises(TypeError, match="repository"):
        apply_github_settings({"repository": []}, client)

    with pytest.raises(TypeError, match="branches"):
        apply_github_settings({"branches": []}, client)

    with pytest.raises(TypeError, match="branch protection"):
        apply_github_settings({"branches": {"main": []}}, client)

    with pytest.raises(RuntimeError, match="branch not found"):
        apply_github_settings({"branches": {"missing": {}}}, client)
