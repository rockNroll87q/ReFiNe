#!/usr/bin/env python3
"""s0c: balanced end-to-end evaluation set — the pilot's included studies + an equal number of rejected ones.

  positives  every paper in ReFiNe_Hub/data/input/eligible_studies.csv (the pilot's final
             inclusion list) that has BOTH a usable abstract in the search CSV AND a scored
             row in the human CSV (screened_studies_full.csv)
  negatives  a random sample, of the same size, of papers with BOTH a usable abstract and a
             scored human row that are NOT in eligible_studies (fixed seed)

"Scored human row" = not flagged duplicate/corrupted and depression column filled in
(never-screened rows are excluded). Both halves therefore have human criterion scores
(for per-criterion full-text comparison) and an abstract (for abstract screening).

Papers used to develop prompts (default: the dev split of runs/abstract_v2) are excluded
from BOTH halves, so this set is held out from prompt development.

Each row gets reference = 1 (eligible) / 0 (not), and group = eligible / not_eligible.

Interpretation: with a 50/50 design, sensitivity and specificity are valid; precision,
NPV and workload are NOT representative of a real search (prevalence is ~15% there, not
50%). s4c_report_pipeline.py reports both and labels this.

Usage:
  python3 scripts/s0c_build_eligible_set.py --run e2e_v4 [--ratio 1.0] [--seed 20261105]
      [--exclude-run abstract_v2 --exclude-group dev]
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (DEPRESSION_COL, HUB_ELIGIBLE_CSV, add_run_arg, assign_paper_ids, load_config,  # noqa: E402
                    load_human_rows, load_search_rows, norm_cell, norm_doi, read_papers, run_paths, write_csv)

COLUMNS = ["paper_id", "title", "doi", "journal", "year", "abstract", "group", "reference", "stratum"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--ratio", type=float, default=1.0, help="negatives per positive (default 1.0 = equal halves)")
    ap.add_argument("--seed", type=int, default=20261105)
    ap.add_argument("--exclude-run", default="abstract_v2", help="run whose papers.csv defines the excluded split")
    ap.add_argument("--exclude-group", default="dev", help="group to exclude ('' = exclude nothing)")
    ap.add_argument("--force", action="store_true", help="overwrite an existing papers.csv (changes the sample!)")
    args = ap.parse_args()
    rp = run_paths(args.run)
    if rp.papers.exists() and not args.force:
        print(f"[error] {rp.papers} exists; refusing to overwrite (the sample must stay fixed). Use --force.")
        return 1

    min_chars = int(load_config()["abstract_screening"].get("min_abstract_chars", 50))
    search = load_search_rows()
    human = load_human_rows()

    with open(HUB_ELIGIBLE_CSV, encoding="utf-8", newline="") as fh:
        eligible = {norm_doi(r.get("doi")) for r in csv.DictReader(fh)} - {""}

    excluded: set[str] = set()
    if args.exclude_group:
        ex_path = run_paths(args.exclude_run).papers
        if ex_path.exists():
            excluded = {norm_doi(r["doi"]) for r in read_papers(ex_path) if r.get("group") == args.exclude_group}
        else:
            print(f"[warn] {ex_path} not found — nothing excluded")

    def usable(d: str) -> bool:
        return d in search and len(search[d]["abstract"]) >= min_chars and d not in excluded

    pos = sorted(d for d in eligible if usable(d) and d in human)
    n_unscored = sum(1 for d in eligible if usable(d) and d not in human)
    neg_pool = sorted(d for d in human if d not in eligible and usable(d))
    rng = random.Random(args.seed)
    n_neg = min(len(neg_pool), round(len(pos) * args.ratio))
    neg = sorted(rng.sample(neg_pool, n_neg))

    def stratum(d: str) -> str:
        row = human.get(d)
        if row is None:
            return "no_human_row"
        return "dep1" if norm_cell(row.get(DEPRESSION_COL)) == "1" else "dep0"

    ids = assign_paper_ids(pos + neg)
    rows = ([{"paper_id": ids[d], "doi": d, "group": "eligible", "reference": "1", "stratum": stratum(d), **search[d]}
             for d in pos] +
            [{"paper_id": ids[d], "doi": d, "group": "not_eligible", "reference": "0", "stratum": stratum(d), **search[d]}
             for d in neg])
    write_csv(rp.papers, rows, COLUMNS)

    print(f"eligible_studies.csv DOIs:        {len(eligible)}")
    print(f"  in search with abstract:         {sum(1 for d in eligible if d in search and len(search[d]['abstract']) >= min_chars)}")
    print(f"  excluded ({args.exclude_run}/{args.exclude_group}): {sum(1 for d in eligible if d in excluded)}")
    print(f"  dropped: no scored human row:    {n_unscored}")
    print(f"positives (eligible):              {len(pos)}   human strata: {dict(Counter(stratum(d) for d in pos))}")
    print(f"negatives (sampled from {len(neg_pool)}):     {len(neg)}   human strata: {dict(Counter(stratum(d) for d in neg))}")
    print(f"-> {rp.papers}")
    return 0


if __name__ == "__main__":
    sys.exit(main())