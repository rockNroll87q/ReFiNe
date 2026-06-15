// ============================================================
// ReFiNe — Replication Feasibility Analysis Tool (Frontend)
// ============================================================
// - Loads papers.json + claims.json
// - Merges static claims with demo volunteer selections from localStorage
// - Renders feature filters, age-range filter, paper cards
// - Compact card layout: coverage line, groups-needed line, volunteer badges
// ============================================================

const PAPERS_URL = "/ReFiNe/data/papers.json";
const CLAIMS_URL = "/ReFiNe/data/claims.json";
const STORAGE_KEY = "refine_demo_claims";

let papers = [];
let allClaims = [];
let demoClaims = []; // volunteered entries stored in localStorage
let featureFilters = {};
let ageRangeMin = 18;
let ageRangeMax = 90;

// Mapping from snake_case feature keys to human-readable labels
const FEATURE_LABELS = {
  "t1w_mri": "T1w MRI",
  "vbm_or_voxelwise_morphometry": "VBM / voxel-wise morphometry",
  "mdd_patients": "MDD patients",
  "healthy_controls": "Healthy controls",
  "genetic_data": "Genetic data",
  "depression_scale": "Depression scale",
  "anxiety_scale": "Anxiety scale",
  "clinical_outcomes": "Clinical outcomes",
  "longitudinal_data": "Longitudinal data",
  "medication_status": "Medication status",
  "trauma_or_life_stress": "Trauma / life-stress data",
  "cognitive_data": "Cognitive data",
  "blood_or_biomarker_data": "Blood / biomarker data"
};

// Helper to get features from a paper (supports both dataset_features_needed and legacy features key)
function getFeatures(paper) {
  return paper.dataset_features_needed || paper.features || {};
}

// Get human-readable label for a feature key
function getFeatureLabel(key) {
  return FEATURE_LABELS[key] || key;
}

// ---- Claims helpers ----

function loadStaticClaims() {
  return fetch(CLAIMS_URL)
    .then(r => r.json())
    .then(j => j.claims || [])
    .catch(() => []);
}

function loadDemoClaims() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveDemoClaims(claims) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(claims));
}

function mergeClaims(staticClaims, demo) {
  const map = new Map();
  for (const c of staticClaims) {
    map.set(c.paper_id, { ...c, source: "static" });
  }
  for (const d of demo) {
    const key = d.paper_id;
    if (map.has(key)) {
      // merge demo into existing claim
      Object.assign(map.get(key), d, { source: "merged" });
    } else {
      map.set(key, { ...d, source: "demo" });
    }
  }
  return Array.from(map.values());
}

function addDemoClaim(claim) {
  demoClaims.push(claim);
  saveDemoClaims(demoClaims);
}

// ---- Filter helpers ----

function buildFeatureFilters(papersList) {
  const features = new Set();
  for (const p of papersList) {
    const feats = getFeatures(p);
    if (feats) {
      for (const key of Object.keys(feats)) {
        features.add(key);
      }
    }
  }
  return Array.from(features).sort();
}

function getFeatureOptions(featureKey) {
  const values = new Set();
  for (const p of papers) {
    const feats = getFeatures(p);
    if (feats && feats[featureKey] != null) {
      const v = feats[featureKey];
      if (typeof v === "boolean") {
        values.add(v ? "yes" : "no");
      } else if (Array.isArray(v)) {
        for (const item of v) values.add(String(item));
      } else {
        values.add(String(v));
      }
    }
  }
  return Array.from(values).sort();
}

