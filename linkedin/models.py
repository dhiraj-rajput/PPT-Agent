"""
linkedin/models.py
------------------
Pydantic data models for all LinkedIn company data.

These models serve as the shared data contracts between every layer
of the LinkedIn module and the downstream pipeline stages
(validation → normalization → BI extraction → presentation).

Design principles:
  - All fields are Optional where LinkedIn may not have the data.
  - Lists default to empty list [] to avoid None-checks downstream.
  - Field descriptions serve as self-documentation and LLM prompt hints.
  - The master model (LinkedInCompanyData) is what gets stored in MongoDB
    and passed to the next pipeline stage.
  - BIProfile is the intelligence output consumed by the PPT generator.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-Models — Company Identity
# ---------------------------------------------------------------------------

class CompanyIdentity(BaseModel):
    """Core identifying information about the company."""

    company_name: str = Field(description="The official name of the company as shown on LinkedIn.")
    linkedin_url: str = Field(description="Canonical LinkedIn company page URL.")
    company_slug: str = Field(description="The LinkedIn URL slug, e.g. 'infosys'.")
    website_url: Optional[str] = Field(default=None, description="The company's official website URL.")
    logo_url: Optional[str] = Field(default=None, description="URL to the company's logo image.")
    tagline: Optional[str] = Field(default=None, description="Short tagline or slogan.")
    industry: Optional[str] = Field(default=None, description="Primary industry, e.g. 'IT Services and IT Consulting'.")
    company_type: Optional[str] = Field(default=None, description="e.g. 'Public Company', 'Private Company', 'Non-profit'.")
    company_size_range: Optional[str] = Field(default=None, description="e.g. '10,001+ employees'.")
    headquarters_location: Optional[str] = Field(default=None, description="Primary HQ location.")
    founded_year: Optional[int] = Field(default=None, description="Year the company was founded.")
    specialties: List[str] = Field(default_factory=list, description="Specialties listed on LinkedIn.")
    followers_count: Optional[int] = Field(default=None, description="Total LinkedIn followers.")
    stock_symbol: Optional[str] = Field(default=None, description="Stock ticker symbol if publicly traded, e.g. 'INFY'.")
    stock_exchange: Optional[str] = Field(default=None, description="Exchange name, e.g. 'NYSE', 'NASDAQ', 'BSE'.")


# ---------------------------------------------------------------------------
# Sub-Models — Company Description
# ---------------------------------------------------------------------------

class CompanyDescription(BaseModel):
    """The full company description and About section content."""

    about_text: Optional[str] = Field(default=None, description="Full About section text.")
    mission_statement: Optional[str] = Field(default=None, description="Mission statement if explicitly stated.")
    vision_statement: Optional[str] = Field(default=None, description="Vision statement if explicitly stated.")
    value_proposition: Optional[str] = Field(default=None, description="Core value proposition — what makes this company uniquely valuable.")
    business_model: Optional[str] = Field(default=None, description="How the company makes money, e.g. 'SaaS', 'Professional Services', 'Marketplace'.")
    target_customer_segments: List[str] = Field(default_factory=list, description="Who are the primary customers, e.g. ['Enterprise', 'SMB', 'Government'].")
    geographies_served: List[str] = Field(default_factory=list, description="Countries or regions the company operates in.")


# ---------------------------------------------------------------------------
# Sub-Models — Products and Services
# ---------------------------------------------------------------------------

class ProductOrService(BaseModel):
    """A single product, platform, or service offered by the company."""

    name: str = Field(description="Product or service name.")
    category: Optional[str] = Field(default=None, description="Category, e.g. 'Cloud Platform', 'Analytics Tool', 'Consulting Service'.")
    description: Optional[str] = Field(default=None, description="Brief description of what it does.")
    target_audience: Optional[str] = Field(default=None, description="Who this product/service is built for.")


# ---------------------------------------------------------------------------
# Sub-Models — Technology Profile
# ---------------------------------------------------------------------------

class TechStackProfile(BaseModel):
    """Technology ecosystem and digital maturity indicators."""

    cloud_providers_used: List[str] = Field(default_factory=list, description="e.g. ['AWS', 'Azure', 'Google Cloud'].")
    ai_ml_technologies: List[str] = Field(default_factory=list, description="AI/ML tools and platforms mentioned, e.g. ['TensorFlow', 'OpenAI', 'Vertex AI'].")
    programming_languages: List[str] = Field(default_factory=list, description="Languages mentioned in job postings or about section.")
    frameworks_and_tools: List[str] = Field(default_factory=list, description="Software frameworks and dev tools, e.g. ['React', 'Kubernetes', 'Spark'].")
    security_certifications: List[str] = Field(default_factory=list, description="e.g. ['ISO 27001', 'SOC 2', 'GDPR Compliant'].")
    data_technologies: List[str] = Field(default_factory=list, description="Data/analytics platforms, e.g. ['Snowflake', 'Databricks', 'Tableau'].")
    digital_maturity_level: Optional[str] = Field(default=None, description="Assessment: 'Early', 'Developing', 'Advanced', 'Leader'.")


# ---------------------------------------------------------------------------
# Sub-Models — Leadership Team
# ---------------------------------------------------------------------------

class LeadershipMember(BaseModel):
    """A single member of the company's leadership team."""

    full_name: str = Field(description="Full name of the executive.")
    job_title: str = Field(description="Current title, e.g. 'Chief Executive Officer'.")
    linkedin_profile_url: Optional[str] = Field(default=None, description="LinkedIn profile URL.")
    profile_image_url: Optional[str] = Field(default=None, description="Profile photo URL.")
    tenure_years: Optional[float] = Field(default=None, description="How long they have been in this role (if mentioned).")
    background_summary: Optional[str] = Field(default=None, description="Brief background or previous notable roles.")


