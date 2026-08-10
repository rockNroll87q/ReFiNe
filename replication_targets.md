---
layout: page
title: ReFiNe
permalink: /replication-targets/
---

<link rel="stylesheet" href="{{ '/assets/css/replication-targets.css' | relative_url }}">

Screen potential replication targets to decide which original findings to replicate with your own (or an openly available) dataset

---

> **Searchable database of replication targets**
>
> We provide a curated collection of eligible original findings based on a systematic literature search and standardized eligibility ratings. You can browse and filter these curated findings using the available filters and descriptors that allow you to match published findings to the characteristics of your own dataset. This tool aims to make it easy to identify suitable replication targets for a given dataset. Findings not yet included in the Replication Hub can be added manually following confirmation of eligibility by the ReFiNe team. 
>
> This collection was developed as part of the ReFiNe-MDD pilot study and is currently available for **voxel-based morphometry findings related to depression**. Expansions of this list of replication targets covering other disorder domains and modalities will be conducted successively. Researchers with relevant datasets or an interest in conducting direct replications can register their interest below to help identify and prioritize future areas of expansion. For example, if you have access to a Parkinson's disease dataset with resting-state fMRI you would like to use to conduct  replications, you can register your interest in adding this domain. If sufficient interest and suitable datasets are available, ReFiNe will prioritize the development of a curated collection of eligible findings in this area.

---

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
