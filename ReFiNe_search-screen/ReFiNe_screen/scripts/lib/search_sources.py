"""Literature database fetchers used by s00_search_papers.py (no side effects on import)."""

from __future__ import annotations

import glob
import os
import time

import pandas as pd
import requests
from loguru import logger
from tqdm import tqdm

COLUMNS = ["title", "doi", "journal", "year", "abstract", "source"]
SOURCES = ("pubmed", "openalex", "semanticscholar", "europepmc", "biorxiv", "medrxiv")


def get_json(url: str, params: dict, headers: dict | None = None) -> dict:
    """
    Summary
        GET request returning parsed JSON, raising on HTTP errors so a failed
        page never silently truncates a source.
    Args
        url (str): endpoint
        params (dict): query parameters
        headers (dict | None): optional request headers
    Returns
        dict: parsed JSON body
    """
    for attempt in range(6):
        r = requests.get(url, params=params, headers=headers, timeout=60)
        if r.status_code not in (429, 502, 503, 504) or attempt == 5:
            break
        wait = float(r.headers.get("Retry-After", 0) or 0) or min(60, 3 * 2 ** attempt)
        logger.warning(f"HTTP {r.status_code}, retrying in {wait:.0f}s")
        time.sleep(wait)
    r.raise_for_status()
    return r.json()


def to_openalex_groups(query_groups):
    """
    Summary
        Converts nested AND/OR keyword groups into OpenAlex filter syntax.
    Args
        query_groups (list[list[str]]): outer AND, inner OR keyword groups
    Returns
        str: filter string for the OpenAlex works endpoint
    """
    def or_clause(terms):
        return " OR ".join(f'"{t}"' if " " in t else t for t in terms)
    return ",".join(f"title_and_abstract.search:{or_clause(g)}" for g in query_groups)


def reconstruct_openalex_abstract(inverted_index):
    """
    Summary
        Rebuilds plain abstract text from OpenAlex's word -> [positions] index.
    Args
        inverted_index (dict | None): abstract_inverted_index from the API
    Returns
        str | None: reconstructed abstract text
    """
    if not inverted_index:
        return None
    positions = {i: w for w, idxs in inverted_index.items() for i in idxs}
    return " ".join(positions[i] for i in sorted(positions))


def fetch_openalex(query_groups, api_key=None, email=None, **_):
    """
    Summary
        Cursor-paginates the OpenAlex works endpoint for the keyword groups.
    Args
        query_groups (list[list[str]]): outer AND, inner OR keyword groups
        api_key (str | None): OpenAlex API key
        email (str | None): contact address for the polite pool
    Returns
        list[dict]: records with the shared schema
    """
    url = "https://api.openalex.org/works"
    params = {"filter": to_openalex_groups(query_groups), "per_page": 200, "cursor": "*"}
    if api_key:
        params["api_key"] = api_key
    if email:
        params["mailto"] = email
    records, pbar = [], None
    while True:
        r = get_json(url, params)
        pbar = pbar or tqdm(total=r["meta"]["count"], desc="openalex")
        for w in r["results"]:
            loc = (w.get("primary_location") or {}).get("source") or {}
            records.append({"title": w.get("title"), "doi": w.get("doi"), "journal": loc.get("display_name"),
                            "year": w.get("publication_year"),
                            "abstract": reconstruct_openalex_abstract(w.get("abstract_inverted_index")),
                            "source": "openalex"})
        pbar.update(len(r["results"]))
        params["cursor"] = (r.get("meta") or {}).get("next_cursor")
        if not params["cursor"]:
            break
        time.sleep(0.1)
    pbar.close()
    return records


def to_s2_query(query_groups):
    """
    Summary
        Converts keyword groups into Semantic Scholar bulk search syntax.
    Args
        query_groups (list[list[str]]): outer AND, inner OR keyword groups
    Returns
        str: query string
    """
    def or_clause(terms):
        return "(" + " | ".join(f'"{t}"' if " " in t else t for t in terms) + ")"
    return " ".join("+" + or_clause(g) for g in query_groups)


