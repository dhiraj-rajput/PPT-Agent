"""
orchestrator/graph.py
----------------------
LangGraph state machine that routes user input through the correct
agent pipeline and merges the results.

Flow by input type:

  website_url  → discover_from_website → run_website_agent + run_linkedin_agent → merge_results
  company_name → discover_website      → discover_linkedin  → run_website_agent + run_linkedin_agent → merge_results
  linkedin_url → discover_website      → run_linkedin_agent + run_website_agent → merge_results

Usage:
    from orchestrator.graph import build_graph, run_pipeline
    result = run_pipeline("https://infosys.com")
    result = run_pipeline("Infosys Limited")
    result = run_pipeline("https://linkedin.com/company/infosys")
"""

from langgraph.graph import StateGraph, END

from orchestrator.state import AgentState
from orchestrator.nodes import (
    classify_input,
    discover_website,
    discover_linkedin,
    discover_from_website,
    run_website_agent,
    run_linkedin_agent,
    merge_results,
)
from utils.helpers import setup_logger

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Routing Logic
# ---------------------------------------------------------------------------

def _route_after_classify(state: AgentState) -> str:
    """
    After classification, decide the next node.

    - "both_urls"     → run_website_agent     (directly scrap website & linkedin)
    - "website_url"   → discover_from_website (find LinkedIn from the given website)
    - "company_name"  → discover_website      (find the official website first)
    - "linkedin_url"  → run_linkedin_agent    (already have LinkedIn — go straight to scraping)
    """
    input_type = state.get("input_type", "company_name")
    logger.info(f"[router] input_type='{input_type}'")

    if input_type == "both_urls":
        return "run_website_agent"
    elif input_type == "website_url":
        return "discover_from_website"
    elif input_type == "linkedin_url":
        return "run_linkedin_agent"
    else:
        return "discover_website"


def _route_after_website_discovery(state: AgentState) -> str:
    """
    After finding the official website, always try to find LinkedIn too.
    """
    return "discover_linkedin"


def _route_after_linkedin_discovery(state: AgentState) -> str:
    """
    After finding LinkedIn URL, run the website agent next.
    (LinkedIn agent runs in parallel as a separate path — see graph construction)
    """
    return "run_website_agent"


def _route_after_website_agent(state: AgentState) -> str:
    """
    After website agent completes, run the LinkedIn agent.
    """
    return "run_linkedin_agent"


def _route_after_linkedin_agent(state: AgentState) -> str:
    """
    After LinkedIn agent completes, merge all results.
    """
    return "merge_results"


def _route_after_discover_from_website(state: AgentState) -> str:
    """
    For website_url inputs: run both agents (website first, then LinkedIn).
    """
    return "run_website_agent"


# ---------------------------------------------------------------------------
# Graph Construction
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """
    Build and compile the LangGraph state machine.

    Returns:
        A compiled LangGraph app ready for invocation.
    """
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("classify_input", classify_input)
    graph.add_node("discover_website", discover_website)
    graph.add_node("discover_linkedin", discover_linkedin)
    graph.add_node("discover_from_website", discover_from_website)
    graph.add_node("run_website_agent", run_website_agent)
    graph.add_node("run_linkedin_agent", run_linkedin_agent)
    graph.add_node("merge_results", merge_results)

    # Entry point
    graph.set_entry_point("classify_input")

    # Conditional routing after classification
    graph.add_conditional_edges(
        "classify_input",
        _route_after_classify,
        {
            "discover_from_website": "discover_from_website",
            "discover_website": "discover_website",
            "run_linkedin_agent": "run_linkedin_agent",
            "run_website_agent": "run_website_agent",
        },
    )

    # company_name path: discover_website → discover_linkedin → run_website_agent → run_linkedin_agent → merge
    graph.add_edge("discover_website", "discover_linkedin")
    graph.add_edge("discover_linkedin", "run_website_agent")
    graph.add_edge("run_website_agent", "run_linkedin_agent")
    graph.add_edge("run_linkedin_agent", "merge_results")

    # website_url path: discover_from_website → run_website_agent → run_linkedin_agent → merge
    graph.add_edge("discover_from_website", "run_website_agent")

    # merge → END
    graph.add_edge("merge_results", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Public runner
# ---------------------------------------------------------------------------

# Module-level compiled graph (singleton)
_app = None


def _get_app():
    global _app
    if _app is None:
        _app = build_graph()
    return _app


def run_pipeline(user_input: str) -> dict:
    """
    Run the full agent pipeline for any user input.

    Args:
        user_input: Company name, official website URL, or LinkedIn URL.

    Returns:
        The final AgentState dict with combined_profile, linkedin_data,
        website_data, and any errors.

    Example:
        result = run_pipeline("https://infosys.com")
        print(result["combined_profile"]["company_name"])
        print(result["combined_profile"]["linkedin_url"])
    """
    app = _get_app()

    initial_state: AgentState = {
        "user_input": user_input,
        "input_type": "",
        "company_name": None,
        "website_url": None,
        "linkedin_url": None,
        "company_slug": None,
        "linkedin_data": None,
        "website_data": None,
        "combined_profile": None,
        "errors": [],
    }

    logger.info(f"=== Pipeline started === input='{user_input}'")
    final_state = app.invoke(initial_state)
    logger.info(f"=== Pipeline complete === slug='{final_state.get('company_slug')}'")

    return final_state
