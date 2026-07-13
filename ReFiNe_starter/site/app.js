const REFINE_FEATURES = [
  ["t1w_mri", "T1w MRI"],
  ["vbm_or_voxelwise_morphometry", "VBM / voxel-wise morphometry"],
  ["mdd_patients", "MDD patients"],
  ["healthy_controls", "Healthy controls"],
  ["genetic_data", "Genetic data"],
  ["depression_scale", "Depression scale"],
  ["anxiety_scale", "Anxiety scale"],
  ["clinical_outcomes", "Clinical outcomes"],
  ["longitudinal_data", "Longitudinal data"],
  ["medication_status", "Medication status"],
  ["trauma_or_life_stress", "Trauma / life-stress data"],
  ["cognitive_data", "Cognitive data"],
  ["blood_or_biomarker_data", "Blood / biomarker data"]
];

function getFeatureKeys() {
  return REFINE_FEATURES.map(f => f[0]);
}

function getFeatureLabel(key) {
  const found = REFINE_FEATURES.find(f => f[0] === key);
  return found ? found[1] : key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const CONTACT_LABELS = {
  "Contact via project coordinator": "Contact via project coordinator",
  "Contact directly via email": "Contact directly via email",
  "Contact via phone": "Contact via phone",
  "No preference": "No preference"
};

const REPLICATION_LABELS = {
  "direct": "Direct",
  "partial": "Partial",
  "exploratory": "Exploratory"
};

const STORAGE_KEY = "refine_demo_claims";

let papers = [];
// claims is now an array of all claim objects (multiple per paper_id allowed)
let claims = [];

// Load static claims from claims.json (returns array)
async function loadStaticClaims() {
  try {
    const resp = await fetch("data/claims.json");
    if (resp.ok) {
      return await resp.json();
    }
  } catch (e) {
    console.warn("Could not load static claims.json:", e);
  }
  return [];
}

// Load demo claims from localStorage as an array
function loadDemoClaims() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    // Backward compatibility: old format was an object keyed by paper_id
    if (Array.isArray(parsed)) {
      return parsed;
    }
    // Convert old object format to array
    if (parsed && typeof parsed === "object") {
      return Object.values(parsed);
    }
    return [];
  } catch (e) {
    console.warn("Could not load demo claims from localStorage:", e);
    return [];
  }
}

// Save demo claims to localStorage as an array
function saveDemoClaims(claimsArray) {
  try {
    const storage = { claims: claimsArray };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(storage));
  } catch (e) {
    console.warn("Could not save demo claims to localStorage:", e);
  }
}

// Merge static claims and demo claims into a single array
function mergeClaims(staticClaims, demoClaims) {
  // Combine both arrays; demo claims come last so they appear at the end when rendering
  return [...staticClaims, ...demoClaims];
}

// Get all claims for a specific paper (returns array)
function getClaimsForPaper(paperId) {
  return claims.filter(c => c.paper_id === paperId);
}

// Compute coverage totals for a specific paper from its claims
function computeCoverageForPaper(paperId) {
  const paperClaims = getClaimsForPaper(paperId);
  let mddTotal = 0;
  let healthyTotal = 0;
  let mddSpecified = false;
  let healthySpecified = false;

  for (const claim of paperClaims) {
    if (claim.mdd_n_available != null && claim.mdd_n_available > 0) {
      mddTotal += claim.mdd_n_available;
      mddSpecified = true;
    }
    if (claim.healthy_control_n_available != null && claim.healthy_control_n_available > 0) {
      healthyTotal += claim.healthy_control_n_available;
      healthySpecified = true;
    }
  }

  return { mddTotal, healthyTotal, mddSpecified, healthySpecified };
}

// Render a compact coverage line for a paper
function renderCoverageLine(coverage) {
  if (!coverage.mddSpecified && !coverage.healthySpecified) {
    return "Coverage: none yet";
  }

  const parts = [];
  if (coverage.mddSpecified) {
    parts.push(`MDD ${coverage.mddTotal} / not specified`);
  } else {
    parts.push("MDD not specified");
  }
  if (coverage.healthySpecified) {
    parts.push(`Healthy controls ${coverage.healthyTotal} / not specified`);
  } else {
    parts.push("Healthy controls not specified");
  }

  return "Coverage: " + parts.join(" | ");
}

function hasActiveClaimForPaper(paperId) {
  return getClaimsForPaper(paperId).some(
    c => c.status?.toLowerCase() === "selected" || c.status?.toLowerCase() === "volunteer_pending"
  );
}

function getStatusDisplay(count) {
  if (count === 0) return { label: "Available", class: "status-available" };
  if (count === 1) return { label: "1 group volunteered", class: "status-selected" };
  return { label: `${count} groups volunteered`, class: "status-volunteer-pending" };
}

