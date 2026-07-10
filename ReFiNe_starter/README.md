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

