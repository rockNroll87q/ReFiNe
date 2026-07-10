#!/usr/bin/env python3
"""
Simplified PDF downloader for the ReFiNe extraction pipeline.

Reads eligible_studies.csv and downloads legal open-access PDFs from:
  1. OpenAlex (primary)
  2. Semantic Scholar (fallback)

PDFs are saved to data/pdfs/{paper_id}.pdf so they can be processed by
the existing refine/extract.py pipeline.

Usage:
    python scripts/download_pdfs.py \
      --input data/input/eligible_studies.csv \
      --out-dir data/pdfs \
      --manifest data/input/pdf_download_manifest.csv
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API constants
# ---------------------------------------------------------------------------

OPENALEX_BASE = "https://api.openalex.org"
SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"


def _get_api_keys() -> Dict[str, str]:
    """Load API keys from environment (already loaded by dotenv in main)."""
    return {
        "openalex": os.environ.get("OPENALEX_API_KEY", ""),
        "semantic_scholar": os.environ.get("SEMANTIC_SCHOLAR_API_KEY", ""),
    }


def _load_env():
    """Load .env file if present."""
    # Search upward from this script's location
    base = Path(__file__).resolve().parent.parent
    for candidate in [base / ".env", Path(".env")]:
        if candidate.exists():
            load_dotenv(str(candidate))
            log.info("Loaded .env from %s", candidate)
            break


# ---------------------------------------------------------------------------
# OpenAlex helpers
# ---------------------------------------------------------------------------

def _openalex_lookup_by_doi(doi: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Fetch a work record from OpenAlex by DOI."""
    url = f"{OPENALEX_BASE}/works/doi:{doi}"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        log.debug("[OpenAlex] DOI=%s → HTTP %d", doi, resp.status_code)
    except requests.RequestException as exc:
        log.warning("[OpenAlex] DOI lookup failed for %s: %s", doi, exc)
    return None