function paperMatchesFilters(paper) {
  // Feature filters
  const feats = getFeatures(paper);
  for (const [key, selected] of Object.entries(featureFilters)) {
    if (!selected || selected === "all") continue;
    const val = feats ? feats[key] : null;
    if (val == null) return false;

    let matches = false;
    if (typeof val === "boolean") {
      matches = (selected === "yes" && val === true) || (selected === "no" && val === false);
    } else if (Array.isArray(val)) {
      matches = val.some(v => selected.toLowerCase() === String(v).toLowerCase());
    } else {
      matches = selected.toLowerCase() === String(val).toLowerCase();
    }
    if (!matches) return false;
  }

  // Age-range filter
  const ageReq = paper.age_requirement;
  if (ageReq && typeof ageReq === "object") {
    const minAge = ageReq.min_age != null ? Number(ageReq.min_age) : null;
    const maxAge = ageReq.max_age != null ? Number(ageReq.max_age) : null;

    // No age requirement → always shown
    if (minAge == null && maxAge == null) return true;

    // Overlap check: selected range [ageRangeMin, ageRangeMax] overlaps [minAge, maxAge]
    const effectiveMin = minAge != null ? minAge : ageRangeMin;
    const effectiveMax = maxAge != null ? maxAge : ageRangeMax;
    if (effectiveMax < ageRangeMin || effectiveMin > ageRangeMax) return false;
  }

  return true;
}

function getClaimForPaper(paperId) {
  return allClaims.find(c => c.paper_id === paperId) || null;
}

// ---- Rendering ----

function render() {
  const filterContainer = document.getElementById("filters");
  if (!filterContainer) return;

  // Build feature filters (only once on first render)
  const features = buildFeatureFilters(papers);
  if (filterContainer.children.length === 0) {
    for (const feat of features) {
      const options = getFeatureOptions(feat);
      const div = document.createElement("div");
      div.className = "filter";

      const label = document.createElement("label");
      label.textContent = getFeatureLabel(feat);
      div.appendChild(label);

      const select = document.createElement("select");
      select.dataset.feature = feat;
      const allOpt = document.createElement("option");
      allOpt.value = "all";
      allOpt.textContent = "All";
      select.appendChild(allOpt);
      for (const opt of options) {
        const o = document.createElement("option");
        o.value = opt.toLowerCase();
        o.textContent = opt;
        select.appendChild(o);
      }
      div.appendChild(select);
      filterContainer.appendChild(div);
    }

    // Add inline age-range control inside the filters grid
    const ageDiv = document.createElement("div");
    ageDiv.className = "filter";
    ageDiv.style.gridColumn = "1 / -1";

    const ageLabel = document.createElement("label");
    ageLabel.textContent = "Available age range";
    ageLabel.style.fontWeight = "600";
    ageDiv.appendChild(ageLabel);

    const ageControl = document.createElement("div");
    ageControl.className = "age-slider-group";
    ageControl.style.width = "100%";
    ageControl.style.display = "flex";
    ageControl.style.alignItems = "center";
    ageControl.style.gap = "12px";

    const minSlider = document.createElement("input");
    minSlider.type = "range";
    minSlider.id = "age-min-slider";
    minSlider.min = 18;
    minSlider.max = 90;
    minSlider.value = ageRangeMin;
    minSlider.step = 1;

    const maxSlider = document.createElement("input");
    maxSlider.type = "range";
    maxSlider.id = "age-max-slider";
    maxSlider.min = 18;
    maxSlider.max = 90;
    maxSlider.value = ageRangeMax;
    minSlider.step = 1;

    const display = document.createElement("span");
    display.id = "age-range-display-inline";
    display.className = "age-range-display-inline";
    updateAgeDisplayInline(display);

    minSlider.addEventListener("input", () => {
      ageRangeMin = parseInt(minSlider.value, 10);
      if (ageRangeMin > ageRangeMax) ageRangeMax = ageRangeMin;
      maxSlider.value = ageRangeMax;
      updateAgeDisplayInline(display);
      renderCards();
    });

    maxSlider.addEventListener("input", () => {
      ageRangeMax = parseInt(maxSlider.value, 10);
      if (ageRangeMax < ageRangeMin) ageRangeMin = ageRangeMax;
      minSlider.value = ageRangeMin;
      updateAgeDisplayInline(display);
      renderCards();
    });

    ageControl.appendChild(minSlider);
    ageControl.appendChild(maxSlider);
    ageControl.appendChild(display);
    ageDiv.appendChild(ageControl);
    filterContainer.appendChild(ageDiv);

    // Wire up select change listeners
    filterContainer.querySelectorAll("select").forEach(sel => {
      sel.addEventListener("change", () => {
        featureFilters[sel.dataset.feature] = sel.value;
        renderCards();
      });
    });
  } else {
    // Re-render cards only on subsequent calls
    renderCards();
    return;
  }

  renderCards();
}

