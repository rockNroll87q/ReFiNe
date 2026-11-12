#!/usr/bin/env python3
"""s0d: build an extended evaluation set from an existing run, reusing finished work.

The new runs/<run>/papers.csv contains:
  1. every paper of --base-run (e.g. e2e_v4)                         heldout = 1
  2. every paper of the dev split (--dev-run / --dev-group)          heldout = 0  (used for prompt tuning)
  3. any remaining eligible_studies paper with an abstract + human scores   heldout = 1
  4. --extra-negatives additional random non-eligible papers (abstract + human scores)  heldout = 1
reference = 1 if the DOI is in eligible_studies.csv, else 0; group = eligible / not_eligible.

Finished artifacts are copied from --copy-from runs (abstract/ and fulltext/) for papers in
the new set, ONLY if they were made with the prompt versions the pipeline would use now
(highest screen_abstract_vN / screen_fulltext_vN), so results never mix prompt versions.
Copied papers are skipped by the pipeline; everything else is screened fresh.

Usage:
  python3 scripts/s0d_extend_set.py --run e2e_v4_all --base-run e2e_v4 \\
      --dev-run abstract_v2 --copy-from e2e_v4 abstract_v4 --extra-negatives 300
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (DEPRESSION_COL, HUB_ELIGIBLE_CSV, add_run_arg, assign_paper_ids, load_config,  # noqa: E402
                    load_human_rows, load_search_rows, norm_cell, norm_doi, pick_prompt, read_papers,
                    run_paths, write_csv)

COLUMNS = ["paper_id", "title", "doi", "journal", "year", "abstract", "group", "reference", "heldout", "stratum",
           "source"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--base-run", required=True, help="existing run whose papers are all kept (held out)")
    ap.add_argument("--dev-run", default="abstract_v2", help="run whose papers.csv defines the dev split ('' = none)")
    ap.add_argument("--dev-group", default="dev")
    ap.add_argument("--extra-negatives", type=int, default=0, help="additional random non-eligible papers")
    ap.add_argument("--copy-from", nargs="*", default=[], help="runs to copy finished artifacts from")
    ap.add_argument("--seed", type=int, default=20261110)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    rp = run_paths(args.run)
    if rp.papers.exists() and not args.force:
        print(f"[error] {rp.papers} exists; refusing to overwrite. Use --force.")
        return 1

    min_chars = int(load_config()["abstract_screening"].get("min_abstract_chars", 50))
    search, human = load_search_rows(), load_human_rows()
    with open(HUB_ELIGIBLE_CSV, encoding="utf-8", newline="") as fh:
        eligible = {norm_doi(r.get("doi")) for r in csv.DictReader(fh)} - {""}

    def usable(d: str) -> bool:
        return d in human and d in search and len(search[d]["abstract"]) >= min_chars

    def stratum(d: str) -> str:
        return "dep1" if norm_cell((human.get(d) or {}).get(DEPRESSION_COL)) == "1" else "dep0"

    chosen: dict[str, dict] = {}   # doi -> {heldout, source}
    for r in read_papers(run_paths(args.base_run).papers):
        chosen[norm_doi(r["doi"])] = {"heldout": "1", "source": args.base_run}
    n_dev = 0
    if args.dev_run:
        for r in read_papers(run_paths(args.dev_run).papers):
            if r.get("group") == args.dev_group:
                d = norm_doi(r["doi"])
                if usable(d):
                    chosen[d] = {"heldout": "0", "source": f"{args.dev_run}:{args.dev_group}"}
                    n_dev += 1
    added_pos = [d for d in sorted(eligible) if usable(d) and d not in chosen]
    for d in added_pos:
        chosen[d] = {"heldout": "1", "source": "remaining_eligible"}
    pool = sorted(d for d in human if usable(d) and d not in eligible and d not in chosen)
    extra = sorted(random.Random(args.seed).sample(pool, min(args.extra_negatives, len(pool))))
    for d in extra:
        chosen[d] = {"heldout": "1", "source": "extra_negatives"}

    ids = assign_paper_ids(sorted(chosen))
    rows = [{"paper_id": ids[d], "doi": d, **search[d], "group": "eligible" if d in eligible else "not_eligible",
             "reference": "1" if d in eligible else "0", "stratum": stratum(d), **meta}
            for d, meta in chosen.items() if d in search]
    rows.sort(key=lambda r: int(r["paper_id"].split("-")[1]))
    write_csv(rp.papers, rows, COLUMNS)

    # ---- copy finished artifacts made with the current prompt versions ----------------
    cur = {"abstract": pick_prompt("screen_abstract").name, "fulltext": pick_prompt("screen_fulltext").name}
    want = {r["paper_id"] for r in rows}
    copied = Counter()
    for src in args.copy_from:
        srp = run_paths(src)
        for stage, sdir, ddir in (("abstract", srp.abstract_dir, rp.abstract_dir),
                                  ("fulltext", srp.fulltext_dir, rp.fulltext_dir)):
            for f in sorted(sdir.glob("*.json")) if sdir.exists() else []:
                if f.stem not in want or (ddir / f.name).exists():
                    continue
                try:
                    art = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if art.get("status") == "ok" and art.get("prompt_version") == cur[stage]:
                    ddir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, ddir / f.name)
                    copied[stage] += 1

    c = Counter((r["source"], r["group"]) for r in rows)
    print(f"-> {rp.papers}: {len(rows)} papers")
    for (src, grp), n in sorted(c.items()):
        print(f"   {src:<22} {grp:<13} {n}")
    print(f"held out: {sum(r['heldout'] == '1' for r in rows)} | dev (prompt-tuning, reported separately): "
          f"{sum(r['heldout'] == '0' for r in rows)}")
    print(f"copied finished results (current prompts {cur['abstract']}, {cur['fulltext']}): "
          f"abstract {copied['abstract']}, full text {copied['fulltext']}")
    print(f"still to screen at abstract: {len(rows) - copied['abstract']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())