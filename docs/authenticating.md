# Authenticating

The deployment pipeline authenticates to Google Drive with short-lived credentials minted at workflow runtime.

## Recommended design

Use:

- GitHub Actions OIDC
- Google Cloud Workload Identity Federation
- a Google Cloud service account
- a Google Workspace Shared Drive that contains the Obsidian vault

This avoids storing a long-lived Google refresh token or service account key in GitHub.

## Runtime flow

1. The workflow starts in GitHub Actions. 2. GitHub presents its OIDC identity token to Google. 3. Google Workload
   Identity Federation exchanges that identity for a short-lived Google credential. 4. `google-github-actions/auth`
   mints a short-lived OAuth access token scoped only to Google Drive read access. 5. `rclone` uses that bearer token
   directly. 6. The job finishes and the token expires.

## Why this is the preferred path

- no long-lived Google refresh token is stored in GitHub
- no service account key JSON is stored in GitHub
- access exists only for the running workflow job
- access can be revoked centrally by removing the Workload Identity binding or the Shared Drive membership
- the runtime token is limited to `https://www.googleapis.com/auth/drive.readonly`

## Repository variables

Set these GitHub repository variables:

- `GCP_WORKLOAD_IDENTITY_PROVIDER`: full provider resource name, for example
  `projects/123456789/locations/global/workloadIdentityPools/github/providers/public-diary`
- `GCP_SERVICE_ACCOUNT`: service account email used by the workflow
- `GOOGLE_DRIVE_SHARED_DRIVE_ID`: Shared Drive ID containing the vault
- `GOOGLE_DRIVE_ROOT_FOLDER_ID`: optional folder ID inside the drive to use as the vault root
- `GOOGLE_DRIVE_PATH`: optional path inside the configured remote root, for example `obs-notes/obs-notes`
- `GOOGLE_WORKSPACE_USER`: optional Workspace user email for domain-wide delegation impersonation when reading from a
  user's My Drive instead of a Shared Drive

## Google-side requirements

- a Google Cloud project with the Drive API enabled
- a Google Cloud service account used by the workflow
- a Workload Identity Pool and Provider that trust `https://token.actions.githubusercontent.com`
- an IAM binding that allows the GitHub repo to impersonate the service account
- an IAM binding that allows the service account to mint scoped access tokens for itself

## Preferred storage model

Put the vault in a Shared Drive and add the service account as a member of that Shared Drive.

This is the cleanest option because service accounts cannot own Drive content and Shared Drives are designed for
non-human access patterns.

For this model:

- set `GOOGLE_DRIVE_SHARED_DRIVE_ID`
- optionally set `GOOGLE_DRIVE_ROOT_FOLDER_ID`
- leave `GOOGLE_WORKSPACE_USER` blank unless you explicitly need impersonation

Grant the service account the minimum access needed, ideally read-only access if the workflow only syncs content out.

## If the vault is in a user's My Drive

If you must read from a user's My Drive, use domain-wide delegation and `impersonate` the Workspace user instead of
storing a user refresh token.

That path is more sensitive because it grants the service account delegated access to user data.

For this model:

- configure Google Workspace domain-wide delegation for the service account
- authorize only the scopes you need
- set `GOOGLE_WORKSPACE_USER` to the delegated Workspace user
- keep the Drive scope at `drive.readonly` unless writes are required

Use this only if the vault cannot be moved into a Shared Drive.

## Workflow behavior

The workflow uses `google-github-actions/auth@v3` with:

- `workload_identity_provider`
- `service_account`
- `token_format: access_token`
- `access_token_scopes: https://www.googleapis.com/auth/drive.readonly`
- `access_token_lifetime: 3600s`
- `create_credentials_file: false`

It then writes a minimal `rclone` config with that access token and runs:

```sh
rclone copy "vault:${GOOGLE_DRIVE_PATH}" vault/ --drive-skip-gdocs --create-empty-src-dirs --log-level INFO --exclude ".obsidian/**"
```

This is intentionally modeled as a one-way clone of your reference script, but it uses `copy` instead of `bisync`.

This command reads from the `vault:` Google Drive remote and writes only to the local `vault/` directory in the runner
workspace.

The repository should not use `rclone bisync`, `rclone copy`, or `rclone sync` with local paths as the source and Google
Drive as the destination.

## Notes

- Prefer Shared Drive membership over domain-wide delegation if you control the Drive layout.
- Do not store a Google service account key JSON in GitHub unless you have no alternative.
- If a future build exceeds the one-hour token lifetime, split the workflow or redesign the sync so it completes within
  the token lifetime.
- Discord notifications use only the `DISCORD_WEBHOOK_URL` GitHub secret and run after workflow job failure or
  cancellation.
