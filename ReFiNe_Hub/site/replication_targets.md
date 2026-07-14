---
layout: page
title: ReFiNe
permalink: /replication-targets/
---

<link rel="stylesheet" href="{{ '/assets/css/replication-targets.css' | relative_url }}">

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
