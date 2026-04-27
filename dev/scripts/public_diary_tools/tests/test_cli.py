import argparse
import asyncio
import io
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Self, cast

import pytest
import requests
from github import GithubException
from public_diary_tools import cli
from public_diary_tools.clients import DRIVE_READONLY_SCOPE
from public_diary_tools.envfiles import read_env_file, write_env_file
from public_diary_tools.paths import github_app_file


def _append_call(calls: list[tuple[Any, ...]], call: tuple[Any, ...], result: Any = None) -> Any:
    calls.append(call)
    return result


def test_write_act_files_uses_local_secret_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    secret_file = tmp_path / "secrets.env"
    webhook_file = tmp_path / "discord"
    token_file = tmp_path / "drive-token"
    write_env_file(var_file, {"GCP_SERVICE_ACCOUNT": "svc@example.iam.gserviceaccount.com"})
    webhook_file.write_text("https://discord.example\n")
    token_file.write_text("drive-token\n")
    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setenv("ACT_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(webhook_file))
    monkeypatch.setenv("GOOGLE_DRIVE_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("PUBLIC_DIARY_APP_CLIENT_ID", "client-id")
    monkeypatch.setenv("PUBLIC_DIARY_APP_PRIVATE_KEY", "private-key")

    assert cli.cmd_write_act_files(None) == 0

    assert read_env_file(secret_file) == {
        "PUBLIC_DIARY_APP_CLIENT_ID": "client-id",
        "PUBLIC_DIARY_APP_PRIVATE_KEY": "private-key",
        "DISCORD_WEBHOOK_URL": "https://discord.example",
        "GOOGLE_DRIVE_ACCESS_TOKEN": "drive-token",
    }


def test_write_act_files_requires_vars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("ACT_SECRET_FILE", str(tmp_path / "secrets.env"))
    try:
        cli.cmd_write_act_files(None)
    except RuntimeError as exc:
        assert "Missing" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_write_act_vars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"

    class FakeVars:
        def as_env(self) -> dict[str, str]:
            return {"A": "1"}

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", lambda: object())
    monkeypatch.setattr(cli, "build_act_vars", lambda _google: FakeVars())

    assert cli.cmd_write_act_vars(None) == 0
    assert read_env_file(var_file) == {"A": "1"}


def test_format_json_prints_changed_files(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "format_json_configs", lambda: [Path("package.json")])

    assert cli.cmd_format_json(None) == 0

    assert "package.json" in capsys.readouterr().out


def test_format_json_prints_no_changes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "format_json_configs", lambda: [])

    assert cli.cmd_format_json(None) == 0

    assert "already formatted" in capsys.readouterr().out


def test_check_json_prints_no_changes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "check_json_configs", lambda: [])

    assert cli.cmd_check_json(None) == 0

    assert "are formatted" in capsys.readouterr().out


def test_check_json_errors_on_unformatted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "check_json_configs", lambda: [Path("package.json")])

    with pytest.raises(RuntimeError, match="format-json"):
        cli.cmd_check_json(None)


def test_coverage_badge_prints_result(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "publish_coverage_badge", lambda: (96.7, [Path("coverage.svg")]))

    assert cli.cmd_coverage_badge(None) == 0

    output = capsys.readouterr().out
    assert "96.7%" in output
    assert "coverage.svg" in output


def test_coverage_badge_prints_no_changes(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "publish_coverage_badge", lambda: (96.7, []))

    assert cli.cmd_coverage_badge(None) == 0

    assert "already up to date" in capsys.readouterr().out


def test_stage_wiki_docs_uses_env_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    wiki_dir = tmp_path / "wiki"
    calls: list[tuple[Path, Path]] = []

    def fake_stage(source: Path, target: Path) -> list[Path]:
        calls.append((source, target))
        return [target / "Home.md"]

    monkeypatch.setenv("WIKI_DIR", str(wiki_dir))
    monkeypatch.setattr(cli, "stage_wiki_docs", fake_stage)

    assert cli.cmd_stage_wiki_docs(None) == 0
    assert calls == [(Path("docs"), wiki_dir)]


def test_write_discord_webhook_prompts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "webhook"
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(path))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("builtins.input", lambda _: "https://discord.example")

    assert cli.cmd_write_discord_webhook(None) == 0

    assert path.read_text() == "https://discord.example\n"


def test_write_discord_webhook_requires_value(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(tmp_path / "webhook"))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("builtins.input", lambda _: "")
    try:
        cli.cmd_write_discord_webhook(None)
    except RuntimeError as exc:
        assert "required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_prompt_discord_webhook_reads_existing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "webhook"
    path.write_text("https://discord.example\n")
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(path))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    assert cli._prompt_discord_webhook() == "https://discord.example"  # noqa: SLF001


def test_discord_webhook_value_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "webhook"
    path.write_text("https://discord-file.example\n")
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(path))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    assert cli._discord_webhook_value() == "https://discord-file.example"  # noqa: SLF001

    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord-env.example")
    assert cli._discord_webhook_value() == "https://discord-env.example"  # noqa: SLF001


def test_discord_webhook_value_requires_value(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    with pytest.raises(RuntimeError, match="DISCORD_WEBHOOK_URL"):
        cli._discord_webhook_value()  # noqa: SLF001


def test_upload_github_vars(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    write_env_file(var_file, {"A": "1", "B": "2"})
    calls: list[tuple[Any, ...]] = []

    class FakeGithub:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("init", repo, token))

        def set_variable(self, name: str, value: str) -> None:
            calls.append((name, value))

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "repository_from_gh", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")

    assert cli.cmd_upload_github_vars(None) == 0
    assert calls == [("init", "owner/repo", "token"), ("A", "1"), ("B", "2")]


def test_upload_github_vars_requires_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "missing.env"))
    try:
        cli.cmd_upload_github_vars(None)
    except RuntimeError as exc:
        assert "Missing" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_upload_github_secrets_reads_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    path = tmp_path / "webhook"
    app_file = tmp_path / "github-app.env"
    path.write_text("https://discord.example\n")
    write_env_file(app_file, {"PUBLIC_DIARY_APP_CLIENT_ID": "client-id", "PUBLIC_DIARY_APP_PRIVATE_KEY": "private-key"})
    calls: list[tuple[Any, ...]] = []

    class FakeGithub:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("init", repo, token))

        def set_secret(self, name: str, value: str) -> None:
            calls.append((name, value))

    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(path))
    monkeypatch.setenv("GITHUB_APP_FILE", str(app_file))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "repository_from_gh", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")

    assert cli.cmd_upload_github_secrets(None) == 0
    assert calls[0] == ("init", "owner/repo", "token")
    assert sorted(calls[1:]) == [
        ("DISCORD_WEBHOOK_URL", "https://discord.example"),
        ("PUBLIC_DIARY_APP_CLIENT_ID", "client-id"),
        ("PUBLIC_DIARY_APP_PRIVATE_KEY", "private-key"),
    ]


