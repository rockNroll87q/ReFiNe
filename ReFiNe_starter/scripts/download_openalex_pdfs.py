#!/usr/bin/env python3
"""
Download PDFs for papers listed in a CSV using the OpenAlex API.

Workflow:
    1. Set your OpenAlex API key:
       export OPENALEX_API_KEY="your-key"
       (or add it to .env and ensure python-dotenv is installed)
    2. Download PDFs:
       python scripts/download_openalex_pdfs.py \
           --input data/input/eligible_studies.csv --out-dir data/pdfs
    3. Run extraction:
       python -m refine.run extract-all --limit 10

For open-access articles, this script follows the OA URL to the publisher's
PDF endpoint (e.g., Frontiers, MDPI, PLOS). For subscription-only papers
without an available PDF, status will be 'no_pdf'.
"""

import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Optional: load_dotenv so .env files work without explicit dependency
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv()  # loads from .env in the project root or current dir
except ImportError:
    pass  # .env won't be auto-loaded; rely on environment variable directly

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENALEX_API_BASE = "https://api.openalex.org"
DEFAULT_INPUT_CSV = "data/input/eligible_studies.csv"
DEFAULT_OUT_DIR = "data/pdfs"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5.0  # exponential back-off base

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column-name heuristics
# ---------------------------------------------------------------------------
COLUMN_HINTS = {
    "doi": {"doi", "DOI", "Doi", "doi_url", "digital_object_identifier"},
    "title": {"title", "Title", "paper_title", "Paper Title"},
    "paper_id": {"paper_id", "Paper_ID", "id", "ID", "source_id", "Source ID"},
}


def detect_column(headers: list[str], key: str) -> str | None:
    """Return the first header name that matches hints for *key*, or None."""
    hints = COLUMN_HINTS.get(key, set())
    # Exact match first
    for h in headers:
        if h.strip() in hints:
            return h.strip()
    # Case-insensitive match
    key_lower = key.lower()
    for h in headers:
        if h.strip().lower() == key_lower:
            return h.strip()
    return None


# ---------------------------------------------------------------------------
# OpenAlex API helpers
# ---------------------------------------------------------------------------
def _get(url: str, params: dict | None = None) -> dict | None:
    """GET from OpenAlex with retry / exponential back-off."""
    api_key = os.environ.get("OPENALEX_API_KEY", "").strip()
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                delay = RETRY_DELAY_SECONDS * (2 ** attempt)
                log.warning("Rate limited (429). Waiting %.1fs before retry…", delay)
                time.sleep(delay)
                continue
            else:
                log.warning("GET %s returned HTTP %d", url, resp.status_code)
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS * (2 ** attempt))
        except requests.RequestException as exc:
            log.warning("Request error on %s: %s", url, exc)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_SECONDS * (2 ** attempt))
    return None


def fetch_work_by_doi(doi: str) -> dict | None:
    """Look up a work by its DOI."""
    return _get(f"{OPENALEX_API_BASE}/works/doi:{doi}")


def search_works_by_title(title: str, per_page: int = 10) -> list[dict]:
    """Search works by title and return results."""
    params = {"filter": f"title.search:{title}", "per_page": per_page}
    result = _get(f"{OPENALEX_API_BASE}/works", params=params)
    if result and "results" in result:
        return result["results"]
    return []


