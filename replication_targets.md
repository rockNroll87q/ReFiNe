---
layout: default
title: Replication targets
permalink: /replication-targets/
---

<link rel="stylesheet" href="{{ '/assets/css/style.css' | relative_url }}">

# Replication targets

Use the filters below to identify papers that could be feasible replication targets for your dataset.

<section class="filters">
  <h2>Filter by dataset features needed</h2>
  <div id="filters"></div>
  <button id="reset">Reset filters</button>
</section>

<section>
  <div id="count"></div>
  <div id="cards"></div>
</section>

<section class="demo-actions">
  <h2>Indicate interest</h2>
  <p class="demo-note">
    This is currently a static demo. Selections are stored only in your browser and are not submitted anywhere.
  </p>

  <div class="demo-buttons">
    <button id="export-json">Export selections as JSON</button>
    <button id="clear-demo">Clear demo selections</button>
  </div>

  <div id="export-output" class="export-output" style="display:none;"></div>
</section>

<div id="volunteer-modal" class="modal-overlay" style="display:none;">
  <div class="modal">
    <div class="modal-header">
      <h2>Volunteer to replicate this paper</h2>
      <button id="close-modal" class="close-btn">&times;</button>
    </div>

    <p id="modal-paper-info" class="modal-paper-info"></p>

    <p class="demo-disclaimer">
      Demo only. This information is stored only in your browser and is not submitted anywhere.
    </p>

    <form id="volunteer-form">
      <input type="hidden" id="form-paper-id">

      <div class="form-group">
        <label for="form-name">Name *</label>
        <input type="text" id="form-name" required>
      </div>

      <div class="form-group">
        <label for="form-institution">Institution / research group *</label>
        <input type="text" id="form-institution" required>
      </div>

      <div class="form-group">
        <label for="form-contact">Contact preference *</label>
        <select id="form-contact" required>
          <option value="">Select...</option>
          <option value="Contact via project coordinator">Contact via project coordinator</option>
          <option value="Contact directly via email">Contact directly via email</option>
          <option value="Contact via phone">Contact via phone</option>
          <option value="No preference">No preference</option>
        </select>
      </div>

      <div class="form-group">
        <label for="form-dataset">Dataset description, short free text *</label>
        <textarea id="form-dataset" rows="3" required></textarea>
      </div>

      <div class="form-group">
        <label for="form-replication">Type of replication *</label>
        <select id="form-replication" required>
          <option value="">Select...</option>
          <option value="direct">Direct</option>
          <option value="partial">Partial</option>
          <option value="exploratory">Exploratory</option>
        </select>
      </div>

      <div class="form-group">
        <label for="form-notes">Notes</label>
        <textarea id="form-notes" rows="3"></textarea>
      </div>

      <div class="form-actions">
        <button type="submit" class="btn-primary">Save demo selection</button>
        <button type="button" id="cancel-volunteer" class="btn-secondary">Cancel</button>
      </div>
    </form>
  </div>
</div>

<script src="{{ '/assets/js/app.js' | relative_url }}"></script>