def test_github_app_values_reads_legacy_local_names(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_file = tmp_path / "github-app.env"
    write_env_file(app_file, {"GITHUB_APP_CLIENT_ID": "legacy-client", "GITHUB_APP_PRIVATE_KEY": "legacy-key"})
    monkeypatch.setenv("GITHUB_APP_FILE", str(app_file))
    monkeypatch.delenv("PUBLIC_DIARY_APP_CLIENT_ID", raising=False)
    monkeypatch.delenv("PUBLIC_DIARY_APP_PRIVATE_KEY", raising=False)

    assert cli._github_app_values(required=True) == {  # noqa: SLF001
        "PUBLIC_DIARY_APP_CLIENT_ID": "legacy-client",
        "PUBLIC_DIARY_APP_PRIVATE_KEY": "legacy-key",
    }


def test_github_app_values_prefers_current_names(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_file = tmp_path / "github-app.env"
    write_env_file(
        app_file,
        {
            "GITHUB_APP_CLIENT_ID": "legacy-client",
            "GITHUB_APP_PRIVATE_KEY": "legacy-key",
            "PUBLIC_DIARY_APP_CLIENT_ID": "file-client",
            "PUBLIC_DIARY_APP_PRIVATE_KEY": "file-key",
        },
    )
    monkeypatch.setenv("GITHUB_APP_FILE", str(app_file))
    monkeypatch.setenv("PUBLIC_DIARY_APP_CLIENT_ID", "env-client")
    monkeypatch.setenv("PUBLIC_DIARY_APP_PRIVATE_KEY", "env-key")

    assert cli._github_app_values(required=True) == {  # noqa: SLF001
        "PUBLIC_DIARY_APP_CLIENT_ID": "env-client",
        "PUBLIC_DIARY_APP_PRIVATE_KEY": "env-key",
    }


def test_upload_github_secrets_requires_github_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GITHUB_APP_FILE", str(tmp_path / "missing"))
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    with pytest.raises(RuntimeError, match="GitHub App credentials"):
        cli.cmd_upload_github_secrets(None)


def test_apply_github_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}\n")
    calls: list[tuple[Any, ...]] = []

    class FakeGitHubSettings:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("init", repo, token))

    monkeypatch.setenv("GITHUB_SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(cli, "repository_from_gh", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")
    monkeypatch.setattr(cli, "GitHubSettingsClient", FakeGitHubSettings)
    monkeypatch.setattr(cli, "load_github_settings", lambda path: {"path": str(path)})
    monkeypatch.setattr(
        cli,
        "apply_github_settings",
        lambda settings, client: [f"settings:{settings['path']}", f"client:{client.__class__.__name__}"],
    )

    assert cli.cmd_apply_github_settings(None) == 0
    assert calls == [("init", "owner/repo", "token")]


def test_service_account_from_vars_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    monkeypatch.delenv("GCP_SERVICE_ACCOUNT", raising=False)
    try:
        cli._service_account_from_vars()  # noqa: SLF001
    except RuntimeError as exc:
        assert "required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")

    write_env_file(tmp_path / "vars.env", {"GCP_SERVICE_ACCOUNT": "dummy@example.iam.gserviceaccount.com"})
    try:
        cli._service_account_from_vars()  # noqa: SLF001
    except RuntimeError as exc:
        assert "dummy" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_project_from_service_account_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "override")
    assert cli._project_from_service_account("svc@proj.iam.gserviceaccount.com") == "override"  # noqa: SLF001