# ---------------------------------------------------------------------------
# Sub-Models — Employee Insights
# ---------------------------------------------------------------------------

class EmployeeInsights(BaseModel):
    """Aggregated data about the company's employees on LinkedIn."""

    total_employee_count: Optional[int] = Field(default=None, description="Estimated total employees globally.")
    employees_on_linkedin_count: Optional[int] = Field(default=None, description="Employees with LinkedIn profiles linked to this company.")
    employee_growth_percentage_6_months: Optional[float] = Field(default=None, description="Headcount growth % over 6 months.")
    employee_growth_percentage_1_year: Optional[float] = Field(default=None, description="Headcount growth % over 12 months.")
    top_skills_listed: List[str] = Field(default_factory=list, description="Most common skills among employees.")
    top_universities_attended: List[str] = Field(default_factory=list, description="Universities most attended by employees.")
    distribution_by_function: Dict[str, int] = Field(default_factory=dict, description="Employee count by job function.")
    distribution_by_location: Dict[str, int] = Field(default_factory=dict, description="Employee count by location.")
    hiring_velocity: Optional[str] = Field(default=None, description="Assessment of hiring pace: 'Aggressive', 'Moderate', 'Slow', 'Freeze'.")
    top_hiring_roles: List[str] = Field(default_factory=list, description="Most in-demand job titles currently being hired.")
    top_hiring_locations: List[str] = Field(default_factory=list, description="Locations with the most open positions.")


# ---------------------------------------------------------------------------
# Sub-Models — Recent Company Posts
# ---------------------------------------------------------------------------