// Render a compact list of all volunteers for a paper
function renderVolunteerList(claimsArray) {
  if (!claimsArray || claimsArray.length === 0) return "";

  let html = `<div class="volunteer-list">`;

  // Show volunteer names/institutions in a collapsed details block
  html += `<details>`;
  html += `<summary>View ${claimsArray.length} volunteer group${claimsArray.length > 1 ? "s" : ""}</summary>`;
  html += `<div class="volunteer-list-inner">`;

  claimsArray.forEach((claim, idx) => {
    html += `<div class="volunteer-entry">`;
    html += `<p><strong>Group ${idx + 1}:</strong> ${escapeHtml(claim.volunteer_name || "Unknown")}</p>`;
    html += `<p><strong>Institution:</strong> ${escapeHtml(claim.institution || "Unknown")}</p>`;

    if (claim.notes || claim.dataset_description || claim.replication_type) {
      html += `<details class="volunteer-details">`;
      html += `<summary>Show details</summary>`;
      if (claim.contact_preference) {
        html += `<div class="detail-row"><span class="detail-label">Contact:</span> ${escapeHtml(claim.contact_preference)}</div>`;
      }
      if (claim.dataset_description) {
        html += `<div class="detail-row"><span class="detail-label">Dataset:</span> ${escapeHtml(claim.dataset_description)}</div>`;
      }
      if (claim.replication_type) {
        html += `<div class="detail-row"><span class="detail-label">Replication type:</span> ${REPLICATION_LABELS[claim.replication_type] || claim.replication_type}</div>`;
      }
      if (claim.notes) {
        html += `<div class="detail-row"><span class="detail-label">Notes:</span> ${escapeHtml(claim.notes)}</div>`;
      }
      html += `</details>`;
    }

    html += `</div>`;
  });

  html += `</div></details></div>`;
  return html;
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderCard(paper) {
  const paperClaims = getClaimsForPaper(paper.paper_id);
  const activeCount = paperClaims.filter(c => c.status?.toLowerCase() === "selected" || c.status?.toLowerCase() === "volunteer_pending").length;
  const status = getStatusDisplay(activeCount);

  // Determine summary text: plain_text_summary > short_description fallback
  let summaryText = null;
  if (paper.website_card?.plain_text_summary) {
    summaryText = paper.website_card.plain_text_summary;
  } else if (paper.website_card?.short_description) {
    summaryText = paper.website_card.short_description;
  }

  let card = `<div class="card" data-paper-id="${paper.paper_id}">`;
  card += `<h3>${escapeHtml(paper.title)} <span class="status-badge ${status.class}">${status.label}</span></h3>`;
  card += `<div class="meta">${escapeHtml(paper.authors)} · ${paper.year}</div>`;
  card += `<div class="meta">DOI: <a href="${paper.doi}" target="_blank">${paper.doi}</a></div>`;

  // Summary section (only if available)
  if (summaryText !== null) {
    card += `<div class="summary-section"><h4>Summary</h4><p>${escapeHtml(summaryText)}</p></div>`;
  }

  // Dataset features needed
  card += `<div class="features-section">`;
  card += `<h4>Dataset features needed</h4>`;
  card += `<div class="badges">`;
  for (const [key, label] of REFINE_FEATURES) {
    const val = paper.dataset_features_needed?.[key] || "unclear";
    card += `<span class="badge ${val}">${label}: ${val}</span>`;
  }
  card += `</div></div>`;

  // Coverage line
  const coverage = computeCoverageForPaper(paper.paper_id);
  card += `<div class="coverage-line">${renderCoverageLine(coverage)}</div>`;

  // Volunteer section
  if (activeCount === 0) {
    // No volunteers: show available badge and volunteer button
    card += `<button class="volunteer-btn" onclick="openVolunteerModal('${paper.paper_id}')">Volunteer to replicate this paper</button>`;
  } else {
    // One or more volunteers: show list and "Add another group" button
    card += renderVolunteerList(paperClaims);
    card += `<button class="volunteer-btn add-another-btn" onclick="openVolunteerModal('${paper.paper_id}')">Add another group</button>`;
  }

  card += `</div>`;
  return card;
}

function render() {
  // Collect active filter values keyed by feature key
  const activeFilters = {};
  for (const [key] of REFINE_FEATURES) {
    const sel = document.querySelector(`.filter select[data-key="${key}"]`);
    if (sel && sel.value !== "any") {
      activeFilters[key] = sel.value;
    }
  }

  const filtered = papers.filter(p => {
    const features = p.dataset_features_needed || {};
    for (const [key, filterVal] of Object.entries(activeFilters)) {
      const paperVal = features[key] || "unclear";
      // If filter is "yes", only show papers with yes
      if (filterVal === "yes" && paperVal !== "yes") return false;
      // If filter is "no", only show papers with no
      if (filterVal === "no" && paperVal !== "no") return false;
      // If filter is "unclear", only show papers with unclear
      if (filterVal === "unclear" && paperVal !== "unclear") return false;
      // If filter is "not_applicable", only show papers with not_applicable
      if (filterVal === "not_applicable" && paperVal !== "not_applicable") return false;
    }
    return true;
  });

  document.getElementById("count").textContent = `Showing ${filtered.length} of ${papers.length} papers`;

  document.getElementById("cards").innerHTML = filtered.map(renderCard).join("");
}

function buildFilters() {
  const container = document.getElementById("filters");
  let html = "";
  for (const [key, label] of REFINE_FEATURES) {
    html += `<div class="filter">`;
    html += `<label>${escapeHtml(label)}</label>`;
    html += `<select class="filter" data-key="${key}">`;
    html += `<option value="any">Any</option>`;
    html += `<option value="yes">Yes only</option>`;
    html += `<option value="no">No only</option>`;
    html += `<option value="unclear">Unclear only</option>`;
    html += `</select>`;
    html += `</div>`;
  }
  container.innerHTML = html;

  container.addEventListener("change", () => render());
}

async function init() {
  // Load papers
  const papersResp = await fetch("data/papers.json");
  papers = await papersResp.json();

  // Load and merge claims (both are arrays)
  const staticClaims = await loadStaticClaims();
  const demoClaims = loadDemoClaims();
  const merged = mergeClaims(staticClaims, demoClaims);
  claims = merged;

  buildFilters();
  render();

  // Setup reset button
  document.getElementById("reset").addEventListener("click", () => {
    document.querySelectorAll(".filter select").forEach(s => s.value = "any");
    render();
  });

  // Setup volunteer modal
  setupVolunteerModal();

  // Setup clear demo button
  document.getElementById("clear-demo").addEventListener("click", clearDemoSelections);

  // Setup export button
  document.getElementById("export-json").addEventListener("click", exportSelectionsAsJson);
}

function setupVolunteerModal() {
  const modal = document.getElementById("volunteer-modal");
  const closeBtn = document.getElementById("close-modal");
  const cancelBtn = document.getElementById("cancel-volunteer");
  const form = document.getElementById("volunteer-form");

  function closeModal() {
    modal.style.display = "none";
    form.reset();
  }

  closeBtn.addEventListener("click", closeModal);
  cancelBtn.addEventListener("click", closeModal);

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeModal();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.style.display !== "none") closeModal();
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();

    const paperId = document.getElementById("form-paper-id").value;
    const name = document.getElementById("form-name").value.trim();
    const institution = document.getElementById("form-institution").value.trim();
    const contact = document.getElementById("form-contact").value;
    const dataset = document.getElementById("form-dataset").value.trim();
    const replication = document.getElementById("form-replication").value;
    const mddN = document.getElementById("form-mdd-n").value;
    const healthyN = document.getElementById("form-healthy-n").value;
    const notes = document.getElementById("form-notes").value.trim();

    // Build new claim entry (array-based)
    const newClaim = {
      paper_id: paperId,
      status: "selected",
      volunteer_name: name,
      institution: institution,
      contact_preference: contact,
      dataset_description: dataset,
      replication_type: replication,
      notes: notes || "No additional notes"
    };

    // Add optional sample-size fields only if provided
    if (mddN !== "") {
      newClaim.mdd_n_available = parseInt(mddN, 10);
    }
    if (healthyN !== "") {
      newClaim.healthy_control_n_available = parseInt(healthyN, 10);
    }

    // Load current claims array and append the new claim
    const demoClaims = loadDemoClaims();
    demoClaims.push(newClaim);

    saveDemoClaims(demoClaims);

    // Reload static claims and re-merge
    loadStaticClaims().then(static => {
      claims = mergeClaims(static, demoClaims);
      render();
      closeModal();
    });
  });
}

