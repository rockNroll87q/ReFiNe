"""PDF-to-text conversion layer for ReFiNe.

Uses **Docling only** to convert PDFs to Markdown-like text.

No fallbacks to pypdf or PyMuPDF.

If Docling is not installed or conversion fails, the caller receives an
error message string (prefixed with ``ERROR: ``) and should set
``extraction_status`` to ``"failed"`` accordingly.

Output path convention: ``data/text/<paper_id>.md``
"""

from pathlib import Path


class Console:
    def print(self, *args, **kwargs):
        print(*args)


console = Console()


# ---------------------------------------------------------------------------
# Docling-only converter
# ---------------------------------------------------------------------------

def convert_with_docling(pdf_path: Path) -> str:
    """Convert a PDF to Markdown using Docling.

    Returns the Markdown string on success.
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
# Public API
# ---------------------------------------------------------------------------

def pdf_to_text(pdf_path: Path, output_path: Path | None = None) -> str:
    """Convert *pdf_path* to Markdown using Docling only.

    If *output_path* is given the resulting text is written there as
    well (UTF-8, ``.md`` extension).

    Returns the extracted Markdown string on success.

    Raises ``RuntimeError`` when Docling is unavailable or conversion fails.
    The caller should catch this and set ``extraction_status`` to ``"failed"``.
    """
    text = convert_with_docling(pdf_path)

    console.print(
        f"PDF-to-text: {pdf_path.name} "
        f"(using docling, {len(text)} chars)"
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
        console.print(f"Saved text: {output_path}")

    return text