# ---------------------------------------------------------------------------
# PDF URL resolution helpers
# ---------------------------------------------------------------------------
def get_pdf_url_from_work(work: dict) -> tuple[str | None, str]:
    """Return (direct_pdf_url_or_None, source_label).

    Priority order:
        1. top_level.pdf_url (direct PDF link from OpenAlex)
        2. best_oa_location.oa_url only if it looks like a direct PDF URL
        3. any repository PDF URL from locations array
    """
    # Direct PDF URL (may be string or list)
    pdf_url = work.get("pdf_url")
    if isinstance(pdf_url, str) and pdf_url.strip():
        return pdf_url.strip(), "top_level_pdf_url"
    if isinstance(pdf_url, list) and len(pdf_url) > 0:
        url = pdf_url[0].strip() if pdf_url[0] else ""
        if url:
            return url, "top_level_pdf_url (list)"

    # Best open-access location
    oa_loc = work.get("best_oa_location") or {}
    if oa_loc and oa_loc.get("oa_url"):
        oa_url = oa_loc["oa_url"]
        # Only use OA URL directly if it looks like a PDF endpoint
        if is_pdf_url(oa_url):
            return oa_url, "best_oa_location (PDF)"
        # For non-PDf OA URLs, check for is_oa_collection or landing_page_url
        # that point to known OA publishers with PDF support
        publisher = work.get("publisher", {}) or {}
        if publisher and publisher.get("name", "").lower() in {
            "frontiers", "mdpi", "plos", "springer nature", "elsevier b.v.",
            "public library of science", "society for neuroscience",
        }:
            # These publishers have reliable PDF endpoints; return the OA URL
            # and let download_pdf resolve it via redirect following
            return oa_url, "best_oa_location (publisher)"

    # Check locations array for direct PDF URLs
    for loc in (work.get("locations") or []):
        if isinstance(loc, dict) and loc.get("pdf_url"):
            url = loc["pdf_url"]
            if isinstance(url, str) and url.strip():
                return url.strip(), "location_pdf_url"

    return None, "none"


def is_pdf_url(url: str) -> bool:
    """Heuristic check whether a URL likely points to a PDF file."""
    lower = url.lower().split("?")[0].split("#")[0]
    return any(p in lower for p in [".pdf", "/pdf/", "article/pdf", "pdfarticle"])


def resolve_pdf_from_oa_url(oa_url: str, session: requests.Session) -> str | None:
    """Follow redirects on an OA landing page to find a direct PDF link.

    Many publisher OA URLs redirect to the actual PDF (e.g., Frontiers, MDPI).
    We follow HEAD request and check if the final URL is a PDF.
    Returns the resolved PDF URL or None.
    """
    try:
        resp = session.head(oa_url, timeout=15, allow_redirects=True)
        final_url = resp.url.lower()
        if is_pdf_url(final_url):
            return resp.url
    except Exception:
        pass
    # If the final URL doesn't look like a PDF but is an OA page,
    # we still try downloading from it (some publishers serve PDF via HTML).
    return oa_url


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------
def download_pdf(work: dict, out_path: Path) -> tuple[str, str | None]:
    """Download a PDF for the given work record to *out_path*.

    Returns (status, error_message).
    Status is one of: 'downloaded', 'already_exists', 'no_pdf', 'error'.
    """
    pdf_url, source = get_pdf_url_from_work(work)

    if not pdf_url:
        return ("no_pdf", None)

    log.info("  PDF URL (%s): %s", source, pdf_url)

    session = requests.Session()

    # If the URL is an OA landing page (not a direct PDF), try to resolve it
    final_url = pdf_url
    if not is_pdf_url(pdf_url):
        resolved = resolve_pdf_from_oa_url(pdf_url, session)
        if resolved:
            final_url = resolved

    try:
        log.debug("Downloading from: %s", final_url)
        resp = session.get(final_url, timeout=120, stream=True)

        if resp.status_code == 404 or resp.status_code == 403:
            return ("no_pdf", f"HTTP {resp.status_code} at PDF URL")

        if resp.status_code != 200:
            # Try to follow redirects manually
            resp = session.get(final_url, timeout=120, allow_redirects=True)
            if resp.status_code != 200:
                return ("error", f"HTTP {resp.status_code}")

        content_type = resp.headers.get("Content-Type", "").lower()
        log.debug("  Content-Type: %s", content_type)

        # Download the file
        data = resp.content
        if len(data) < 100:
            return ("error", f"Downloaded too little data ({len(data)} bytes)")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)

        # Verify it looks like a PDF (magic number) - STRICT check
        if data[:4] != b"%PDF":
            log.warning("[%s] File does NOT start with %%PDF header (got %r). Deleting invalid file.", out_path.name, data[:20])
            # Delete the invalid file
            try:
                out_path.unlink()
            except OSError:
                pass
            return ("error", f"Downloaded file is not a valid PDF (Content-Type: {content_type})")

        log.info("  Valid PDF (%d bytes)", len(data))
        return ("downloaded", None)

    except requests.RequestException as exc:
        return ("error", str(exc))
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Column resolution helpers
# ---------------------------------------------------------------------------
def resolve_paper_id(row: dict, id_col: str | None, idx: int) -> str:
    """Return a stable paper ID for this row."""
    if id_col and row.get(id_col):
        pid = str(row[id_col]).strip()
        if pid:
            return pid
    # Generate one from index
    return f"refine_{idx + 1:04d}"


