#!/usr/bin/env python3
"""s3b: full-text eligibility rating.

For each paper in runs/<run>/eval_set.jsonl (built by s3a), this script:
  1. converts the PDF to markdown once (cache/text/<paper_id>.md, shared by all runs) —
     done up-front, sequentially, before any LLM call (Docling's converter is
     a shared singleton and is not guaranteed thread-safe);
  2. packs the text into the model's context budget with section-aware packing
     (methods/MRI/measures prioritised over introduction/discussion);
  3. renders prompts/screen_fulltext_v<N>.md and makes one LLM call;
  4. validates the JSON answer (one re-ask on a malformed response);
  5. writes runs/<run>/fulltext/<paper_id>.json (status ok | llm_error).

Resumable: papers whose artifact has status ok are skipped unless --force.
Health check + retry/backoff + circuit breaker as in screen_abstract.py
(exit code 2 when the run aborts on an unreachable endpoint).

Usage:
  python3 scripts/s3b_screen_fulltext.py --run combined_400 --limit 3
  python3 scripts/s3b_screen_fulltext.py --run combined_400
  python3 scripts/s3b_screen_fulltext.py --run combined_400 --ids REFINE-0001,REFINE-0002
  python3 scripts/s3b_screen_fulltext.py --run combined_400 --dry-run --limit 3

Environment: REFINE_LLM_* (see llm_client.py), REFINE_MAX_CONTEXT_TOKENS
(default 32768), REFINE_LLM_RESERVE_TOKENS (default 4096).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import (PDF_DIR, ROOT, SYSTEM_PROMPT, TEXT_DIR, add_run_arg, load_config, pick_prompt,  # noqa: E402
                    render_criteria_block, run_paths)
from llm_client import CircuitBreaker, health_check, rate_with_retry  # noqa: E402
from runner import print_stats, read_status, run_items  # noqa: E402

TOKEN_CHAR_RATIO = 4.0  # approximate characters per token


def render_prompt(template: str, paper_id: str, title: str, full_text: str, criteria_block: str) -> str:
    # .replace (not .format): paper text may contain curly braces.
    return (template
            .replace("{{CANDIDATE_ID}}", paper_id)
            .replace("{{CRITERIA_BLOCK}}", criteria_block)
            .replace("{{TITLE}}", title or "(no title)")
            .replace("{{FULL_TEXT}}", full_text))


# ---------------------------------------------------------------------------
# Section-aware text packing (adapted from ReFiNe_Hub/refine/extract.py)
# 2026-11-04: "vb m" -> "vbm", "dar tel" -> "dartel" (the split forms were OCR
# artefacts that never matched normal headings).
# ---------------------------------------------------------------------------

_IMPORTANT_SECTION_KEYWORDS = [
    "subjects", "participants", "sample", "cohort", "population",
    "methods", "materials", "procedure", "protocol", "design",
    "mri", "magnetic resonance", "t1", "t2", "voxel-based morphometry",
    "vbm", "spm", "dartel", "brain imaging", "image acquisition",
    "measures", "measurements", "questionnaires", "scales", "assessment",
    "inventory", "rating", "score", "scores",
    "depression", "anxiety", "trauma", "adversity", "stress",
    "genetics", "genetic", "genotype", "snp", "blood", "biomarker",
    "medication", "drug", "treatment",
    "longitudinal", "follow-up", "follow up", "prospective", "cross-sectional",
    "results", "findings", "conclusion", "discussion", "summary",
]

_SECTION_PRIORITY = {
    "abstract": 100, "introduction": 50, "subjects": 90, "participants": 90,
    "sample": 85, "methods": 95, "materials": 90, "procedure": 80,
    "protocol": 80, "image acquisition": 90, "mri acquisition": 95,
    "data acquisition": 85, "voxel-based morphometry": 90, "vbm analysis": 90,
    "spm": 70, "dartel": 85, "preprocessing": 85, "measures": 90,
    "measurements": 85, "questionnaires": 90, "scales": 85, "assessment": 80,
    "statistical analysis": 85, "depression": 75, "anxiety": 70, "trauma": 65,
    "adversity": 60, "stress": 65, "genetics": 75, "blood": 70, "biomarker": 70,
    "medication": 80, "longitudinal": 80, "follow-up": 80, "results": 95,
    "findings": 90, "conclusion": 85, "discussion": 75,
}


def _looks_like_caps_heading(s: str) -> bool:
    """Short ALL-CAPS line made of plain alphabetic words (a heading, not a table row)."""
    if not s or len(s) > 60 or s != s.upper():
        return False
    words = s.split()
    return 1 <= len(words) <= 8 and all(re.fullmatch(r"[A-Z][A-Za-z]*(?:-[A-Za-z]+)*", w) for w in words)


def _parse_sections(text: str) -> list[tuple[str, str]]:
    """Split markdown text into (heading, content) sections."""
    sections: list[list] = []
    for line in text.split("\n"):
        stripped = line.strip()
        is_heading = (
            (stripped.startswith("#") and not stripped.startswith("--- PAGE BREAK ---"))
            or bool(re.match(r"^\d+[.\)]\s+[A-Z][a-z]+", stripped))
            or _looks_like_caps_heading(stripped)
        )
        if is_heading:
            sections.append([re.sub(r"^#+\s*|\d+[.\)]\s*", "", stripped).strip(), []])
        elif sections:
            sections[-1][1].append(line)
        else:
            sections.append(["(no heading)", [line]])
    out = []
    for heading, lines in sections:
        content = "\n".join(lines).strip()
        if heading and content:
            out.append((heading, content))
    return out


def _section_priority(heading: str) -> int:
    h = heading.lower().strip()
    for key, prio in _SECTION_PRIORITY.items():
        if key in h:
            return prio
    return 40 if any(k in h for k in _IMPORTANT_SECTION_KEYWORDS) else 5


def build_text_pack(full_text: str, title: str, max_chars: int) -> tuple[str, bool]:
    """Fit the paper text into max_chars, keeping the most criterion-relevant sections."""
    if len(full_text) <= max_chars:
        return full_text, False

    meta = f"# Title: {title}\n" if title else ""
    abstract_content = None
    scored: list[tuple[str, str, int]] = []
    for heading, content in _parse_sections(full_text):
        if "abstract" in heading.lower():
            abstract_content = content
            continue
        prio = _section_priority(heading)
        if any(k in (heading + " " + content[:500]).lower() for k in _IMPORTANT_SECTION_KEYWORDS):
            prio = max(prio, 45)
        scored.append((heading, content, prio))

    scored.sort(key=lambda x: (-x[2], len(x[1])))
    high = [(h, c) for h, c, p in scored if p >= 80]
    medium = [(h, c) for h, c, p in scored if 50 <= p < 80]
    low = [(h, c) for h, c, p in scored if p < 50]

    parts: list[str] = [meta] if meta else []
    current_len = len(meta)

    def try_add(section_text: str) -> bool:
        nonlocal current_len
        if current_len + len(section_text) <= max_chars:
            parts.append(section_text)
            current_len += len(section_text)
            return True
        return False

    if abstract_content is not None:
        try_add(f"# Abstract\n\n{abstract_content}")
    for heading, content in high + medium:
        try_add(f"\n# {heading}\n\n{content}")

    low_limit = int(max(0, max_chars - current_len) * 0.3)  # filler capped at 30% of leftover
    for heading, content in low:
        section_text = f"\n# {heading}\n\n{content}"
        if len(section_text) <= low_limit and try_add(section_text):
            continue
        if current_len >= max_chars:
            break
    return "\n".join(parts).strip(), True


# ---------------------------------------------------------------------------
# Text conversion + per-paper rating
# ---------------------------------------------------------------------------

def text_path(rec: dict) -> Path:
    return TEXT_DIR / f"{rec['paper_id']}.md"


def ensure_text(rec: dict) -> Path:
    """Return the markdown path for a paper, converting the PDF if needed."""
    tp = text_path(rec)
    if not tp.exists():
        from pdf_to_text import pdf_to_text  # heavy (Docling); only import when converting

        pdf = PDF_DIR / f"{rec['paper_id']}.pdf"  # current cache, not the path stored at build time
        pdf_to_text(pdf if pdf.exists() else ROOT / rec["pdf_path"], tp)
    return tp


def rate_paper(rec: dict, criteria: list[dict], template: str, template_name: str,
               dry_run: bool, breaker: CircuitBreaker | None) -> dict:
    paper_id, title = rec["paper_id"], rec.get("title", "")
    criteria_block = render_criteria_block(criteria)
    full_text = ensure_text(rec).read_text(encoding="utf-8")

    # available_for_text = context - prompt_overhead - response_reserve
    overhead_chars = len(render_prompt(template, paper_id, title, "", criteria_block))
    max_ctx = int(os.environ.get("REFINE_MAX_CONTEXT_TOKENS", "32768"))
    reserve = int(os.environ.get("REFINE_LLM_RESERVE_TOKENS", "4096"))
    budget_chars = int(max(max_ctx - overhead_chars // 4 - reserve, 256) * TOKEN_CHAR_RATIO)

    packed_text, was_packed = build_text_pack(full_text, title, budget_chars)
    prompt = render_prompt(template, paper_id, title, packed_text, criteria_block)
    artifact: dict = {
        "paper_id": paper_id, "doi": rec.get("doi", ""), "title": title,
        "text_chars_full": len(full_text), "text_chars_used": len(packed_text), "packed": was_packed,
    }

    if dry_run:
        dry_dir = ROOT / "data" / "dryrun"
        dry_dir.mkdir(parents=True, exist_ok=True)
        (dry_dir / f"{paper_id}.prompt.txt").write_text(prompt, encoding="utf-8")
        artifact["status"] = "dry_run"
        return artifact

    result = rate_with_retry(prompt, paper_id, [c["id"] for c in criteria], SYSTEM_PROMPT,
                             stage="fulltext", breaker=breaker)
    if result["status"] != "ok":
        artifact.update(status="llm_error", error=result["error"])
        return artifact
    artifact.update(
        status="ok",
        model=result["model"],
        prompt_version=template_name,
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        criteria=result["criteria"],
    )
    return artifact


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_run_arg(ap)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ids", default="", help="comma-separated paper_ids")
    ap.add_argument("--force", action="store_true", help="re-rate even if artifact exists")
    ap.add_argument("--dry-run", action="store_true", help="render prompts only, no LLM call")
    ap.add_argument("--prompt", default=None, help="explicit template path (default: highest vN)")
    ap.add_argument("--workers", type=int, default=2, help="parallel LLM calls (1 = sequential)")
    ap.add_argument("--max-consecutive-failures", type=int, default=3)
    ap.add_argument("--skip-health-check", action="store_true")
    args = ap.parse_args()

    rp = run_paths(args.run)
    if not rp.eval_set.exists():
        print(f"[error] {rp.eval_set} not found — run s3a_build_fulltext_set.py first")
        return 1
    RATINGS_DIR = rp.fulltext_dir
    criteria = load_config()["criteria"]
    template_path = pick_prompt("screen_fulltext", args.prompt)
    template = template_path.read_text(encoding="utf-8")
    print(f"Prompt template: {template_path.name}")

    evals = [json.loads(line) for line in open(rp.eval_set, encoding="utf-8") if line.strip()]
    wanted = {s.strip() for s in args.ids.split(",") if s.strip()}
    if wanted:
        evals = [e for e in evals if e["paper_id"] in wanted]
    if args.limit:
        evals = evals[: args.limit]

    def is_done(rec: dict) -> str | None:
        if args.force or args.dry_run:
            return None
        return "already ok" if read_status(RATINGS_DIR / f"{rec['paper_id']}.json") == "ok" else None

    # 1) Convert missing texts sequentially, outside the LLM thread pool.
    todo = [e for e in evals if not is_done(e) and not text_path(e).exists()]
    if todo:
        print(f"Converting {len(todo)} PDF(s) to text first...", flush=True)
    unconvertible = set()
    for e in todo:
        try:
            ensure_text(e)
        except Exception as exc:  # noqa: BLE001
            print(f"[convert-fail] {e['paper_id']}: {exc}", flush=True)
            unconvertible.add(e["paper_id"])
    evals = [e for e in evals if e["paper_id"] not in unconvertible]

    # 2) LLM rating.
    n_todo = sum(1 for e in evals if not is_done(e))
    print(f"Run: {args.run} | papers: {len(evals)} | to rate: {n_todo}", flush=True)
    if n_todo and not args.dry_run and not args.skip_health_check:
        ok, msg = health_check()
        print(msg, flush=True)
        if not ok:
            return 2
    breaker = CircuitBreaker(args.max_consecutive_failures)

    def describe(a: dict) -> str:
        return (f", text {a.get('text_chars_used')}/{a.get('text_chars_full')} chars"
                + (" packed" if a.get("packed") else ""))

    t0 = time.time()
    stats = run_items(evals, id_key="paper_id", artifact_dir=RATINGS_DIR, is_done=is_done,
                      work=lambda r: rate_paper(r, criteria, template, template_path.name, args.dry_run, breaker),
                      describe=describe, workers=args.workers, breaker=breaker)
    print_stats(stats, time.time() - t0)
    if unconvertible:
        print(f"PDF conversion failed for {len(unconvertible)}: {', '.join(sorted(unconvertible))}")
    return 2 if stats.aborted else (1 if stats.failed else 0)


if __name__ == "__main__":
    sys.exit(main())