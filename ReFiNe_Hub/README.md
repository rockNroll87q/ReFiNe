# ReFiNe

A minimal starter pipeline for building a searchable catalogue of **dataset features needed** to attempt replications of depression-related voxel-wise morphometry papers.

The immediate goal is simple:

> Does your group have the broad data type needed to attempt a replication of this paper?

This starter keeps the system deliberately lightweight:
- no database server
- no containers yet
- no manual-review stage for now
- one command builds the website database

## Full Pipeline: From Eligible Studies to Extracted Features

This is a **two-stage workflow**: first download PDFs for your eligible studies, then run feature extraction on each paper.

### Stage 1: Download PDFs

```bash
# Set your API keys (get OpenAlex key free at https://openalex.org/)
export OPENALEX_API_KEY="your-api-key-here"
# Optional: Semantic Scholar API key (free, but not required)
export SEMANTIC_SCHOLAR_API_KEY="your-api-key-here"

# Download all PDFs (tries OpenAlex first, then Semantic Scholar as fallback)
python scripts/download_pdfs.py \
  --input data/input/eligible_studies.csv \
  --out-dir data/pdfs \
  --manifest data/input/pdf_download_manifest.csv
```

**Optional flags:**
- `--limit N` — Process only the first N papers
- `--overwrite` — Re-download existing PDFs
- `--dry-run` — Preview what would be downloaded without downloading anything
- `--manual-only` — Skip downloads; queue all papers for manual PDF acquisition

**Output files:**
- `data/pdfs/REFINE-XXXX.pdf` — Downloaded PDFs (one per paper)
- `data/input/pdf_download_manifest.csv` — Full manifest with status, source, URLs for each paper
- `data/input/manual_pdf_needed.csv` — Papers where no legal open-access PDF was found

**Sources used (in priority order):**
1. **OpenAlex** — DOI lookup first, then title search fallback
2. **Semantic Scholar** — Only if OpenAlex fails; DOI lookup first, then title search fallback

> Note: `scripts/download_openalex_pdfs.py` is deprecated. Use `download_pdfs.py` instead.

### Stage 2: Run Feature Extraction

Once PDFs are in place, run the extraction pipeline:

```bash
# Extract features for all downloaded papers
python -m refine.run extract-all
```

**Optional flags:**
- `--limit N` - Process only the first N papers
- `--paper-id ID` - Extract a single paper


---

### Notes

- The script uses DOI lookup first, falling back to title search if DOI is missing.
- Only downloads **open-access** PDFs (free via OpenAlex). Subscription-only papers will be skipped with `no_pdf` status.
- A download manifest is written to `data/input/openalex_pdf_downloads.csv`.
- Use `--overwrite` to re-download existing PDFs.
- Papers are named using the `REFINE-XXXX` ID scheme expected by the extraction pipeline.


## What is included

- `data/input/eligible_studies.csv`  
  Converted from the uploaded spreadsheet. It contains **363 paper records**.

- `site/data/papers.json`  
  The database used by the website.

- `site/`  
  A static website with broad filters.

- `refine/`  
  A small Python package with the build command.

## Quick start

Create an environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Build the ReFiNe website database:

```bash
python -m refine.run build \
  --input data/input/eligible_studies.csv \
  --output site/data/papers.json
```

Run the website locally:

```bash
python -m http.server 8000 --directory site
```

Then open:

```text
http://localhost:8000
```

## Current output

The current `build` command creates a valid paper-level database where the broad dataset features are set to:

```text
unclear
```

This is intentional. The next step is to add an extraction command that reads local PDFs/text and populates the feature fields.

## Optional heuristic mode

If you place extracted text files in `data/text/` using the same paper IDs, for example:

```text
data/text/REFINE-0003.txt
```

you can run:

```bash
python -m refine.run build \
  --input data/input/eligible_studies.csv \
  --output site/data/papers.json \
  --text-dir data/text \
  --mode heuristic
```

This performs simple keyword extraction only. It is just a scaffold before the LLM/agent extraction.

