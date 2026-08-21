"""
orchestrator/__init__.py
-------------------------
Public API for the LangGraph orchestration pipeline.

Usage:
    from pipeline.orchestrator import run_pipeline

    result = run_pipeline("https://infosys.com")
    result = run_pipeline("Infosys Limited")
    result = run_pipeline("https://linkedin.com/company/infosys")
"""

from pipeline.orchestrator.graph import build_graph, run_pipeline

__all__ = ["build_graph", "run_pipeline"]
