from __future__ import annotations

import argparse
import asyncio
import html
import http.server
import json
import logging
import os
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from string import Template
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

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
from public_diary_tools.config import ActVars, active_user_member, build_act_vars, select_project, select_repository
from public_diary_tools.coverage_badge import publish_coverage_badge
from public_diary_tools.envfiles import is_dummy, read_env_file, write_env_file
from public_diary_tools.github_settings import (
    DEFAULT_SETTINGS_FILE,
    GitHubSettingsClient,
    apply_github_settings,
    load_github_settings,
)
from public_diary_tools.json_tools import check_json_configs, format_json_configs
from public_diary_tools.paths import (
    act_secret_file,
    act_var_file,
    discord_webhook_file,
    github_app_file,
    google_drive_token_file,
)
from public_diary_tools.progress import track_web_request, web_request_progress
from public_diary_tools.wiki import stage_wiki_docs

REQUIRED_APIS = [
    "drive.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "serviceusage.googleapis.com",
]

COMMANDS_DOC_TEMPLATE = Path(__file__).with_name("templates") / "commands.md.template"
COMMANDS_DOC_WIDTH = 78
ROOT_MAKEFILE = Path("Makefile")
LOG_LEVEL_ENV_NAMES = ("PUBLIC_DIARY_LOG_LEVEL", "LOG_LEVEL")
LOGGER = logging.getLogger(__name__)
GITHUB_API_VERSION = "2022-11-28"
GITHUB_APP_CLIENT_ID_SECRET = "PUBLIC_DIARY_APP_CLIENT_ID"
GITHUB_APP_PRIVATE_KEY_SECRET = "PUBLIC_DIARY_APP_PRIVATE_KEY"
LEGACY_GITHUB_APP_CLIENT_ID_SECRET = "GITHUB_APP_CLIENT_ID"
LEGACY_GITHUB_APP_PRIVATE_KEY_SECRET = "GITHUB_APP_PRIVATE_KEY"
GITHUB_APP_NAME_MAX_LENGTH = 34


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "line_number": record.lineno,
                "function_name": record.funcName,
                "msg": record.getMessage(),
                "level": record.levelname.lower(),
            },
        )


def _env_log_level() -> str:
    for name in LOG_LEVEL_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value
    return "info"


def _log_level_value(level: str) -> int:
    normalized = level.upper()
    value = logging.getLevelName(normalized)
    if not isinstance(value, int):
        raise ValueError(f"Invalid log level: {level}")
    return value


def _configure_logging(level: str, output: str) -> None:
    handler: logging.Handler
    if output == "stderr":
        handler = logging.StreamHandler(sys.stderr)
    else:
        path = Path(output)
        with path.open("a"):
            pass
        handler = logging.FileHandler(path, mode="a")
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(_log_level_value(level))


def cmd_write_act_vars(_: argparse.Namespace | None) -> int:
    """Write local act repository variables from prompts and dynamic discovery."""
    LOGGER.debug("writing act vars")
    act_vars = build_act_vars(GoogleApis())
    write_env_file(act_var_file(), act_vars.as_env())
    print(f"Wrote {act_var_file()}")
    return 0


def cmd_format_json(_: argparse.Namespace | None) -> int:
    """Format repository JSON config files."""
    changed = format_json_configs()
    if changed:
        print("Formatted JSON config files:")
        for path in changed:
            print(f"- {path}")
    else:
        print("JSON config files already formatted.")
    return 0


def cmd_check_json(_: argparse.Namespace | None) -> int:
    """Validate repository JSON config files without modifying them."""
    unformatted = check_json_configs()
    if unformatted:
        print("JSON config files need formatting:")
        for path in unformatted:
            print(f"- {path}")
        raise RuntimeError('Run make python-tool ARGS="format-json" to format JSON config files.')
    print("JSON config files are formatted.")
    return 0


def cmd_coverage_badge(_: argparse.Namespace | None) -> int:
    """Generate the README test coverage badge from pytest coverage JSON."""
    percent, changed = publish_coverage_badge()
    print(f"Coverage: {percent:.1f}%")
    if changed:
        print("Updated coverage badge files:")
        for path in changed:
            print(f"- {path}")
    else:
        print("Coverage badge files already up to date.")
    return 0


