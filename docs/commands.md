# Commands

## Main components

- `Makefile`: local setup, staging, build, provisioning, and validation entry points
- `config/quartz-site.json`: source-of-truth site settings used to generate `quartz/quartz.config.ts`
- `config/quartz-layout.json`: source-of-truth layout settings used to generate `quartz/quartz.layout.ts`
- `dev/makefiles/`: composable makefile fragments for repo setup, Quartz, Drive sync, docs, provisioning, and
  `act`
- `dev/scripts/public_diary_tools/`: Python 3.13 provisioning, GitHub, Google Drive, Discord, and `act` helper
  package with colocated tests
- `pyproject.toml`: Python dependencies, Ruff config, pytest config, and coverage threshold
- `.github/workflows/pr-validation.yml`: pull request lint and test validation
- `.github/workflows/deploy-pages.yml`: scheduled and on-demand Pages deployment
- `.github/workflows/sync-wiki.yml`: publishes `docs/` to the GitHub wiki
- `.githooks/`: tracked git hooks configured automatically by `make build` or `make serve`
- `docs/`: project documentation mirrored to the wiki

## Common commands

- `make setup`
- `make pre-commit`
- `make lint`
- `make test`
- `make build`
- `make serve`
- `make repo-setup`
- `make repo-root-deps`
- `make quartz-bootstrap`
- `make quartz-configure`
- `make quartz-deps`
- `make quartz-stage`
- `make quartz-build`
- `make quartz-serve`
- `make quartz-clean`
- `make notes-clone`
- `make docs-readme-sync`
- `make docs-commands`
- `make docs-generated-check`
- `make venv`
- `make ruff`
- `make mypy`
- `make yamllint`
- `make jsonlint`
- `make pytests`
- `make coverage-badge`
- `make checkmake`
- `make markdownlint`
- `make act-files`
- `make act-test-pr-validation`
- `make act-test-publish`
- `make act-test-sync-wiki`
- `make act-run-publish`
- `make python-help`
- `make python-tool`

## Python Tool Commands

### `write-act-vars`

```text
usage: public-diary-tools write-act-vars [-h]

Write local act repository variables from prompts and dynamic discovery.

options:
  -h, --help  show this help message and exit
```

### `format-json`

```text
usage: public-diary-tools format-json [-h]

Format repository JSON config files.

options:
  -h, --help  show this help message and exit
```

### `check-json`

```text
usage: public-diary-tools check-json [-h]

Validate repository JSON config files without modifying them.

options:
  -h, --help  show this help message and exit
```

### `coverage-badge`

```text
usage: public-diary-tools coverage-badge [-h]

Generate the README test coverage badge from pytest coverage JSON.

options:
  -h, --help  show this help message and exit
```

### `upload-github-vars`

```text
usage: public-diary-tools upload-github-vars [-h]

Upload GitHub repository variables from dev/act/vars.env.

options:
  -h, --help  show this help message and exit
```

### `write-discord-webhook`

```text
usage: public-diary-tools write-discord-webhook [-h]

Write the local Discord webhook URL file used by act and secret upload.

options:
  -h, --help  show this help message and exit
```

### `upload-github-secrets`

```text
usage: public-diary-tools upload-github-secrets [-h]

Upload repository secrets such as DISCORD_WEBHOOK_URL.

options:
  -h, --help  show this help message and exit
```

### `apply-github-settings`

```text
usage: public-diary-tools apply-github-settings [-h]

Apply GitHub repository and branch permissions from .github/config.

options:
  -h, --help  show this help message and exit
```

### `write-act-drive-token`

```text
usage: public-diary-tools write-act-drive-token [-h]

Write a local Google Drive read-only token for act.

options:
  -h, --help  show this help message and exit
```

### `write-act-files`

```text
usage: public-diary-tools write-act-files [-h]

Write local act variable and secret files.

options:
  -h, --help  show this help message and exit
```

### `configure-drive-access`

```text
usage: public-diary-tools configure-drive-access [-h]

Grant the deploy service account read access to the configured Drive
target.

options:
  -h, --help  show this help message and exit
```

### `provision-auth`

