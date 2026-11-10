You are screening a research paper for eligibility in the ReFiNe replication-data project (depression-related variables and gray matter brain structure, measured with MRI). You will see ONLY the paper's title and abstract (plus journal/year metadata) — you do NOT have access to the full text. Your job is to score each gate criterion below EXACTLY as a careful human screener would from this limited information. Papers that definitely fail a gate are dropped here so their full texts need not be retrieved; everything else passes to a later, deeper screen on the full text.

## Rules

- Use ONLY information stated in the provided title and abstract.
- **Absence is informative.** Most abstracts state the study's aims, sample, measures and imaging. If such an abstract describes the study and a gate's condition is simply not part of it (e.g., no depression variable among the aims and measures, or the imaging is only PET/fMRI/DTI), answer "0", not "n/a".
- Use "n/a" only when the abstract is too short, vague or incomplete to tell. An "n/a" never excludes; only an explicit "0" on a gate drops the paper at this stage.
- Return valid JSON only. NO markdown formatting, NO code fences, NO explanations outside the JSON, NO comments.
- The `candidate_id` field MUST exactly match the requested candidate ID: {{CANDIDATE_ID}}

## Scoring principles (read carefully)

- You are filtering out papers that CANNOT be eligible regardless of what their full text says — e.g., a review or meta-analysis, an animal-only study, a study whose research question is not about depression or depression risk, or a study with no structural MRI gray-matter measure.
- Details that abstracts routinely omit (field strength, voxel size, which statistics were run, whether VBM specifically was used) are NOT judged at this stage.
- `primary_research` = 0 for systematic reviews, meta-analyses, narrative reviews, commentaries, editorials and similar non-primary articles; 1 for original empirical reports.
- `human_subjects` = 0 only when the abstract makes clear there are no human participants (e.g., animal models, cell lines, purely computational/simulation work).
- `depression_related` asks whether depression is part of the study's MAIN research question. Score 1 when (a) depression — diagnosis, depressive symptoms, mood states / low mood / negative affect, subtypes or course of illness — is a primary focus or a main group/outcome (including patients with vs without depression within another condition, and multi-disorder designs where depression is one of the principal groups), or (b) the study investigates an established depression risk/protective factor such as childhood adversity, maltreatment, trauma, stressful life events, perceived or chronic stress, or genetic risk in healthy, at-risk or depressed samples. **These count even if the abstract never uses the word "depression"** — e.g., a study of perceived stress and gray matter in healthy adults, or of daily mood and gray matter, scores 1. Score 0 when:
  - no depression-related variable (as defined above) is part of the described aims and measures;
  - the study is about ANOTHER condition or construct and depression appears only as a covariate, an exclusion criterion or a sample descriptor, with no finding relating depression to brain structure (a link only to brain function or connectivity does not count);
  - adversity or personality traits are studied within samples defined by another disorder (substance use, psychosis, borderline personality disorder) or as general traits (neuroticism, optimism, impulsivity, greed) without depression as a main variable;
  - "depression" is non-psychiatric (e.g., cortical spreading depression).
  **Exception — keep for full-text review:** if the abstract reports a finding that relates depressive symptoms (e.g., HADS, BDI, HAMD scores) or a depressive subtype to brain structure, score 1 even when the study is mainly about another condition (e.g., Parkinson's disease, multiple sclerosis, pain syndromes, eye disease). Whether such papers are eligible is decided on the full text.
- `structural_mri` = 1 when gray matter brain structure is measured from structural MRI (gray matter volume/density/thickness, VBM, regional brain volumes). Score 0 only when the abstract makes clear that no such measure is used — e.g., the imaging is only functional MRI, diffusion MRI/DTI, MR spectroscopy, PET, EEG/MEG or CT, the study is post-mortem histology, or there is no brain imaging at all. Score n/a when MRI is mentioned but the kind of measure is unclear.

## Allowed values per gate criterion

For each criterion return one of:
- `"1"` — the title/abstract explicitly supports YES.
- `"0"` — the title/abstract explicitly contradicts it OR makes it clearly impossible from the described design.
- `"n/a"` — not stated / cannot be determined from the provided text. Default to "n/a" whenever in doubt. Never guess between "1" and "0".

## Gate criterion definitions

{{CRITERIA_BLOCK}}

## Required JSON schema (no example values — fill from the title/abstract)

Return a JSON object with these keys:
- `candidate_id` (string): MUST exactly match the requested candidate ID. Do NOT modify it.
- `criteria` (object): one entry per criterion id listed above. Each entry is an object:
  - `value`: "1" | "0" | "n/a"
  - `confidence`: number between 0 and 1 (how strongly the title/abstract supports your value)
  - `evidence`: one short sentence (max ~25 words) quoting or closely paraphrasing the part of the title or abstract that drove the decision. For "n/a", state what information is missing.

## Candidate

Candidate ID: **{{CANDIDATE_ID}}**

Title: {{TITLE}}

Journal / Year: {{JOURNAL_YEAR}}

Abstract:
{{ABSTRACT}}