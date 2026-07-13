"""ReFiNe schema definitions for paper records and extraction."""

from typing import Literal

from pydantic import BaseModel, Field

# Broad dataset feature keys as specified in the task
FEATURE_KEYS = [
    "t1w_mri",
    "vbm_or_voxelwise_morphometry",
    "mdd_patients",
    "healthy_controls",
    "genetic_data",
    "depression_scale",
    "anxiety_scale",
    "clinical_outcomes",
    "longitudinal_data",
    "medication_status",
    "trauma_or_life_stress",
    "cognitive_data",
    "blood_or_biomarker_data",
]

# Aliases for backward compatibility with existing papers.json
# The existing data uses keys like "longitudinal_followup", "treatment_or_antidepressant_data", etc.
# We support both the new canonical keys and legacy keys.
LEGACY_FEATURE_KEYS = [
    "t1w_mri",
    "vbm_or_voxelwise_morphometry",
    "mdd_patients",
    "healthy_controls",
    "other_clinical_population",
    "genetic_data",
    "depression_scale",
    "anxiety_scale",
    "trauma_or_life_stress",
    "medication_status",
    "treatment_or_antidepressant_data",
    "clinical_outcomes",
    "longitudinal_followup",
    "cognitive_data",
    "blood_or_biomarker_data",
    "multi_site_data",
]

# Canonical mapping: legacy key -> new key
LEGACY_TO_CANONICAL = {
    "longitudinal_followup": "longitudinal_data",
    "treatment_or_antidepressant_data": "medication_status",
    "other_clinical_population": "healthy_controls",
    "multi_site_data": "vbm_or_voxelwise_morphometry",
}

Flag = Literal["yes", "no", "unclear", "not_applicable"]


class WebsiteCard(BaseModel):
    """Fields displayed on the paper card in the website."""

    short_description: str | None = None
    dataset_features_summary: list[str] = Field(default_factory=list)
    plain_text_summary: str | None = None


class ExtractionInfo(BaseModel):
    """Extraction metadata."""

    status: str = "seeded_from_spreadsheet"
    source: str | None = None
    notes: str | None = None


class PaperRecord(BaseModel):
    """A single paper record in papers.json."""

    paper_id: str
    title: str | None = None
    year: str | None = None
    doi: str | None = None
    doi_url: str | None = None
    citation: str
    dataset_features_needed: dict[str, Flag] = Field(default_factory=dict)
    sample_summary: dict | None = None
    website_card: WebsiteCard = Field(default_factory=WebsiteCard)
    extraction: ExtractionInfo = Field(default_factory=ExtractionInfo)

    @classmethod
    def from_csv_row(cls, row: dict) -> "PaperRecord":
        """Create a PaperRecord from a CSV row (legacy build path)."""
        title = row.get("title") or row.get("paper_id")
        return cls(
            paper_id=row["paper_id"],
            title=row.get("title") or None,
            year=row.get("year") or None,
            doi=row.get("doi") or None,
            doi_url=row.get("doi_url") or None,
            citation=row["paper"],
            dataset_features_needed={key: "unclear" for key in LEGACY_FEATURE_KEYS},
            website_card=WebsiteCard(
                short_description=(title[:90] if title else row["paper_id"]),
                dataset_features_summary=[],
            ),
            extraction=ExtractionInfo(
                status="seeded_from_spreadsheet",
                source="eligible_studies.csv",
                notes="Broad dataset features not extracted yet.",
            ),
        )


# ---------------------------------------------------------------------------
# Extraction-specific models (used by the LLM pipeline)
# ---------------------------------------------------------------------------

class ExtractedFeatures(BaseModel):
    """The JSON structure returned by the LLM / fallback."""

    paper_id: str
    dataset_features_needed: dict[str, Flag] = Field(default_factory=dict)
    website_card: dict = Field(default_factory=dict)
    extraction_status: str = "unclear"
    extraction_notes: str | None = None

    def to_extraction_info(self) -> ExtractionInfo:
        """Convert extraction_status fields into the ExtractionInfo model."""
        status_map = {
            "completed": "completed",
            "failed": "failed",
            "missing_pdf": "missing_pdf",
        }
        return ExtractionInfo(
            status=status_map.get(self.extraction_status, self.extraction_status),
            source="pdf_extraction" if self.extraction_status == "completed" else None,
            notes=self.extraction_notes,
        )

    def to_website_card(self) -> WebsiteCard:
        """Convert the website_card dict into a WebsiteCard model."""
        wc = self.website_card
        return WebsiteCard(
            short_description=wc.get("short_description") or wc.get("short_title"),
            dataset_features_summary=wc.get("dataset_features_summary")
            or wc.get("dataset_features_summary", []),
            plain_text_summary=wc.get("plain_text_summary"),
        )