def fetch_semanticscholar(query_groups, s2_key=None, **_):
    """
    Summary
        Token-paginates the Semantic Scholar bulk search endpoint.
    Args
        query_groups (list[list[str]]): outer AND, inner OR keyword groups
        s2_key (str | None): Semantic Scholar API key
    Returns
        list[dict]: records with the shared schema
    """
    url = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
    headers = {"x-api-key": s2_key} if s2_key else {}
    params = {"query": to_s2_query(query_groups), "fields": "title,externalIds,venue,year,abstract"}
    records, pbar = [], None
    while True:
        r = get_json(url, params, headers)
        pbar = pbar or tqdm(total=r.get("total", 0), desc="semanticscholar")
        data = r.get("data", [])
        records += [{"title": p.get("title"), "doi": (p.get("externalIds") or {}).get("DOI"),
                     "journal": p.get("venue"), "year": p.get("year"), "abstract": p.get("abstract"),
                     "source": "semanticscholar"} for p in data]
        pbar.update(len(data))
        if not r.get("token"):
            break
        params["token"] = r["token"]
        time.sleep(0.2)
    pbar.close()
    return records


def to_epmc_query(query_groups):
    """
    Summary
        Converts keyword groups into Europe PMC query syntax.
    Args
        query_groups (list[list[str]]): outer AND, inner OR keyword groups
    Returns
        str: query string
    """
    def or_clause(terms):
        return "(" + " OR ".join(f'"{t}"' if " " in t else t for t in terms) + ")"
    return " AND ".join(or_clause(g) for g in query_groups)


def fetch_europepmc(query_groups, **_):
    """
    Summary
        Cursor-paginates the Europe PMC search endpoint.
    Args
        query_groups (list[list[str]]): outer AND, inner OR keyword groups
    Returns
        list[dict]: records with the shared schema
    """
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {"query": to_epmc_query(query_groups), "format": "json", "pageSize": 1000,
              "cursorMark": "*", "resultType": "core"}
    records, pbar = [], None
    while True:
        r = get_json(url, params)
        pbar = pbar or tqdm(total=r.get("hitCount", 0), desc="europepmc")
        results = r.get("resultList", {}).get("result", [])
        records += [{"title": x.get("title"), "doi": x.get("doi"), "journal": x.get("journalTitle"),
                     "year": x.get("pubYear"), "abstract": x.get("abstractText"), "source": "europepmc"}
                    for x in results]
        pbar.update(len(results))
        cursor = r.get("nextCursorMark")
        if not cursor or cursor == params["cursorMark"]:
            break
        params["cursorMark"] = cursor
        time.sleep(0.1)
    pbar.close()
    return records


def _frame_to_records(raw: pd.DataFrame, source: str, journal: str | None = None) -> list[dict]:
    """
    Summary
        Maps a paperscraper dump onto the shared schema.
    Args
        raw (pd.DataFrame): jsonl dump with title, doi, abstract, date columns
        source (str): source label
        journal (str | None): fixed journal label, else the journal column
    Returns
        list[dict]: records with the shared schema
    """
    year = raw["date"].astype(str).str[:4].where(raw["date"].notna()) if "date" in raw else None
    out = pd.DataFrame({"title": raw.get("title"), "doi": raw.get("doi"),
                        "journal": journal if journal else raw.get("journal"), "year": year,
                        "abstract": raw.get("abstract"), "source": source})
    return out.to_dict("records")


def fetch_pubmed(query_groups, pubmed_jsonl, pubmed_max_results=9998, **_):
    """
    Summary
        Queries PubMed through paperscraper and normalises the dump.
    Args
        query_groups (list[list[str]]): outer AND, inner OR keyword groups
        pubmed_jsonl (str): raw dump path, must end in .jsonl
        pubmed_max_results (int): per query cap, NCBI hard limit is 9999
    Returns
        list[dict]: records with the shared schema
    """
    from paperscraper.pubmed import get_and_dump_pubmed_papers
    get_and_dump_pubmed_papers(query_groups, output_filepath=str(pubmed_jsonl), max_results=pubmed_max_results)
    return _frame_to_records(pd.read_json(pubmed_jsonl, lines=True), "pubmed")


