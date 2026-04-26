# Deploying

The site is built with Quartz and deployed to GitHub Pages from GitHub Actions.

## Triggers

- push to `main`
- manual `workflow_dispatch`
- nightly schedule at `0 0 * * *` which is 00:00 UTC daily

## Build flow

1. Check out the repository.
2. Configure GitHub Pages.
3. Install Node.js.
4. Authenticate to Google Cloud with GitHub OIDC and Workload Identity Federation.
5. Install `rclone`.
6. Build a temporary `rclone` config that uses runtime credentials.
7. Run `make build`.
10. Upload `quartz/public` as the Pages artifact.
11. Deploy the artifact to GitHub Pages.

## Local preview

Use:

```sh
make serve
```

This pulls the latest notes, stages the current vault into Quartz, and runs `npx quartz build --serve` for a local preview.

## Quartz configuration

Do not hand-edit `quartz/quartz.config.ts` or `quartz/quartz.layout.ts`.

This repository treats `config/quartz-site.json` and `config/quartz-layout.json` as the source of truth and uses `scripts/configure-quartz.mjs` to generate `quartz/quartz.config.ts` and `quartz/quartz.layout.ts` from those JSON files during build and serve flows.

## Comments

Comments are enabled through Quartz's built-in Giscus component, configured in `config/quartz-layout.json`.

Quartz handles the script injection itself. You should not add the raw `giscus.app/client.js` script manually.

The current Quartz comments docs recommend using the `Announcements` discussion category for Giscus. This repository is configured with your provided `Q&A` category. If comment threads do not appear correctly, that category choice is the first thing to revisit.

## Prerequisites

- `make setup`, `make build`, or `make serve` can bootstrap Quartz automatically
- GitHub Pages enabled for Actions deployments
- Google Workload Identity Federation configured
- Google Drive variables configured
- the workflow service account can read the target Shared Drive or delegated My Drive location

## Google Drive access model

The workflow is designed around short-lived runtime auth.

Preferred:

- store the Obsidian vault in a Google Workspace Shared Drive
- add the workflow service account as a member of that Shared Drive
- clone the drive content into `vault/` during the build job through `make build`

Fallback:

- keep the vault in a user's My Drive
- configure domain-wide delegation
- impersonate that Workspace user during sync

## GitHub configuration

Set these repository variables:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`
- `GCP_SERVICE_ACCOUNT`
- `GOOGLE_DRIVE_SHARED_DRIVE_ID`
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`
- `GOOGLE_DRIVE_PATH`
- `GOOGLE_WORKSPACE_USER`

No long-lived Google credential secret is required for the preferred setup.

## Runtime cleanup

The workflow uses `google-github-actions/auth` with `cleanup_credentials: true`.

That means generated credential files are removed automatically when the job ends.

## Read-only sync rule

This repository must never write back to Google Drive.

The workflow enforces that by cloning notes during:

```sh
make build
```

The underlying clone step runs:

```sh
rclone copy "vault:${GOOGLE_DRIVE_PATH}" vault/ --drive-skip-gdocs --create-empty-src-dirs --log-level INFO --exclude ".obsidian/**"
```

Because the Google Drive remote is the source and the local workspace is the destination, the command reads from Drive and writes only to local disk.

Unlike your personal sync script, this repository does not use `rclone bisync`.

## Date handling and Obsidian markdown

Quartz already supports Obsidian-flavored markdown through `Plugin.ObsidianFlavoredMarkdown()`, and this repository keeps that plugin enabled.

Quartz also ships with git-based date lookup by default. Because your timestamps are managed by Google Drive and sync clients rather than git history, this repository rewrites `Plugin.CreatedModifiedDate()` to prefer:

```ts
["frontmatter", "filesystem"]
```

That avoids git warnings for untracked notes and makes rendered dates come from note metadata or local file timestamps instead.

## Schedule note

The nightly trigger is currently:

```yaml
schedule:
  - cron: "0 0 * * *"
```

GitHub Actions interprets cron schedules in UTC, so this runs daily at 00:00 UTC, not local midnight in Australia/Sydney.

## Wiki publishing

Documentation in `docs/` is published separately to the GitHub wiki by `sync-wiki.yml`.

Initialize the wiki once in GitHub before using that workflow, otherwise the wiki Git backend does not exist yet.
