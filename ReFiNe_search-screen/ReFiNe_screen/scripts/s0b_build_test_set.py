#!/usr/bin/env python3
"""s0b: build a representative evaluation set = human-screened papers ∩ search CSV.

Every paper the humans actually screened (duplicate / corrupted / never-screened
rows excluded) that the search found WITH a usable abstract becomes one row of
runs/<run>/papers.csv, assigned to a fixed random split:

  group = dev   used while developing prompts/criteria (look at errors freely)
  group = test  held out: run and report ONCE, after prompts are frozen

The split is stratified by human outcome (depression gate 1/0 and human final
inclusion), with a fixed seed, so dev and test have the same mix.

Also prints search coverage: how many human-screened (and human-included)
papers the search CSV contains at all — the "same keywords, same papers" check.

Usage:
  python3 scripts/s0b_build_test_set.py --run abstract_v2 [--dev-frac 0.2] [--seed 20261104]
  python3 scripts/s1_screen_abstract.py --run abstract_v2 --group dev     # then test, once
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (DEPRESSION_COL, add_run_arg, assign_paper_ids, human_included, load_config,  # noqa: E402
                    load_human_rows, load_search_rows, norm_cell, run_paths, write_csv)

COLUMNS = ["paper_id", "title", "doi", "journal", "year", "abstract", "group", "stratum"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--dev-frac", type=float, default=0.2, help="fraction of each stratum in dev (default 0.2)")
    ap.add_argument("--seed", type=int, default=20261104)
    ap.add_argument("--min-abstract-chars", type=int, default=None,
                    help="default: abstract_screening.min_abstract_chars from config")
    ap.add_argument("--force", action="store_true", help="overwrite an existing papers.csv (changes the split!)")
    args = ap.parse_args()
    rp = run_paths(args.run)
    if rp.papers.exists() and not args.force:
        print(f"[error] {rp.papers} exists; refusing to overwrite (the split must stay fixed). Use --force.")
        return 1

    cfg = load_config()
    min_chars = args.min_abstract_chars or int(cfg["abstract_screening"].get("min_abstract_chars", 50))
    human = load_human_rows()          # screened rows only, first scored row per DOI
    search = load_search_rows()

    def stratum(row: dict) -> str:
        if human_included(row, cfg["criteria"]):
            return "included"
        return "dep1" if norm_cell(row.get(DEPRESSION_COL)) == "1" else "dep0"

    in_search = [d for d in human if d in search]
    usable = [d for d in in_search if len(search[d]["abstract"]) >= min_chars]

    # --- coverage report ------------------------------------------------------
    hum_strata = Counter(stratum(r) for r in human.values())
    cov_strata = Counter(stratum(human[d]) for d in in_search)
    use_strata = Counter(stratum(human[d]) for d in usable)
    print("Search coverage of human-screened papers (unique DOIs):")
    print(f"  {'stratum':<10} {'human':>7} {'in search':>10} {'with abstract':>14}")
    for s in ("included", "dep1", "dep0"):
        h, c, u = hum_strata[s], cov_strata[s], use_strata[s]
        print(f"  {s:<10} {h:>7} {c:>6} ({100 * c / h if h else 0:4.1f}%) {u:>8}")
    tot_h, tot_c = sum(hum_strata.values()), len(in_search)
    print(f"  {'total':<10} {tot_h:>7} {tot_c:>6} ({100 * tot_c / tot_h if tot_h else 0:4.1f}%) {len(usable):>8}")
    print("  (included = humans scored 1 on every LLM-rated criterion; dep1 = depression 1 but not included)")

    # --- stratified split -----------------------------------------------------
    rng = random.Random(args.seed)
    group: dict[str, str] = {}
    for s in ("included", "dep1", "dep0"):
        dois = sorted(d for d in usable if stratum(human[d]) == s)  # sort first: order-independent
        rng.shuffle(dois)
        n_dev = round(len(dois) * args.dev_frac)
        for i, d in enumerate(dois):
            group[d] = "dev" if i < n_dev else "test"

    ids = assign_paper_ids(sorted(usable))
    rows = [{"paper_id": ids[d], "doi": d, "group": group[d], "stratum": stratum(human[d]), **search[d]}
            for d in sorted(usable, key=lambda x: ids[x])]
    write_csv(rp.papers, rows, COLUMNS)

    g = Counter((r["group"], r["stratum"]) for r in rows)
    print(f"\n-> {rp.papers}  ({len(rows)} papers)")
    for grp in ("dev", "test"):
        print(f"  {grp:<5} n={sum(v for (gg, _), v in g.items() if gg == grp):>5}  "
              + "  ".join(f"{s}={g[(grp, s)]}" for s in ("included", "dep1", "dep0")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
