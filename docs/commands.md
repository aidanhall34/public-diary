# Commands

## Main components

- `Makefile`: local setup, staging, build, provisioning, and validation entry points
- `config/quartz-site.json`: source-of-truth site settings used to generate `quartz/quartz.config.ts`
- `config/quartz-layout.json`: source-of-truth layout settings used to generate `quartz/quartz.layout.ts`
- `dev/makefiles/`: composable makefile fragments for repo setup, Quartz, Drive sync, docs, provisioning, and `act`
- `dev/scripts/public_diary_tools/`: Python 3.13 provisioning, GitHub, Google Drive, Discord, and `act` helper package with colocated tests
- `pyproject.toml`: Python dependencies, Ruff config, pytest config, and coverage threshold
- `.github/workflows/deploy-pages.yml`: scheduled and on-demand Pages deployment
- `.github/workflows/sync-wiki.yml`: publishes `docs/` to the GitHub wiki
- `.githooks/`: tracked git hooks configured automatically by `make build` or `make serve`
- `docs/`: project documentation mirrored to the wiki

## Common commands

- `make pre-commit`: regenerate docs and fail if generated docs need to be staged
- `make test`: run pytest, check makefiles, and dry-run the GitHub Actions workflows with act
- `make setup`: install root and Quartz dependencies, configure hooks, bootstrap Quartz, and generate Quartz config
- `make build`: pull the latest notes, bootstrap Quartz if needed, and build the static site
- `make serve`: pull the latest notes, bootstrap Quartz if needed, and serve the site locally with Quartz
- `make docs-commands`: regenerate docs/commands.md from Python command help strings
- `make python-tools`: print the Python tooling usage guide
- `make act-run-publish`: run the deploy workflow build job locally with act
- `make ruff`: lint Python tooling with Ruff
- `make yamllint`: lint YAML files with yamllint
- `make checkmake`: lint makefiles with checkmake
- `make markdownlint`: lint Markdown files with markdownlint
- `make lint`: run all linting recipes
- `make pytests`: run Python tests with pytest and coverage

## Python-backed provisioning commands

- `make provision-auth`: Create or update Google Cloud auth and GitHub repository variables.
- `make provision-drive-access`: Grant the deploy service account read access to the configured Drive target.
- `make provision-act-vars`: Write local act repository variables from prompts and dynamic discovery.
- `make provision-github-vars`: Upload GitHub repository variables from dev/act/vars.env.
- `make provision-discord-webhook-file`: Write the local Discord webhook URL file used by act and secret upload.
- `make provision-github-secrets`: Upload repository secrets such as DISCORD_WEBHOOK_URL.
- `make provision-act-drive-token`: Write a local Google Drive read-only token for act.
- `make provision-act-files`: Write local act variable and secret files.

The same tools can be run directly with:

```sh
PYTHONPATH=dev/scripts uv run python -m public_diary_tools.cli --help
PYTHONPATH=dev/scripts uv run python -m public_diary_tools.cli <command>
```

Regenerate this command list from Python help strings with:

```sh
make docs-commands
```

## Provisioning notes

This repository uses GitHub Actions OIDC, Google Workload Identity Federation, and a Google Cloud service account to read the Google Drive vault without storing a Google key in GitHub.

Authenticate locally before provisioning:

```sh
gcloud auth login --enable-gdrive-access
gh auth login
```

If the provisioning run needs to configure Google Drive sharing, authenticate application-default credentials with Drive permission-management scope:

```sh
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive
```

`make provision-auth` enables the required Google Cloud APIs, creates or reuses the deploy service account, configures Workload Identity Federation for this repository, grants token creation permissions needed by GitHub Actions and local `act`, uploads GitHub repository variables, and writes `dev/act/vars.env`. No Google service account key is generated.

The GitHub Actions build mints a short-lived OAuth access token with only `https://www.googleapis.com/auth/drive.readonly` and passes it directly to `rclone`.

Google Drive permissions are managed through the Drive API, not a `gcloud drive` command group. Use `make provision-drive-access` after `dev/act/vars.env` exists, or set `DRIVE_TARGET_ID` to a Shared Drive ID, folder ID, or file ID. For Shared Drives, the authenticated user must be an organizer. Set `DRIVE_USE_DOMAIN_ADMIN_ACCESS=true` only when making Workspace administrator changes across the domain.

Prefer Shared Drive membership when possible. If the vault must stay in a user's My Drive, configure Google Workspace domain-wide delegation for the service account, authorize only the Drive scopes needed, and set `GOOGLE_WORKSPACE_USER`.

GitHub repository variables written by the tooling:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `GOOGLE_DRIVE_SHARED_DRIVE_ID`
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`
- `GOOGLE_DRIVE_PATH`
- `GOOGLE_WORKSPACE_USER`

Discord failure notifications use the `DISCORD_WEBHOOK_URL` repository secret. Write the local file with `make provision-discord-webhook-file`, then upload it with `make provision-github-secrets`. GitHub secrets are write-only through `gh`, so the tooling uploads the value but cannot read it back later.

Generate local `act` inputs with:

```sh
make provision-act-vars
make provision-act-drive-token
make provision-act-files
```

This writes `dev/act/vars.env`, `dev/act/secrets.env`, and `dev/act/google-drive-access-token`. These files are intentionally ignored by git. The secrets file includes a short-lived `GITHUB_TOKEN` from `gh auth token`, and includes `DISCORD_WEBHOOK_URL` and `GOOGLE_DRIVE_ACCESS_TOKEN` when their local files exist.

`make provision-act-vars` discovers the current `gcloud` project, lists accessible projects when needed, prompts for missing values, ignores stale dummy values, and can list visible Shared Drives after `gcloud auth login --enable-gdrive-access`.
