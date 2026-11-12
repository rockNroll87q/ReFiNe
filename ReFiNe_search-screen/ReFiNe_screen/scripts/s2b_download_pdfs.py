#!/usr/bin/env python3
"""s2b: download open-access PDFs (wraps ReFiNe_Hub's download_pdfs.py, unmodified).

Source order per paper, unchanged from the Hub script:
  1. OpenAlex OA locations   2. Semantic Scholar   3. PubMed Central
plus, added here, ONLY when all of those fail:
  4. OpenAlex cached full text (content.openalex.org/works/<id>.pdf) — OpenAlex's
     own stored copy, so publisher bot-blocking (HTTP 403) does not apply. Costs
     $0.01 per file against the OpenAlex key's $1/day free allowance; capped by
     --openalex-content-max (default 100 per run). Only works OpenAlex reports
     as having content (has_content.pdf) are fetched, so no money is spent on misses.

Also fixed here: the Hub script's title check compared the expected title with
the whole first two pages (fuzz.ratio), which rejects correct PDFs; it now uses
best-substring matching (partial_ratio).

The Hub module is loaded from scripts/lib/hub_download_pdfs.py if present (copy
ReFiNe_Hub/scripts/download_pdfs.py there to make this repo self-contained),
otherwise from ../../ReFiNe_Hub/scripts/download_pdfs.py.

Keys come from the environment / .env (see s2_check_keys.py): OPENALEX_API_KEY,
SEMANTIC_SCHOLAR_API_KEY, NCBI_EMAIL, NCBI_API_KEY. Keys are never written to the
manifest or logs.

Usage (all Hub flags pass through):
  python3 scripts/s2b_download_pdfs.py --input runs/X/download/download_input.csv \\
      --out-dir cache/pdf --manifest runs/X/download/manifest.csv [--openalex-content-max 100]
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))
from common import HUB_ROOT, load_env, mask  # noqa: E402

CONTENT_URL = "https://content.openalex.org/works/{wid}.pdf"


def load_hub_module():
    for cand in (LIB / "hub_download_pdfs.py", HUB_ROOT / "scripts" / "download_pdfs.py"):
        if cand.exists():
            spec = importlib.util.spec_from_file_location("hub_download_pdfs", cand)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod  # must be registered before exec: @dataclass looks itself up here
            spec.loader.exec_module(mod)
            return mod, cand
    raise FileNotFoundError("download_pdfs.py not found: copy ReFiNe_Hub/scripts/download_pdfs.py "
                            "to scripts/lib/hub_download_pdfs.py")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (s or "").lower())).strip()


def title_similarity(expected_title: str, candidate_text: str) -> float:
    """0-100: best match of the title anywhere in the first pages' text."""
    e, t = _norm(expected_title), _norm(candidate_text[:6000])
    if not e or not t:
        return 0.0
    if e in t:
        return 100.0
    try:
        from rapidfuzz import fuzz
        return float(fuzz.partial_ratio(e, t))
    except ImportError:
        from difflib import SequenceMatcher
        # slide a title-length window over the text; keep the best window
        n, step = len(e), max(1, len(e) // 4)
        return max((SequenceMatcher(None, e, t[i:i + n]).ratio() * 100 for i in range(0, max(1, len(t) - n + 1), step)),
                   default=0.0)


def patch(dp, content_max: int, logger):
    """Install the title fix and the OpenAlex-content fallback into the Hub module."""
    dp._title_similarity = title_similarity
    state = {"used": 0, "got": 0, "max": content_max}
    original = dp.process_paper

    def process_paper(**kw):
        res = original(**kw)
        key = kw.get("openalex_key") or ""
        if (res.get("status") in dp.SUCCESS_STATUSES or not key or state["used"] >= state["max"]):
            return res
        wid = (res.get("openalex_id") or "").rstrip("/").rsplit("/", 1)[-1]
        if not wid.startswith("W"):
            return res
        session, row, pid = kw["session"], kw["row"], kw["row"]["paper_id"]
        try:  # free singleton lookup: does OpenAlex hold a copy?
            r = session.get(f"{dp.OPENALEX_BASE}/works/{wid}", params={"api_key": key, "select": "id,has_content"},
                            timeout=30)
            has_pdf = r.status_code == 200 and bool((r.json().get("has_content") or {}).get("pdf"))
        except Exception:  # noqa: BLE001
            has_pdf = False
        if not has_pdf:
            return res
        pdf_path = kw["out_dir"] / f"{pid}.pdf"
        if kw.get("dry_run"):
            res.update(status=dp.STATUS_DRY_RUN, source_used="openalex_content", pdf_url=CONTENT_URL.format(wid=wid))
            return res
        state["used"] += 1
        logger.info("[%s] Trying OpenAlex cached PDF (%d/%d of this run's cap)", pid, state["used"], state["max"])
        status, _err = dp.download_pdf(session, CONTENT_URL.format(wid=wid) + f"?api_key={key}", pdf_path)
        prev_status, prev_err = res.get("status", ""), res.get("error_message", "")
        if status == dp.STATUS_DOWNLOADED:
            ok, reason = dp.validate_downloaded_pdf(pdf_path, row.get("title", ""), row.get("doi", ""))
            if ok:
                state["got"] += 1
                res.update(status=dp.STATUS_DOWNLOADED, source_used="openalex_content",
                           pdf_url=CONTENT_URL.format(wid=wid), pdf_path=str(pdf_path), error_message="",
                           secondary_status=prev_status, secondary_error_message=prev_err[:300])
                logger.info("[%s] OpenAlex cached PDF accepted (%s)", pid, reason)
                return res
            pdf_path.unlink(missing_ok=True)
            res.update(secondary_status="openalex_content_rejected", secondary_error_message=reason)
        else:  # never store the URL (it carries the key) — status only
            res.update(secondary_status=f"openalex_content_{status}", secondary_error_message="")
        return res

    dp.process_paper = process_paper
    return state


def main() -> int:
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--openalex-content-max", type=int,
                    default=int(os.environ.get("REFINE_OPENALEX_CONTENT_MAX", "100")),
                    help="max OpenAlex cached-PDF downloads this run ($0.01 each; 0 disables)")
    ap.add_argument("-h", "--help", action="store_true")
    own, rest = ap.parse_known_args()
    if own.help:
        print(__doc__)
        return 0

    env_file, _ = load_env()
    dp, path = load_hub_module()
    logger = dp.logger
    print(f"[s2b] Hub downloader: {path}")
    print(f"[s2b] keys: OpenAlex {mask(os.environ.get('OPENALEX_API_KEY'))} · Semantic Scholar "
          f"{mask(os.environ.get('SEMANTIC_SCHOLAR_API_KEY'))} · NCBI {mask(os.environ.get('NCBI_API_KEY'))} "
          f"(email {'set' if os.environ.get('NCBI_EMAIL') else 'not set'})")
    if not os.environ.get("OPENALEX_API_KEY"):
        print("[s2b] ⚠ No OPENALEX_API_KEY: OpenAlex has required a key since 13 Feb 2026; title searches and the "
              "cached-PDF route will not work. Run scripts/s2_check_keys.py.")
    state = patch(dp, own.openalex_content_max, logger)
    rc = dp.main(rest)
    print(f"[s2b] OpenAlex cached-PDF route: {state['got']} downloaded, {state['used']} attempted "
          f"(cap {state['max']}, ≈ ${state['used'] * 0.01:.2f} of the daily allowance)")
    return rc


if __name__ == "__main__":
    sys.exit(main())