def cmd_stage_wiki_docs(_: argparse.Namespace | None) -> int:
    """Stage docs into a checked-out GitHub wiki directory."""
    wiki_dir = Path(os.environ.get("WIKI_DIR", "wiki"))
    changed = stage_wiki_docs(Path("docs"), wiki_dir)
    print(f"Staged {len(changed)} docs files into {wiki_dir}.")
    return 0


def cmd_upload_github_vars(_: argparse.Namespace | None) -> int:
    """Upload GitHub repository variables from dev/act/vars.env."""
    LOGGER.debug("uploading github vars")
    values = read_env_file(act_var_file())
    if not values:
        raise RuntimeError(f'Missing {act_var_file()}. Run make python-tool ARGS="write-act-vars" first.')
    asyncio.run(_upload_github_vars(values, repository_from_gh(), github_token_from_gh()))
    print(f"Uploaded variables from {act_var_file()}.")
    return 0


def cmd_write_discord_webhook(_: argparse.Namespace | None) -> int:
    """Write the local Discord webhook URL file used by act and secret upload."""
    webhook = _prompt_discord_webhook()
    _write_discord_webhook_file(webhook)
    print(f"Wrote {discord_webhook_file()}")
    return 0


def cmd_upload_github_secrets(_: argparse.Namespace | None) -> int:
    """Upload GitHub repository secrets used by workflows."""
    secrets = _github_secret_values(require_app=True)
    token = github_token_from_gh()
    asyncio.run(_upload_github_secrets(secrets, repository_from_gh(), token))
    print(f"Uploaded GitHub secrets: {', '.join(sorted(secrets))}.")
    return 0


def cmd_apply_github_settings(_: argparse.Namespace | None) -> int:
    """Apply GitHub repository and branch permissions from .github/config."""
    applied = asyncio.run(_apply_github_settings(repository_from_gh(), github_token_from_gh()))
    for item in applied:
        print(f"Applied {item}")
    return 0


def cmd_write_act_files(_: argparse.Namespace | None) -> int:
    """Write local act variable and secret files."""
    if not act_var_file().exists():
        raise RuntimeError(f'Missing {act_var_file()}. Run make python-tool ARGS="write-act-vars" first.')

    values = _github_app_values(required=True)
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


def cmd_write_act_drive_token(_: argparse.Namespace | None) -> int:
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
    LOGGER.debug("minting local act token with service account impersonation")
    token = gcloud_impersonated_token(service_account, [DRIVE_READONLY_SCOPE])
    google_drive_token_file().parent.mkdir(parents=True, exist_ok=True)
    google_drive_token_file().write_text(f"{token}\n")
    google_drive_token_file().chmod(0o600)
    print(f"Wrote {google_drive_token_file()}")
    return 0


def cmd_configure_drive_access(_: argparse.Namespace | None) -> int:
    """Grant the deploy service account read access to the configured Drive target."""
    values = read_env_file(act_var_file())
    service_account = os.environ.get("SERVICE_ACCOUNT_EMAIL") or values.get("GCP_SERVICE_ACCOUNT", "")
    root_folder_id = os.environ.get("DRIVE_TARGET_ID") or values.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")
    shared_drive_id = values.get("GOOGLE_DRIVE_SHARED_DRIVE_ID", "")
    if not service_account:
        raise RuntimeError("SERVICE_ACCOUNT_EMAIL is required or dev/act/vars.env must contain GCP_SERVICE_ACCOUNT.")
    if not root_folder_id and not shared_drive_id:
        raise RuntimeError("DRIVE_TARGET_ID is required or Drive IDs must exist in dev/act/vars.env.")
    act_vars = ActVars(
        gcp_workload_identity_provider="",
        gcp_service_account=service_account,
        google_drive_root_folder_id=root_folder_id,
        google_drive_shared_drive_id=shared_drive_id,
        google_workspace_delegation_enabled="",
        google_workspace_user="",
        google_drive_path="",
    )
    result = _grant_drive_access(GoogleApis(), act_vars)
    print(json.dumps(result, indent=2))
    return 0