def find_latest_dump(server_name):
    """
    Summary
        Finds the newest local paperscraper dump for a preprint server.
    Args
        server_name (str): "biorxiv" or "medrxiv"
    Returns
        str: path to the newest matching jsonl dump
    """
    from paperscraper.utils import get_server_dumps_dir
    matches = sorted(glob.glob(os.path.join(get_server_dumps_dir(), f"{server_name}_*.jsonl")))
    if not matches:
        raise FileNotFoundError(f"no local {server_name} dump, run paperscraper.get_dumps.{server_name}() first")
    return matches[-1]


def make_xrxiv_fetcher(server_name):
    """
    Summary
        Builds a fetcher that searches a local bioRxiv or medRxiv dump.
    Args
        server_name (str): "biorxiv" or "medrxiv"
    Returns
        callable: fetcher(query_groups, tmp_dir) -> list[dict]
    """
    def fetch(query_groups, tmp_dir=".", **_):
        from paperscraper.xrxiv.xrxiv_query import XRXivQuery
        tmp = os.path.join(tmp_dir, f"{server_name}_matches.jsonl")
        XRXivQuery(find_latest_dump(server_name)).search_keywords(query_groups, output_filepath=tmp)
        return _frame_to_records(pd.read_json(tmp, lines=True), server_name, journal=server_name)
    return fetch


FETCHERS = {"pubmed": fetch_pubmed, "openalex": fetch_openalex, "semanticscholar": fetch_semanticscholar,
            "europepmc": fetch_europepmc, "biorxiv": make_xrxiv_fetcher("biorxiv"),
            "medrxiv": make_xrxiv_fetcher("medrxiv")}


def normalize_doi(series):
    """
    Summary
        Strips a doi.org prefix and normalises case and whitespace.
    Args
        series (pd.Series): raw doi values
    Returns
        pd.Series: normalised doi values
    """
    return series.str.strip().str.replace(r"^https?://(dx\.)?doi\.org/", "", regex=True).str.lower()


def dedupe(records: list[dict]) -> pd.DataFrame:
    """
    Summary
        Keeps DOI rows only, normalises DOIs and drops duplicates, preferring
        the copy that has an abstract (then source order).
    Args
        records (list[dict]): concatenated records from all sources
    Returns
        pd.DataFrame: one row per unique DOI
    """
    df = pd.DataFrame(records, columns=COLUMNS)
    df = df[df["doi"].notna() & (df["doi"].astype(str).str.strip() != "")].copy()
    df["doi"] = normalize_doi(df["doi"].astype(str))
    df["abstract"] = df["abstract"].where(df["abstract"].astype(str).str.strip() != "")
    df = df.assign(_has=df["abstract"].notna()).sort_values("_has", ascending=False, kind="stable")
    return df.drop_duplicates("doi").drop(columns="_has").reset_index(drop=True)


def run_search(query_groups, sources, **cfg):
    """
    Summary
        Runs the selected sources, collecting per source counts and failures.
    Args
        query_groups (list[list[str]]): outer AND, inner OR keyword groups
        sources (list[str]): names from SOURCES
        **cfg: api_key, email, s2_key, pubmed_jsonl, pubmed_max_results, tmp_dir
    Returns
        tuple[list[dict], dict, dict]: records, raw count per source, error per failed source
    """
    records, counts, errors = [], {}, {}
    for s in sources:
        logger.info(f"{s}: querying")
        t0 = time.time()
        try:
            got = FETCHERS[s](query_groups, **cfg)
        except Exception as e:
            errors[s] = f"{type(e).__name__}: {e}"
            logger.error(f"{s} failed: {errors[s]}")
            continue
        counts[s] = len(got)
        records += got
        logger.info(f"{s}: {len(got)} records in {time.time() - t0:.0f}s")
    return records, counts, errors