def test_write_act_drive_token_grants_active_user(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    token_file = tmp_path / "drive-token"
    service_account = "svc@proj.iam.gserviceaccount.com"
    write_env_file(var_file, {"GCP_SERVICE_ACCOUNT": service_account})
    calls: list[tuple[Any, ...]] = []

    class FakeGoogle:
        def service_account_exists(self, project: str, email: str) -> bool:
            calls.append(("exists", project, email))
            return True

        def add_service_account_binding(self, project: str, email: str, role: str, member: str) -> None:
            calls.append(("binding", project, email, role, member))

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setenv("GOOGLE_DRIVE_TOKEN_FILE", str(token_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    monkeypatch.setattr(cli, "active_gcloud_account", lambda: "user@example.com")

    def fake_impersonated_token(_service_account: str, scopes: list[str]) -> str:
        calls.append(("token", tuple(scopes)))
        return "drive-token"

    monkeypatch.setattr(cli, "gcloud_impersonated_token", fake_impersonated_token)

    assert cli.cmd_write_act_drive_token(None) == 0
    assert token_file.read_text() == "drive-token\n"
    assert calls == [
        ("exists", "proj", service_account),
        (
            "binding",
            "proj",
            service_account,
            "roles/iam.serviceAccountTokenCreator",
            "user:user@example.com",
        ),
        ("token", (DRIVE_READONLY_SCOPE,)),
    ]


def test_write_act_drive_token_requires_existing_service_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    var_file = tmp_path / "vars.env"
    write_env_file(var_file, {"GCP_SERVICE_ACCOUNT": "svc@proj.iam.gserviceaccount.com"})

    class FakeGoogle:
        def service_account_exists(self, project: str, email: str) -> bool:
            return False

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    try:
        cli.cmd_write_act_drive_token(None)
    except RuntimeError as exc:
        assert "not found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_configure_drive_access(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    write_env_file(
        var_file,
        {
            "GCP_SERVICE_ACCOUNT": "svc@proj.iam.gserviceaccount.com",
            "GOOGLE_DRIVE_ROOT_FOLDER_ID": "folder-id",
        },
    )

    class FakeGoogle:
        def grant_drive_permission(self, target_id: str, email: str, role: str) -> dict[str, str]:
            return {"id": target_id, "emailAddress": email, "role": role}

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    assert cli.cmd_configure_drive_access(None) == 0


def test_configure_drive_access_skips_shared_drive_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    var_file = tmp_path / "vars.env"
    write_env_file(
        var_file,
        {
            "GCP_SERVICE_ACCOUNT": "svc@proj.iam.gserviceaccount.com",
            "GOOGLE_DRIVE_SHARED_DRIVE_ID": "drive-id",
        },
    )

    class FakeGoogle:
        def grant_drive_permission(self, target_id: str, email: str, role: str) -> dict[str, str]:
            raise AssertionError((target_id, email, role))

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)

    assert cli.cmd_configure_drive_access(None) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["id"] == "drive-id"
    assert output["status"] == "skipped"


def test_configure_drive_access_requires_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "vars.env"))
    try:
        cli.cmd_configure_drive_access(None)
    except RuntimeError as exc:
        assert "SERVICE_ACCOUNT_EMAIL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")

    write_env_file(tmp_path / "vars.env", {"GCP_SERVICE_ACCOUNT": "svc@proj.iam.gserviceaccount.com"})
    try:
        cli.cmd_configure_drive_access(None)
    except RuntimeError as exc:
        assert "DRIVE_TARGET_ID" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_grant_drive_access_requires_target() -> None:
    class FakeVars:
        google_drive_root_folder_id = ""
        google_drive_shared_drive_id = ""
        gcp_service_account = "svc@proj.iam.gserviceaccount.com"

    with pytest.raises(RuntimeError, match="Google Drive"):
        cli._grant_drive_access(object(), FakeVars())  # type: ignore[arg-type]  # noqa: SLF001


def test_provision_auth_writes_vars_and_uploads(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    calls: list[tuple[Any, ...]] = []

    class FakeVars:
        gcp_service_account = "svc@proj.iam.gserviceaccount.com"

        def as_env(self) -> dict[str, str]:
            return {"GCP_SERVICE_ACCOUNT": self.gcp_service_account}

    class FakeGoogle:
        def enable_services(self, project: str, services: list[str]) -> None:
            calls.append(("enable", project, tuple(services)))

        def service_account_exists(self, project: str, email: str) -> bool:
            calls.append(("exists", project, email))
            return False

        def create_service_account(self, project: str, account_id: str, display_name: str) -> None:
            calls.append(("create", project, account_id, display_name))

        def project_number(self, project: str) -> str:
            return "123"

        def workload_identity_pool_exists(self, project_number: str, pool_id: str) -> bool:
            calls.append(("pool_exists", project_number, pool_id))
            return False

        def create_workload_identity_pool(self, project_number: str, pool_id: str, display_name: str) -> None:
            calls.append(("create_pool", project_number, pool_id, display_name))

        def workload_identity_provider_exists(self, project_number: str, pool_id: str, provider_id: str) -> bool:
            calls.append(("provider_exists", project_number, pool_id, provider_id))
            return False

        def create_workload_identity_provider(
            self,
            project_number: str,
            pool_id: str,
            provider_id: str,
            repo: str,
            display_name: str,
        ) -> None:
            calls.append(("create_provider", project_number, pool_id, provider_id, repo, display_name))

        def add_service_account_binding(self, project: str, email: str, role: str, member: str) -> None:
            calls.append(("binding", project, email, role, member))

    class FakeGithub:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("github", repo, token))

        def set_variable(self, name: str, value: str) -> None:
            calls.append(("var", name, value))

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    monkeypatch.setattr(cli, "select_project", lambda _google: "proj")
    monkeypatch.setattr(cli, "build_act_vars", lambda _google: FakeVars())
    monkeypatch.setattr(cli, "select_repository", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")
    monkeypatch.setattr(cli, "active_user_member", lambda: "user:user@example.com")
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)

    assert cli.cmd_provision_auth(None) == 0
    assert read_env_file(var_file) == {"GCP_SERVICE_ACCOUNT": "svc@proj.iam.gserviceaccount.com"}
    assert ("var", "GCP_SERVICE_ACCOUNT", "svc@proj.iam.gserviceaccount.com") in calls
    assert ("create_provider", "123", "github", "public-diary", "owner/repo", "GitHub repository") in calls
    github_principal = (
        "principalSet://iam.googleapis.com/"
        "projects/123/locations/global/workloadIdentityPools/github/attribute.repository/owner/repo"
    )
    assert (
        "binding",
        "proj",
        "svc@proj.iam.gserviceaccount.com",
        "roles/iam.serviceAccountTokenCreator",
        github_principal,
    ) in calls


