# Public Diary Publishing

This repository turns an Obsidian vault into a static Quartz site and deploys it to GitHub Pages.

The source notes are stored outside the repository in Google Drive. The deployment workflow authenticates to Google Drive through GitHub OIDC and Google Workload Identity Federation, syncs the vault into the build workspace, stages the markdown into Quartz, and publishes the generated HTML site.

The repository also stores operational documentation in `docs/`, mirrors that documentation to the GitHub wiki, and provides local workflow validation through `act`.

## Main components

- `Makefile`: local setup, staging, build, and validation entry points
- `config/quartz-site.json`: source-of-truth site settings used to generate `quartz/quartz.config.ts`
- `config/quartz-layout.json`: source-of-truth layout settings used to generate `quartz/quartz.layout.ts`
- `dev/makefiles/`: composable makefile fragments for repo setup, Quartz, Drive sync, docs, and `act`
- `.github/workflows/deploy-pages.yml`: scheduled and on-demand Pages deployment
- `.github/workflows/sync-wiki.yml`: publishes `docs/` to the GitHub wiki
- `.githooks/`: tracked git hooks configured automatically by `make build` or `make serve`
- `docs/`: project documentation mirrored to the wiki

## Expected layout

- `quartz/`: Quartz project checkout
- `vault/`: synced Obsidian vault content used for builds
- `quartz/content/`: staged markdown copied from `vault/`

## Common commands

- `make pre-commit`: sync documentation README content and dry-run workflows with `act`
- `make setup`: install root and Quartz dependencies, configure hooks, bootstrap Quartz, and generate `quartz/quartz.config.ts`
- `make build`: pull the latest notes, bootstrap Quartz if needed, and build the static site
- `make serve`: pull the latest notes, bootstrap Quartz if needed, and serve the site locally with Quartz

## Notes

- The preferred Google Drive layout is a Google Workspace Shared Drive plus a service account member. This avoids long-lived user refresh tokens.
- Quartz site settings are managed in `config/quartz-site.json`, and `scripts/configure-quartz.mjs` generates `quartz/quartz.config.ts` from that JSON.
- Quartz layout settings, including comments, are managed in `config/quartz-layout.json`, and `scripts/configure-quartz.mjs` generates `quartz/quartz.layout.ts` from that JSON.
- Quartz is configured to keep Obsidian markdown support enabled and to prefer frontmatter/filesystem dates over git dates.
- The nightly deployment workflow is scheduled for `0 0 * * *`, which GitHub Actions interprets as 00:00 UTC daily.
- The GitHub wiki must be initialized once in the repository UI before the wiki sync workflow can push content.
