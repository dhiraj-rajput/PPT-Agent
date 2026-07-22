"""
app/routes/preview.py
---------------------
Pre-generation Preview Wizard API endpoints.

Provides interactive questionnaire generation, document outline preview,
and customization settings prior to running full document generation.
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user
from utils.db_client import get_collection
from pipeline.ai.client import get_ai_client

router = APIRouter(prefix="/preview", tags=["preview"])


class QuestionOption(BaseModel):
    id: str
    label: str
    description: Optional[str] = None


class WizardQuestion(BaseModel):
    id: str
    question: str
    category: str
    is_multi_select: bool = False
    options: List[QuestionOption]
    recommended_option_id: Optional[str] = None


class OutlineSection(BaseModel):
    key: str
    title: str
    word_budget: int
    included: bool = True
    key_points: List[str] = []


class QuestionResponse(BaseModel):
    question_id: str
    selected_option_ids: List[str]


class CustomAnswersPayload(BaseModel):
    tender_id: Optional[str] = None
    solicitation_number: Optional[str] = None
    proposal_type: str = "Prime RFP Response"  # or Subcontract Response
    answers: List[QuestionResponse] = []
    custom_sections: Optional[List[OutlineSection]] = None
    company_profile: Optional[dict] = None


@router.get("/questions")
async def get_wizard_questions(
    tender_id: Optional[str] = None,
    proposal_type: str = "Prime RFP Response",
    current_user: dict = Depends(get_current_user),
):
    """
    Generate tailored pre-generation questions with multi-choice options based on tender details.
    """
    tender_info = {}
    if tender_id:
        col = get_collection("tenders")
        tender = col.find_one({"$or": [{"noticeId": tender_id}, {"_id": tender_id}]})
        if tender:
            tender_info = tender

    title = tender_info.get("title", "Government Contracting Opportunity")
    naics = tender_info.get("naicsCode", "General")
    
    # Get company profile
    company_col = get_collection("own_company_profile")
    company_profile = company_col.find_one({}) or {}
    company_context = company_profile.get("company_name", "Our Company")
    if company_profile.get("capabilities"):
        company_context += f" - Capabilities: {company_profile.get('capabilities')}"

    default_questions = [
        {
            "id": "strategy_focus",
            "question": f"What should be the primary value proposition focus for '{title[:60]}...'?",
            "category": "Strategic Alignment",
            "is_multi_select": False,
            "recommended_option_id": "opt_cost_tech",
            "options": [
                {"id": "opt_cost_tech", "label": "Best Value (Technical Superiority & Optimized Lifecycle Cost)", "description": "Highlights risk reduction, experienced team, and modern technology stack."},
                {"id": "opt_low_risk", "label": "Lowest Risk & Compliance First", "description": "Emphasizes strict FAR compliance, ISO standards, and zero transition risk."},
                {"id": "opt_innovation", "label": "Innovation & Rapid Execution", "description": "Focuses on automated workflows, modern AI/cloud capabilities, and fast delivery."}
            ]
        },
        {
            "id": "pricing_model",
            "question": "Which pricing structure model should be emphasized in the proposal?",
            "category": "Pricing Strategy",
            "is_multi_select": False,
            "recommended_option_id": "opt_firm_fixed",
            "options": [
                {"id": "opt_firm_fixed", "label": "Firm-Fixed-Price (FFP) with Performance Guarantees", "description": "Predictable budget with milestone-based deliverable billing."},
                {"id": "opt_time_materials", "label": "Time & Materials (T&M) with Ceiling Cap", "description": "Flexible staffing and hourly rates for dynamic requirement scopes."},
                {"id": "opt_value_tiered", "label": "Tiered Volume Discount Model", "description": "Provides cost savings at higher volume tiers for multi-year contracts."}
            ]
        }
    ]

    try:
        client = get_ai_client()
        prompt = f"""
You are an expert proposal manager. Based on the RFP/Tender Title: '{title}' (NAICS: {naics}) 
and the bidding company profile: '{company_context}', generate 3 strategic multiple-choice questions 
to ask the proposal team before generating the document.

