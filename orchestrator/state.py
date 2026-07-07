"""
orchestrator/state.py
----------------------
TypedDict definition for the LangGraph agent state.

Every node in the graph reads from and writes into this shared state dict.
LangGraph passes a copy of the state to each node; nodes return only the
keys they want to update.
"""

from typing import Optional, List
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """
    Shared state object passed between all LangGraph nodes.

    Fields are populated progressively as the graph executes.
    Any field can be None if not yet determined or unavailable.
    """

    # --- Input ---
    user_input: str                        # Raw string from the user
    input_type: str                        # Classified: "website_url" | "company_name" | "linkedin_url"

    # --- Discovered URLs ---
    company_name: Optional[str]            # Human-readable company name
    website_url: Optional[str]             # Official company website URL
    linkedin_url: Optional[str]            # LinkedIn company page URL
    company_slug: Optional[str]            # Unified slug used across MongoDB collections

    # --- Agent Outputs ---
    linkedin_data: Optional[dict]          # Serialized LinkedInCompanyData
    website_data: Optional[dict]           # Serialized WebsiteData

    # --- Intermediate Search Outputs ---
    external_news: Optional[List[dict]]                 # Snippets from Google/Tavily external search (news, competitors, etc.)
    external_structured_insights: Optional[dict]        # Structured LLM news profile (insights, value prop, etc.)

    # --- Final Output ---
    combined_profile: Optional[dict]       # Merged profile saved to 'company_profiles' collection

    # --- Errors (non-fatal) ---
    errors: List[str]                      # Accumulated error messages from any node