```text
usage: public-diary-tools provision-auth [-h]

Create or update Google Cloud auth and GitHub repository variables.

options:
  -h, --help  show this help message and exit
```

### `provision-all`

```text
usage: public-diary-tools provision-all [-h]

Discover Drive values and provision Google, GitHub, Discord, and local
act inputs.

options:
  -h, --help  show this help message and exit
```

### `notify-discord`

```text
usage: public-diary-tools notify-discord [-h]

Send a Discord failure notification for GitHub Actions.

options:
  -h, --help  show this help message and exit
```

### `write-commands-doc`

```text
usage: public-diary-tools write-commands-doc [-h]

Regenerate docs/commands.md from Python command help strings.

options:
  -h, --help  show this help message and exit
```

Run tools through Make with:

```sh
make python-tool ARGS="<command> [options]"
make python-help
make python-help TOOL=<command>
```

Regenerate this command list from Python help strings with:

```sh
make docs-commands
```

Apply repository and branch protection settings from `.github/config/repository-permissions.json` with:

```sh
make python-tool ARGS="apply-github-settings"
```

## Provisioning notes

This repository uses GitHub Actions OIDC, Google Workload Identity Federation, and a Google Cloud service account to
read the Google Drive vault without storing a Google key in GitHub.

Authenticate locally before provisioning:

```sh
gcloud auth login --enable-gdrive-access
gh auth login
```

If the provisioning run needs to configure Google Drive sharing, authenticate application-default credentials with Drive
permission-management scope:

```sh
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive
```

`make python-tool ARGS="provision-all"` discovers Drive values and provisions Google Cloud, Workload Identity
Federation, GitHub repository settings, Discord notifications, Drive access, and local `act` files in one flow.

`make python-tool ARGS="provision-auth"` enables the required Google Cloud APIs, creates or reuses the deploy service
account, configures Workload Identity Federation for this repository, grants token creation permissions needed by GitHub
Actions and local `act`, uploads GitHub repository variables, and writes `dev/act/vars.env`. No Google service account
key is generated.

The GitHub Actions build mints a short-lived OAuth access token with only
`https://www.googleapis.com/auth/drive.readonly` and passes it directly to `rclone`.

Google Drive permissions are managed through the Drive API, not a `gcloud drive` command group. Use
`make python-tool ARGS="configure-drive-access"` after `dev/act/vars.env` exists, or set `DRIVE_TARGET_ID` to a Shared
Drive ID, folder ID, or file ID. For Shared Drives, the authenticated user must be an organizer. Set
`DRIVE_USE_DOMAIN_ADMIN_ACCESS=true` only when making Workspace administrator changes across the domain.

Prefer Shared Drive membership when possible. If the vault must stay in a user's My Drive, configure Google Workspace
domain-wide delegation for the service account, authorize only the Drive scopes needed, and set `GOOGLE_WORKSPACE_USER`.

GitHub repository variables written by the tooling:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `GOOGLE_DRIVE_SHARED_DRIVE_ID`
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`
- `GOOGLE_DRIVE_PATH`
- `GOOGLE_WORKSPACE_USER`

Discord failure notifications use the `DISCORD_WEBHOOK_URL` repository secret. Write the local file with
`make python-tool ARGS="write-discord-webhook"`, then upload it with
`make python-tool ARGS="upload-github-secrets"`. GitHub secrets are write-only through `gh`, so the tooling uploads the
value but cannot read it back later.

Generate local `act` inputs with:

```sh
make python-tool ARGS="write-act-vars"
make python-tool ARGS="write-act-drive-token"
make python-tool ARGS="write-act-files"
```

This writes `dev/act/vars.env`, `dev/act/secrets.env`, and `dev/act/google-drive-access-token`. These files are
intentionally ignored by git. The secrets file includes a short-lived `GITHUB_TOKEN` from `gh auth token`, and includes
`DISCORD_WEBHOOK_URL` and `GOOGLE_DRIVE_ACCESS_TOKEN` when their local files exist.

`make python-tool ARGS="write-act-vars"` discovers the current `gcloud` project, lists accessible projects with a custom
option when needed, prompts for missing values, ignores stale dummy values, and can list visible Shared Drives after
`gcloud auth login --enable-gdrive-access`.
