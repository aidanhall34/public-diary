from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

from public_diary_tools.clients import (
    DRIVE_READONLY_SCOPE,
    GithubClient,
    GoogleApis,
    active_gcloud_account,
    gcloud_impersonated_token,
    github_token_from_gh,
    repository_from_gh,
)
from public_diary_tools.config import active_user_member, build_act_vars, select_project
from public_diary_tools.envfiles import is_dummy, read_env_file, write_env_file
from public_diary_tools.paths import act_secret_file, act_var_file, discord_webhook_file, google_drive_token_file

REQUIRED_APIS = [
    "drive.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "serviceusage.googleapis.com",
]


def cmd_write_act_vars(_: argparse.Namespace) -> int:
    """Write local act repository variables from prompts and dynamic discovery."""
    act_vars = build_act_vars(GoogleApis())
    write_env_file(act_var_file(), act_vars.as_env())
    print(f"Wrote {act_var_file()}")
    return 0


def cmd_upload_github_vars(_: argparse.Namespace) -> int:
    """Upload GitHub repository variables from dev/act/vars.env."""
    values = read_env_file(act_var_file())
    if not values:
        raise RuntimeError(f"Missing {act_var_file()}. Run make provision-act-vars first.")
    client = GithubClient(repository_from_gh(), github_token_from_gh())
    for name, value in values.items():
        client.set_variable(name, value)
    print(f"Uploaded variables from {act_var_file()}.")
    return 0


def cmd_write_discord_webhook(_: argparse.Namespace) -> int:
    """Write the local Discord webhook URL file used by act and secret upload."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        webhook = input("Paste Discord webhook URL, then press Enter: ")
    if not webhook:
        raise RuntimeError("Discord webhook URL is required.")
    discord_webhook_file().parent.mkdir(parents=True, exist_ok=True)
    discord_webhook_file().write_text(f"{webhook}\n")
    discord_webhook_file().chmod(0o600)
    print(f"Wrote {discord_webhook_file()}")
    return 0


def cmd_upload_github_secrets(_: argparse.Namespace) -> int:
    """Upload repository secrets such as DISCORD_WEBHOOK_URL."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook and discord_webhook_file().exists():
        webhook = discord_webhook_file().read_text().strip()
    if not webhook:
        raise RuntimeError(f"DISCORD_WEBHOOK_URL is required or {discord_webhook_file()} must exist.")
    GithubClient(repository_from_gh(), github_token_from_gh()).set_secret("DISCORD_WEBHOOK_URL", webhook)
    print("Uploaded DISCORD_WEBHOOK_URL.")
    return 0


def cmd_write_act_files(_: argparse.Namespace) -> int:
    """Write local act variable and secret files."""
    if not act_var_file().exists():
        raise RuntimeError(f"Missing {act_var_file()}. Run make provision-act-vars first.")

    values = {"GITHUB_TOKEN": github_token_from_gh()}
    if discord_webhook_file().exists():
        values["DISCORD_WEBHOOK_URL"] = discord_webhook_file().read_text().strip()
    if google_drive_token_file().exists():
        values["GOOGLE_DRIVE_ACCESS_TOKEN"] = google_drive_token_file().read_text().strip()
    write_env_file(act_secret_file(), values)
    print(f"Wrote {act_secret_file()}")
    return 0


def _service_account_from_vars() -> str:
    service_account = os.environ.get("GCP_SERVICE_ACCOUNT") or read_env_file(act_var_file()).get(
        "GCP_SERVICE_ACCOUNT",
        "",
    )
    if not service_account:
        raise RuntimeError(f"GCP_SERVICE_ACCOUNT is required or {act_var_file()} must contain it.")
    if is_dummy(service_account):
        raise RuntimeError(f"{act_var_file()} contains dummy GCP_SERVICE_ACCOUNT: {service_account}")
    return service_account


def _project_from_service_account(service_account: str) -> str:
    project = os.environ.get("GCP_PROJECT_ID")
    if project:
        return project
    domain = service_account.split("@", 1)[1]
    return domain.removesuffix(".iam.gserviceaccount.com")


def cmd_write_act_drive_token(_: argparse.Namespace) -> int:
    """Write a local Google Drive read-only token for act."""
    service_account = _service_account_from_vars()
    project_id = _project_from_service_account(service_account)
    google = GoogleApis()
    if not google.service_account_exists(project_id, service_account):
        raise RuntimeError(f"Service account not found: {service_account}")

    user = os.environ.get("GCLOUD_ACCOUNT") or active_gcloud_account()
    google.add_service_account_binding(
        project_id,
        service_account,
        "roles/iam.serviceAccountTokenCreator",
        f"user:{user}",
    )
    token = gcloud_impersonated_token(service_account, [DRIVE_READONLY_SCOPE])
    google_drive_token_file().parent.mkdir(parents=True, exist_ok=True)
    google_drive_token_file().write_text(f"{token}\n")
    google_drive_token_file().chmod(0o600)
    print(f"Wrote {google_drive_token_file()}")
    return 0


