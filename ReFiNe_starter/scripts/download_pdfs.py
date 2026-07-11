#!/usr/bin/env python3
"""Download PDFs for ReFiNe eligible studies using OpenAlex and Semantic Scholar.

This script reads `data/input/eligible_studies.csv`, tries to locate legal OA PDFs
through OpenAlex first and Semantic Scholar second, resolves obvious legal landing
pages, downloads valid PDFs into `data/pdfs/{paper_id}.pdf`, and maintains a
manifest plus a deduplicated manual queue.

It deliberately does not use Sci-Hub or paywall-bypass sources.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import quote, urljoin, urlparse

import requests

try:
    from bs4 import BeautifulSoup  # type: ignore
except Exception:  # pragma: no cover - regex fallback is used if bs4 is absent
    BeautifulSoup = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OPENALEX_BASE = "https://api.openalex.org"
SEMANTIC_SCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1"

STATUS_DOWNLOADED = "downloaded"
STATUS_ALREADY_EXISTS = "already_exists"
STATUS_DRY_RUN = "dry_run"
STATUS_PUBLISHER_403 = "publisher_403"
STATUS_INVALID_PDF = "invalid_pdf"
STATUS_NO_OA_LOCATION = "no_oa_location"
STATUS_LANDING_PAGE_UNRESOLVED = "landing_page_unresolved"
STATUS_REPOSITORY_LANDING_PAGE = "repository_landing_page"
STATUS_PMC_LANDING_PAGE = "pmc_landing_page"
STATUS_EUROPEPMC_BAD_PDF_URL = "europepmc_bad_pdf_url"
STATUS_ERROR = "error"

SUCCESS_STATUSES = {STATUS_DOWNLOADED, STATUS_ALREADY_EXISTS, STATUS_DRY_RUN}
MANUAL_STATUSES = {
    STATUS_PUBLISHER_403,
    STATUS_INVALID_PDF,
    STATUS_NO_OA_LOCATION,
    STATUS_LANDING_PAGE_UNRESOLVED,
    STATUS_REPOSITORY_LANDING_PAGE,
    STATUS_PMC_LANDING_PAGE,
    STATUS_EUROPEPMC_BAD_PDF_URL,
    STATUS_ERROR,
}

MANIFEST_COLUMNS = [
    "paper_id",
    "title",
    "doi",
    "openalex_id",
    "semantic_scholar_id",
    "status",
    "source_used",
    "pdf_path",
    "landing_page_url",
    "pdf_url",
    "oa_status",
    "license",
    "error_message",
]

TRUSTED_LANDING_DOMAINS = (
    "ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "europepmc.org",
    "frontiersin.org",
    "hal.science",
    "doaj.org",
    "escholarship.org",
    "hdl.handle.net",
)

DEFAULT_HEADERS = {
    "User-Agent": "ReFiNe PDF downloader/0.2 (mailto:refine-project@example.org)",
    "Accept": "application/pdf,text/html,application/xhtml+xml,*/*;q=0.8",
}

MIN_PDF_BYTES = 10_000
HTML_READ_LIMIT = 512_000

logger = logging.getLogger("download_pdfs")


@dataclass
class UrlAttempt:
    url: str
    source: str
    kind: str = "pdf_or_landing"


# ---------------------------------------------------------------------------
# Environment / simple helpers
# ---------------------------------------------------------------------------


def load_dotenv_if_available() -> None:
    """Load `.env` if python-dotenv is installed; otherwise silently ignore."""
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        return

    for candidate in (Path(".env"), Path(__file__).resolve().parent.parent / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            logger.info("Loaded environment from %s", candidate)
            return


def clean_doi(value: str) -> str:
    doi = (value or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.I)
    return doi.strip().lower()


def get_first(row: Dict[str, str], names: Sequence[str]) -> str:
    lower_map = {k.lower(): k for k in row.keys()}
    for name in names:
        key = lower_map.get(name.lower())
        if key is not None and row.get(key) is not None:
            value = str(row.get(key, "")).strip()
            if value:
                return value
    return ""


def get_domain(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def is_semantic_scholar_page(url: str) -> bool:
    return "semanticscholar.org" in get_domain(url)


def is_probable_landing_domain(url: str) -> bool:
    domain = get_domain(url)
    if domain in TRUSTED_LANDING_DOMAINS:
        return True
    if domain.endswith(".ncbi.nlm.nih.gov"):
        return True
    if domain == "doi.org" or domain.endswith("doi.org"):
        return True
    return False


def normalize_absolute_url(href: str, base_url: str) -> str:
    return urljoin(base_url, href.strip())


def is_pdfish_link(href: str) -> bool:
    h = href.lower()
    return ".pdf" in h or "/pdf/" in h or "?pdf" in h or "pdf=" in h


# ---------------------------------------------------------------------------
# OpenAlex helpers
# ---------------------------------------------------------------------------


def openalex_lookup_by_doi(session: requests.Session, doi: str, api_key: str = "") -> Optional[Dict[str, Any]]:
    url = f"{OPENALEX_BASE}/works/doi:{doi}"
    params: Dict[str, str] = {}
    if api_key:
        params["api_key"] = api_key
    try:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code != 404:
            logger.warning("OpenAlex DOI lookup returned HTTP %d for %s", resp.status_code, doi)
    except requests.RequestException as exc:
        logger.warning("OpenAlex DOI lookup failed for %s: %s", doi, exc)
    return None


def openalex_search_by_title(session: requests.Session, title: str, api_key: str = "") -> Optional[Dict[str, Any]]:
    url = f"{OPENALEX_BASE}/works"
    params: Dict[str, str] = {
        "search": title,
        "per_page": "1",
        "sort": "cited_by_count:desc",
    }
    if api_key:
        params["api_key"] = api_key
    try:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                return results[0]
        else:
            logger.warning("OpenAlex title search returned HTTP %d", resp.status_code)
    except requests.RequestException as exc:
        logger.warning("OpenAlex title search failed for %s: %s", title[:80], exc)
    return None


def openalex_candidate_urls(work: Dict[str, Any]) -> List[UrlAttempt]:
    attempts: List[UrlAttempt] = []

    def add(url: Any, kind: str = "pdf_or_landing") -> None:
        if not isinstance(url, str):
            return
        url = url.strip()
        if not url or is_semantic_scholar_page(url):
            return
        if url not in {a.url for a in attempts}:
            attempts.append(UrlAttempt(url=url, source="openalex", kind=kind))

    open_access = work.get("open_access") or {}

    # OpenAlex currently exposes best_oa_location as a top-level field, but keep
    # older/alternate shapes too.
    locations: List[Dict[str, Any]] = []
    for key in ("best_oa_location", "primary_location"):
        if isinstance(work.get(key), dict):
            locations.append(work[key])
    if isinstance(open_access.get("best_oa_location"), dict):
        locations.append(open_access["best_oa_location"])
    for key in ("locations", "oa_locations"):
        if isinstance(work.get(key), list):
            locations.extend([loc for loc in work[key] if isinstance(loc, dict)])
        if isinstance(open_access.get(key), list):
            locations.extend([loc for loc in open_access[key] if isinstance(loc, dict)])

    for loc in locations:
        add(loc.get("pdf_url"), "pdf")
    for loc in locations:
        add(loc.get("landing_page_url") or loc.get("url"), "landing")

    add(open_access.get("oa_url"), "landing")
    add(work.get("doi"), "landing")
    return attempts


# ---------------------------------------------------------------------------
# Semantic Scholar helpers
# ---------------------------------------------------------------------------


SS_FIELDS = "title,year,authors,externalIds,openAccessPdf,url,publicationTypes,journal"


def ss_lookup_by_doi(session: requests.Session, doi: str, api_key: str = "") -> Optional[Dict[str, Any]]:
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/DOI:{quote(doi, safe='')}"
    headers: Dict[str, str] = {}
    if api_key:
        headers["x-api-key"] = api_key
    try:
        resp = session.get(url, params={"fields": SS_FIELDS}, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            returned_doi = clean_doi((data.get("externalIds") or {}).get("DOI", ""))
            # Some records do not echo a DOI exactly; accept the direct DOI endpoint response.
            if not returned_doi or returned_doi == doi:
                return data
        elif resp.status_code != 404:
            logger.warning("Semantic Scholar DOI lookup returned HTTP %d for %s", resp.status_code, doi)
    except requests.RequestException as exc:
        logger.warning("Semantic Scholar DOI lookup failed for %s: %s", doi, exc)
    return None


def ss_search_by_title(session: requests.Session, title: str, api_key: str = "") -> Optional[Dict[str, Any]]:
    url = f"{SEMANTIC_SCHOLAR_BASE}/paper/search"
    headers: Dict[str, str] = {}
    if api_key:
        headers["x-api-key"] = api_key
    params = {"query": title, "limit": "1", "fields": SS_FIELDS}
    try:
        resp = session.get(url, params=params, headers=headers, timeout=30)
        if resp.status_code == 200:
            results = resp.json().get("data", [])
            if results:
                return results[0]
        elif resp.status_code != 404:
            logger.warning("Semantic Scholar title search returned HTTP %d", resp.status_code)
    except requests.RequestException as exc:
        logger.warning("Semantic Scholar title search failed for %s: %s", title[:80], exc)
    return None


def ss_candidate_urls(paper: Dict[str, Any]) -> List[UrlAttempt]:
    attempts: List[UrlAttempt] = []
    oa_pdf = paper.get("openAccessPdf") or {}
    if isinstance(oa_pdf, dict):
        pdf_url = (oa_pdf.get("url") or "").strip()
        # Do not use normal Semantic Scholar paper pages as PDF URLs.
        if pdf_url and not is_semantic_scholar_page(pdf_url):
            attempts.append(UrlAttempt(url=pdf_url, source="semantic_scholar", kind="pdf"))
    return attempts


# ---------------------------------------------------------------------------
# PDF validation / download
# ---------------------------------------------------------------------------


def read_limited_response(resp: requests.Response, limit: int = HTML_READ_LIMIT) -> bytes:
    content = bytearray()
    for chunk in resp.iter_content(chunk_size=8192):
        if not chunk:
            continue
        remaining = limit - len(content)
        content.extend(chunk[:remaining])
        if len(content) >= limit:
            break
    return bytes(content)


def validate_pdf_or_landing(session: requests.Session, url: str) -> Tuple[str, str, bytes]:
    """Return `(status, error, content)` for a URL.

    Status values: `pdf`, `html_landing_page`, `403`, `error`.
    For HTML pages, `content` contains a bounded HTML body for parsing.
    """
    try:
        # HEAD is only a hint; many sites block it or lie. Always use GET for the
        # actual decision.
        try:
            head = session.head(url, timeout=20, allow_redirects=True)
            if head.status_code == 403:
                return "403", "HTTP 403", b""
        except requests.RequestException:
            pass

        resp = session.get(url, timeout=60, stream=True, allow_redirects=True)
        if resp.status_code == 403:
            return "403", "HTTP 403", b""
        if resp.status_code == 404:
            return "error", "HTTP 404", b""
        if resp.status_code != 200:
            return "error", f"HTTP {resp.status_code}", b""

        prefix = read_limited_response(resp, limit=HTML_READ_LIMIT)
        if len(prefix) < 5:
            return "error", "Empty response", b""

        if prefix.startswith(b"%PDF"):
            return "pdf", "", b""

        preview = prefix[:4096].decode("utf-8", errors="replace").lower()
        content_type = resp.headers.get("Content-Type", "").lower()
        if "html" in content_type or "<!doctype" in preview or "<html" in preview:
            return "html_landing_page", "", prefix

        if "pdf" in content_type:
            return "error", "Content-Type suggested PDF but no %PDF header", b""

        if any(token in preview for token in ("captcha", "access denied", "login", "<script")):
            return "error", "Non-PDF blocker/login page detected", b""

        return "error", f"Unknown non-PDF response; first bytes={prefix[:32]!r}", b""
    except requests.RequestException as exc:
        return "error", str(exc), b""


def download_pdf(session: requests.Session, url: str, dest_path: Path, min_bytes: int = MIN_PDF_BYTES) -> Tuple[str, str]:
    """Download a complete PDF to disk.

    This streams the full response. It validates the first non-empty chunk before
    writing and then writes that chunk plus every remaining chunk. It never writes
    only the first 512 bytes.
    """
    tmp_path = dest_path.with_suffix(dest_path.suffix + ".part")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        resp = session.get(url, timeout=120, stream=True, allow_redirects=True)
        if resp.status_code == 403:
            return STATUS_PUBLISHER_403, f"Publisher HTTP 403: {get_domain(url)}"
        if resp.status_code != 200:
            return STATUS_ERROR, f"HTTP {resp.status_code} from {url}"

        iterator = resp.iter_content(chunk_size=8192)
        first_chunk = b""
        for chunk in iterator:
            if chunk:
                first_chunk = chunk
                break

        if len(first_chunk) < 5:
            return STATUS_ERROR, "Empty response"

        if not first_chunk.startswith(b"%PDF"):
            preview = first_chunk[:2048].decode("utf-8", errors="replace").lower()
            if "<!doctype" in preview or "<html" in preview:
                return STATUS_INVALID_PDF, "URL returned HTML, not PDF"
            return STATUS_INVALID_PDF, f"No %PDF header; first bytes={first_chunk[:32]!r}"

        with tmp_path.open("wb") as f:
            f.write(first_chunk)
            for chunk in iterator:
                if chunk:
                    f.write(chunk)

        size = tmp_path.stat().st_size
        if size < min_bytes:
            tmp_path.unlink(missing_ok=True)
            return STATUS_INVALID_PDF, f"Downloaded PDF is suspiciously small ({size} bytes)"

        tmp_path.replace(dest_path)
        logger.info("Downloaded %d bytes to %s", size, dest_path)
        return STATUS_DOWNLOADED, ""
    except requests.RequestException as exc:
        tmp_path.unlink(missing_ok=True)
        return STATUS_ERROR, str(exc)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        return STATUS_ERROR, str(exc)


# ---------------------------------------------------------------------------
# Landing-page resolution
# ---------------------------------------------------------------------------


def extract_pdf_links_from_html(html: str, base_url: str) -> List[str]:
    links: List[str] = []

    def add(href: Optional[str]) -> None:
        if not href:
            return
        absolute = normalize_absolute_url(href, base_url)
        if is_pdfish_link(absolute) and absolute not in links:
            links.append(absolute)

    if BeautifulSoup is not None:
        soup = BeautifulSoup(html, "html.parser")

        # High-value scholarly metadata.
        for attrs in (
            {"name": "citation_pdf_url"},
            {"name": "dc.identifier"},
            {"property": "citation_pdf_url"},
        ):
            tag = soup.find("meta", attrs=attrs)
            if tag is not None:
                content = tag.get("content")
                if content and is_pdfish_link(content):
                    add(content)

        # Some pages provide full text HTML metadata. Keep only if it is PDF-ish.
        tag = soup.find("meta", attrs={"name": "citation_fulltext_html_url"})
        if tag is not None:
            content = tag.get("content")
            if content and is_pdfish_link(content):
                add(content)

        for a in soup.find_all("a", href=True):
            href = str(a.get("href", ""))
            if is_pdfish_link(href):
                add(href)
    else:
        # Regex fallback if bs4 is unavailable.
        for match in re.finditer(r'<meta[^>]+name=["\']citation_pdf_url["\'][^>]+content=["\']([^"\']+)["\']', html, re.I):
            add(match.group(1))
        for match in re.finditer(r'href=["\']([^"\']*(?:\.pdf|/pdf/|\?pdf)[^"\']*)["\']', html, re.I):
            add(match.group(1))

    return links


def resolve_landing_page(session: requests.Session, url: str, content: bytes) -> Tuple[str, str, str]:
    """Resolve a known landing page to a real PDF URL.

    Returns `(status, pdf_url, error)`.
    """
    html = content.decode("utf-8", errors="replace")
    domain = get_domain(url)

    links = extract_pdf_links_from_html(html, url)
    for candidate in links:
        status, error, _ = validate_pdf_or_landing(session, candidate)
        if status == "pdf":
            return STATUS_DOWNLOADED, candidate, ""
        if status == "403":
            # Keep trying other links; one blocked link does not prove all are blocked.
            continue

    # PMC pages often expose a PDF link in the page HTML. If not, classify clearly.
    if "pmc.ncbi.nlm.nih.gov" in domain or "ncbi.nlm.nih.gov" in domain:
        return STATUS_PMC_LANDING_PAGE, "", "PMC/NCBI landing page found but no valid direct PDF link discovered"

    if "europepmc.org" in domain:
        render_url = f"{url.split('?')[0]}?pdf=render"
        status, error, _ = validate_pdf_or_landing(session, render_url)
        if status == "pdf":
            return STATUS_DOWNLOADED, render_url, ""
        return STATUS_EUROPEPMC_BAD_PDF_URL, "", error or "EuropePMC PDF render URL did not return a PDF"

    if any(domain == d or domain.endswith("." + d) for d in TRUSTED_LANDING_DOMAINS):
        return STATUS_REPOSITORY_LANDING_PAGE, "", "Repository landing page unresolved"

    if domain.endswith("doi.org") or domain == "doi.org":
        return STATUS_LANDING_PAGE_UNRESOLVED, "", "DOI landing page unresolved"

    return STATUS_LANDING_PAGE_UNRESOLVED, "", "Landing page unresolved"


def try_url_attempt(
    session: requests.Session,
    attempt: UrlAttempt,
    paper_id: str,
    pdf_path: Path,
    dry_run: bool,
) -> Tuple[Optional[Dict[str, str]], Optional[Tuple[str, str, str]]]:
    """Try one URL attempt.

    Returns `(manifest_result_if_success, failure_tuple)`.
    Failure tuple is `(status, url, error)`.
    """
    url = attempt.url
    if not url:
        return None, None

    logger.info("[%s] Trying %s URL: %s", paper_id, attempt.source, url[:120])
    status, error, content = validate_pdf_or_landing(session, url)

    if status == "pdf":
        if dry_run:
            return {
                "status": STATUS_DRY_RUN,
                "source_used": attempt.source,
                "pdf_url": url,
                "landing_page_url": "",
                "error_message": "",
            }, None
        dl_status, dl_error = download_pdf(session, url, pdf_path)
        if dl_status == STATUS_DOWNLOADED:
            return {
                "status": STATUS_DOWNLOADED,
                "source_used": attempt.source,
                "pdf_url": url,
                "landing_page_url": "",
                "error_message": "",
            }, None
        return None, (dl_status, url, dl_error)

    if status == "html_landing_page":
        # Only resolve known OA/repository/DOI landing pages. Do not crawl broadly.
        if is_probable_landing_domain(url):
            resolved_status, pdf_url, resolved_error = resolve_landing_page(session, url, content)
            if resolved_status == STATUS_DOWNLOADED and pdf_url:
                if dry_run:
                    return {
                        "status": STATUS_DRY_RUN,
                        "source_used": f"{attempt.source}_landing_page",
                        "pdf_url": pdf_url,
                        "landing_page_url": url,
                        "error_message": "",
                    }, None
                dl_status, dl_error = download_pdf(session, pdf_url, pdf_path)
                if dl_status == STATUS_DOWNLOADED:
                    return {
                        "status": STATUS_DOWNLOADED,
                        "source_used": f"{attempt.source}_landing_page",
                        "pdf_url": pdf_url,
                        "landing_page_url": url,
                        "error_message": "",
                    }, None
                return None, (dl_status, pdf_url, dl_error)
            return None, (resolved_status, url, resolved_error)
        return None, (STATUS_LANDING_PAGE_UNRESOLVED, url, "HTML landing page on untrusted/non-OA domain")

    if status == "403":
        return None, (STATUS_PUBLISHER_403, url, f"Publisher HTTP 403: {get_domain(url)}")

    return None, (STATUS_INVALID_PDF if "no %pdf" in error.lower() else STATUS_ERROR, url, error)


# ---------------------------------------------------------------------------
# Manifest / manual queue helpers
# ---------------------------------------------------------------------------


def load_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_manifest_rows(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    rows = load_csv_rows(path)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        pid = row.get("paper_id", "").strip()
        if pid:
            out[pid] = {k: row.get(k, "") for k in MANIFEST_COLUMNS}
    return out


def write_manifest(rows_by_id: Dict[str, Dict[str, str]], paper_order: Sequence[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered: List[str] = []
    seen: Set[str] = set()
    for pid in paper_order:
        if pid in rows_by_id and pid not in seen:
            ordered.append(pid)
            seen.add(pid)
    for pid in rows_by_id:
        if pid not in seen:
            ordered.append(pid)

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for pid in ordered:
            row = rows_by_id[pid]
            writer.writerow({col: row.get(col, "") for col in MANIFEST_COLUMNS})


def load_manual_ids(path: Path) -> Set[str]:
    if not path.exists() or path.stat().st_size == 0:
        return set()
    return {row.get("paper_id", "").strip() for row in load_csv_rows(path) if row.get("paper_id", "").strip()}


def write_manual_queue(rows_by_id: Dict[str, Dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["paper_id", "title", "doi", "reason"])
        writer.writeheader()
        for pid, row in sorted(rows_by_id.items()):
            if row.get("status") in MANUAL_STATUSES:
                writer.writerow(
                    {
                        "paper_id": pid,
                        "title": row.get("title", ""),
                        "doi": row.get("doi", ""),
                        "reason": row.get("error_message", row.get("status", "")),
                    }
                )


def existing_pdf_ids(out_dir: Path) -> Set[str]:
    if not out_dir.exists():
        return set()
    return {p.stem for p in out_dir.glob("*.pdf") if p.is_file()}


# ---------------------------------------------------------------------------
# Core paper processing
# ---------------------------------------------------------------------------


def build_manifest_row(
    base: Dict[str, str],
    *,
    status: str,
    source_used: str,
    pdf_path: Path,
    openalex_id: str = "",
    semantic_scholar_id: str = "",
    landing_page_url: str = "",
    pdf_url: str = "",
    oa_status: str = "",
    license_value: str = "",
    error_message: str = "",
) -> Dict[str, str]:
    return {
        "paper_id": base["paper_id"],
        "title": base["title"],
        "doi": base["doi"],
        "openalex_id": openalex_id,
        "semantic_scholar_id": semantic_scholar_id,
        "status": status,
        "source_used": source_used,
        "pdf_path": str(pdf_path),
        "landing_page_url": landing_page_url,
        "pdf_url": pdf_url,
        "oa_status": oa_status,
        "license": license_value,
        "error_message": error_message,
    }


def normalized_input_row(row: Dict[str, str], index: int) -> Dict[str, str]:
    paper_id = get_first(row, ["paper_id", "id", "ID", "refine_id"])
    if not paper_id:
        paper_id = f"REFINE-{index:04d}"
    title = get_first(row, ["title", "Title", "display_name", "paper_title"])
    doi = clean_doi(get_first(row, ["doi", "DOI", "paper_doi"] ))
    return {"paper_id": paper_id, "title": title, "doi": doi}


def process_paper(
    session: requests.Session,
    row: Dict[str, str],
    out_dir: Path,
    openalex_key: str,
    ss_key: str,
    overwrite: bool,
    dry_run: bool,
) -> Dict[str, str]:
    paper_id = row["paper_id"]
    title = row["title"]
    doi = row["doi"]
    pdf_path = out_dir / f"{paper_id}.pdf"

    if pdf_path.exists() and not overwrite:
        return build_manifest_row(row, status=STATUS_ALREADY_EXISTS, source_used="already_exists", pdf_path=pdf_path)

    failures: List[Tuple[str, str, str]] = []

    openalex_id = ""
    oa_status = ""
    license_value = ""

    # 1. OpenAlex
    oa_work: Optional[Dict[str, Any]] = None
    if doi:
        logger.info("[%s] OpenAlex DOI lookup: %s", paper_id, doi)
        oa_work = openalex_lookup_by_doi(session, doi, openalex_key)
    if oa_work is None and title:
        logger.info("[%s] OpenAlex title search: %s", paper_id, title[:80])
        oa_work = openalex_search_by_title(session, title, openalex_key)

    if oa_work is not None:
        openalex_id = str(oa_work.get("id", "") or "")
        oa_info = oa_work.get("open_access") or {}
        oa_status = str(oa_info.get("oa_status", "") or "")
        best_oa = oa_work.get("best_oa_location") or oa_info.get("best_oa_location") or {}
        if isinstance(best_oa, dict):
            license_value = str(best_oa.get("license", "") or "")

        attempts = openalex_candidate_urls(oa_work)
        if not attempts:
            failures.append((STATUS_NO_OA_LOCATION, "", "OpenAlex returned no OA PDF/location URL"))
        for attempt in attempts:
            result, failure = try_url_attempt(session, attempt, paper_id, pdf_path, dry_run)
            if result is not None:
                return build_manifest_row(
                    row,
                    status=result["status"],
                    source_used=result["source_used"],
                    pdf_path=pdf_path,
                    openalex_id=openalex_id,
                    landing_page_url=result.get("landing_page_url", ""),
                    pdf_url=result.get("pdf_url", ""),
                    oa_status=oa_status,
                    license_value=license_value,
                    error_message=result.get("error_message", ""),
                )
            if failure:
                failures.append(failure)

    # 2. Semantic Scholar fallback
    ss_paper: Optional[Dict[str, Any]] = None
    ss_id = ""
    if doi:
        logger.info("[%s] Semantic Scholar DOI lookup: %s", paper_id, doi)
        ss_paper = ss_lookup_by_doi(session, doi, ss_key)
    if ss_paper is None and title:
        logger.info("[%s] Semantic Scholar title search: %s", paper_id, title[:80])
        ss_paper = ss_search_by_title(session, title, ss_key)

    if ss_paper is not None:
        ss_id = str(ss_paper.get("paperId", "") or "")
        attempts = ss_candidate_urls(ss_paper)
        if not attempts:
            failures.append((STATUS_NO_OA_LOCATION, "", "Semantic Scholar returned no openAccessPdf.url"))
        for attempt in attempts:
            result, failure = try_url_attempt(session, attempt, paper_id, pdf_path, dry_run)
            if result is not None:
                return build_manifest_row(
                    row,
                    status=result["status"],
                    source_used=result["source_used"],
                    pdf_path=pdf_path,
                    openalex_id=openalex_id,
                    semantic_scholar_id=ss_id,
                    landing_page_url=result.get("landing_page_url", ""),
                    pdf_url=result.get("pdf_url", ""),
                    oa_status=oa_status,
                    license_value=license_value,
                    error_message=result.get("error_message", ""),
                )
            if failure:
                failures.append(failure)

    # Choose the most informative final failure.
    priority = [
        STATUS_PUBLISHER_403,
        STATUS_PMC_LANDING_PAGE,
        STATUS_EUROPEPMC_BAD_PDF_URL,
        STATUS_REPOSITORY_LANDING_PAGE,
        STATUS_LANDING_PAGE_UNRESOLVED,
        STATUS_INVALID_PDF,
        STATUS_ERROR,
        STATUS_NO_OA_LOCATION,
    ]
    final_status, final_url, final_error = STATUS_NO_OA_LOCATION, "", "No OA PDF location found from OpenAlex or Semantic Scholar"
    for status in priority:
        match = next((f for f in failures if f[0] == status), None)
        if match:
            final_status, final_url, final_error = match
            break

    return build_manifest_row(
        row,
        status=final_status,
        source_used="none",
        pdf_path=pdf_path,
        openalex_id=openalex_id,
        semantic_scholar_id=ss_id,
        landing_page_url=final_url if final_status != STATUS_PUBLISHER_403 else "",
        pdf_url=final_url if final_status == STATUS_PUBLISHER_403 else "",
        oa_status=oa_status,
        license_value=license_value,
        error_message=final_error,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download legal OA PDFs for ReFiNe eligible studies.")
    parser.add_argument("--input", type=Path, default=Path("data/input/eligible_studies.csv"))
    parser.add_argument("--out-dir", type=Path, default=Path("data/pdfs"))
    parser.add_argument("--manifest", type=Path, default=Path("data/input/pdf_download_manifest.csv"))
    parser.add_argument("--manual-queue", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manual-only", action="store_true")
    parser.add_argument("--api-key", default=None, help="OpenAlex API key; overrides OPENALEX_API_KEY")
    parser.add_argument("--ss-api-key", default=None, help="Semantic Scholar API key; overrides SEMANTIC_SCHOLAR_API_KEY")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds between papers; default 1.0")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    load_dotenv_if_available()

    if not args.input.exists():
        logger.error("Input CSV not found: %s", args.input)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    manual_queue = args.manual_queue or (args.input.parent / "manual_pdf_needed.csv")

    openalex_key = args.api_key or os.environ.get("OPENALEX_API_KEY", "")
    ss_key = args.ss_api_key or os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "")

    raw_rows = load_csv_rows(args.input)
    papers = [normalized_input_row(row, idx + 1) for idx, row in enumerate(raw_rows)]
    paper_order = [p["paper_id"] for p in papers]
    logger.info("Loaded %d papers from %s", len(papers), args.input)

    manifest_by_id = load_manifest_rows(args.manifest)
    manual_ids = load_manual_ids(manual_queue)
    pdf_ids = existing_pdf_ids(args.out_dir)

    if args.manual_only:
        papers = [p for p in papers if p["paper_id"] in manual_ids or p["paper_id"] not in pdf_ids]
        logger.info("manual-only mode: %d papers selected", len(papers))

    if args.limit is not None and args.limit > 0:
        papers = papers[: args.limit]
        logger.info("Limiting to %d papers", len(papers))

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    stats: Dict[str, int] = {}
    for idx, row in enumerate(papers, start=1):
        paper_id = row["paper_id"]
        logger.info("[%d/%d] Processing %s", idx, len(papers), paper_id)
        result = process_paper(
            session=session,
            row=row,
            out_dir=args.out_dir,
            openalex_key=openalex_key,
            ss_key=ss_key,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        manifest_by_id[paper_id] = result
        stats[result["status"]] = stats.get(result["status"], 0) + 1
        if args.sleep and idx < len(papers):
            time.sleep(args.sleep)

    write_manifest(manifest_by_id, paper_order, args.manifest)
    write_manual_queue(manifest_by_id, manual_queue)

    print("\n" + "=" * 60)
    print("PDF Download Summary")
    print("=" * 60)
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    print("-" * 60)
    print(f"  processed_this_run: {sum(stats.values())}")
    print(f"  manifest_rows_total: {len(manifest_by_id)}")
    print(f"  manual_queue: {manual_queue}")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
