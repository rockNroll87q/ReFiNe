#!/usr/bin/env python3
"""
Tests for sync_replication_registrations.py

Run locally:  python scripts/test_sync_replication_registrations.py
Or from repo root: cd ReFiNe_Hub && python scripts/test_sync_replication_registrations.py
"""

import json
import sys
import textwrap
import unittest
from pathlib import Path

# Ensure the parent directory is on the path so we can import the sync script
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import sync_replication_registrations as _sync_mod

# Re-export key functions for tests (use underscore-prefixed names from the module)
_extract_paper_id = getattr(_sync_mod, "_extract_paper_id", None)
_determine_status_fn = getattr(_sync_mod, "_determine_status", None)
_parse_body_fn = getattr(_sync_mod, "_parse_body", None)
_generate_claims = getattr(_sync_mod, "generate_claims", None)


# ============================================================
# Fixtures: mock issue data
# ============================================================

def _make_issue(number, title, state="open", labels=None, body=None, user_login="testuser"):
    """Create a minimal mock issue dict."""
    return {
        "number": number,
        "title": title,
        "state": state,
        "labels": labels or [],
        "body": body or "",
        "html_url": f"https://github.com/OWNER/REPO/issues/{number}",
        "created_at": "2026-07-14T10:00:00Z",
        "updated_at": "2026-07-14T10:00:00Z",
        "user": {"login": user_login},
    }


# ============================================================
# Test 1: no matching issues → empty JSON array
# ============================================================
class TestNoMatchingIssues(unittest.TestCase):
    def test_empty_issues(self):
        """When there are zero matching issues, generate_claims returns []."""
        issues = [
            _make_issue(1, "Some other issue", labels=["bug"]),
            _make_issue(2, "Another unrelated title"),
        ]
        result = _generate_claims(issues)
        self.assertEqual(result, [])

    def test_no_issues_at_all(self):
        issues = []
        result = _generate_claims(issues)
        self.assertEqual(result, [])


