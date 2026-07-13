// ============================================================
// Tag-label mapping for filter_tags taxonomy
// Uses exact internal tag values from paper.filter_tags
// ============================================================
const FILTER_GROUP_CONFIG = [
  {
    key: "imaging",
    label: "Imaging",
    tags: [
      { value: "voxel_based_morphometry_t1w_mri", label: "Voxel-based morphometry (T1-weighted MRI)" },
      { value: "parcellation_based_morphometry_t1w_mri", label: "Parcellation-based morphometry (T1-weighted MRI)" },
      { value: "vertex_wise_morphometry_t1w_mri", label: "Vertex-wise morphometry (T1-weighted MRI)" },
      { value: "voxel_wise_task_related_activity_tb_fmri", label: "Voxel-wise task-related activity (task-based fMRI)" },
      { value: "seed_to_voxel_functional_connectivity_rs_fmri", label: "Seed-to-voxel functional connectivity (resting-state fMRI)" }
    ]
  },
  {
    key: "population",
    label: "Population",
    tags: [
      { value: "healthy", label: "Healthy" },
      { value: "clinical", label: "Clinical" },
      { value: "mixed_clinical_and_healthy_controls", label: "Mixed clinical and healthy controls" }
    ]
  },
  {
    key: "clinical_group",
    label: "Clinical group",
    tags: [
      { value: "mood_affective_disorders", label: "Mood / affective disorders" },
      { value: "anxiety_stress_ocd_disorders", label: "Anxiety-, stress-, and OCD-related disorders" },
      { value: "psychotic_disorders", label: "Psychotic disorders" },
      { value: "neurodevelopmental_disorders", label: "Neurodevelopmental disorders" },
      { value: "neurological_disorders", label: "Neurological disorders" },
      { value: "dementia_neurodegenerative_disorders", label: "Dementia / neurodegenerative disorders" },
      { value: "other_clinical_group", label: "Other clinical group" }
    ]
  },
  {
    key: "age_group",
    label: "Age group",
    tags: [
      { value: "children", label: "Children" },
      { value: "adolescents", label: "Adolescents" },
      { value: "young_adults", label: "Young adults" },
      { value: "adults", label: "Adults" },
      { value: "older_adults", label: "Older adults" },
      { value: "mixed_lifespan", label: "Mixed lifespan" }
    ]
  },
  {
    key: "study_design",
    label: "Study design",
    tags: [
      { value: "cross_sectional", label: "Cross-sectional" },
      { value: "longitudinal", label: "Longitudinal" },
      { value: "intervention_treatment", label: "Intervention / treatment" },
      { value: "case_control", label: "Case-control" },
      { value: "cohort_population_based", label: "Cohort / population-based" }
    ]
  },
  {
    key: "associated_data",
    label: "Associated data required",
    tags: [
      { value: "depression_severity", label: "Depression severity" },
      { value: "anxiety_severity", label: "Anxiety severity" },
      { value: "general_psychopathology", label: "General psychopathology" },
      { value: "diagnosis_clinical_status", label: "Diagnosis / clinical status" },
      { value: "illness_duration", label: "Illness duration" },
      { value: "age_of_onset", label: "Age of onset" },
      { value: "episode_history", label: "Episode history" },
      { value: "comorbidity", label: "Comorbidity" },
      { value: "medication_status", label: "Medication status" },
      { value: "psychotherapy", label: "Psychotherapy" },
      { value: "treatment_response", label: "Treatment response" },
      { value: "remission_relapse", label: "Remission / relapse" },
      { value: "childhood_trauma", label: "Childhood trauma" },
      { value: "stressful_life_events", label: "Stressful life events" },
      { value: "social_relationships", label: "Social relationships" },
      { value: "socioeconomic_adversity", label: "Socioeconomic adversity" },
      { value: "iq", label: "IQ" },
      { value: "executive_function", label: "Executive function" },
      { value: "memory", label: "Memory" },
      { value: "behavioural_scales", label: "Behavioural scales" },
      { value: "genetics", label: "Genetics" },
      { value: "blood_biomarkers", label: "Blood biomarkers" },
      { value: "cortisol_endocrine_markers", label: "Cortisol / endocrine markers" },
      { value: "microbiome", label: "Microbiome" },
      { value: "other_omics", label: "Other omics" },
      { value: "smoking", label: "Smoking" },
      { value: "physical_activity", label: "Physical activity" },
      { value: "sleep", label: "Sleep" },
      { value: "education", label: "Education" },
      { value: "employment", label: "Employment" },
      { value: "socioeconomic_status", label: "Socioeconomic status" }
    ]
  }
];