def test_provision_github_app_writes_and_uploads_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_file = tmp_path / "github-app.env"
    calls: list[tuple[Any, ...]] = []

    class FakeGithub:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("github", repo, token))

        def set_secret(self, name: str, value: str) -> None:
            calls.append(("secret", name, value))

    def fake_request(method: str, path: str, token: str | None = None, payload: dict[str, Any] | None = None) -> Any:
        calls.append(("request", method, path, token, payload))
        if path == "/app-manifests/manifest-code/conversions":
            return {
                "id": 123,
                "slug": "public-diary-automation",
                "client_id": "client-id",
                "pem": "-----BEGIN KEY-----\nprivate\n-----END KEY-----\n",
            }
        raise AssertionError((method, path, token, payload))

    monkeypatch.setenv("GITHUB_APP_FILE", str(app_file))
    monkeypatch.setattr(cli, "select_repository", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "_wait_for_manifest_code", lambda _manifest: "manifest-code")
    monkeypatch.setattr(cli, "_select_github_app_setup_action", lambda _has_credentials: "create")
    monkeypatch.setattr(
        cli,
        "_prompt_github_app_installation",
        lambda app_slug, repo: _append_call(calls, ("install", app_slug, repo)),
    )
    monkeypatch.setattr(cli, "_github_request", fake_request)

    assert cli.cmd_provision_github_app(None) == 0

    assert read_env_file(app_file) == {
        "PUBLIC_DIARY_APP_CLIENT_ID": "client-id",
        "PUBLIC_DIARY_APP_PRIVATE_KEY": "-----BEGIN KEY-----\\nprivate\\n-----END KEY-----",
    }
    assert ("install", "public-diary-automation", "owner/repo") in calls
    assert ("secret", "PUBLIC_DIARY_APP_CLIENT_ID", "client-id") in calls
    assert ("secret", "PUBLIC_DIARY_APP_PRIVATE_KEY", "-----BEGIN KEY-----\\nprivate\\n-----END KEY-----") in calls


def test_provision_github_app_skips_when_existing_app_has_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_file = tmp_path / "github-app.env"
    write_env_file(
        app_file,
        {"PUBLIC_DIARY_APP_CLIENT_ID": "client-id", "PUBLIC_DIARY_APP_PRIVATE_KEY": "private-key"},
    )
    calls: list[tuple[Any, ...]] = []
    installation = {
        "app_slug": "public-diary-automation",
        "permissions": cli.GITHUB_APP_REQUIRED_PERMISSIONS,
        "html_url": "https://github.com/settings/installations/1",
    }

    class FakeGithub:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("github", repo, token))

        def set_secret(self, name: str, value: str) -> None:
            calls.append(("secret", name, value))

    monkeypatch.setenv("GITHUB_APP_FILE", str(app_file))
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "_github_app_installation_for_repo", lambda repo, credentials: installation)
    monkeypatch.setattr(
        cli,
        "_select_github_app_setup_action",
        lambda _has_credentials: _append_call(calls, ("select",), "create"),
    )

    assert cli._provision_github_app("owner/repo", "token") == "public-diary-automation"  # noqa: SLF001

    assert ("select",) not in calls
    assert ("secret", "PUBLIC_DIARY_APP_CLIENT_ID", "client-id") in calls
    assert ("secret", "PUBLIC_DIARY_APP_PRIVATE_KEY", "private-key") in calls


def test_ensure_existing_github_app_adds_missing_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_file = tmp_path / "github-app.env"
    credentials = cli.GitHubAppCredentials("client-id", "private-key")
    calls: list[tuple[Any, ...]] = []
    owner_installation = {
        "id": 456,
        "app_slug": "public-diary-automation",
        "repository_selection": "selected",
        "permissions": cli.GITHUB_APP_REQUIRED_PERMISSIONS,
    }
    repo_installation = {
        **owner_installation,
        "html_url": "https://github.com/settings/installations/456",
    }
    install_lookup = iter([None, repo_installation])

    class FakeGithub:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("github", repo, token))

        def set_secret(self, name: str, value: str) -> None:
            calls.append(("secret", name, value))

    monkeypatch.setenv("GITHUB_APP_FILE", str(app_file))
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "_github_app_installation_for_repo", lambda _repo, _credentials: next(install_lookup))
    monkeypatch.setattr(cli, "_find_owner_installation", lambda _repo, _credentials: owner_installation)
    monkeypatch.setattr(
        cli,
        "_add_repo_to_github_app_installation",
        lambda repo, installation, token: _append_call(calls, ("add", repo, installation["id"], token)),
    )

    assert cli._ensure_existing_github_app("owner/repo", "token", credentials) == "public-diary-automation"  # noqa: SLF001

    assert read_env_file(app_file) == {
        "PUBLIC_DIARY_APP_CLIENT_ID": "client-id",
        "PUBLIC_DIARY_APP_PRIVATE_KEY": "private-key",
    }
    assert ("add", "owner/repo", 456, "token") in calls
    assert ("secret", "PUBLIC_DIARY_APP_CLIENT_ID", "client-id") in calls


def test_validate_github_app_permissions_reports_missing() -> None:
    installation = {
        "permissions": {"metadata": "read", "contents": "read"},
        "html_url": "https://github.com/settings/installations/1",
    }

    with pytest.raises(RuntimeError, match="contents: write"):
        cli._validate_github_app_permissions(installation)  # noqa: SLF001


def test_github_app_installation_helpers_use_app_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    @dataclass
    class FakeObject:
        raw_data: dict[str, Any]

    class FakeIntegration:
        def __init__(self, client_id: str, private_key: str) -> None:
            assert client_id == "client-id"
            assert private_key == "private\nkey"

        def get_app(self) -> FakeObject:
            return FakeObject({"slug": "public-diary-automation"})

        def get_repo_installation(self, owner: str, repo: str) -> FakeObject:
            assert (owner, repo) == ("owner", "repo")
            return FakeObject({"app_slug": "public-diary-automation"})

        def get_installations(self) -> list[FakeObject]:
            return [
                FakeObject({"account": {"login": "other"}}),
                FakeObject({"account": {"login": "owner"}, "id": 456}),
            ]

    credentials = cli.GitHubAppCredentials("client-id", "private\nkey")
    monkeypatch.setattr(cli, "GithubIntegration", FakeIntegration)

    assert cli._github_app_info(credentials) == {"slug": "public-diary-automation"}  # noqa: SLF001
    assert cli._github_app_installation_for_repo("owner/repo", credentials) == {  # noqa: SLF001
        "app_slug": "public-diary-automation",
    }
    assert cli._find_owner_installation("owner/repo", credentials) == {"account": {"login": "owner"}, "id": 456}  # noqa: SLF001


def test_github_app_installation_for_repo_returns_none_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeIntegration:
        def __init__(self, _client_id: str, _private_key: str) -> None:
            return None

        def get_repo_installation(self, _owner: str, _repo: str) -> object:
            raise GithubException(404, {})

    monkeypatch.setattr(cli, "GithubIntegration", FakeIntegration)

    assert cli._github_app_installation_for_repo("owner/repo", cli.GitHubAppCredentials("id", "key")) is None  # noqa: SLF001


