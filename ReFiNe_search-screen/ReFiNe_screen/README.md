# ReFiNe_screen

LLM-assisted eligibility screening for the [ReFiNe](https://rocknroll87q.github.io/ReFiNe/) replication study (depression and VBM). A local LLM screens search results first on title and abstract, then on full text. The pipeline downloads PDFs for the papers that pass, and every stage is compared against the human ratings.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in the API keys (see below)
python3 scripts/run_pipeline.py --run my_run
```

Results go to `runs/my_run/`. The key output is `runs/my_run/reports/`, which holds markdown reports, CSVs and figures.

## What you need

| Item | Where it goes | Notes |
|---|---|---|
| Python 3.10+ and `requirements.txt` | — | `docling` (PDF → text) is large and only needed for full-text screening |
| An OpenAI-compatible LLM endpoint | `.env` → `REFINE_LLM_*` | We use Qwen3.8-27B (Q8_0) in LM Studio |
| Human ratings | `data/input/screened_studies_full.csv` | Not in git, ask the team |
| Search output | `data/input/vbm_depression_wide.csv` | Not in git, ask the team |
| `ReFiNe_Hub` checkout | next to `ReFiNe_search-screen/` | Provides `eligible_studies.csv` and the PDF downloader |
| OpenAlex API key | `.env` | **Required** for downloads (free, openalex.org/settings/api) |
| Semantic Scholar key, NCBI email/key | `.env` | Optional, but they improve download coverage and speed |

Check your keys with `python3 scripts/s2_check_keys.py`. Never commit `.env`.

## Pipeline stages

| Stage | Script | What it does |
|---|---|---|
| s0 | `s0_*.py` | Build the paper set for a run (`runs/<run>/papers.csv`) |
| s1 | `s1_screen_abstract.py` | LLM rates each abstract against the gate criteria |
| s2 | `s2a_prepare_download.py`, `s2b_download_pdfs.py` | Fetch PDFs for papers that passed (open access, then OpenAlex) |
| s3 | `s3a_build_fulltext_set.py`, `s3b_screen_fulltext.py` | Convert PDFs to text; LLM rates every criterion |
| s4 | `s4a/b/c_report_*.py` | Agreement with humans: full text, abstract, end-to-end |
| s5–s6 | `s5_export_csv.py`, `s6_plots.py` | CSV export and figures (s4 also makes figures) |

`run_pipeline.py` runs all of these in order. Each script also runs on its own, and every script has `--help`.

## Layout

```
config/criteria.yaml   eligibility criteria (versioned; the single source of truth)
prompts/               prompt templates, e.g. screen_abstract_v4.md, screen_fulltext_v8.md
scripts/               stage scripts (s0–s6) + run_pipeline.py
scripts/lib/           shared code: LLM client, metrics, plots, run paths
data/input/            input CSVs (not in git)
cache/                 PDFs, extracted text, paper-ID registry (shared across runs; not in git)
runs/<run>/            everything one run produces; only reports/ is tracked
```

By default the newest prompt version for each stage is used. To use another, pass `--prompt`.

## Useful options

```bash
python3 scripts/run_pipeline.py --run my_run --dry-run              # show what would run
python3 scripts/run_pipeline.py --run my_run --skip-s2b --skip-s3b  # abstract stage only
python3 scripts/run_pipeline.py --run my_run --paper-set eligible-balanced
```

- **Resumable:** each paper's result is saved as it finishes, so a rerun skips finished work. To redo it, pass `--force` to the individual script.
- **Fails safe:** if the LLM stops responding, the run aborts after a few consecutive failures (`--max-consecutive-failures`, exit code 2) instead of writing junk. Restart the LLM and rerun the same command.
- **Long runs:** run them in the background:
  `nohup python3 scripts/run_pipeline.py --run my_run > data/logs/my_run.log 2>&1 &`

## Good to know

- **Running in the Yoda container:** LM Studio runs on the host and is reached at `http://172.17.0.1:1235/v1`, which is already set in `.env.example`. Load the model in LM Studio before starting a run.
- **Cost:** OpenAlex cached-PDF downloads cost $0.01 each. They are capped at 100 per run, which fits the free daily allowance (`--openalex-content-max`).
- **Speed:** a few hundred papers takes hours on a single local GPU. Keep `--workers` low (1–2) on a local model.
- **Don't share `cache/` publicly.** It contains copyrighted PDFs.
- **Changing criteria or prompts:** bump the version in `criteria.yaml` or add a new prompt file rather than editing an old one. Results record the prompt and criteria version they were made with.
- **Reference standard:** the reports score against the human ratings, and against `eligible_studies.csv` where relevant. These two don't fully agree yet; see the run reports.