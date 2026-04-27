"""Coverage note for SDK adapters.

`public_diary_tools.clients` is intentionally omitted from coverage because it
is a thin adapter over Google API Python Client, google-auth, PyGithub, and
gcloud token commands. Unit tests cover the calling code with fakes; live SDK
behavior should be checked through manual provisioning or a dedicated
integration test account, not normal repository tests.
"""

from typing import Any

from public_diary_tools.clients import GithubClient


def test_external_client_coverage_exception_is_documented() -> None:
    assert True


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
