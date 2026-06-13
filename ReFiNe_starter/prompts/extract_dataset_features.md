You are extracting broad dataset features needed to attempt a replication for the ReFiNe project.

## Rules

- Use ONLY information explicitly reported in the paper.
- Do NOT infer, guess, or assume missing information.
- Bias toward "unclear" when information is missing, ambiguous, or only implied.
- Return valid JSON only. NO markdown formatting, NO code fences, NO explanations, NO comments.

## Allowed values

- `"yes"` — the paper explicitly reports this feature
- `"no"` — the paper explicitly states absence or non-use of this feature
- `"unclear"` — the information is missing, ambiguous, or only implied
- `"not_applicable"` — this feature does not apply to this type of study

## Features to extract

{
  "paper_id": "refine_0001",
  "dataset_features_needed": {
    "t1w_mri": "unclear",
    "vbm_or_voxelwise_morphometry": "unclear",
    "mdd_patients": "unclear",
    "healthy_controls": "unclear",
    "genetic_data": "unclear",
    "depression_scale": "unclear",
    "anxiety_scale": "unclear",
    "clinical_outcomes": "unclear",
    "longitudinal_data": "unclear",
    "medication_status": "unclear",
    "trauma_or_life_stress": "unclear",
    "cognitive_data": "unclear",
    "blood_or_biomarker_data": "unclear"
  },
  "website_card": {
    "short_description": null,
    "dataset_features_summary": []
  },
  "extraction_status": "completed",
  "extraction_notes": null
}

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
