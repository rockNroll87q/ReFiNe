"""LLM client for ReFiNe extraction.

Supports three providers:
  - ``none``                          – no LLM; returns a valid template with all features ``"unclear"``
  - ``openai_compatible``             – calls any OpenAI-compatible HTTP API

Configuration is done entirely through environment variables:

  * ``REFINE_LLM_PROVIDER``           – ``none`` (default), ``openai_compatible``
  * ``REFINE_LLM_BASE_URL``           – e.g. ``http://localhost:8000/v1``
  * ``REFINE_LLM_MODEL``              – e.g. ``qwen/qwen3.6-35b-a3b``
  * ``REFINE_LLM_API_KEY``            – API key (required for ``openai_compatible``)
  * ``REFINE_MAX_CONTEXT_TOKENS``     – max tokens for context window (default: 131072)
  * ``REFINE_N_KEEP``                 – number of tokens to keep in context (default: 8192)
"""

import os
from pathlib import Path


from .schema import FEATURE_KEYS

class Console:
    def print(self, *args, **kwargs):
        print(*args)

console = Console()

# ---------------------------------------------------------------------------
# Provider: none
# ---------------------------------------------------------------------------

def _call_none(prompt: str, system_prompt: str, paper_id: str | None = None) -> tuple[str, dict | None]:
    """Return a valid JSON template with all features set to ``unclear``.
    
    Returns:
        (raw_response, metadata): The raw JSON string and optional metadata dict.
        metadata includes 'status' for the extraction_status field.
    """
    features = {k: "unclear" for k in FEATURE_KEYS}
    json_str = (
        '{"paper_id": "PLACEHOLDER", '
        '"dataset_features_needed": '
        + _json_encode(features)
        + ', '
        '"website_card": {"short_description": null, "dataset_features_summary": []}, '
        '"extraction_status": "template_no_llm", '
        '"extraction_notes": "No LLM configured. Fallback template generated with all dataset features set to unclear."}'
    )
    result = json_str.replace('"paper_id": "PLACEHOLDER"', f'"paper_id": "{paper_id}"') if paper_id else json_str.replace('"paper_id": "PLACEHOLDER"', '"paper_id": ""')
    
    # Save the raw response for debugging
    _save_raw_response(result, prompt, paper_id)
    
    return result, {"status": "template_no_llm"}


# ---------------------------------------------------------------------------
# Provider: openai_compatible
# ---------------------------------------------------------------------------

def _call_openai_compatible(prompt: str, system_prompt: str, paper_id: str | None = None) -> tuple[str, dict | None]:
    """Call an OpenAI-compatible chat completions endpoint.
    
    Returns:
        (raw_response, metadata): The raw response string and optional metadata dict.
        metadata is None for openai_compatible provider (status determined by parsing).
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package is required for openai_compatible provider")

    base_url = os.environ.get("REFINE_LLM_BASE_URL", "http://localhost:8000/v1")
    model = os.environ.get("REFINE_LLM_MODEL", "gpt-3.5-turbo")
    api_key = os.environ.get("REFINE_LLM_API_KEY", "dummy")

    client = OpenAI(base_url=base_url, api_key=api_key)

    response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=int(os.environ.get("REFINE_MAX_CONTEXT_TOKENS", "32768")),
        )

    raw_content = response.choices[0].message.content
    
    # Save the raw response for debugging
    _save_raw_response(raw_content, prompt, paper_id)
    
    return raw_content, None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_encode(obj: object) -> str:
    """Simple JSON encoder (avoids importing json inside the function scope)."""
    import json
    return json.dumps(obj, ensure_ascii=False)


def _save_raw_response(raw_response: str, prompt: str, paper_id: str | None = None) -> None:
    """Save raw LLM response and prompt to logs directory for debugging."""
    if not paper_id:
        return
    
    LOGS_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Save raw response
    response_path = LOGS_DIR / f"{paper_id}.llm_raw_response.txt"
    response_path.write_text(raw_response, encoding="utf-8")
    
    # Save prompt
    prompt_path = LOGS_DIR / f"{paper_id}.llm_prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")


def call_llm(prompt: str, system_prompt: str, paper_id: str | None = None) -> tuple[str, dict | None]:
    """Call the configured LLM provider and return (raw_response, metadata).
    
    Args:
        prompt: The user prompt text.
        system_prompt: The system prompt text.
        paper_id: Optional paper ID for logging/debugging purposes.
    
    Returns:
        Tuple of (raw_response_string, metadata_dict_or_None).
        For 'none' provider: metadata contains {'status': 'template_no_llm'}
        For 'openai_compatible' provider: metadata is None
    
    Falls back to ``none`` when no provider is configured or when the
    configured provider is ``none``.
    """
    provider = os.environ.get("REFINE_LLM_PROVIDER", "none").strip().lower()

    if provider == "none" or provider == "":
        console.print("No LLM configured (provider=none). Using fallback template.")
        return _call_none(prompt, system_prompt, paper_id)
    elif provider == "openai_compatible":
        console.print(
            f"LLM provider=openai_compatible, model={os.environ.get('REFINE_LLM_MODEL')}, "
            f"base_url={os.environ.get('REFINE_LLM_BASE_URL')}"
        )
        return _call_openai_compatible(prompt, system_prompt, paper_id)
    else:
        console.print(f"Unknown provider '{provider}'. Falling back to none.")
        return _call_none(prompt, system_prompt, paper_id)