async def _upload_github_vars(values: dict[str, str], repo: str, token: str) -> None:
    client = GithubClient(repo, token)
    await asyncio.gather(*(_run_sync(client.set_variable, name, value) for name, value in values.items()))


async def _upload_github_secrets(values: dict[str, str], repo: str, token: str) -> None:
    client = GithubClient(repo, token)
    await asyncio.gather(*(_run_sync(client.set_secret, name, value) for name, value in values.items()))


async def _apply_github_settings(repo: str, token: str) -> list[str]:
    settings_file = Path(os.environ.get("GITHUB_SETTINGS_FILE", DEFAULT_SETTINGS_FILE))
    client = GitHubSettingsClient(repo, token)
    return cast(list[str], await _run_sync(apply_github_settings, load_github_settings(settings_file), client))


async def _run_sync(function: Callable[..., Any], *args: Any) -> Any:
    await asyncio.sleep(0)
    return function(*args)


def _discord_webhook_value() -> str:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook and discord_webhook_file().exists():
        webhook = discord_webhook_file().read_text().strip()
    if not webhook:
        raise RuntimeError(f"DISCORD_WEBHOOK_URL is required or {discord_webhook_file()} must exist.")
    return webhook


def _optional_discord_webhook_value() -> str:
    return os.environ.get("DISCORD_WEBHOOK_URL") or (
        discord_webhook_file().read_text().strip() if discord_webhook_file().exists() else ""
    )


def _github_app_values(required: bool = False) -> dict[str, str]:
    values = {
        GITHUB_APP_CLIENT_ID_SECRET: "",
        GITHUB_APP_PRIVATE_KEY_SECRET: "",
    }
    legacy_keys = {
        LEGACY_GITHUB_APP_CLIENT_ID_SECRET: GITHUB_APP_CLIENT_ID_SECRET,
        LEGACY_GITHUB_APP_PRIVATE_KEY_SECRET: GITHUB_APP_PRIVATE_KEY_SECRET,
    }
    if github_app_file().exists():
        file_values = read_env_file(github_app_file())
        values.update({key: value for key, value in file_values.items() if key in values})
        values.update(
            {
                target: file_values[source]
                for source, target in legacy_keys.items()
                if file_values.get(source) and not values[target]
            },
        )
    values.update(
        {
            target: os.environ[source]
            for source, target in legacy_keys.items()
            if os.environ.get(source) and not values[target]
        },
    )
    values.update(
        {
            key: value
            for key, value in {
                GITHUB_APP_CLIENT_ID_SECRET: os.environ.get(GITHUB_APP_CLIENT_ID_SECRET, ""),
                GITHUB_APP_PRIVATE_KEY_SECRET: os.environ.get(GITHUB_APP_PRIVATE_KEY_SECRET, ""),
            }.items()
            if value
        },
    )
    values = {key: value for key, value in values.items() if value}
    if required and set(values) != {GITHUB_APP_CLIENT_ID_SECRET, GITHUB_APP_PRIVATE_KEY_SECRET}:
        raise RuntimeError(
            f"GitHub App credentials are required. Run "
            f'`make python-tool ARGS="provision-github-app"` or set {GITHUB_APP_CLIENT_ID_SECRET} and '
            f"{GITHUB_APP_PRIVATE_KEY_SECRET}.",
        )
    return values


def _github_secret_values(webhook: str = "", require_app: bool = False) -> dict[str, str]:
    values = _github_app_values(required=require_app)
    webhook = webhook or _optional_discord_webhook_value()
    if webhook:
        values["DISCORD_WEBHOOK_URL"] = webhook
    return values


def _write_github_app_file(client_id: str, private_key: str) -> None:
    write_env_file(
        github_app_file(),
        {
            GITHUB_APP_CLIENT_ID_SECRET: client_id,
            GITHUB_APP_PRIVATE_KEY_SECRET: _escaped_pem(private_key),
        },
    )


def _escaped_pem(private_key: str) -> str:
    return private_key.strip().replace("\n", "\\n")


def _write_discord_webhook_file(webhook: str) -> None:
    discord_webhook_file().parent.mkdir(parents=True, exist_ok=True)
    discord_webhook_file().write_text(f"{webhook}\n")
    discord_webhook_file().chmod(0o600)