def _openalex_search_by_title(title: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Search OpenAlex by title and return the first matching work."""
    url = f"{OPENALEX_BASE}/works"
    params = {"search": title, "limit": 1}
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0]
        log.debug("[OpenAlex] Title search '%s' → HTTP %d (no results)", title[:50], resp.status_code)
    except requests.RequestException as exc:
        log.warning("[OpenAlex] Title search failed for '%s': %s", title[:50], exc)
    return None


def _extract_pdf_from_openalex(work: Dict[str, Any]) -> Optional[str]:
    """Return a downloadable PDF URL from an OpenAlex work record."""
    # Direct open_access pdf_url
    oa = work.get("open_access") or {}
    oa_pdf = oa.get("oa_url") or oa.get("best_oa_location", {}).get("pdf_url")
    if oa_pdf:
        return oa_pdf

    # primary_location.pdf_url (newer OpenAlex schema)
    pl = work.get("primary_location") or {}
    pdf_from_loc = pl.get("pdf_url")
    if pdf_from_loc and isinstance(pdf_from_loc, str) and pdf_from_loc.strip():
        return pdf_from_loc

    # Also check the top-level 'download_pdf' field from our CSV-derived data
    download_pdf = work.get("download_pdf") or work.get("downloadPdf")
    if download_pdf and isinstance(download_pdf, str) and download_pdf.strip():
        return download_pdf

    return None


# ---------------------------------------------------------------------------
# Semantic Scholar helpers
# ---------------------------------------------------------------------------

def _ss_lookup_by_doi(doi: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Fetch a paper record from Semantic Scholar by DOI."""
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/DOI/{quote(doi, safe='')}"
    params = {"fields": "title,year,externalIds,openAccessPdf,url,venue,publicationDate"}
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code == 200 and resp.json() is not None:
            return resp.json()
        log.debug("[SS] DOI=%s → HTTP %d", doi, resp.status_code)
    except requests.RequestException as exc:
        log.warning("[SS] DOI lookup failed for %s: %s", doi, exc)
    return None


def _ss_search_by_title(title: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Search Semantic Scholar by title."""
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/search"
    params = {"query": title, "limit": 1, "fields": "title,year,externalIds,openAccessPdf,url"}
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code == 200:
            results = resp.json().get("data", [])
            if results:
                return results[0]
        log.debug("[SS] Title search '%s' → HTTP %d (no results)", title[:50], resp.status_code)
    except requests.RequestException as exc:
        log.warning("[SS] Title search failed for '%s': %s", title[:50], exc)
    return None


def _extract_pdf_from_ss(paper: Dict[str, Any]) -> Optional[str]:
    """Return a downloadable PDF URL from a Semantic Scholar paper record."""
    oa = paper.get("openAccessPdf") or {}
    url = oa.get("url") if isinstance(oa, dict) else None
    return url


# ---------------------------------------------------------------------------
# Download & validation
# ---------------------------------------------------------------------------

def download_pdf(url: str, dest_path: Path, max_retries: int = 3) -> tuple[str, Optional[str]]:
    """Download a PDF from *url* to *dest_path*.

    Returns (status, error_message).
    status is one of: 'downloaded', 'error'
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, stream=True, timeout=120)
            if resp.status_code == 429:
                wait = min(60, 10 * (2 ** attempt))
                log.warning("Rate limited (429). Waiting %ds before retry.", wait)
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                return "error", f"HTTP {resp.status_code} from {url}"

            # Validate content type
            ct = resp.headers.get("Content-Type", "")
            if "pdf" not in ct.lower() and "application/octet-stream" not in ct.lower():
                log.warning("[PDF] Unexpected Content-Type '%s' for %s", ct, url)

            # Read content and validate %PDF header
            content = resp.content
            if not content or len(content) < 5:
                return "error", "Empty response"

            if not content[:5].startswith(b"%PDF-"):
                log.warning("[PDF] No %%PDF header. First bytes: %s", content[:20])
                # Some servers still serve valid PDFs without the right header;
                # try to validate further by checking for common PDF structures
                if b"/Type" not in content and b"/Catalog" not in content and b"/Pages" not in content:
                    return "error", f"File does not appear to be a valid PDF (no %%PDF header)"

            dest_path.write_bytes(content)
            size = dest_path.stat().st_size
            log.info("[PDF] Downloaded %d bytes from source: %s", size, url[:100])
            return "downloaded", None

        except requests.RequestException as exc:
            wait = min(30, 5 * (2 ** attempt))
            log.warning("Download attempt %d failed for %s: %s. Retrying in %ds.",
                        attempt + 1, url[:80], exc, wait)
            time.sleep(wait)

    return "error", f"Failed after {max_retries} retries"


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------

MANIFEST_COLUMNS = [
    "paper_id", "title", "doi", "openalex_id", "semantic_scholar_id",
    "status", "source_used", "pdf_path", "landing_page_url",
    "pdf_url", "oa_status", "license", "error_message",
]


def _write_manifest_rows(rows: List[Dict[str, str]], manifest_path: Path):
    """Append *rows* to the CSV manifest."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Check if file has a proper header already
    write_header = True
    if manifest_path.exists() and manifest_path.stat().st_size > 0:
        with open(manifest_path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            # If the first line looks like our header, don't write it again
            if first_line.startswith("paper_id"):
                write_header = False

    with open(manifest_path, "a", newline="", encoding="utf-8") as mf:
        writer = csv.DictWriter(mf, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        for row in rows:
            # Ensure all values are strings or empty
            cleaned = {k: (str(v) if v is not None else "") for k, v in row.items()}
            writer.writerow(cleaned)


def _append_manual_needed(papers: List[Dict[str, str]], path: Path):
    """Append papers needing manual PDF acquisition."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # Check if header already exists
    write_header = not path.exists() or path.stat().st_size == 0
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            if first_line.startswith("paper_id"):
                write_header = False

    with open(path, "a", newline="", encoding="utf-8") as mf:
        writer = csv.writer(mf)
        if write_header:
            writer.writerow(["paper_id", "title", "doi", "reason"])
        for p in papers:
            writer.writerow([p["paper_id"], p.get("title", ""), p.get("doi", ""), p.get("reason", "")])


# ---------------------------------------------------------------------------
# Core download logic
# ---------------------------------------------------------------------------

def _sanitize_filename(name: str) -> str:
    """Ensure a safe filename component."""
    return name.replace("/", "_").replace("\\", "_").replace(":", "_")


def process_paper(
    row: Dict[str, str],
    out_dir: Path,
    keys: Dict[str, str],
    overwrite: bool = False,
    dry_run: bool = False,
) -> Dict[str, str]:
    """Process a single paper row. Returns the manifest row dict."""

    paper_id = row.get("paper_id", "").strip()
    doi = (row.get("doi") or "").strip().lower() if row.get("doi") else ""
    title_raw = (row.get("title") or "").strip()
    # Truncate title for display in manifest
    title_display = title_raw[:200] if title_raw else ""

    pdf_path = out_dir / f"{paper_id}.pdf"

    # --- Check already exists ---
    if pdf_path.exists() and not overwrite:
        return {
            "paper_id": paper_id,
            "title": title_display,
            "doi": doi,
            "openalex_id": "",
            "semantic_scholar_id": "",
            "status": "already_exists",
            "source_used": "already_exists",
            "pdf_path": str(pdf_path),
            "landing_page_url": row.get("doi_url", "") or "",
            "pdf_url": "",
            "oa_status": "",
            "license": "",
            "error_message": "",
        }

    # --- 1. Try OpenAlex ---
    oa_work = None
    work_id = ""
    landing_url = ""
    oa_status = ""
    license_val = ""

    if doi:
        log.info("[%s] OpenAlex DOI lookup: %s", paper_id, doi)
        oa_work = _openalex_lookup_by_doi(doi, keys["openalex"])
        # Retry with backoff for rate limiting
        if not oa_work:
            time.sleep(2)
            oa_work = _openalex_lookup_by_doi(doi, keys["openalex"])

    if not oa_work and title_raw:
        log.info("[%s] OpenAlex title search: %s", paper_id, title_display[:60])
        oa_work = _openalex_search_by_title(title_raw, keys["openalex"])
        if not oa_work:
            time.sleep(2)
            oa_work = _openalex_search_by_title(title_raw, keys["openalex"])

    if oa_work:
        work_id = oa_work.get("id", "") or ""
        oa_info = oa_work.get("open_access") or {}
        oa_status = oa_info.get("oa_status", "")
        best_oa = oa_info.get("best_oa_location") or {}
        license_val = best_oa.get("license") or ""

        pdf_url = _extract_pdf_from_openalex(oa_work)
        landing_url = oa_work.get("oai_url") or oa_work.get("doi_url") or oa_work.get("url", "")

        if pdf_url:
            log.info("[%s] OpenAlex PDF found: %s", paper_id, pdf_url[:100])
            if dry_run:
                return {
                    "paper_id": paper_id,
                    "title": title_display,
                    "doi": doi,
                    "openalex_id": work_id,
                    "semantic_scholar_id": "",
                    "status": "dry_run",
                    "source_used": "openalex",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": landing_url,
                    "pdf_url": pdf_url,
                    "oa_status": oa_status,
                    "license": license_val or "",
                    "error_message": "",
                }
            status, err = download_pdf(pdf_url, pdf_path)
            if status == "downloaded":
                return {
                    "paper_id": paper_id,
                    "title": title_display,
                    "doi": doi,
                    "openalex_id": work_id,
                    "semantic_scholar_id": "",
                    "status": "downloaded",
                    "source_used": "openalex",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": landing_url,
                    "pdf_url": pdf_url,
                    "oa_status": oa_status,
                    "license": license_val or "",
                    "error_message": "",
                }
            log.warning("[%s] OpenAlex download failed: %s", paper_id, err)

    # --- 2. Try Semantic Scholar (only if OpenAlex had no PDF) ---
    ss_paper = None
    ss_id = ""

    if doi:
        log.info("[%s] Semantic Scholar DOI lookup: %s", paper_id, doi)
        ss_paper = _ss_lookup_by_doi(doi, keys["semantic_scholar"])

    if not ss_paper and title_raw:
        log.info("[%s] Semantic Scholar title search: %s", paper_id, title_display[:60])
        ss_paper = _ss_search_by_title(title_raw, keys["semantic_scholar"])

    if ss_paper:
        ss_id = ss_paper.get("paperId") or ""
        pdf_url = _extract_pdf_from_ss(ss_paper)
        landing_url = ss_paper.get("url", "")

        if pdf_url:
            log.info("[%s] Semantic Scholar PDF found: %s", paper_id, pdf_url[:100])
            if dry_run:
                return {
                    "paper_id": paper_id,
                    "title": title_display,
                    "doi": doi,
                    "openalex_id": work_id,
                    "semantic_scholar_id": ss_id,
                    "status": "dry_run",
                    "source_used": "semantic_scholar",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": landing_url,
                    "pdf_url": pdf_url,
                    "oa_status": "",
                    "license": "",
                    "error_message": "",
                }
            status, err = download_pdf(pdf_url, pdf_path)
            if status == "downloaded":
                return {
                    "paper_id": paper_id,
                    "title": title_display,
                    "doi": doi,
                    "openalex_id": work_id,
                    "semantic_scholar_id": ss_id,
                    "status": "downloaded",
                    "source_used": "semantic_scholar",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": landing_url,
                    "pdf_url": pdf_url,
                    "oa_status": "",
                    "license": "",
                    "error_message": "",
                }
            log.warning("[%s] Semantic Scholar download failed: %s", paper_id, err)

    # --- 3. No legal PDF found ---
    return {
        "paper_id": paper_id,
        "title": title_display,
        "doi": doi,
        "openalex_id": work_id,
        "semantic_scholar_id": ss_id if ss_paper else "",
        "status": "no_legal_pdf",
        "source_used": "none",
        "pdf_path": str(pdf_path),
        "landing_page_url": landing_url or (row.get("doi_url") or ""),
        "pdf_url": "",
        "oa_status": oa_status if oa_work else "",
        "license": license_val if oa_work else "",
        "error_message": "No legal PDF found from OpenAlex or Semantic Scholar",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download open-access PDFs for eligible studies.",
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to the input CSV (e.g., data/input/eligible_studies.csv)",
    )
    parser.add_argument(
        "--out-dir", "-o",
        default="data/pdfs",
        help="Directory to save PDFs (default: data/pdfs)",
    )
    parser.add_argument(
        "--manifest", "-m",
        default=None,
        help="Path to write the manifest CSV (default: data/input/pdf_download_manifest.csv)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=0,
        help="Process at most this many papers (0 = all)",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Re-download PDFs even if they already exist",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without downloading",
    )
    parser.add_argument(
        "--manual-only", action="store_true",
        help="Only write papers that need manual PDF acquisition (skip download attempts)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    # Load environment
    _load_env()

    out_dir = Path(args.out_dir)
    manifest_path = Path(args.manifest) if args.manifest else Path("data/input/pdf_download_manifest.csv")
    manual_path = Path("data/input/manual_pdf_needed.csv")

    keys = _get_api_keys()

    # Read input CSV
    input_path = Path(args.input)
    if not input_path.exists():
        log.error("Input file not found: %s", input_path)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        papers = list(reader)

    if args.limit > 0:
        papers = papers[:args.limit]

    log.info("Processing %d papers from %s", len(papers), input_path)
    log.info("Output directory: %s", out_dir)
    log.info("Manifest path: %s", manifest_path)

    # Counters
    downloaded_ox = 0
    downloaded_ss = 0
    existed = 0
    no_pdf = 0
    errors = 0
    dry_run_count = 0
    manual_rows: List[Dict[str, str]] = []

    manifest_rows: List[Dict[str, str]] = []

    for idx, row in enumerate(papers):
        paper_id = row.get("paper_id", "").strip()
        log.info("[%d/%d] Processing %s ...", idx + 1, len(papers), paper_id)

        try:
            if args.manual_only:
                # Skip download, just add to manual queue
                result = {
                    "paper_id": paper_id,
                    "title": (row.get("title") or "")[:200],
                    "doi": (row.get("doi") or "").strip().lower(),
                    "openalex_id": "",
                    "semantic_scholar_id": "",
                    "status": "no_legal_pdf",
                    "source_used": "none",
                    "pdf_path": str(out_dir / f"{paper_id}.pdf"),
                    "landing_page_url": row.get("doi_url") or "",
                    "pdf_url": "",
                    "oa_status": "",
                    "license": "",
                    "error_message": "Manual-only mode: skipping download",
                }
                manual_rows.append({
                    "paper_id": paper_id,
                    "title": row.get("title") or "",
                    "doi": (row.get("doi") or "").strip(),
                    "reason": "Manual-only mode requested",
                })
            else:
                result = process_paper(
                    row, out_dir, keys,
                    overwrite=args.overwrite,
                    dry_run=args.dry_run,
                )

            # Update counters
            status = result["status"]
            if status == "downloaded":
                downloaded_ox += 1 if result["source_used"] == "openalex" else 0
                downloaded_ss += 1 if result["source_used"] == "semantic_scholar" else 0
            elif status == "already_exists":
                existed += 1
            elif status == "no_legal_pdf":
                no_pdf += 1
                manual_rows.append({
                    "paper_id": paper_id,
                    "title": row.get("title") or "",
                    "doi": (row.get("doi") or "").strip(),
                    "reason": result.get("error_message", "No legal PDF found"),
                })
            elif status == "dry_run":
                dry_run_count += 1

            manifest_rows.append(result)

        except Exception as exc:
            errors += 1
            log.error("[%s] Unexpected error: %s", paper_id, exc, exc_info=True)
            manifest_rows.append({
                "paper_id": paper_id,
                "title": (row.get("title") or "")[:200],
                "doi": (row.get("doi") or "").strip().lower(),
                "openalex_id": "",
                "semantic_scholar_id": "",
                "status": "error",
                "source_used": "none",
                "pdf_path": str(out_dir / f"{paper_id}.pdf"),
                "landing_page_url": row.get("doi_url") or "",
                "pdf_url": "",
                "oa_status": "",
                "license": "",
                "error_message": str(exc),
            })

    # Write manifest
    if manifest_rows:
        _write_manifest_rows(manifest_rows, manifest_path)
        log.info("Manifest written to %s", manifest_path)

    # Write manual queue
    if manual_rows:
        _append_manual_needed(manual_rows, manual_path)
        log.info("Manual PDF queue written to %s (%d papers)", manual_path, len(manual_rows))

    # --- Summary ---
    print("\n" + "=" * 60)
    print("PDF Download Summary")
    print("=" * 60)
    print(f"  Downloaded (OpenAlex):   {downloaded_ox}")
    print(f"  Downloaded (Semantic Sch):{downloaded_ss}")
    print(f"  Already existed:         {existed}")
    print(f"  No legal PDF found:      {no_pdf}")
    print(f"  Errors:                  {errors}")
    if args.dry_run:
        print(f"  Dry-run entries:         {dry_run_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()