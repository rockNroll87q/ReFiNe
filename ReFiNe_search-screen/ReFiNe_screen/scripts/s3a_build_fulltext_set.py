#!/usr/bin/env python3
"""s3a: build runs/<run>/eval_set.jsonl — the papers rateable at full text.

A paper enters the full-text set when it has a PDF in cache/pdf/<paper_id>.pdf
and a scored row in the human CSV (matched by DOI). Scope:
  --scope run   (default) papers listed in runs/<run>/papers.csv
  --scope all   every cached PDF (previous behaviour of build_combined_eval_set.py;
                includes Hub PDFs of papers outside this run)
Add --group dev|test to restrict a run built with s0b to one split.

Each record: paper_id, doi, title, pdf_path, human {criterion: '1'|'0'|'n/a'|None},
n_csv_rows_for_doi. Unmatched PDFs are listed in eval_set_unmatched.txt.
Idempotent: re-run whenever more PDFs arrive.

Usage: python3 scripts/s3a_build_fulltext_set.py [--run combined_400] [--scope run|all] [--group dev]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (HUB_MANIFEST_CSV, PDF_DIR, ROOT, path_str, SCREENED_CSV, add_run_arg, human_row_doi,  # noqa: E402
                    human_row_status, load_config, load_id_registry, norm_cell, norm_doi, read_papers,
                    run_paths)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--scope", choices=("run", "all"), default="run")
    ap.add_argument("--group", default=None)
    args = ap.parse_args()
    rp = run_paths(args.run)
    criteria = load_config()["criteria"]

    # paper_id -> (doi, title): this run first, then registry / Hub manifest for other cached PDFs
    meta: dict[str, tuple[str, str]] = {}
    run_ids: set[str] = set()
    if rp.papers.exists():
        for r in read_papers(rp.papers):
            if args.group and r.get("group") != args.group:
                continue
            meta[r["paper_id"]] = (norm_doi(r.get("doi")), r.get("title", ""))
            run_ids.add(r["paper_id"])
    elif args.scope == "run":
        print(f"[error] {rp.papers} not found")
        return 1
    if args.scope == "all":
        for d, pid in load_id_registry().items():
            meta.setdefault(pid, (d, ""))
        if HUB_MANIFEST_CSV.exists():
            with open(HUB_MANIFEST_CSV, newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    pid = (r.get("paper_id") or "").strip()
                    if pid and (pid not in meta or not meta[pid][1]):
                        meta[pid] = (norm_doi(r.get("doi")) or meta.get(pid, ("", ""))[0], r.get("title", ""))

    # human CSV: DOI -> list of scored rows (duplicates kept to report label noise)
    with open(SCREENED_CSV, newline="", encoding="latin-1") as fh:
        reader = csv.DictReader(fh)
        missing = [c["source_column"] for c in criteria if c["source_column"] not in (reader.fieldnames or [])]
        if missing:
            print(f"[error] criterion columns not in human CSV: {missing}")
            return 1
        by_doi: dict[str, list[dict]] = {}
        for row in reader:
            if human_row_status(row) != "screened":
                continue
            d = human_row_doi(row)
            if d:
                by_doi.setdefault(d, []).append({c["id"]: norm_cell(row.get(c["source_column"])) for c in criteria})

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    if args.scope == "run":
        pdfs = [p for p in pdfs if p.stem in run_ids]
    records, unmatched = [], []
    for pdf in pdfs:
        doi, title = meta.get(pdf.stem, ("", ""))
        rows = by_doi.get(doi, []) if doi else []
        if not rows:
            unmatched.append(f"{pdf.stem}\t{doi or '(no DOI known)'}\tno scored human row")
            continue
        records.append({"paper_id": pdf.stem, "doi": doi, "title": title,
                        "pdf_path": path_str(pdf), "human": rows[0],
                        "n_csv_rows_for_doi": len(rows)})

    rp.dir.mkdir(parents=True, exist_ok=True)
    rp.eval_set.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    unmatched_path = rp.dir / "eval_set_unmatched.txt"
    unmatched_path.write_text("\n".join(unmatched) + ("\n" if unmatched else ""), encoding="utf-8")

    print(f"PDFs considered: {len(pdfs)} (scope={args.scope}{', group=' + args.group if args.group else ''})")
    print(f"-> {rp.eval_set}: {len(records)} papers with human scores; unmatched: {len(unmatched)}")
    print(f"papers with duplicate human rows (label-noise caveat): {sum(r['n_csv_rows_for_doi'] > 1 for r in records)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())