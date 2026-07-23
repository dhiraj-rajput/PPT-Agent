"""
orchestrator/state.py
----------------------
TypedDict definition for the LangGraph agent state.

Every node in the graph reads from and writes into this shared state dict.
LangGraph passes a copy of the state to each node; nodes return only the
keys they want to update.
"""

from typing import Optional, List, Annotated
from typing_extensions import TypedDict


def merge_optional_str(left: Optional[str], right: Optional[str]) -> Optional[str]:
    """
    Reducer that deterministically merges optional string fields across parallel graph nodes.
    Prefers non-empty strings over None/empty strings, and longer/richer values if both are non-empty.
    """
    l_str = (left or "").strip()
    r_str = (right or "").strip()

    if not l_str:
        return right if right is not None else left
    if not r_str:
        return left

    # If both are non-empty, prefer non-generic strings
    generic_placeholders = {"n/a", "none", "unknown", "null"}
    if r_str.lower() in generic_placeholders and l_str.lower() not in generic_placeholders:
        return left
    if l_str.lower() in generic_placeholders and r_str.lower() not in generic_placeholders:
        return right

    return right if len(r_str) > len(l_str) else left


def merge_errors(left: List[str], right: List[str]) -> List[str]:
    """Reducer that combines concurrent errors."""
    return (left or []) + (right or [])


class AgentState(TypedDict):
    """
    Shared state object passed between all LangGraph nodes.

    Fields are populated progressively as the graph executes.
    Any field can be None if not yet determined or unavailable.
    """

    # --- Input ---
    user_input: str                        # Raw string from the user
    input_type: str                        # Classified: "website_url" | "company_name" | "linkedin_url"

    # --- Options ---
    force: Optional[bool]                  # Force re-scrape even if cached

    # --- Discovered URLs (Annotated with reducers for concurrent safety) ---
    company_name: Annotated[Optional[str], merge_optional_str]            # Human-readable company name
    website_url: Annotated[Optional[str], merge_optional_str]             # Official company website URL
    linkedin_url: Annotated[Optional[str], merge_optional_str]            # LinkedIn company page URL
    company_slug: Annotated[Optional[str], merge_optional_str]            # Unified slug used across MongoDB collections

    # --- Agent Outputs ---
    linkedin_data: Optional[dict]          # Serialized LinkedInCompanyData
    website_data: Optional[dict]           # Serialized WebsiteData

    # --- Intermediate Search Outputs ---
    external_news: Optional[List[dict]]               # Snippets from Google/Tavily external search
    external_structured_insights: Optional[dict]      # LLM-structured BI profile (insights, value prop, competitors, etc.)

    # --- Merged Profile (raw, pre-compaction) ---
    combined_profile: Optional[dict]       # Merged profile saved to 'company_profiles' collection

    # --- Final Compacted Profile (post-compaction) ---
    optimized_profile: Optional[dict]      # OptimizedCompanyProfile — output of run_compactor node

    # --- Teaming Proposal & PDF Outreach Path ---
    solicitation_number: Optional[str]     # Target solicitation number to compile teaming proposal for
    pdf_proposal_path: Optional[str]       # Path to the generated B2B teaming proposal PDF

    # --- RFP Response Generator (respond_to_rfp pipeline) ---
    rfp_response_mode: Optional[str]       # "prime" | "subcontract" — which response mode to use
    rfp_response_pdf_path: Optional[str]   # Path to the DOCX-styled RFP response PDF

    # --- Errors (Annotated with reducer for concurrent safety) ---
    errors: Annotated[List[str], merge_errors]                      # Accumulated error messages from any node

