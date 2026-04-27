import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Self, cast

import pytest
from public_diary_tools import cli
from public_diary_tools.clients import DRIVE_READONLY_SCOPE
from public_diary_tools.envfiles import read_env_file, write_env_file


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
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "github-token")

    assert cli.cmd_write_act_files(None) == 0

    assert read_env_file(secret_file) == {
        "GITHUB_TOKEN": "github-token",
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
    path.write_text("https://discord.example\n")
    calls: list[tuple[Any, ...]] = []

    class FakeGithub:
        def __init__(self, repo: str, token: str) -> None:
            calls.append(("init", repo, token))

        def set_secret(self, name: str, value: str) -> None:
            calls.append((name, value))

    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(path))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "repository_from_gh", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")

    assert cli.cmd_upload_github_secrets(None) == 0
    assert calls == [("init", "owner/repo", "token"), ("DISCORD_WEBHOOK_URL", "https://discord.example")]


def test_upload_github_secrets_requires_webhook(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    try:
        cli.cmd_upload_github_secrets(None)
    except RuntimeError as exc:
        assert "DISCORD_WEBHOOK_URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


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
            "GOOGLE_DRIVE_SHARED_DRIVE_ID": "drive-id",
        },
    )

    class FakeGoogle:
        def grant_drive_permission(self, target_id: str, email: str, role: str) -> dict[str, str]:
            return {"id": target_id, "emailAddress": email, "role": role}

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    assert cli.cmd_configure_drive_access(None) == 0


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
    assert ("secret", "DISCORD_WEBHOOK_URL", "https://discord.example") in calls
    assert ("drive", "drive-id", "svc@proj.iam.gserviceaccount.com", "reader") in calls


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


def test_main_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example")
    assert cli.main(["write-discord-webhook"]) == 0


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


def test_notify_discord_payload(monkeypatch: pytest.MonkeyPatch) -> None:
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
    fields = cast(list[dict[str, str]], sent["json"]["embeds"][0]["fields"])
    assert fields[1]["value"] == "[owner/repo](https://github.com/owner/repo)"
    assert fields[3]["value"] == "[abcdef1](https://github.com/owner/repo/commit/abcdef123456)"


def test_notify_discord_requires_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    try:
        cli.cmd_notify_discord(None)
    except RuntimeError as exc:
        assert "DISCORD_WEBHOOK_URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")
