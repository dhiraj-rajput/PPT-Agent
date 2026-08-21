"""
documents/schemas.py
--------------------
Pydantic schemas for typed LLM responses across the entire pipeline.
"""

from typing import Any

from pydantic import BaseModel, Field


class ParsedRFP(BaseModel):
    parsed_content: str = Field(description="Full structured analysis of requirements, grouped by category")
    missing_fields: list[str] = Field(default_factory=list, description="Specific gaps identified in the RFP")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Metadata like buyer name, deadline, agency, etc.")
    requirements: list[dict[str, Any]] = Field(default_factory=list, description="List of extracted requirement objects")
    compliance_requirements: list[str] = Field(default_factory=list, description="Mandatory certifications or compliance items")
    summary: str = Field(default="", description="2-4 sentence plain-English summary of what is being solicited")

class InventoryItem(BaseModel):
    name: str = Field(description="Requirement name from RFP")
    present: str = Field(description="YES, PARTIAL, or NO availability in catalog")
    our_price: str = Field(default="Not listed", description="Exact price or pricing model from catalog")
    availability: str = Field(default="Not listed", description="Capacity or stock status")
    features_matched: list[str] = Field(default_factory=list, description="Matched features")
    features_missing: list[str] = Field(default_factory=list, description="Missing features")
    notes: str = Field(default="", description="Detailed match notes")

class InventoryAnalysis(BaseModel):
    items: list[InventoryItem] = Field(default_factory=list)
    overall_summary: str | None = Field(default=None)

class CompetitorEntry(BaseModel):
    name: str = Field(description="Competitor company name")
    price: str = Field(default="Not listed", description="Observed price")
    notes: str = Field(default="", description="Key notes or differentiators")

class CompetitorItem(BaseModel):
    item_name: str = Field(description="Requirement or product name")
    competitors: list[CompetitorEntry] = Field(default_factory=list)
    avg_price: str | None = Field(default=None)
    market_summary: str | None = Field(default=None)

class CompetitorIntel(BaseModel):
    items: list[CompetitorItem] = Field(default_factory=list)

class SummariserItem(BaseModel):
    name: str = Field(description="Product or service name")
    current_price: str = Field(description="Our current list price")
    options: list[str] = Field(description="2-3 strategic pricing options")
    avg_competitor_price: str | None = Field(default=None)
    recommended_option_index: int = Field(default=0, description="0-based index of recommended option")
    data: str = Field(description="Comprehensive Markdown summary for this item")

class SummariserResponse(BaseModel):
    items: list[SummariserItem] = Field(default_factory=list)
    strategic_notes: str | None = Field(default=None)
