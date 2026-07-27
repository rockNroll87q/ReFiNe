---
layout: page
title: ReFiNe
permalink: /replication-targets/
---

<link rel="stylesheet" href="{{ '/assets/css/replication-targets.css' | relative_url }}">

Learn about the scope of ReFiNe and the eligibility criteria for replication targets to decide which original findings to replicate with your own (or an openly available) dataset.

---

> **Searchable curated list of replication targets**
>
> We provide a curated collection of eligible original findings based on a systematic literature search and standardized eligibility ratings. Browse and filter these curated findings using the available filters that allow you to match published findings to the characteristics of your own dataset, helping you efficiently identify suitable replication targets. Findings not yet included in the Replication Hub can be added manually following confirmation of eligibility. 
>
> This collection was developed as part of the ReFiNe-MDD pilot study and is currently available for **voxel-based morphometry findings related to depression**. Expansions of this list of replication targets covering other disorder domains and modalities will be subject of further expansions. Researchers with relevant datasets or an interest in conducting direct replications can register their interest below to help identify and prioritize future areas of expansion. For example, if you have access to a Parkinson's disease dataset with resting-state MRI and would like to conduct direct replications, you can register your interest in adding this domain. If sufficient interest and suitable datasets are available, ReFiNe will prioritize the development of a curated collection of eligible findings in this area.

---

## Eligibility criteria

Studies included in the ReFiNe Replication Hub are identified through systematic literature searches and screened using predefined eligibility criteria. Candidate studies first undergo an eligibility assessment and are subsequently evaluated regarding their suitability for direct replication using available datasets.

### Scientific scope of ReFiNe

ReFiNe is designed to support systematic direct replications within the following research domains. The current implementation of the Replication Hub contains a curated collection of replication targets for voxel-based morphometry findings in major depression only (see **Current implementation** above). Additional research domains and imaging modalities will be incorporated as curated collections become available.

#### Clinical domains

- Affective disorders (depression and bipolar disorder)
- Anxiety disorders (including PTSD and OCD)
- Psychotic disorders
- Neurodevelopmental disorders (ADHD and ASD)
- Addiction
- Epilepsy
- Parkinson's disease
- Stroke
- Ataxia

#### MRI modalities

- Voxel-based morphometry (VBM)
- Resting-state functional MRI
- Task-based functional MRI

### General eligibility criteria

Eligible studies must:

- report an original MRI finding associating a predictor with brain structure or function;
- investigate predictors related to mental health or neurological disorders (e.g., diagnosis, symptoms, treatment response, disease progression, risk or protective factors, or disorder-related biomarkers);
- include human participants from clinical and/or non-clinical populations (neonatal or infant-specific MRI methodologies are excluded);
- use voxel-wise gray matter structure (VBM) or voxel-wise functional findings (task-based or resting-state fMRI), based on cerebral MRI scans acquired at a minimum field strength of 3 T, with isotropic voxels and a spatial resolution of at least 1.5 mm for VBM (3.5 mm for fMRI);
- use whole-brain, mass-univariate voxel-based MRI analyses within a general linear modelling framework or a comparable statistical approach (multivariate machine-learning approaches are excluded);
- be published as primary research articles in peer-reviewed journals and be available in English.

### Replication-specific feasibility assessment

For each selected replication target, the replication team evaluates whether direct replication is feasible using the available dataset. This assessment includes:

- availability of a comparable predictor variable;
- availability of required covariates;
- sufficiently similar sample characteristics;
- comparable MRI modality and statistical analysis;
- comparable study design (e.g., cross-sectional or longitudinal);
- a replication sample size at least as large as the original study.

Only studies meeting these feasibility criteria are approved for direct replication.

<div class="replication-targets-page">

<!-- ============================================================
     Replication Targets — loads papers.json and renders cards
     using relative_url for Jekyll compatibility.
     ============================================================ -->

<!-- Filter panel with title and bordered container (includes search bar) -->
<section class="filters-compact" id="filters-compact">
  <h2 class="filter-panel-title">Filter by dataset features needed</h2>
  <div class="filter-panel-container">
    <!-- Search bar inside the filter panel -->
    <div id="search-container">
      <input type="text" id="search-input" placeholder="Search papers by title, diagnosis, feature, or summary..." class="search-input">
      <button id="clear-search" class="clear-search-btn" style="display:none;" title="Clear search">&times;</button>
    </div>

    <!-- Compact filter buttons row -->
    <div class="filter-buttons-row" id="filter-buttons-row"></div>
    <!-- Dropdown panels appear below the button when opened -->
    <div id="filter-dropdowns-container"></div>
    <!-- Active filter chips (inline, always visible) -->
    <div id="active-filters-bar" class="active-filters-bar">
      <span class="active-filters-label">Active filters:</span>
      <div id="active-filters-chips"></div>
      <button id="reset-filters-btn" class="reset-filters-btn">&times;&nbsp;Reset filters</button>
    </div>
  </div>
</section>

<section class="replication-targets-app">
  <div id="count"></div>
  <div id="cards"></div>
</section>

</div><!-- /.replication-targets-page -->

<script>
  window.REFINE_BASE_URL = "{{ '/' | relative_url }}";
</script>
<script src="{{ '/assets/js/app.js' | relative_url }}"></script>
