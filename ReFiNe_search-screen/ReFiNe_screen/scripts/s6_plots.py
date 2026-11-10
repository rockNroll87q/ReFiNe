#!/usr/bin/env python3
"""s6: (re)draw performance figures from existing reports — no LLM, no re-scoring.

s4a / s4b already draw their figures automatically; use this to redraw them or to
compare runs (e.g. prompt v2 vs v3 on the same split).

Usage:
  python3 scripts/s6_plots.py --run abstract_v3 --group dev            # redraw abstract figure
  python3 scripts/s6_plots.py --run combined_400 --fulltext            # redraw latest full-text figure
  python3 scripts/s6_plots.py --compare abstract_v2 abstract_v3 --group dev
        -> runs/abstract_v3/reports/figures/compare_abstract_dev.png (last run named)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import DEFAULT_RUN, run_paths  # noqa: E402
from plots import plot_abstract, plot_compare_abstract, plot_fulltext, safe_plot  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default=DEFAULT_RUN)
    ap.add_argument("--group", default=None)
    ap.add_argument("--fulltext", action="store_true", help="draw the latest full-text report instead")
    ap.add_argument("--compare", nargs="+", metavar="RUN", help="2-3 runs to compare (abstract stage)")
    args = ap.parse_args()

    if args.compare:
        if not 2 <= len(args.compare) <= 3:
            print("[error] --compare takes 2 or 3 runs")
            return 1
        runs = [(r, run_paths(r).reports_dir) for r in args.compare]
        return 0 if safe_plot(plot_compare_abstract, runs, args.group) else 1

    rp = run_paths(args.run)
    if args.fulltext:
        reports = sorted((d for d in rp.reports_dir.glob("fulltext_v*") if d.name.split("_v")[1].isdigit()),
                         key=lambda d: int(d.name.split("_v")[1]))
        if not reports:
            print(f"[error] no fulltext_v* reports in {rp.reports_dir}")
            return 1
        return 0 if safe_plot(plot_fulltext, reports[-1], f"{args.run} (report {reports[-1].name})") else 1
    return 0 if safe_plot(plot_abstract, rp.reports_dir, args.group, args.run) else 1


if __name__ == "__main__":
    sys.exit(main())