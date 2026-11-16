#!/usr/bin/env python3
"""s00: search literature databases and write the candidate CSV that s0/s0b/s0c/s0d read.

Search settings live in config/search.yaml (query groups, sources, output paths).
Any command line option overrides the matching config value. API keys come from the
environment / .env (OPENALEX_API_KEY, SEMANTIC_SCHOLAR_API_KEY), never from the YAML.

Output columns: title,doi,journal,year,abstract,source (one row per unique DOI, abstract
preferred when several sources return the same DOI). A <csv>.meta.json records the resolved
query, date and per source counts. An existing CSV is not overwritten without --force,
and nothing is written if any source fails (unless --allow-partial).

Usage:
  python3 scripts/s00_search_papers.py
  python3 scripts/s00_search_papers.py --query-group "voxel based morphometry|VBM" --query-group "anxiety"
  python3 scripts/s00_search_papers.py --sources pubmed,openalex --out data/input/anxiety_search.csv --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import INPUT_DIR, ROOT, SEARCH_CSV, load_env  # noqa: E402
from search_sources import SOURCES, dedupe, run_search  # noqa: E402


def resolve(p: str | Path) -> Path:
    """
    Summary
        Resolves a path against the project root unless it is absolute.
    Args
        p (str | Path): path from config or CLI
    Returns
        Path: absolute path
    """
    p = Path(p).expanduser()
    return p if p.is_absolute() else ROOT / p


def build_settings(args: argparse.Namespace) -> dict:
    """
    Summary
        Merges config/search.yaml with command line overrides (CLI wins).
    Args
        args (argparse.Namespace): parsed arguments
    Returns
        dict: query_groups, sources, email, pubmed_max_results, csv, pubmed_jsonl
    """
    cfg_path = resolve(args.config)
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    if not cfg_path.exists() and args.config != str(ROOT / "config" / "search.yaml"):
        raise FileNotFoundError(cfg_path)
    out = cfg.get("output") or {}
    groups = ([[t.strip() for t in g.split("|") if t.strip()] for g in args.query_group]
              if args.query_group else [list(map(str, g)) for g in cfg.get("query_groups") or []])
    sources = ([s.strip() for s in args.sources.split(",") if s.strip()] if args.sources
               else list(cfg.get("sources") or SOURCES))
    bad = [s for s in sources if s not in SOURCES]
    if bad:
        raise ValueError(f"unknown source(s) {bad}, choose from {list(SOURCES)}")
    if not groups or not all(groups):
        raise ValueError("no query groups: set query_groups in the config or pass --query-group")
    csv_path = args.out or out.get("csv") or SEARCH_CSV
    return {
        "query_groups": groups,
        "sources": sources,
        "email": args.email or cfg.get("email") or os.environ.get("NCBI_EMAIL", ""),
        "pubmed_max_results": args.pubmed_max_results or int(cfg.get("pubmed_max_results", 9998)),
        "csv": resolve(csv_path),
        "pubmed_jsonl": resolve(args.pubmed_jsonl or out.get("pubmed_jsonl") or INPUT_DIR / "pubmed_raw.jsonl"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "search.yaml"))
    ap.add_argument("--query-group", action="append", default=[],
                    help='one AND group, terms separated by "|" (repeat per group); replaces config query_groups')
    ap.add_argument("--sources", default=None, help=f"comma separated subset of {','.join(SOURCES)}")
    ap.add_argument("--out", default=None, help="output csv path")
    ap.add_argument("--pubmed-jsonl", default=None)
    ap.add_argument("--pubmed-max-results", type=int, default=None)
    ap.add_argument("--email", default=None)
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--force", action="store_true", help="overwrite an existing output csv")
    ap.add_argument("--allow-partial", action="store_true", help="write the csv even if some sources failed")
    ap.add_argument("--dry-run", action="store_true", help="print the resolved settings and exit")
    args = ap.parse_args()

    load_env(args.env_file)
    s = build_settings(args)
    print(f"[search] groups (AND of ORs): {s['query_groups']}")
    print(f"[search] sources: {s['sources']} | out: {s['csv']}")
    if s["csv"].resolve() != SEARCH_CSV.resolve():
        print(f"[warn] {s['csv']} is not common.SEARCH_CSV ({SEARCH_CSV.name}); s0/s0b/s0c/s0d will not read it "
              "until SEARCH_CSV is changed or the file is copied over")
    if args.dry_run:
        return 0
    if s["csv"].exists() and not args.force:
        print(f"[error] {s['csv']} exists; refusing to overwrite (downstream sets depend on it). Use --force.")
        return 1

    s["csv"].parent.mkdir(parents=True, exist_ok=True)
    s["pubmed_jsonl"].parent.mkdir(parents=True, exist_ok=True)
    records, counts, errors = run_search(
        s["query_groups"], s["sources"],
        api_key=os.environ.get("OPENALEX_API_KEY"), s2_key=os.environ.get("SEMANTIC_SCHOLAR_API_KEY"),
        email=s["email"], pubmed_jsonl=s["pubmed_jsonl"], pubmed_max_results=s["pubmed_max_results"],
        tmp_dir=str(s["csv"].parent))
    if errors and not args.allow_partial:
        print(f"[FAILED] sources failed {errors}. Nothing written. Fix and re-run, or pass --allow-partial.")
        return 1
    if not records:
        print("[FAILED] no records returned")
        return 1

    df = dedupe(records)
    df.to_csv(s["csv"], index=False)
    meta = {"date_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "query_groups": s["query_groups"], "raw_counts": counts, "errors": errors,
            "unique_dois": int(df["doi"].nunique()), "with_abstract": int(df["abstract"].notna().sum())}
    s["csv"].with_suffix(".meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    logger.info(f"Records in candidate set: {len(df)}")
    logger.info(f"Abstracts present: {meta['with_abstract']} / {len(df)}")
    logger.info(f"Records by source:\n{df['source'].value_counts()}")
    logger.info(f"Missing abstracts by source:\n{df.loc[df['abstract'].isna(), 'source'].value_counts()}")
    print(f"-> {s['csv']}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