def _prompt_discord_webhook() -> str:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook and discord_webhook_file().exists():
        webhook = discord_webhook_file().read_text().strip()
    if not webhook:
        webhook = input("Paste Discord webhook URL, then press Enter: ")
    if not webhook:
        raise RuntimeError("Discord webhook URL is required.")
    return webhook


def _configure_workload_identity(google: GoogleApis, project_number: str, repo: str) -> None:
    pool_id = os.environ.get("WIF_POOL_ID", "github")
    provider_id = os.environ.get("WIF_PROVIDER_ID", "public-diary")
    if not google.workload_identity_pool_exists(project_number, pool_id):
        google.create_workload_identity_pool(
            project_number,
            pool_id,
            os.environ.get("WIF_POOL_DISPLAY_NAME", "GitHub Actions"),
        )
    if not google.workload_identity_provider_exists(project_number, pool_id, provider_id):
        google.create_workload_identity_provider(
            project_number,
            pool_id,
            provider_id,
            repo,
            os.environ.get("WIF_PROVIDER_DISPLAY_NAME", "GitHub repository"),
        )


def _github_wif_principal(project_number: str, pool_id: str, repo: str) -> str:
    return (
        "principalSet://iam.googleapis.com/"
        f"projects/{project_number}/locations/global/workloadIdentityPools/{pool_id}/attribute.repository/{repo}"
    )


def _provision_google_auth(google: GoogleApis, project_id: str, act_vars: ActVars, repo: str) -> None:
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
    wif_pool_id = os.environ.get("WIF_POOL_ID", "github")
    github_principal = _github_wif_principal(project_number, wif_pool_id, repo)
    _configure_workload_identity(google, project_number, repo)
    google.add_service_account_binding(
        project_id,
        service_account,
        "roles/iam.workloadIdentityUser",
        github_principal,
    )
    google.add_service_account_binding(
        project_id,
        service_account,
        "roles/iam.serviceAccountTokenCreator",
        github_principal,
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


def _grant_drive_access(google: GoogleApis, act_vars: ActVars) -> dict[str, str]:
    if act_vars.google_drive_root_folder_id:
        return google.grant_drive_permission(
            act_vars.google_drive_root_folder_id,
            act_vars.gcp_service_account,
            os.environ.get("DRIVE_PERMISSION_ROLE", "reader"),
        )
    if act_vars.google_drive_shared_drive_id:
        return {
            "id": act_vars.google_drive_shared_drive_id,
            "emailAddress": act_vars.gcp_service_account,
            "role": os.environ.get("DRIVE_PERMISSION_ROLE", "reader"),
            "status": "skipped",
            "reason": "Shared Drive root permissions must be managed from Google Drive.",
        }
    raise RuntimeError("A Google Drive shared drive or root folder ID is required.")


def _github_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_request(method: str, path: str, token: str | None = None, payload: dict[str, Any] | None = None) -> Any:
    with track_web_request():
        response = requests.request(
            method,
            f"https://api.github.com{path}",
            headers=_github_headers(token),
            json=payload,
            timeout=30,
        )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return {}


def _github_app_name(repo: str) -> str:
    configured_name = os.environ.get("GITHUB_APP_NAME")
    if configured_name is not None:
        app_name = configured_name.strip()
        if not app_name:
            raise RuntimeError("GITHUB_APP_NAME cannot be empty.")
    else:
        repo_name = repo.rsplit("/", 1)[-1]
        suffix = " automation"
        app_name = f"{repo_name[: GITHUB_APP_NAME_MAX_LENGTH - len(suffix)]}{suffix}"
    if len(app_name) > GITHUB_APP_NAME_MAX_LENGTH:
        raise RuntimeError(f"GitHub App name cannot be longer than {GITHUB_APP_NAME_MAX_LENGTH} characters.")
    return app_name


def _github_app_manifest(repo: str, callback_url: str) -> dict[str, Any]:
    app_name = _github_app_name(repo)
    return {
        "name": app_name,
        "url": f"https://github.com/{repo}",
        "redirect_url": callback_url,
        "public": False,
        "default_permissions": {
            "actions": "read",
            "contents": "write",
            "metadata": "read",
            "pages": "write",
            "pull_requests": "write",
        },
        "default_events": [],
    }


class _ManifestCallbackServer(http.server.HTTPServer):
    code = ""
    github_create_path = "/settings/apps/new"
    manifest_json = "{}"


class _ManifestCallbackHandler(http.server.BaseHTTPRequestHandler):
    server: _ManifestCallbackServer

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name.
        parsed = urlparse(self.path)
        if parsed.path == "/github-app-manifest-start":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_manifest_start_html(self.server.github_create_path, self.server.manifest_json).encode())
            return

        query = parse_qs(parsed.query)
        code = query.get("code", [""])[0]
        if code:
            self.server.code = code
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"GitHub App manifest code received. You can return to the terminal.")
            return
        self.send_response(400)
        self.end_headers()
        self.wfile.write(b"Missing GitHub App manifest code.")

    def log_message(self, _format: str, *args: Any) -> None:
        LOGGER.debug("github app callback request", extra={"args": args})