Output MUST be a JSON object with a 'questions' array. Each question must have:
- 'id': short string
- 'question': string
- 'category': string
- 'is_multi_select': boolean
- 'recommended_option_id': string
- 'options': array of objects with 'id', 'label', 'description'
"""
        res = client.chat_json([{"role": "user", "content": prompt}])
        questions = res.get("questions", default_questions)
    except Exception as e:
        print(f"Error generating questions via AI: {e}")
        questions = default_questions

    return {
        "tender_id": tender_id,
        "proposal_type": proposal_type,
        "questions": questions
    }


@router.post("/outline")
async def generate_proposal_outline(
    payload: CustomAnswersPayload,
    current_user: dict = Depends(get_current_user),
):
    """
    Generate an editable proposal outline and section structure based on user choices.
    """
    is_subcontract = "subcontract" in payload.proposal_type.lower()

    if is_subcontract:
        default_sections = [
            {
                "key": "executive_summary",
                "title": "1. Executive Summary & Capabilities",
                "word_budget": 500,
                "included": True,
                "key_points": [
                    "Alignment with Prime Integrator goals",
                    "Core technical capabilities & specialized domain knowledge",
                    "SBA Small Business / Subcontracting compliance"
                ]
            },
            {
                "key": "scope_of_work",
                "title": "2. Work Package & Task Responsibilities",
                "word_budget": 750,
                "included": True,
                "key_points": [
                    "Detailed task Breakdown Structure (WBS)",
                    "Interface & collaboration protocol with Prime team",
                    "Deliverables timetable"
                ]
            },
            {
                "key": "pricing_table",
                "title": "3. Subcontract Pricing & Rate Card",
                "word_budget": 300,
                "included": True,
                "key_points": [
                    "Fully-burdened labor rates",
                    "Material & travel cost breakdown",
                    "Volume discount tier options"
                ]
            },
            {
                "key": "past_performance",
                "title": "4. Relevant Past Performance & Case Studies",
                "word_budget": 450,
                "included": True,
                "key_points": [
                    "3 recent relevant contract engagements",
                    "Client contacts & CPARS ratings highlights"
                ]
            }
        ]
    else:
        default_sections = [
            {
                "key": "executive_summary",
                "title": "1. Executive Summary",
                "word_budget": 600,
                "included": True,
                "key_points": [
                    "Understanding of Agency mission & critical objectives",
                    "Summary of proposed solution & key discriminators",
                    "Commitment to schedule & compliance"
                ]
            },
            {
                "key": "technical_approach",
                "title": "2. Technical Approach & Solution Architecture",
                "word_budget": 1200,
                "included": True,
                "key_points": [
                    "Methodology & implementation framework",
                    "Security, quality control & risk mitigation strategy",
                    "Tools, technology stack & standards"
                ]
            }
        ]

    # Try AI generation for outline based on RFP and Company
    tender_info = {}
    if payload.tender_id:
        col = get_collection("tenders")
        tender = col.find_one({"$or": [{"noticeId": payload.tender_id}, {"_id": payload.tender_id}]})
        if tender:
            tender_info = tender

    title = tender_info.get("title", "Government Opportunity")
    
    company_profile = payload.company_profile
    if not company_profile:
        company_col = get_collection("own_company_profile")
        company_profile = company_col.find_one({}) or {}
    company_context = company_profile.get("name") or company_profile.get("company_name", "Our Company")
    
    try:
        client = get_ai_client()
        prompt = f"""
You are an expert proposal writer. Create a tailored document outline for a '{payload.proposal_type}' 
for the RFP titled '{title}', bid by company '{company_context}'.
User answers to strategy questions: {payload.answers}

Output MUST be a JSON object with a 'sections' array. Each section must have:
- 'key': short string
- 'title': string
- 'word_budget': integer
- 'included': true
- 'key_points': array of 2-3 short strings describing what this section will cover.
"""
        res = client.chat_json([{"role": "user", "content": prompt}])
        sections = res.get("sections", default_sections)
    except Exception as e:
        print(f"Error generating outline via AI: {e}")
        sections = default_sections

    total_words = sum(s.get("word_budget", 500) for s in sections if s.get("included", True))
    estimated_pages = max(3, round(total_words / 450, 1))

    return {
        "proposal_type": payload.proposal_type,
        "total_estimated_pages": estimated_pages,
        "total_estimated_words": total_words,
        "sections": default_sections
    }
