#!/usr/bin/env python3
"""
sync_replication_registrations.py

Fetches all GitHub issues from this repository whose title matches
``Replication interest: REFINE-XXXX`` and writes a public-facing
claims.json file that the ReFiNe website reads.

Usage (local testing):
    # Set GITHUB_TOKEN if the repo is private or you hit rate limits
    python scripts/sync_replication_registrations.py

Environment variables:
    GITHUB_TOKEN   – GitHub personal access token or GH App token
    GITHUB_REPO    – owner/repo (default: derived from remote URL)
    OUTPUT_PATH    – path to write claims.json (default: site/data/claims.json)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

# ------------------------------------------------------------------ #
# Regex that identifies a replication-registration issue title
# ------------------------------------------------------------------ #
_ISSUE_TITLE_RE = re.compile(
    r"^replication\s+interest:\s*(refine-\d{4})\s*$", re.IGNORECASE
)

# ------------------------------------------------------------------ #
# Label → logical status mapping (precedence order documented in docstring)
# ------------------------------------------------------------------ #
_LABEL_STATUS_MAP: dict[str, str] = {
    "registration-withdrawn": "withdrawn",
    "replication-completed":  "completed",
    "replication-in-progress":"in_progress",
    "registration-confirmed": "confirmed",
    "registration-pending":   "pending",
}

# Statuses that count as "active" on the website
_ACTIVE_STATUSES = {"pending", "confirmed", "in_progress", "completed"}

# ------------------------------------------------------------------ #
# Issue body parsing — extracts structured fields from the form
# ------------------------------------------------------------------ #
_BODY_FIELD_RE = re.compile(
    r"^##\s+(.+)$", re.MULTILINE   # section headings (greedy to capture full title)
)
_TABLE_FIELD_RE = re.compile(
    r"\|\s*\*\*?([^|]+?)\*\*?\s*\|\s*([^|]*?)\s*\|"  # table cells
)

# Key → markdown heading mapping for the contributor info section
_CONTRIBUTOR_FIELDS: list[tuple[str, str]] = [
    ("volunteer_name", "Name / group"),
    ("institution",  "Institution"),
]


def _parse_body(body: str | None) -> dict[str, str]:
    """Parse the issue body and extract contributor fields.

    Uses heading-based section detection so that field positions are not
    tied to fixed line numbers.  Missing fields default to ``""``.
    """
    result: dict[str, str] = {}
    if not body:
        for key, _ in _CONTRIBUTOR_FIELDS:
            result[key] = ""
        return result

    # Find the "Contributor / Group Information" section
    contributor_section: str | None = None
    sections: list[tuple[str, str]] = []  # (heading, body)

    current_heading: str | None = None
    current_lines: list[str] = []

    for line in body.splitlines():
        m = _BODY_FIELD_RE.match(line.strip())
        if m:
            if current_heading is not None:
                sections.append((current_heading, "\n".join(current_lines)))
            current_heading = m.group(1).strip()
            current_lines = []
        else:
            if current_heading is not None:
                current_lines.append(line)

    if current_heading is not None:
        sections.append((current_heading, "\n".join(current_lines)))

    # Look for contributor section (case-insensitive heading match)
    contrib_section_body: str | None = None
    for heading, body_text in sections:
        if "contributor" in heading.lower() or "group information" in heading.lower():
            contrib_section_body = body_text
            break

    # Extract fields from the contributor section using table parsing first
    found_fields: dict[str, str] = {}
    if contrib_section_body:
        for key, label in _CONTRIBUTOR_FIELDS:
            # Try table format first: | **label** | value |
            pattern = re.compile(
                r"\|\s*\*\*" + re.escape(label) + r"\*\*\s*\|\s*([^|]*?)\s*\|",
                re.IGNORECASE,
            )
            m = pattern.search(contrib_section_body)
            if m:
                found_fields[key] = m.group(1).strip()

    # Fallback / supplement: bullet format "- **label:** value" or "- **label:** "
    # The closing ** may appear before or after the colon, e.g.:
    #   - **Name / group:** Brain Imaging Lab
    #   - **Name / group**: Brain Imaging Lab
    for key, label in _CONTRIBUTOR_FIELDS:
        if found_fields.get(key):
            continue
        search_text = contrib_section_body if contrib_section_body else body
        for line in search_text.splitlines():
            # Try multiple patterns to handle different markdown bold/colon placements
            patterns_to_try = [
                # **label:** value  (colon inside bold)
                r"^[-*]\s*\*\*" + re.escape(label) + r":\s*\*\*\s*(.*)$",
                # **label**: value  (colon outside bold)
                r"^[-*]\s*\*\*" + re.escape(label) + r"\*\*:\s*(.*)$",
                # **label** value  (no colon at all)
                r"^[-*]\s*\*\*" + re.escape(label) + r"\*\*\s+(.*)$",
            ]
            for pat in patterns_to_try:
                m = re.search(pat, line.strip(), re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    if val:
                        found_fields[key] = val
                    break

    for key, _ in _CONTRIBUTOR_FIELDS:
        result[key] = found_fields.get(key, "")

    return result


# ------------------------------------------------------------------ #
# GitHub API helpers (stdlib only — no external dependencies)
# ------------------------------------------------------------------ #

def _get_env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name) or default


def _fetch_all_issues(repo: str, token: str | None) -> list[dict[str, Any]]:
    """Fetch ALL issues (including closed) with pagination."""
    base_url = "https://api.github.com"
    headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{base_url}/repos/{repo}/issues"
    params = [
        ("state", "all"),
        ("per_page", 100),
        ("sort", "created"),
        ("direction", "asc"),
    ]
    all_issues: list[dict[str, Any]] = []

    page_url = f"{url}?{urllib.parse.urlencode(params)}" if params else url

    while page_url:
        req = urllib.request.Request(page_url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status != 200:
                    print(
                        f"WARNING: GitHub API returned status {resp.status} for {page_url}",
                        file=sys.stderr,
                    )
                    # Try to read error body
                    try:
                        err_body = resp.read().decode("utf-8", errors="replace")
                        print(f"  Error response: {err_body[:500]}", file=sys.stderr)
                    except Exception:
                        pass
                    break
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            print(f"ERROR: HTTP {e.code} fetching {page_url}: {e.reason}", file=sys.stderr)
            break
        except urllib.error.URLError as e:
            print(f"ERROR: URL error fetching {page_url}: {e.reason}", file=sys.stderr)
            break

        if not isinstance(data, list):
            print("WARNING: Expected array from GitHub Issues API, got different type", file=sys.stderr)
            break

        all_issues.extend(data)

        # Pagination via Link header
        link_header = resp.headers.get("Link", "")
        next_url = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                start = part.index("<") + 1
                end = part.index(">")
                next_url = part[start:end].strip()
                break
        page_url = next_url

    return all_issues


# ------------------------------------------------------------------ #
# Core logic
# ------------------------------------------------------------------ #

def _determine_status(issue: dict[str, Any], is_closed: bool) -> str:
    """Determine the logical registration status from labels and state.

    Handles both GitHub API label dicts (``{"name": "foo"}``) and plain
    string labels for testing / local use.
    """
    raw_labels = issue.get("labels", [])
    labels: list[str] = []
    for lb in raw_labels:
        if isinstance(lb, str):
            labels.append(lb)
        elif isinstance(lb, dict):
            labels.append(lb.get("name", ""))

    # Check for known status labels (precedence order)
    for label_name in ["registration-withdrawn", "replication-completed",
                        "replication-in-progress", "registration-confirmed",
                        "registration-pending"]:
        if label_name in labels:
            return _LABEL_STATUS_MAP[label_name]

    # No recognised status label → default
    if is_closed:
        return "pending"  # closed but not withdrawn → still registered
    return "pending"


def _extract_paper_id(title: str) -> str | None:
    m = _ISSUE_TITLE_RE.match(title.strip())
    return m.group(1).upper() if m else None


def generate_claims(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert matching issues into claims.json entries."""
    records: list[dict[str, Any]] = []
    seen_issue_numbers: set[int] = set()

    for issue in issues:
        # Skip pull requests (GitHub returns PRs through the Issues API)
        if issue.get("pull_request") is not None:
            continue

        title = issue.get("title", "") or ""
        paper_id = _extract_paper_id(title)
        if paper_id is None:
            continue  # not a registration issue

        issue_number = issue.get("number")
        if issue_number in seen_issue_numbers:
            print(f"WARNING: Duplicate issue number {issue_number} skipped", file=sys.stderr)
            continue
        seen_issue_numbers.add(issue_number)

        is_closed = issue.get("state") == "closed"
        status = _determine_status(issue, is_closed)

        body = issue.get("body") or ""
        parsed = _parse_body(body)

        # Validate paper_id format
        if not re.fullmatch(r"REFINE-\d{4}", paper_id):
            print(f"WARNING: Invalid paper_id '{paper_id}' for issue #{issue_number}", file=sys.stderr)
            continue

        created_at = issue.get("created_at", "")
        updated_at = issue.get("updated_at", "")

        record = {
            "paper_id": paper_id,
            "status": status,
            "volunteer_name": parsed.get("volunteer_name", ""),
            "institution": parsed.get("institution", ""),
            "github_issue": issue_number,
            "issue_url": issue.get("html_url", ""),
            "github_user": (issue.get("user") or {}).get("login", ""),
            "created_at": created_at,
            "updated_at": updated_at,
        }
        records.append(record)

    # Sort by paper_id then issue number for deterministic output
    records.sort(key=lambda r: (r["paper_id"], r["github_issue"]))
    return records


