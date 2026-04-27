# Setup

This guide provisions this repository for a general Obsidian vault stored in Google Drive. It assumes the notes already
exist in Google Drive, and that no Google Cloud, GitHub Actions, or local `act` support resources have been created yet.

For command reference, run:

```sh
make python-help
make python-help TOOL=provision-auth
```

## Prerequisites

Install and authenticate these tools before starting:

- Google Cloud CLI: see [gcloud CLI authentication](https://cloud.google.com/docs/authentication/gcloud)
- GitHub CLI: see [`gh auth login`](https://cli.github.com/manual/gh_auth_login)
- Docker and `act`: see the [`act` project documentation](https://github.com/nektos/act)
- `uv`: used by the Make recipes to run the Python tooling
- `rclone`: the GitHub Actions workflow installs it automatically, but direct local `make build` usage needs a local
  rclone remote; see the [rclone Google Drive backend documentation](https://rclone.org/drive/)

This project uses `rclone` to copy from Google Drive and `rsync` only to stage already-synced vault files into Quartz.

## Local Tooling

Bootstrap the repository:

```sh
make setup
```

Authenticate to GitHub. The token must be able to manage repository Actions variables/secrets, enable Pages, and run
workflows:

```sh
gh auth login --scopes repo,workflow
gh auth status
```

Authenticate to Google Cloud and Google Drive:

```sh
gcloud auth login --enable-gdrive-access
gcloud auth application-default login \
  --scopes=https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/drive
```

`gcloud auth login` and Application Default Credentials are separate credentials. For details, see Google's [gcloud
authentication overview](https://cloud.google.com/docs/authentication/gcloud) and [`gcloud auth application-default
login`](https://cloud.google.com/sdk/gcloud/reference/auth/application-default/login).

Use the `provision-all` tool to setup up the Google and Github permissions.

```sh
make python-tool ARGS="provision-all"
```

### Logging

Python tools emit JSON logs. Set `PUBLIC_DIARY_LOG_LEVEL=debug` or pass `--debug` / `--log-level debug` before the
subcommand. Pass `--log-output PATH` to append logs to a file after the tool confirms the file is writable:

```sh
make python-tool ARGS="--log-level debug --log-output out.log provision-all"
```

## Google Cloud Project

The provisioning tool searches for visible Google Cloud project IDs and presents them as a numbered list with a custom
option. Press `Ctrl+C` at any prompt to exit without making changes.

```sh
make python-tool ARGS="write-act-vars"
```

If you choose the custom option and enter a project ID that does not exist, the tool creates the project and sets it as
the active `gcloud` project. If you leave the project ID blank, provisioning fails. If the project is new, attach
billing in the way your organization requires. For project and billing details, use the Google Cloud Console or the
relevant `gcloud billing` commands for your account.

## Workload Identity Federation

The tooling creates the Workload Identity Pool and GitHub OIDC provider when they do not already exist. Defaults are:

- `WIF_POOL_ID=github`
- `WIF_PROVIDER_ID=public-diary`
- `SERVICE_ACCOUNT_ID=public-diary-deploy`

Set those environment variables before provisioning if you want different defaults.

The interactive flow also asks whether to keep those defaults. Answer `n` to enter custom service account, pool, and
provider IDs.

For the repository trust condition, the tool suggests the repository for the current directory. If the current directory
is not a GitHub repository, it prompts for `OWNER/REPO`. If no repository is provided, provisioning fails.

For details about this trust relationship, see Google Cloud's [Workload Identity
Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation) and [deployment pipeline
configuration](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) documentation.

## Discover Drive Values

Create the local `act` variable file. The tool discovers the active Google Cloud project, accessible projects, Shared
Drives, and top-level Drive folders. If discovery cannot find the right values, enter them when prompted.

For `GOOGLE_DRIVE_PATH`, the tool opens a folder browser starting at the selected `GOOGLE_DRIVE_ROOT_FOLDER_ID`. Select
`.` to use the current folder, select a child folder to move into it, select `..` to move back toward the selected root,
or choose the manual path option.

```sh
make python-tool ARGS="write-act-vars"
```

If you already know the Drive IDs, provide them explicitly:

```sh
GOOGLE_DRIVE_SHARED_DRIVE_ID=YOUR_SHARED_DRIVE_ID \
GOOGLE_DRIVE_ROOT_FOLDER_ID=YOUR_FOLDER_ID \
GOOGLE_DRIVE_PATH=PATH/INSIDE/DRIVE \
make python-tool ARGS="write-act-vars"
```

For Drive ID and rclone configuration details, see the [rclone Google Drive backend
documentation](https://rclone.org/drive/).

## Provision Google and GitHub

Run the full setup in one batch:

```sh
make python-tool ARGS="provision-all"
```

That command discovers Drive values, creates or reuses Google Cloud resources, configures Workload Identity Federation,
grants Drive read access, uploads GitHub variables, applies repository and branch protection settings, writes/uploads
the Discord webhook secret, mints the local read-only Drive token, and writes local `act` files. Independent GitHub,
Discord, and Drive permission jobs are scheduled concurrently by the Python tool.

You can also run each part individually. Create the deploy service account, enable required Google APIs, configure
Workload Identity Federation, grant GitHub Actions permission to impersonate the service account, upload repository
variables, and write `dev/act/vars.env`:

```sh
make python-tool ARGS="provision-auth"
```

Grant the deploy service account read access to the Drive target:

```sh
make python-tool ARGS="configure-drive-access"
```

Upload repository variables from `dev/act/vars.env` if you later edit that file:

```sh
make python-tool ARGS="upload-github-vars"
```

Apply repository settings, GitHub Pages settings, and main branch protection from
`.github/config/repository-permissions.json`:

```sh
make python-tool ARGS="apply-github-settings"
```

This config sets the Pages custom domain to `notes.ah34.net`, enforces HTTPS for Pages, and requires the pull request
validation `lint` and `test` checks before merging to `main`.

The preferred Google Drive layout is a Shared Drive with the deploy service account as a reader. If the vault must stay
in a user's My Drive, configure Google Workspace domain-wide delegation separately, set
`GOOGLE_WORKSPACE_DELEGATION_ENABLED=true`, and set `GOOGLE_WORKSPACE_USER`.

## GitHub App Authentication

The batch command creates the GitHub App when no local app credentials exist. To run only that step:

```sh
make python-tool ARGS="provision-github-app"
```

The command prints a GitHub App manifest URL, runs a local callback listener, converts the returned manifest code into
an app private key, prompts you to install the app, adds this repository to the installation when the installation uses
selected repositories, uploads `GITHUB_APP_CLIENT_ID` and `GITHUB_APP_PRIVATE_KEY` to repository secrets, and writes
`dev/act/github-app.env` for local `act` runs.

Set these GitHub App repository permissions:

- Actions: read-only. Lets workflow-created app tokens read Actions metadata.
- Contents: read and write. Required for repository checkout, release metadata, committing synced vault notes, and
  pushing wiki/docs changes.
- Metadata: read-only. Required by GitHub for all GitHub Apps.
- Pages: read and write. Required by `actions/configure-pages` and `actions/deploy-pages`.
- Pull requests: read and write. Required when the deploy workflow opens or finds the automated vault sync PR.

No organization permissions, account permissions, webhook events, or webhook URL are required for this repository. The
tool-generated manifest sets webhooks inactive.

## GitHub Secrets

To run only the remaining secret steps, create the optional local Discord webhook file and upload secrets. The tool
uploads the GitHub App credentials from `dev/act/github-app.env` or matching environment variables, and uploads
`DISCORD_WEBHOOK_URL` when the webhook is configured:

```sh
make python-tool ARGS="write-discord-webhook"
make python-tool ARGS="upload-github-secrets"
```

GitHub secrets are write-only through GitHub APIs, so the tool uploads values but cannot read them back later.

## Local act Files

Mint a short-lived Google Drive read-only token for local `act` runs and write the local `act` secret file:

```sh
gcloud auth login --enable-gdrive-access

make python-tool ARGS="write-act-drive-token"
make python-tool ARGS="write-act-files"
```

This writes ignored local files under `dev/act/`:

- `vars.env`
- `secrets.env`
- `google-drive-access-token`
- `discord-webhook-url`
- `github-app.env`

## Validate Locally

Run linting and tests:

```sh
make lint
make pytests
```

Dry-run the configured `act` jobs:

```sh
make test
```

Run the Pages build job locally with `act`:

```sh
make act-run-publish
```

This validates checkout, rclone configuration, Drive access, Quartz build, and Pages artifact creation. It does not
create a production GitHub Pages deployment.

## Publish

GitHub Pages production deployment must run on GitHub Actions because `actions/deploy-pages` depends on GitHub Pages
deployment infrastructure and OIDC context. From your local terminal, trigger the remote workflow:

```sh
gh workflow run deploy-pages.yml
gh run watch
```

For details, see GitHub's [manual workflow run
documentation](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow), [`gh workflow
run`](https://cli.github.com/manual/gh_workflow_run), and
[`actions/deploy-pages`](https://github.com/actions/deploy-pages).

The wiki workflow can be run from `act` if your local GitHub token can push to the repository wiki:

```sh
act push \
  -W .github/workflows/sync-wiki.yml \
  -j publish-wiki \
  --secret-file dev/act/secrets.env
```

The GitHub wiki must be initialized once in the GitHub UI before the workflow can push documentation. For wiki behavior
and availability, see GitHub's [About
wikis](https://docs.github.com/communities/documenting-your-project-with-wikis/about-wikis).

You can also publish the wiki through GitHub Actions:

```sh
gh workflow run sync-wiki.yml
gh run watch
```

## Common Maintenance

Refresh local `act` inputs after changing Drive, GitHub, or Discord configuration:

```sh
make python-tool ARGS="write-act-vars"
make python-tool ARGS="write-act-drive-token"
make python-tool ARGS="write-act-files"
```

Regenerate command documentation after adding or changing Python tool commands:

```sh
make docs-commands
```