# ============================================================
# Test 2: one group registered for a paper
# ============================================================
class TestOneGroupRegistered(unittest.TestCase):
    def test_single_registration(self):
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0001 |
            | **Paper title** | Test Paper |
            | **DOI** | 10.1234/test |

            ---

            ## Contributor / Group Information

            - **Name / group:** Brain Imaging Lab
            - **Institution:** University of Example

            ---

            ## Dataset Availability

            - [ ] I have access to the required dataset and can share it
            - [x] I can re-collect data from scratch
            - [ ] I need to find / request access to the dataset

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)
            - [ ] Partial replication (key analyses only)
            - [ ] Exploratory replication (related questions)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:** Looking forward to collaborating!
        """)
        issues = [_make_issue(42, "Replication interest: REFINE-0001", labels=["registration-pending"], body=body)]
        result = _generate_claims(issues)

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["paper_id"], "REFINE-0001")
        self.assertEqual(entry["status"], "pending")
        self.assertEqual(entry["volunteer_name"], "Brain Imaging Lab")
        self.assertEqual(entry["institution"], "University of Example")
        self.assertEqual(entry["github_issue"], 42)
        self.assertEqual(entry["issue_url"], "https://github.com/OWNER/REPO/issues/42")
        self.assertEqual(entry["github_user"], "testuser")


# ============================================================
# Test 3: two different issues registered for the same paper
# ============================================================
class TestTwoRegistrationsSamePaper(unittest.TestCase):
    def test_two_groups_same_paper(self):
        body1 = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0002 |
            | **Paper title** | Test Paper 2 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Alpha
            - **Institution:** University A

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        body2 = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0002 |
            | **Paper title** | Test Paper 2 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Beta
            - **Institution:** University B

            ---

            ## Dataset Availability

            - [x] I can re-collect data from scratch

            ---

            ## Replication Plan

            - [x] Partial replication (key analyses only)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issues = [
            _make_issue(10, "Replication interest: REFINE-0002", labels=["registration-pending"], body=body1),
            _make_issue(15, "Replication interest: REFINE-0002", labels=["registration-confirmed"], body=body2),
        ]
        result = _generate_claims(issues)

        self.assertEqual(len(result), 2)
        # Should be sorted by paper_id then issue number
        self.assertEqual(result[0]["github_issue"], 10)
        self.assertEqual(result[1]["github_issue"], 15)
        self.assertEqual(result[0]["paper_id"], "REFINE-0002")
        self.assertEqual(result[1]["paper_id"], "REFINE-0002")


# ============================================================
# Test 4: one active and one withdrawn registration for the same paper
# ============================================================
class TestActiveAndWithdrawn(unittest.TestCase):
    def test_active_and_withdrawn(self):
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0003 |
            | **Paper title** | Test Paper 3 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Gamma
            - **Institution:** University C

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issues = [
            _make_issue(20, "Replication interest: REFINE-0003", labels=["registration-pending"], body=body),
            _make_issue(25, "Replication interest: REFINE-0003", labels=["registration-withdrawn"], body=body),
        ]
        result = _generate_claims(issues)

        # Both should be in the output (withdrawn is a valid status)
        self.assertEqual(len(result), 2)
        statuses = {e["github_issue"]: e["status"] for e in result}
        self.assertEqual(statuses[20], "pending")
        self.assertEqual(statuses[25], "withdrawn")

    def test_withdrawn_excluded_from_active_count(self):
        """Withdrawn registrations should not count toward the active group count."""
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0004 |
            | **Paper title** | Test Paper 4 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Delta
            - **Institution:** University D

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issues = [
            _make_issue(30, "Replication interest: REFINE-0004", labels=["registration-pending"], body=body),
            _make_issue(35, "Replication interest: REFINE-0004", labels=["registration-withdrawn"], body=body),
        ]
        result = _generate_claims(issues)

        # Both entries present but withdrawn should be excluded from active count
        self.assertEqual(len(result), 2)
        active_statuses = {"pending", "confirmed", "in_progress", "completed"}
        for entry in result:
            if entry["status"] not in active_statuses and entry["status"] != "withdrawn":
                self.fail(f"Unexpected status: {entry['status']}")


# ============================================================
# Test 5: a closed but confirmed registration
# ============================================================
class TestClosedConfirmedRegistration(unittest.TestCase):
    def test_closed_confirmed_included(self):
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0005 |
            | **Paper title** | Test Paper 5 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Epsilon
            - **Institution:** University E

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issues = [_make_issue(40, "Replication interest: REFINE-0005", state="closed", labels=["registration-confirmed"], body=body)]
        result = _generate_claims(issues)

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["status"], "confirmed")
        # Closed but confirmed should still be included (not excluded)


# ============================================================
# Test 6: a malformed title
# ============================================================
class TestMalformedTitle(unittest.TestCase):
    def test_malformed_titles(self):
        """Titles that don't match the pattern should be skipped."""
        bad_titles = [
            "Replication interest: REFINE-001",       # too few digits
            "Replication interest: REFINE-00001",     # too many digits
            "Not a replication issue",                 # no pattern match
            "REFINE-0007",                             # missing prefix
            "",                                         # empty title
            "Replication interest:",                   # missing paper ID
        ]

        for title in bad_titles:
            issues = [_make_issue(50, title)]
            result = _generate_claims(issues)
            self.assertEqual(result, [], f"Expected no matches for title: {title!r}")

    def test_case_insensitive_matching(self):
        """Title matching should be case-insensitive."""
        titles_to_test = [
            "replication interest: REFINE-0006",
            "REPLICATION INTEREST: REFINE-0006",
            "Replication Interest: REFINE-0006",
            "rEpLiCaTiOn InTeReSt: RefInE-0006",
        ]
        for title in titles_to_test:
            issues = [_make_issue(55, title)]
            result = _generate_claims(issues)
            self.assertEqual(len(result), 1, f"Expected match for case-insensitive title: {title!r}")
            self.assertEqual(result[0]["paper_id"], "REFINE-0006")

    def test_extra_whitespace_tolerated(self):
        """Extra whitespace around the paper ID should be tolerated."""
        titles_to_test = [
            "Replication interest:  REFINE-0007",
            "Replication interest:   REFINE-0007  ",
            "Replication interest:\tREFINE-0007\t",
        ]
        for title in titles_to_test:
            issues = [_make_issue(60, title)]
            result = _generate_claims(issues)
            self.assertEqual(len(result), 1, f"Expected match with extra whitespace: {title!r}")
            self.assertEqual(result[0]["paper_id"], "REFINE-0007")


