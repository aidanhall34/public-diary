from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from public_diary_tools.github_settings import (
    GitHubNotFoundError,
    GitHubSettingsClient,
    apply_github_settings,
    load_github_settings,
)


class FakeGitHub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.rulesets: list[dict[str, Any]] = []

    def default_branch(self) -> str:
        return "main"

    def branch_exists(self, branch: str) -> bool:
        return branch == "main"

    def patch_repository(self, settings: dict[str, Any]) -> None:
        self.calls.append(("repo", "", settings))

    def create_pages(self, settings: dict[str, Any]) -> None:
        self.calls.append(("create-pages", "", settings))

    def update_pages(self, settings: dict[str, Any]) -> None:
        self.calls.append(("pages", "", settings))

    def put_branch_protection(self, branch: str, settings: dict[str, Any]) -> None:
        self.calls.append(("branch", branch, settings))

    def list_rulesets(self) -> list[dict[str, Any]]:
        self.calls.append(("rulesets", "", {}))
        return self.rulesets

    def create_ruleset(self, settings: dict[str, Any]) -> None:
        self.calls.append(("create-ruleset", "", settings))

    def update_ruleset(self, ruleset_id: int, settings: dict[str, Any]) -> None:
        self.calls.append(("update-ruleset", str(ruleset_id), settings))

    def delete_ruleset(self, ruleset_id: int) -> None:
        self.calls.append(("delete-ruleset", str(ruleset_id), {}))


def test_load_github_settings(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"repository": {"delete_branch_on_merge": true}}\n')

    assert load_github_settings(path) == {"repository": {"delete_branch_on_merge": True}}


def test_apply_github_settings() -> None:
    client = FakeGitHub()
    settings = {
        "repository": {"delete_branch_on_merge": True},
        "pages": {"build_type": "workflow", "cname": "notes.ah34.net", "https_enforced": True},
        "branches": {"main": {"enforce_admins": True}},
        "rulesets": [{"name": "main pull request reviews"}],
    }

    assert apply_github_settings(settings, client) == [
        "repository",
        "pages",
        "branch:main",
        "ruleset:main pull request reviews",
    ]
    assert client.calls == [
        ("repo", "", {"delete_branch_on_merge": True}),
        ("pages", "", {"build_type": "workflow", "cname": "notes.ah34.net", "https_enforced": True}),
        ("branch", "main", {"enforce_admins": True}),
        ("rulesets", "", {}),
        ("create-ruleset", "", {"name": "main pull request reviews"}),
    ]


def test_apply_github_settings_updates_existing_rulesets() -> None:
    client = FakeGitHub()
    client.rulesets = [{"id": 42, "name": "main pull request reviews"}]
    settings = {"rulesets": [{"name": "main pull request reviews", "enforcement": "active"}]}

    assert apply_github_settings(settings, client) == ["ruleset:main pull request reviews"]
    assert client.calls == [
        ("rulesets", "", {}),
        ("update-ruleset", "42", {"name": "main pull request reviews", "enforcement": "active"}),
    ]


def test_apply_github_settings_deletes_named_rulesets() -> None:
    client = FakeGitHub()
    client.rulesets = [
        {"id": 41, "name": "main"},
        {"id": 42, "name": "main pull request reviews"},
    ]
    settings = {"delete_rulesets": ["main", "missing"]}

    assert apply_github_settings(settings, client) == ["delete-ruleset:main"]
    assert client.calls == [
        ("rulesets", "", {}),
        ("delete-ruleset", "41", {}),
    ]