def cmd_configure_drive_access(_: argparse.Namespace) -> int:
    """Grant the deploy service account read access to the configured Drive target."""
    values = read_env_file(act_var_file())
    service_account = os.environ.get("SERVICE_ACCOUNT_EMAIL") or values.get("GCP_SERVICE_ACCOUNT", "")
    target_id = (
        os.environ.get("DRIVE_TARGET_ID")
        or values.get("GOOGLE_DRIVE_ROOT_FOLDER_ID")
        or values.get("GOOGLE_DRIVE_SHARED_DRIVE_ID")
    )
    if not service_account:
        raise RuntimeError("SERVICE_ACCOUNT_EMAIL is required or dev/act/vars.env must contain GCP_SERVICE_ACCOUNT.")
    if not target_id:
        raise RuntimeError("DRIVE_TARGET_ID is required or Drive IDs must exist in dev/act/vars.env.")
    role = os.environ.get("DRIVE_PERMISSION_ROLE", "reader")
    result = GoogleApis().grant_drive_permission(target_id, service_account, role)
    print(json.dumps(result, indent=2))
    return 0


def cmd_provision_auth(_: argparse.Namespace) -> int:
    """Create or update Google Cloud auth and GitHub repository variables."""
    google = GoogleApis()
    project_id = select_project(google)
    act_vars = build_act_vars(google)
    service_account = act_vars.gcp_service_account
    account_id = service_account.split("@", 1)[0]

    google.enable_services(project_id, REQUIRED_APIS)
    if not google.service_account_exists(project_id, service_account):
        google.create_service_account(
            project_id,
            account_id,
            os.environ.get("SERVICE_ACCOUNT_DISPLAY_NAME", "Public Diary deploy"),
        )

    project_number = google.project_number(project_id)
    repo = repository_from_gh()
    wif_pool_id = os.environ.get("WIF_POOL_ID", "github")
    google.add_service_account_binding(
        project_id,
        service_account,
        "roles/iam.workloadIdentityUser",
        (
            "principalSet://iam.googleapis.com/"
            f"projects/{project_number}/locations/global/workloadIdentityPools/{wif_pool_id}/attribute.repository/{repo}"
        ),
    )
    google.add_service_account_binding(
        project_id,
        service_account,
        "roles/iam.serviceAccountTokenCreator",
        f"serviceAccount:{service_account}",
    )
    google.add_service_account_binding(
        project_id,
        service_account,
        "roles/iam.serviceAccountTokenCreator",
        active_user_member(),
    )

    write_env_file(act_var_file(), act_vars.as_env())
    github = GithubClient(repo, github_token_from_gh())
    for name, value in act_vars.as_env().items():
        github.set_variable(name, value)
    print(f"Provisioned auth and wrote {act_var_file()}.")
    return 0


