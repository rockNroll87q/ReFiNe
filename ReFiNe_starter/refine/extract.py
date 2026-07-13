"""Core extraction logic for ReFiNe.

This module orchestrates:
  1. PDF-to-text conversion
  2. LLM-based broad dataset-feature extraction
  3. Schema validation with retry
  4. Merging results back into papers.json
"""

import json
import logging
import os
import re as _re
from pathlib import Path

from rich.console import Console as RichConsole

console = RichConsole()

from .llm_client import call_llm
from .pdf_to_text import pdf_to_text
from .schema import ExtractedFeatures, FEATURE_KEYS

logger = logging.getLogger(__name__)


def _as_dict(value):
    """Convert a Pydantic model or dict to a plain dict."""
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    raise TypeError(f"Expected dict or Pydantic model, got {type(value)}")

# ---------------------------------------------------------------------------
# Paths (relative to the project root)
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # ReFiNe_starter/
PAPERS_JSON = PROJECT_ROOT / "site" / "data" / "papers.json"
PDFS_DIR = PROJECT_ROOT / "data" / "pdfs"
TEXT_DIR = PROJECT_ROOT / "data" / "text"
EXTRACTED_DIR = PROJECT_ROOT / "data" / "extracted"
LOGS_DIR = PROJECT_ROOT / "data" / "logs"

# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE_PATH = PROJECT_ROOT / "prompts" / "extract_dataset_features.md"


def _load_prompt_template() -> str:
    """Load the extraction prompt template from disk."""
    if PROMPT_TEMPLATE_PATH.exists():
        return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    # Inline fallback (should not normally be reached)
    raise FileNotFoundError(
        f"Prompt template not found at {PROMPT_TEMPLATE_PATH}. "
        "Ensure the prompts/ directory exists with extract_dataset_features.md."
    )


SYSTEM_PROMPT = (
    "You are a precise scientific paper data extractor. "
    "Your job is to return ONLY valid JSON with no markdown formatting, "
    "no explanations, and no comments. "
    "The JSON must match the requested schema exactly."
)


# ---------------------------------------------------------------------------
# Feature mapping helpers
# ---------------------------------------------------------------------------

