#!/usr/bin/env python3
"""Check the download-stage API keys before a run (one cheap call per service).

Reads ReFiNe_screen/.env (or ReFiNe_Hub/.env); environment variables win. Never
prints a key — only its last 4 characters.

  OPENALEX_API_KEY           required by OpenAlex since 13 Feb 2026 (free: openalex.org/settings/api)
  SEMANTIC_SCHOLAR_API_KEY   optional; dedicated 1 request/s instead of the shared anonymous pool
  NCBI_EMAIL                 recommended by NCBI for PubMed/PMC E-utilities
  NCBI_API_KEY               optional; 10 instead of 3 requests/s

Usage: python3 scripts/s2_check_keys.py
Exit code 0 = OpenAlex key works (the one that matters most); 1 otherwise.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from common import load_env, mask  # noqa: E402

TEST_DOI = "10.1038/nature14539"  # any well-known DOI


def main() -> int:
    import requests

    env_file, n = load_env()
    print(f"[env] {env_file or 'no .env file found'}" + (f" ({n} variables loaded)" if env_file else ""))
    s = requests.Session()
    s.headers["User-Agent"] = "ReFiNe_screen key check"
    ok_openalex = False

    # --- OpenAlex ---------------------------------------------------------------
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    print(f"\nOpenAlex           key {mask(key)}")
    if not key:
        print("  ✗ no key — since 13 Feb 2026 keyless use is limited to a tiny test allowance.\n"
              "    Get a free key at https://openalex.org/settings/api and add OPENALEX_API_KEY=... to .env")
    else:
        try:
            r = s.get("https://api.openalex.org/rate-limit", params={"api_key": key}, timeout=30)
            if r.status_code == 200:
                rl = r.json().get("rate_limit", {})
                print(f"  ✓ key accepted — daily budget ${rl.get('daily_budget_usd', '?')}, "
                      f"used ${rl.get('daily_used_usd', '?')}, remaining ${rl.get('daily_remaining_usd', '?')}")
                print("    (DOI lookups are free; cached-PDF downloads cost $0.01 each ≈ 100/day on the free key)")
                ok_openalex = True
            else:
                print(f"  ✗ HTTP {r.status_code}: {r.text[:200]}")
        except requests.RequestException as exc:
            print(f"  ✗ request failed: {exc}")

    # --- Semantic Scholar ---------------------------------------------------------
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    print(f"\nSemantic Scholar   key {mask(key)}")
    try:
        r = s.get(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{TEST_DOI}", params={"fields": "title"},
                  headers={"x-api-key": key} if key else {}, timeout=30)
        if r.status_code == 200:
            print("  ✓ " + ("key accepted (dedicated 1 request/s)" if key else
                        "works without key, but on the shared anonymous pool (expect 429s on long runs)"))
        elif r.status_code == 403 and key:
            print("  ✗ HTTP 403 — key rejected (check for typos / whitespace)")
        elif r.status_code == 429:
            print("  ⚠ HTTP 429 rate-limited" + ("" if key else " — this is what a key avoids"))
        else:
            print(f"  ✗ HTTP {r.status_code}")
    except requests.RequestException as exc:
        print(f"  ✗ request failed: {exc}")
    if not key:
        print("    Request a free key: https://www.semanticscholar.org/product/api#api-key-form (arrives by email)")

    # --- NCBI ---------------------------------------------------------------------
    key = os.environ.get("NCBI_API_KEY", "").strip()
    email = os.environ.get("NCBI_EMAIL", "").strip()
    print(f"\nNCBI E-utilities   key {mask(key)}, email {'set' if email else '(not set)'}")
    params = {"db": "pubmed", "term": "depression", "retmax": "1", "retmode": "json", "tool": "refine_pdf_downloader"}
    if email:
        params["email"] = email
    if key:
        params["api_key"] = key
    try:
        r = s.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params=params, timeout=30)
        body = r.text[:300]
        if r.status_code == 200 and "error" not in r.json():
            print("  ✓ " + ("key accepted (10 requests/s)" if key else "works without key (3 requests/s)"))
        else:
            print(f"  ✗ HTTP {r.status_code}: {body}")
    except (requests.RequestException, ValueError) as exc:
        print(f"  ✗ request failed: {exc}")
    if not email:
        print("    Set NCBI_EMAIL in .env (NCBI asks for a contact email from scripted tools).")
    if not key:
        print("    Optional key: NCBI account → Account settings → API Key Management → Create API Key")

    print("\n" + ("Ready: OpenAlex key works." if ok_openalex else "Not ready: fix the OpenAlex key first."))
    return 0 if ok_openalex else 1


if __name__ == "__main__":
    sys.exit(main())