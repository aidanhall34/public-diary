from __future__ import annotations

import os
from pathlib import Path


def act_dir() -> Path:
    return Path(os.environ.get("ACT_DIR", "dev/act"))


def act_var_file() -> Path:
    return Path(os.environ.get("ACT_VAR_FILE", act_dir() / "vars.env"))


def act_secret_file() -> Path:
    return Path(os.environ.get("ACT_SECRET_FILE", act_dir() / "secrets.env"))


def discord_webhook_file() -> Path:
    return Path(os.environ.get("DISCORD_WEBHOOK_FILE", act_dir() / "discord-webhook-url"))


def google_drive_token_file() -> Path:
    return Path(os.environ.get("GOOGLE_DRIVE_TOKEN_FILE", act_dir() / "google-drive-access-token"))


def github_app_file() -> Path:
    return Path(os.environ.get("GITHUB_APP_FILE", act_dir() / "github-app.env"))
