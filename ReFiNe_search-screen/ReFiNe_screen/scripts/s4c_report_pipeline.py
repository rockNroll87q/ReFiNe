#!/usr/bin/env python3
"""s4c: end-to-end pipeline report — what happened to every paper, vs a reference.

Reference: the `reference` column of runs/<run>/papers.csv (1 = should be included;
written by s0c_build_eligible_set.py from the pilot's eligible_studies.csv). Runs
without that column fall back to human final inclusion (1 on every full-text
criterion in the human CSV).

Fate of each paper:
  not_screened       no abstract decision yet (excluded from metrics, counted)
  dropped_abstract   abstract stage said no
  no_fulltext        kept, but no PDF in cache/pdf or no successful full-text rating
  excluded_fulltext  rated at full text and failed the inclusion rule
  included           rated at full text and passed

Full-text inclusion rules (both reported):
  strict   every criterion = "1"
  lenient  no criterion = "0" ("n/a" — detail not found in the text — does not exclude)

Metrics (95% CIs): end-to-end sensitivity/specificity vs reference; the same for the
full-text stage alone (papers that reached a rating); full-text accessibility of
kept reference-positive papers; and which criteria failed for eligible papers.

Caveats printed in the report: comparability with the replication data (part of the
pilot's eligibility) is not rated by the LLM, so specificity vs eligible_studies is a
lower bound; balanced sets do not give real-search precision.

Outputs (runs/<run>/reports/): pipeline_report.md, pipeline_papers.csv, pipeline_fates.csv,
pipeline_metrics.csv, pipeline_failed_criteria.csv, figures/pipeline_overview.png

Usage: python3 scripts/s4c_report_pipeline.py --run e2e_v4 [--n-boot 2000] [--no-figures]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (PDF_DIR, add_run_arg, human_included, load_config, load_human_rows, norm_doi,  # noqa: E402
                    norm_llm_value, read_papers, run_paths, write_csv)
from metrics import Prop, binary_metrics  # noqa: E402

FATE_ORDER = ["not_screened", "dropped_abstract", "no_fulltext", "excluded_fulltext", "included"]
RULES = ("strict", "lenient")


def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def ft_pass(values: dict[str, str], rule: str) -> bool:
    if rule == "strict":
        return all(v == "1" for v in values.values())
    return all(v != "0" for v in values.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--no-figures", action="store_true")
    args = ap.parse_args()
    rp = run_paths(args.run)
    cfg = load_config()
    crit_ids = [c["id"] for c in cfg["criteria"]]
    papers = read_papers(rp.papers)

    has_ref = any(p.get("reference") in ("0", "1") for p in papers)
    human = None if has_ref else load_human_rows()
    ref_label = "papers.csv `reference` (eligible_studies.csv)" if has_ref else "human final inclusion (CSV)"

    per_paper, fates = [], Counter()
    failed = {c: Counter() for c in crit_ids}  # eligible, rated, strict-excluded: which criteria were 0 / n/a
    prompts = Counter()
    for p in papers:
        pid = p["paper_id"]
        if has_ref:
            ref = p.get("reference")
            if ref not in ("0", "1"):
                continue
        else:
            row = human.get(norm_doi(p.get("doi")))
            if row is None:
                continue
            ref = "1" if human_included(row, cfg["criteria"]) else "0"
        ab = load_json(rp.abstract_dir / f"{pid}.json") or {}
        ft = load_json(rp.fulltext_dir / f"{pid}.json") or {}
        has_pdf = (PDF_DIR / f"{pid}.pdf").exists()
        vals = {c: norm_llm_value(((ft.get("criteria") or {}).get(c) or {}).get("value")) for c in crit_ids}
        rated = ft.get("status") == "ok"
        if rated:
            prompts[ft.get("prompt_version", "?")] += 1
        rec = {"paper_id": pid, "doi": p.get("doi"), "title": p.get("title"), "reference": ref,
               "abstract_decision": ab.get("decision") or ab.get("status") or "", "has_pdf": int(has_pdf),
               "fulltext_status": ft.get("status", ""), **{f"ft_{c}": vals[c] if rated else "" for c in crit_ids}}
        for rule in RULES:
            if ab.get("status") not in ("ok", "no_abstract"):
                fate = "not_screened"
            elif ab.get("decision") != "yes":
                fate = "dropped_abstract"
            elif not rated:
                fate = "no_fulltext"
            else:
                fate = "included" if ft_pass(vals, rule) else "excluded_fulltext"
            rec[f"fate_{rule}"] = fate
            fates[(rule, ref, fate)] += 1
        if ref == "1" and rated and not ft_pass(vals, "strict"):
            for c in crit_ids:
                if vals[c] == "0":
                    failed[c]["zero"] += 1
                elif vals[c] != "1":
                    failed[c]["na"] += 1
        per_paper.append(rec)

    out = rp.reports_dir
    write_csv(out / "pipeline_papers.csv", per_paper, list(per_paper[0].keys()) if per_paper else ["paper_id"])
    write_csv(out / "pipeline_fates.csv",
              [{"rule": r, "reference": ref, "fate": f, "n": fates[(r, ref, f)]}
               for r in RULES for ref in ("1", "0") for f in FATE_ORDER],
              ["rule", "reference", "fate", "n"])
    write_csv(out / "pipeline_failed_criteria.csv",
              [{"criterion": c, "n_zero": failed[c]["zero"], "n_na": failed[c]["na"]} for c in crit_ids],
              ["criterion", "n_zero", "n_na"])

    # ---- metrics -------------------------------------------------------------------
    metric_rows, L = [], []
    add = L.append
    n_ref = Counter(r["reference"] for r in per_paper)
    add(f"# End-to-end pipeline report — run `{args.run}`\n")
    add(f"- Reference: {ref_label}. Papers: {n_ref['1']} reference-positive, {n_ref['0']} reference-negative.")
    add("- Full-text prompt(s): " + (", ".join(f"`{k}` ({v})" for k, v in prompts.most_common()) or "none yet")
        + ("  **⚠ mixed**" if len(prompts) > 1 else ""))
    n_ns = sum(1 for r in per_paper if r["fate_strict"] == "not_screened")
    if n_ns:
        add(f"- **{n_ns} papers not screened yet — excluded from the metrics below.**")
    add("")
    add("## Where each paper ended up\n")
    add("| Reference | Rule | dropped at abstract | no full text | excluded at full text | **included** |")
    add("|---|---|---|---|---|---|")
    for ref, name in (("1", "eligible"), ("0", "not eligible")):
        for rule in RULES:
            c = {f: fates[(rule, ref, f)] for f in FATE_ORDER}
            tot = sum(c[f] for f in FATE_ORDER[1:])
            add(f"| {name} (n={tot}) | {rule} | {c['dropped_abstract']} | {c['no_fulltext']} | "
                f"{c['excluded_fulltext']} | **{c['included']}** |")
    add("")
    add("## Metrics (95% CI)\n")
    add("| Scope | Rule | n | Sensitivity | Specificity | κ |")
    add("|---|---|---|---|---|---|")
    for rule in RULES:
        scored = [r for r in per_paper if r[f"fate_{rule}"] != "not_screened"]
        e2e = binary_metrics([(r["reference"] == "1", r[f"fate_{rule}"] == "included") for r in scored], args.n_boot)
        reached = [r for r in scored if r["fulltext_status"] == "ok" and r["abstract_decision"] == "yes"]
        ftm = binary_metrics([(r["reference"] == "1", r[f"fate_{rule}"] == "included") for r in reached], args.n_boot)
        for scope, m in (("end-to-end (all papers)", e2e), ("full-text stage only (papers rated)", ftm)):
            add(f"| {scope} | {rule} | {m.n} | {m.sensitivity.fmt()} | {m.specificity.fmt()} | {m.fmt_kappa()} |")
            metric_rows.append({"scope": scope, "rule": rule, **m.as_dict()})
    heldout = {p["paper_id"]: p.get("heldout", "") for p in papers}
    if any(v in ("0", "1") for v in heldout.values()):
        add("")
        add("**Held-out papers only** (excludes papers used to tune the prompts — quote these):\n")
        add("| Rule | n | Sensitivity | Specificity | κ |")
        add("|---|---|---|---|---|")
        for rule in RULES:
            sub = [r for r in per_paper if heldout.get(r["paper_id"]) == "1" and r[f"fate_{rule}"] != "not_screened"]
            m = binary_metrics([(r["reference"] == "1", r[f"fate_{rule}"] == "included") for r in sub], args.n_boot)
            add(f"| {rule} | {m.n} | {m.sensitivity.fmt()} | {m.specificity.fmt()} | {m.fmt_kappa()} |")
            metric_rows.append({"scope": "end-to-end, held-out only", "rule": rule, **m.as_dict()})
    kept_pos = [r for r in per_paper if r["reference"] == "1" and r["abstract_decision"] == "yes"]
    acc = Prop(sum(r["has_pdf"] for r in kept_pos), len(kept_pos))
    rated_pos = Prop(sum(r["fulltext_status"] == "ok" for r in kept_pos), len(kept_pos))
    add("")
    add(f"- Full text available for eligible papers kept at abstract: **{acc.fmt()}**; rated: {rated_pos.fmt()}.")
    add("- End-to-end sensitivity = share of eligible studies the whole pipeline (abstract → download → full text) "
        "includes; full-text-only metrics separate screening errors from missing PDFs.")
    add("")
    add("## Which criteria failed for eligible papers (rated at full text, strict rule)\n")
    add("| Criterion | LLM said 0 | LLM n/a |")
    add("|---|---|---|")
    for c in sorted(crit_ids, key=lambda c: -(failed[c]["zero"] + failed[c]["na"])):
        if failed[c]["zero"] + failed[c]["na"]:
            add(f"| {c} | {failed[c]['zero']} | {failed[c]['na']} |")
    add("\nCaveats: the pilot's eligibility also required comparability with the replication data, which the LLM "
        "does not rate — specificity vs eligible_studies is therefore a lower bound. A 50/50 set gives valid "
        "sensitivity/specificity but not real-search precision or workload. Per-paper detail: `pipeline_papers.csv`.")
    write_csv(out / "pipeline_metrics.csv", metric_rows, list(metric_rows[0].keys()))
    (out / "pipeline_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"report -> {out / 'pipeline_report.md'}")
    if not args.no_figures:
        from plots import plot_pipeline, safe_plot
        safe_plot(plot_pipeline, out, args.run)
    return 0


if __name__ == "__main__":
    sys.exit(main())