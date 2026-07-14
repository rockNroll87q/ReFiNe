// ============================================================
// Base URL resolution — used when this app is served under sub-paths
// (e.g. /replication-targets/) so that data/ paths resolve correctly.
// ============================================================
const REFINE_BASE_URL = typeof window !== "undefined" && window.REFINE_BASE_URL ? window.REFINE_BASE_URL : "/";

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

// ============================================================
// GitHub registration config
// ============================================================
const GITHUB_REPO_URL = "https://github.com/rocknroll87q/ReFiNe";

function buildRegistrationIssueUrl(paper) {
  const paperId = paper.paper_id || "";
  const paperTitle = paper.title || "";
  const doi = paper.doi || "";

  // Build title: `Replication interest: REFINE-0003`
  const title = "Replication interest: " + paperId;

  // Build body with structured registration fields
  const lines = [
    "## Replication Interest Registration",
    "",
    "| Field | Value |",
    "| --- | --- |",
    "| **Paper ID** | " + paperId + " |",
    "| **Paper title** | " + paperTitle + " |",
    "| **DOI** | " + (doi ? "[" + doi + "](" + (doi.startsWith("http") ? doi : "https://doi.org/" + doi) + ") |" : "N/A |"),
    "",
    "---",
    "",
    "## Contributor / Group Information",
    "",
    "- **Name / group:** ",
    "- **Institution:** ",
    "",
    "---",
    "",
    "## Dataset Availability",
    "",
    "- [ ] I have access to the required dataset and can share it",
    "- [ ] I can re-collect data from scratch",
    "- [ ] I need to find / request access to the dataset",
    "",
    "---",
    "",
    "## Replication Plan",
    "",
    "- [ ] Direct replication (exact same methods)",
    "- [ ] Partial replication (key analyses only)",
    "- [ ] Exploratory replication (related questions)",
    "",
    "---",
    "",
    "## Additional Information",
    "",
    "- **Public listing:** I agree to have this registration listed publicly on GitHub.",
    "- **Notes for organisers:** ",
    ""
  ];

  const body = lines.join("\n");

  // Build URL with query parameters
  const baseUrl = GITHUB_REPO_URL + "/issues/new";
  const params = new URLSearchParams();
  params.set("title", title);
  params.set("body", body);
  params.set("labels", "replication-registration");

  return baseUrl + "?" + params.toString();
}

let papers = [];
let claims = [];

// Load static claims from claims.json (returns array) — uses REFINE_BASE_URL
async function loadStaticClaims() {
  try {
    const resp = await fetch(`${REFINE_BASE_URL}data/claims.json`);
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
    const raw = localStorage.getItem("refine_demo_claims");
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
    localStorage.setItem("refine_demo_claims", JSON.stringify(storage));
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

// Statuses that count as active registrations on the website
const _ACTIVE_REGISTRATION_STATUSES = new Set([
  "pending", "confirmed", "in_progress", "completed",
  // Legacy statuses for backward compatibility
  "selected", "volunteer_pending",
]);

function hasActiveClaimForPaper(paperId) {
  return getClaimsForPaper(paperId).some(
    c => _ACTIVE_REGISTRATION_STATUSES.has((c.status || "").toLowerCase())
  );
}

/**
 * Count active registrations for a paper and return a display object.
 * Supports multiple groups per paper (one record per GitHub issue).
 */
function getStatusDisplay(count) {
  if (count === 0) return { label: "Open — no groups registered", class: "status-available" };
  if (count === 1) return { label: "Open — 1 group registered", class: "status-selected" };
  return { label: `Open — ${count} groups registered`, class: "status-volunteer-pending" };
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
        html += `<div class="detail-row"><span class="detail-label">Replication type:</span> ${escapeHtml(claim.replication_type)}</div>`;
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
// Extract author text from a paper's metadata
// Checks dedicated fields first, then falls back to citation
// ============================================================
function getAuthorsText(paper) {
  try {
    if (!paper) return "Unknown authors";

    if (Array.isArray(paper.authors) && paper.authors.length) {
      return escapeHtml(paper.authors.join(", "));
    }

    if (typeof paper.authors === "string" && paper.authors.trim()) {
      return escapeHtml(paper.authors.trim());
    }

    if (typeof paper.author === "string" && paper.author.trim()) {
      return escapeHtml(paper.author.trim());
    }

    if (typeof paper.citation === "string" && paper.citation.trim()) {
      const citation = paper.citation.trim();
      const match = citation.match(/^(.*?)\s*\(\d{4}[a-z]?\)\./i);
      const authorPart = match ? match[1].trim() : "";

      if (authorPart) {
        const firstAuthor = authorPart.split(",")[0].trim();
        if (firstAuthor) {
          if (authorPart.includes(",") || authorPart.includes("&")) {
            return `${firstAuthor} et al.`;
          }
          return firstAuthor;
        }
      }
    }

    return "Unknown authors";
  } catch (err) {
    console.warn("Could not parse authors", err, paper);
    return "Unknown authors";
  }
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
  // Count only active registrations (exclude withdrawn, malformed, invalid paper_id)
  const _PAPER_ID_RE = /^REFINE-\d{4}$/i;
  const activeCount = paperClaims.filter(c => {
    if (!c || typeof c !== "object") return false;
    if (!c.paper_id || !_PAPER_ID_RE.test(c.paper_id)) return false;
    return _ACTIVE_REGISTRATION_STATUSES.has((c.status || "").toLowerCase());
  }).length;
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
  card += `<div class="meta">${getAuthorsText(paper)} · ${paper.year}</div>`;
  const doiUrl = paper.doi ? (paper.doi.startsWith('http') ? paper.doi : `https://doi.org/${paper.doi}`) : '';
  card += `<div class="meta">DOI: ${doiUrl ? `<a href="${doiUrl}" target="_blank" rel="noopener noreferrer">${paper.doi || "N/A"}</a>` : "N/A"}</div>`;

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

  // Registration button — always shown, opens GitHub issue in new tab
  const regUrl = buildRegistrationIssueUrl(paper);
  card += `<a class="volunteer-btn register-link" href="${regUrl}" target="_blank" rel="noopener noreferrer">Register interest</a>`;

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
  // Load papers — use REFINE_BASE_URL so paths resolve correctly under sub-paths
  const papersResp = await fetch(`${REFINE_BASE_URL}data/papers.json`);
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

  // Append registration info note below the results count
  const countEl = document.getElementById("count");
  if (countEl) {
    const noteDiv = document.createElement("div");
    noteDiv.className = "registration-note";
    noteDiv.textContent = "Registrations are submitted as public GitHub issues and used to coordinate ReFiNe replication efforts.";
    countEl.parentNode.insertBefore(noteDiv, countEl.nextSibling);
  }
}

init();