def _github_app_create_path(owner: str) -> str:
    return f"/organizations/{owner}/settings/apps/new" if owner else "/settings/apps/new"


def _manifest_start_html(github_create_path: str, manifest_json: str) -> str:
    action = html.escape(f"https://github.com{github_create_path}", quote=True)
    manifest = html.escape(manifest_json, quote=True)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Create GitHub App</title>
  </head>
  <body>
    <form id="github-app-manifest" method="post" action="{action}">
      <input type="hidden" name="manifest" value="{manifest}">
      <button type="submit">Create GitHub App</button>
    </form>
    <script>
      document.getElementById("github-app-manifest").submit();
    </script>
  </body>
</html>
"""


def _wait_for_manifest_code(manifest: dict[str, Any], input_fn: Callable[[str], str] = input) -> str:
    with _ManifestCallbackServer(("127.0.0.1", 0), _ManifestCallbackHandler) as server:
        callback_url = f"http://127.0.0.1:{server.server_port}/github-app-manifest-callback"
        manifest["redirect_url"] = callback_url
        owner = os.environ.get("GITHUB_APP_OWNER", "")
        server.github_create_path = _github_app_create_path(owner)
        server.manifest_json = json.dumps(manifest, separators=(",", ":"))
        start_url = f"http://127.0.0.1:{server.server_port}/github-app-manifest-start"
        print("Open this local URL to create the GitHub App, then finish the GitHub prompts:")
        print(start_url)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            pasted = input_fn(
                "Press Enter after your browser reaches the local callback, or paste the returned code/URL: ",
            ).strip()
        finally:
            server.shutdown()
            thread.join(timeout=5)
        if server.code:
            return server.code
        if not pasted:
            raise RuntimeError("GitHub App manifest code was not received.")
        parsed = urlparse(pasted)
        if parsed.query:
            code = parse_qs(parsed.query).get("code", [""])[0]
            if code:
                return code
        return pasted


def _convert_github_app_manifest(code: str) -> dict[str, Any]:
    return cast(dict[str, Any], _github_request("POST", f"/app-manifests/{code}/conversions"))


def _prompt_github_app_installation(app_slug: str, repo: str) -> None:
    print(f"Install the GitHub App for {repo}: https://github.com/apps/{app_slug}/installations/new")
    print("If GitHub asks for repository access, select this repository or all repositories.")
    input("Press Enter after installing the app: ")


def _provision_github_app(repo: str, token: str) -> str:
    manifest = _github_app_manifest(repo, "http://127.0.0.1/")
    app = _convert_github_app_manifest(_wait_for_manifest_code(manifest))
    client_id = str(app["client_id"])
    private_key = str(app["pem"])
    app_slug = str(app["slug"])
    _prompt_github_app_installation(app_slug, repo)
    _write_github_app_file(client_id, private_key)
    asyncio.run(_upload_github_secrets(_github_app_values(required=True), repo, token))
    return app_slug


def cmd_provision_github_app(_: argparse.Namespace | None) -> int:
    """Create a GitHub App, install it on the repository, and upload app secrets."""
    repo = select_repository()
    token = github_token_from_gh()
    app_slug = _provision_github_app(repo, token)
    print(f"Provisioned GitHub App {app_slug}, installed it on {repo}, and wrote {github_app_file()}.")
    return 0


def cmd_provision_auth(_: argparse.Namespace | None) -> int:
    """Create or update Google Cloud auth and GitHub repository variables."""
    LOGGER.info("starting auth provisioning")
    google = GoogleApis()
    project_id = select_project(google)
    act_vars = build_act_vars(google)
    repo = select_repository()
    _provision_google_auth(google, project_id, act_vars, repo)
    asyncio.run(_upload_github_vars(act_vars.as_env(), repo, github_token_from_gh()))
    print(f"Provisioned auth and wrote {act_var_file()}.")
    return 0


async def _provision_all_async(google: GoogleApis, act_vars: ActVars, repo: str, webhook: str) -> None:
    token = github_token_from_gh()
    await asyncio.gather(
        _upload_github_vars(act_vars.as_env(), repo, token),
        _apply_github_settings(repo, token),
        _run_sync(_write_discord_webhook_file, webhook),
        _upload_github_secrets(_github_secret_values(webhook, require_app=True), repo, token),
        _run_sync(_grant_drive_access, google, act_vars),
    )


def cmd_provision_all(_: argparse.Namespace | None) -> int:
    """Discover Drive values and provision Google, GitHub, Discord, and local act inputs."""
    LOGGER.info("starting full provisioning")
    google = GoogleApis()
    project_id = select_project(google)
    act_vars = build_act_vars(google)
    repo = select_repository()
    webhook = _prompt_discord_webhook()
    if not _github_app_values():
        app_slug = _provision_github_app(repo, github_token_from_gh())
        print(f"Provisioned GitHub App {app_slug}.")
    _provision_google_auth(google, project_id, act_vars, repo)
    asyncio.run(_provision_all_async(google, act_vars, repo, webhook))
    cmd_write_act_drive_token(None)
    cmd_write_act_files(None)
    print("Provisioned Google, GitHub, Discord, Drive access, and local act inputs.")
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


def _status_values_from_job_results(job_results: str) -> list[str]:
    values: list[str] = []
    for item in job_results.split(","):
        if "=" not in item:
            continue
        _, value = item.rsplit("=", 1)
        value = value.strip().lower()
        if value:
            values.append(value)
    return values


def _workflow_status_from_job_results(job_results: str) -> tuple[str, int, str]:
    statuses = _status_values_from_job_results(job_results)
    if "failure" in statuses:
        return ("failed", 15158332, "failure")
    if "cancelled" in statuses:
        return ("cancelled", 16753920, "cancelled")
    if statuses and all(status in {"success", "skipped"} for status in statuses):
        return ("succeeded", 3066993, "success")
    return ("completed", 3447003, "completion")


def cmd_notify_discord(_: argparse.Namespace | None) -> int:
    """Send a Discord notification for a GitHub Actions workflow result."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook:
        raise RuntimeError("DISCORD_WEBHOOK_URL is required.")
    repo = os.environ["GITHUB_REPOSITORY"]
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    run_id = os.environ["GITHUB_RUN_ID"]
    run_url = f"{server}/{repo}/actions/runs/{run_id}"
    sha = os.environ.get("GITHUB_SHA", "")
    job_results = os.environ.get("DISCORD_JOB_RESULTS", "unknown")
    status, color, notification_kind = _workflow_status_from_job_results(job_results)
    payload = {
        "username": "GitHub Actions",
        "embeds": [
            {
                "title": f"Workflow {status}: {os.environ.get('GITHUB_WORKFLOW', 'unknown workflow')}",
                "color": color,
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
                    {"name": "Job results", "value": job_results, "inline": False},
                ],
            }
        ],
    }
    with track_web_request():
        requests.post(webhook, json=payload, timeout=10).raise_for_status()
    print(f"Discord {notification_kind} notification sent.")
    return 0


