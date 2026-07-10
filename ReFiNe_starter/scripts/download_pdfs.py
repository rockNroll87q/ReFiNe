#!/usr/bin/env python3
"""Enhanced PDF download script with landing-page resolution.

This script:
1. Reads eligible studies from a CSV
2. Looks up each paper in OpenAlex and Semantic Scholar
3. Validates whether returned URLs are actual PDFs or HTML landing pages
4. Resolves trusted OA/repository landing pages to find real PDF links
5. Classifies failures into clear categories
6. Writes results to a manifest CSV

Failure categories:
- downloaded: PDF successfully downloaded
- already_exists: PDF file was already present
- no_oa_location: No OA PDF found from any source
- publisher_403: Publisher returned HTTP 403 (blocked)
- doi_landing_page: DOI landing page returned HTML (not a PDF)
- pmc_landing_page: PMC/NCBI page resolved (may have full text)
- europepmc_bad_pdf_url: EuropePMC ?pdf=render returned 404
- repository_landing_page: Repository page that could/was resolved
- landing_page_unresolved: Landing page with no discoverable PDF
- invalid_pdf: Content-Type suggested PDF but %PDF header missing
- error: General/networking error

Legal/ethical boundaries:
- Does NOT use Sci-Hub
- Does NOT bypass paywalls
- Does NOT add Unpaywall or EuropePMC as broad new discovery sources
- Only resolves URLs already returned by OpenAlex/Semantic Scholar
"""

import argparse
import csv
import logging
import os
import re
import sys
import time
from bs4 import BeautifulSoup
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, quote

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENALEX_BASE = "https://api.openalex.org"
SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"

TRUSTED_OA_DOMAINS = {
    "ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "europepmc.org",
    "frontiersin.org",
    "hal.science",
    "doaj.org",
    "escholarship.org",
}

# Status constants for manifest
STATUS_DOWNLOADED = "downloaded"
STATUS_ALREADY_EXISTS = "already_exists"
STATUS_NO_OA_LOCATION = "no_oa_location"
STATUS_PUBLISHER_403 = "publisher_403"
STATUS_DOI_LANDING_PAGE = "doi_landing_page"
STATUS_PMIC_LANDING_PAGE = "pmc_landing_page"
STATUS_EUROPEPMC_BAD_PDF = "europepmc_bad_pdf_url"
STATUS_REPOSITORY_LANDING_PAGE = "repository_landing_page"
STATUS_LANDING_PAGE_UNRESOLVED = "landing_page_unresolved"
STATUS_INVALID_PDF = "invalid_pdf"
STATUS_ERROR = "error"

# ---------------------------------------------------------------------------
# HTML Parser for discovering PDF links in landing pages
# ---------------------------------------------------------------------------

class PDFLinkFinder:
    """Extract PDF URLs and citation metadata from HTML content."""

    def __init__(self):
        self.pdf_urls: List[str] = []
        self.citation_pdf_url: Optional[str] = None
        self.citation_fulltext_html_url: Optional[str] = None
        self._meta_name: Optional[str] = None
        self._meta_content: Optional[str] = None

    def parse(self, html: str):
        """Parse HTML and extract PDF links."""
        soup = BeautifulSoup(html, 'html.parser')

        # Look for <meta name="citation_pdf_url">
        meta_pdf = soup.find('meta', attrs={'name': 'citation_pdf_url'})
        if meta_pdf and meta_pdf.get('content'):
            self.citation_pdf_url = meta_pdf['content'].strip()

        # Look for <meta name="citation_fulltext_html_url">
        meta_html = soup.find('meta', attrs={'name': 'citation_fulltext_html_url'})
        if meta_html and meta_html.get('content'):
            self.citation_fulltext_html_url = meta_html['content'].strip()

        # Look for <a> tags with PDF links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            if any(p in href.lower() for p in ['.pdf', '/pdf/', '?pdf=']):
                self.pdf_urls.append(href)


# ---------------------------------------------------------------------------
# API key loading
# ---------------------------------------------------------------------------

def _get_api_keys() -> Dict[str, str]:
    """Load API keys from environment."""
    return {
        "openalex": os.environ.get("OPENALEX_API_KEY", ""),
        "semantic_scholar": os.environ.get("SEMANTIC_SCHOLAR_API_KEY", ""),
    }


def _load_env():
    """Load .env file if present."""
    base = Path(__file__).resolve().parent.parent
    for candidate in [base / ".env", Path(".env")]:
        if candidate.exists():
            from dotenv import load_dotenv
            load_dotenv(str(candidate))
            logging.info("Loaded .env from %s", candidate)
            break


