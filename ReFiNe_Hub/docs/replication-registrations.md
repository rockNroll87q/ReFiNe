# Replication Registration Synchronisation

This document describes how GitHub Issues are used as the **source of truth** for groups volunteering to replicate a ReFiNe paper.

## Overview

- **GitHub Issues are the source of truth.** Each issue titled `Replication interest: REFINE-XXXX` represents one group's registration to attempt a replication of that paper.
- **One issue = one volunteering group.** Multiple groups may register for the same paper by creating separate issues.
- **Multiple registrations per paper are expected and encouraged.** The website counts all active registrations and displays `N groups registered`.
- **The generated file is `site/data/claims.json`.** This file is produced automatically by a GitHub Action and should not normally be edited by hand.

## Issue title format

An issue is recognised as a replication registration when its title matches (case-insensitive, tolerant of extra whitespace):

```
Replication interest: REFINE-0001
```

The regex used is: `^replication\s+interest:\s*(refine-\d{4})\s*$`

## Issue body format

The registration issue template uses a structured form with Markdown headings and table rows. The synchronisation script parses fields by their **heading sections**, not by fixed line numbers, so reordering fields within a section is safe.

### Key sections in the issue body

| Section heading (case-insensitive) | Purpose |
|-------------------------------------|---------|
| `## Replication Interest Registration` | Paper metadata (paper ID, title, DOI) |
| `## Contributor / Group Information` | Volunteer name and institution (table format: `\*\*label\*\* \| value`) |
| `## Dataset Availability` | Checkbox list of dataset access options |
| `## Replication Plan` | Checkbox list of replication type options |
| `## Additional Information` | Free-text notes, public listing consent |

### Extracted fields

The script extracts the following from the **Contributor / Group Information** section:

| JSON field | Source in issue body | Default if missing |
|------------|---------------------|--------------------|
| `volunteer_name` | Table row `\*\*Name / group\*\* \| value` or bullet `- \*\*Name / group:\*\* value` | `""` (empty string) |
| `institution` | Table row `\*\*Institution\*\* \| value` or bullet `- \*\*Institution:\*\* value` | `""` (empty string) |

Other fields (`github_issue`, `issue_url`, `github_user`, `created_at`, `updated_at`) are taken directly from the GitHub API issue object.

## Registration statuses and labels

Labels on the issue determine its logical status. The following label-to-status mapping is used:

| GitHub label | Logical status |
|-------------|----------------|
| `registration-withdrawn` | `withdrawn` |
| `replication-completed` | `completed` |
| `replication-in-progress` | `in_progress` |
| `registration-confirmed` | `confirmed` |
| `registration-pending` | `pending` |

### Precedence when multiple status labels are present

1. `registration-withdrawn` (highest priority)
2. `replication-completed`
3. `replication-in-progress`
4. `registration-confirmed`
5. `registration-pending` (lowest priority)

### Default status when no recognised label exists

| Issue state | Default status |
|-------------|---------------|
| Open issue | `pending` |
| Closed issue | `pending` (closed does **not** mean withdrawn; use `registration-withdrawn` to withdraw) |

## Generated claims.json schema

Each matching issue produces one entry in `site/data/claims.json`:

```json
{
  "paper_id": "REFINE-0001",
  "status": "pending",
  "volunteer_name": "Brain Imaging Lab",
  "institution": "University of Example",
  "github_issue": 42,
  "issue_url": "https://github.com/OWNER/REPOSITORY/issues/42",
  "github_user": "username",
  "created_at": "2026-07-14T10:00:00Z",
  "updated_at": "2026-07-14T10:00:00Z"
}
```

### Field descriptions

| Field | Type | Description |
|-------|------|-------------|
| `paper_id` | string | Extracted paper ID (e.g. `REFINE-0001`) |
| `status` | string | One of: `pending`, `confirmed`, `in_progress`, `completed`, `withdrawn` |
| `volunteer_name` | string | Name or group name of the volunteering team |
| `institution` | string | Institution or organisation |
| `github_issue` | integer | GitHub issue number |
| `issue_url` | string | Direct URL to the issue on GitHub |
| `github_user` | string | Login of the user who created the issue |
| `created_at` | string | ISO 8601 timestamp of issue creation |
| `updated_at` | string | ISO 8601 timestamp of last update |