// Legacy REFINE_FEATURES kept for volunteer/claim rendering (not used as main filter)
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

// ============================================================
// Get display label for a filter tag value using the config
// ============================================================
function getTagLabel(tagValue) {
  for (const group of FILTER_GROUP_CONFIG) {
    const found = group.tags.find(t => t.value === tagValue);
    if (found) return found.label;
  }
  // Fallback: convert snake_case to readable
  return tagValue.replace(/_/g, " ");
}

// Track which dropdown is currently open (only one at a time)
let _openDropdownGroup = null;

// Close all dropdown panels
function closeAllDropdowns() {
  document.querySelectorAll(".compact-filter-btn").forEach(btn => {
    btn.classList.remove("active", "open");
  });
  document.querySelectorAll(".filter-dropdown-panel").forEach(panel => {
    panel.classList.remove("show");
  });
  _openDropdownGroup = null;
}

// ============================================================
// Render paper card with Summary + Replication requirements tags
// ============================================================
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
  card += `<div class="meta">${escapeHtml(paper.authors || "Unknown authors")} · ${paper.year}</div>`;
  card += `<div class="meta">DOI: <a href="${paper.doi}" target="_blank">${paper.doi || "N/A"}</a></div>`;

  // Summary section (only if available)
  if (summaryText !== null) {
    card += `<div class="summary-section"><h4>Summary</h4><p>${escapeHtml(summaryText)}</p></div>`;
  }

  // Required data section - compact single row from all filter_tags
   const filterTags = paper.filter_tags || {};
   const hasFilterTags = Object.values(filterTags).some(arr => Array.isArray(arr) && arr.length > 0);

   if (hasFilterTags) {
     // Collect all tags across groups into a flat array
     const allTags = [];
     for (const group of FILTER_GROUP_CONFIG) {
       const tags = filterTags[group.key] || [];
       for (const tag of tags) {
         allTags.push(tag);
       }
     }

     card += `<div class="replication-requirements">`;
     card += `<h4>Required data:</h4>`;
     card += `<div class="req-chips-inline">`;
     for (const tag of allTags) {
       const label = getTagLabel(tag);
       card += `<span class="req-chip">${escapeHtml(label)}</span>`;
     }
     card += `</div></div>`;
   }

  // Coverage line
  const coverage = computeCoverageForPaper(paper.paper_id);
  card += `<div class="coverage-line">${renderCoverageLine(coverage)}</div>`;

  // Volunteer section
  if (activeCount === 0) {
    card += `<button class="volunteer-btn" onclick="openVolunteerModal('${paper.paper_id}')">Volunteer to replicate this paper</button>`;
  } else {
    card += renderVolunteerList(paperClaims);
    card += `<button class="volunteer-btn add-another-btn" onclick="openVolunteerModal('${paper.paper_id}')">Add another group</button>`;
  }

  card += `</div>`;
  return card;
}

// ============================================================
// Search matching (unchanged logic, combined with filters via AND)
// ============================================================
function matchesSearch(paper, query) {
  const q = query.toLowerCase().trim();
  if (!q) return true;

  function textMatch(text) {
    if (!text) return false;
    return String(text).toLowerCase().includes(q);
  }

  function arrayMatch(arr) {
    if (!Array.isArray(arr)) return false;
    return arr.some(item => String(item).toLowerCase().includes(q));
  }

  if (textMatch(paper.paper_id)) return true;
  if (textMatch(paper.title)) return true;
  if (textMatch(paper.year)) return true;
  if (textMatch(paper.doi)) return true;
  if (paper.citation && textMatch(paper.citation)) return true;
  if (textMatch(paper.disease)) return true;
  if (textMatch(paper.family)) return true;
  if (textMatch(paper.diagnosis)) return true;

  const wc = paper.website_card || {};
  if (textMatch(wc.short_description)) return true;
  if (textMatch(wc.plain_text_summary)) return true;
  if (arrayMatch(wc.dataset_features_summary)) return true;

  // Also search within filter_tags for richer text matching
  const ft = paper.filter_tags || {};
  for (const catTags of Object.values(ft)) {
    if (Array.isArray(catTags)) {
      for (const tag of catTags) {
        if (textMatch(tag)) return true;
      }
    }
  }

  return false;
}

// ============================================================
// Filter logic: grouped multi-select with AND across groups, OR within groups
// ============================================================
function getActiveFilters() {
  // Returns array of { groupKey, tagValue } for all selected tags
  const active = [];
  for (const group of FILTER_GROUP_CONFIG) {
    for (const tag of group.tags) {
      const checkbox = document.getElementById(`filter-${group.key}-${tag.value}`);
      if (checkbox && checkbox.checked) {
        active.push({ groupKey: group.key, tagValue: tag.value });
      }
    }
  }
  return active;
}