# ---------------------------------------------------------------------------
# OpenAlex helpers
# ---------------------------------------------------------------------------

def _openalex_lookup_by_doi(doi: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Fetch a work record from OpenAlex by DOI."""
    import requests
    url = f"{OPENALEX_BASE}/works/doi:{doi}"
    headers = {"From": os.environ.get("OPENALEX_EMAIL", "refine-project")}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        logging.debug("[OpenAlex] DOI=%s → HTTP %d", doi, resp.status_code)
    except requests.RequestException as exc:
        logging.warning("[OpenAlex] DOI lookup failed for %s: %s", doi, exc)
    return None


def _openalex_search_by_title(title: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Search OpenAlex by title and return the first matching work."""
    import requests
    url = f"{OPENALEX_BASE}/works"
    params = {"search": title, "limit": 1}
    headers = {"From": os.environ.get("OPENALEX_EMAIL", "refine-project")}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0]
        logging.debug("[OpenAlex] Title search '%s' → HTTP %d (no results)", title[:50], resp.status_code)
    except requests.RequestException as exc:
        logging.warning("[OpenAlex] Title search failed for '%s': %s", title[:50], exc)
    return None


def _extract_pdf_from_openalex(work: Dict[str, Any]) -> Optional[str]:
    """Return a downloadable PDF URL from an OpenAlex work record."""
    oa = work.get("open_access") or {}
    best_oa = oa.get("best_oa_location") or {}

    # Check oa_url (legacy)
    oa_url = oa.get("oa_url")
    if oa_url and isinstance(oa_url, str) and oa_url.strip():
        return oa_url.strip()

    # Check best_oa_location fields
    pdf_url = best_oa.get("pdf_url")
    if pdf_url and isinstance(pdf_url, str) and pdf_url.strip():
        return pdf_url.strip()

    url = best_oa.get("url")
    if url and isinstance(url, str) and url.strip():
        return url.strip()

    # Check primary_location
    pl = work.get("primary_location") or {}
    pl_pdf = pl.get("pdf_url")
    if pl_pdf and isinstance(pl_pdf, str) and pl_pdf.strip():
        return pl_pdf.strip()

    return None


# ---------------------------------------------------------------------------
# Semantic Scholar helpers
# ---------------------------------------------------------------------------