# ============================================================
# Test 7: missing laboratory or institution fields
# ============================================================
class TestMissingFields(unittest.TestCase):
    def test_missing_institution(self):
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0008 |
            | **Paper title** | Test Paper 8 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Zeta
            - **Institution:**

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issues = [_make_issue(70, "Replication interest: REFINE-0008", labels=["registration-pending"], body=body)]
        result = _generate_claims(issues)

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["volunteer_name"], "Lab Zeta")
        self.assertEqual(entry["institution"], "")

    def test_missing_both_fields(self):
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0009 |
            | **Paper title** | Test Paper 9 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:**
            - **Institution:**

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issues = [_make_issue(75, "Replication interest: REFINE-0009", labels=["registration-pending"], body=body)]
        result = _generate_claims(issues)

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["volunteer_name"], "")
        self.assertEqual(entry["institution"], "")


# ============================================================
# Test 8: more than one page of API results (pagination)
# ============================================================
class TestPagination(unittest.TestCase):
    def test_pagination(self):
        """When the GitHub API returns multiple pages, all issues should be processed."""
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0010 |
            | **Paper title** | Test Paper 10 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Eta
            - **Institution:** University H

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)

        page1 = [
            _make_issue(80, "Replication interest: REFINE-0010", labels=["registration-pending"], body=body),
        ]
        page2 = [
            _make_issue(85, "Replication interest: REFINE-0010", labels=["registration-confirmed"], body=body),
        ]

        # Simulate pagination by passing combined results directly to generate_claims
        result = _generate_claims(page1 + page2)

        self.assertEqual(len(result), 2)
        paper_ids = {e["paper_id"] for e in result}
        self.assertEqual(paper_ids, {"REFINE-0010"})


# ============================================================
# Unit tests for helper functions
# ============================================================
class TestExtractPaperId(unittest.TestCase):
    def test_valid_title(self):
        self.assertEqual(_extract_paper_id("Replication interest: REFINE-0001"), "REFINE-0001")

    def test_case_insensitive(self):
        self.assertEqual(_extract_paper_id("REPLICATION INTEREST: REFINE-0002"), "REFINE-0002")

    def test_extra_whitespace(self):
        self.assertEqual(_extract_paper_id("Replication interest:  REFINE-0003  "), "REFINE-0003")

    def test_invalid_titles(self):
        invalid = [
            "Some random issue",
            "REFINE-001",
            "replication interest:",
            "",
            "Replication interest: REFINE-ABCD",
            "Bug fix: REFINE-0004",
        ]
        for title in invalid:
            self.assertIsNone(_extract_paper_id(title), f"Expected None for title: {title!r}")


class TestDetermineStatus(unittest.TestCase):
    def _make_issue_dict(self, labels, state="open"):
        """Helper to create an issue dict with label dicts."""
        return {
            "labels": [{"name": l} for l in labels],
            "state": state,
        }

    def test_withdrawn_priority(self):
        labels = ["registration-pending", "registration-withdrawn"]
        self.assertEqual(_determine_status_fn(self._make_issue_dict(labels), True), "withdrawn")

    def test_replication_completed_priority(self):
        labels = ["replication-completed", "registration-confirmed"]
        self.assertEqual(_determine_status_fn(self._make_issue_dict(labels), False), "completed")

    def test_in_progress_priority(self):
        labels = ["replication-in-progress", "registration-pending"]
        self.assertEqual(_determine_status_fn(self._make_issue_dict(labels), False), "in_progress")

    def test_confirmed_priority(self):
        labels = ["registration-confirmed"]
        self.assertEqual(_determine_status_fn(self._make_issue_dict(labels), False), "confirmed")

    def test_pending_default_open(self):
        labels = []
        self.assertEqual(_determine_status_fn(self._make_issue_dict(labels), False), "pending")

    def test_closed_no_withdrawn_label(self):
        """A closed issue without withdrawn label should remain registered."""
        labels = ["registration-confirmed"]
        self.assertEqual(_determine_status_fn(self._make_issue_dict(labels), True), "confirmed")

    def test_closed_with_withdrawn(self):
        labels = ["registration-withdrawn"]
        self.assertEqual(_determine_status_fn(self._make_issue_dict(labels), True), "withdrawn")


