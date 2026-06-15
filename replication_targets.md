---
layout: default
title: Replication targets
permalink: /replication-targets/
---

# Replication targets

Use the filters below to identify replication targets that are feasible for your available dataset.

<section id="filter-panel" class="panel">
  <h2>Filter by dataset features needed</h2>

  <div id="filters"></div>

  <button id="reset">Reset filters</button>
</section>

<p id="count"></p>

<div id="cards" class="card-grid"></div>

<div id="volunteer-modal" class="modal">
  <div class="modal-content">
    <span id="close-modal" class="close">&times;</span>
    <h3>Indicate interest in this replication</h3>
    <p id="modal-paper-info"></p>

    <form id="volunteer-form">
      <input type="hidden" id="form-paper-id" />

      <label>Name:
        <input type="text" id="form-name" required />
      </label>

      <label>Institution / Research Group:
        <input type="text" id="form-institution" />
      </label>

      <label>Contact Preference:
        <select id="form-contact">
          <option value="email">Email</option>
          <option value="phone">Phone</option>
          <option value="institution">Institution</option>
        </select>
      </label>

      <label>Dataset Description:
        <textarea id="form-dataset" rows="3"></textarea>
      </label>

      <label>Replication Type:
        <select id="form-replication">
          <option value="direct">Direct</option>
          <option value="conceptual">Conceptual</option>
          <option value="collaborative">Collaborative</option>
        </select>
      </label>

      <label>Number of MDD Patients Available:
        <input type="number" id="form-mdd-n" min="0" />
      </label>

      <label>Number of Healthy Controls Available:
        <input type="number" id="form-hc-n" min="0" />
      </label>

      <label>Other Clinical Groups Available:
        <textarea id="form-other-groups" rows="2"></textarea>
      </label>

      <label>Minimum Age Available:
        <input type="number" id="form-age-min" min="18" />
      </label>

      <label>Maximum Age Available:
        <input type="number" id="form-age-max" max="90" />
      </label>

      <label>Notes:
        <textarea id="form-notes" rows="3"></textarea>
      </label>

      <button type="submit">Submit</button>
      <button type="button" id="cancel-volunteer">Cancel</button>
    </form>
  </div>
</div>

<script src="{{ '/app.js' | relative_url }}"></script>