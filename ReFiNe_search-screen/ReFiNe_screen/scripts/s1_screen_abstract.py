#!/usr/bin/env python3
"""s1: abstract-level eligibility screening.

For each paper in runs/<run>/papers.csv (built by s0 / s0b):
  1. renders prompts/screen_abstract_v<N>.md with the title + abstract;
  2. makes one LLM call scoring the gates in `abstract_screening` (config/criteria.yaml);
  3. derives keep/drop IN CODE (no_if_any_gate_zero: drop only on an explicit "0";
     "n/a" never excludes — recall-first);
  4. writes runs/<run>/abstract/<paper_id>.json (status ok | llm_error | no_abstract).

Afterwards runs/<run>/abstract_yes.csv and abstract_decisions.csv are rewritten
from all artifacts. Resumable: ok / no_abstract artifacts are skipped unless
--force; llm_error ones are retried. The LLM endpoint is health-checked only if
there is work to do; the run aborts (exit 2) after --max-consecutive-failures.

Usage:
  python3 scripts/s1_screen_abstract.py --run abstract_v2 --group dev
  python3 scripts/s1_screen_abstract.py --run abstract_v2 --limit 10
  python3 scripts/s1_screen_abstract.py --run abstract_v2 --ids REFINE-0001,REFINE-0456
  python3 scripts/s1_screen_abstract.py --run abstract_v2 --dry-run --limit 3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (ROOT, SYSTEM_PROMPT, add_run_arg, load_config, pick_prompt, read_papers,  # noqa: E402
                    render_criteria_block, run_paths, write_csv)
from llm_client import CircuitBreaker, health_check, rate_with_retry  # noqa: E402
from runner import print_stats, read_status, run_items  # noqa: E402

BASE_COLUMNS = ["paper_id", "doi", "title", "journal", "year", "group"]
DONE_STATUSES = ("ok", "no_abstract")


def render_prompt(template: str, rec: dict, criteria_block: str) -> str:
    # .replace (not .format): titles/abstracts may contain curly braces.
    journal_year = " / ".join(p for p in (rec.get("journal", ""), rec.get("year", "")) if p) or "(no journal/year)"
    return (template
            .replace("{{CANDIDATE_ID}}", rec["paper_id"])
            .replace("{{CRITERIA_BLOCK}}", criteria_block)
            .replace("{{TITLE}}", rec.get("title") or "(no title)")
            .replace("{{JOURNAL_YEAR}}", journal_year)
            .replace("{{ABSTRACT}}", rec.get("abstract") or "(no abstract)"))


def decide(cfg: dict, parsed: dict) -> tuple[str, list[str]]:
    """no_if_any_gate_zero: NO when any gate is explicitly "0"; otherwise YES."""
    if cfg["decision_rule"] != "no_if_any_gate_zero":
        raise ValueError(f"unsupported decision_rule: {cfg['decision_rule']!r}")
    failed = [c["id"] for c in cfg["criteria"] if parsed[c["id"]]["value"] == "0"]
    return ("no", failed) if failed else ("yes", [])


def rate_row(rec: dict, cfg: dict, template: str, template_name: str, dry_run: bool,
             breaker: CircuitBreaker | None) -> dict:
    artifact = {k: rec.get(k, "") for k in BASE_COLUMNS}
    artifact["screen_id"] = rec["paper_id"]  # backward-compatible field name
    artifact["abstract_chars"] = len(rec.get("abstract", ""))

    if artifact["abstract_chars"] < int(cfg.get("min_abstract_chars", 0)):
        artifact.update(status="no_abstract", decision=None, failed_gates=[])
        return artifact

    prompt = render_prompt(template, rec, render_criteria_block(cfg["criteria"]))
    if dry_run:
        dry_dir = ROOT / "data" / "dryrun"
        dry_dir.mkdir(parents=True, exist_ok=True)
        (dry_dir / f"{rec['paper_id']}.abstract_prompt.txt").write_text(prompt, encoding="utf-8")
        artifact.update(status="dry_run", decision=None, failed_gates=[])
        return artifact

    result = rate_with_retry(prompt, rec["paper_id"], [c["id"] for c in cfg["criteria"]],
                             SYSTEM_PROMPT, stage="abstract", breaker=breaker)
    if result["status"] != "ok":
        artifact.update(status="llm_error", error=result["error"])
        return artifact
    decision, failed = decide(cfg, result["criteria"])
    artifact.update(
        status="ok", decision=decision, failed_gates=failed,
        model=result["model"], prompt_version=template_name, criteria_version=cfg.get("criteria_version", ""),
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        criteria=result["criteria"],
    )
    return artifact


def write_summaries(papers: list[dict], cfg: dict, rp) -> tuple[list, list]:
    gate_ids = [c["id"] for c in cfg["criteria"]]
    yes_rows, dec_rows = [], []
    for rec in papers:
        try:
            art = json.loads((rp.abstract_dir / f"{rec['paper_id']}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if art.get("status") == "dry_run":
            continue
        base = {k: rec.get(k, "") for k in BASE_COLUMNS}
        crit = art.get("criteria") or {}
        dec_rows.append({**base, "status": art.get("status", ""), "decision": art.get("decision") or "",
                         **{g: (crit.get(g) or {}).get("value", "") for g in gate_ids},
                         "failed_gates": ";".join(art.get("failed_gates") or []),
                         "prompt_version": art.get("prompt_version", ""),
                         "criteria_version": art.get("criteria_version", ""), "error": art.get("error", "")})
        if art.get("decision") == "yes":
            yes_rows.append(base)
    write_csv(rp.abstract_yes, yes_rows, BASE_COLUMNS)
    write_csv(rp.abstract_decisions, dec_rows,
              BASE_COLUMNS + ["status", "decision", *gate_ids, "failed_gates", "prompt_version", "criteria_version", "error"])
    return yes_rows, dec_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--group", default=None, help="only screen papers whose `group` column equals this (e.g. dev)")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", default="", help="comma-separated paper_ids")
    ap.add_argument("--force", action="store_true", help="re-screen even if an artifact exists")
    ap.add_argument("--dry-run", action="store_true", help="render prompts only, no LLM call")
    ap.add_argument("--prompt", default=None, help="explicit template path (default: highest vN)")
    ap.add_argument("--workers", type=int, default=2, help="parallel LLM calls (1 = sequential)")
    ap.add_argument("--max-consecutive-failures", type=int, default=3)
    ap.add_argument("--skip-health-check", action="store_true")
    args = ap.parse_args()

    rp = run_paths(args.run)
    if not rp.papers.exists():
        print(f"[error] {rp.papers} not found — build it with s0_collect_combined_papers.py or s0b_build_test_set.py")
        return 1
    full_cfg = load_config()
    cfg = {**full_cfg["abstract_screening"], "criteria_version": full_cfg.get("version", "")}
    template_path = pick_prompt("screen_abstract", args.prompt)
    template = template_path.read_text(encoding="utf-8")

    papers = read_papers(rp.papers)
    sel = papers
    if args.group:
        sel = [r for r in sel if r.get("group") == args.group]
    wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
    if wanted:
        sel = [r for r in sel if r["paper_id"] in wanted]
    if args.limit:
        sel = sel[: args.limit]

    def is_done(rec: dict) -> str | None:
        if args.force or args.dry_run:
            return None
        st = read_status(rp.abstract_dir / f"{rec['paper_id']}.json")
        return st if st in DONE_STATUSES else None

    n_todo = sum(1 for r in sel if not is_done(r))
    print(f"Run: {args.run} | prompt: {template_path.name} | criteria v{cfg['criteria_version']} | papers: {len(papers)} | "
          f"selected: {len(sel)}{f' (group={args.group})' if args.group else ''} | to screen: {n_todo}", flush=True)

    if n_todo and not args.dry_run and not args.skip_health_check:
        ok, msg = health_check()
        print(msg, flush=True)
        if not ok:
            return 2
    breaker = CircuitBreaker(args.max_consecutive_failures)

    def describe(a: dict) -> str:
        s = f" decision={a['decision']}" if a.get("status") == "ok" else ""
        if a.get("failed_gates"):
            s += f" failed={','.join(a['failed_gates'])}"
        return s

    t0 = time.time()
    stats = run_items(sel, id_key="paper_id", artifact_dir=rp.abstract_dir, is_done=is_done,
                      work=lambda r: rate_row(r, cfg, template, template_path.name, args.dry_run, breaker),
                      describe=describe, workers=args.workers, breaker=breaker)
    print_stats(stats, time.time() - t0)

    yes_rows, dec_rows = write_summaries(papers, cfg, rp)
    n_err = sum(1 for r in dec_rows if r["status"] == "llm_error")
    prompts = sorted({r["prompt_version"] for r in dec_rows if r["prompt_version"]})
    print(f"Summaries: {rp.abstract_yes.name} ({len(yes_rows)} yes) | {rp.abstract_decisions.name} "
          f"({len(dec_rows)} screened, {n_err} llm_error)" + (f" | ⚠ mixed prompts {prompts}" if len(prompts) > 1 else ""),
          flush=True)
    return 2 if stats.aborted else (1 if stats.failed else 0)


if __name__ == "__main__":
    sys.exit(main())