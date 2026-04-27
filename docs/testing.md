# Testing

Workflow validation for this repository is handled locally with [`act`](https://github.com/nektos/act).

## Purpose

- validate workflow syntax before push
- catch missing job inputs, workflow names, and basic step wiring
- keep pre-commit checks focused on workflow execution paths instead of custom shell parsing

## Requirements

- Docker available locally
- `act` installed and on `PATH`
- repository dependencies installed through `make setup`, `make build`, or `make serve`

## Commands

- `make pre-commit`
- `make lint`
- `make ruff`
- `make yamllint`
- `make checkmake`
- `make markdownlint`
- `make pytests`
- `make test`

The test target writes local `act` input files and runs two dry runs:

- Python unit tests through pytest with at least 95% coverage
- Makefile linting through checkmake
- `deploy-pages.yml` build job with local Drive variables and GitHub App credentials from local `act` secrets
- `sync-wiki.yml` publish job

`make ruff` lints Python tooling and colocated tests under `dev/scripts/public_diary_tools`.

`make lint` runs Ruff, yamllint, and checkmake.

`make markdownlint` runs from the repository root and excludes generated or external directories through
`.markdownlintignore`.

To include GitHub Pages enablement and Discord notification secrets in local `act` runs:

```sh
make python-tool ARGS="write-discord-webhook"

make test
```

`make test` reads GitHub App credentials from `dev/act/github-app.env`, reads `dev/act/discord-webhook-url` when
present, and writes the generated `dev/act/secrets.env` file. The local secret files are ignored by git.

## Notes

- `act` dry runs do not validate live Google Drive authentication or GitHub Pages deployment permissions.
- `make act-run-publish` runs the build job locally with `act`. It uses a locally minted Drive read-only token from
  `dev/act/google-drive-access-token` because GitHub OIDC is only available inside GitHub Actions.

## End-to-end local build

First ensure the local variable file exists:

```sh
make python-tool ARGS="write-act-vars"
```

Replace any dummy values when prompted. `GCP_SERVICE_ACCOUNT` must be a real service account email, for example
`public-diary-deploy@my-project.iam.gserviceaccount.com`.

Then write the local token and `act` files:

```sh
gcloud auth login

make python-tool ARGS="write-act-drive-token"
make python-tool ARGS="write-act-files"
```

`make python-tool ARGS="write-act-drive-token"` uses the active `gcloud` account, grants that user
`roles/iam.serviceAccountTokenCreator` on the service account when needed, then writes a Drive read-only token for
`act`.

Run the deploy workflow build job locally:

```sh
make act-run-publish
```

This tests checkout, Pages setup, Node setup, rclone configuration, Drive read, `make build`, and Pages artifact upload.
It does not perform the real GitHub Pages deployment, because that depends on GitHub-hosted deployment infrastructure.