def _build_feature_summary(features: dict) -> list[str]:
    """Build a human-readable summary list from extracted features.

    Only includes features whose value is ``"yes"``.
    """
    labels = {
        "t1w_mri": "T1w MRI",
        "vbm_or_voxelwise_morphometry": "VBM / voxel-wise morphometry",
        "mdd_patients": "MDD patients",
        "healthy_controls": "Healthy controls",
        "genetic_data": "Genetic data",
        "depression_scale": "Depression scale",
        "anxiety_scale": "Anxiety scale",
        "clinical_outcomes": "Clinical outcomes",
        "longitudinal_data": "Longitudinal data",
        "medication_status": "Medication status",
        "trauma_or_life_stress": "Trauma / life stress",
        "cognitive_data": "Cognitive data",
        "blood_or_biomarker_data": "Blood / biomarker data",
    }
    return [labels.get(k, k) for k, v in features.items() if v == "yes"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _validate_and_parse(raw: str, paper_id: str) -> ExtractedFeatures:
    """Validate the LLM response and parse it into an ExtractedFeatures model.

    If parsing fails, raises ValueError with the error message.
    """
    import json as _json

    # Try to extract JSON from the raw response.
    # LLMs sometimes wrap in ```json ... ``` or add surrounding text.
    cleaned = raw.strip()

    # Try direct parse first
    try:
        data = _json.loads(cleaned)
        return ExtractedFeatures.model_validate(data)
    except Exception:
        pass

    # Try to find JSON block in the response
    json_match = _re.search(r'\{[\s\S]*\}', cleaned)
    if json_match:
        try:
            data = _json.loads(json_match.group())
            return ExtractedFeatures.model_validate(data)
        except Exception:
            pass

    raise ValueError(f"Could not parse LLM response as JSON. Raw response:\n{raw[:500]}")


def _repair_and_parse(raw: str, paper_id: str, error: str) -> ExtractedFeatures:
    """Attempt to repair invalid JSON by sending a repair prompt to the LLM."""
    repair_prompt = (
        f"Your previous JSON response was invalid. Error: {error}\n\n"
        f"Please return ONLY valid JSON. No markdown, no explanations, no comments.\n\n"
        f"Required schema:\n"
        f'{{"paper_id": "{paper_id}", '
        f'"dataset_features_needed": {{"t1w_mri": "yes"|"no"|"unclear"|"not_applicable", ...}}, '
        f'"website_card": {{"short_description": null, "dataset_features_summary": []}}, '
        f'"extraction_status": "completed", '
        f'"extraction_notes": null}}'
    )
    repaired = call_llm(repair_prompt, SYSTEM_PROMPT)
    return _validate_and_parse(repaired, paper_id)


# ---------------------------------------------------------------------------
# Context window truncation helper
# ---------------------------------------------------------------------------

# Keywords that indicate important sections for scientific paper extraction
_IMPORTANT_SECTION_KEYWORDS = [
    # Subjects / participants
    "subjects", "participants", "sample", "cohort", "population",
    # Methods / materials
    "methods", "materials", "procedure", "protocol", "design",
    # MRI / imaging
    "mri", "magnetic resonance", "t1", "t2", "voxel-based morphometry",
    "vb m", "spm", "dar tel", "brain imaging", "image acquisition",
    # Clinical measures
    "measures", "measurements", "questionnaires", "scales", "assessment",
    "inventory", "rating", "score", "scores",
    # Specific constructs
    "depression", "anxiety", "trauma", "adversity", "stress",
    "genetics", "genetic", "genotype", "snp", "blood", "biomarker",
    "medication", "drug", "treatment",
    # Study design
    "longitudinal", "follow-up", "follow up", "prospective", "cross-sectional",
    # Results and conclusions
    "results", "findings", "conclusion", "discussion", "summary",
]

# Priority order for sections (higher = included first if budget is tight)
_SECTION_PRIORITY = {
    "abstract": 100,
    "introduction": 50,
    "subjects": 90,
    "participants": 90,
    "sample": 85,
    "methods": 95,
    "materials": 90,
    "procedure": 80,
    "protocol": 80,
    "image acquisition": 90,
    "mri acquisition": 95,
    "data acquisition": 85,
    "voxel-based morphometry": 90,
    "vb m analysis": 90,
    "spm": 70,
    "dar tel": 85,
    "preprocessing": 85,
    "measures": 90,
    "measurements": 85,
    "questionnaires": 90,
    "scales": 85,
    "assessment": 80,
    "statistical analysis": 85,
    "depression": 75,
    "anxiety": 70,
    "trauma": 65,
    "adversity": 60,
    "stress": 65,
    "genetics": 75,
    "blood": 70,
    "biomarker": 70,
    "medication": 80,
    "longitudinal": 80,
    "follow-up": 80,
    "results": 95,
    "findings": 90,
    "conclusion": 85,
    "discussion": 75,
}


def _parse_sections(text: str) -> list[tuple[str, str]]:
    """Parse paper text into (heading, content) sections.

    Handles headings like:
      # Heading
      ## Heading
      ### Heading
      Heading
      1. Heading
      1.1 Heading
    """
    sections = []
    lines = text.split('\n')
    current_heading = None
    current_content_lines = []

    for line in lines:
        # Check if this is a heading line
        stripped = line.strip()
        is_heading = False

        # Markdown headings (#, ##, ###)
        if stripped.startswith('#'):
            is_heading = True
        # Numbered headings (e.g., "1. Methods", "2.1 Participants")
        elif _re.match(r'^\d+[\.\)]\s+[A-Z][a-z]+', stripped):
            is_heading = True
        # All-caps heading (short line, all uppercase)
        elif stripped == stripped.upper() and len(stripped) < 80 and len(stripped.split()) <= 10:
            is_heading = True

        if is_heading and current_heading is not None:
            # Save previous section
            sections.append((current_heading, '\n'.join(current_content_lines)))
            current_heading = stripped.lstrip('#').strip()
            current_heading = _re.sub(r'^\d+[\.\)]\s*', '', current_heading).strip()
            current_content_lines = []
        elif is_heading and current_heading is None:
            # First heading
            current_heading = stripped.lstrip('#').strip()
            current_heading = _re.sub(r'^\d+[\.\)]\s*', '', current_heading).strip()
            current_content_lines = []
        else:
            current_content_lines.append(line)

    # Don't forget the last section
    if current_heading is not None:
        sections.append((current_heading, '\n'.join(current_content_lines)))

    return sections


def _section_matches_heading(heading: str, keywords: list[str]) -> bool:
    """Check if a heading matches any of the important keywords."""
    heading_lower = heading.lower()
    for kw in keywords:
        if kw.lower() in heading_lower:
            return True
    return False


def _section_matches_content(content: str, keywords: list[str], max_chars: int = 500) -> bool:
    """Check if the beginning of a section's content matches any keyword."""
    check_text = content[:max_chars].lower()
    for kw in keywords:
        if kw.lower() in check_text:
            return True
    return False


def _get_section_priority(heading: str, keywords: list[str]) -> int:
    """Get the priority score for a section based on its heading."""
    heading_lower = heading.lower()
    max_priority = 0

    # Direct match with known sections
    for sec_name, priority in _SECTION_PRIORITY.items():
        if sec_name in heading_lower:
            max_priority = max(max_priority, priority)

    return max_priority


def _build_text_pack(
    text: str,
    paper_record: dict | None,
    max_chars: int,
) -> tuple[str, bool]:
    """Build a section-aware text pack for the LLM.

    Returns (packed_text, was_packed) where was_packed indicates if truncation
    was needed.
    """
    sections = _parse_sections(text)

    # Separate abstract and other sections
    abstract_content = ""
    other_sections: list[tuple[str, str]] = []

    for heading, content in sections:
        heading_lower = heading.lower().strip()
        if "abstract" in heading_lower:
            abstract_content = content.strip()
        else:
            other_sections.append((heading, content))

    # Build priority list of important sections
    important_sections: list[tuple[str, str, int]] = []
    for heading, content in other_sections:
        priority = _get_section_priority(heading, _IMPORTANT_SECTION_KEYWORDS)
        if priority > 0 or _section_matches_content(content, _IMPORTANT_SECTION_KEYWORDS):
            # Boost priority if keyword found in content
            if not _section_matches_heading(heading, _IMPORTANT_SECTION_KEYWORDS):
                if _section_matches_content(content, _IMPORTANT_SECTION_KEYWORDS):
                    priority = max(priority, 70)
            important_sections.append((heading, content, priority))

    # Sort by priority (highest first), then by length (shorter first for same priority)
    important_sections.sort(key=lambda x: (-x[2], len(x[1])))

    # Also include all other sections with low priority
    low_priority = [(h, c, 5) for h, c in other_sections
                    if not _section_matches_heading(h, _IMPORTANT_SECTION_KEYWORDS)
                    and not _section_matches_content(c, _IMPORTANT_SECTION_KEYWORDS)]

    # Build the text pack
    result_parts = []
    current_len = 0

    # Add metadata (title, citation)
    meta_text = ""
    if paper_record:
        title = paper_record.get("title", "")
        if title:
            meta_text += f"# Title: {title}\n\n"
        authors = paper_record.get("authors", "")
        if authors:
            meta_text += f"# Authors: {authors}\n\n"
        journal = paper_record.get("journal", "")
        year = paper_record.get("year", "")
        if journal or year:
            pub_info = []
            if journal:
                pub_info.append(journal)
            if year:
                pub_info.append(year)
            meta_text += f"# Publication: {'; '.join(pub_info)}\n\n"

    if meta_text:
        result_parts.append(meta_text.strip())
        current_len += len(meta_text)

    # Add abstract (always included first)
    if abstract_content:
        abstract_section = f"# Abstract\n\n{abstract_content}"
        abstract_len = len(abstract_section) + 2  # +2 for \n\n separator
        if current_len + abstract_len <= max_chars:
            result_parts.append(abstract_section)
            current_len += abstract_len

    # Add high-priority sections first (priority >= 80)
    high_priority = [(h, c, p) for h, c, p in important_sections if p >= 80]
    medium_priority = [(h, c, p) for h, c, p in important_sections if 50 <= p < 80]
    low_priority_final = [(h, c, p) for h, c, p in important_sections if p < 50] + low_priority

    for heading, content, _priority in high_priority:
        section_text = f"\n\n# {heading}\n\n{content}"
        section_len = len(section_text)
        if current_len + section_len <= max_chars:
            result_parts.append(section_text)
            current_len += section_len

    # Add medium-priority sections if space allows
    for heading, content, _priority in medium_priority:
        section_text = f"\n\n# {heading}\n\n{content}"
        section_len = len(section_text)
        if current_len + section_len <= max_chars:
            result_parts.append(section_text)
            current_len += section_len

    # Add low-priority sections if space allows (up to 50% of remaining budget)
    remaining_budget = max_chars - current_len
    low_priority_limit = int(remaining_budget * 0.3)  # Use up to 30% for low priority

    for heading, content, _priority in low_priority_final:
        section_text = f"\n\n# {heading}\n\n{content}"
        section_len = len(section_text)
        if current_len + section_len <= max_chars and section_len <= low_priority_limit:
            result_parts.append(section_text)
            current_len += section_len

    packed_text = '\n'.join(result_parts)
    was_packed = len(packed_text) < len(text)

    return packed_text, was_packed


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_paper(paper_id: str) -> None:
    """Extract broad dataset features for a single paper.

    Steps:
      1. Load the paper record from papers.json
      2. Look for the local PDF
      3. Convert PDF to text/markdown
      4. Run LLM-based extraction (or fallback)
      5. Validate and parse the result
      6. Save extracted features JSON
      7. Merge back into papers.json
    """
    # --- 1. Load paper record ---
    papers = _load_papers_json()
    record = None
    record_index = None
    for i, p in enumerate(papers):
        if p.get("paper_id") == paper_id:
            record = p
            record_index = i
            break

    if record is None:
        console.print(f"Paper '{paper_id}' not found in {PAPERS_JSON}")
        return

    console.print(f"Processing paper: {paper_id}")
    if record.get("title"):
        console.print(f"  Title: {record['title']}")

    # --- 2. Find PDF ---
    pdf_path = PDFS_DIR / f"{paper_id}.pdf"
    if not pdf_path.exists():
        console.print(f"PDF not found: {pdf_path}")
        _update_paper_status(papers, record_index, paper_id, "missing_pdf",
                             f"PDF not found at {pdf_path}")
        _save_papers_json(papers)
        return

    # --- 3. Convert PDF to text (reuse existing by default) ---
    text_path = TEXT_DIR / f"{paper_id}.md"
    
    # Check if --force-pdf flag is set (passed via sys.argv or env)
    force_pdf = os.environ.get("REFINE_FORCE_PDF", "false").lower() == "true"
    
    if text_path.exists() and not force_pdf:
        console.print(f"Using cached text: {text_path}")
        text = text_path.read_text(encoding="utf-8")
    else:
        if force_pdf:
            console.print("REFINE_FORCE_PDF=true: rerunning Docling despite existing text file.")
        try:
            text = pdf_to_text(pdf_path, output_path=text_path)
        except Exception as exc:
            console.print(f"PDF conversion failed: {exc}")
            _update_paper_status(papers, record_index, paper_id, "failed",
                                 f"PDF conversion failed: {exc}")
            _save_papers_json(papers)
            return

    # --- 4. LLM extraction with section-aware text packing ---
    prompt_template = _load_prompt_template()

    # ------------------------------------------------------------------
    # Context length: read from environment variables (priority order).
    #   1. REFINE_LLM_CONTEXT_LENGTH  (paper-specific override)
    #   2. LLM_CONTEXT_LENGTH         (global, shared with other modules)
    #   3. Default 32768
    # ------------------------------------------------------------------
    _ctx_env_names = ["REFINE_LLM_CONTEXT_LENGTH", "LLM_CONTEXT_LENGTH"]
    _context_length: int | None = None
    for env_name in _ctx_env_names:
        val = os.environ.get(env_name)
        if val is not None:
            try:
                _context_length = int(val)
                break
            except ValueError:
                logger.warning("Invalid value for %s: %r", env_name, val)

    MAX_CONTEXT_TOKENS = _context_length if _context_length is not None else 32768

    # ------------------------------------------------------------------
    # Paper-text token budget.
    #   If REFINE_LLM_TEXT_TOKEN_BUDGET is set, use it directly.
    #   Otherwise compute from context length minus overhead minus reserve.
    # ------------------------------------------------------------------
    _raw_text_budget = os.environ.get("REFINE_LLM_TEXT_TOKEN_BUDGET")
    if _raw_text_budget is not None:
        try:
            TEXT_TOKEN_BUDGET = int(_raw_text_budget)
            text_budget_from_env = True
        except ValueError:
            logger.warning("Invalid value for REFINE_LLM_TEXT_TOKEN_BUDGET: %r; computing automatically", _raw_text_budget)
            text_budget_from_env = False
    else:
        TEXT_TOKEN_BUDGET = None
        text_budget_from_env = False

    TOKEN_CHAR_RATIO = 4.0  # Approximate characters per token

    # Measure the full prompt overhead: system_prompt + template with minimal placeholders
    min_id = "R"  # single char to minimize placeholder size impact
    min_placeholder_text = ""  # empty text to measure pure overhead
    measured_full_prompt = SYSTEM_PROMPT + "\n\n" + prompt_template.replace("{{PAPER_ID}}", min_id).replace("{{PAPER_TEXT}}", min_placeholder_text)

    # Total tokens for the full prompt with zero text content (system + template overhead)
    overhead_tokens = int(len(measured_full_prompt) / TOKEN_CHAR_RATIO)

    # Reserve extra space for LLM response (minimum 2048 chars / ~512 tokens safety margin)
    reserved_chars = 2048

    if not text_budget_from_env:
        # Compute paper-text budget from context length minus overhead and reserve
        available_for_text_tokens = MAX_CONTEXT_TOKENS - overhead_tokens - int(reserved_chars / TOKEN_CHAR_RATIO)
        if available_for_text_tokens < 0:
            available_for_text_tokens = 256  # fallback minimum (very conservative)
        TEXT_TOKEN_BUDGET = max(available_for_text_tokens, 256)

    # Convert token budget → char budget for the packing function
    max_text_chars = int(TEXT_TOKEN_BUDGET * TOKEN_CHAR_RATIO)
    
    # Ensure minimum text length for meaningful content
    min_text_chars = 10000  # Keep at least 10K chars (~2.5K tokens)
    max_text_chars = max(max_text_chars, min_text_chars)

    original_text_len = len(text)
    original_text_tokens = int(original_text_len / TOKEN_CHAR_RATIO)
    was_packed = False

    # Re-derive max_text_tokens for display purposes
    max_text_tokens = int(max_text_chars / TOKEN_CHAR_RATIO)

    # ------------------------------------------------------------------
    # Diagnostics: print before extraction so the user can see what's
    # happening regardless of whether packing is triggered.
    # ------------------------------------------------------------------
    console.print(f"\n--- Extraction Context Budget ---")
    console.print(f"  Context length (max input tokens):   {MAX_CONTEXT_TOKENS}")
    if text_budget_from_env:
        console.print(f"  Text token budget (env override):     {TEXT_TOKEN_BUDGET}")
    else:
        console.print(f"  Paper text token budget:             {TEXT_TOKEN_BUDGET}  (computed from context {MAX_CONTEXT_TOKENS} - overhead {overhead_tokens} - reserve {int(reserved_chars / TOKEN_CHAR_RATIO)})")
    console.print(f"  Original paper text length:          {original_text_len} chars (~{original_text_tokens} tokens)")
    console.print("--- End Context Budget ---\n")

    if len(text) > max_text_chars:
        console.print(f"Text exceeds text budget ({len(text)} chars ≈ {len(text)//TOKEN_CHAR_RATIO:.0f} tokens > {max_text_tokens} text tokens). Using section-aware text packing...")

        # Build a section-aware text pack
        packed_text, was_packed = _build_text_pack(text, record, max_text_chars)

        # Save the actual packed text to disk for debugging/inspection
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        text_pack_path = LOGS_DIR / f"{paper_id}.llm_text_pack.txt"
        text_pack_path.write_text(packed_text, encoding="utf-8")
        console.print(f"  Saved LLM text pack to: {text_pack_path}")

        prompt = prompt_template.replace("{{PAPER_ID}}", paper_id).replace("{{PAPER_TEXT}}", packed_text)
    else:
        packed_text = text
        was_packed = False

        # Still save the text pack even when no packing needed
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        text_pack_path = LOGS_DIR / f"{paper_id}.llm_text_pack.txt"
        text_pack_path.write_text(packed_text, encoding="utf-8")

        prompt = prompt_template.replace("{{PAPER_ID}}", paper_id).replace("{{PAPER_TEXT}}", text)

    # Print post-packing diagnostics
    packed_len = len(packed_text)
    packed_tokens = int(packed_len / TOKEN_CHAR_RATIO)

    # Estimate total prompt size that will be sent to LLM
    full_prompt_for_llm = SYSTEM_PROMPT + "\n\n" + prompt_template.replace("{{PAPER_ID}}", paper_id).replace("{{PAPER_TEXT}}", packed_text)
    estimated_total_tokens = int(len(full_prompt_for_llm) / TOKEN_CHAR_RATIO)

    console.print(f"\n--- Packing Diagnostics ---")
    console.print(f"  Original text length:          {original_text_len} chars (~{original_text_tokens} tokens)")
    console.print(f"  Packed text length:            {packed_len} chars (~{packed_tokens} tokens)")
    console.print(f"  Packing applied:               {'Yes' if was_packed else 'No'}")
    console.print(f"  Estimated total prompt tokens: {estimated_total_tokens}")
    console.print(f"  Context window limit:          {MAX_CONTEXT_TOKENS} tokens")
    console.print("--- End Diagnostics ---\n")

    raw_response, llm_metadata = call_llm(prompt, SYSTEM_PROMPT, paper_id=paper_id)

    # Print preview of raw response (first 500 chars)
    console.print(f"\n--- LLM Response Preview (first 500 chars) ---")
    console.print(raw_response[:500])
    console.print("--- End Preview ---\n")

    extracted = None
    extraction_status = "completed"
    extraction_notes = None

    # Check if this is the no-LLM fallback template
    if llm_metadata and llm_metadata.get("status") == "template_no_llm":
        console.print("Using no-LLM fallback template (REFINE_LLM_PROVIDER=none).")
        extracted = ExtractedFeatures(
            paper_id=paper_id,
            dataset_features_needed={k: "unclear" for k in FEATURE_KEYS},
            website_card={"short_description": None, "dataset_features_summary": []},
            extraction_status="template_no_llm",
            extraction_notes="No LLM configured. Fallback template generated with all dataset features set to unclear.",
        )
    else:
        # --- 5. Validate and parse ---
        try:
            extracted = _validate_and_parse(raw_response, paper_id)
            console.print("JSON parsing and schema validation: SUCCESS")
        except ValueError as ve:
            console.print(f"JSON parsing/validation: FAILED - {ve}")
            
            # When LLM is configured but parsing fails, do NOT silently fall back.
            extraction_status = "failed"
            extraction_notes = f"LLM response failed JSON validation: {ve}"
            console.print(f"LLM configured but parsing failed. Status set to 'failed'.")
            
            # Create a minimal extracted object for saving (with failure status)
            extracted = ExtractedFeatures(
                paper_id=paper_id,
                dataset_features_needed={k: "unclear" for k in FEATURE_KEYS},
                website_card={"short_description": None, "dataset_features_summary": []},
                extraction_status="failed",
                extraction_notes=extraction_notes,
            )

    # --- 6. Save extracted features JSON ---
    if extracted is None:
        console.print("ERROR: No extracted data available.")
        return
    
    features_path = EXTRACTED_DIR / f"{paper_id}.features.json"
    features_path.parent.mkdir(parents=True, exist_ok=True)
    features_path.write_text(
        json.dumps(extracted.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    console.print(f"Saved features: {features_path}")

    # --- 7. Merge back into papers.json ---
    _merge_into_papers(papers, record_index, extracted)
    _save_papers_json(papers)

    console.print(f"Extraction complete for {paper_id}: status={extraction_status}")

    # Log
    _log_extraction(paper_id, extraction_status, extraction_notes)


# ---------------------------------------------------------------------------
# extract-all
# ---------------------------------------------------------------------------

def extract_all(limit: int | None = None, force: bool = False) -> None:
    """Extract broad dataset features for the first N papers that have a local PDF.

    Args:
        limit: Maximum number of papers to process. If None, processes all eligible papers.
        force: If True, re-extract even if features already exist (overwrites them).
    """
    # Default to processing all eligible papers when no limit specified
    if limit is None:
        limit = 10000  # Large default to effectively process all papers

    if force:
        console.print("Force mode enabled: will re-extract all eligible papers regardless of existing files.")

    papers = _load_papers_json()
    processed = 0
    skipped = 0

    for i, record in enumerate(papers):
        if processed >= limit:
            break

        paper_id = record.get("paper_id", "")
        if not paper_id:
            skipped += 1
            continue

        # Skip if no local PDF
        pdf_path = PDFS_DIR / f"{paper_id}.pdf"
        if not pdf_path.exists():
            skipped += 1
            continue

        # Check if already has a completed extraction (skip unless force mode)
        features_path = EXTRACTED_DIR / f"{paper_id}.features.json"
        if features_path.exists() and not force:
            try:
                existing = json.loads(features_path.read_text(encoding="utf-8"))
                if existing.get("extraction_status") == "completed":
                    console.print(f"Skipping {paper_id} (already extracted)")
                    skipped += 1
                    continue
            except Exception:
                pass  # Corrupted file, re-extract

        console.print(f"\n--- Processing {paper_id} ({processed + 1}/{limit}) ---")
        extract_paper(paper_id)
        processed += 1

    console.print(f"\nextract-all complete: processed={processed}, skipped={skipped}")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_papers_json() -> list[dict]:
    """Load papers.json, returning an empty list if missing or invalid."""
    if not PAPERS_JSON.exists():
        console.print(f"{PAPERS_JSON} not found. Creating empty database.")
        return []
    try:
        text = PAPERS_JSON.read_text(encoding="utf-8")
        data = json.loads(text)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError as exc:
        console.print(f"Failed to parse {PAPERS_JSON}: {exc}")
        return []


def _save_papers_json(papers: list[dict]) -> None:
    """Save papers list back to papers.json."""
    PAPERS_JSON.parent.mkdir(parents=True, exist_ok=True)
    PAPERS_JSON.write_text(
        json.dumps(papers, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    console.print(f"Updated {PAPERS_JSON}")


def _update_paper_status(
    papers: list[dict],
    index: int,
    paper_id: str,
    status: str,
    notes: str | None = None,
) -> None:
    """Update a paper record's extraction status fields."""
    papers[index]["extraction"] = {
        "status": status,
        "notes": notes,
    }
    papers[index]["extraction_status"] = status
    papers[index]["extraction_notes"] = notes


def _merge_into_papers(
    papers: list[dict],
    index: int,
    extracted: ExtractedFeatures,
) -> None:
    """Merge extracted features into the paper record at *index*."""
    record = papers[index]

    # Merge dataset_features_needed
    record["dataset_features_needed"] = extracted.dataset_features_needed

    # Merge website_card - replace entirely when extracted data is available
    wc = _as_dict(extracted.website_card)
    if wc:
        record["website_card"] = {}
        if wc.get("short_description") is not None:
            record["website_card"]["short_description"] = wc["short_description"]
        if wc.get("dataset_features_summary"):
            record["website_card"]["dataset_features_summary"] = wc["dataset_features_summary"]
        if wc.get("plain_text_summary") is not None:
            record["website_card"]["plain_text_summary"] = wc["plain_text_summary"]

    # Merge extraction info
    ext_status = extracted.extraction_status
    ext_notes = extracted.extraction_notes
    record["extraction"] = {
        "status": ext_status,
        "notes": ext_notes,
    }
    record["extraction_status"] = ext_status
    record["extraction_notes"] = ext_notes

    # Ensure extraction_status top-level key exists for backward compat
    if "extraction_status" not in record:
        record["extraction_status"] = extracted.extraction_status
    if "extraction_notes" not in record:
        record["extraction_notes"] = extracted.extraction_notes


def _make_fallback(paper_id: str) -> ExtractedFeatures:
    """Create a fallback extraction with all features set to 'unclear'."""
    features = {k: "unclear" for k in FEATURE_KEYS}
    return ExtractedFeatures(
        paper_id=paper_id,
        dataset_features_needed=features,
        website_card={"short_description": None, "dataset_features_summary": []},
        extraction_status="completed",
        extraction_notes="Fallback template (no LLM available)",
    )


def _log_extraction(paper_id: str, status: str, notes: str | None) -> None:
    """Write a simple log entry."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / "extraction.log"
    import datetime
    timestamp = datetime.datetime.utcnow().isoformat()
    line = f"{timestamp} | {paper_id} | {status}"
    if notes:
        line += f" | {notes}"
    line += "\n"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line)