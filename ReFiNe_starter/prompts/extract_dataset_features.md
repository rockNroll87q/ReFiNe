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
- `website_card` (object): {"short_description": null or string, "dataset_features_summary": [list of strings]}
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