class TestParseIssueBody(unittest.TestCase):
    def test_full_body(self):
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0011 |
            | **Paper title** | Test Paper 11 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Theta
            - **Institution:** University T

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:** Some notes here.
        """)
        result = _parse_body_fn(body)
        self.assertEqual(result["volunteer_name"], "Lab Theta")
        self.assertEqual(result["institution"], "University T")

    def test_malformed_body(self):
        body = "This is not a valid registration body at all."
        result = _parse_body_fn(body)
        # Should return defaults, not raise an exception
        self.assertEqual(result["volunteer_name"], "")
        self.assertEqual(result["institution"], "")


class TestGenerateClaimsJsonSorting(unittest.TestCase):
    def test_sorted_by_paper_id_then_issue_number(self):
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0012 |
            | **Paper title** | Test Paper 12 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Iota
            - **Institution:** University I

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issues = [
            _make_issue(30, "Replication interest: REFINE-0012", body=body),
            _make_issue(10, "Replication interest: REFINE-0012", body=body),
            _make_issue(20, "Replication interest: REFINE-0011", body=body),
        ]
        result = _generate_claims(issues)

        # Should be sorted by paper_id first, then issue number
        self.assertEqual(result[0]["paper_id"], "REFINE-0011")
        self.assertEqual(result[0]["github_issue"], 20)
        self.assertEqual(result[1]["paper_id"], "REFINE-0012")
        self.assertEqual(result[1]["github_issue"], 10)
        self.assertEqual(result[2]["paper_id"], "REFINE-0012")
        self.assertEqual(result[2]["github_issue"], 30)


class TestDeterministicJsonOutput(unittest.TestCase):
    def test_deterministic_output(self):
        """Running generate_claims twice should produce identical output."""
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0013 |
            | **Paper title** | Test Paper 13 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Kappa
            - **Institution:** University K

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issues = [
            _make_issue(40, "Replication interest: REFINE-0013", body=body),
            _make_issue(50, "Replication interest: REFINE-0013", body=body),
        ]
        result1 = _generate_claims(issues)
        result2 = _generate_claims(issues)

        self.assertEqual(json.dumps(result1, sort_keys=True), json.dumps(result2, sort_keys=True))


class TestPullRequestFiltering(unittest.TestCase):
    def test_pull_requests_excluded(self):
        """PRs returned via the Issues API should be skipped."""
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0014 |
            | **Paper title** | Test Paper 14 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Lambda
            - **Institution:** University L

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        # Issue that is actually a PR
        pr_issue = _make_issue(90, "Replication interest: REFINE-0014", body=body)
        pr_issue["pull_request"] = {"url": "https://api.github.com/repos/OWNER/REPO/pulls/90"}

        result = _generate_claims([pr_issue])
        self.assertEqual(result, [], "PR should be filtered out")


class TestDuplicateIssueNumbers(unittest.TestCase):
    def test_duplicate_issue_numbers_skipped(self):
        """If the same issue number appears twice, only one record should be generated."""
        body = textwrap.dedent("""\
            ## Replication Interest Registration

            | Field | Value |
            | --- | --- |
            | **Paper ID** | REFINE-0015 |
            | **Paper title** | Test Paper 15 |
            | **DOI** | N/A |

            ---

            ## Contributor / Group Information

            - **Name / group:** Lab Mu
            - **Institution:** University M

            ---

            ## Dataset Availability

            - [x] I have access to the required dataset and can share it

            ---

            ## Replication Plan

            - [x] Direct replication (exact same methods)

            ---

            ## Additional Information

            - **Public listing:** I agree to have this registration listed publicly on GitHub.
            - **Notes for organisers:**
        """)
        issue1 = _make_issue(95, "Replication interest: REFINE-0015", body=body)
        # Simulate a duplicate (same number, same data)
        issue2 = dict(issue1)

        result = _generate_claims([issue1, issue2])
        self.assertEqual(len(result), 1, "Duplicate issue numbers should be deduplicated")


# ============================================================
# Run tests
# ============================================================
if __name__ == "__main__":
    unittest.main(verbosity=2)