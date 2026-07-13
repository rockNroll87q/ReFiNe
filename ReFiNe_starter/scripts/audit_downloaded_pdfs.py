#!/usr/bin/env python3
"""Audit downloaded PDFs for ReFiNe eligible studies.

Compares extracted PDF text/titles against expected titles from eligible_studies.csv
and manifest data to detect false-positive downloads (wrong papers, manuals, acknowledgements, etc.).

Usage:
    python scripts/audit_downloaded_pdfs.py \\
        --input data/input/eligible_studies.csv \\
        --manifest data/input/pdf_download_manifest.csv \\
        --pdf-dir data/pdfs \\
        --out data/input/pdf_audit_report.csv \\
        --suspects data/input/suspect_pdfs.csv \\
        [--quarantine]
"""

import argparse
import csv
import logging
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Sequence

try:
    from rapidfuzz import fuzz, process as rf_process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("audit_downloaded_pdfs")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_COLUMNS = [
    "paper_id", "title", "doi", "openalex_id", "semantic_scholar_id",
    "pmid", "pmcid", "pubmed_url", "pmc_url", "status", "source_used",
    "pdf_path", "landing_page_url", "pdf_url", "oa_status", "license",
    "error_message", "secondary_status", "secondary_error_message",
]

SUSPECT_PDF_KEYWORDS = [
    r"\bmanual\b",
    r"\backnowledgement\b",
    r"\backnowledgment\b",
    r"\bsupplement(?:ary)?\b",
    r"\bappendix\b",
    r"\bprotocol\b",
    r"\bchecklist\b",
    r"\bdata\s+availability\b",
    r"\bauthor\s+manuscript\s+only\b",
]

SUSPECT_PDF_TITLE_KEYWORDS = [
    "vbm8 manual",
    "spm manual",
    "acknowledgement list",
    "acknowledgment list",
    "supplementary material",
    "supplemental material",
    "data availability statement",
]

TITLE_SIMILARITY_VALIDATED = 85
TITLE_SIMILARITY_HIGH = 90


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------


def extract_pdf_text(pdf_path: Path, max_pages: int = 2) -> Tuple[str, str]:
    """Extract text from the first `max_pages` pages of a PDF.

    Returns (full_extracted_text, title_or_first_line).
    """
    if not pdf_path.exists():
        return "", ""

    file_size = pdf_path.stat().st_size
    if file_size < 100:
        return "", "too_small"

    # Check for valid PDF header
    with open(pdf_path, "rb") as f:
        header = f.read(5)
    if not header.startswith(b"%PDF"):
        return "", "not_a_pdf"

    text_parts: List[str] = []
    title_candidate = ""

    if HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            num_pages = min(len(reader.pages), max_pages)
            for i in range(num_pages):
                page_text = reader.pages[i].extract_text() or ""
                page_text = _clean_pdf_text(page_text)
                text_parts.append(page_text)
                if not title_candidate:
                    title_candidate = _extract_title_from_page(page_text)
        except Exception as exc:
            logger.debug("pypdf extraction failed for %s: %s", pdf_path.name, exc)

    if not text_parts or all(not t.strip() for t in text_parts):
        return "", "unreadable"

    full_text = "\n".join(text_parts)
    if not title_candidate:
        title_candidate = _extract_title_from_page(full_text)

    return full_text, title_candidate


def _clean_pdf_text(text: str) -> str:
    """Clean up common PDF extraction artifacts."""
    # Remove form feed characters
    text = text.replace("\f", "\n")
    # Collapse excessive whitespace but preserve newlines
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def _extract_title_from_page(text: str) -> str:
    """Try to extract a title-like string from the top of a PDF page."""
    for line in text.split("\n"):
        stripped = line.strip()
        if len(stripped) > 20 and len(stripped) < 300:
            # Skip lines that look like author names, affiliations, or addresses
            if re.match(r"^\d+$", stripped):
                continue
            if re.search(r"\(20\d{2}\)", stripped) and "," in stripped:
                continue
            return stripped
    return ""


# ---------------------------------------------------------------------------
# Title similarity
# ---------------------------------------------------------------------------