def test_add_repo_to_github_app_installation_skips_all_repos(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(cli, "_repository_id", lambda *_args: _append_call(calls, ("repo-id",), 789))

    cli._add_repo_to_github_app_installation("owner/repo", {"repository_selection": "all"}, "token")  # noqa: SLF001

    assert calls == []


def test_add_repo_to_github_app_installation_uses_api(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(cli, "_repository_id", lambda repo, token: _append_call(calls, ("repo-id", repo, token), 789))
    monkeypatch.setattr(
        cli,
        "_github_request",
        lambda method, path, token: _append_call(calls, ("request", method, path, token)),
    )

    cli._add_repo_to_github_app_installation(  # noqa: SLF001
        "owner/repo",
        {"id": 456, "repository_selection": "selected"},
        "token",
    )

    assert calls == [
        ("repo-id", "owner/repo", "token"),
        ("request", "PUT", "/user/installations/456/repositories/789", "token"),
    ]


def test_add_repo_to_github_app_installation_falls_back_to_manual(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prompts: list[str] = []

    def raise_http_error(*_args: Any) -> None:
        response = requests.Response()
        response.status_code = 403
        raise requests.HTTPError("403 forbidden", response=response)

    monkeypatch.setattr(cli, "_repository_id", lambda _repo, _token: 789)
    monkeypatch.setattr(cli, "_github_request", raise_http_error)
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt))

    cli._add_repo_to_github_app_installation(  # noqa: SLF001
        "owner/repo",
        {
            "id": 456,
            "repository_selection": "selected",
            "html_url": "https://github.com/settings/installations/456",
        },
        "token",
    )

    output = capsys.readouterr().out
    assert "https://github.com/settings/installations/456" in output
    assert prompts == ["Press Enter after updating the app installation: "]


def test_prompt_existing_github_app_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    private_key = tmp_path / "app.pem"
    private_key.write_text("private-key")
    answers = iter(["client-id", str(private_key)])
    monkeypatch.setattr(cli, "prompt_required_value", lambda _label: next(answers))

    assert cli._prompt_existing_github_app_credentials() == cli.GitHubAppCredentials("client-id", "private-key")  # noqa: SLF001


def test_provision_github_app_uses_existing_choice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    app_file = tmp_path / "github-app.env"
    credentials = cli.GitHubAppCredentials("client-id", "private-key")
    calls: list[tuple[Any, ...]] = []

    monkeypatch.setenv("GITHUB_APP_FILE", str(app_file))
    monkeypatch.setattr(cli, "_github_app_values", lambda required=False: {})
    monkeypatch.setattr(cli, "_select_github_app_setup_action", lambda _has_credentials: "existing")
    monkeypatch.setattr(cli, "_prompt_existing_github_app_credentials", lambda: credentials)
    monkeypatch.setattr(
        cli,
        "_ensure_existing_github_app",
        lambda repo, token, creds: _append_call(calls, (repo, token, creds), "public-diary-automation"),
    )

    assert cli._provision_github_app("owner/repo", "token") == "public-diary-automation"  # noqa: SLF001
    assert calls == [("owner/repo", "token", credentials)]


def test_select_github_app_setup_action_renders_numbered_options(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, list[tuple[str, str]]]] = []

    def fake_select(label: str, options: list[tuple[str, str]]) -> str:
        calls.append((label, options))
        return "existing"

    monkeypatch.setattr(cli, "select_option", fake_select)

    assert cli._select_github_app_setup_action(has_credentials=True) == "existing"  # noqa: SLF001
    assert calls == [
        (
            "GitHub App setup",
            [
                ("create", "Create a new GitHub App"),
                ("existing", f"Use existing GitHub App credentials from {github_app_file()} or environment"),
            ],
        ),
    ]


def test_prompt_github_app_installation_waits_for_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt))

    cli._prompt_github_app_installation("public-diary-automation", "owner/repo")  # noqa: SLF001

    output = capsys.readouterr().out
    assert "https://github.com/apps/public-diary-automation/installations/new" in output
    assert "owner/repo" in output
    assert prompts == ["Press Enter after installing the app: "]


def test_github_request_and_manifest_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str, dict[str, str], dict[str, Any] | None, int]] = []

    class JsonResponse:
        def raise_for_status(self) -> None:
            calls.append(("raise", "", {}, None, 0))

        def json(self) -> dict[str, str]:
            return {"ok": "true"}

    def fake_request(
        method: str,
        url: str,
        headers: dict[str, str],
        json: dict[str, Any] | None,  # noqa: A002
        timeout: int,
    ) -> JsonResponse:
        calls.append((method, url, headers, json, timeout))
        return JsonResponse()

    monkeypatch.setenv("GITHUB_APP_NAME", "Custom App")
    monkeypatch.setattr("public_diary_tools.cli.requests.request", fake_request)

    assert cli._github_headers()["Accept"] == "application/vnd.github+json"  # noqa: SLF001
    assert cli._github_headers("token")["Authorization"] == "Bearer token"  # noqa: SLF001
    assert cli._github_request("POST", "/path", "token", {"a": 1}) == {"ok": "true"}  # noqa: SLF001
    manifest = cli._github_app_manifest("owner/repo", "http://callback")  # noqa: SLF001

    assert manifest["name"] == "Custom App"
    assert manifest["url"] == "https://github.com/owner/repo"
    assert manifest["redirect_url"] == "http://callback"
    assert "hook_attributes" not in manifest
    assert manifest["default_permissions"]["contents"] == "write"
    assert calls[0][1] == "https://api.github.com/path"


def test_github_app_name_defaults_to_short_repository_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_APP_NAME", raising=False)

    manifest = cli._github_app_manifest("aidanhall34/public-diary", "http://callback")  # noqa: SLF001
    long_manifest = cli._github_app_manifest("owner/repository-name-that-is-too-long", "http://callback")  # noqa: SLF001

    assert manifest["name"] == "public-diary automation"
    assert long_manifest["name"] == "repository-name-that-is automation"
    assert len(long_manifest["name"]) == 34


