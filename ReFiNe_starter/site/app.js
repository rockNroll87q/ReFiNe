const FEATURE_KEYS = [
  "t1w_mri",
  "fmap",
  "resting_state_fMRI",
  "task_fMRI",
  "dti",
  "pet",
  "eeeg",
  "meg",
  "eyetracking",
  "genetic_or_genomic_data",
  "structural_connectivity"
];

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
let claims = [];

// Load static claims from claims.json
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

// Load demo claims from localStorage
function loadDemoClaims() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    console.warn("Could not load demo claims from localStorage:", e);
    return {};
  }
}

// Save demo claims to localStorage
function saveDemoClaims(demoClaims) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(demoClaims));
  } catch (e) {
    console.warn("Could not save demo claims to localStorage:", e);
  }
}

// Merge static claims and demo claims
function mergeClaims(staticClaims, demoClaims) {
  const merged = {};

  // Start with static claims
  for (const claim of staticClaims) {
    merged[claim.paper_id] = { ...claim };
  }

  // Overlay demo claims (demo takes precedence)
  for (const [paperId, demoClaim] of Object.entries(demoClaims)) {
    if (merged[paperId]) {
      // Merge: demo values override static
      merged[paperId] = { ...merged[paperId], ...demoClaim };
    } else {
      merged[paperId] = { ...demoClaim };
    }
  }

  return merged;
}

function getClaimForPaper(paperId) {
  return claims[paperId] || null;
}

function getStatusDisplay(claim) {
  if (!claim) return { label: "Available", class: "status-available" };
  const status = claim.status?.toLowerCase() || "available";
  if (status === "selected") return { label: "Selected", class: "status-selected" };
  if (status === "volunteer_pending") return { label: "Volunteer pending", class: "status-volunteer-pending" };
  return { label: "Available", class: "status-available" };
}

function renderVolunteerInfo(claim) {
  if (!claim) return "";

  let html = `<div class="volunteer-info">`;
  html += `<p><strong>Volunteer:</strong> ${escapeHtml(claim.volunteer_name || "")}</p>`;
  html += `<p><strong>Institution:</strong> ${escapeHtml(claim.institution || "")}</p>`;

  if (claim.notes || claim.dataset_description || claim.replication_type) {
    html += `<details>`;
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
  return html;
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderCard(paper) {
  const claim = getClaimForPaper(paper.paper_id);
  const status = getStatusDisplay(claim);

  let card = `<div class="card" data-paper-id="${paper.paper_id}">`;
  card += `<h3>${escapeHtml(paper.title)} <span class="status-badge ${status.class}">${status.label}</span></h3>`;
  card += `<div class="meta">${escapeHtml(paper.authors)} · ${paper.year}</div>`;
  card += `<div class="meta">DOI: <a href="${paper.doi}" target="_blank">${paper.doi}</a></div>`;

  // Dataset features needed
  card += `<p><strong>Dataset features needed:</strong></p>`;
  card += `<div class="badges">`;
  for (const key of FEATURE_KEYS) {
    const val = paper.dataset_features_needed?.[key] || "unclear";
    const label = key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    card += `<span class="badge ${val}">${label}: ${val}</span>`;
  }
  card += `</div>`;

  // Volunteer button for available papers
  if (!claim) {
    card += `<button class="volunteer-btn" onclick="openVolunteerModal('${paper.paper_id}')">Volunteer to replicate this paper</button>`;
  } else if (claim.status?.toLowerCase() === "selected" || claim.status?.toLowerCase() === "volunteer_pending") {
    card += renderVolunteerInfo(claim);
  }

  card += `</div>`;
  return card;
}

function render() {
  const activeFilters = new Set(
    Array.from(document.querySelectorAll(".filter select"))
      .map(s => s.value)
      .filter(v => v !== "any")
  );

  const filtered = papers.filter(p => {
    const features = p.dataset_features_needed || {};
    for (const key of activeFilters) {
      if (features[key] !== "yes") return false;
    }
    return true;
  });

  document.getElementById("count").textContent = `Showing ${filtered.length} of ${papers.length} papers`;

  document.getElementById("cards").innerHTML = filtered.map(renderCard).join("");
}

function buildFilters() {
  const container = document.getElementById("filters");
  let html = "";
  for (const key of FEATURE_KEYS) {
    const label = key.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
    html += `<div class="filter">`;
    html += `<label>${label}</label>`;
    html += `<select class="filter" data-key="${key}">`;
    html += `<option value="any">Any</option>`;
    html += `<option value="yes">Yes only</option>`;
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

  // Load and merge claims
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
    const notes = document.getElementById("form-notes").value.trim();

    // Get current demo claims
    const demoClaims = loadDemoClaims();

    // Save demo claim
    demoClaims[paperId] = {
      paper_id: paperId,
      status: "selected",
      volunteer_name: name,
      institution: institution,
      contact_preference: contact,
      dataset_description: dataset,
      replication_type: replication,
      notes: notes || "No additional notes"
    };

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
    localStorage.removeItem(STORAGE_KEY);

    // Reload static claims and re-render
    loadStaticClaims().then(static => {
      claims = mergeClaims(static, {});
      render();
    });
  }
}

function exportSelectionsAsJson() {
  const demoClaims = loadDemoClaims();
  const staticClaims = claims; // This is already merged, need to get fresh static

  // Build export from all claims (static + demo)
  loadStaticClaims().then(static => {
    const allClaims = mergeClaims(static, demoClaims);
    const exportData = {
      claims: Object.values(allClaims).map(c => ({
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