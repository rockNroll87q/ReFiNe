#!/usr/bin/env python3
"""s2a: download list = papers accepted at the abstract stage that have no PDF in cache/pdf/.

Reads runs/<run>/abstract_yes.csv, writes runs/<run>/download/download_input.csv
(paper_id,title,doi) for s2b_download_pdfs.py.

Usage: python3 scripts/s2a_prepare_download.py [--run combined_400]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import PDF_DIR, add_run_arg, read_papers, run_paths, write_csv  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_run_arg(ap)
    args = ap.parse_args()
    rp = run_paths(args.run)
    if not rp.abstract_yes.exists():
        print(f"[error] {rp.abstract_yes} not found — run s1_screen_abstract.py first")
        return 1

    yes = read_papers(rp.abstract_yes)
    seen, todo, have = set(), [], 0
    for r in yes:
        pid = r["paper_id"]
        if pid in seen:
            continue
        seen.add(pid)
        if (PDF_DIR / f"{pid}.pdf").exists():
            have += 1
        else:
            todo.append({"paper_id": pid, "title": r.get("title", ""), "doi": r.get("doi", "")})
    out = rp.download_dir / "download_input.csv"
    write_csv(out, todo, ["paper_id", "title", "doi"])
    print(f"accepted papers: {len(seen)} | already in cache/pdf: {have} | to download: {len(todo)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