def test_github_app_name_rejects_invalid_configured_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_APP_NAME", "x" * 35)
    with pytest.raises(RuntimeError, match="cannot be longer than 34"):
        cli._github_app_manifest("owner/repo", "http://callback")  # noqa: SLF001

    monkeypatch.setenv("GITHUB_APP_NAME", " ")
    with pytest.raises(RuntimeError, match="cannot be empty"):
        cli._github_app_manifest("owner/repo", "http://callback")  # noqa: SLF001


def test_github_request_handles_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class EmptyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            raise ValueError

    monkeypatch.setattr("public_diary_tools.cli.requests.request", lambda *_args, **_kwargs: EmptyResponse())

    assert cli._github_request("DELETE", "/path") == {}  # noqa: SLF001


def test_manifest_start_html_posts_manifest() -> None:
    output = cli._manifest_start_html(  # noqa: SLF001
        "/organizations/example/settings/apps/new",
        '{"name":"A&B"}',
    )

    assert 'method="post"' in output
    assert 'action="https://github.com/organizations/example/settings/apps/new"' in output
    assert 'name="manifest"' in output
    assert "{&quot;name&quot;:&quot;A&amp;B&quot;}" in output


def test_manifest_callback_handler_serves_start_and_callback() -> None:
    class FakeServer:
        code = ""
        github_create_path = "/settings/apps/new"
        manifest_json = '{"name":"app"}'

    class FakeHandler:
        path = "/github-app-manifest-start"
        server = FakeServer()
        wfile = io.BytesIO()
        responses: list[int] = []
        headers: list[tuple[str, str]] = []

        def send_response(self, status: int) -> None:
            self.responses.append(status)

        def send_header(self, name: str, value: str) -> None:
            self.headers.append((name, value))

        def end_headers(self) -> None:
            return None

    handler = FakeHandler()
    cli._ManifestCallbackHandler.do_GET(handler)  # type: ignore[arg-type]  # noqa: SLF001

    assert handler.responses == [200]
    assert b"<form" in handler.wfile.getvalue()

    handler.path = "/github-app-manifest-callback?code=abc"
    handler.wfile = io.BytesIO()
    cli._ManifestCallbackHandler.do_GET(handler)  # type: ignore[arg-type]  # noqa: SLF001

    assert handler.server.code == "abc"
    assert b"code received" in handler.wfile.getvalue()

    handler.path = "/github-app-manifest-callback"
    handler.wfile = io.BytesIO()
    cli._ManifestCallbackHandler.do_GET(handler)  # type: ignore[arg-type]  # noqa: SLF001

    assert handler.responses[-1] == 400
    assert b"Missing" in handler.wfile.getvalue()


def test_github_app_create_path() -> None:
    assert cli._github_app_create_path("") == "/settings/apps/new"  # noqa: SLF001
    assert cli._github_app_create_path("owner") == "/organizations/owner/settings/apps/new"  # noqa: SLF001