function openVolunteerModal(paperId) {
  const modal = document.getElementById("volunteer-modal");
  const paperInfo = document.getElementById("modal-paper-info");
  const paperIdInput = document.getElementById("form-paper-id");

  // Find paper details
  const paper = papers.find(p => p.paper_id === paperId);
  if (paper) {
    paperInfo.textContent = `${paper.title} (${paper.paper_id})`;
  } else {
    paperInfo.textContent = `Paper ${paperId}`;
  }

  paperIdInput.value = paperId;
  modal.style.display = "flex";
}

function clearDemoSelections() {
  if (confirm("Clear all demo volunteer selections? This will restore the original static claims from claims.json.")) {
    const storage = { claims: [] };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(storage));

    // Reload static claims and re-render
    loadStaticClaims().then(static => {
      claims = mergeClaims(static, []);
      render();
    });
  }
}

function exportSelectionsAsJson() {
  const demoClaims = loadDemoClaims();

  // Build export from all claims (static + demo) as an array
  loadStaticClaims().then(static => {
    const allClaims = mergeClaims(static, demoClaims);
    const exportData = {
      claims: allClaims.map(c => ({
        paper_id: c.paper_id,
        status: c.status?.toLowerCase() || "available",
        volunteer_name: c.volunteer_name || "",
        institution: c.institution || "",
        contact_preference: c.contact_preference || "",
        dataset_description: c.dataset_description || "",
        replication_type: c.replication_type || "",
        notes: c.notes || ""
      }))
    };

    const jsonStr = JSON.stringify(exportData, null, 2);
    const output = document.getElementById("export-output");
    output.textContent = jsonStr;
    output.style.display = "block";

    // Also offer download
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

init();