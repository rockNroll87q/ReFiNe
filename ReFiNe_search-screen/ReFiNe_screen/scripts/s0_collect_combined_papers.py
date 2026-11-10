#!/usr/bin/env python3
"""s0 (combined set): build runs/<run>/papers.csv for the original combined evaluation.

Selection rule (deterministic, unchanged from collect_combined_papers.py):
  1. "all_three": papers whose DOI is in ALL of the search CSV (abstracts), the
     human CSV (scores) and ReFiNe_Hub/data/input/eligible_studies.csv;
  2. "extra": papers in search + human CSV but NOT in eligible, in human-CSV
     file order, first N unique DOIs (default 100).

NOTE: this set is enriched for human-eligible papers (all_three = papers the
humans passed), so precision/specificity estimated on it do not transfer to the
full search output. For a representative evaluation use s0b_build_test_set.py.

Paper IDs come from the shared registry (cache/paper_ids.csv), so a DOI keeps
the same REFINE id in every run.

Output columns: paper_id,title,doi,journal,year,abstract,group

Usage: python3 scripts/s0_collect_combined_papers.py [--run combined_400] [--n-extra 100] [--max-papers N]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (HUB_ELIGIBLE_CSV, SCREENED_CSV, add_run_arg, assign_paper_ids, human_row_doi,  # noqa: E402
                    load_search_rows, norm_doi, run_paths, write_csv)

COLUMNS = ["paper_id", "title", "doi", "journal", "year", "abstract", "group"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--n-extra", type=int, default=100)
    ap.add_argument("--max-papers", type=int, default=None,
                    help="cap TOTAL rows; n_extra is trimmed so all_three + extra <= max_papers")
    args = ap.parse_args()
    rp = run_paths(args.run)

    search = load_search_rows()
    screened_order: list[str] = []
    seen: set[str] = set()
    with open(SCREENED_CSV, encoding="latin-1", newline="") as fh:
        for r in csv.DictReader(fh):
            d = human_row_doi(r)
            if d and d not in seen:
                seen.add(d)
                screened_order.append(d)
    eligible: set[str] = set()
    with open(HUB_ELIGIBLE_CSV, encoding="utf-8", newline="") as fh:
        eligible = {norm_doi(r.get("doi")) for r in csv.DictReader(fh)} - {""}

    all_three = [d for d in screened_order if d in search and d in eligible]
    extra_pool = [d for d in screened_order if d in search and d not in eligible]
    n_extra = args.n_extra
    if args.max_papers is not None:
        n_extra = min(n_extra, max(0, args.max_papers - len(all_three)))
    extra = extra_pool[:n_extra]

    ids = assign_paper_ids(all_three + extra)
    rows = [{"paper_id": ids[d], "doi": d, "group": grp, **search[d]}
            for grp, dois in (("all_three", all_three), ("extra", extra)) for d in dois]
    write_csv(rp.papers, rows, COLUMNS)

    print(f"search unique DOIs:   {len(search)}")
    print(f"human unique DOIs:    {len(seen)}")
    print(f"all_three: {len(all_three)}   extra: {len(extra)} (pool {len(extra_pool)})")
    print(f"-> {rp.papers.relative_to(rp.dir.parent.parent)}  ({len(rows)} papers; "
          f"{sum(1 for r in rows if len(r['abstract']) >= 50)} with abstract >= 50 chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
