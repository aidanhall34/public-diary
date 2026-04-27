# Public Diary Publishing

![Test coverage](docs/images/coverage.svg)

[![Build status](https://github.com/aidanhall34/public-diary/actions/workflows/deploy-pages.yml/badge.svg)](https://github.com/aidanhall34/public-diary/actions/workflows/deploy-pages.yml)

This repository turns an Obsidian vault into a static Quartz site and deploys it to GitHub Pages.

The source notes are stored outside the repository in Google Drive. The deployment workflow authenticates to Google
Drive through GitHub OIDC and Google Workload Identity Federation, syncs the vault into the build workspace, stages the
markdown into Quartz, and publishes the generated HTML site.

The repository also stores operational documentation in `docs/`, mirrors that documentation to the GitHub wiki, and
provides local workflow validation through `act`.

Start with `docs/setup.md` for first-time provisioning. See `docs/commands.md` for the main components and make targets.

## Expected layout

- `quartz/`: Quartz project checkout
- `vault/`: synced Obsidian vault content used for builds
- `quartz/content/`: staged markdown copied from `vault/`

## Notes

- The preferred Google Drive layout is a Google Workspace Shared Drive plus a service account member. This avoids
  long-lived user refresh tokens.
- Quartz site settings are managed in `config/quartz-site.json`, and `./dev/scripts/configure-quartz.mjs` generates
  `quartz/quartz.config.ts` from that JSON.
- Quartz layout settings, including comments, are managed in `config/quartz-layout.json`, and
  `./dev/scripts/configure-quartz.mjs` generates `quartz/quartz.layout.ts` from that JSON.
- Quartz is configured to keep Obsidian markdown support enabled and to prefer frontmatter/filesystem dates over git
  dates.
- The nightly deployment workflow is scheduled for `0 14 * * *`, which GitHub Actions interprets as 00:00 AEST daily.
- The GitHub wiki must be initialized once in the repository UI before the wiki sync workflow can push content.