def _first_doc_line(function: Callable[..., Any]) -> str:
    return (function.__doc__ or "").strip().splitlines()[0]


def _command_functions() -> dict[str, Callable[..., int]]:
    return {
        "write-act-vars": cmd_write_act_vars,
        "format-json": cmd_format_json,
        "check-json": cmd_check_json,
        "coverage-badge": cmd_coverage_badge,
        "stage-wiki-docs": cmd_stage_wiki_docs,
        "upload-github-vars": cmd_upload_github_vars,
        "write-discord-webhook": cmd_write_discord_webhook,
        "upload-github-secrets": cmd_upload_github_secrets,
        "apply-github-settings": cmd_apply_github_settings,
        "write-act-drive-token": cmd_write_act_drive_token,
        "write-act-files": cmd_write_act_files,
        "configure-drive-access": cmd_configure_drive_access,
        "provision-github-app": cmd_provision_github_app,
        "provision-auth": cmd_provision_auth,
        "provision-all": cmd_provision_all,
        "notify-discord": cmd_notify_discord,
        "write-commands-doc": cmd_write_commands_doc,
    }


def _makefile_paths(makefile: Path = ROOT_MAKEFILE) -> list[Path]:
    paths = [makefile]
    if not makefile.exists():
        return paths
    for line in makefile.read_text().splitlines():
        words = line.strip().split()
        if words and words[0] == "include":
            paths.extend(Path(word) for word in words[1:])
    return paths


