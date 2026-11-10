"""Shared helpers for ReFiNe_screen: paths, run folders, paper IDs, config, human CSV.

Layout (see REORG_PLAN.md):
  data/input/   INPUTS ONLY  (screened_studies_full.csv, vbm_depression_wide.csv)
  cache/        reusable across runs: pdf/<paper_id>.pdf, text/<paper_id>.md,
                paper_ids.csv (DOI -> paper_id registry, so IDs never change)
  runs/<run>/   everything one run produced (papers.csv, abstract/, download/,
                eval_set.jsonl, fulltext/, reports/)
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # scripts/lib/common.py -> repo root
CONFIG_PATH = ROOT / "config" / "criteria.yaml"
PROMPTS_DIR = ROOT / "prompts"
INPUT_DIR = ROOT / "data" / "input"
SCREENED_CSV = INPUT_DIR / "screened_studies_full.csv"   # human scores, latin-1
SEARCH_CSV = INPUT_DIR / "vbm_depression_wide.csv"       # search output, utf-8
CACHE_DIR = ROOT / "cache"
PDF_DIR = CACHE_DIR / "pdf"
TEXT_DIR = CACHE_DIR / "text"
ID_REGISTRY = CACHE_DIR / "paper_ids.csv"
RUNS_DIR = ROOT / "runs"

HUB_ROOT = ROOT.parent.parent / "ReFiNe_Hub"
HUB_ELIGIBLE_CSV = HUB_ROOT / "data/input/eligible_studies.csv"
HUB_MANIFEST_CSV = HUB_ROOT / "data/input/pdf_download_manifest.csv"

DEFAULT_RUN = "combined_400"
SYSTEM_PROMPT = "You are a careful scientific paper screener. You respond with valid JSON only."
DOI_RE = re.compile(r"(?:https?://(?:dx\.)?doi\.org/|doi:)\s*([0-9A-Za-z./+-]+)", re.IGNORECASE)

# Human CSV bookkeeping columns (row-level flags, not paper criteria).
DUPLICATE_COL = "duplicate entry yes/no"
CORRUPTED_COL = "corrupted entry yes/no"
DEPRESSION_COL = "research question related to depression yes/no"


# ---------------------------------------------------------------------------
# Run folders
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RunPaths:
    name: str

    @property
    def dir(self) -> Path:
        return RUNS_DIR / self.name

    @property
    def papers(self) -> Path:            # input set of this run (paper_id, title, doi, journal, year, abstract, group)
        return self.dir / "papers.csv"

    @property
    def abstract_dir(self) -> Path:      # one JSON per paper
        return self.dir / "abstract"

    @property
    def abstract_yes(self) -> Path:
        return self.dir / "abstract_yes.csv"

    @property
    def abstract_decisions(self) -> Path:
        return self.dir / "abstract_decisions.csv"

    @property
    def download_dir(self) -> Path:      # download list, manifest, audit
        return self.dir / "download"

    @property
    def manifest(self) -> Path:
        return self.download_dir / "manifest.csv"

    @property
    def eval_set(self) -> Path:
        return self.dir / "eval_set.jsonl"

    @property
    def fulltext_dir(self) -> Path:      # one JSON per paper
        return self.dir / "fulltext"

    @property
    def reports_dir(self) -> Path:
        return self.dir / "reports"


def run_paths(name: str) -> RunPaths:
    if not name or "/" in name or name.startswith("."):
        raise ValueError(f"invalid run name: {name!r}")
    return RunPaths(name)


def add_run_arg(ap, help_extra: str = "") -> None:
    ap.add_argument("--run", default=DEFAULT_RUN,
                    help=f"run name; all outputs go to runs/<run>/ (default: {DEFAULT_RUN}){help_extra}")


# ---------------------------------------------------------------------------
# Identifiers / cell normalisation
# ---------------------------------------------------------------------------

def norm_doi(doi: str | None) -> str:
    doi = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/",
                   "http://dx.doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix):]
    return doi.rstrip(".,;)")


def norm_cell(value: str | None, warn: bool = False) -> str | None:
    """Normalise a human score cell to '1' / '0' / 'n/a' / None (unscored)."""
    if value is None:
        return None
    v = value.strip().lower()
    if not v or v in ("?", "-"):
        return None
    if v in ("1", "1.0", "yes"):
        return "1"
    if v in ("0", "0.0", "no"):
        return "0"
    if v in ("n/a", "na", "n.a.", "-/a"):
        return "n/a"
    if warn:
        print(f"[warn] unexpected human score value {value!r}; treating as unscored")
    return None


def norm_llm_value(value) -> str:
    v = str(value if value is not None else "").strip().lower()
    return "n/a" if v == "na" else v


# ---------------------------------------------------------------------------
# Paper-ID registry (cache/paper_ids.csv): DOI -> REFINE-NNNN, assigned once
# ---------------------------------------------------------------------------

def _seed_sources() -> list[Path]:
    """Existing ID assignments, in priority order (first assignment of a DOI wins)."""
    return [HUB_ELIGIBLE_CSV, HUB_MANIFEST_CSV, *sorted(RUNS_DIR.glob("*/papers.csv")),
            INPUT_DIR / "combined_400.csv"]  # last one: legacy location, pre-migration


def load_id_registry() -> dict[str, str]:
    """norm DOI -> paper_id. Seeds the registry from existing ID sources if missing."""
    reg: dict[str, str] = {}
    if ID_REGISTRY.exists():
        with open(ID_REGISTRY, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r.get("doi") and r.get("paper_id"):
                    reg[r["doi"]] = r["paper_id"]
        return reg
    used: set[str] = set()
    for src in _seed_sources():
        if not src.exists():
            continue
        with open(src, newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                d, pid = norm_doi(r.get("doi")), (r.get("paper_id") or "").strip()
                if d and re.fullmatch(r"REFINE-\d+", pid) and d not in reg and pid not in used:
                    reg[d] = pid
                    used.add(pid)
    save_id_registry(reg)
    return reg


def save_id_registry(reg: dict[str, str]) -> None:
    ID_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = ID_REGISTRY.with_suffix(".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["doi", "paper_id"])
        for d, pid in sorted(reg.items(), key=lambda kv: int(kv[1].split("-")[1])):
            w.writerow([d, pid])
    tmp.replace(ID_REGISTRY)


def assign_paper_ids(dois: list[str]) -> dict[str, str]:
    """Return DOI -> paper_id for `dois`, registering new DOIs as REFINE-<next>."""
    reg = load_id_registry()
    nxt = max((int(p.split("-")[1]) for p in reg.values()), default=0) + 1
    changed = False
    for d in dois:
        d = norm_doi(d)
        if d and d not in reg:
            reg[d] = f"REFINE-{nxt:04d}"
            nxt += 1
            changed = True
    if changed:
        save_id_registry(reg)
    return {norm_doi(d): reg[norm_doi(d)] for d in dois if norm_doi(d)}


# ---------------------------------------------------------------------------
# Config + prompts
# ---------------------------------------------------------------------------

def load_config() -> dict:
    import yaml

    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def render_criteria_block(criteria: list[dict]) -> str:
    return "\n".join(f"- `{c['id']}`: {str(c['definition']).strip()}" for c in criteria)


def pick_prompt(prefix: str, explicit: str | None = None) -> Path:
    """Explicit template path, else the highest prompts/<prefix>_v<N>.md."""
    if explicit:
        p = Path(explicit) if Path(explicit).is_absolute() else ROOT / explicit
        if not p.exists():
            raise FileNotFoundError(f"prompt template not found: {p}")
        return p
    cands = sorted(PROMPTS_DIR.glob(f"{prefix}_v*.md"),
                   key=lambda f: int(re.search(r"_v(\d+)\.md$", f.name).group(1)))
    if not cands:
        raise FileNotFoundError(f"no {prefix}_v*.md templates in {PROMPTS_DIR}")
    return cands[-1]


# ---------------------------------------------------------------------------
# Input CSVs
# ---------------------------------------------------------------------------

def read_papers(path: Path) -> list[dict]:
    """A run's papers.csv (or any CSV with paper_id/title/doi/journal/year/abstract[/group])."""
    csv.field_size_limit(10**8)
    with open(path, encoding="utf-8", newline="") as fh:
        return [{k: (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(fh)]


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def load_search_rows(path: Path = SEARCH_CSV) -> dict[str, dict]:
    """norm DOI -> first search-CSV row (title, journal, year, abstract, source)."""
    csv.field_size_limit(10**8)
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            d = norm_doi(r.get("doi"))
            if d and d not in out:
                out[d] = {k: (r.get(k) or "").strip() for k in ("title", "journal", "year", "abstract", "source")}
    return out


# ---------------------------------------------------------------------------
# Human reference CSV
# ---------------------------------------------------------------------------

def human_row_doi(row: dict) -> str:
    """DOI from the `link` column, falling back to a DOI embedded in the citation."""
    doi = norm_doi(row.get("link") or "")
    if not doi:
        m = DOI_RE.search(row.get("Paper") or "")
        doi = norm_doi(m.group(1)) if m else ""
    return doi


def human_row_status(row: dict) -> str:
    """'duplicate' | 'corrupted' | 'unscreened' | 'screened'.

    'unscreened' = not flagged duplicate/corrupted but no depression score (469
    rows, mostly at the end of the file): never screened, NOT negatives.
    """
    if norm_cell(row.get(DUPLICATE_COL)) == "1":
        return "duplicate"
    if norm_cell(row.get(CORRUPTED_COL)) == "1":
        return "corrupted"
    if norm_cell(row.get(DEPRESSION_COL)) is None:
        return "unscreened"
    return "screened"


def load_human_rows(path: Path = SCREENED_CSV, screened_only: bool = True) -> dict[str, dict]:
    """norm DOI -> first (screened) human row for that DOI."""
    rows: dict[str, dict] = {}
    with open(path, newline="", encoding="latin-1") as fh:
        for r in csv.DictReader(fh):
            if screened_only and human_row_status(r) != "screened":
                continue
            d = human_row_doi(r)
            if d and d not in rows:
                rows[d] = r
    return rows


def human_included(row: dict, criteria: list[dict]) -> bool:
    """Human final inclusion on the LLM-rateable criteria: every one scored '1'."""
    return all(norm_cell(row.get(c["source_column"])) == "1" for c in criteria)


# ---------------------------------------------------------------------------
# Environment (.env) — API keys and LLM settings
# ---------------------------------------------------------------------------

ENV_FILES = (ROOT / ".env", HUB_ROOT / ".env")  # first existing wins; real env vars always win


def load_env(path: Path | None = None) -> tuple[Path | None, int]:
    """Load KEY=VALUE lines into os.environ without overriding variables already set.

    Returns (file used or None, number of variables loaded). Values are never printed.
    """
    import os

    candidates = [path] if path else [p for p in ENV_FILES if p.exists()]
    for p in candidates:
        if p is None or not p.exists():
            continue
        n = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip().removeprefix("export ").strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
                n += 1
        return p, n
    return None, 0


def mask(secret: str | None) -> str:
    """'abcd…wxyz' style hint for logs — never the full value."""
    if not secret:
        return "(not set)"
    return f"…{secret[-4:]} ({len(secret)} chars)" if len(secret) > 8 else "(set)"