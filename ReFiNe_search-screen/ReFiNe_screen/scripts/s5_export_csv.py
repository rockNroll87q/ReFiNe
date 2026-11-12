#!/usr/bin/env python3
"""s5: write LLM full-text ratings in the exact layout of data/input/screened_studies_full.csv.

Reads runs/<run>/fulltext/<paper_id>.json, maps each rated criterion to its
human-CSV header via config/criteria.yaml, joins to the human rows by DOI and
writes (into runs/<run>/reports/):

  <base>.csv          the input's columns with LLM values in place (latin-1,
                      same formatting as the input). Paper/link and non-rated
                      columns (duplicate, corrupted, instrument) are copied from
                      the human row.
  <base>_detail.csv   same rows, each rated criterion expanded to
                      "<criterion> score", "... score confidence", "... evidence"
                      (UTF-8 with BOM: evidence text is not latin-1 safe).

Modes:
  --paper REFINE-XXXX   one row  -> <paper>_llm.csv
  --all                 one row per ok artifact, in input-CSV order -> screened_studies_llm.csv
                        (a DOI on several input rows keeps its first row only)

Usage: python3 scripts/s5_export_csv.py [--run combined_400] (--paper REFINE-XXXX | --all) [--out PATH]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import SCREENED_CSV, add_run_arg, load_config, norm_doi, run_paths  # noqa: E402


def id_to_column() -> dict[str, str]:
    return {c["id"]: c["source_column"] for c in load_config()["criteria"]}


def llm_values(rating: dict, id2col: dict[str, str]) -> dict[str, str]:
    """Rated criterion's CSV header -> LLM value; raises if a criterion is missing."""
    values = {}
    for cid, col in id2col.items():
        if cid not in rating.get("criteria", {}):
            raise ValueError(f"artifact {rating.get('paper_id')!r} is missing criterion '{cid}'")
        values[col] = rating["criteria"][cid]["value"]
    return values


def build_row(header: list[str], human: list[str], vals: dict[str, str]) -> list[str]:
    return [human[i] if i < 2 or col not in vals else vals[col] for i, col in enumerate(header)]


def build_detail_row(header: list[str], human: list[str], rating: dict, id2col: dict[str, str]) -> list[str]:
    col2crit = {col: cid for cid, col in id2col.items()}
    out = []
    for i, col in enumerate(header):
        if i < 2 or col not in col2crit:
            out.append(human[i])
            continue
        c = rating["criteria"][col2crit[col]]
        out.extend([c["value"], str(float(c.get("confidence", 0.0))), c.get("evidence", "")])
    return out


def detail_header(header: list[str], id2col: dict[str, str]) -> list[str]:
    col2name = {col: cid.replace("_", " ") for cid, col in id2col.items()}
    out = []
    for i, col in enumerate(header):
        if i < 2 or col not in col2name:
            out.append(col)
        else:
            n = col2name[col]
            out.extend([f"{n} score", f"{n} score confidence", f"{n} evidence"])
    return out


def write_pair(out: Path, header, rows, details, id2col) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="latin-1", errors="replace") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    detail_out = out.with_name(out.stem + "_detail.csv")
    with detail_out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(detail_header(header, id2col))
        w.writerows(details)
    print(f"wrote {out}\nwrote {detail_out}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--paper", help="single paper id")
    g.add_argument("--all", action="store_true", help="one row per ok ratings artifact")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    rp = run_paths(args.run)
    id2col = id_to_column()

    with SCREENED_CSV.open(newline="", encoding="latin-1") as f:
        reader = csv.reader(f)
        header = next(reader)
        human_rows = [r for r in reader if len(r) == len(header)]

    if args.paper:
        path = rp.fulltext_dir / f"{args.paper}.json"
        if not path.exists():
            print(f"[error] no ratings artifact: {path}")
            return 1
        rating = json.loads(path.read_text(encoding="utf-8"))
        matches = [r for r in human_rows if norm_doi(r[1]) == norm_doi(rating["doi"])]
        if not matches:
            print(f"[error] no human CSV row with DOI {rating['doi']}")
            return 1
        vals = llm_values(rating, id2col)
        write_pair(args.out or rp.reports_dir / f"{args.paper}_llm.csv", header,
                   [build_row(header, matches[0], vals)], [build_detail_row(header, matches[0], rating, id2col)], id2col)
        return 0

    by_doi: dict[str, tuple[str, dict]] = {}
    for p in sorted(rp.fulltext_dir.glob("*.json")):
        a = json.loads(p.read_text(encoding="utf-8"))
        if a.get("status") == "ok":
            by_doi.setdefault(norm_doi(a.get("doi")), (p.stem, a))
    rows, details, used = [], [], set()
    for human in human_rows:
        entry = by_doi.get(norm_doi(human[1]))
        if entry is None or entry[0] in used:
            continue
        used.add(entry[0])
        try:
            vals = llm_values(entry[1], id2col)
        except ValueError as e:
            print(f"skipping: {e}")
            continue
        rows.append(build_row(header, human, vals))
        details.append(build_detail_row(header, human, entry[1], id2col))
    write_pair(args.out or rp.reports_dir / "screened_studies_llm.csv", header, rows, details, id2col)
    print(f"{len(rows)} of {len(by_doi)} rated papers, in input-CSV order")
    return 0


if __name__ == "__main__":
    sys.exit(main())
