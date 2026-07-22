"""
documents/unified_generator.py
------------------------------
Unified entry point for proposal generation supporting 4 modes:
  1. prime        - Direct response to RFP as Prime Contractor
  2. subcontract  - Teaming/subcontracting proposal to a Prime Winner
  3. partnership  - B2B Partnership/Joint Venture proposal
  4. bidforge     - Uploaded RFP document response generation (BidForge pipeline)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from pipeline.ai.client import get_ai_client
from documents.prompts import (
    RFP_PARSER_PROMPT,
    INVENTORY_STATS_PROMPT,
    COMPETITOR_PRICING_PROMPT,
    SUMMARISER_PROMPT,
    FINAL_DOCUMENT_PROMPT,
    PRIME_PROPOSAL_PROMPT,
    SUBCONTRACT_PROPOSAL_PROMPT,
    PARTNERSHIP_PROPOSAL_PROMPT
)
from documents.markdown_renderer import render_markdown_to_pdf
from utils.helpers import setup_logger

logger = setup_logger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

class ProposalGenerator:
    """Unified Orchestrator for all proposal generation workflows."""

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else PROJECT_ROOT
        self.ai_client = get_ai_client()

    def generate(self, mode: str, rfp_data: Dict[str, Any], output_path: str, **kwargs) -> str:
        """Main entry point to execute the appropriate generation mode."""
        logger.info(f"[ProposalGenerator] Generating proposal in mode '{mode}' -> {output_path}")

        if mode == "prime":
            markdown = self._generate_prime(rfp_data, **kwargs)
        elif mode == "subcontract":
            markdown = self._generate_subcontract(rfp_data, **kwargs)
        elif mode == "partnership":
            markdown = self._generate_partnership(rfp_data, **kwargs)
        elif mode == "bidforge":
            markdown = self._generate_bidforge(rfp_data, **kwargs)
        else:
            raise ValueError(f"Unsupported proposal mode: {mode}")

        # Render generated markdown to PDF using optional template branding
        template_path = kwargs.get("template_path")
        pdf_path = render_markdown_to_pdf(markdown, output_path, template_path=template_path)
        return pdf_path

    def _generate_prime(self, rfp_data: Dict[str, Any], **kwargs) -> str:
        """Generates Prime proposal via LLM."""
        company_profile = self._load_company_profile()
        user_content = f"OUR COMPANY PROFILE:\n{json.dumps(company_profile, indent=2)}\n\nSOLICITATION / RFP DATA:\n{json.dumps(rfp_data, indent=2)}"

        messages = [
            {"role": "system", "content": PRIME_PROPOSAL_PROMPT},
            {"role": "user", "content": user_content}
        ]
        return self.ai_client.chat_text(messages)

    def _generate_subcontract(self, rfp_data: Dict[str, Any], **kwargs) -> str:
        """Generates Subcontract Teaming proposal via LLM."""
        winner_name = kwargs.get("winner_name", "Prime Contractor")
        workshare = kwargs.get("workshare", 15.0)
        winner_profile = kwargs.get("winner_profile", {})
        company_profile = self._load_company_profile()

        user_content = (
            f"PROPOSED WORKSHARE: {workshare}%\n"
            f"PRIME CONTRACTOR NAME: {winner_name}\n"
            f"PRIME PROFILE:\n{json.dumps(winner_profile, indent=2)}\n\n"
            f"OUR COMPANY PROFILE:\n{json.dumps(company_profile, indent=2)}\n\n"
            f"SOLICITATION / RFP DATA:\n{json.dumps(rfp_data, indent=2)}"
        )

        messages = [
            {"role": "system", "content": SUBCONTRACT_PROPOSAL_PROMPT},
            {"role": "user", "content": user_content}
        ]
        return self.ai_client.chat_text(messages)

    def _generate_partnership(self, rfp_data: Dict[str, Any], **kwargs) -> str:
        """Generates B2B Partnership proposal via LLM."""
        partner_profile = kwargs.get("partner_profile", {})
        company_profile = self._load_company_profile()

        user_content = (
            f"PARTNER COMPANY PROFILE:\n{json.dumps(partner_profile, indent=2)}\n\n"
            f"OUR COMPANY PROFILE:\n{json.dumps(company_profile, indent=2)}"
        )

        messages = [
            {"role": "system", "content": PARTNERSHIP_PROPOSAL_PROMPT},
            {"role": "user", "content": user_content}
        ]
        return self.ai_client.chat_text(messages)

    def _generate_bidforge(self, rfp_data: Dict[str, Any], **kwargs) -> str:
        """Executes full BidForge pipeline on uploaded RFP data."""
        inventory = kwargs.get("inventory", {})
        competitor_intel = kwargs.get("competitor_intel", {})
        strategy = kwargs.get("strategy", {})

        user_content = (
            f"PARSED RFP REQUIREMENTS:\n{json.dumps(rfp_data, indent=2)}\n\n"
            f"EXPLORE OUTPUT (INVENTORY & COMPETITOR DATA):\nInventory:\n{json.dumps(inventory, indent=2)}\nCompetitor Intel:\n{json.dumps(competitor_intel, indent=2)}\n\n"
            f"SUMMARISE OUTPUT (PRICING STRATEGY):\n{json.dumps(strategy, indent=2)}"
        )

        messages = [
            {"role": "system", "content": FINAL_DOCUMENT_PROMPT},
            {"role": "user", "content": user_content}
        ]
        return self.ai_client.chat_text(messages)

    def _load_company_profile(self) -> Dict[str, Any]:
        """Loads Orbit Avanya's profile data from private/orbit_avanya_detailed_profiles.json."""
        profile_path = self.project_root / "private" / "orbit_avanya_detailed_profiles.json"
        if profile_path.exists():
            try:
                return json.loads(profile_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load company profile from {profile_path}: {e}")

        # Fallback profile
        return {
            "company_name": "OrbitAvanya Tech LLP",
            "product_name": "AvanyaEdge AI Platform",
            "about_text": "OrbitAvanya delivers enterprise AI, custom cloud solutions, and full-stack software development.",
            "key_features": ["Enterprise Systems", "AI/ML Integration", "Cloud Infrastructure", "Cybersecurity Compliance"]
        }
