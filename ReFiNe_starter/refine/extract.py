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
    import re as _re
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

def _truncate_text_for_context(text: str, max_chars: int) -> str:
    """Truncate paper text to fit within a context window limit.
    
    Preserves the abstract (beginning) and key sections from the end 
    of the paper (results/conclusion).
    """
    if len(text) <= max_chars:
        return text
    
    marker = "\n\n[... TEXT TRUNCATED DUE TO CONTEXT WINDOW LIMIT ...]\n\n"
    available_chars = max_chars - len(marker)
    
    sections = text.split('\n\n')
    split_point = int(len(sections) * 0.25)
    
    min_from_start = max(3, int(len(sections) * 0.1))
    min_from_end = max(5, int(len(sections) * 0.2))
    
    if split_point < min_from_start:
        split_point = min_from_start
    if len(sections) - split_point < min_from_end:
        split_point = len(sections) - min_from_end
    
    start_sections = sections[:split_point]
    end_sections = sections[split_point:]
    
    result_parts = []
    current_len = 0
    
    for section in start_sections:
        section_text = section + '\n\n'
        if current_len + len(section_text) <= available_chars:
            result_parts.append(section)
            current_len += len(section_text)
        else:
            break
    
    for section in reversed(end_sections):
        section_text = '\n\n' + section
        if current_len + len(section_text) <= available_chars:
            result_parts.append(section)
            current_len += len(section_text)
        else:
            break
    
    result = '\n\n'.join(result_parts)
    
    if len(result) > max_chars:
        result = result[:max_chars]
        last_space = result.rfind(' ')
        if last_space > max_chars * 0.5:
            result = result[:last_space]
    
    return result + marker


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

    # --- 4. LLM extraction with context window truncation ---
    prompt_template = _load_prompt_template()
    
    # Read context length from environment, default to 32768 (LM Studio's safe default)
    MAX_CONTEXT_TOKENS = int(os.environ.get("REFINE_MAX_CONTEXT_TOKENS", "32768"))
    TOKEN_CHAR_RATIO = 4.0  # Approximate characters per token
    
    # Estimate prompt overhead (system prompt + template structure)
    system_prompt_tokens = int(len(SYSTEM_PROMPT) / TOKEN_CHAR_RATIO)
    template_overhead = int(len(prompt_template.replace("{{PAPER_TEXT}}", "").replace("{{PAPER_ID}}", "")) / TOKEN_CHAR_RATIO)
    
    # Reserve extra space for LLM response and safety margin (20%)
    reserved_tokens = int((system_prompt_tokens + template_overhead) * 1.2)
    
    max_text_tokens = MAX_CONTEXT_TOKENS - system_prompt_tokens - template_overhead - reserved_tokens
    max_text_chars = int(max_text_tokens * TOKEN_CHAR_RATIO)
    
    # Ensure minimum text length for meaningful content
    min_text_chars = 10000  # Keep at least 10K chars (~2.5K tokens)
    max_text_chars = max(max_text_chars, min_text_chars)
    
    if len(text) > max_text_chars:
        console.print(f"Text exceeds context limit ({len(text)} chars ≈ {len(text)//TOKEN_CHAR_RATIO} tokens > {max_text_tokens} text tokens). Truncating...")
        
        # Keep abstract (beginning) and key sections (end/results)
        truncated_text = _truncate_text_for_context(text, max_text_chars)
        prompt = prompt_template.replace("{{PAPER_ID}}", paper_id).replace("{{PAPER_TEXT}}", truncated_text)
    else:
        prompt = prompt_template.replace("{{PAPER_ID}}", paper_id).replace("{{PAPER_TEXT}}", text)

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

def extract_all(limit: int = 10) -> None:
    """Extract broad dataset features for the first N papers that have a local PDF
    and do not already have a completed extraction.

    Args:
        limit: Maximum number of papers to process.
    """
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

        # Skip if already extracted
        pdf_path = PDFS_DIR / f"{paper_id}.pdf"
        if not pdf_path.exists():
            skipped += 1
            continue

        # Check if already has a completed extraction
        features_path = EXTRACTED_DIR / f"{paper_id}.features.json"
        if features_path.exists():
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

    # Merge website_card
    wc = _as_dict(extracted.website_card)
    if wc.get("short_description") is not None:
        record.setdefault("website_card", {})["short_description"] = wc["short_description"]
    if wc.get("dataset_features_summary"):
        record.setdefault("website_card", {})["dataset_features_summary"] = wc["dataset_features_summary"]

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