function updateAgeDisplayInline(el) {
  el.textContent = `${ageRangeMin} – ${ageRangeMax}`;
}

function getCoverageLine(paper) {
  const claim = getClaimForPaper(paper.paper_id);
  if (!claim || claim.source === "static") {
    return null; // no coverage yet
  }

  const mddAvail = claim.mdd_n_available != null ? claim.mdd_n_available : null;
  const hcAvail = claim.healthy_control_n_available != null ? claim.healthy_control_n_available : null;

  const feats = getFeatures(paper);
  const mddNeeded = feats && feats["mdd_patients"] ? feats["mdd_patients"] : null;
  const hcNeeded = feats && feats["healthy_controls"] ? feats["healthy_controls"] : null;

  let parts = [];

  // MDD coverage
  if (mddNeeded) {
    if (mddAvail != null) {
      parts.push(`MDD ${mddAvail} / needed: ${mddNeeded}`);
    } else {
      parts.push(`MDD not specified / needed: ${mddNeeded}`);
    }
  }

  // HC coverage
  if (hcNeeded) {
    if (hcAvail != null) {
      parts.push(`HC ${hcAvail} / needed: ${hcNeeded}`);
    } else {
      parts.push(`HC not specified / needed: ${hcNeeded}`);
    }
  }

  return parts.length > 0 ? parts.join(" | ") : null;
}

function getGroupsNeededLine(paper) {
  const feats = getFeatures(paper);
  const mddNeeded = feats && feats["mdd_patients"] ? feats["mdd_patients"] : null;
  const hcNeeded = feats && feats["healthy_controls"] ? feats["healthy_controls"] : null;

  if (mddNeeded == null && hcNeeded == null) {
    return "Groups needed: not specified";
  }

  let parts = [];
  if (mddNeeded != null) {
    parts.push(`MDD patients: ${mddNeeded ? "yes" : "no"}`);
  }
  if (hcNeeded != null) {
    parts.push(`Healthy controls: ${hcNeeded ? "yes" : "no"}`);
  }

  return "Groups needed: " + parts.join(" | ");
}

function getVolunteerStatus(paperId) {
  // Count demo claims for this paper (each entry in localStorage = one volunteer group)
  const demoForPaper = demoClaims.filter(c => c.paper_id === paperId);
  if (demoForPaper.length > 0) {
    const volunteers = [];
    for (const d of demoForPaper) {
      if (d.volunteer_name) {
        volunteers.push({ name: d.volunteer_name, institution: d.institution || "Unknown" });
      }
    }
    return { count: demoForPaper.length, volunteers };
  }

  // Static claims only — no volunteer info
  const claim = getClaimForPaper(paperId);
  if (!claim || claim.source === "static") return { count: 0, volunteers: [] };
  return { count: 0, volunteers: [] };
}