class CompanyPost(BaseModel):
    """A single post or update from the company's LinkedIn feed."""

    post_text: Optional[str] = Field(default=None, description="Clean text content of the post.")
    post_url: Optional[str] = Field(default=None, description="Direct URL to the LinkedIn post.")
    posted_date: Optional[str] = Field(default=None, description="When the post was published.")
    reactions_count: Optional[int] = Field(default=None, description="Total reactions count.")
    comments_count: Optional[int] = Field(default=None, description="Total comments count.")
    reshares_count: Optional[int] = Field(default=None, description="Number of reshares.")
    media_urls: List[str] = Field(default_factory=list, description="Attached image/video URLs.")
    post_type: Optional[str] = Field(default=None, description="'text', 'image', 'video', 'article', 'event', 'job'.")
    post_topic: Optional[str] = Field(default=None, description="Inferred topic: 'Product Launch', 'Partnership', 'Award', 'Culture', 'CSR', 'Thought Leadership'.")
    engagement_rate: Optional[float] = Field(default=None, description="Engagement score = (reactions + comments + reshares) / followers.")


# ---------------------------------------------------------------------------
# Sub-Models — Job Postings
# ---------------------------------------------------------------------------

class JobPosting(BaseModel):
    """A single job listing from the company's LinkedIn Jobs page."""

    job_title: str = Field(description="Title of the open position.")
    job_location: Optional[str] = Field(default=None, description="Location of the job.")
    employment_type: Optional[str] = Field(default=None, description="'Full-time', 'Part-time', 'Contract', 'Remote'.")
    experience_level: Optional[str] = Field(default=None, description="'Entry level', 'Mid-Senior level', 'Director', 'Executive'.")
    department: Optional[str] = Field(default=None, description="Department this role belongs to, e.g. 'Engineering', 'Sales', 'Data Science'.")
    posted_date: Optional[str] = Field(default=None, description="When the job was posted.")
    job_listing_url: Optional[str] = Field(default=None, description="Direct URL to the job listing.")
    applicant_count: Optional[str] = Field(default=None, description="e.g. 'Over 200 applicants'.")
    key_skills_required: List[str] = Field(default_factory=list, description="Key skills or technologies mentioned in the job description.")


# ---------------------------------------------------------------------------
# Sub-Models — Office Locations
# ---------------------------------------------------------------------------

class CompanyLocation(BaseModel):
    """A single office or facility location for the company."""

    full_address: Optional[str] = Field(default=None, description="Complete address.")
    city: Optional[str] = Field(default=None, description="City.")
    country: Optional[str] = Field(default=None, description="Country.")
    is_headquarters: bool = Field(default=False, description="True if this is the primary HQ.")
    office_type: Optional[str] = Field(default=None, description="'HQ', 'Regional Office', 'R&D Center', 'Sales Office', 'Development Center'.")


# ---------------------------------------------------------------------------
# Sub-Models — Funding Information
# ---------------------------------------------------------------------------

class FundingInfo(BaseModel):
    """Funding and investment information."""

    total_funding_amount: Optional[str] = Field(default=None, description="Total funding raised, e.g. '$250M'.")
    last_funding_round: Optional[str] = Field(default=None, description="e.g. 'Series B', 'IPO', 'Seed'.")
    last_funding_date: Optional[str] = Field(default=None, description="Date of the most recent funding round.")
    investors: List[str] = Field(default_factory=list, description="Known investors or VC firms.")
    valuation: Optional[str] = Field(default=None, description="Company valuation if disclosed, e.g. '$1.2B'.")
    is_profitable: Optional[bool] = Field(default=None, description="True if the company is known to be profitable.")


# ---------------------------------------------------------------------------
# Sub-Models — Growth Signals
# ---------------------------------------------------------------------------

class GrowthSignal(BaseModel):
    """A single observable indicator of business momentum or growth."""

    signal_type: str = Field(
        description="Type of signal: 'Funding', 'Acquisition', 'Partnership', 'Product Launch', "
                    "'Market Expansion', 'Award', 'Hiring Surge', 'IPO', 'Revenue Milestone', 'New Office'."
    )
    description: str = Field(description="What happened — the specific growth event.")
    date_mentioned: Optional[str] = Field(default=None, description="When this was announced or occurred.")
    source: Optional[str] = Field(default=None, description="Where this signal was found: 'post', 'about', 'job_posting'.")
    significance: Optional[str] = Field(default=None, description="'High', 'Medium', 'Low' — impact on business trajectory.")


