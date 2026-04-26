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

That target currently does two dry runs:

- `deploy-pages.yml` build job with placeholder Drive secrets and variables
- `sync-wiki.yml` publish job

## Notes

- `act` dry runs do not validate live Google Drive authentication or GitHub Pages deployment permissions.
- If you want a fuller local run later, add a dedicated `act` secrets file and switch specific jobs from dry-run to execution.