function renderCards() {
  const container = document.getElementById("cards");
  if (!container) return;
  container.innerHTML = "";

  const filtered = papers.filter(p => paperMatchesFilters(p));

  const countEl = document.getElementById("count");
  if (countEl) {
    countEl.textContent = `Showing ${filtered.length} of ${papers.length} studies`;
  }

  for (const paper of filtered) {
    const card = document.createElement("div");
    card.className = "card";

    // Title and meta
    const title = document.createElement("h3");
    title.textContent = paper.title;
    card.appendChild(title);

    const meta = document.createElement("p");
    meta.className = "meta";
    let metaText = "";
    if (paper.authors) metaText += `Authors: ${paper.authors}`;
    if (paper.year) metaText += ` · Year: ${paper.year}`;
    meta.textContent = metaText;
    card.appendChild(meta);

    // Coverage line (compact, single line at top)
    const coverage = getCoverageLine(paper);
    let coverageText = null;
    if (coverage) {
      coverageText = `Coverage: ${coverage}`;
    } else {
      coverageText = "Coverage: none yet";
    }
    const covEl = document.createElement("div");
    covEl.className = "sample-coverage";
    covEl.textContent = coverageText;
    card.appendChild(covEl);

    // Groups needed line (compact, one-line)
    const groupsLine = getGroupsNeededLine(paper);
    const grpEl = document.createElement("div");
    grpEl.className = "groups-needed";
    grpEl.textContent = groupsLine;
    card.appendChild(grpEl);

    // Feature badges — show dataset_features_needed values
    const feats = getFeatures(paper);
    if (feats && Object.keys(feats).length > 0) {
      const badgesDiv = document.createElement("div");
      badgesDiv.className = "badges";
      for (const [key, val] of Object.entries(feats)) {
        let badgeText = "";
        let badgeClass = "badge";

        if (typeof val === "boolean") {
          badgeText = val ? "Yes" : "No";
          badgeClass += val ? " yes" : " no";
        } else if (Array.isArray(val)) {
          badgeText = val.join(", ");
          badgeClass += " unclear";
        } else {
          badgeText = String(val);
          badgeClass += " unclear";
        }

        const span = document.createElement("span");
        span.className = badgeClass;
        span.textContent = `${getFeatureLabel(key)}: ${badgeText}`;
        badgesDiv.appendChild(span);
      }
      card.appendChild(badgesDiv);
    }

    // Volunteer status and button (compact display)
    const statusInfo = getVolunteerStatus(paper.paper_id);

    if (statusInfo.count > 0) {
      // Has volunteers — show badge + compact collapsed details
      const badgeSpan = document.createElement("span");
      badgeSpan.className = "badge";
      badgeSpan.style.background = "#dbeafe";
      badgeSpan.style.color = "#1e40af";
      badgeSpan.textContent = `${statusInfo.count} group${statusInfo.count > 1 ? "s" : ""} volunteered`;
      card.appendChild(badgeSpan);

      // Compact volunteer details (collapsible)
      if (statusInfo.volunteers.length > 0) {
        const details = document.createElement("details");
        details.className = "volunteer-compact";

        const summary = document.createElement("summary");
        summary.textContent = `View ${statusInfo.volunteers.length} volunteer${statusInfo.volunteers.length > 1 ? "s" : ""}`;
        details.appendChild(summary);

        for (const v of statusInfo.volunteers) {
          const pEl = document.createElement("p");
          pEl.style.margin = "2px 0";
          pEl.style.fontSize = "13px";
          pEl.textContent = `${v.name}${v.institution ? ` (${v.institution})` : ""}`;
          details.appendChild(pEl);
        }

        card.appendChild(details);
      }

      // Add another group button
      const btn = document.createElement("button");
      btn.className = "volunteer-btn";
      btn.textContent = "Add another group";
      btn.addEventListener("click", () => openVolunteerModal(paper.paper_id));
      card.appendChild(btn);
    } else {
      // Available — no volunteers yet
      const badgeSpan = document.createElement("span");
      badgeSpan.className = "badge";
      badgeSpan.style.background = "#dcfce7";
      badgeSpan.style.color = "#166534";
      badgeSpan.textContent = "Available";
      card.appendChild(badgeSpan);

      const btn = document.createElement("button");
      btn.className = "volunteer-btn";
      btn.textContent = "Volunteer to replicate this paper";
      btn.addEventListener("click", () => openVolunteerModal(paper.paper_id));
      card.appendChild(btn);
    }

    container.appendChild(card);
  }
}

// ---- Modal ----

function openVolunteerModal(paperId) {
  const modal = document.getElementById("volunteer-modal");
  const paperInfo = document.getElementById("modal-paper-info");
  const paperIdInput = document.getElementById("form-paper-id");

  const paper = papers.find(p => p.paper_id === paperId);
  if (paper) {
    paperInfo.textContent = `${paper.title} (${paper.paper_id})`;
  } else {
    paperInfo.textContent = `Paper ${paperId}`;
  }

  paperIdInput.value = paperId;
  modal.style.display = "flex";
}

function closeModal() {
  const modal = document.getElementById("volunteer-modal");
  if (modal) modal.style.display = "none";
  const form = document.getElementById("volunteer-form");
  if (form) form.reset();
}

