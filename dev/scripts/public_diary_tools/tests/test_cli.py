import os
from pathlib import Path

from public_diary_tools import cli
from public_diary_tools.envfiles import read_env_file, write_env_file


def test_write_act_files_uses_local_secret_files(monkeypatch, tmp_path: Path) -> None:
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


def test_write_act_files_requires_vars(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("ACT_SECRET_FILE", str(tmp_path / "secrets.env"))
    try:
        cli.cmd_write_act_files(None)
    except RuntimeError as exc:
        assert "Missing" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_write_act_vars(monkeypatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"

    class FakeVars:
        def as_env(self):
            return {"A": "1"}

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", lambda: object())
    monkeypatch.setattr(cli, "build_act_vars", lambda _google: FakeVars())

    assert cli.cmd_write_act_vars(None) == 0
    assert read_env_file(var_file) == {"A": "1"}


def test_write_discord_webhook_prompts(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "webhook"
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(path))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("builtins.input", lambda _: "https://discord.example")

    assert cli.cmd_write_discord_webhook(None) == 0

    assert path.read_text() == "https://discord.example\n"


def test_write_discord_webhook_requires_value(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(tmp_path / "webhook"))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("builtins.input", lambda _: "")
    try:
        cli.cmd_write_discord_webhook(None)
    except RuntimeError as exc:
        assert "required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_upload_github_vars(monkeypatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    write_env_file(var_file, {"A": "1", "B": "2"})
    calls = []

    class FakeGithub:
        def __init__(self, repo, token):
            calls.append(("init", repo, token))

        def set_variable(self, name, value):
            calls.append((name, value))

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "repository_from_gh", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")

    assert cli.cmd_upload_github_vars(None) == 0
    assert calls == [("init", "owner/repo", "token"), ("A", "1"), ("B", "2")]


def test_upload_github_vars_requires_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ACT_VAR_FILE", str(tmp_path / "missing.env"))
    try:
        cli.cmd_upload_github_vars(None)
    except RuntimeError as exc:
        assert "Missing" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_upload_github_secrets_reads_file(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "webhook"
    path.write_text("https://discord.example\n")
    calls = []

    class FakeGithub:
        def __init__(self, repo, token):
            calls.append(("init", repo, token))

        def set_secret(self, name, value):
            calls.append((name, value))

    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(path))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)
    monkeypatch.setattr(cli, "repository_from_gh", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")

    assert cli.cmd_upload_github_secrets(None) == 0
    assert calls == [("init", "owner/repo", "token"), ("DISCORD_WEBHOOK_URL", "https://discord.example")]


def test_upload_github_secrets_requires_webhook(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_FILE", str(tmp_path / "missing"))
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    try:
        cli.cmd_upload_github_secrets(None)
    except RuntimeError as exc:
        assert "DISCORD_WEBHOOK_URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_service_account_from_vars_errors(monkeypatch, tmp_path: Path) -> None:
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


def test_project_from_service_account_prefers_env(monkeypatch) -> None:
    monkeypatch.setenv("GCP_PROJECT_ID", "override")
    assert cli._project_from_service_account("svc@proj.iam.gserviceaccount.com") == "override"  # noqa: SLF001


def test_write_act_drive_token_grants_active_user(monkeypatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    token_file = tmp_path / "drive-token"
    service_account = "svc@proj.iam.gserviceaccount.com"
    write_env_file(var_file, {"GCP_SERVICE_ACCOUNT": service_account})
    calls = []

    class FakeGoogle:
        def service_account_exists(self, project, email):
            calls.append(("exists", project, email))
            return True

        def add_service_account_binding(self, project, email, role, member):
            calls.append(("binding", project, email, role, member))

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setenv("GOOGLE_DRIVE_TOKEN_FILE", str(token_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    monkeypatch.setattr(cli, "active_gcloud_account", lambda: "user@example.com")
    monkeypatch.setattr(cli, "gcloud_impersonated_token", lambda *_: "drive-token")

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
    ]


def test_write_act_drive_token_requires_existing_service_account(monkeypatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    write_env_file(var_file, {"GCP_SERVICE_ACCOUNT": "svc@proj.iam.gserviceaccount.com"})

    class FakeGoogle:
        def service_account_exists(self, project, email):
            return False

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    try:
        cli.cmd_write_act_drive_token(None)
    except RuntimeError as exc:
        assert "not found" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")


def test_configure_drive_access(monkeypatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    write_env_file(
        var_file,
        {
            "GCP_SERVICE_ACCOUNT": "svc@proj.iam.gserviceaccount.com",
            "GOOGLE_DRIVE_SHARED_DRIVE_ID": "drive-id",
        },
    )

    class FakeGoogle:
        def grant_drive_permission(self, target_id, email, role):
            return {"id": target_id, "emailAddress": email, "role": role}

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    assert cli.cmd_configure_drive_access(None) == 0


def test_configure_drive_access_requires_values(monkeypatch, tmp_path: Path) -> None:
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


def test_provision_auth_writes_vars_and_uploads(monkeypatch, tmp_path: Path) -> None:
    var_file = tmp_path / "vars.env"
    calls = []

    class FakeVars:
        gcp_service_account = "svc@proj.iam.gserviceaccount.com"

        def as_env(self):
            return {"GCP_SERVICE_ACCOUNT": self.gcp_service_account}

    class FakeGoogle:
        def enable_services(self, project, services):
            calls.append(("enable", project, tuple(services)))

        def service_account_exists(self, project, email):
            calls.append(("exists", project, email))
            return False

        def create_service_account(self, project, account_id, display_name):
            calls.append(("create", project, account_id, display_name))

        def project_number(self, project):
            return "123"

        def add_service_account_binding(self, project, email, role, member):
            calls.append(("binding", project, email, role, member))

    class FakeGithub:
        def __init__(self, repo, token):
            calls.append(("github", repo, token))

        def set_variable(self, name, value):
            calls.append(("var", name, value))

    monkeypatch.setenv("ACT_VAR_FILE", str(var_file))
    monkeypatch.setattr(cli, "GoogleApis", FakeGoogle)
    monkeypatch.setattr(cli, "select_project", lambda _google: "proj")
    monkeypatch.setattr(cli, "build_act_vars", lambda _google: FakeVars())
    monkeypatch.setattr(cli, "repository_from_gh", lambda: "owner/repo")
    monkeypatch.setattr(cli, "github_token_from_gh", lambda: "token")
    monkeypatch.setattr(cli, "active_user_member", lambda: "user:user@example.com")
    monkeypatch.setattr(cli, "GithubClient", FakeGithub)

    assert cli.cmd_provision_auth(None) == 0
    assert read_env_file(var_file) == {"GCP_SERVICE_ACCOUNT": "svc@proj.iam.gserviceaccount.com"}
    assert ("var", "GCP_SERVICE_ACCOUNT", "svc@proj.iam.gserviceaccount.com") in calls


def test_format_duration_unknown() -> None:
    assert cli._format_duration("") == "unknown"  # noqa: SLF001


def test_format_duration_values() -> None:
    assert cli._format_duration("2999-01-01T00:00:00Z") == "0s"  # noqa: SLF001


def test_format_duration_minutes(monkeypatch) -> None:
    class FixedDateTime(cli.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return cls(2026, 1, 1, 0, 2, 3, tzinfo=tz)

    monkeypatch.setattr(cli, "datetime", FixedDateTime)

    assert cli._format_duration("2026-01-01T00:00:00Z") == "2m 3s"  # noqa: SLF001


def test_format_duration_hours(monkeypatch) -> None:
    class FixedDateTime(cli.datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001
            return cls(2026, 1, 1, 2, 3, 4, tzinfo=tz)

    monkeypatch.setattr(cli, "datetime", FixedDateTime)

    assert cli._format_duration("2026-01-01T00:00:00Z") == "2h 3m 4s"  # noqa: SLF001


def test_main_returns_error_for_exception(monkeypatch) -> None:
    def boom(_args):
        raise RuntimeError("broken")

    parser = cli.build_parser()
    args = parser.parse_args(["write-act-files"])
    args.func = boom
    monkeypatch.setattr(cli, "build_parser", lambda: parser)
    assert cli.main(["write-act-files"]) == 1


def test_main_success(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example")
    assert cli.main(["write-discord-webhook"]) == 0


def test_python_tool_help_uses_command_docstrings() -> None:
    output = cli._render_python_tool_help()  # noqa: SLF001

    assert "make provision-act-vars" in output
    assert cli.cmd_write_act_vars.__doc__.strip() in output
    assert "Docs: docs/commands.md" in output


def test_write_commands_doc_uses_command_docstrings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()

    assert cli.cmd_write_commands_doc(None) == 0

    output = (tmp_path / "docs/commands.md").read_text()
    assert "## Python-backed provisioning commands" in output
    assert cli.cmd_provision_auth.__doc__.strip() in output
    assert "## Provisioning notes" in output


def test_print_tool_help(capsys) -> None:
    assert cli.cmd_print_tool_help(None) == 0

    assert "Python tools run through make" in capsys.readouterr().out


def test_parser_help_includes_command_descriptions(capsys) -> None:
    parser = cli.build_parser()

    try:
        parser.parse_args(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit")

    assert "Write local act repository variables" in capsys.readouterr().out


def test_notify_discord_payload(monkeypatch) -> None:
    sent = {}

    class Response:
        def raise_for_status(self) -> None:
            sent["ok"] = True

    def fake_post(url, json, timeout):  # noqa: A002
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
        monkeypatch.setattr(cli.requests, "post", fake_post)
        assert cli.cmd_notify_discord(None) == 0
    finally:
        os.environ.clear()
        os.environ.update(old)

    assert sent["url"] == "https://discord.example"
    fields = sent["json"]["embeds"][0]["fields"]
    assert fields[1]["value"] == "[owner/repo](https://github.com/owner/repo)"
    assert fields[3]["value"] == "[abcdef1](https://github.com/owner/repo/commit/abcdef123456)"


def test_notify_discord_requires_webhook(monkeypatch) -> None:
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    try:
        cli.cmd_notify_discord(None)
    except RuntimeError as exc:
        assert "DISCORD_WEBHOOK_URL" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError")
