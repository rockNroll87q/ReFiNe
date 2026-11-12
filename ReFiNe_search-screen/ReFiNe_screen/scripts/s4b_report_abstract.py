#!/usr/bin/env python3
"""s4b: abstract-screening accuracy vs humans, plus PDF accessibility, for one run.

1. Each gate in config `abstract_screening` is evaluated as a FILTER:
     truth = human scored the gate's `human_column` "1" (met) vs "0" (not met)
     pred  = LLM kept the paper on that gate ("1" or "n/a"; only "0" drops)
   -> sensitivity, specificity, PPV/NPV, Cohen's kappa, 95% CIs. Gates with a
   `human_proxy_column` (scored => met) have positives only: sensitivity only.
2. The overall keep/drop decision vs two human references:
     human-eligible  = depression 1 and no explicit 0 on primary research / human subjects
     human-included  = humans scored 1 on EVERY full-text criterion (final inclusion)
   Recall of human-included papers = the share of finally-included findings the
   abstract stage keeps — the number that matters most for the paper.
3. PDF accessibility of accepted papers (cache/pdf) with download status.

Outputs in runs/<run>/reports/: abstract_report.md, abstract_metrics.csv,
abstract_missed_papers.csv, abstract_gate_false_positives.csv, inaccessible_papers.csv,
and figures/abstract_overview.png (needs matplotlib; skipped with a warning otherwise).

Usage: python3 scripts/s4b_report_abstract.py [--run combined_400] [--group dev] [--n-boot 2000]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (DEPRESSION_COL, PDF_DIR, add_run_arg, human_included, load_config,  # noqa: E402
                    load_human_rows, norm_cell, norm_doi, read_papers, run_paths, write_csv)
from metrics import binary_metrics  # noqa: E402

ELIGIBLE_GATE_COLS = {  # human columns defining "human-eligible" at abstract level
    "depression_related": DEPRESSION_COL,
    "primary_research": "primary research yes/no",
    "human_subjects": "human subjects yes/no",
}
OA_STATUSES = ("gold", "green", "hybrid", "bronze", "diamond")


def kept(v: str | None) -> bool:
    return v != "0"


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--group", default=None, help="restrict to papers whose `group` equals this (e.g. dev)")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--no-figures", action="store_true", help="skip reports/figures/*.png")
    args = ap.parse_args()
    rp = run_paths(args.run)
    cfg = load_config()
    gates = cfg["abstract_screening"]["criteria"]
    ft_criteria = cfg["criteria"]
    out = rp.reports_dir
    sfx = f"_{args.group}" if args.group else ""

    papers = [p for p in read_papers(rp.papers) if not args.group or p.get("group") == args.group]
    human = load_human_rows()
    arts: dict[str, dict] = {}
    for p in papers:
        try:
            arts[p["paper_id"]] = json.loads((rp.abstract_dir / f"{p['paper_id']}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    status_counts = Counter(a.get("status", "?") for a in arts.values())
    n_missing = len(papers) - len(arts)
    prompts = Counter(a.get("prompt_version", "") for a in arts.values() if a.get("status") == "ok")

    # ---- per-gate + decision metrics ----------------------------------------
    gate_pairs = {g["id"]: [] for g in gates}
    gate_excl = {g["id"]: Counter() for g in gates}
    gate_na = Counter()
    gate_fps: list[dict] = []   # human scored the gate 0, LLM kept the paper on it
    dec_elig, dec_incl = [], []
    by_group: dict[str, list] = {}
    misses = []
    n_eval = n_no_human = 0
    for p in papers:
        art = arts.get(p["paper_id"])
        if not art or art.get("status") != "ok":
            continue
        row = human.get(norm_doi(p.get("doi")))
        if row is None:
            n_no_human += 1
            continue
        n_eval += 1
        crit = art.get("criteria") or {}
        lv = {g["id"]: (crit.get(g["id"]) or {}).get("value") for g in gates}
        for g in gates:
            gid = g["id"]
            if g.get("human_column"):
                hv = norm_cell(row.get(g["human_column"]))
                if hv not in ("1", "0"):
                    gate_excl[gid]["blank" if hv is None else "n/a"] += 1
                    continue
                gate_pairs[gid].append((hv == "1", kept(lv[gid])))
                if hv == "0" and kept(lv[gid]):
                    gate_fps.append({"gate": gid, "paper_id": p["paper_id"], "title": p.get("title"),
                                     "doi": p.get("doi"), "llm_value": lv[gid],
                                     "llm_confidence": (crit.get(gid) or {}).get("confidence", ""),
                                     "decision": art.get("decision"),
                                     **{f"llm_{g['id']}": lv[g["id"]] for g in gates},
                                     **{f"evidence_{g['id']}": (crit.get(g["id"]) or {}).get("evidence", "")
                                        for g in gates}})
            elif g.get("human_proxy_column"):
                if norm_cell(row.get(g["human_proxy_column"])) not in ("1", "0"):
                    continue
                gate_pairs[gid].append((True, kept(lv[gid])))
            gate_na[gid] += lv[gid] == "n/a"

        core = {k: norm_cell(row.get(c)) for k, c in ELIGIBLE_GATE_COLS.items()}
        eligible = core["depression_related"] == "1" and all(v != "0" for v in core.values())
        included = human_included(row, ft_criteria)
        keep = art.get("decision") == "yes"
        dec_elig.append((eligible, keep))
        dec_incl.append((included, keep))
        by_group.setdefault(p.get("group") or "-", []).append((eligible, keep))
        if eligible and not keep:
            misses.append({"paper_id": p["paper_id"], "doi": p.get("doi"), "title": p.get("title"),
                           "human_included": int(included), "failed_gates": ";".join(art.get("failed_gates") or []),
                           **{f"llm_{g['id']}": lv[g["id"]] for g in gates},
                           **{f"evidence_{gid}": (crit.get(gid) or {}).get("evidence", "")
                              for gid in (art.get("failed_gates") or [])}})

    gate_res = {gid: binary_metrics(pr, args.n_boot) for gid, pr in gate_pairs.items()}
    res_elig = binary_metrics(dec_elig, args.n_boot)
    res_incl = binary_metrics(dec_incl, args.n_boot)
    res_group = {g: binary_metrics(pr, args.n_boot) for g, pr in sorted(by_group.items())}

    rows = [{"target": f"gate:{gid}" + ("" if g.get("human_column") else " (proxy: sensitivity only)"),
             **gate_res[gid].as_dict()} for g in gates for gid in [g["id"]]]
    rows += [{"target": "decision vs human-eligible", **res_elig.as_dict()},
             {"target": "decision vs human-included", **res_incl.as_dict()}]
    rows += [{"target": f"decision vs human-eligible, group={g}", **r.as_dict()} for g, r in res_group.items()]
    write_csv(out / f"abstract_metrics{sfx}.csv", rows, list(rows[0].keys()))
    miss_cols = sorted({k for m in misses for k in m}, key=lambda k: (k.startswith("evidence_"), k.startswith("llm_"), k))
    write_csv(out / f"abstract_missed_papers{sfx}.csv", misses, miss_cols or ["paper_id"])
    fp_cols = ["gate", "paper_id", "title", "doi", "llm_value", "llm_confidence", "decision",
               *[f"llm_{g['id']}" for g in gates], *[f"evidence_{g['id']}" for g in gates]]
    write_csv(out / f"abstract_gate_false_positives{sfx}.csv", gate_fps, fp_cols)

    # ---- PDF accessibility ----------------------------------------------------
    yes = [p for p in papers if (arts.get(p["paper_id"]) or {}).get("decision") == "yes"]
    manifest = {r["paper_id"]: r for r in read_papers(rp.manifest)} if rp.manifest.exists() else {}
    inaccessible = []
    for p in yes:
        if not (PDF_DIR / f"{p['paper_id']}.pdf").exists():
            m = manifest.get(p["paper_id"], {})
            inaccessible.append({**p, "status": m.get("status") or "not_attempted", "oa_status": m.get("oa_status", ""),
                                 "pmcid": m.get("pmcid", ""), "error_message": (m.get("error_message") or "")[:200]})
    write_csv(out / f"inaccessible_papers{sfx}.csv", inaccessible,
              ["paper_id", "title", "doi", "group", "status", "oa_status", "pmcid", "error_message"])

    # ---- report ---------------------------------------------------------------
    L: list[str] = []
    add = L.append
    add(f"# Abstract screening report — run `{args.run}`" + (f", group `{args.group}`" if args.group else "") + "\n")
    add("## 0. Coverage")
    add(f"- Papers: {len(papers)}; artifacts by status: "
        + ", ".join(f"{k} {v}" for k, v in sorted(status_counts.items())) + f"; not screened yet: {n_missing}")
    add("- Prompt(s): " + ", ".join(f"`{k}` ({v})" for k, v in prompts.most_common())
        + ("  **⚠ mixed prompt versions**" if len(prompts) > 1 else ""))
    if status_counts.get("llm_error") or n_missing:
        add(f"- **{status_counts.get('llm_error', 0) + n_missing} papers unscreened — metrics below exclude them.**")
    add(f"- Evaluated (ok + human row): {n_eval} (ok without human row: {n_no_human})\n")

    add("## 1. Gates vs human scores\n")
    add("Filter view: positive = human scored the criterion as met; LLM keep = 1 or n/a. "
        "Cells: estimate (95% CI) [k/n]; n/e = not estimable.\n")
    add("| Gate | Human reference | n | Sensitivity | Specificity | κ | LLM n/a | Excluded (blank / n/a) |")
    add("|---|---|---|---|---|---|---|---|")
    for g in gates:
        r, gid = gate_res[g["id"]], g["id"]
        ref = f"`{g['human_column']}`" if g.get("human_column") else f"proxy: `{g.get('human_proxy_column')}` scored"
        spec = r.specificity.fmt() if g.get("human_column") else "n/e (no negatives)"
        kap = r.fmt_kappa() if g.get("human_column") else "n/e"
        ex = gate_excl[gid]
        add(f"| {gid} | {ref} | {r.n} | {r.sensitivity.fmt()} | {spec} | {kap} | {gate_na[gid]} | "
            f"{ex['blank']} / {ex['n/a']} |")
    add("\nHumans scored primary research / human subjects only when depression = 1, so those rows are "
        "conditional on depression-related papers. κ is unstable when a class has few cases.\n")

    add("## 2. Overall keep/drop\n")
    add("| Reference | n (positives) | Recall | Specificity | Precision | NPV | κ |")
    add("|---|---|---|---|---|---|---|")
    for label, r in (("human-eligible (depression 1, no 0 on primary/human)", res_elig),
                     ("human-included (1 on every full-text criterion)", res_incl)):
        add(f"| {label} | {r.n} ({r.tp + r.fn}) | {r.sensitivity.fmt()} | {r.specificity.fmt()} | "
            f"{r.ppv.fmt()} | {r.npv.fmt()} | {r.fmt_kappa()} |")
    add(f"\nMissed human-eligible papers: {res_elig.fn} (of which human-included: "
        f"{sum(m['human_included'] for m in misses)}) → `abstract_missed_papers{sfx}.csv` (with the LLM's evidence).\n")
    if len(res_group) > 1:
        add("By group (precision/NPV depend on each group's prevalence):\n")
        add("| Group | n | human-eligible | Recall | Specificity | Precision |")
        add("|---|---|---|---|---|---|")
        for g, r in res_group.items():
            add(f"| {g} | {r.n} | {r.tp + r.fn} | {r.sensitivity.fmt()} | {r.specificity.fmt()} | {r.ppv.fmt()} |")
        add("")

    add("## 3. Full-text accessibility of accepted papers")
    add(f"With a PDF in cache: **{len(yes) - len(inaccessible)}/{len(yes)}** ({pct(len(yes) - len(inaccessible), len(yes))}).")
    if inaccessible:
        add("\n| Download status | n | open access | with PMCID |")
        add("|---|---|---|---|")
        for st, n in Counter(r["status"] for r in inaccessible).most_common():
            sub = [r for r in inaccessible if r["status"] == st]
            add(f"| {st} | {n} | {sum(r['oa_status'] in OA_STATUSES for r in sub)} | {sum(bool(r['pmcid']) for r in sub)} |")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"abstract_report{sfx}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"report -> {out / f'abstract_report{sfx}.md'}  (evaluated {n_eval}; missed eligible {res_elig.fn})")
    if not args.no_figures:
        from plots import plot_abstract, safe_plot
        safe_plot(plot_abstract, out, args.group, args.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())