def test_wait_for_manifest_code_accepts_pasted_url(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []

    class FakeServer:
        code = ""
        server_port = 8765

        def __init__(self, address: tuple[str, int], handler: Any) -> None:
            events.append(f"server:{address[0]}:{address[1]}:{handler.__name__}")

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            events.append("exit")

        def serve_forever(self) -> None:
            events.append("serve")

        def shutdown(self) -> None:
            events.append("shutdown")

    class FakeThread:
        def __init__(self, target: Callable[[], None], daemon: bool) -> None:
            self.target = target
            self.daemon = daemon

        def start(self) -> None:
            assert self.daemon is True
            self.target()

        def join(self, timeout: int) -> None:
            events.append(f"join:{timeout}")

    monkeypatch.setenv("GITHUB_APP_OWNER", "owner")
    monkeypatch.setattr(cli, "_ManifestCallbackServer", FakeServer)
    monkeypatch.setattr("public_diary_tools.cli.threading.Thread", FakeThread)

    code = cli._wait_for_manifest_code(  # noqa: SLF001
        {"name": "app"},
        lambda _prompt: "http://127.0.0.1:8765/github-app-manifest-callback?code=abc",
    )

    assert code == "abc"
    assert "serve" in events
    assert "shutdown" in events


def test_wait_for_manifest_code_uses_server_code(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeServer:
        code = "server-code"
        server_port = 8765

        def __init__(self, _address: tuple[str, int], _handler: object) -> None:
            return None

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    class FakeThread:
        def __init__(self, target: Callable[[], None], daemon: bool) -> None:
            self.target = target

        def start(self) -> None:
            self.target()

        def join(self, timeout: int) -> None:
            return None

    monkeypatch.setattr(cli, "_ManifestCallbackServer", FakeServer)
    monkeypatch.setattr("public_diary_tools.cli.threading.Thread", FakeThread)

    assert cli._wait_for_manifest_code({}, lambda _prompt: "") == "server-code"  # noqa: SLF001


def test_wait_for_manifest_code_accepts_pasted_code(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeServer:
        code = ""
        server_port = 8765

        def __init__(self, _address: tuple[str, int], _handler: object) -> None:
            return None

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    class FakeThread:
        def __init__(self, target: Callable[[], None], daemon: bool) -> None:
            self.target = target

        def start(self) -> None:
            self.target()

        def join(self, timeout: int) -> None:
            return None

    monkeypatch.setattr(cli, "_ManifestCallbackServer", FakeServer)
    monkeypatch.setattr("public_diary_tools.cli.threading.Thread", FakeThread)

    assert cli._wait_for_manifest_code({}, lambda _prompt: "pasted-code") == "pasted-code"  # noqa: SLF001


def test_wait_for_manifest_code_requires_value(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeServer:
        code = ""
        server_port = 8765

        def __init__(self, _address: tuple[str, int], _handler: object) -> None:
            return None

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

    class FakeThread:
        def __init__(self, target: Callable[[], None], daemon: bool) -> None:
            self.target = target

        def start(self) -> None:
            self.target()

        def join(self, timeout: int) -> None:
            return None

    monkeypatch.setattr(cli, "_ManifestCallbackServer", FakeServer)
    monkeypatch.setattr("public_diary_tools.cli.threading.Thread", FakeThread)

    with pytest.raises(RuntimeError, match="manifest code"):
        cli._wait_for_manifest_code({}, lambda _prompt: "")  # noqa: SLF001


def test_provision_all_batches_independent_work(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    secret_file = tmp_path / "secrets.env"
    webhook_file = tmp_path / "webhook"
    token_file = tmp_path / "drive-token"
    calls: list[tuple[Any, ...]] = []

    class FakeVars:
        gcp_service_account = "svc@proj.iam.gserviceaccount.com"
        google_drive_root_folder_id = ""
        google_drive_shared_drive_id = "drive-id"

        def as_env(self) -> dict[str, str]:
            return {"GCP_SERVICE_ACCOUNT": self.gcp_service_account, "GOOGLE_DRIVE_SHARED_DRIVE_ID": "drive-id"}

    class FakeGoogle:
        def enable_services(self, project: str, services: list[str]) -> None:
            calls.append(("enable", project, tuple(services)))

        def service_account_exists(self, project: str, email: str) -> bool:
            calls.append(("exists", project, email))
            return True

        def project_number(self, project: str) -> str:
            return "123"

        def workload_identity_pool_exists(self, project_number: str, pool_id: str) -> bool:
            return True

        def workload_identity_provider_exists(self, project_number: str, pool_id: str, provider_id: str) -> bool:
            return True

        def add_service_account_binding(self, project: str, email: str, role: str, member: str) -> None:
            calls.append(("binding", project, email, role, member))

        def grant_drive_permission(self, target_id: str, email: str, role: str) -> dict[str, str]:
            calls.append(("drive", target_id, email, role))
            return {"id": target_id}

        def service_account_exists_for_token(self) -> bool:
            return True

    class FakeGithub:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("github", repo, token))

        def set_variable(self, name: str, value: str) -> None:
            calls.append(("var", name, value))

        def set_secret(self, name: str, value: str) -> None:
            calls.append(("secret", name, value))

    def fake_write_token(_: argparse.Namespace | None) -> int:
        token_file.write_text("drive-token\n")
        calls.append(("drive_token",))
        return 0

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setenv("ACT_SECRET_FILE", str(secret_file))
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(webhook_file))
    monkeypatch.setenv("GOOGLE_DRIVE_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example")
    monkeypatch.setenv("PUBLIC_DIARY_APP_CLIENT_ID", "client-id")
    monkeypatch.setenv("PUBLIC_DIARY_APP_PRIVATE_KEY", "private-key")
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    monkeypatch.setattr(cli, "select_project", lambda _google: "proj")
    monkeypatch.setattr(cli, "build_act_vars", lambda _google: FakeVars())
    monkeypatch.setattr(cli, "select_repository", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")
    monkeypatch.setattr(cli, "active_user_member", lambda: "user:user@example.com")
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "_apply_github_settings", lambda _repo, _token: asyncio.sleep(0, result=["repo"]))
    monkeypatch.setattr(cli, "cmd_write_act_drive_token", fake_write_token)

    assert cli.cmd_provision_all(None) == 0

    assert read_env_file(var_file)["GCP_SERVICE_ACCOUNT"] == "svc@proj.iam.gserviceaccount.com"
    assert read_env_file(secret_file)["DISCORD_WEBHOOK_URL"] == "https://discord.example"
    assert read_env_file(secret_file)["PUBLIC_DIARY_APP_CLIENT_ID"] == "client-id"
    assert read_env_file(secret_file)["PUBLIC_DIARY_APP_PRIVATE_KEY"] == "private-key"
    assert ("secret", "DISCORD_WEBHOOK_URL", "https://discord.example") in calls
    assert ("secret", "PUBLIC_DIARY_APP_CLIENT_ID", "client-id") in calls
    assert ("secret", "PUBLIC_DIARY_APP_PRIVATE_KEY", "private-key") in calls
    assert ("drive", "drive-id", "svc@proj.iam.gserviceaccount.com", "reader") not in calls
    github_principal = (
        "principalSet://iam.googleapis.com/"
        "projects/123/locations/global/workloadIdentityPools/github/attribute.repository/owner/repo"
    )
    assert (
        "binding",
        "proj",
        "svc@proj.iam.gserviceaccount.com",
        "roles/iam.serviceAccountTokenCreator",
        github_principal,
    ) in calls


def test_format_duration_unknown() -> None:
    assert cli._format_duration("") == "unknown"  # noqa: SLF001


def test_format_duration_values() -> None:
    assert cli._format_duration("2999-01-01T00:00:00Z") == "0s"  # noqa: SLF001


def test_format_duration_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Self:
            return cls(2026, 1, 1, 0, 2, 3, tzinfo=tz)

    monkeypatch.setattr(cli, "datetime", FixedDateTime)

    assert cli._format_duration("2026-01-01T00:00:00Z") == "2m 3s"  # noqa: SLF001


def test_format_duration_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Self:
            return cls(2026, 1, 1, 2, 3, 4, tzinfo=tz)

    monkeypatch.setattr(cli, "datetime", FixedDateTime)

    assert cli._format_duration("2026-01-01T00:00:00Z") == "2h 3m 4s"  # noqa: SLF001


def test_main_returns_error_for_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_args: Any) -> int:
        raise RuntimeError("broken")

    class FakeParser:
        def parse_args(self, argv: list[str] | None) -> argparse.Namespace:
            assert argv == ["write-act-files"]
            return argparse.Namespace(func=boom)

    monkeypatch.setattr(cli, "build_parser", FakeParser)

    assert cli.main(["write-act-files"]) == 1


def test_main_returns_clean_exit_for_user_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    def cancel(_args: Any) -> int:
        raise KeyboardInterrupt

    class FakeParser:
        def parse_args(self, argv: list[str] | None) -> argparse.Namespace:
            assert argv == ["write-act-files"]
            return argparse.Namespace(func=cancel)

    monkeypatch.setattr(cli, "build_parser", FakeParser)

    assert cli.main(["write-act-files"]) == 130


def test_main_returns_clean_exit_for_eof(monkeypatch: pytest.MonkeyPatch) -> None:
    def cancel(_args: Any) -> int:
        raise EOFError

    class FakeParser:
        def parse_args(self, argv: list[str] | None) -> argparse.Namespace:
            assert argv == ["write-act-files"]
            return argparse.Namespace(func=cancel)

    monkeypatch.setattr(cli, "build_parser", FakeParser)

    assert cli.main(["write-act-files"]) == 130


def test_main_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    webhook_file = tmp_path / "webhook"
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(webhook_file))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example")

    assert cli.main(["write-discord-webhook"]) == 0
    assert webhook_file.read_text() == "https://discord.example\n"


def test_main_writes_json_debug_log(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "Makefile").write_text(".PHONY: docs-commands\n")
    log_file = tmp_path / "tool.log"

    assert cli.main(["--debug", "--log-output", str(log_file), "write-commands-doc"]) == 0

    log_line = json.loads(log_file.read_text().splitlines()[0])
    assert log_line["level"] == "debug"
    assert log_line["msg"] == "configured logging"
    assert isinstance(log_line["line_number"], int)
    assert log_line["function_name"] == "main"
    assert "timestamp" in log_line


def test_write_commands_doc_uses_command_docstrings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "dev/makefiles").mkdir(parents=True)
    (tmp_path / "Makefile").write_text("include dev/makefiles/python.mk\n.PHONY: setup test\n")
    (tmp_path / "dev/makefiles/python.mk").write_text(".PHONY: python-tool python-help\n")

    assert cli.cmd_write_commands_doc(None) == 0

    output = (tmp_path / "docs/commands.md").read_text()
    provision_auth_doc = cli.cmd_provision_auth.__doc__
    assert provision_auth_doc is not None
    assert "- `make setup`" in output
    assert "- `make python-tool`" in output
    assert "## Python Tool Commands" in output
    assert "usage: public-diary-tools provision-auth" in output
    assert provision_auth_doc.strip() in output
    assert "## Provisioning notes" in output