function paperMatchesFilters(paper, activeFilters) {
  // If no filters selected, show all papers (including those without filter_tags)
  if (activeFilters.length === 0) {
    return true;
  }

  const paperTags = paper.filter_tags || {};

  // Group active filters by group key for OR logic within groups
  const filtersByGroup = {};
  for (const f of activeFilters) {
    if (!filtersByGroup[f.groupKey]) {
      filtersByGroup[f.groupKey] = [];
    }
    filtersByGroup[f.groupKey].push(f.tagValue);
  }

  // For each group, check if paper has at least one matching tag (OR logic within group)
  for (const [groupKey, requiredTags] of Object.entries(filtersByGroup)) {
    const paperGroupTags = paperTags[groupKey] || [];

    // If the filter group requires a tag that the paper doesn't have any tags for, exclude
    // Papers without filter_tags should be excluded when filters are active
    if (paperGroupTags.length === 0) {
      return false;
    }

    // Check OR logic: at least one of requiredTags must match
    const hasMatch = requiredTags.some(tag => paperGroupTags.includes(tag));
    if (!hasMatch) {
      return false;
    }
  }

  return true;
}

// ============================================================
// Render active filter chips (inline in the bar) — always visible
// ============================================================
function renderActiveFilterChips(activeFilters) {
  const bar = document.getElementById("active-filters-bar");
  const chipsContainer = document.getElementById("active-filters-chips");
  const resetBtn = document.getElementById("reset-filters-btn");

  // Always show the bar (even when nothing is active)
  bar.style.display = "flex";

  // Reset filters button always visible
  resetBtn.style.display = "inline-block";

  // Get search state for display
  const searchInput = document.getElementById("search-input");
  const hasSearch = searchInput && searchInput.value.trim() !== "";

  let html = "";
  if (activeFilters.length === 0 && !hasSearch) {
    // No filters or search active — show "none" placeholder
    html = '<span class="no-filters-label">none</span>';
  } else {
    // Show active filter chips
    for (const f of activeFilters) {
      const label = getTagLabel(f.tagValue);
      html += `<span class="filter-chip" data-group="${f.groupKey}" data-tag="${f.tagValue}">`;
      html += `${escapeHtml(label)} <button class="chip-remove" onclick="removeFilterChip('${f.groupKey}','${f.tagValue}')">&times;</button>`;
      html += `</span>`;
    }
    // Show active search term as a chip
    if (hasSearch) {
      const searchTerm = searchInput.value.trim();
      html += `<span class="filter-chip" data-type="search">`;
      html += `🔍 ${escapeHtml(searchTerm)} <button class="chip-remove" onclick="clearSearchFromChip()">&times;</button>`;
      html += `</span>`;
    }
  }
  chipsContainer.innerHTML = html;
}

// ============================================================
// Clear search from the active filter chip (called from inline onclick)
// ============================================================
function clearSearchFromChip() {
  const searchInput = document.getElementById("search-input");
  const clearBtn = document.getElementById("clear-search");
  if (searchInput) {
    searchInput.value = "";
    render();
    if (clearBtn) clearBtn.style.display = "none";
    searchInput.focus();
  }
}

// ============================================================
// Remove a single filter chip (called from inline onclick)
// ============================================================
function removeFilterChip(groupKey, tagValue) {
  const checkbox = document.getElementById(`filter-${groupKey}-${tagValue}`);
  if (checkbox) {
    checkbox.checked = false;
    render();
  }
}

// ============================================================
// Main render function
// ============================================================
function render() {
  // Get search query
  const searchInput = document.getElementById("search-input");
  const clearBtn = document.getElementById("clear-search");
  const searchQuery = searchInput ? searchInput.value : "";

  // Show/hide clear button based on search input
  if (clearBtn) {
    clearBtn.style.display = searchQuery.trim() ? "inline-block" : "none";
  }

  // Collect active filters
  const activeFilters = getActiveFilters();

  // Render active filter chips
  renderActiveFilterChips(activeFilters);

  // Filter papers: text search AND grouped filters combined with AND logic
  const filtered = papers.filter(p => {
    // Text search (AND)
    if (!matchesSearch(p, searchQuery)) return false;

    // Grouped tag filters (AND across groups, OR within groups)
    if (!paperMatchesFilters(p, activeFilters)) return false;

    return true;
  });

  document.getElementById("count").textContent = `Showing ${filtered.length} of ${papers.length} papers`;
  document.getElementById("cards").innerHTML = filtered.map(renderCard).join("");
}

