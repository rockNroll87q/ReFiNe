You are extracting broad dataset features needed to attempt a replication for the ReFiNe project.

## Rules

- Use ONLY information explicitly reported in the paper text below.
- Do NOT infer, guess, or assume missing information.
- Bias toward "unclear" when information is missing, ambiguous, or only implied.
- Return valid JSON only. NO markdown formatting, NO code fences, NO explanations, NO comments.
- **Do NOT copy any example values.** Every feature must be determined from the actual paper text below.
- **Do NOT return placeholder values.** If you cannot determine a feature from the text, use "unclear".
- The `paper_id` field MUST exactly match the requested paper ID: {{PAPER_ID}}

## Paper ID

Requesting extraction for paper: **{{PAPER_ID}}**

## Allowed values

- `"yes"` — the paper explicitly reports that this data type or measure was used in this study
- `"no"` — the paper explicitly states that the feature was absent, not assessed, or not part of the study
- `"unclear"` — the information is not reported, ambiguous, or only implied (not directly stated)
- `"not_applicable"` — this feature does not apply to this type of study design

## Required JSON schema (no example values — fill from paper text)

Return a JSON object with these keys:
- `paper_id` (string): MUST exactly match the requested paper ID. Do NOT modify it.
- `dataset_features_needed` (object): For each feature key below, set one of "yes", "no", "unclear", "not_applicable" based on the actual paper text.
- `website_card` (object) with these fields:
  - `short_description`: null or a short string summarizing the paper in one sentence.
  - `dataset_features_summary`: [list of strings] — brief bullet-style summaries of dataset features needed for replication.
  - `plain_text_summary`: A plain-English summary of 2–3 sentences focused on:
    1. Data used / population / imaging modality (e.g., "T1-weighted MRI from 112 healthy volunteers").
    2. Main broad result (e.g., "FKBP5 genotypes were associated with grey matter volume in the amygdala.").
    3. Key data requirements useful for replication (e.g., "Replication would require access to raw MRI scans, FKBP5 SNP genotype data, and mood/anxiety scale scores.").
    - Do NOT include detailed statistics, p-values, coordinates, or overly technical model details.
- `filter_tags` (object): Structured filter tags for the replication-target catalogue. Each category is an array of strings. Only assign tags when explicitly supported by the paper text. Use empty arrays if no tag applies.
  - `imaging`: One or more from: "voxel_based_morphometry_t1w_mri", "parcellation_based_morphometry_t1w_mri", "vertex_wise_morphometry_t1w_mri", "voxel_wise_task_related_activity_task_fmri", "seed_to_voxel_functional_connectivity_resting_fmri"
  - `population`: One of: "healthy", "clinical", "mixed_clinical_and_healthy_controls"
  - `clinical_group`: One level only (no subgroups): "mood_affective_disorders", "anxiety_stress_ocd_related_disorders", "psychotic_disorders", "neurodevelopmental_disorders", "neurological_disorders", "dementia_neurodegenerative_disorders", "other_clinical_group"
  - `age_group`: One of: "children", "adolescents", "young_adults", "adults", "older_adults", "mixed_lifespan"
    Assign age-group tags whenever the paper reports participant age ranges, mean ages, school stage, or cohort age.
    Use "children" for pre-adolescent samples (typically under 13).
    Use "adolescents" for teenage samples (approximately 13–19 years).
    Use "young_adults" for university-age or early-adult samples (approximately 18–30 years).
    Use "adults" for general adult samples.
    Use "older_adults" for late-life or ageing samples (typically 60+ years).
    Use "mixed_lifespan" when the sample clearly spans multiple life stages.
    If uncertain, prefer fewer tags, but do not leave age_group empty when the age range is explicitly stated.
  - `study_design`: One or more from: "cross_sectional", "longitudinal", "intervention_treatment", "case_control", "cohort_population_based"
    Use "cross_sectional" when the neuroimaging analysis uses one imaging timepoint per participant, even if participants come from a longitudinal cohort.
    Use "longitudinal" only when the replication would require repeated imaging, longitudinal outcome modelling, follow-up diagnoses, or within-person change over time.
    Do NOT tag "longitudinal" only because questionnaires or life-event measures were collected at multiple ages, unless the paper explicitly models longitudinal change or requires follow-up for the main finding.
    Use "case_control" together with "cross_sectional" when the study compares clinical participants and controls at one timepoint.
    Use "cohort_population_based" when the paper uses a community/population cohort rather than a selected case-control clinical sample.
  - `associated_data`: Zero or more from: "depression_severity", "anxiety_severity", "general_psychopathology", "diagnosis_clinical_status", "illness_duration", "age_of_onset", "episode_history", "comorbidity", "medication_status", "psychotherapy", "treatment_response", "remission_relapse", "childhood_trauma", "stressful_life_events", "social_relationships", "socioeconomic_adversity", "iq", "executive_function", "memory", "behavioural_scales", "genetics", "blood_biomarkers", "cortisol_endocrine_markers", "microbiome", "other_omics", "smoking", "physical_activity", "sleep", "education", "employment", "socioeconomic_status"
- `extraction_status` (string): "completed" if you extracted features from the paper text.
- `extraction_notes` (string or null): Brief notes about your extraction.

## Feature definitions

- **t1w_mri**: T1-weighted MRI data was acquired
- **vbm_or_voxelwise_morphometry**: VBM or voxel-wise morphometric analysis was performed
- **mdd_patients**: Major Depressive Disorder (MDD) patients were studied
- **healthy_controls**: Healthy control subjects were included
- **genetic_data**: Genetic or genotypic data was collected/used
- **depression_scale**: Standardized depression rating scales were used (e.g., HAM-D, MADRS, BDI)
- **anxiety_scale**: Standardized anxiety rating scales were used (e.g., HAM-A, GAD-7)
- **clinical_outcomes**: Clinical outcome measures were reported
- **longitudinal_data**: Longitudinal/follow-up data was collected (multiple time points)
- **medication_status**: Medication status or history was recorded
- **trauma_or_life_stress**: Trauma or life stress exposure was assessed
- **cognitive_data**: Cognitive assessment data was collected
- **blood_or_biomarker_data**: Blood samples or biological biomarkers were measured

## Paper text (extracted from PDF)

{{PAPER_TEXT}}

