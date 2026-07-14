#!/usr/bin/env python3
"""
Import PDFs from a local Zotero library into the ReFiNe PDF directory.

The script:
1. Reads DOI metadata and PDF attachment paths from Zotero's SQLite database.
2. Scans ReFiNe CSV files for REFINE-XXXX <-> DOI mappings.
3. Copies matching PDFs to data/pdfs/REFINE-XXXX.pdf.
4. Writes a CSV report describing copied, existing, invalid, and missing files.

It never writes to the Zotero database.

Usage:
    $ python import_zotero_pdfs.py [options]

"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

DEFAULT_ZOTERO_STORAGE = Path("/Users/micheles/Zotero/storage")
DEFAULT_PROJECT_ROOT = Path(
    "/Users/micheles/Desktop/Temp/sshfs_2/home/micheles/Desktop/"
    "Vigilate/agent_yoda/workspaces/ReFiNe/ReFiNe_Hub"
)
DEFAULT_TARGET_DIR = DEFAULT_PROJECT_ROOT / "data" / "pdfs"
DEFAULT_INPUT_DIR = DEFAULT_PROJECT_ROOT / "data" / "input"
DEFAULT_REPORT = DEFAULT_INPUT_DIR / "zotero_import_report.csv"

REFINE_RE = re.compile(r"\bREFINE-\d+\b", re.IGNORECASE)
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)


@dataclass(frozen=True)
class RefineRecord:
    refine_id: str
    doi: str
    source_csv: Path


@dataclass(frozen=True)
class ZoteroPDF:
    doi: str
    path: Path
    attachment_key: str


def normalize_refine_id(value: str) -> str | None:
    match = REFINE_RE.search(value or "")
    return match.group(0).upper() if match else None


def normalize_doi(value: str) -> str | None:
    if not value:
        return None

    text = unquote(str(value)).strip()
    text = re.sub(
        r"^\s*(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)",
        "",
        text,
        flags=re.IGNORECASE,
    )

    match = DOI_RE.search(text)
    if not match:
        return None

    doi = match.group(0).strip().lower()

    # Remove punctuation that is commonly part of prose/CSV formatting,
    # while retaining parentheses because they can legitimately occur in DOIs.
    doi = doi.rstrip(".,;:'\"")
    return doi or None


def is_valid_pdf(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size < 100:
            return False
        with path.open("rb") as handle:
            return b"%PDF-" in handle.read(1024)
    except OSError:
        return False


def discover_refine_records(input_dir: Path) -> list[RefineRecord]:
    """
    Search every CSV row for a REFINE ID and a DOI.

    This intentionally does not require fixed column names, making the script
    compatible with eligible_studies.csv, manual_pdf_needed.csv, and the
    download manifest.
    """
    records: dict[tuple[str, str], RefineRecord] = {}

    for csv_path in sorted(input_dir.rglob("*.csv")):
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                for row in reader:
                    values = [str(cell).strip() for cell in row if cell is not None]
                    refine_id = next(
                        (rid for cell in values if (rid := normalize_refine_id(cell))),
                        None,
                    )
                    doi = next(
                        (doi for cell in values if (doi := normalize_doi(cell))),
                        None,
                    )
                    if refine_id and doi:
                        records.setdefault(
                            (refine_id, doi),
                            RefineRecord(refine_id, doi, csv_path),
                        )
        except (OSError, UnicodeError, csv.Error) as exc:
            print(f"Warning: could not read {csv_path}: {exc}", file=sys.stderr)

    return sorted(records.values(), key=lambda r: (r.refine_id, r.doi))


def query_zotero_pdfs(zotero_db: Path, storage_dir: Path) -> list[ZoteroPDF]:
    """
    Read Zotero attachment metadata without modifying the database.

    Zotero stores an attachment in:
        <storage>/<attachment item key>/<filename from storage:... path>
    """
    uri = f"{zotero_db.resolve().as_uri()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=5)
    connection.row_factory = sqlite3.Row

    sql = """
        SELECT
            idv.value AS doi,
            attachment_item.key AS attachment_key,
            ia.path AS attachment_path
        FROM itemAttachments AS ia
        JOIN items AS attachment_item
            ON attachment_item.itemID = ia.itemID
        JOIN itemData AS metadata
            ON metadata.itemID = ia.parentItemID
        JOIN fieldsCombined AS field
            ON field.fieldID = metadata.fieldID
        JOIN itemDataValues AS idv
            ON idv.valueID = metadata.valueID
        WHERE LOWER(field.fieldName) = 'doi'
          AND ia.parentItemID IS NOT NULL
          AND ia.path IS NOT NULL
          AND ia.path LIKE 'storage:%'
          AND (
                LOWER(COALESCE(ia.contentType, '')) = 'application/pdf'
                OR LOWER(ia.path) LIKE '%.pdf'
              )
    """

    try:
        rows = connection.execute(sql).fetchall()
    finally:
        connection.close()

    results: list[ZoteroPDF] = []
    for row in rows:
        doi = normalize_doi(row["doi"])
        stored_path = row["attachment_path"]
        key = row["attachment_key"]
        if not doi or not stored_path or not key:
            continue

        relative_name = stored_path.removeprefix("storage:")
        pdf_path = storage_dir / key / relative_name
        results.append(ZoteroPDF(doi=doi, path=pdf_path, attachment_key=key))

    return results


def select_best_pdf(candidates: Iterable[ZoteroPDF]) -> tuple[ZoteroPDF | None, str]:
    existing = [candidate for candidate in candidates if candidate.path.is_file()]
    valid = [candidate for candidate in existing if is_valid_pdf(candidate.path)]

    if valid:
        # Prefer the largest valid file if Zotero has multiple attachments.
        best = max(valid, key=lambda item: item.path.stat().st_size)
        note = "multiple_valid_pdfs" if len(valid) > 1 else ""
        return best, note

    if existing:
        return max(existing, key=lambda item: item.path.stat().st_size), "invalid_pdf"

    return None, "zotero_attachment_missing"


def write_report(report_path: Path, rows: list[dict[str, str]]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "refine_id",
        "doi",
        "status",
        "source_pdf",
        "target_pdf",
        "bytes",
        "mapping_source_csv",
        "note",
    ]
    with report_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def import_pdfs(
    records: list[RefineRecord],
    zotero_pdfs: list[ZoteroPDF],
    target_dir: Path,
    report_path: Path,
    *,
    dry_run: bool,
    overwrite: bool,
) -> int:
    by_doi: dict[str, list[ZoteroPDF]] = defaultdict(list)
    for attachment in zotero_pdfs:
        by_doi[attachment.doi].append(attachment)

    target_dir.mkdir(parents=True, exist_ok=True)
    report_rows: list[dict[str, str]] = []
    counts: dict[str, int] = defaultdict(int)

    for record in records:
        target_pdf = target_dir / f"{record.refine_id}.pdf"
        selected, note = select_best_pdf(by_doi.get(record.doi, []))

        source_pdf = ""
        size = ""

        if target_pdf.exists() and not overwrite:
            status = "already_exists"
        elif selected is None:
            status = "not_found_in_zotero"
        elif note == "invalid_pdf":
            status = "invalid_source_pdf"
            source_pdf = str(selected.path)
            try:
                size = str(selected.path.stat().st_size)
            except OSError:
                pass
        else:
            source_pdf = str(selected.path)
            size = str(selected.path.stat().st_size)
            status = "would_copy" if dry_run else "copied"
            if not dry_run:
                shutil.copy2(selected.path, target_pdf)

        counts[status] += 1
        report_rows.append(
            {
                "refine_id": record.refine_id,
                "doi": record.doi,
                "status": status,
                "source_pdf": source_pdf,
                "target_pdf": str(target_pdf),
                "bytes": size,
                "mapping_source_csv": str(record.source_csv),
                "note": note,
            }
        )

    write_report(report_path, report_rows)

    print("\nImport summary")
    print("--------------")
    print(f"ReFiNe DOI records:     {len(records)}")
    print(f"Zotero PDF attachments: {len(zotero_pdfs)}")
    for status in sorted(counts):
        print(f"{status:24s} {counts[status]}")
    print(f"\nReport: {report_path}")
    print(f"Target: {target_dir}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy Zotero PDFs into ReFiNe data/pdfs using DOI matching."
    )
    parser.add_argument(
        "--zotero-storage",
        type=Path,
        default=DEFAULT_ZOTERO_STORAGE,
        help=f"Zotero storage directory (default: {DEFAULT_ZOTERO_STORAGE})",
    )
    parser.add_argument(
        "--zotero-db",
        type=Path,
        default=None,
        help="Path to zotero.sqlite. Defaults to the parent of --zotero-storage.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        help=f"Directory containing ReFiNe CSV files (default: {DEFAULT_INPUT_DIR})",
    )
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=DEFAULT_TARGET_DIR,
        help=f"Destination PDF directory (default: {DEFAULT_TARGET_DIR})",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"CSV report path (default: {DEFAULT_REPORT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be copied without copying files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing REFINE-XXXX.pdf file.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    storage_dir = args.zotero_storage.expanduser().resolve()
    zotero_db = (
        args.zotero_db.expanduser().resolve()
        if args.zotero_db
        else storage_dir.parent / "zotero.sqlite"
    )
    input_dir = args.input_dir.expanduser().resolve()
    target_dir = args.target_dir.expanduser().resolve()
    report_path = args.report.expanduser().resolve()

    missing = [
        str(path)
        for path in (storage_dir, zotero_db, input_dir)
        if not path.exists()
    ]
    if missing:
        print("Error: required path(s) not found:", file=sys.stderr)
        for path in missing:
            print(f"  - {path}", file=sys.stderr)
        return 2

    wal_path = zotero_db.with_name(zotero_db.name + "-wal")
    if wal_path.exists():
        print(
            "Warning: Zotero appears to be open. Close Zotero before importing "
            "to ensure the database and attachments are fully up to date.",
            file=sys.stderr,
        )

    records = discover_refine_records(input_dir)
    if not records:
        print(
            f"Error: no REFINE-XXXX and DOI pairs were found in {input_dir}",
            file=sys.stderr,
        )
        return 3

    try:
        zotero_pdfs = query_zotero_pdfs(zotero_db, storage_dir)
    except sqlite3.Error as exc:
        print(f"Error reading Zotero database: {exc}", file=sys.stderr)
        print("Close Zotero and try again.", file=sys.stderr)
        return 4

    return import_pdfs(
        records,
        zotero_pdfs,
        target_dir,
        report_path,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
    )


if __name__ == "__main__":
    raise SystemExit(main())
