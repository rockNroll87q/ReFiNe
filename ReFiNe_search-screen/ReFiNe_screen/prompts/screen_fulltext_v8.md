You are screening a research paper for eligibility in the ReFiNe replication-data project (depression-related variables and gray matter brain structure, measured with MRI / voxel-based morphometry). You will see the paper's title and its FULL TEXT (converted from the PDF; section headings preserved, occasionally with layout noise). Your job is to score each criterion below EXACTLY as a careful human screener would from this information.

## Rules

- Use ONLY information explicitly stated in the provided paper text.
- Do NOT infer, guess, or assume missing information. If a detail (e.g., voxel size) is not reported anywhere in the text, the answer is "n/a".
- Return valid JSON only. NO markdown formatting, NO code fences, NO explanations outside the JSON, NO comments.
- **Do NOT copy any example values.** Every criterion must be determined from the actual paper text below.
- The `candidate_id` field MUST exactly match the requested candidate ID: {{CANDIDATE_ID}}

## Scoring principles (read carefully)

- Score what THIS study did with its own data and analyses. Content that merely cites, reviews, or meta-analyzes results from other studies is NOT evidence for this study's own methods or statistics.
- **Own participants only.** For `living_human_subjects` and `past_infancy`, judge the human components of THIS study (its own collected/acquired data). External public reference datasets or atlas data used purely as a comparison target do NOT count.
- `depression_related` asks whether depression is part of the study's MAIN research question. Answer 1 when depression (diagnosis, depressive symptoms, mood states / low mood / negative affect, subtypes or course of illness) is a primary focus or a main group/outcome related to gray matter structure — including depression within another condition (e.g., patients with vs without depression) and multi-disorder designs where depression is one of the principal groups — or when the study investigates an established depression risk/protective factor (childhood adversity, maltreatment, trauma, stressful life events, perceived or chronic stress, genetic risk) in healthy, at-risk or depressed samples — even if the word "depression" is not used. Answer 0 when the study is about another condition or construct and depression is only one of several secondary symptom scales, exploratory correlates or covariates (even if a correlation with gray matter is reported); when adversity or personality traits are studied within samples defined by another disorder (substance use, psychosis, borderline personality disorder) or as general traits without depression as a main variable; or when "depression" is non-psychiatric.
- `statistics_reported` = 1 only if UNIVARIATE STANDARD inferential statistics are reported for this study's own analyses — e.g., general linear models or similar (t/F/chi-square values, ANOVA/regression p-values, correlations). Machine-learning-based tests do NOT count. If the study's PRIMARY inference is machine-learning-based (prediction/classification), answer 0 even when secondary or exploratory classical tests of model features are reported. Neither do statistics belonging to other studies.
- `vbm` = 1 only if the paper itself performs VBM as an actual morphometric analysis on MRI data it acquired/processed (e.g., group comparisons or associations on VBM-derived gray matter maps). A meta-analysis OF other VBM studies scores 0, and so does merely running VBM-toolbox segmentation (CAT12/SPM) to feed machine-learning classifiers or normative models.
- `living_human_subjects` = 0 as soon as ANY component of the study uses post-mortem / autopsy tissue, even alongside living participants.
- `gray_matter` = 1 when the study reports at least one statistically significant effect involving gray matter structure (volume, density, thickness) — in a primary OR a secondary analysis of its own data. Answer 0 when no gray-matter structural effect is significant, when "gray matter" measures quantify something else (CBF/BOLD in a GM mask, MRS metabolites in a GM voxel, histological measures), or when GM findings come only from other studies.
- `mri_3t` = 1 only if ALL of the study's structural T1 data were acquired at 3T or higher. Mixed samples that include any 1.5T structural data score 0. If the field strength is not stated in the text, answer n/a.
- `mri_resolution_isotropic` = 1 when the structural T1 acquisition has voxels of about 1.5 mm or finer in EVERY dimension (1 x 1 x 1, 1.2 x 1.2 x 1.5, 1 x 1 x 1.5 mm, or a stated 1 mm^3 voxel volume for a 3D T1 sequence all qualify). Any dimension clearly coarser than ~1.5 mm (e.g., 1.2 x 1.2 x 2.5 or 1 x 1 x 3 mm) scores 0. If voxel size is not given directly but field of view, matrix and slice thickness (+ gap) are, derive it. Judge the acquisition, not the resolution images were resampled to. If parameters are only in supplementary material that is not in the text, answer n/a.

## Allowed values per criterion

For each criterion return one of:
- `"1"` — the paper explicitly supports YES (the condition is stated or unambiguously reported).
- `"0"` — the paper explicitly contradicts it (e.g., states it is a review, uses 1.5T only, animal subjects) OR makes it clearly impossible from the described design.
- `"n/a"` — not stated / cannot be determined from the provided text. Default to "n/a" whenever in doubt. Never guess between "1" and "0".

## Criterion definitions

{{CRITERIA_BLOCK}}

## Required JSON schema (no example values — fill from the paper)

Return a JSON object with these keys:
- `candidate_id` (string): MUST exactly match the requested candidate ID. Do NOT modify it.
- `criteria` (object): one entry per criterion id listed above. Each entry is an object:
  - `value`: "1" | "0" | "n/a"
  - `confidence`: number between 0 and 1 (how strongly the text supports your value; use low values when relying on weak or indirect evidence)
  - `evidence`: one short sentence quoting or closely paraphrasing the specific part of the paper that drove the decision, naming where it appears (e.g., "Methods section: ..."). For "n/a", state what information is missing.

## Candidate

Candidate ID: **{{CANDIDATE_ID}}**

Title: {{TITLE}}

Full text:
{{FULL_TEXT}}