def _compute_hash(data: list[dict[str, Any]]) -> str:
    """Compute a stable hash of the data for change detection."""
    text = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def format_json(records: list[dict[str, Any]]) -> str:
    """Produce deterministic JSON formatting."""
    return json.dumps(records, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


# ------------------------------------------------------------------ #
# CLI entry point
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync GitHub replication-registration issues to claims.json",
    )
    parser.add_argument("--repo", default=None, help="owner/repo (default: infer from git remote)")
    parser.add_argument("--output", default=None, help="output path for claims.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print generated JSON to stdout without writing files")
    parser.add_argument("--check-changes", action="store_true",
                        help="Exit with 0 if no changes, 1 if changes detected (for CI)")
    args = parser.parse_args()

    # Determine repo
    repo = args.repo or _get_env("GITHUB_REPO")
    if not repo:
        # Try to infer from git remote
        try:
            import subprocess
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                remote = result.stdout.strip()
                # Handle both https://github.com/owner/repo.git and git@github.com:owner/repo.git
                m = re.search(r"github\.com[:/]([^/]+)/(.+?)(?:\.git)?$", remote)
                if m:
                    repo = f"{m.group(1)}/{m.group(2)}"
        except Exception:
            pass
    if not repo:
        print("ERROR: Cannot determine repository. Set GITHUB_REPO or configure git remote.", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    output_path = args.output or _get_env("OUTPUT_PATH", "site/data/claims.json")

    token = _get_env("GITHUB_TOKEN")

    print(f"Fetching issues from {repo} ...", file=sys.stderr)
    issues = _fetch_all_issues(repo, token)
    print(f"Fetched {len(issues)} total issues.", file=sys.stderr)

    records = generate_claims(issues)
    json_output = format_json(records)

    if args.dry_run:
        print(json_output)
        return

    if args.check_changes:
        # Compare with existing file by hash
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing_text = f.read()
            existing_hash = hashlib.sha256(existing_text.encode("utf-8")).hexdigest()
            new_hash = _compute_hash(records)
            if existing_hash == new_hash:
                print("No changes detected.", file=sys.stderr)
                sys.exit(0)
            else:
                print("Changes detected.", file=sys.stderr)
                # Write the new content so CI can commit it
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(json_output)
                sys.exit(1)
        except FileNotFoundError:
            print("File not found; changes detected.", file=sys.stderr)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(json_output)
            sys.exit(1)
    else:
        # Normal mode — always write
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_output)
        print(f"Wrote {len(records)} registration records to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()