## Volunteer replication demo (static)

The website includes a **static demo** of the "Volunteer to replicate this paper" feature. This is a showcase/demo that runs entirely in the browser with no backend, database, or credentials required.

### How it works

1. **Paper cards show status badges**:
   - 🟢 **Available** — No volunteer has claimed this paper yet
   - 🔵 **Selected** — A volunteer has submitted a demo selection (shown from `site/data/claims.json` or browser localStorage)
   - 🟡 **Volunteer pending** — A volunteer has submitted but is awaiting confirmation (shown from `site/data/claims.json`)

2. **Volunteer button**: Each available paper card has a "Volunteer to replicate this paper" button. Clicking it opens a modal form with fields for:
   - Name
   - Institution / research group
   - Contact preference
   - Dataset description (free text)
   - Type of replication (direct / partial / exploratory)
   - Notes

3. **Demo disclaimer**: The modal clearly states: "Demo only. This information is stored only in your browser and is not submitted anywhere."

4. **Saving selections**: Clicking "Save demo selection" updates the card immediately:
   - Status changes to "Selected"
   - Volunteer name and institution appear on the card
   - Additional details are shown in a collapsible details view

5. **Persistence**: All demo selections are stored in the browser's **localStorage** under the key `refine_demo_claims`. Refreshing the page preserves your selections on the same browser.

6. **Combining sources**: The website merges claims from two sources:
   - Static `site/data/claims.json` — pre-populated example selections
   - Browser localStorage — user-created demo selections

### Where demo selections are stored

Demo selections are stored in your browser's localStorage under the key `refine_demo_claims`. This is a JSON object mapping paper IDs to claim data:

```json
{
  "REFINE-0001": {
    "paper_id": "REFINE-0001",
    "status": "selected",
    "volunteer_name": "Your Name",
    "institution": "Your Institution",
    "contact_preference": "Contact directly via email",
    "dataset_description": "My dataset description",
    "replication_type": "partial",
    "notes": "Additional notes"
  }
}
```

### How to clear demo selections

Click the **"Clear demo selections"** button at the top of the page. This will:
- Remove all user-created demo selections from localStorage
- Restore the original static claims from `site/data/claims.json`

Alternatively, you can clear it manually in your browser's developer tools:
```javascript
localStorage.removeItem('refine_demo_claims');
location.reload();
```

### How to export selections as JSON

Click the **"Export selections as JSON"** button. This will:
- Download a file named `refine_demo_selections.json` containing all current claims (static + demo)
- Also display the JSON output on the page for inspection

The exported format matches this structure:

```json
{
  "claims": [
    {
      "paper_id": "REFINE-0001",
      "status": "selected",
      "volunteer_name": "Example Name",
      "institution": "Example Institution",
      "contact_preference": "Contact via project coordinator",
      "dataset_description": "Example in-house MDD T1w MRI dataset",
      "replication_type": "partial",
      "notes": "Example only"
    }
  ]
}
```

### Future integration options

In future versions, the localStorage-based demo could be replaced with a real backend:

1. **GitHub Issues API**: Each volunteer submission creates a new Issue on the ReFiNe repository, with labels for paper_id, status, and replication_type. Volunteers authenticate via GitHub OAuth.

2. **Google Sheets API**: Submissions are appended as new rows in a Google Sheet. The sheet acts as a simple database. The website reads from the sheet via the Google Sheets API.

3. **Full backend**: A lightweight API server (e.g., FastAPI, Flask) with a real database (SQLite, PostgreSQL). Volunteers could create accounts, manage their claims, and receive status updates.

4. **Static site + Netlify Forms**: For a purely static deployment, Netlify Forms or similar services could collect submissions without a backend server.

The current static demo is designed to be a drop-in visual replacement — the frontend code structure makes it straightforward to swap `localStorage` calls for real API calls later.


## Volunteer replication registrations (GitHub Issues)