def resolve_doi(row: dict, doi_col: str | None) -> str | None:
    """Extract a cleaned DOI from a CSV row."""
    if not doi_col or not row.get(doi_col):
        return None
    val = str(row[doi_col]).strip()
    # Strip DOI prefix
    for prefix in ("https://doi.org/", "http://dx.doi.org/"):
        if val.startswith(prefix):
            val = val[len(prefix):]
    val = val.upper().replace("DOI:", "").strip()
    return val if val else None


def resolve_title(row: dict, title_col: str | None) -> str | None:
    """Extract a title from a CSV row."""
    if not title_col or not row.get(title_col):
        return None
    val = str(row[title_col]).strip()
    return val if val else None


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Download PDFs for papers in a CSV using OpenAlex."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_CSV, help="Path to input CSV.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Directory to save PDFs.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of papers to process.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing PDFs.")
    parser.add_argument("--dry-run", action="store_true", help="Do not download anything; just report what would happen.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read CSV
    input_path = Path(args.input)
    if not input_path.exists():
        log.error("Input CSV not found: %s", input_path)
        sys.exit(1)

    with open(input_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        doi_col = detect_column(headers, "doi")
        title_col = detect_column(headers, "title")
        id_col = detect_column(headers, "paper_id")

        rows = list(reader)

    # Process
    downloaded = 0
    existed = 0
    not_found = 0
    no_pdf = 0
    errors = 0
    manifest_rows: list[dict] = []

    limit = args.limit if args.limit else len(rows)

    for idx, row in enumerate(rows):
        if idx >= limit:
            break

        paper_id = resolve_paper_id(row, id_col, idx)
        # Sanitize paper_id – replace slashes etc. that could be problematic as filenames
        safe_pid = "".join(c if c.isalnum() or c in "-_" else "_" for c in paper_id)

        doi_val = resolve_doi(row, doi_col)
        title_val = resolve_title(row, title_col)

        pdf_filename = f"{safe_pid}.pdf"
        pdf_path = out_dir / pdf_filename

        # Check existing file
        if pdf_path.exists() and not args.overwrite:
            log.info("[%s] PDF already exists – skipping (use --overwrite to re-download)", paper_id)
            existed += 1
            manifest_rows.append({
                "paper_id": paper_id,
                "title": title_val[:500] if title_val else "",
                "doi": doi_val or "",
                "openalex_id": "",
                "status": "already_exists",
                "pdf_path": str(pdf_path),
                "oa_status": "",
                "license": "",
                "error_message": "",
            })
            continue

        if args.dry_run:
            log.info("[DRY RUN] Would process [%s]: doi=%s title='%s'", paper_id, doi_val or "(none)", (title_val or "")[:80])
            manifest_rows.append({
                "paper_id": paper_id,
                "title": title_val[:500] if title_val else "",
                "doi": doi_val or "",
                "openalex_id": "",
                "status": "dry_run",
                "pdf_path": str(pdf_path),
                "oa_status": "",
                "license": "",
                "error_message": "",
            })
            continue

        # Look up by DOI first
        work = None
        if doi_val:
            log.info("[%s] Looking up by DOI: %s", paper_id, doi_val)
            work = fetch_work_by_doi(doi_val)

        # Fallback to title search
        if not work and title_val:
            log.info("[%s] No DOI lookup success; searching by title: '%s'", paper_id, title_val[:80])
            results = search_works_by_title(title_val, per_page=5)
            if results:
                # Pick the best match – prefer one with a PDF or OA URL
                for r in results:
                    if get_pdf_url_from_work(r):
                        work = r
                        break
                if not work:
                    work = results[0]

        if not work:
            log.warning("[%s] Could not find paper in OpenAlex", paper_id)
            not_found += 1
            manifest_rows.append({
                "paper_id": paper_id,
                "title": title_val[:500] if title_val else "",
                "doi": doi_val or "",
                "openalex_id": "",
                "status": "not_found",
                "pdf_path": str(pdf_path),
                "oa_status": "",
                "license": "",
                "error_message": "Paper not found in OpenAlex",
            })
            continue

        work_id = work.get("id", "")
        oa_status = work.get("oa_status", "")
        oa_loc = work.get("best_oa_location") or {}
        license_val = oa_loc.get("license", "") if oa_loc else ""

        log.info("[%s] Found work: %s (OA: %s)", paper_id, work_id, oa_status)

        pdf_url, source = get_pdf_url_from_work(work)
        if not pdf_url:
            log.info("[%s] No PDF available for this work (OA status: %s)", paper_id, oa_status)
            no_pdf += 1
            manifest_rows.append({
                "paper_id": paper_id,
                "title": title_val[:500] if title_val else "",
                "doi": doi_val or "",
                "openalex_id": work_id,
                "status": "no_pdf",
                "pdf_path": str(pdf_path),
                "oa_status": oa_status,
                "license": license_val,
                "error_message": "No PDF URL found in OpenAlex record",
            })
            continue

        log.info("[%s] Downloading PDF from: %s", paper_id, pdf_url)
        status, error_msg = download_pdf(work, pdf_path)

        if status == "downloaded":
            downloaded += 1
            log.info("[%s] ✓ Downloaded successfully (%d bytes)", paper_id, pdf_path.stat().st_size if pdf_path.exists() else 0)
        elif status == "no_pdf":
            no_pdf += 1
        else:
            errors += 1
            log.error("[%s] ✗ Error downloading PDF: %s", paper_id, error_msg)

        manifest_rows.append({
            "paper_id": paper_id,
            "title": title_val[:500] if title_val else "",
            "doi": doi_val or "",
            "openalex_id": work_id,
            "status": status,
            "pdf_path": str(pdf_path),
            "oa_status": oa_status,
            "license": license_val,
            "error_message": error_msg or "",
        })

    # Write manifest
    manifest_dir = Path(args.input).parent
    manifest_path = manifest_dir / "openalex_pdf_downloads.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    if manifest_rows:
        fieldnames = [
            "paper_id", "title", "doi", "openalex_id", "status",
            "pdf_path", "oa_status", "license", "error_message",
        ]
        with open(manifest_path, "w", newline="", encoding="utf-8") as mf:
            writer = csv.DictWriter(mf, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(manifest_rows)

    # Summary
    print("\n" + "=" * 60)
    print("Download Summary")
    print("=" * 60)
    print(f"  Downloaded:      {downloaded}")
    print(f"  Already existed: {existed}")
    print(f"  Not found:       {not_found}")
    print(f"  No PDF available:{no_pdf}")
    print(f"  Errors:          {errors}")
    if args.dry_run:
        dry_count = sum(1 for r in manifest_rows if r["status"] == "dry_run")
        print(f"  Dry-run entries: {dry_count}")
    print("=" * 60)
    print(f"Manifest written to: {manifest_path}")


if __name__ == "__main__":
    main()