"""
bidforge/
---------
Python port of the BidForge pipeline (originally TypeScript / OpenRouter),
rebuilt to run natively inside PPT-Agent:

  Parse -> Explore (inventory + competitor intel, in parallel) -> Summarise -> Generate

Differences from the original BidForge:
  - Runs on Ollama Cloud (ai/client.py) instead of OpenRouter, governed by the
    same global AI_MODE toggle as the rest of the project (BIDFORGE_MODE override).
  - No RabbitMQ / email ingestion — RFPs are uploaded manually (see
    api/routes/bidforge.py).
  - "Inventory" and "competitor" data are no longer manually-uploaded files —
    inventory is our own company profile (private/orbit_avanya_detailed_profiles.json,
    the same source respond_to_rfp.py already uses), and competitor/market
    intelligence is gathered live using PPT-Agent's existing website / linkedin /
    google_search agents instead of requiring pre-uploaded competitor files.
  - Supports an optional uploaded .docx template: if provided, the final
    document is generated INTO that template (headings preserved, header/footer
    preserved, no page-count cap) instead of the default OrbitAvanya template.
"""