// ============================================================
// Build compact filter buttons + dropdown panels from FILTER_GROUP_CONFIG
// ============================================================
function buildFilterGroups() {
  const btnRow = document.getElementById("filter-buttons-row");
  const dropContainer = document.getElementById("filter-dropdowns-container");
  let btnHtml = "";
  let dropHtml = "";

  for (const group of FILTER_GROUP_CONFIG) {
    // Button for this filter group
    btnHtml += `<button class="compact-filter-btn" data-group="${group.key}" title="Filter by ${escapeHtml(group.label)}">`;
    btnHtml += `${escapeHtml(group.label)} <span class="arrow">▼</span>`;
    btnHtml += `</button>`;

    // Dropdown panel for this filter group
    dropHtml += `<div class="filter-dropdown-panel" data-group="${group.key}"><div class="filter-chips-wrap">`;

    for (const tag of group.tags) {
      const checkboxId = `filter-${group.key}-${tag.value}`;
      dropHtml += `<label class="filter-chip-input" for="${checkboxId}">`;
      dropHtml += `<input type="checkbox" id="${checkboxId}" data-group="${group.key}" data-tag="${tag.value}">`;
      dropHtml += `<span class="chip-label">${escapeHtml(tag.label)}</span>`;
      dropHtml += `</label>`;
    }

    dropHtml += `</div></div>`;
  }

  btnRow.innerHTML = btnHtml;
  dropContainer.innerHTML = dropHtml;

  // Click handler for filter group buttons (toggle dropdown)
  btnRow.addEventListener("click", (e) => {
    const btn = e.target.closest(".compact-filter-btn");
    if (!btn) return;

    const groupKey = btn.dataset.group;
    const panel = dropContainer.querySelector(`.filter-dropdown-panel[data-group="${groupKey}"]`);

    // If clicking the already-open button, close it
    if (_openDropdownGroup === groupKey) {
      closeAllDropdowns();
      return;
    }

    // Close any open dropdown first
    closeAllDropdowns();

    // Open this one - position panel below the button
    btn.classList.add("active", "open");
    panel.classList.add("show");

    // Position the panel directly below its button (viewport-relative for position:fixed)
    const btnRect = btn.getBoundingClientRect();
    panel.style.left = btnRect.left + "px";
    panel.style.top = btnRect.bottom + 4 + "px";

    _openDropdownGroup = groupKey;
  });

  // Listen for checkbox changes inside dropdown panels
  dropContainer.addEventListener("change", (e) => {
    if (e.target.type === "checkbox") {
      render();
    }
  });

  // Close dropdowns when clicking outside
  document.addEventListener("click", (e) => {
    if (!_openDropdownGroup) return;
    const btnRowEl = document.getElementById("filter-buttons-row");
    const dropContainerEl = document.getElementById("filter-dropdowns-container");
    if (!btnRowEl.contains(e.target) && !dropContainerEl.contains(e.target)) {
      closeAllDropdowns();
    }
  });

  // Reposition dropdown on scroll to keep it aligned with its button
  window.addEventListener("scroll", () => {
    if (_openDropdownGroup) {
      const btn = document.querySelector(`.compact-filter-btn[data-group="${_openDropdownGroup}"]`);
      const panel = dropContainer.querySelector(`.filter-dropdown-panel[data-group="${_openDropdownGroup}"]`);
      if (btn && panel) {
        const btnRect = btn.getBoundingClientRect();
        panel.style.top = btnRect.bottom + 4 + "px";
      }
    }
  });
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

  buildFilterGroups();
  render();

  // Setup reset filters button (primary in active-filters-bar)
  document.getElementById("reset-filters-btn").addEventListener("click", () => {
    closeAllDropdowns();
    document.querySelectorAll("#filter-buttons-row ~ * input[type=checkbox], .filter-dropdown-panel input[type=checkbox]").forEach(cb => cb.checked = false);
    const searchInput = document.getElementById("search-input");
    if (searchInput) searchInput.value = "";
    render();
  });

  // Setup search input - debounce to avoid excessive re-renders
  const searchInput = document.getElementById("search-input");
  let searchDebounceTimer = null;
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      clearTimeout(searchDebounceTimer);
      searchDebounceTimer = setTimeout(() => render(), 150);
    });

    // Setup clear button
    const clearBtn = document.getElementById("clear-search");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        searchInput.value = "";
        clearBtn.style.display = "none";
        render();
        searchInput.focus();
      });
    }
  }

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