def test_github_settings_client_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, str], dict[str, Any] | None, int] | tuple[str]] = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            calls.append(("raise_for_status",))

        def __init__(self, url: str) -> None:
            self.url = url

        def json(self) -> dict[str, str] | list[dict[str, str | int]]:
            if self.url.endswith("/rulesets"):
                return [{"id": 42, "name": "main pull request reviews"}]
            return {"default_branch": "main"}

    def fake_request(
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any] | None,
        timeout: int,
    ) -> FakeResponse:
        calls.append((method, url, headers, json, timeout))
        return FakeResponse(url)

    monkeypatch.setattr("public_diary_tools.github_settings.requests.request", fake_request)

    client = GitHubSettingsClient(
        repository="owner/repo",
        token="github-token",
        base_url="https://api.example.test",
    )
    client.patch_repository({"delete_branch_on_merge": True})
    client.create_pages({"build_type": "workflow"})
    client.update_pages({"build_type": "workflow", "cname": "notes.ah34.net", "https_enforced": True})
    client.put_branch_protection("main", {"enforce_admins": True})
    assert client.list_rulesets() == [{"id": 42, "name": "main pull request reviews"}]
    client.create_ruleset({"name": "new ruleset"})
    client.update_ruleset(42, {"name": "main pull request reviews"})
    client.delete_ruleset(42)
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
            "POST",
            "https://api.example.test/repos/owner/repo/pages",
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer github-token",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            {"build_type": "workflow"},
            30,
        ),
        ("raise_for_status",),
        (
            "PUT",
            "https://api.example.test/repos/owner/repo/pages",
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer github-token",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            {"build_type": "workflow", "cname": "notes.ah34.net", "https_enforced": True},
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
            "https://api.example.test/repos/owner/repo/rulesets",
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
            "POST",
            "https://api.example.test/repos/owner/repo/rulesets",
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer github-token",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            {"name": "new ruleset"},
            30,
        ),
        ("raise_for_status",),
        (
            "PUT",
            "https://api.example.test/repos/owner/repo/rulesets/42",
            {
                "Accept": "application/vnd.github+json",
                "Authorization": "Bearer github-token",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            {"name": "main pull request reviews"},
            30,
        ),
        ("raise_for_status",),
        (
            "DELETE",
            "https://api.example.test/repos/owner/repo/rulesets/42",
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


def test_github_settings_client_creates_pages_site_before_update(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    client = GitHubSettingsClient(
        repository="owner/repo",
        token="github-token",
        base_url="https://api.example.test",
    )

    def fake_request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        calls.append((method, path, payload))
        if calls == [("PUT", "/pages", {"cname": "notes.ah34.net", "https_enforced": True})]:
            raise GitHubNotFoundError("missing pages site")
        return {}

    monkeypatch.setattr(client, "_request", fake_request)

    client.update_pages({"cname": "notes.ah34.net", "https_enforced": True})

    assert calls == [
        ("PUT", "/pages", {"cname": "notes.ah34.net", "https_enforced": True}),
        ("POST", "/pages", {"build_type": "workflow"}),
        ("PUT", "/pages", {"cname": "notes.ah34.net", "https_enforced": True}),
    ]


def test_apply_github_settings_rejects_invalid_shapes() -> None:
    client = FakeGitHub()
    with pytest.raises(TypeError, match="repository"):
        apply_github_settings({"repository": []}, client)

    with pytest.raises(TypeError, match="branches"):
        apply_github_settings({"branches": []}, client)

    with pytest.raises(TypeError, match="pages"):
        apply_github_settings({"pages": []}, client)

    with pytest.raises(TypeError, match="branch protection"):
        apply_github_settings({"branches": {"main": []}}, client)

    with pytest.raises(TypeError, match="rulesets"):
        apply_github_settings({"rulesets": {}}, client)

    with pytest.raises(TypeError, match="rulesets"):
        apply_github_settings({"rulesets": [{}]}, client)

    with pytest.raises(TypeError, match="delete_rulesets"):
        apply_github_settings({"delete_rulesets": {}}, client)

    with pytest.raises(TypeError, match="delete_rulesets"):
        apply_github_settings({"delete_rulesets": [1]}, client)

    with pytest.raises(RuntimeError, match="branch not found"):
        apply_github_settings({"branches": {"missing": {}}}, client)
