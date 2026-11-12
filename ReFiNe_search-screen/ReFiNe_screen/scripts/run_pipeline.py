#!/usr/bin/env python3
"""One-command runner for the ReFiNe_screen pipeline. All outputs go to runs/<run>/.

  s0   s0_collect_combined_papers.py | s0b_build_test_set.py | s0c_build_eligible_set.py
       -> runs/<run>/papers.csv (only if it does not exist yet; choose with --paper-set)
  s1   s1_screen_abstract.py          abstract screening        -> abstract/, abstract_yes.csv
  s2a  s2a_prepare_download.py        accepted papers without a cached PDF
  s2k  s2_check_keys.py               API keys work? (stops the run if the OpenAlex key fails)
  s2b  s2b_download_pdfs.py           OA download (+ OpenAlex cached PDFs) -> cache/pdf/, download/manifest.csv
  s2c  s2c_audit_pdfs.py              PDF vs expected DOI/title -> download/audit_report.csv
  s3a  s3a_build_fulltext_set.py      papers with PDF + human scores -> eval_set.jsonl
  s3b  s3b_screen_fulltext.py         full-text screening       -> fulltext/
  s4a  s4a_report_fulltext.py         full-text accuracy        -> reports/fulltext_vN/
  s4b  s4b_report_abstract.py         abstract accuracy + access -> reports/abstract_report.md
  s4c  s4c_report_pipeline.py         end-to-end fate of every paper -> reports/pipeline_report.md

s2c is taken from scripts/ when present, otherwise from ReFiNe_Hub/scripts/.
LLM settings come from the environment, else from --env-file (default: ./.env,
falling back to ReFiNe_Hub/.env). Variables already set win over the file.

Examples:
  # finish the original combined run (download + full text + reports)
  python3 scripts/run_pipeline.py --run combined_400 --skip-abstract
  # representative set: abstract screening of the dev split + report only
  python3 scripts/run_pipeline.py --run abstract_v2 --paper-set test-set --group dev \\
      --skip-download --skip-fulltext
  # full pipeline on eligible studies + an equal number of rejected papers
  python3 scripts/run_pipeline.py --run e2e_v4 --paper-set eligible-balanced

Exit code 2 from s1/s3b = LLM endpoint unreachable: start LM Studio, re-run the same command.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import DEFAULT_RUN, HUB_MANIFEST_CSV, HUB_ROOT, PDF_DIR, ROOT, load_env, path_str, run_paths  # noqa: E402

SCRIPTS = ROOT / "scripts"
HUB_SCRIPTS = HUB_ROOT / "scripts"


def script(local_name: str, hub_name: str | None = None) -> Path:
    local = SCRIPTS / local_name
    return local if local.exists() or hub_name is None else HUB_SCRIPTS / hub_name


def build_merged_manifest(hub_csv: Path, run_csv: Path, out_csv: Path) -> int:
    """Hub + run manifests (run rows win), pdf_path pointed at the PDF cache. Returns row count."""
    rows: dict[str, dict] = {}
    for path, winning in ((hub_csv, False), (run_csv, True)):
        if not path.exists():
            continue
        with open(path, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                pid = (r.get("paper_id") or "").strip()
                if pid and (winning or pid not in rows):
                    rows[pid] = r
    if not rows:
        return 0
    for pid, r in rows.items():
        local = PDF_DIR / f"{pid}.pdf"
        r["pdf_path"] = path_str(local) if local.exists() else ""  # failures: no path -> no "missing" noise
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = list(dict.fromkeys(k for r in rows.values() for k in r))
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows.values())
    return len(rows)


def csv_has_rows(path: Path) -> bool:
    if not path.exists():
        return False
    with open(path, newline="", encoding="utf-8") as fh:
        return any((r.get("paper_id") or "").strip() for r in csv.DictReader(fh))


def build_stages(args, rp) -> list[tuple[str, str, list[str]]]:
    py = sys.executable
    run = ["--run", args.run]
    grp = ["--group", args.group] if args.group else []
    llm = ["--workers", str(args.workers), "--max-consecutive-failures", str(args.max_consecutive_failures)]
    st: list[tuple[str, str, list[str]]] = []

    if not args.skip_collect and not rp.papers.exists():
        if args.paper_set == "combined":
            cmd = [py, str(script("s0_collect_combined_papers.py")), *run, "--n-extra", str(args.n_extra)]
            if args.max_papers is not None:
                cmd += ["--max-papers", str(args.max_papers)]
            st.append(("s0", "Build combined paper set", cmd))
        elif args.paper_set == "test-set":
            st.append(("s0b", "Build representative test set (human ∩ search, dev/test split)",
                       [py, str(script("s0b_build_test_set.py")), *run]))
        else:
            st.append(("s0c", "Build balanced set (eligible studies + equal rejected, dev excluded)",
                       [py, str(script("s0c_build_eligible_set.py")), *run]))
    if not args.skip_abstract:
        st.append(("s1", "Abstract screening", [py, str(script("s1_screen_abstract.py")), *run, *grp, *llm]))
    if not args.skip_download:
        dl = rp.download_dir
        st.append(("s2a", "Download list (accepted, no cached PDF)", [py, str(script("s2a_prepare_download.py")), *run]))
        if not args.skip_key_check:
            st.append(("s2k", "Check API keys", [py, str(script("s2_check_keys.py"))]))
        st.append(("s2b", "Download OA PDFs (+ OpenAlex cached copies)", [
            py, str(script("s2b_download_pdfs.py")),
            "--openalex-content-max", str(args.openalex_content_max),
            "--input", str(dl / "download_input.csv"), "--out-dir", str(PDF_DIR),
            "--manifest", str(rp.manifest), "--manual-queue", str(dl / "manual_pdf_needed.csv"),
            "--sleep", f"{args.sleep:g}", "-v"]))
        if not args.skip_audit:
            st.append(("s2c", "Audit PDFs against expected DOI/title", [
                py, str(script("s2c_audit_pdfs.py", "audit_downloaded_pdfs.py")),
                "--input", str(rp.papers), "--manifest", str(dl / "manifest_merged_for_audit.csv"),
                "--pdf-dir", str(PDF_DIR), "--out", str(dl / "audit_report.csv"),
                "--suspects", str(dl / "suspect_pdfs.csv")]))
    if not args.skip_fulltext:
        st.append(("s3a", f"Full-text set (scope={args.fulltext_scope})", [
            py, str(script("s3a_build_fulltext_set.py")), *run, "--scope", args.fulltext_scope, *grp]))
        st.append(("s3b", "Full-text screening", [py, str(script("s3b_screen_fulltext.py")), *run, *llm]))
    if not args.skip_report:
        if not args.skip_fulltext or rp.eval_set.exists():
            st.append(("s4a", "Full-text accuracy report", [py, str(script("s4a_report_fulltext.py")), *run]))
        st.append(("s4b", "Abstract accuracy + PDF access report",
                   [py, str(script("s4b_report_abstract.py")), *run, *grp]))
        if not args.skip_fulltext or rp.fulltext_dir.exists():
            st.append(("s4c", "End-to-end pipeline report", [py, str(script("s4c_report_pipeline.py")), *run]))
    return st


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", default=DEFAULT_RUN, help=f"run name -> runs/<run>/ (default {DEFAULT_RUN})")
    ap.add_argument("--paper-set", choices=("combined", "test-set", "eligible-balanced"), default="combined",
                    help="how to build papers.csv if it does not exist yet")
    ap.add_argument("--group", default=None, help="restrict screening/reports to one split (e.g. dev)")
    ap.add_argument("--fulltext-scope", choices=("run", "all"), default="run",
                    help="s3a: this run's papers only, or every cached PDF")
    ap.add_argument("--n-extra", type=int, default=100)
    ap.add_argument("--max-papers", type=int, default=None)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-consecutive-failures", type=int, default=3)
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--api-key", default=None, help="OpenAlex API key -> OPENALEX_API_KEY")
    ap.add_argument("--ss-api-key", default=None, help="Semantic Scholar key -> SEMANTIC_SCHOLAR_API_KEY")
    ap.add_argument("--ncbi-email", default=None)
    ap.add_argument("--ncbi-api-key", default=None)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--openalex-content-max", type=int, default=100,
                    help="max OpenAlex cached-PDF downloads per run ($0.01 each; ~100/day free with a key; 0 = off)")
    ap.add_argument("--skip-key-check", action="store_true", help="download even if the API key check fails")
    for s in ("collect", "abstract", "download", "audit", "fulltext", "report"):
        ap.add_argument(f"--skip-{s}", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rp = run_paths(args.run)

    env_file, n_env = load_env(args.env_file)
    for var, val in (("OPENALEX_API_KEY", args.api_key), ("SEMANTIC_SCHOLAR_API_KEY", args.ss_api_key),
                     ("NCBI_EMAIL", args.ncbi_email), ("NCBI_API_KEY", args.ncbi_api_key)):
        if val:
            os.environ[var] = val
    print(f"[run] {args.run} -> {rp.dir}" + (f" (group={args.group})" if args.group else ""))
    print(f"[env] {env_file or 'no .env file found'}" + (f": loaded {n_env} vars" if env_file else ""))

    stages = build_stages(args, rp)
    if not rp.papers.exists() and not any(s[0] in ("s0", "s0b") for s in stages) and not args.dry_run:
        print(f"[error] {rp.papers} does not exist and collection is skipped")
        return 1
    missing = [c[1] for _, _, c in stages if not Path(c[1]).exists()]
    if missing:
        print("[error] stage script(s) not found:\n  " + "\n  ".join(missing))
        return 1

    t_all = time.time()
    for sid, desc, cmd in stages:
        print(f"\n=== {sid}: {desc} " + "=" * max(0, 60 - len(sid) - len(desc)))
        print("    $ " + " ".join(a[len(str(ROOT)) + 1:] if a.startswith(str(ROOT) + os.sep) else a for a in cmd))
        if args.dry_run:
            continue
        if sid == "s2b" and not csv_has_rows(rp.download_dir / "download_input.csv"):
            print("    SKIP — nothing to download")
            continue
        if sid == "s2c":
            n = build_merged_manifest(HUB_MANIFEST_CSV, rp.manifest, rp.download_dir / "manifest_merged_for_audit.csv")
            if not n:
                print("    SKIP — no manifest yet")
                continue
        t = time.time()
        sys.stdout.flush()
        proc = subprocess.run(cmd, cwd=str(ROOT))
        if proc.returncode != 0:
            print(f"\n[FAILED] {sid} exited with code {proc.returncode} after {time.time() - t:.0f}s.")
            if sid == "s2k":
                print("API key check failed — see the messages above, fix .env, or pass --skip-key-check.")
            if proc.returncode == 2 and sid in ("s1", "s3b"):
                print("LLM endpoint unreachable — check LM Studio is running and the model is loaded.")
            print("Stages are resumable: fix the issue and re-run the SAME command (or --skip-<stage>).")
            return proc.returncode
        print(f"    done in {time.time() - t:.0f}s")

    if args.dry_run:
        print("\n[dry-run] nothing executed.")
        return 0
    print(f"\nAll stages finished in {(time.time() - t_all) / 60:.1f} min. Outputs: {rp.dir.relative_to(ROOT)}/")
    for p in sorted(rp.reports_dir.glob("*.md")) if rp.reports_dir.exists() else []:
        print(f"  {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())