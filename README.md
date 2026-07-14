# ReFiNe

**Investigating the Replicability of Findings in Neuroimaging**

**Website:** https://rocknroll87q.github.io/ReFiNe/

## Overview

ReFiNe is an open community initiative to coordinate direct replication efforts in neuroimaging. It brings together researchers who are interested in replicating published findings and makes it easier to organise, track, and collaborate on replication studies.

## Mission

ReFiNe aims to make replication easier to organise by providing a searchable catalogue of candidate replication targets and a public mechanism for research groups to register interest in attempting a replication.

## ReFiNe_Hub

[ReFiNe_Hub](https://rocknroll87q.github.io/ReFiNe/) is the website/platform used to browse replication targets, search and filter papers, and register interest in attempting a replication. It provides:

- A searchable catalogue of candidate replication targets
- Filtering by study characteristics (e.g., imaging modality, condition)
- A public mechanism for research groups to register interest in replications

## Current scope

The current version focuses on neuroimaging replication targets, initially emphasising structural MRI / morphometry and mental-health-related findings. The scope is expected to evolve as the community grows and new domains are incorporated.

## How to participate

1. **Browse replication targets** on the [ReFiNe_Hub website](https://rocknroll87q.github.io/ReFiNe/)
2. **Search and filter papers** by study characteristics, imaging modality, or condition
3. **Register interest** in attempting a replication — registrations will be coordinated publicly through GitHub Issues once enabled

Contributors are welcome to open issues, submit pull requests, and join the community discussion.

## Repository organisation

- `ReFiNe_Hub/` — Contains the static website, extraction pipeline, prompts, and data-generation workflow.
- Root-level files — Describe the initiative, licensing, and public repository purpose.

## Deployment (GitHub Pages)

### Selective file sync to gh-pages

A GitHub Action on `main` automatically syncs only the **replication-targets** related files to the `gh-pages` branch:

- `replication_targets.md`
- `assets/js/app.js`
- `assets/css/style.css`
- `data/papers.json`
- `data/claims.json` (only if it exists)

The rest of the public website content on `gh-pages` (e.g., `index.md`, `contributors.md`, `resources.md`, `_layouts/`, `_config.yml`, `misc/`) is **manually maintained** and will **not** be overwritten by the automated deployment. The action uses `keep_files: true` to preserve all existing files that are not part of the sync payload.

### Manual website pages

The gh-pages branch already contains Jekyll source files for the main site (index.md, contributors.md, resources.md, etc.). These are hand-written and should be updated manually via direct commits or PRs to the `gh-pages` branch.

## Important notes

- The catalogue is intended to support replication planning only.
- LLM-assisted metadata and summaries may contain errors and should be checked against the original papers.
- Inclusion of a paper does not imply endorsement or validation of the original finding.
- ReFiNe does not redistribute or relicense third-party published articles.

## Licensing

- **Code** is licensed under the [MIT License](LICENSE).
  Copyright (c) 2026 ReFiNe contributors
- **ReFiNe-created website text, catalogue metadata, and extracted summaries** are licensed under [CC BY 4.0](LICENSE-CONTENT.md).
- **Third-party papers, PDFs, abstracts, publisher-owned text, figures, and article content** remain under their original copyright and are not redistributed or relicensed by ReFiNe.

## Citation

If you use ReFiNe, please cite the project website and/or forthcoming manuscript. Citation details will be added here.

## Contact

For questions or collaboration enquiries, please contact the ReFiNe organisers. Contact details will be added here.