Groups can register interest in replicating a ReFiNe paper by opening a **public GitHub issue** titled `Replication interest: REFINE-XXXX`. Each issue represents one volunteering group. Multiple groups may register for the same paper.

### How it works

1. Click **"Register interest"** on any paper card → opens a new GitHub issue pre-filled with the paper ID and title.
2. Fill in your group name, institution, and other details in the issue body.
3. Submit the issue. The synchronisation script (or GitHub Action) picks it up automatically.
4. The website reads `site/data/claims.json` and displays the count of registered groups per paper.

### Registration statuses

Labels on the issue determine its status:

| Label | Status | Counted? |
|-------|--------|----------|
| `registration-pending` | pending | Yes |
| `registration-confirmed` | confirmed | Yes |
| `replication-in-progress` | in_progress | Yes |
| `replication-completed` | completed | Yes |
| `registration-withdrawn` | withdrawn | No |

If no recognised label exists, an open issue defaults to `pending`. A closed issue remains registered unless explicitly labelled `registration-withdrawn`.

### Synchronisation

A GitHub Action at `.github/workflows/sync-replication-registrations.yml` runs automatically on issue events and writes the generated data to `site/data/claims.json`. It can also be run manually via `workflow_dispatch`.

For full details, see [docs/replication-registrations.md](docs/replication-registrations.md).

### What NOT to edit by hand

**`site/data/claims.json`** is generated automatically. Do not edit it manually — changes will be overwritten on the next sync run. To fix data, either edit the corresponding GitHub issue or run `python scripts/sync_replication_registrations.py --dry-run` locally first.

---

## Optional: recover missing PDFs through Zotero

This is an **optional second-pass retrieval method** for papers not found by the normal downloader. Use it when you have a local Zotero library that contains (or can be populated with) the missing PDFs.

### On the computer where Zotero is installed

1. Add any missing papers to a dedicated Zotero collection using their DOIs.
2. Use Zotero's **Find Available PDF** command (puzzle-piece icon → "Find Full Text") to let Zotero retrieve open-access copies automatically.
3. Close Zotero if necessary (to ensure the database is fully flushed).
4. Run a dry-run first, then the real import:

```bash
python3 scripts/import_zotero_pdfs.py --dry-run
python3 scripts/import_zotero_pdfs.py
```

The script reads your local Zotero library and copies matched PDFs into `data/pdfs/REFINE-XXXX.pdf`.

### When the repository is remote

The Zotero import **must** run on the local machine where the Zotero library exists. You have two options:

1. Run it against a locally cloned ReFiNe repository, then synchronise the `data/pdfs/` files to your compute machine afterwards.
2. Run it against a remote repository mounted locally through SSHFS (use `--target-dir` and `--input-dir` to point at the mount):

```bash
python3 scripts/import_zotero_pdfs.py \
  --target-dir /path/to/mounted/ReFiNe_Hub/data/pdfs \
  --input-dir /path/to/mounted/ReFiNe_Hub/data/input
```

After importing, run the normal extraction pipeline on your compute machine:

```bash
python -m refine.run extract-all
```

### Important notes

- PDFs are renamed to `REFINE-XXXX.pdf` so they integrate with the existing extraction pipeline.
- Existing PDFs are **protected** — they will not be overwritten unless you supply `--overwrite`.
- A status of `not_found_in_zotero` means no DOI-linked PDF attachment was found for that paper in Zotero; it does **not** prove that no copy exists anywhere in your library.
- Zotero's "Find Available PDF" may only retrieve a subset of the missing papers (depending on open-access availability and institutional access).
- Users must respect publisher licences and institutional-access conditions. Article PDFs should not be committed to a public repository unless redistribution is permitted.

---

## Recommended next step

Add this next command later:

```bash
python -m refine.run extract-pdfs --pdf-dir data/pdfs --out data/text
```

Then add an LLM/agent extraction step:

```bash
python -m refine.run extract-features --text-dir data/text --out site/data/papers.json
```

The website does not need to change. It only reads `site/data/papers.json`.