# ---------------------------------------------------------------------------
# Sub-Models — Business Challenges & Pain Points
# ---------------------------------------------------------------------------

class BusinessChallenge(BaseModel):
    """An inferred or explicitly stated business challenge the company faces."""

    challenge_area: str = Field(
        description="Area of challenge: 'Talent Acquisition', 'Digital Transformation', "
                    "'Scalability', 'Competition', 'Regulatory Compliance', 'Cost Optimization', "
                    "'AI Adoption', 'Security', 'Customer Retention', 'Market Expansion'."
    )
    description: str = Field(description="What the challenge is and why it matters to this company.")
    evidence: Optional[str] = Field(default=None, description="What from the scraped data suggests this challenge exists.")
    opportunity_for_us: Optional[str] = Field(default=None, description="How our solution can address this challenge (for sales use).")


# ---------------------------------------------------------------------------
# Sub-Models — Competitor Analysis
# ---------------------------------------------------------------------------

class CompetitorMention(BaseModel):
    """A competitor identified from LinkedIn content or inferred from context."""

    competitor_name: str = Field(description="Name of the competitor.")
    relationship_type: Optional[str] = Field(default=None, description="'Direct Competitor', 'Indirect Competitor', 'Adjacent Player'.")
    source: Optional[str] = Field(default=None, description="Where this competitor was identified: 'post', 'about', 'inferred'.")


# ---------------------------------------------------------------------------
# Sub-Models — Strategic Initiatives
# ---------------------------------------------------------------------------

class StrategicInitiative(BaseModel):
    """A major strategic focus area or initiative the company is pursuing."""

    initiative_name: str = Field(description="Short name for the initiative, e.g. 'AI Transformation', 'Global Expansion'.")
    description: str = Field(description="What the company is doing and why.")
    evidence: Optional[str] = Field(default=None, description="What from the scraped data indicates this initiative.")
    timeline: Optional[str] = Field(default=None, description="When this was announced or expected to complete.")
    priority_level: Optional[str] = Field(default=None, description="'Critical', 'High', 'Medium'.")


# ---------------------------------------------------------------------------
# Sub-Models — BI Intelligence Profile (the key output for PPT generation)
# ---------------------------------------------------------------------------

class BIProfile(BaseModel):
    """
    Business Intelligence profile derived from all scraped LinkedIn data.

    This is the highest-value output of the LinkedIn module —
    the intelligence layer that transforms raw company data into
    actionable insights for presentations, sales, and BI.

    This model feeds directly into the PPT planning stage.
    """

    # ---- Competitive Positioning -------------------------------------------
    key_differentiators: List[str] = Field(
        default_factory=list,
        description="What makes this company unique vs competitors. Max 5 points."
    )
    competitive_advantages: List[str] = Field(
        default_factory=list,
        description="Sustainable advantages: brand, IP, network effects, cost, etc."
    )
    identified_competitors: List[CompetitorMention] = Field(
        default_factory=list,
        description="Key competitors identified from the data."
    )

    # ---- Strategic Direction -----------------------------------------------
    strategic_initiatives: List[StrategicInitiative] = Field(
        default_factory=list,
        description="Major strategic bets the company is making."
    )
    growth_signals: List[GrowthSignal] = Field(
        default_factory=list,
        description="Observable indicators of business momentum."
    )

    # ---- Challenges & Opportunities ----------------------------------------
    business_challenges: List[BusinessChallenge] = Field(
        default_factory=list,
        description="Key challenges this company faces."
    )
    digital_transformation_status: Optional[str] = Field(
        default=None,
        description="Assessment: 'Not Started', 'Early Stage', 'In Progress', 'Advanced', 'Complete'."
    )
    ai_adoption_level: Optional[str] = Field(
        default=None,
        description="Assessment of AI/ML adoption: 'None', 'Exploring', 'Pilot', 'Scaled', 'AI-Native'."
    )

    # ---- Products & Technology ---------------------------------------------
    products_and_services: List[ProductOrService] = Field(
        default_factory=list,
        description="Key products and services offered."
    )
    tech_stack: Optional[TechStackProfile] = Field(
        default=None,
        description="Technology ecosystem and tools used."
    )

    # ---- Summary Insights --------------------------------------------------
    company_maturity_stage: Optional[str] = Field(
        default=None,
        description="'Startup', 'Growth Stage', 'Scale-up', 'Mature Enterprise', 'Declining'."
    )
    executive_summary: Optional[str] = Field(
        default=None,
        description="2-3 sentence summary of the company from a business analyst perspective. "
                    "Should convey what they do, who they serve, and their current trajectory."
    )
    sales_talking_points: List[str] = Field(
        default_factory=list,
        description="3-5 personalized talking points for a sales or partnership conversation."
    )
    recommended_approach: Optional[str] = Field(
        default=None,
        description="How to position our outreach to this company based on their context."
    )


