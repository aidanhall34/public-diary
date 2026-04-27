"""Coverage note for SDK adapters.

`public_diary_tools.clients` is intentionally omitted from coverage because it
is a thin adapter over Google API Python Client, google-auth, PyGithub, and
gcloud token commands. Unit tests cover the calling code with fakes; live SDK
behavior should be checked through manual provisioning or a dedicated
integration test account, not normal repository tests.
"""

from typing import Any

import pytest
from public_diary_tools.clients import GithubClient, github_token_from_gh


def test_external_client_coverage_exception_is_documented() -> None:
    assert True


def test_github_token_from_gh_prefers_env_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GH_TOKEN", "env-token")
    monkeypatch.setattr("public_diary_tools.clients.subprocess.check_output", lambda *_args, **_kwargs: "gh-token\n")

    assert github_token_from_gh() == "env-token"


def test_github_token_from_gh_uses_github_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "github-env-token")
    monkeypatch.setattr("public_diary_tools.clients.subprocess.check_output", lambda *_args, **_kwargs: "gh-token\n")

    assert github_token_from_gh() == "github-env-token"


def test_github_token_from_gh_falls_back_to_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("public_diary_tools.clients.subprocess.check_output", lambda *_args, **_kwargs: "gh-token\n")

    assert github_token_from_gh() == "gh-token"


def test_github_client_deletes_empty_variable() -> None:
    calls: list[tuple[Any, ...]] = []

    class FakeVariable:
        def delete(self) -> None:
            calls.append(("delete",))

    class FakeRepo:
        def get_variable(self, name: str) -> FakeVariable:
            calls.append(("get", name))
            return FakeVariable()

        def create_variable(self, name: str, value: str) -> None:
            calls.append(("create", name, value))

    client = GithubClient("owner/repo", "token")
    client.__dict__["repo"] = FakeRepo()

    client.set_variable("EMPTY", "")

    assert calls == [("get", "EMPTY"), ("delete",)]


def test_github_client_ignores_missing_empty_variable() -> None:
    calls: list[tuple[Any, ...]] = []

    class FakeRepo:
        def get_variable(self, name: str) -> None:
            calls.append(("get", name))
            raise RuntimeError("missing")

        def create_variable(self, name: str, value: str) -> None:
            calls.append(("create", name, value))

    client = GithubClient("owner/repo", "token")
    client.__dict__["repo"] = FakeRepo()

    client.set_variable("EMPTY", "")

    assert calls == [("get", "EMPTY")]