def _make_targets(makefile: Path = ROOT_MAKEFILE) -> list[str]:
    targets: list[str] = []
    for path in _makefile_paths(makefile):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            if not line.startswith(".PHONY:"):
                continue
            for target in line.removeprefix(".PHONY:").split():
                if target not in targets:
                    targets.append(target)
    return targets


def _render_common_commands() -> str:
    return "\n".join(f"- `make {target}`" for target in _make_targets())


class CommandsDocHelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog: str) -> None:
        super().__init__(prog, width=COMMANDS_DOC_WIDTH)


def _render_python_tool_commands() -> str:
    sections = []
    for command, function in _command_functions().items():
        parser = argparse.ArgumentParser(
            prog=f"public-diary-tools {command}",
            description=_first_doc_line(function),
            formatter_class=CommandsDocHelpFormatter,
        )
        sections.append(f"### `{command}`\n\n```text\n{parser.format_help().strip()}\n```")
    return "\n\n".join(sections)


def _render_commands_doc(template_path: Path = COMMANDS_DOC_TEMPLATE) -> str:
    template = Template(template_path.read_text())
    return template.substitute(
        common_commands=_render_common_commands(),
        python_tool_commands=_render_python_tool_commands(),
    ).rstrip()


def cmd_write_commands_doc(_: argparse.Namespace | None) -> int:
    """Regenerate docs/commands.md from Python command help strings."""
    Path("docs/commands.md").write_text(f"{_render_commands_doc()}\n")
    print("Wrote docs/commands.md")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="public-diary-tools")
    parser.add_argument(
        "--log-level",
        default=_env_log_level(),
        help="JSON log level; env PUBLIC_DIARY_LOG_LEVEL or LOG_LEVEL also works.",
    )
    parser.add_argument(
        "--log-output",
        default="stderr",
        help="JSON log output path to append to, or stderr.",
    )
    parser.add_argument("--debug", action="store_true", help="Shortcut for --log-level debug.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, function in _command_functions().items():
        subparser = subparsers.add_parser(name, help=_first_doc_line(function), description=_first_doc_line(function))
        subparser.set_defaults(func=function)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        log_level = "debug" if getattr(args, "debug", False) else str(getattr(args, "log_level", _env_log_level()))
        log_output = str(getattr(args, "log_output", "stderr"))
        _configure_logging(log_level, log_output)
        LOGGER.debug("configured logging")
        func = cast(Callable[[argparse.Namespace], int], args.func)
        if os.environ.get("PUBLIC_DIARY_WEB_PROGRESS", "1").lower() in {"0", "false", "no"}:
            return func(args)
        with web_request_progress():
            return func(args)
    except KeyboardInterrupt:
        print("Cancelled by user.", file=sys.stderr)
        return 130
    except EOFError:
        print("Input cancelled by user.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI should print clean operational errors.
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