# ---------------------------------------------------------------------------
# Master Model — Complete LinkedIn Company Data
# ---------------------------------------------------------------------------

class LinkedInCompanyData(BaseModel):
    """
    The master data object representing everything collected about a company
    from LinkedIn. Stored in 'structured_linkedin' MongoDB collection.
    Passed to the downstream pipeline (validation → normalization → BI → PPT).
    """

    # ---- Identifiers -------------------------------------------------------
    company_slug: str = Field(description="LinkedIn URL slug — unique identifier.")

    # ---- Raw Structured Data -----------------------------------------------
    identity: Optional[CompanyIdentity] = Field(default=None)
    description: Optional[CompanyDescription] = Field(default=None)
    leadership_team: List[LeadershipMember] = Field(default_factory=list)
    employee_insights: Optional[EmployeeInsights] = Field(default=None)
    recent_posts: List[CompanyPost] = Field(default_factory=list)
    job_postings: List[JobPosting] = Field(default_factory=list)
    office_locations: List[CompanyLocation] = Field(default_factory=list)
    funding_info: Optional[FundingInfo] = Field(default=None)
    affiliated_companies: List[str] = Field(default_factory=list)
    showcase_pages: List[str] = Field(default_factory=list)

    # ---- BI Intelligence Output --------------------------------------------
    bi_profile: Optional[BIProfile] = Field(
        default=None,
        description="High-level business intelligence extracted for PPT generation."
    )

    # ---- Metadata & Quality ------------------------------------------------
    scraped_at: datetime = Field(description="UTC timestamp of scraping.")
    scrape_layers_used: List[str] = Field(default_factory=list)
    source_urls_scraped: List[str] = Field(default_factory=list)
    field_confidence_scores: Dict[str, float] = Field(default_factory=dict)
    raw_data_document_id: Optional[str] = Field(default=None)
    data_quality_score: Optional[float] = Field(
        default=None,
        description="Overall data quality score 0.0-1.0 assigned by the data cleaner."
    )

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}


# ---------------------------------------------------------------------------
# Intermediate Model — Raw Scrape Document
# ---------------------------------------------------------------------------

class RawLinkedInScrapedData(BaseModel):
    """Raw, unstructured data from a single scraping layer. Stored in 'raw_linkedin'."""

    company_slug: str
    scrape_layer: str
    page_url: str
    raw_html: Optional[str] = Field(default=None, description="Raw HTML (first 50KB).")
    raw_text: Optional[str] = Field(default=None, description="Extracted plain text.")
    json_ld_data: Optional[Dict] = Field(default=None, description="JSON-LD structured data.")
    meta_tags: Optional[Dict[str, str]] = Field(default=None, description="Meta tag key-value pairs.")
    scraped_at: datetime
    scrape_success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None)
