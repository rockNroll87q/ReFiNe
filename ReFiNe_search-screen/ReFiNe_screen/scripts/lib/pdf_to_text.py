"""PDF-to-text conversion layer for ReFiNe_screen.

Adapted from ReFiNe_Hub/refine/pdf_to_text.py with one efficiency fix: the
Docling converter is expensive to instantiate (model loading), so it is now a
lazy module-level singleton instead of being rebuilt per file — important when
converting hundreds of PDFs in one run. Swap-in point for the coworker's
converter: replace/add an entry in CONVERTERS keeping the same
``(name, fn(Path) -> str)`` contract.

Output path convention: data/text/<paper_id>.md
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2.0  # seconds; exponential back-off


def _retry_with_backoff(func, *args, max_retries: int = MAX_RETRIES, **kwargs):
    """Call *func* with retry and exponential back-off.

    Returns (success, result_or_error_message). Errors indicating a missing
    library ("... is not installed") are permanent — they fail fast without
    sleeping through the remaining retries.
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            return True, func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 — any converter failure falls through to the next parser
            last_err = str(exc)
            if "is not installed" in last_err or attempt == max_retries - 1:
                break
            delay = RETRY_DELAY_BASE * (2**attempt)
            logger.warning("Conversion failed (attempt %d/%d): %s. Retrying in %.1fs...",
                           attempt + 1, max_retries, exc, delay)
            time.sleep(delay)
    return False, last_err


# ---------------------------------------------------------------------------
# Converter implementations
# ---------------------------------------------------------------------------

_docling_converter = None  # lazy singleton — Docling model loading is slow


def _convert_with_docling(pdf_path: Path) -> str:
    """Convert a PDF to Markdown using Docling (best layout handling)."""
    global _docling_converter
    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise RuntimeError("Docling is not installed. Install it with: pip install docling") from exc

    if _docling_converter is None:
        logger.info("Instantiating Docling converter (one-time model load)...")
        _docling_converter = DocumentConverter()
    result = _docling_converter.convert(str(pdf_path))
    return result.document.export_to_markdown()


def _convert_with_pymupdf(pdf_path: Path) -> str:
    """Convert a PDF to text using PyMuPDF (fast, no OCR)."""
    try:
        import pymupdf  # `import fitz` is deprecated in recent versions
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is not installed. Install it with: pip install pymupdf") from exc

    doc = pymupdf.open(str(pdf_path))
    try:
        texts = [page.get_text("text") for page in doc]
    finally:
        doc.close()
    return "\n\n--- PAGE BREAK ---\n\n".join(t for t in texts if t)


def _convert_with_pdfplumber(pdf_path: Path) -> str:
    """Convert a PDF to text using pdfplumber (better layout preservation)."""
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is not installed. Install it with: pip install pdfplumber") from exc

    texts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if text:
                texts.append(text)
    return "\n\n--- PAGE BREAK ---\n\n".join(texts)


def _convert_with_pypdf(pdf_path: Path) -> str:
    """Convert a PDF to text using pypdf (lightweight, no OCR)."""
    try:
        import pypdf
    except ImportError as exc:
        raise RuntimeError("pypdf is not installed. Install it with: pip install pypdf") from exc

    reader = pypdf.PdfReader(str(pdf_path))
    texts = [page.extract_text() or "" for page in reader.pages]
    return "\n\n--- PAGE BREAK ---\n\n".join(t for t in texts if t)


CONVERTERS = [
    ("docling", _convert_with_docling),
    ("pymupdf", _convert_with_pymupdf),
    ("pdfplumber", _convert_with_pdfplumber),
    ("pypdf", _convert_with_pypdf),
]

_UNAVAILABLE_CONVERTERS: set[str] = set()  # names whose library is missing in this environment


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_pdf(pdf_path: Path) -> tuple[bool, str]:
    """Convert a PDF to text using the best available converter.

    Tries each converter in CONVERTERS order until one succeeds and returns
    non-trivial output (>10 chars). Returns (success, text_or_error_message);
    on failure the message starts with "ERROR: ". Converters whose library is
    missing are remembered in _UNAVAILABLE_CONVERTERS and skipped from then on.
    """
    if not pdf_path.exists():
        return False, f"ERROR: PDF file not found: {pdf_path}"
    if pdf_path.stat().st_size == 0:
        return False, "ERROR: PDF file is empty (0 bytes)"

    logger.info("Converting PDF: %s (%d bytes)", pdf_path.name, pdf_path.stat().st_size)

    for name, converter in CONVERTERS:
        if name in _UNAVAILABLE_CONVERTERS:
            continue
        logger.info("Trying converter: %s", name)
        success, result = _retry_with_backoff(converter, pdf_path)
        if not success and "is not installed" in (result or ""):
            _UNAVAILABLE_CONVERTERS.add(name)  # don't pay the import check again per file
        if success and isinstance(result, str):
            if len(result.strip()) > 10:
                logger.info("Converter '%s' succeeded (%d chars)", name, len(result))
                return True, result
            logger.warning("Converter '%s' returned very little text (%d chars). Trying next...",
                           name, len(result.strip()))
        else:
            logger.warning("Converter '%s' failed: %s", name, result)

    return False, f"ERROR: All PDF converters failed. Tried: {[c[0] for c in CONVERTERS]}"


def pdf_to_text(pdf_path: Path, output_path: Path | None = None) -> str:
    """Convert *pdf_path* to text; optionally write it to *output_path*.

    Raises RuntimeError when all converters fail.
    """
    success, result = convert_pdf(pdf_path)
    if not success:
        raise RuntimeError(result)  # already starts with "ERROR: "
    logger.info("PDF-to-text: %s (%d chars)", pdf_path.name, len(result))
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        logger.info("Saved text: %s", output_path)
    return result