def _ss_lookup_by_doi(doi: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Fetch a paper record from Semantic Scholar by DOI."""
    import requests
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/DOI/{quote(doi, safe='')}"
    params = {"fields": "title,year,externalIds,openAccessPdf,url"}
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=60)
        if resp.status_code == 200 and resp.json() is not None:
            return resp.json()
        logging.debug("[SS] DOI=%s → HTTP %d", doi, resp.status_code)
    except requests.RequestException as exc:
        logging.warning("[SS] DOI lookup failed for %s: %s", doi, exc)
    return None


def _ss_search_by_title(title: str, api_key: str) -> Optional[Dict[str, Any]]:
    """Search Semantic Scholar by title."""
    import requests
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
        logging.debug("[SS] Title search '%s' → HTTP %d (no results)", title[:50], resp.status_code)
    except requests.RequestException as exc:
        logging.warning("[SS] Title search failed for '%s': %s", title[:50], exc)
    return None


def _extract_pdf_from_ss(paper: Dict[str, Any]) -> Optional[str]:
    """Return a downloadable PDF URL from a Semantic Scholar paper record."""
    oa = paper.get("openAccessPdf") or {}
    url = oa.get("url") if isinstance(oa, dict) else None
    return url


# ---------------------------------------------------------------------------
# URL validation helpers
# ---------------------------------------------------------------------------

def _get_domain(url: str) -> str:
    """Extract the domain from a URL."""
    parsed = urlparse(url)
    return parsed.hostname or ""


def _validate_pdf_url(url: str, max_retries: int = 2) -> Tuple[str, Optional[str], Optional[bytes]]:
    """Validate whether a URL returns a valid PDF.

    Returns (status, error_message, content).
    status is one of: 'pdf', 'html_landing_page', '403', 'error'
    """
    import requests
    for attempt in range(max_retries):
        try:
            resp = requests.head(url, timeout=30, allow_redirects=True)

            # If head fails or returns unusual codes, try GET with stream
            if resp.status_code not in (200, 301, 302, 403, 404):
                resp = requests.get(url, stream=True, timeout=60)

            ct = resp.headers.get("Content-Type", "").lower()

            # 403 = publisher blocked
            if resp.status_code == 403:
                return "403", f"Publisher returned HTTP 403 for {url}", None

            # 404 = not found
            if resp.status_code == 404:
                return "error", f"HTTP 404 for {url}", None

            # Check content type
            if "pdf" in ct or "application/octet-stream" in ct:
                content = resp.content
                if content and len(content) >= 5 and content[:5].startswith(b"%PDF-"):
                    return "pdf", None, content
                # Try full download for validation
                resp_full = requests.get(url, timeout=120)
                content = resp_full.content
                if content and len(content) >= 5 and content[:5].startswith(b"%PDF-"):
                    return "pdf", None, content
                return "error", f"Content-Type suggests PDF but no %PDF header: {ct}", None

            # HTML content = landing page
            if "html" in ct or resp.text.lower().strip().startswith(("<!doctype", "<html")):
                return "html_landing_page", None, resp.content[:50000]  # Limit content size

            # Default: treat as potential PDF if not HTML and status is OK
            if resp.status_code == 200:
                content = resp.content
                if content and len(content) >= 5:
                    if content[:5].startswith(b"%PDF-"):
                        return "pdf", None, content
                    # Might still be a valid PDF with wrong Content-Type
                    return "pdf", None, content

            return "error", f"Unexpected response: HTTP {resp.status_code}, Content-Type: {ct}", None

        except requests.RequestException as exc:
            logging.warning("Validation attempt %d failed for %s: %s", attempt + 1, url[:80], exc)
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    return "error", f"Failed to validate {url} after {max_retries} attempts", None


# ---------------------------------------------------------------------------
# Status constants for manifest categorization
# ---------------------------------------------------------------------------

STATUS_DOWNLOADED = "downloaded"
STATUS_ALREADY_EXISTS = "already_exists"
STATUS_NO_OA_LOCATION = "no_oa_location"
STATUS_PUBLISHER_403 = "publisher_403"
STATUS_DOI_LANDING_PAGE = "doi_landing_page"
STATUS_PMC_LANDING_PAGE = "pmc_landing_page"
STATUS_EUROPEPMC_BAD_PDF_URL = "europepmc_bad_pdf_url"
STATUS_REPOSITORY_LANDING_PAGE = "repository_landing_page"
STATUS_LANDING_PAGE_UNRESOLVED = "landing_page_unresolved"
STATUS_INVALID_PDF = "invalid_pdf"
STATUS_ERROR = "error"
STATUS_PMC_FULLTEXT_AVAILABLE = "pmc_fulltext_available"

# ---------------------------------------------------------------------------
# Landing page resolvers for trusted OA domains
# ---------------------------------------------------------------------------

def _resolve_html_landing_page(content: bytes, base_url: str) -> Optional[str]:
    """Extract PDF URL from HTML landing page content."""
    try:
        html = content.decode("utf-8", errors="replace")
    except Exception:
        return None

    finder = PDFLinkFinder()
    finder.parse(html)

    # Priority 1: citation_pdf_url meta tag
    if finder.citation_pdf_url:
        pdf_url = finder.citation_pdf_url
        if not pdf_url.startswith(("http://", "https://")):
            parsed = urlparse(base_url)
            if pdf_url.startswith('/'):
                pdf_url = f"{parsed.scheme}://{parsed.netloc}{pdf_url}"
            else:
                pdf_url = f"{base_url.rsplit('/', 1)[0]}/{pdf_url}"
        logging.info("Found citation_pdf_url from %s: %s", base_url[:60], pdf_url[:120])
        return pdf_url

    # Priority 2: direct PDF links in <a> tags
    if finder.pdf_urls:
        link = finder.pdf_urls[0]
        if not link.startswith(("http://", "https://")):
            parsed = urlparse(base_url)
            if link.startswith('/'):
                link = f"{parsed.scheme}://{parsed.netloc}{link}"
            else:
                link = f"{base_url.rsplit('/', 1)[0]}/{link}"
        return link

    return None


def _resolve_pmc_page(content: bytes, base_url: str) -> Dict[str, Any]:
    """Resolve a PMC/NCBI landing page to find PDF or full text info."""
    try:
        html = content.decode("utf-8", errors="replace")
    except Exception:
        return {"status": "pmc_unresolved", "error": "Failed to decode HTML"}

    finder = PDFLinkFinder()
    finder.parse(html)

    # Extract PMCID from URL or page
    pmcid_match = re.search(r'/pmc/articles/(\w+)', base_url, re.IGNORECASE)
    if not pmcid_match:
        pmcid_match = re.search(r'pmcid[":\s]+(PMC\d+)', html, re.IGNORECASE)

    pmcid = pmcid_match.group(1) if pmcid_match else "unknown"

    # Check for PDF link
    pdf_url = finder.citation_pdf_url
    if not pdf_url:
        # Try EuropePMC API pattern
        europepmc_api = f"https://www.europepmc.org/backend/ptpmcrender.fcgi?pullid=1&repo=PMC&id={pmcid}&blobtype=pdf"
        logging.info("PMC page for %s (PMCID: %s). Suggested EuropePMC API: %s", base_url[:60], pmcid, europepmc_api[:100])

    # Check if full text is available
    has_fulltext = "full text" in html.lower() or "open access article" in html.lower()

    return {
        "status": "pmc_found" if pdf_url else ("pmc_fulltext_available" if has_fulltext else "pmc_no_pdf"),
        "pmcid": pmcid,
        "pdf_url": pdf_url or "",
        "has_fulltext": has_fulltext,
    }


def _resolve_europepmc_page(content: bytes, base_url: str) -> Dict[str, Any]:
    """Resolve a EuropePMC landing page."""
    try:
        html = content.decode("utf-8", errors="replace")
    except Exception:
        return {"status": "europepmc_unresolved", "error": "Failed to decode HTML"}

    finder = PDFLinkFinder()
    finder.parse(html)

    # Extract article ID
    article_match = re.search(r'/articles/(\w+)', base_url)
    article_id = article_match.group(1) if article_match else "unknown"

    pdf_url = finder.citation_pdf_url
    if not pdf_url:
        # Try PDF render endpoint
        pdf_render_url = f"{base_url.split('?')[0]}?pdf=render"
        logging.info("EuropePMC page for %s. Try PDF render: %s", base_url[:60], pdf_render_url[:100])

    return {
        "status": "europepmc_found" if pdf_url else "europepmc_no_pdf",
        "article_id": article_id,
        "pdf_url": pdf_url or "",
    }


def _resolve_repository_page(content: bytes, base_url: str) -> Optional[str]:
    """Resolve a repository landing page (HAL, DOAJ, eScholarship)."""
    domain = _get_domain(base_url)

    try:
        html = content.decode("utf-8", errors="replace")
    except Exception:
        return None

    finder = PDFLinkFinder()
    finder.parse(html)

    # HAL-specific: look for "pdf" link in download section
    if domain == "hal.science":
        hal_pdf_match = re.search(r'"(https?://[^"]+pdf[^"]+)"', html)
        if not hal_pdf_match:
            hal_pdf_match = re.search(r'href="(https?://[^"]+/pdf[^"]+)"', html)
        if hal_pdf_match:
            return hal_pdf_match.group(1)

    # DOAJ-specific: look for PDF link in article metadata
    if domain == "doaj.org":
        if finder.citation_pdf_url:
            return finder.citation_pdf_url
        doaj_pdf_match = re.search(r'"pdfUrl"\s*:\s*"([^"]+)"', html)
        if doaj_pdf_match:
            return doaj_pdf_match.group(1)

    # eScholarship-specific
    if domain == "escholarship.org":
        eschol_pdf_match = re.search(r'content="([^"]+)".*name="citation_pdf_url"', html, re.DOTALL)
        if not eschol_pdf_match:
            eschol_pdf_match = re.search(r'"(https?://[^"]+.*\.pdf[^"]*)"', html)
        if eschol_pdf_match:
            return eschol_pdf_match.group(1)

    # Generic fallback
    if finder.citation_pdf_url:
        return finder.citation_pdf_url
    if finder.pdf_urls:
        return finder.pdf_urls[0]

    return None


# ---------------------------------------------------------------------------
# Landing page resolution dispatcher
# ---------------------------------------------------------------------------

def resolve_landing_page(url: str, content: bytes) -> Dict[str, Any]:
    """Resolve a landing page URL and attempt to find the PDF.

    Returns a dict with resolution results.
    """
    domain = _get_domain(url)

    # PMC/NCBI pages
    if "ncbi.nlm.nih.gov/pmc" in url or "pmc.ncbi.nlm.nih.gov" in url:
        result = _resolve_pmc_page(content, url)
        logging.info("[PMC] Resolved %s → %s (PMCID: %s)", url[:60], result["status"], result.get("pmcid", ""))
        return result

    # EuropePMC pages
    if "europepmc.org" in domain:
        result = _resolve_europepmc_page(content, url)
        logging.info("[EuropePMC] Resolved %s → %s", url[:60], result["status"])
        return result

    # Trusted repository pages
    if domain in TRUSTED_OA_DOMAINS:
        pdf_url = _resolve_repository_page(content, url)
        if pdf_url:
            logging.info("[Repository] Found PDF from %s: %s", domain, pdf_url[:120])
            return {"status": "repository_pdf_found", "pdf_url": pdf_url}
        logging.warning("[Repository] No PDF found from %s", url[:60])
        return {"status": "repository_unresolved", "url": url}

    # Generic landing page
    pdf_url = _resolve_html_landing_page(content, url)
    if pdf_url:
        logging.info("[Generic] Found PDF from landing page: %s", pdf_url[:120])
        return {"status": "landing_page_pdf_found", "pdf_url": pdf_url}

    logging.warning("[Generic] No PDF found from landing page: %s", url[:60])
    return {"status": "landing_page_unresolved", "url": url}


# ---------------------------------------------------------------------------
# Download & validation
# ---------------------------------------------------------------------------

def download_pdf(url: str, dest_path: Path, max_retries: int = 3) -> Tuple[str, Optional[str]]:
    """Download a PDF from *url* to *dest_path*.

    Returns (status, error_message).
    status is one of: 'downloaded', 'invalid_pdf', 'error'
    """
    import requests
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, stream=True, timeout=120)
            if resp.status_code == 429:
                wait = min(60, 10 * (2 ** attempt))
                logging.warning("Rate limited (429). Waiting %ds before retry.", wait)
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                return "error", f"HTTP {resp.status_code} from {url}"

            # Validate content type
            ct = resp.headers.get("Content-Type", "")

            # Read content and validate %PDF header
            content = resp.content
            if not content or len(content) < 5:
                return "error", "Empty response"

            if not content[:5].startswith(b"%PDF-"):
                logging.warning("[PDF] No %%PDF header. First bytes: %s", content[:20])
                # Some servers still serve valid PDFs without the right header;
                # try to validate further by checking for common PDF structures
                if b"/Type" not in content and b"/Catalog" not in content and b"/Pages" not in content:
                    return "invalid_pdf", f"File does not appear to be a valid PDF (no %%PDF header)"

            dest_path.write_bytes(content)
            size = dest_path.stat().st_size
            logging.info("[PDF] Downloaded %d bytes from source: %s", size, url[:100])
            return "downloaded", None

        except requests.RequestException as exc:
            wait = min(30, 5 * (2 ** attempt))
            logging.warning("Download attempt %d failed for %s: %s. Retrying in %ds.",
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
# Core download logic with landing-page resolution
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
            "status": STATUS_ALREADY_EXISTS,
            "source_used": "already_exists",
            "pdf_path": str(pdf_path),
            "landing_page_url": row.get("doi_url") or "",
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
        logging.info("[%s] OpenAlex DOI lookup: %s", paper_id, doi)
        oa_work = _openalex_lookup_by_doi(doi, keys["openalex"])
        # Retry with backoff for rate limiting
        if not oa_work:
            time.sleep(2)
            oa_work = _openalex_lookup_by_doi(doi, keys["openalex"])

    if not oa_work and title_raw:
        logging.info("[%s] OpenAlex title search: %s", paper_id, title_display[:60])
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
            logging.info("[%s] OpenAlex PDF URL found: %s", paper_id, pdf_url[:100])

            # Validate the PDF URL before downloading
            validation_status, val_error, val_content = _validate_pdf_url(pdf_url)

            if validation_status == "403":
                domain = _get_domain(pdf_url)
                logging.warning("[%s] Publisher 403 for %s", paper_id, pdf_url[:80])
                # Try landing page resolution as fallback
                if landing_url:
                    result = _try_landing_page_resolution(paper_id, landing_url, out_dir, pdf_path)
                    if result["status"] == STATUS_DOWNLOADED:
                        return result
                return {
                    "paper_id": paper_id,
                    "title": title_display,
                    "doi": doi,
                    "openalex_id": work_id,
                    "semantic_scholar_id": "",
                    "status": STATUS_PUBLISHER_403,
                    "source_used": "openalex",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": landing_url or "",
                    "pdf_url": pdf_url,
                    "oa_status": oa_status,
                    "license": license_val or "",
                    "error_message": f"Publisher HTTP 403: {domain}",
                }

            elif validation_status == "html_landing_page":
                logging.info("[%s] OpenAlex URL returned HTML. Resolving landing page...", paper_id)
                result = _try_landing_page_resolution(paper_id, pdf_url, out_dir, pdf_path, content=val_content)
                if result["status"] in (STATUS_DOWNLOADED, STATUS_PMIC_LANDING_PAGE):
                    return result
                # Also try the landing URL
                if landing_url and landing_url != pdf_url:
                    result = _try_landing_page_resolution(paper_id, landing_url, out_dir, pdf_path)
                    if result["status"] in (STATUS_DOWNLOADED, STATUS_PMIC_LANDING_PAGE):
                        return result

            elif validation_status == "error":
                logging.warning("[%s] PDF URL validation failed: %s", paper_id, val_error)

            else:  # validation_status == "pdf" - valid PDF
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
                        "landing_page_url": landing_url or "",
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
                        "status": STATUS_DOWNLOADED,
                        "source_used": "openalex",
                        "pdf_path": str(pdf_path),
                        "landing_page_url": landing_url or "",
                        "pdf_url": pdf_url,
                        "oa_status": oa_status,
                        "license": license_val or "",
                        "error_message": "",
                    }
                if status == "invalid_pdf":
                    return {
                        "paper_id": paper_id,
                        "title": title_display,
                        "doi": doi,
                        "openalex_id": work_id,
                        "semantic_scholar_id": "",
                        "status": STATUS_INVALID_PDF,
                        "source_used": "openalex",
                        "pdf_path": str(pdf_path),
                        "landing_page_url": landing_url or "",
                        "pdf_url": pdf_url,
                        "oa_status": oa_status,
                        "license": license_val or "",
                        "error_message": err or "Invalid PDF content",
                    }
                logging.warning("[%s] OpenAlex download failed: %s", paper_id, err)

    # --- 2. Try Semantic Scholar (only if OpenAlex had no PDF) ---
    ss_paper = None
    ss_id = ""

    if doi:
        logging.info("[%s] Semantic Scholar DOI lookup: %s", paper_id, doi)
        ss_paper = _ss_lookup_by_doi(doi, keys["semantic_scholar"])

    if not ss_paper and title_raw:
        logging.info("[%s] Semantic Scholar title search: %s", paper_id, title_display[:60])
        ss_paper = _ss_search_by_title(title_raw, keys["semantic_scholar"])

    if ss_paper:
        ss_id = ss_paper.get("paperId") or ""
        pdf_url = _extract_pdf_from_ss(ss_paper)
        landing_url = ss_paper.get("url", "")

        if pdf_url:
            logging.info("[%s] Semantic Scholar PDF URL found: %s", paper_id, pdf_url[:100])

            # Validate the PDF URL before downloading
            validation_status, val_error, val_content = _validate_pdf_url(pdf_url)

            if validation_status == "403":
                domain = _get_domain(pdf_url)
                logging.warning("[%s] Publisher 403 for %s", paper_id, pdf_url[:80])
                # Try landing page resolution as fallback
                if landing_url:
                    result = _try_landing_page_resolution(paper_id, landing_url, out_dir, pdf_path)
                    if result["status"] == STATUS_DOWNLOADED:
                        return result
                return {
                    "paper_id": paper_id,
                    "title": title_display,
                    "doi": doi,
                    "openalex_id": work_id,
                    "semantic_scholar_id": ss_id,
                    "status": STATUS_PUBLISHER_403,
                    "source_used": "semantic_scholar",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": landing_url or "",
                    "pdf_url": pdf_url,
                    "oa_status": "",
                    "license": "",
                    "error_message": f"Publisher HTTP 403: {domain}",
                }

            elif validation_status == "html_landing_page":
                logging.info("[%s] Semantic Scholar URL returned HTML. Resolving landing page...", paper_id)
                result = _try_landing_page_resolution(paper_id, pdf_url, out_dir, pdf_path, content=val_content)
                if result["status"] in (STATUS_DOWNLOADED, STATUS_PMIC_LANDING_PAGE):
                    return result

            elif validation_status == "error":
                logging.warning("[%s] PDF URL validation failed: %s", paper_id, val_error)

            else:  # valid PDF
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
                        "landing_page_url": landing_url or "",
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
                        "status": STATUS_DOWNLOADED,
                        "source_used": "semantic_scholar",
                        "pdf_path": str(pdf_path),
                        "landing_page_url": landing_url or "",
                        "pdf_url": pdf_url,
                        "oa_status": "",
                        "license": "",
                        "error_message": "",
                    }
                if status == "invalid_pdf":
                    return {
                        "paper_id": paper_id,
                        "title": title_display,
                        "doi": doi,
                        "openalex_id": work_id,
                        "semantic_scholar_id": ss_id,
                        "status": STATUS_INVALID_PDF,
                        "source_used": "semantic_scholar",
                        "pdf_path": str(pdf_path),
                        "landing_page_url": landing_url or "",
                        "pdf_url": pdf_url,
                        "oa_status": "",
                        "license": "",
                        "error_message": err or "Invalid PDF content",
                    }
                logging.warning("[%s] Semantic Scholar download failed: %s", paper_id, err)

    # --- 3. No legal PDF found ---
    return {
        "paper_id": paper_id,
        "title": title_display,
        "doi": doi,
        "openalex_id": work_id,
        "semantic_scholar_id": ss_id if ss_paper else "",
        "status": STATUS_NO_OA_LOCATION,
        "source_used": "none",
        "pdf_path": str(pdf_path),
        "landing_page_url": landing_url or (row.get("doi_url") or ""),
        "pdf_url": "",
        "oa_status": oa_status if oa_work else "",
        "license": license_val if oa_work else "",
        "error_message": "No OA PDF location found from OpenAlex or Semantic Scholar",
    }


def _try_landing_page_resolution(
    paper_id: str,
    url: str,
    out_dir: Path,
    pdf_path: Path,
    content: Optional[bytes] = None,
) -> Dict[str, str]:
    """Try to resolve a landing page URL and download the PDF."""

    # Fetch content if not provided
    if content is None:
        try:
            import requests
            resp = requests.get(url, timeout=60)
            if resp.status_code == 403:
                domain = _get_domain(url)
                return {
                    "paper_id": paper_id,
                    "title": "",
                    "doi": "",
                    "openalex_id": "",
                    "semantic_scholar_id": "",
                    "status": STATUS_PUBLISHER_403,
                    "source_used": "landing_page",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": url,
                    "pdf_url": "",
                    "oa_status": "",
                    "license": "",
                    "error_message": f"Publisher HTTP 403: {domain}",
                }
            if resp.status_code != 200:
                return {
                    "paper_id": paper_id,
                    "title": "",
                    "doi": "",
                    "openalex_id": "",
                    "semantic_scholar_id": "",
                    "status": STATUS_LANDING_PAGE_UNRESOLVED,
                    "source_used": "landing_page",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": url,
                    "pdf_url": "",
                    "oa_status": "",
                    "license": "",
                    "error_message": f"HTTP {resp.status_code} from landing page",
                }
            content = resp.content
        except requests.RequestException as exc:
            return {
                "paper_id": paper_id,
                "title": "",
                "doi": "",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "status": STATUS_ERROR,
                "source_used": "landing_page",
                "pdf_path": str(pdf_path),
                "landing_page_url": url,
                "pdf_url": "",
                "oa_status": "",
                "license": "",
                "error_message": f"Failed to fetch landing page: {exc}",
            }

    # Resolve the landing page
    result = resolve_landing_page(url, content)
    status = result.get("status", "")

    if status in ("pmc_found", "repository_pdf_found", "landing_page_pdf_found"):
        pdf_url = result.get("pdf_url", "")
        if pdf_url:
            logging.info("[%s] Found PDF from landing page: %s", paper_id, pdf_url[:100])
            # Validate before downloading
            val_status, val_err, _ = _validate_pdf_url(pdf_url)
            if val_status == "403":
                domain = _get_domain(pdf_url)
                return {
                    "paper_id": paper_id,
                    "title": "",
                    "doi": "",
                    "openalex_id": "",
                    "semantic_scholar_id": "",
                    "status": STATUS_PUBLISHER_403,
                    "source_used": "landing_page",
                    "pdf_path": str(pdf_path),
                    "landing_page_url": url,
                    "pdf_url": pdf_url,
                    "oa_status": "",
                    "license": "",
                    "error_message": f"Publisher HTTP 403: {domain}",
                }
            if val_status == "pdf":
                # Valid PDF - download it
                status_dl, err = download_pdf(pdf_url, pdf_path)
                if status_dl == "downloaded":
                    return {
                        "paper_id": paper_id,
                        "title": "",
                        "doi": "",
                        "openalex_id": "",
                        "semantic_scholar_id": "",
                        "status": STATUS_DOWNLOADED,
                        "source_used": "landing_page",
                        "pdf_path": str(pdf_path),
                        "landing_page_url": url,
                        "pdf_url": pdf_url,
                        "oa_status": "",
                        "license": "",
                        "error_message": "",
                    }
                logging.warning("[%s] Download failed from landing page: %s", paper_id, err)

        elif status == "pmc_fulltext_available":
            pmcid = result.get("pmcid", "")
            has_ft = result.get("has_fulltext", False)
            return {
                "paper_id": paper_id,
                "title": "",
                "doi": "",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "status": STATUS_PMIC_LANDING_PAGE,
                "source_used": "landing_page",
                "pdf_path": str(pdf_path),
                "landing_page_url": url,
                "pdf_url": result.get("pdf_url", ""),
                "oa_status": "",
                "license": "",
                "error_message": f"PMC full text available (PMCID: {pmcid}), no direct PDF download",
            }

        elif status == "pmc_no_pdf":
            pmcid = result.get("pmcid", "")
            return {
                "paper_id": paper_id,
                "title": "",
                "doi": "",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "status": STATUS_PMIC_LANDING_PAGE,
                "source_used": "landing_page",
                "pdf_path": str(pdf_path),
                "landing_page_url": url,
                "pdf_url": "",
                "oa_status": "",
                "license": "",
                "error_message": f"PMC article available but no PDF (PMCID: {pmcid})",
            }

        elif status == "europepmc_found":
            pdf_url = result.get("pdf_url", "")
            if pdf_url:
                # Try the EuropePMC PDF render endpoint
                pdf_render_url = f"{url.split('?')[0]}?pdf=render"
                logging.info("[%s] Trying EuropePMC PDF render: %s", paper_id, pdf_render_url[:100])
                val_status2, val_err2, _ = _validate_pdf_url(pdf_render_url)
                if val_status2 == "403":
                    return {
                        "paper_id": paper_id,
                        "title": "",
                        "doi": "",
                        "openalex_id": "",
                        "semantic_scholar_id": "",
                        "status": STATUS_EUROPEPMC_BAD_PDF_URL,
                        "source_used": "landing_page",
                        "pdf_path": str(pdf_path),
                        "landing_page_url": url,
                        "pdf_url": pdf_render_url,
                        "oa_status": "",
                        "license": "",
                        "error_message": "EuropePMC PDF render returned 403",
                    }
                if val_status2 == "pdf":
                    status_dl, err = download_pdf(pdf_render_url, pdf_path)
                    if status_dl == "downloaded":
                        return {
                            "paper_id": paper_id,
                            "title": "",
                            "doi": "",
                            "openalex_id": "",
                            "semantic_scholar_id": "",
                            "status": STATUS_DOWNLOADED,
                            "source_used": "europepmc",
                            "pdf_path": str(pdf_path),
                            "landing_page_url": url,
                            "pdf_url": pdf_render_url,
                            "oa_status": "",
                            "license": "",
                            "error_message": "",
                        }

        elif status == "europepmc_no_pdf":
            return {
                "paper_id": paper_id,
                "title": "",
                "doi": "",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "status": STATUS_EUROPEPMC_BAD_PDF_URL,
                "source_used": "landing_page",
                "pdf_path": str(pdf_path),
                "landing_page_url": url,
                "pdf_url": "",
                "oa_status": "",
                "license": "",
                "error_message": "EuropePMC article found but no PDF available",
            }

        elif status == "repository_unresolved":
            return {
                "paper_id": paper_id,
                "title": "",
                "doi": "",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "status": STATUS_REPOSITORY_LANDING_PAGE,
                "source_used": "landing_page",
                "pdf_path": str(pdf_path),
                "landing_page_url": url,
                "pdf_url": "",
                "oa_status": "",
                "license": "",
                "error_message": f"Repository landing page unresolved: {url[:80]}",
            }

        else:  # landing_page_unresolved or unknown
            return {
                "paper_id": paper_id,
                "title": "",
                "doi": "",
                "openalex_id": "",
                "semantic_scholar_id": "",
                "status": STATUS_LANDING_PAGE_UNRESOLVED,
                "source_used": "landing_page",
                "pdf_path": str(pdf_path),
                "landing_page_url": url,
                "pdf_url": "",
                "oa_status": "",
                "license": "",
                "error_message": f"Landing page unresolved: {url[:80]}",
            }

    # No PDF found from landing page resolution
    return {
        "paper_id": paper_id,
        "title": "",
        "doi": "",
        "openalex_id": "",
        "semantic_scholar_id": "",
        "status": STATUS_LANDING_PAGE_UNRESOLVED,
        "source_used": "landing_page",
        "pdf_path": str(pdf_path),
        "landing_page_url": url,
        "pdf_url": "",
        "oa_status": "",
        "license": "",
        "error_message": f"Failed to resolve PDF from landing page: {url[:80]}",
    }