function handleVolunteerSubmit(e) {
  e.preventDefault();

  const paperId = document.getElementById("form-paper-id").value;
  const claim = {
    paper_id: paperId,
    status: "selected",
    volunteer_name: document.getElementById("form-name").value,
    institution: document.getElementById("form-institution").value || null,
    contact_preference: document.getElementById("form-contact").value || null,
    dataset_description: document.getElementById("form-dataset").value || null,
    replication_type: document.getElementById("form-replication").value || null,
    mdd_n_available: parseInt(document.getElementById("form-mdd-n").value, 10) || null,
    healthy_control_n_available: parseInt(document.getElementById("form-hc-n").value, 10) || null,
    other_groups_available: document.getElementById("form-other-groups").value || null,
    age_min_available: parseInt(document.getElementById("form-age-min").value, 10) || null,
    age_max_available: parseInt(document.getElementById("form-age-max").value, 10) || null,
    notes: document.getElementById("form-notes").value || null
  };

  addDemoClaim(claim);

  // Reload static claims and merge
  loadStaticClaims().then(static => {
    allClaims = mergeClaims(static, demoClaims);
    renderCards();
    closeModal();
  });
}

function clearDemoSelections() {
  if (confirm("Clear all demo volunteer selections? This will restore the original static claims from claims.json.")) {
    localStorage.removeItem(STORAGE_KEY);
    demoClaims = [];
    loadStaticClaims().then(static => {
      allClaims = mergeClaims(static, []);
      render();
    });
  }
}

function exportSelectionsAsJson() {
  const dc = loadDemoClaims();
  loadStaticClaims().then(static => {
    const merged = mergeClaims(static, dc);
    const exportData = {
      claims: merged.map(c => ({
        paper_id: c.paper_id,
        status: c.status?.toLowerCase() || "available",
        volunteer_name: c.volunteer_name || "",
        institution: c.institution || "",
        contact_preference: c.contact_preference || "",
        dataset_description: c.dataset_description || "",
        replication_type: c.replication_type || "",
        mdd_n_available: c.mdd_n_available != null ? parseInt(c.mdd_n_available, 10) : null,
        healthy_control_n_available: c.healthy_control_n_available != null ? parseInt(c.healthy_control_n_available, 10) : null,
        other_groups_available: c.other_groups_available || "",
        age_min_available: c.age_min_available != null ? parseInt(c.age_min_available, 10) : null,
        age_max_available: c.age_max_available != null ? parseInt(c.age_max_available, 10) : null,
        notes: c.notes || ""
      }))
    };

    const jsonStr = JSON.stringify(exportData, null, 2);
    const blob = new Blob([jsonStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "refine_demo_selections.json";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });
}

// ---- Reset filters ----

function resetFilters() {
  featureFilters = {};
  ageRangeMin = 18;
  ageRangeMax = 90;

  // Reset select elements
  document.querySelectorAll("#filters select").forEach(sel => {
    sel.value = "all";
  });

  renderCards();
}

// ---- Init ----

function init() {
  fetch(PAPERS_URL)
    .then(r => r.json())
    .then(data => {
      papers = data.papers || [];

      return Promise.all([
        loadStaticClaims(),
        new Promise(resolve => {
          demoClaims = loadDemoClaims();
          resolve();
        })
      ]);
    })
    .then(([staticClaims]) => {
      allClaims = mergeClaims(staticClaims, demoClaims);
      render();

      // Wire up reset button
      const resetBtn = document.getElementById("reset");
      if (resetBtn) resetBtn.addEventListener("click", resetFilters);

      // Wire up modal close buttons
      const closeModalBtn = document.getElementById("close-modal");
      if (closeModalBtn) closeModalBtn.addEventListener("click", closeModal);

      const cancelBtn = document.getElementById("cancel-volunteer");
      if (cancelBtn) cancelBtn.addEventListener("click", closeModal);

      // Wire up volunteer form submit
      const form = document.getElementById("volunteer-form");
      if (form) form.addEventListener("submit", handleVolunteerSubmit);
    })
    .catch(err => {
      console.error("Failed to load papers:", err);
      const countEl = document.getElementById("count");
      if (countEl) countEl.textContent = "Error loading papers. Check that papers.json is available.";
    });
}

// Make functions accessible globally for onclick handlers
window.openVolunteerModal = openVolunteerModal;
window.clearDemoSelections = clearDemoSelections;
window.exportSelectionsAsJson = exportSelectionsAsJson;
window.init = init;

init();