def test_python_tool_command_docs_use_fixed_width(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "20")

    output = cli._render_python_tool_commands()  # noqa: SLF001

    assert "Discover Drive values and provision Google, GitHub, Discord, and local act\ninputs." in output


def test_make_target_discovery_handles_missing_files(tmp_path: Path) -> None:
    makefile = tmp_path / "Makefile"
    makefile.write_text("include missing.mk\n.PHONY: setup\n")

    assert cli._makefile_paths(tmp_path / "missing-root.mk") == [tmp_path / "missing-root.mk"]  # noqa: SLF001
    assert cli._make_targets(makefile) == ["setup"]  # noqa: SLF001


def test_parser_help_includes_command_descriptions(capsys: pytest.CaptureFixture[str]) -> None:
    parser = cli.build_parser()

    try:
        parser.parse_args(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit")

    assert "Write local act repository variables" in capsys.readouterr().out


def test_notify_discord_failure_payload(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sent: dict[str, Any] = {}

    class Response:
        def raise_for_status(self) -> None:
            sent["ok"] = True

    def fake_post(url: str, json: dict[str, Any], timeout: int) -> Response:  # noqa: A002
        sent["url"] = url
        sent["json"] = json
        sent["timeout"] = timeout
        return Response()

    env = {
        "DISCORD_WEBHOOK_URL": "https://discord.example",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "42",
        "GITHUB_SHA": "abcdef123456",
        "GITHUB_WORKFLOW": "Deploy",
        "GITHUB_RUN_NUMBER": "7",
        "DISCORD_JOB_RESULTS": "build=success, deploy=failure",
    }
    old = os.environ.copy()
    os.environ.update(env)
    try:
        monkeypatch.setattr("public_diary_tools.cli.requests.post", fake_post)
        assert cli.cmd_notify_discord(None) == 0
    finally:
        os.environ.clear()
        os.environ.update(old)

    assert sent["url"] == "https://discord.example"
    embed = sent["json"]["embeds"][0]
    assert embed["title"] == "Workflow failed: Deploy"
    assert embed["color"] == 15158332
    fields = cast(list[dict[str, str]], sent["json"]["embeds"][0]["fields"])
    assert fields[1]["value"] == "[owner/repo](https://github.com/owner/repo)"
    assert fields[3]["value"] == "[abcdef1](https://github.com/owner/repo/commit/abcdef123456)"
    assert fields[6]["value"] == "build=success, deploy=failure"
    assert "Discord failure notification sent." in capsys.readouterr().out


def test_notify_discord_success_payload(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    sent: dict[str, Any] = {}

    class Response:
        def raise_for_status(self) -> None:
            sent["ok"] = True

    def fake_post(url: str, json: dict[str, Any], timeout: int) -> Response:  # noqa: A002
        sent["url"] = url
        sent["json"] = json
        sent["timeout"] = timeout
        return Response()

    env = {
        "DISCORD_WEBHOOK_URL": "https://discord.example",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "42",
        "GITHUB_SHA": "abcdef123456",
        "GITHUB_WORKFLOW": "Deploy",
        "GITHUB_RUN_NUMBER": "7",
        "DISCORD_JOB_RESULTS": "build=success, deploy=skipped",
    }
    old = os.environ.copy()
    os.environ.update(env)
    try:
        monkeypatch.setattr("public_diary_tools.cli.requests.post", fake_post)
        assert cli.cmd_notify_discord(None) == 0
    finally:
        os.environ.clear()
        os.environ.update(old)

    embed = sent["json"]["embeds"][0]
    assert embed["title"] == "Workflow succeeded: Deploy"
    assert embed["color"] == 3066993
    assert "Discord success notification sent." in capsys.readouterr().out


def test_notify_discord_requires_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    try:
        cli.cmd_notify_discord(None)
    except RuntimeError as exc:
        assert "DISCORD_WEBHOOK_URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")
