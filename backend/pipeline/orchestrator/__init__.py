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

from pipeline.orchestrator.graph import run_pipeline, build_graph

__all__ = ["run_pipeline", "build_graph"]
