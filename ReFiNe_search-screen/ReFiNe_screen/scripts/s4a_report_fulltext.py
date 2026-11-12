#!/usr/bin/env python3
"""s4a: compare LLM full-text ratings against human scores.

Joins runs/<run>/eval_set.jsonl with runs/<run>/fulltext/*.json and writes a
versioned report dir runs/<run>/reports/fulltext_v<N>/:
  summary.md         per-criterion agreement, Cohen's kappa, sensitivity/specificity (95% CIs)
  agreement.csv      the same numbers, machine-readable
  confusion.md       3x3 human-vs-LLM confusion matrix per criterion
  disagreements.csv  every paper x criterion mismatch incl. the model's evidence quote
  figures/fulltext_overview.png  agreement per criterion + why they disagree (needs matplotlib)

Policy:
  - only cells humans actually scored ({1, 0, n/a}) count; blank cells are excluded;
  - 3-class agreement + kappa over {1, 0, n/a} (LLM "n/a" vs human "n/a" = match);
  - binary sensitivity/specificity on cells where the human gave 1 or 0, with
    positive = "1"; an LLM "n/a" there counts as NOT positive (it would not
    satisfy an inclusion rule requiring a 1). The LLM n/a count is reported.
  - "v<N>" is just the report counter; the prompt / criteria / model actually
    used are read from the artifacts and printed in the report header.

Usage: python3 scripts/s4a_report_fulltext.py [--run combined_400] [--version N] [--n-boot 2000]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import ROOT, add_run_arg, load_config, norm_llm_value, run_paths  # noqa: E402
from metrics import Prop, binary_metrics, multiclass_agreement  # noqa: E402

VALID = ("1", "0", "n/a")


def load_eval(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rec = json.loads(line)
                out[rec["paper_id"]] = rec
    return out


def load_ratings(ratings_dir: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(ratings_dir.glob("*.json")):
        try:
            art = json.loads(p.read_text(encoding="utf-8"))
            out[art.get("paper_id") or p.stem] = art
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] skipping unreadable rating {p.name}: {exc}")
    return out


def next_version(reports_dir: Path, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    existing = [int(d.name.split("_v")[1]) for d in reports_dir.glob("fulltext_v*") if d.name.split("_v")[1].isdigit()]
    return max(existing, default=0) + 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--version", type=int, default=None, help="report version (default: next)")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--no-figures", action="store_true", help="skip figures/fulltext_overview.png")
    args = ap.parse_args()

    cfg = load_config()
    crit_ids = [c["id"] for c in cfg["criteria"]]
    rp = run_paths(args.run)
    if not rp.eval_set.exists():
        print(f"[error] {rp.eval_set} not found")
        return 1
    evals, ratings = load_eval(rp.eval_set), load_ratings(rp.fulltext_dir)
    v = next_version(rp.reports_dir, args.version)
    out_dir = rp.reports_dir / f"fulltext_v{v}"
    out_dir.mkdir(parents=True, exist_ok=True)

    cells: dict[str, list[tuple[str, str]]] = {cid: [] for cid in crit_ids}  # (human, llm)
    all_cells: list[tuple[str, str]] = []
    paper_all_match: list[bool] = []
    disagreements: list[tuple] = []
    error_papers = sorted(pid for pid, a in ratings.items() if a.get("status") != "ok")
    used = [a for pid, a in ratings.items() if pid in evals and a.get("status") == "ok"]
    prompts = Counter(a.get("prompt_version", "?") for a in used)
    models = Counter(a.get("model", "?") for a in used)

    for paper_id, eval_rec in sorted(evals.items()):
        art = ratings.get(paper_id)
        if not art or art.get("status") != "ok":
            continue
        llm_criteria = art.get("criteria", {})
        row_all, row_any = True, False
        for cid in crit_ids:
            hv = eval_rec["human"].get(cid)
            if hv not in VALID:
                continue  # unscored by humans
            entry = llm_criteria.get(cid) or {}
            lv = norm_llm_value(entry.get("value")) or "(missing)"
            cells[cid].append((hv, lv))
            all_cells.append((hv, lv))
            row_any = True
            if lv != hv:
                row_all = False
                disagreements.append((paper_id, cid, hv, lv, entry.get("confidence", ""),
                                      str(entry.get("evidence", ""))[:500]))
        if row_any:
            paper_all_match.append(row_all)

    table, conf_md = [], []
    for cid in crit_ids:
        agr = multiclass_agreement(cells[cid], n_boot=args.n_boot)
        bin_pairs = [(h == "1", l == "1") for h, l in cells[cid] if h in ("1", "0")]
        b = binary_metrics(bin_pairs, n_boot=args.n_boot)
        n_llm_na = sum(1 for h, l in cells[cid] if h in ("1", "0") and l == "n/a")
        table.append({"criterion": cid, "agr": agr, "bin": b, "llm_na_on_scored": n_llm_na})
        conf_md += [f"### {cid}", "", *agr.confusion_md(), ""]

    with open(out_dir / "agreement.csv", "w", newline="", encoding="utf-8") as fh:
        rows = []
        for t in table:
            a = t["agr"]
            lo, hi = a.agreement.ci
            rows.append({"criterion": t["criterion"], "n_scored": a.n, "n_agree": a.agreement.k,
                         "agree": f"{a.agreement.p:.4f}" if a.n else "", "agree_lo": f"{lo:.4f}" if a.n else "",
                         "agree_hi": f"{hi:.4f}" if a.n else "",
                         "kappa_3class": f"{a.kappa:.4f}" if a.kappa == a.kappa else "",
                         "llm_na_on_human_1or0": t["llm_na_on_scored"], **t["bin"].as_dict("bin_")})
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    with open(out_dir / "disagreements.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["paper_id", "criterion", "human", "llm", "llm_confidence", "llm_evidence"])
        w.writerows(disagreements)
    (out_dir / "confusion.md").write_text("# Human (rows) vs LLM (columns)\n\n" + "\n".join(conf_md), encoding="utf-8")

    overall = multiclass_agreement(all_cells, n_boot=args.n_boot)
    n_papers = len(paper_all_match)
    lines = [
        f"# Full-text screening agreement — run {args.run}, report v{v}", "",
        f"- Prompt(s): {', '.join(f'`{k}` ({n})' for k, n in prompts.most_common())}"
        + ("  **⚠ mixed prompt versions**" if len(prompts) > 1 else ""),
        f"- Model(s): {', '.join(f'`{k}` ({n})' for k, n in models.most_common())}",
        f"- Criteria config version: {cfg.get('version', '?')}",
        f"- Papers in eval set: **{len(evals)}**; rated ok: **{len(used)}**  (llm_error: {len(error_papers)}"
        + (f": {', '.join(error_papers)}" if error_papers else "") + ")",
        f"- Paper-level full match (all scored criteria): **{Prop(sum(paper_all_match), n_papers).fmt()}**", "",
        "Estimates: value (95% CI) [k/n]. 3-class = agreement over {1, 0, n/a}. "
        "Sens/Spec: human 1/0 cells only, positive = \"1\", LLM n/a counted as not-1. n/e = not estimable.", "",
        "| Criterion | n | 3-class agreement | κ (3-class) | Sensitivity | Specificity | LLM n/a on human 1/0 |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in table:
        a, b = t["agr"], t["bin"]
        lines.append(f"| {t['criterion']} | {a.n} | {a.agreement.fmt()} | {a.fmt_kappa()} | "
                     f"{b.sensitivity.fmt()} | {b.specificity.fmt()} | {t['llm_na_on_scored']} |")
    lines += ["",
              f"**Overall: {overall.agreement.fmt()} of scored cells match; pooled κ {overall.fmt_kappa()}.**", "",
              "Caveats:",
              "- The eval set is the set of accessible PDFs (OA-biased), not a random sample of the search output.",
              "- Criteria/prompt revisions were tuned on papers in this set, so these figures are optimistic "
              "until confirmed on a held-out split.",
              "- κ is prevalence-sensitive; criteria with very few human negatives (e.g. human_subjects) can show "
              "low/undefined κ despite near-perfect agreement.",
              "- Pooled κ treats cells as independent; cells within a paper are correlated, so its CI is too narrow.",
              "",
              f"Disagreements: {len(disagreements)} -> `disagreements.csv`; confusion matrices -> `confusion.md`."]
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Report written to {out_dir.relative_to(ROOT)}/  (papers rated ok: {len(used)}, "
          f"cells matched: {overall.agreement.k}/{overall.n})")
    if not args.no_figures:
        from plots import plot_fulltext, safe_plot
        safe_plot(plot_fulltext, out_dir, f"{args.run} (report v{v})")
    return 0


if __name__ == "__main__":
    sys.exit(main())