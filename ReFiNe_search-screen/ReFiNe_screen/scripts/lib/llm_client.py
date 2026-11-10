"""LLM client for ReFiNe_screen (abstract + full-text screening).

Configuration via environment variables (see ReFiNe_Hub/.env for current values):

  * REFINE_LLM_PROVIDER      – must be ``openai_compatible``
  * REFINE_LLM_BASE_URL      – e.g. http://172.17.0.1:1235/v1
  * REFINE_LLM_MODEL         – e.g. local/qwen3.8-27b
  * REFINE_LLM_API_KEY       – API key (default "lm-studio")
  * REFINE_MAX_OUTPUT_TOKENS – output cap (default 32768)
  * REFINE_ENABLE_THINKING   – "true" to keep Qwen3-style hidden reasoning (default false)
  * REFINE_LLM_RETRIES       – attempts per call on connection/server errors (default 6)
  * REFINE_LLM_BACKOFF_S     – initial backoff seconds, doubled each retry, capped at 60 (default 5)
  * REFINE_LLM_TIMEOUT_S     – per-request timeout seconds (default 600)

Robustness (added 2026-11-04 after an LM Studio disconnect turned 144 abstract
screens into instant ``llm_error`` artifacts):
  - one client per process (thread-safe, reused) instead of one per call;
  - transient errors (connection refused/reset, timeouts, HTTP 5xx/429) are
    retried with exponential backoff, so a short server restart is ridden out;
  - ``health_check()`` pings the server before a run starts;
  - ``CircuitBreaker`` lets the run loop abort after N consecutive call
    failures instead of burning through the whole queue during an outage.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time

from common import ROOT, norm_llm_value

_client = None
_client_lock = threading.Lock()


class LLMCallError(RuntimeError):
    """The endpoint could not be reached / answered after all retries."""


# ---------------------------------------------------------------------------
# Client + configuration
# ---------------------------------------------------------------------------

def _settings() -> dict:
    provider = os.environ.get("REFINE_LLM_PROVIDER", "").strip().lower()
    if provider != "openai_compatible":
        raise RuntimeError("REFINE_LLM_PROVIDER must be 'openai_compatible' "
                           "(see ReFiNe_Hub/.env for the local LM Studio configuration)")
    base_url = os.environ.get("REFINE_LLM_BASE_URL", "")
    model = os.environ.get("REFINE_LLM_MODEL", "")
    if not base_url or not model:
        raise RuntimeError("REFINE_LLM_BASE_URL and REFINE_LLM_MODEL must be set")
    return {
        "base_url": base_url,
        "model": model,
        "api_key": os.environ.get("REFINE_LLM_API_KEY", "lm-studio"),
        "max_tokens": int(os.environ.get("REFINE_MAX_OUTPUT_TOKENS", "32768")),
        "thinking": os.environ.get("REFINE_ENABLE_THINKING", "false").strip().lower()
        not in ("0", "false", "no", "off"),
        "retries": max(1, int(os.environ.get("REFINE_LLM_RETRIES", "6"))),
        "backoff": float(os.environ.get("REFINE_LLM_BACKOFF_S", "5")),
        "timeout": float(os.environ.get("REFINE_LLM_TIMEOUT_S", "600")),
    }


def get_client():
    """Process-wide OpenAI client (httpx pool is thread-safe; reused across calls)."""
    global _client
    with _client_lock:
        if _client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise RuntimeError("openai package is required: pip install openai") from exc
            s = _settings()
            # max_retries=0: retries are handled below so the backoff is visible/configurable.
            _client = OpenAI(base_url=s["base_url"], api_key=s["api_key"],
                             timeout=s["timeout"], max_retries=0)
        return _client


def _is_transient(exc: Exception) -> bool:
    """True for errors worth retrying: connection problems, timeouts, 5xx, 429."""
    try:
        import openai
    except ImportError:
        return False
    if isinstance(exc, (openai.APIConnectionError, openai.APITimeoutError,
                        openai.InternalServerError, openai.RateLimitError)):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status >= 500


def health_check() -> tuple[bool, str]:
    """Ping the endpoint (GET /models). Returns (ok, message)."""
    try:
        s = _settings()
        models = [m.id for m in get_client().models.list().data]
    except Exception as exc:  # noqa: BLE001 — report any failure as unhealthy
        return False, f"LLM endpoint not reachable: {exc}"
    note = "" if s["model"] in models else f" (warning: {s['model']!r} not in served models {models[:5]})"
    return True, f"LLM endpoint OK at {s['base_url']}{note}"


# ---------------------------------------------------------------------------
# Debug logging
# ---------------------------------------------------------------------------

def _save_raw_response(raw_response: str, prompt: str, paper_id: str | None, stage: str) -> None:
    """Save prompt + raw response to data/logs/<stage>/ (debug only; never fails the call)."""
    if not paper_id:
        return
    safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", paper_id)
    logs_dir = ROOT / "data" / "logs" / stage
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / f"{safe_id}.llm_raw_response.txt").write_text(raw_response or "", encoding="utf-8")
        (logs_dir / f"{safe_id}.llm_prompt.txt").write_text(prompt, encoding="utf-8")
    except OSError as exc:
        print(f"[warn] could not save LLM debug logs for {paper_id}: {exc}")


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------

def call_llm(prompt: str, system_prompt: str = "", paper_id: str | None = None,
             stage: str = "misc") -> tuple[str, dict]:
    """Call the configured OpenAI-compatible endpoint, retrying transient failures.

    Returns (raw_response_string, {"model": ...}). Raises LLMCallError when the
    endpoint stays unreachable after REFINE_LLM_RETRIES attempts, or re-raises a
    non-transient error (e.g. HTTP 400) immediately.
    """
    s = _settings()
    client = get_client()
    messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + \
               [{"role": "user", "content": prompt}]
    params = dict(model=s["model"], messages=messages, temperature=0.0, max_tokens=s["max_tokens"])
    # Qwen3-style thinking off by default (~3x faster on a probe); see module docstring.
    if not s["thinking"]:
        params["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

    delay = s["backoff"]
    last_exc: Exception | None = None
    for attempt in range(1, s["retries"] + 1):
        try:
            response = client.chat.completions.create(**params)
            break
        except Exception as exc:  # noqa: BLE001
            # Endpoint rejected the thinking-toggle flag -> retry once without it.
            if params.get("extra_body") and any(
                    t in str(exc).lower() for t in ("400", "bad request", "unsupported")):
                del params["extra_body"]
                continue
            if not _is_transient(exc):
                raise
            last_exc = exc
            if attempt == s["retries"]:
                raise LLMCallError(f"endpoint failed after {attempt} attempts: {exc}") from exc
            print(f"[retry] {paper_id or ''} attempt {attempt}/{s['retries']} failed "
                  f"({type(exc).__name__}); sleeping {delay:.0f}s", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    else:  # pragma: no cover — loop always breaks or raises
        raise LLMCallError(f"endpoint failed: {last_exc}")

    raw_content = response.choices[0].message.content or ""  # thinking models can return None
    _save_raw_response(raw_content, prompt, paper_id, stage)
    return raw_content, {"model": s["model"]}


# ---------------------------------------------------------------------------
# Output parsing / validation (moved here from screen_fulltext.py so both tiers
# share it without importing each other)
# ---------------------------------------------------------------------------

def _strip_fences(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        if "```" in s:
            s = s.rsplit("```", 1)[0]
    return s.strip()


def parse_rating(raw: str, paper_id: str, crit_ids: list[str]) -> tuple[dict | None, str]:
    """Validate the model's JSON answer. Returns (criteria_dict_or_None, error)."""
    try:
        obj = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(obj, dict):
        return None, "top-level JSON is not an object"
    if str(obj.get("candidate_id", "")).strip() != paper_id:
        return None, f"candidate_id mismatch (got {obj.get('candidate_id')!r})"
    crit = obj.get("criteria")
    if not isinstance(crit, dict):
        return None, "missing 'criteria' object"

    out: dict[str, dict] = {}
    for cid in crit_ids:
        entry = crit.get(cid)
        if not isinstance(entry, dict):
            return None, f"criterion '{cid}' missing or not an object"
        val = norm_llm_value(entry.get("value"))
        if val not in ("1", "0", "n/a"):
            return None, f"criterion '{cid}' has invalid value {entry.get('value')!r}"
        try:
            conf = float(entry.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        out[cid] = {"value": val, "confidence": conf, "evidence": str(entry.get("evidence", "")).strip()}
    return out, ""


def rate_with_retry(prompt: str, paper_id: str, crit_ids: list[str], system_prompt: str,
                    stage: str, breaker: "CircuitBreaker | None" = None) -> dict:
    """One rating: call + validate, with one re-ask on a malformed answer.

    Returns {"status": "ok", "criteria", "model"} or {"status": "llm_error", "error"}.
    Endpoint failures (after call_llm's own retries) are reported to `breaker`;
    successful calls reset it. Malformed answers do NOT count toward the breaker
    (the server is up; the model just answered badly).
    """
    err = ""
    for _attempt in (1, 2):
        try:
            raw, meta = call_llm(prompt, system_prompt, paper_id, stage)
        except LLMCallError as exc:
            if breaker:
                breaker.record_failure()
            return {"status": "llm_error", "error": f"call failed: {exc}"}
        if breaker:
            breaker.record_success()
        parsed, err = parse_rating(raw, paper_id, crit_ids)
        if parsed is not None:
            return {"status": "ok", "criteria": parsed, "model": meta.get("model", "")}
    return {"status": "llm_error", "error": f"parse failed after 2 attempts: {err}"}


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

class CircuitBreaker:
    """Trips after `threshold` consecutive endpoint failures (thread-safe).

    Each failure has already survived call_llm's retry/backoff (minutes, by
    default), so a few in a row means the server is genuinely down: stop the
    run rather than writing an llm_error artifact for every remaining paper.
    """

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._consecutive = 0
        self._lock = threading.Lock()
        self.tripped = threading.Event()

    def record_success(self) -> None:
        with self._lock:
            self._consecutive = 0

    def record_failure(self) -> None:
        with self._lock:
            self._consecutive += 1
            if self._consecutive >= self.threshold and not self.tripped.is_set():
                print(f"\n[ABORT] {self._consecutive} consecutive LLM endpoint failures — "
                      "stopping the run. Fix the server and re-run the same command; "
                      "finished papers are skipped.", flush=True)
                self.tripped.set()