def _format_duration(started_at: str) -> str:
    if not started_at:
        return "unknown"
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    elapsed = max(0, int((datetime.now(UTC) - started).total_seconds()))
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def cmd_notify_discord(_: argparse.Namespace) -> int:
    """Send a Discord failure notification for GitHub Actions."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL is required.")
    repo = os.environ["GITHUB_REPOSITORY"]
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ["GITHUB_RUN_ID"]
    run_url = f"{server}/{repo}/actions/runs/{run_id}"
    sha = os.environ.get("GITHUB_SHA", "")
    payload = {
        "username": "GitHub Actions",
        "embeds": [
            {
                "title": f"Workflow failed: {os.environ.get('GITHUB_WORKFLOW', 'unknown workflow')}",
                "color": 15158332,
                "fields": [
                    {
                        "name": "Duration",
                        "value": _format_duration(os.environ.get("GITHUB_RUN_STARTED_AT", "")),
                        "inline": True,
                    },
                    {"name": "Repository", "value": f"[{repo}]({server}/{repo})", "inline": True},
                    {
                        "name": "Run",
                        "value": f"[run #{os.environ.get('GITHUB_RUN_NUMBER', 'unknown')}]({run_url})",
                        "inline": True,
                    },
                    {
                        "name": "Commit",
                        "value": f"[{sha[:7] or 'unknown'}]({server}/{repo}/commit/{sha})",
                        "inline": True,
                    },
                    {"name": "Ref", "value": os.environ.get("GITHUB_REF_NAME", "unknown"), "inline": True},
                    {"name": "Actor", "value": os.environ.get("GITHUB_ACTOR", "unknown"), "inline": True},
                    {"name": "Job results", "value": os.environ.get("DISCORD_JOB_RESULTS", "unknown"), "inline": False},
                ],
            }
        ],
    }
    requests.post(webhook, json=payload, timeout=10).raise_for_status()
    print("Discord failure notification sent.")
    return 0


PYTHON_MAKE_TARGETS = {
    "provision-auth": "provision-auth",
    "configure-drive-access": "provision-drive-access",
    "write-act-vars": "provision-act-vars",
    "upload-github-vars": "provision-github-vars",
    "write-discord-webhook": "provision-discord-webhook-file",
    "upload-github-secrets": "provision-github-secrets",
    "write-act-drive-token": "provision-act-drive-token",
    "write-act-files": "provision-act-files",
}


def _first_doc_line(function) -> str:
    return (function.__doc__ or "").strip().splitlines()[0]


def _command_functions() -> dict[str, object]:
    return {
        "write-act-vars": cmd_write_act_vars,
        "upload-github-vars": cmd_upload_github_vars,
        "write-discord-webhook": cmd_write_discord_webhook,
        "upload-github-secrets": cmd_upload_github_secrets,
        "write-act-drive-token": cmd_write_act_drive_token,
        "write-act-files": cmd_write_act_files,
        "configure-drive-access": cmd_configure_drive_access,
        "provision-auth": cmd_provision_auth,
        "notify-discord": cmd_notify_discord,
        "print-tool-help": cmd_print_tool_help,
        "write-commands-doc": cmd_write_commands_doc,
    }


def _render_python_tool_help() -> str:
    lines = [
        "Python tools run through make with uv and .venv activated.",
        "",
        "Common setup flow:",
        "  make provision-act-vars",
        "  make provision-github-vars",
        "  make provision-discord-webhook-file",
        "  make provision-github-secrets",
        "  gcloud auth login",
        "  make provision-act-drive-token",
        "  make provision-act-files",
        "  make act-run-publish",
        "",
        "Python-backed Make targets:",
    ]
    for command, target in PYTHON_MAKE_TARGETS.items():
        lines.append(f"  make {target:<32} {_first_doc_line(_command_functions()[command])}")
    lines.extend(
        [
            "",
            "Direct CLI form:",
            "  PYTHONPATH=dev/scripts uv run python -m public_diary_tools.cli --help",
            "  PYTHONPATH=dev/scripts uv run python -m public_diary_tools.cli <command>",
            "",
            "Docs: docs/commands.md",
        ],
    )
    return "\n".join(lines)


def _render_commands_doc() -> str:
    common_commands = {
        "pre-commit": "regenerate docs and fail if generated docs need to be staged",
        "test": "run pytest, check makefiles, and dry-run the GitHub Actions workflows with act",
        "setup": "install root and Quartz dependencies, configure hooks, bootstrap Quartz, and generate Quartz config",
        "build": "pull the latest notes, bootstrap Quartz if needed, and build the static site",
        "serve": "pull the latest notes, bootstrap Quartz if needed, and serve the site locally with Quartz",
        "docs-commands": "regenerate docs/commands.md from Python command help strings",
        "python-tools": "print the Python tooling usage guide",
        "act-run-publish": "run the deploy workflow build job locally with act",
        "ruff": "lint Python tooling with Ruff",
        "yamllint": "lint YAML files with yamllint",
        "checkmake": "lint makefiles with checkmake",
        "markdownlint": "lint Markdown files with markdownlint",
        "lint": "run all linting recipes",
        "pytests": "run Python tests with pytest and coverage",
    }
    lines = [
        "# Commands",
        "",
        "## Main components",
        "",
        "- `Makefile`: local setup, staging, build, provisioning, and validation entry points",
        "- `config/quartz-site.json`: source-of-truth site settings used to generate `quartz/quartz.config.ts`",
        "- `config/quartz-layout.json`: source-of-truth layout settings used to generate `quartz/quartz.layout.ts`",
        "- `dev/makefiles/`: composable makefile fragments for repo setup, Quartz, Drive sync, docs, "
        "provisioning, and `act`",
        "- `dev/scripts/public_diary_tools/`: Python 3.13 provisioning, GitHub, Google Drive, Discord, "
        "and `act` helper package with colocated tests",
        "- `pyproject.toml`: Python dependencies, Ruff config, pytest config, and coverage threshold",
        "- `.github/workflows/deploy-pages.yml`: scheduled and on-demand Pages deployment",
        "- `.github/workflows/sync-wiki.yml`: publishes `docs/` to the GitHub wiki",
        "- `.githooks/`: tracked git hooks configured automatically by `make build` or `make serve`",
        "- `docs/`: project documentation mirrored to the wiki",
        "",
        "## Common commands",
        "",
    ]
    lines.extend(f"- `make {target}`: {description}" for target, description in common_commands.items())
    lines.extend(
        [
            "",
            "## Python-backed provisioning commands",
            "",
        ],
    )
    for command, target in PYTHON_MAKE_TARGETS.items():
        lines.append(f"- `make {target}`: {_first_doc_line(_command_functions()[command])}")
    lines.extend(
        [
            "",
            "The same tools can be run directly with:",
            "",
            "```sh",
            "PYTHONPATH=dev/scripts uv run python -m public_diary_tools.cli --help",
            "PYTHONPATH=dev/scripts uv run python -m public_diary_tools.cli <command>",
            "```",
            "",
            "Regenerate this command list from Python help strings with:",
            "",
            "```sh",
            "make docs-commands",
            "```",
            "",
            "## Provisioning notes",
            "",
            "This repository uses GitHub Actions OIDC, Google Workload Identity Federation, and a Google Cloud "
            "service account to read the Google Drive vault without storing a Google key in GitHub.",
            "",
            "Authenticate locally before provisioning:",
            "",
            "```sh",
            "gcloud auth login --enable-gdrive-access",
            "gh auth login",
            "```",
            "",
            "If the provisioning run needs to configure Google Drive sharing, authenticate application-default "
            "credentials with Drive permission-management scope:",
            "",
            "```sh",
            "gcloud auth application-default login \\",
            "  --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive",
            "```",
            "",
            "`make provision-auth` enables the required Google Cloud APIs, creates or reuses the deploy service "
            "account, configures Workload Identity Federation for this repository, grants token creation "
            "permissions needed by GitHub Actions and local `act`, uploads GitHub repository variables, "
            "and writes `dev/act/vars.env`. No Google service account key is generated.",
            "",
            "The GitHub Actions build mints a short-lived OAuth access token with only "
            "`https://www.googleapis.com/auth/drive.readonly` and passes it directly to `rclone`.",
            "",
            "Google Drive permissions are managed through the Drive API, not a `gcloud drive` command group. "
            "Use `make provision-drive-access` after `dev/act/vars.env` exists, or set `DRIVE_TARGET_ID` "
            "to a Shared Drive ID, folder ID, or file ID. For Shared Drives, the authenticated user must be "
            "an organizer. Set `DRIVE_USE_DOMAIN_ADMIN_ACCESS=true` only when making Workspace administrator "
            "changes across the domain.",
            "",
            "Prefer Shared Drive membership when possible. If the vault must stay in a user's My Drive, configure "
            "Google Workspace domain-wide delegation for the service account, authorize only the Drive scopes "
            "needed, and set `GOOGLE_WORKSPACE_USER`.",
            "",
            "GitHub repository variables written by the tooling:",
            "",
            "- `GCP_WORKLOAD_IDENTITY_PROVIDER`",
            "- `GCP_SERVICE_ACCOUNT`",
            "- `GOOGLE_DRIVE_SHARED_DRIVE_ID`",
            "- `GOOGLE_DRIVE_ROOT_FOLDER_ID`",
            "- `GOOGLE_DRIVE_PATH`",
            "- `GOOGLE_WORKSPACE_USER`",
            "",
            "Discord failure notifications use the `DISCORD_WEBHOOK_URL` repository secret. Write the local file "
            "with `make provision-discord-webhook-file`, then upload it with `make provision-github-secrets`. "
            "GitHub secrets are write-only through `gh`, so the tooling uploads the value but cannot read it "
            "back later.",
            "",
            "Generate local `act` inputs with:",
            "",
            "```sh",
            "make provision-act-vars",
            "make provision-act-drive-token",
            "make provision-act-files",
            "```",
            "",
            "This writes `dev/act/vars.env`, `dev/act/secrets.env`, and `dev/act/google-drive-access-token`. "
            "These files are intentionally ignored by git. The secrets file includes a short-lived "
            "`GITHUB_TOKEN` from `gh auth token`, and includes `DISCORD_WEBHOOK_URL` and "
            "`GOOGLE_DRIVE_ACCESS_TOKEN` when their local files exist.",
            "",
            "`make provision-act-vars` discovers the current `gcloud` project, lists accessible projects when "
            "needed, prompts for missing values, ignores stale dummy values, and can list visible Shared Drives "
            "after `gcloud auth login --enable-gdrive-access`.",
        ],
    )
    return "\n".join(lines)


def cmd_print_tool_help(_: argparse.Namespace) -> int:
    """Print the Python tooling usage guide."""
    print(_render_python_tool_help())
    return 0


def cmd_write_commands_doc(_: argparse.Namespace) -> int:
    """Regenerate docs/commands.md from Python command help strings."""
    Path("docs/commands.md").write_text(f"{_render_commands_doc()}\n")
    print("Wrote docs/commands.md")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="public-diary-tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, function in _command_functions().items():
        subparser = subparsers.add_parser(name, help=_first_doc_line(function), description=_first_doc_line(function))
        subparser.set_defaults(func=function)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - CLI should print clean operational errors.
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