### Ordering and formatting

- Records are sorted by `paper_id`, then by `github_issue`.
- JSON is formatted with 2-space indentation, keys sorted alphabetically.
- A trailing newline is appended.

## Website display logic

The website loads `site/data/claims.json` (a JSON array) and counts active registrations per paper:

| Active count | Display text |
|-------------|-------------|
| 0 | `Available — no groups registered` |
| 1 | `1 group registered` |
| N > 1 | `N groups registered` |

### Active statuses counted

- `pending`, `confirmed`, `in_progress`, `completed`

### Excluded from count

- `withdrawn` status
- Malformed entries (no valid `paper_id`)
- Entries without a valid `REFINE-\d{4}` paper ID

The "Register interest" button remains visible and enabled regardless of how many groups have registered.

## GitHub Action workflow

**File:** `.github/workflows/sync-replication-registrations.yml`

### Triggers

| Event | Description |
|-------|-------------|
| `issues.opened` | New registration issue created |
| `issues.edited` | Issue title or body changed |
| `issues.labeled` | Status label added |
| `issues.unlabeled` | Status label removed |
| `issues.reopened` | Closed issue reopened |
| `issues.closed` | Open issue closed |
| `workflow_dispatch` | Manual trigger |

### How it works

1. Checks out the repository.
2. Sets up Python 3.12.
3. Runs `scripts/sync_replication_registrations.py` (fetches all issues, generates claims.json).
4. Commits and pushes only if the file changed.
5. Uses `[skip ci]` in the commit message to avoid triggering another workflow run.

### Permissions

| Permission | Reason |
|-----------|--------|
| `contents: write` | To commit the updated claims.json |
| `issues: read` | To fetch all issues via the API |

## Running synchronisation locally

### Prerequisites

- Python 3.10+
- A GitHub token (optional, for rate-limited repos): `export GITHUB_TOKEN=ghp_xxx`

### Run normally

```bash
cd ReFiNe_Hub
python scripts/sync_replication_registrations.py
```

This writes to `site/data/claims.json`.

### Dry run (print without writing)

```bash
python scripts/sync_replication_registrations.py --dry-run
```

### Check for changes only (exit code 0 = no changes, 1 = changes written)

```bash
python scripts/sync_replication_registrations.py --check-changes
```

### Custom repo and output path

```bash
python scripts/sync_replication_registrations.py \
  --repo owner/repo \
  --output /path/to/claims.json
```

## Running the workflow manually

1. Go to the repository's **Actions** tab.
2. Click **Sync Replication Registrations**.
3. Click **Run workflow** and optionally select a branch.

Or via the GitHub CLI:

```bash
gh workflow run sync-replication-registrations.yml -R owner/repo
```

## Testing

### Run unit tests

```bash
cd ReFiNe_Hub
python scripts/test_sync_replication_registrations.py
```

### Test scenarios covered

| # | Scenario | Expected result |
|---|----------|-----------------|
| 1 | No matching issues | Empty claims array `[]` |
| 2 | One group registered for a paper | Single entry with correct paper_id and status |
| 3 | Two different issues for the same paper | Two entries, both counted as active |
| 4 | One active + one withdrawn for same paper | Only the active one counted (count = 1) |
| 5 | Closed but confirmed registration | Included in active count |
| 6 | Malformed title (no REFINE-XXXX) | Issue ignored, no entry generated |
| 7 | Missing laboratory or institution fields | Entry created with empty strings for missing fields |
| 8 | More than one page of API results | All pages fetched and processed correctly |

## Assumptions about issue-form headings

The synchronisation script makes the following assumptions about the GitHub issue form:

1. The **Contributor / Group Information** section contains a heading that includes either `contributor` or `group information` (case-insensitive).
2. Within that section, fields are stored as table rows (`\*\*label\*\* \| value`) or bullet points (`- \*\*label:\*\* value`).
3. Recognised field labels: `Name / group`, `Institution`.
4. The script does **not** depend on fixed line numbers; it finds sections by their Markdown headings.

## What NOT to edit by hand

**`site/data/claims.json`** should not normally be edited manually because the GitHub Action overwrites it on every issue event. If you need to fix data, either:

1. Edit the corresponding GitHub issue and let the sync run, or
2. Run `sync_replication_registrations.py --dry-run` to inspect output before committing.