def normalize_title(title: str) -> str:
    """Normalize a title for comparison: lowercase, strip punctuation."""
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def compute_title_similarity(expected_title: str, pdf_text_or_title: str) -> float:
    """Compute a similarity score between expected title and PDF text/title.

    Returns a percentage 0-100.
    """
    if not expected_title or not pdf_text_or_title:
        return 0.0

    norm_expected = normalize_title(expected_title)
    norm_pdf = normalize_title(pdf_text_or_title)

    if HAS_RAPIDFUZZ:
        # Use partial ratio for cases where the PDF title might be a substring
        score = fuzz.partial_ratio(norm_expected, norm_pdf)
        # Also use token sort ratio
        token_score = fuzz.token_sort_ratio(norm_expected, norm_pdf)
        # Use token set ratio for overlapping words
        token_set_score = fuzz.token_set_ratio(norm_expected, norm_pdf)
        return max(score, token_score, token_set_score)
    else:
        # Fallback to difflib
        matcher = difflib.SequenceMatcher(None, norm_expected, norm_pdf)
        ratio = matcher.ratio() * 100
        return min(ratio, 100.0)


def compute_best_title_similarity(expected_title: str, candidates: List[str]) -> Tuple[float, str]:
    """Find the best title similarity score among multiple candidate strings."""
    if not candidates or not expected_title:
        return 0.0, ""

    best_score = 0.0
    best_candidate = ""

    for candidate in candidates:
        score = compute_title_similarity(expected_title, candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate

    return best_score, best_candidate


# ---------------------------------------------------------------------------
# DOI detection in PDF text/metadata
# ---------------------------------------------------------------------------


def extract_doi_from_pdf(pdf_path: Path) -> Optional[str]:
    """Try to extract a DOI from PDF metadata or first few pages of text."""
    if not pdf_path.exists():
        return None

    doi_pattern = re.compile(r"10\.\d{4,}/[^\s;,\)\]]+")

    # Try PDF metadata first
    if HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(str(pdf_path))
            meta = reader.metadata
            if meta and hasattr(meta, '/DOI') and meta['/DOI']:
                doi_match = re.search(doi_pattern, str(meta['/DOI']))
                if doi_match:
                    return doi_match.group(0)
            if meta and hasattr(meta, '/Title') and meta['/Title']:
                doi_match = re.search(doi_pattern, str(meta['/Title']))
                if doi_match:
                    return doi_match.group(0)
        except Exception:
            pass

    # Try text extraction for DOI
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        num_pages = min(len(reader.pages), 3)
        for i in range(num_pages):
            page_text = reader.pages[i].extract_text() or ""
            doi_match = re.search(doi_pattern, page_text)
            if doi_match:
                return doi_match.group(0)
    except Exception:
        pass

    return None


def doi_matches(expected_doi: str, found_doi: Optional[str]) -> bool:
    """Check whether two DOIs match (after normalization)."""
    if not expected_doi or not found_doi:
        return False
    clean_expected = re.sub(r"[^0-9a-zA-Z]", "", expected_doi.lower())
    clean_found = re.sub(r"[^0-9a-zA-Z]", "", found_doi.lower())
    return clean_expected == clean_found


# ---------------------------------------------------------------------------
# Suspect PDF detection
# ---------------------------------------------------------------------------


def is_suspect_pdf_text(text: str) -> Optional[str]:
    """Check if extracted text looks like a suspect document.

    Returns the reason string or None if not suspect.
    """
    lower = text.lower()
    for keyword in SUSPECT_PDF_KEYWORDS:
        if re.search(keyword, lower):
            return f"Text contains suspect keyword pattern: {keyword}"
    return None


def is_suspect_pdf_title(title: str) -> Optional[str]:
    """Check if the extracted title looks like a non-paper document."""
    lower = title.lower()
    for kw in SUSPECT_PDF_TITLE_KEYWORDS:
        if kw in lower:
            return f"Extracted title matches suspect pattern: {kw}"
    return None


# ---------------------------------------------------------------------------
# Audit classification
# ---------------------------------------------------------------------------


def audit_pdf(
    paper_id: str,
    expected_title: str,
    doi: str,
    pdf_path: Path,
    manifest_status: str,
    source_used: str,
    pdf_url: str,
) -> Dict[str, str]:
    """Audit one PDF and return an audit report row."""

    # Check if file exists
    if not pdf_path.exists():
        return {
            "paper_id": paper_id,
            "expected_title": expected_title,
            "doi": doi,
            "pdf_path": str(pdf_path),
            "manifest_status": manifest_status,
            "source_used": source_used,
            "pdf_url": pdf_url,
            "extracted_title_or_first_text": "",
            "title_similarity": 0.0,
            "doi_found_in_pdf": "",
            "audit_status": "missing_pdf",
            "reason": "PDF file not found on disk",
        }

    # Extract text
    full_text, title_candidate = extract_pdf_text(pdf_path)

    if not full_text or full_text == "unreadable" or full_text == "not_a_pdf":
        return {
            "paper_id": paper_id,
            "expected_title": expected_title,
            "doi": doi,
            "pdf_path": str(pdf_path),
            "manifest_status": manifest_status,
            "source_used": source_used,
            "pdf_url": pdf_url,
            "extracted_title_or_first_text": full_text if full_text else "",
            "title_similarity": 0.0,
            "doi_found_in_pdf": "",
            "audit_status": "unreadable_pdf",
            "reason": f"PDF text extraction failed: {full_text}" if full_text else "Empty or unreadable PDF",
        }

    # Extract DOI from PDF
    found_doi = extract_doi_from_pdf(pdf_path)
    doi_match = doi_matches(doi, found_doi) if (doi and found_doi) else False

    # Compute title similarity using both the extracted title and first few lines of text
    candidates_for_similarity = [title_candidate] + [line.strip() for line in full_text.split("\n")[:5] if len(line.strip()) > 20]
    best_sim, best_candidate = compute_best_title_similarity(expected_title, candidates_for_similarity)

    # Check suspect patterns
    suspect_reason = is_suspect_pdf_title(title_candidate) or is_suspect_pdf_text(full_text)

    # Classify
    if doi_match:
        audit_status = "validated"
        reason = f"DOI {found_doi} found in PDF matches expected DOI {doi}"
    elif suspect_reason and best_sim < TITLE_SIMILARITY_VALIDATED:
        audit_status = "suspect_wrong_document"
        reason = f"{suspect_reason} (title similarity={best_sim:.1f})"
    elif best_sim >= TITLE_SIMILARITY_VALIDATED:
        audit_status = "validated"
        reason = f"Title similarity {best_sim:.1f}% >= {TITLE_SIMILARITY_VALIDATED}% threshold"
    elif suspect_reason:
        audit_status = "suspect_wrong_document"
        reason = f"{suspect_reason} (title similarity={best_sim:.1f})"
    else:
        audit_status = "suspect_title_mismatch"
        reason = f"Title similarity {best_sim:.1f}% below threshold (no suspect keywords found)"

    return {
        "paper_id": paper_id,
        "expected_title": expected_title,
        "doi": doi,
        "pdf_path": str(pdf_path),
        "manifest_status": manifest_status,
        "source_used": source_used,
        "pdf_url": pdf_url,
        "extracted_title_or_first_text": best_candidate if best_candidate else title_candidate,
        "title_similarity": round(best_sim, 1),
        "doi_found_in_pdf": found_doi or "",
        "audit_status": audit_status,
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

AUDIT_REPORT_COLUMNS = [
    "paper_id", "expected_title", "doi", "pdf_path", "manifest_status",
    "source_used", "pdf_url", "extracted_title_or_first_text",
    "title_similarity", "doi_found_in_pdf", "audit_status", "reason",
]

SUSPECT_PDF_COLUMNS = [
    "paper_id", "expected_title", "doi", "pdf_path", "manifest_status",
    "source_used", "pdf_url", "extracted_title_or_first_text",
    "title_similarity", "doi_found_in_pdf", "audit_status", "reason",
]


def load_manifest(path: Path) -> Dict[str, Dict[str, str]]:
    """Load manifest CSV into a dict keyed by paper_id."""
    if not path.exists() or path.stat().st_size == 0:
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {row.get("paper_id", "").strip(): row for row in rows if row.get("paper_id", "").strip()}


def load_eligible_studies(path: Path) -> Dict[str, Dict[str, str]]:
    """Load eligible_studies.csv into a dict keyed by paper_id."""
    if not path.exists() or path.stat().st_size == 0:
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        pid = row.get("paper_id", "").strip()
        if pid:
            out[pid] = {k: row.get(k, "") for k in ["title", "doi", "year"]}
    return out


# ---------------------------------------------------------------------------
# Quarantine
# ---------------------------------------------------------------------------


def quarantine_suspect_pdfs(suspect_rows: List[Dict[str, str]], pdf_dir: Path) -> Path:
    """Move suspect PDFs to data/pdfs_suspect/ and return the directory path."""
    quarantine_dir = pdf_dir.parent / "pdfs_suspect"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    moved_count = 0
    for row in suspect_rows:
        src = Path(row["pdf_path"])
        if src.exists():
            dst = quarantine_dir / src.name
            # Avoid overwriting
            counter = 1
            while dst.exists():
                stem = src.stem
                suffix = src.suffix
                dst = quarantine_dir / f"{stem}_{counter}{suffix}"
                counter += 1
            try:
                os.rename(str(src), str(dst))
                moved_count += 1
                logger.info("Quarantined: %s -> %s", src.name, dst.name)
            except OSError as exc:
                logger.warning("Failed to quarantine %s: %s", src.name, exc)

    return quarantine_dir


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit downloaded PDFs for ReFiNe eligible studies.",
    )
    parser.add_argument("--input", type=Path, default=Path("data/input/eligible_studies.csv"),
                        help="Path to eligible_studies.csv")
    parser.add_argument("--manifest", type=Path, default=Path("data/input/pdf_download_manifest.csv"),
                        help="Path to pdf_download_manifest.csv")
    parser.add_argument("--pdf-dir", type=Path, default=Path("data/pdfs"),
                        help="Directory containing downloaded PDFs")
    parser.add_argument("--out", type=Path, default=Path("data/input/pdf_audit_report.csv"),
                        help="Output path for audit report CSV")
    parser.add_argument("--suspects", type=Path, default=Path("data/input/suspect_pdfs.csv"),
                        help="Output path for suspect PDFs CSV")
    parser.add_argument("--quarantine", action="store_true",
                        help="Move suspect PDFs to data/pdfs_suspect/")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    from typing import Sequence  # noqa: local import for type

    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.input.exists():
        logger.error("Input CSV not found: %s", args.input)
        return 1

    if not args.manifest.exists():
        logger.error("Manifest CSV not found: %s", args.manifest)
        return 1

    # Load data
    eligible = load_eligible_studies(args.input)
    manifest = load_manifest(args.manifest)

    # Build list of PDFs to audit from the manifest (only those with a pdf_path and status indicating download attempt)
    papers_to_audit: List[Tuple[str, str, str, str, str]] = []  # (paper_id, title, doi, pdf_path, source_used, pdf_url)

    for pid, row in sorted(manifest.items()):
        pdf_path_str = row.get("pdf_path", "")
        if not pdf_path_str:
            continue
        status = row.get("status", "")
        # Audit all papers that had a download attempt (including failures where pdf_path was set)
        papers_to_audit.append((
            pid,
            row.get("title", ""),
            row.get("doi", ""),
            pdf_path_str,
            row.get("source_used", ""),
            row.get("pdf_url", ""),
        ))

    # Audit each PDF
    audit_rows: List[Dict[str, str]] = []
    for paper_id, title, doi, pdf_path_str, source_used, pdf_url in papers_to_audit:
        pdf_path = Path(pdf_path_str) if not pdf_path_str.startswith("/") else Path(pdf_path_str)

        # Use eligible_studies title as fallback
        expected_title = title
        if not expected_title and paper_id in eligible:
            expected_title = eligible[paper_id].get("title", "")

        if not expected_title:
            logger.info("[%s] Skipping: no expected title available", paper_id)
            continue

        row = audit_pdf(
            paper_id=paper_id,
            expected_title=expected_title,
            doi=doi,
            pdf_path=pdf_path,
            manifest_status=row.get("status", ""),
            source_used=source_used,
            pdf_url=pdf_url,
        )

        # Override manifest_status from our row lookup
        row["manifest_status"] = row.get("manifest_status", "") or (manifest.get(paper_id, {}).get("status", ""))
        audit_rows.append(row)

    # Write audit report
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_REPORT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in audit_rows:
            writer.writerow(row)

    # Identify suspect PDFs
    suspect_rows = [r for r in audit_rows if r["audit_status"] in ("suspect_title_mismatch", "suspect_wrong_document")]

    # Write suspect PDFs CSV
    args.suspects.parent.mkdir(parents=True, exist_ok=True)
    with args.suspects.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUSPECT_PDF_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in suspect_rows:
            writer.writerow(row)

    # Quarantine if requested
    quarantine_dir = None
    if args.quarantine and suspect_rows:
        quarantine_dir = quarantine_suspect_pdfs(suspect_rows, args.pdf_dir)

    # Print summary
    total_audited = len(audit_rows)
    validated_count = sum(1 for r in audit_rows if r["audit_status"] == "validated")
    suspect_count = len(suspect_rows)
    unreadable_count = sum(1 for r in audit_rows if r["audit_status"] == "unreadable_pdf")
    missing_count = sum(1 for r in audit_rows if r["audit_status"] == "missing_pdf")

    print("\n" + "=" * 70)
    print("PDF Audit Summary")
    print("=" * 70)
    print(f"  Total PDFs audited: {total_audited}")
    print(f"  Validated: {validated_count}")
    print(f"  Suspect (title mismatch): {sum(1 for r in audit_rows if r['audit_status'] == 'suspect_title_mismatch')}")
    print(f"  Suspect (wrong document): {sum(1 for r in audit_rows if r['audit_status'] == 'suspect_wrong_document')}")
    print(f"  Unreadable PDFs: {unreadable_count}")
    print(f"  Missing PDFs: {missing_count}")
    print("-" * 70)

    # Top 20 suspect PDFs (sorted by lowest similarity first)
    sorted_suspects = sorted(suspect_rows, key=lambda r: r["title_similarity"])[:20]
    if sorted_suspects:
        print("\nTop Suspect PDFs:")
        print("-" * 70)
        for i, row in enumerate(sorted_suspects, 1):
            print(f"  {i}. [{row['audit_status']}] {row['paper_id']}")
            print(f"     Expected: {row['expected_title'][:80]}...")
            print(f"     Extracted: {row.get('extracted_title_or_first_text', '')[:80] or '(none)'}")
            print(f"     Title similarity: {row['title_similarity']}%")
            print(f"     Reason: {row['reason']}")
            print()

    # Specific reports for requested paper IDs
    for specific_pid in ["REFINE-0095", "REFINE-0160", "REFINE-0249"]:
        matching = [r for r in audit_rows if r["paper_id"] == specific_pid]
        if matching:
            row = matching[0]
            print(f"\n{specific_pid} Audit Detail:")
            print("-" * 70)
            print(f"  Expected title: {row['expected_title']}")
            print(f"  DOI: {row.get('doi', '')}")
            print(f"  PDF path: {row['pdf_path']}")
            print(f"  Manifest status: {row['manifest_status']}")
            print(f"  Source used: {row['source_used']}")
            print(f"  PDF URL: {row.get('pdf_url', '')}")
            print(f"  Extracted title/text: {row.get('extracted_title_or_first_text', '')[:100]}")
            print(f"  Title similarity: {row['title_similarity']}%")
            print(f"  DOI found in PDF: {row.get('doi_found_in_pdf', '')}")
            print(f"  Audit status: {row['audit_status']}")
            print(f"  Reason: {row['reason']}")

    if quarantine_dir:
        print(f"\nQuarantined suspect PDFs to: {quarantine_dir}")

    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())