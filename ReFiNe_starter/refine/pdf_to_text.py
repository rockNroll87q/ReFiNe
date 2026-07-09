"""PDF-to-text conversion layer for ReFiNe.

Uses **Docling** as the primary converter with automatic fallback to pypdf
and pdfplumber when Docling fails (e.g., scanned PDFs, corrupted files).

Retry logic with exponential back-off is applied before falling through
to alternative parsers.

Output path convention: ``data/text/<paper_id>.md``
"""

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

    Returns (success, result_or_error).
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            return True, func(*args, **kwargs)
        except Exception as exc:
            last_err = exc
            if attempt < max_retries - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                logger.warning(
                    "Conversion failed (attempt %d/%d): %s. Retrying in %.1fs...",
                    attempt + 1, max_retries, exc, delay,
                )
                time.sleep(delay)
    return False, last_err


# ---------------------------------------------------------------------------
# Docling converter
# ---------------------------------------------------------------------------

def _convert_with_docling(pdf_path: Path) -> str:
    """Convert a PDF to Markdown using Docling.

    Raises ``RuntimeError`` if Docling is not installed or conversion fails.
    """
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        raise RuntimeError(
            "Docling is not installed. Install it with: pip install docling"
        )

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    markdown_text = result.document.export_to_markdown()
    return markdown_text


# ---------------------------------------------------------------------------
# Fallback parser 1: pypdf (lightweight, no OCR)
# ---------------------------------------------------------------------------

def _convert_with_pypdf(pdf_path: Path) -> str:
    """Convert a PDF to text using pypdf as a fallback parser.

    This is a lightweight option that extracts text from non-scanned PDFs.
    Returns the extracted text (may be empty for scanned/image-based PDFs).
    """
    try:
        import pypdf
    except ImportError:
        raise RuntimeError(
            "pypdf is not installed. Install it with: pip install pypdf"
        )

    reader = pypdf.PdfReader(str(pdf_path))
    texts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            texts.append(text)

    result = "\n\n--- PAGE BREAK ---\n\n".join(texts)
    return result


# ---------------------------------------------------------------------------
# Fallback parser 2: pdfplumber (better layout preservation)
# ---------------------------------------------------------------------------

def _convert_with_pdfplumber(pdf_path: Path) -> str:
    """Convert a PDF to text using pdfplumber as a fallback parser.

    This preserves more layout information than pypdf for tables and
    structured content. Returns the extracted text.
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError(
            "pdfplumber is not installed. Install it with: pip install pdfplumber"
        )

    texts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text)

    result = "\n\n--- PAGE BREAK ---\n\n".join(texts)
    return result


# ---------------------------------------------------------------------------
# Fallback parser 3: PyMuPDF (fitz) - best OCR-like extraction without OCR
# ---------------------------------------------------------------------------

def _convert_with_pymupdf(pdf_path: Path) -> str:
    """Convert a PDF to text using PyMuPDF (fitz) as a fallback parser.

    PyMuPDF often handles complex PDF layouts better than other libraries.
    Returns the extracted text.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise RuntimeError(
            "PyMuPDF is not installed. Install it with: pip install pymupdf"
        )

    doc = fitz.open(str(pdf_path))
    texts = []
    for page in doc:
        text = page.get_text("text")
        if text:
            texts.append(text)
    doc.close()

    result = "\n\n--- PAGE BREAK ---\n\n".join(texts)
    return result


# ---------------------------------------------------------------------------
# Converter pipeline
# ---------------------------------------------------------------------------

CONVERTERS = [
    ("docling", _convert_with_docling),
    ("pymupdf", _convert_with_pymupdf),
    ("pdfplumber", _convert_with_pdfplumber),
    ("pypdf", _convert_with_pypdf),
]


def convert_pdf(pdf_path: Path) -> tuple[bool, str]:
    """Convert a PDF to text using the best available converter.

    Tries each converter in order until one succeeds:
        1. Docling (with retries)
        2. PyMuPDF (fallback)
        3. pdfplumber (fallback)
        4. pypdf (fallback)

    Returns (success, text_or_error_message).
    On success, *text* is a non-empty string of extracted text.
    On failure, *text* starts with "ERROR: " and describes the problem.
    """
    if not pdf_path.exists():
        return False, f"ERROR: PDF file not found: {pdf_path}"

    # Check file size
    file_size = pdf_path.stat().st_size
    if file_size == 0:
        return False, "ERROR: PDF file is empty (0 bytes)"

    logger.info("Converting PDF: %s (%d bytes)", pdf_path.name, file_size)

    for name, converter in CONVERTERS:
        logger.info("Trying converter: %s", name)
        success, result = _retry_with_backoff(converter, pdf_path)
        if success:
            # Validate output quality
            if isinstance(result, str) and len(result.strip()) > 10:
                logger.info("Converter '%s' succeeded (%d chars)", name, len(result))
                return True, result
            elif isinstance(result, str) and len(result.strip()) <= 10:
                logger.warning(
                    "Converter '%s' returned very little text (%d chars). Trying next...",
                    name, len(result),
                )
                continue
            else:
                # Non-string result (e.g., None or other)
                logger.warning("Converter '%s' returned non-string. Trying next...", name)
                continue

        if isinstance(result, Exception):
            logger.warning(
                "Converter '%s' failed: %s", name, str(result)
            )
        else:
            logger.warning("Converter '%s' returned invalid result type.", name)

    # All converters exhausted
    return False, f"ERROR: All PDF converters failed. Tried: {[c[0] for c in CONVERTERS]}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pdf_to_text(pdf_path: Path, output_path: Path | None = None) -> str:
    """Convert *pdf_path* to text using the best available converter.

    If *output_path* is given the resulting text is written there as
    well (UTF-8, ``.md`` extension).

    Returns the extracted text on success.

    Raises ``RuntimeError`` when all converters fail.
    The caller should catch this and set ``extraction_status`` to ``"failed"``.
    """
    success, result = convert_pdf(pdf_path)

    if not success:
        error_msg = result  # Already starts with "ERROR: "
        raise RuntimeError(error_msg)

    text = result

    logger.info(
        "PDF-to-text: %s (%d chars)",
        pdf_path.name, len(text),
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        logger.info("Saved text: %s", output_path)

    return text
