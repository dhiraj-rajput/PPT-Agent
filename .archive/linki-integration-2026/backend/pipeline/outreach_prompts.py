"""
pipeline/ai/outreach_prompts.py
---------------------------------
AI services for generating personalized LinkedIn outreach messages
and classifying prospect replies using the configured LLM.
"""

import json
import logging
from typing import Dict, Any, List
from pipeline.ai.client import get_ai_client

logger = logging.getLogger(__name__)


def generate_connection_note(
    target_profile: Dict[str, Any],
    our_company: str,
    custom_prompt: str = ""
) -> str:
    """
    Generate a personalized connection note for a prospect.
    LinkedIn has a strict limit of 300 characters for connection notes.
    """
    ai_client = get_ai_client()
    
    # Format target profile info safely
    target_name = target_profile.get("full_name") or f"{target_profile.get('first_name', '')} {target_profile.get('last_name', '')}".strip() or "there"
    target_title = target_profile.get("title") or "Professional"
    target_org = target_profile.get("organization_name") or ""
    
    profile_summary = (
        f"Name: {target_name}\n"
        f"Title: {target_title}\n"
        f"Company: {target_org}\n"
    )
    if "headline" in target_profile:
        profile_summary += f"Headline: {target_profile['headline']}\n"
    if "summary" in target_profile:
        profile_summary += f"Summary: {target_profile['summary']}\n"
    if "experience" in target_profile:
        exp_list = target_profile["experience"]
        if isinstance(exp_list, list):
            profile_summary += "Experience:\n"
            for exp in exp_list[:2]:  # Use top 2 items
                title = exp.get("title") or ""
                company = exp.get("company") or ""
                profile_summary += f"- {title} at {company}\n"

    system_prompt = (
        "You are an expert sales copywriter. Write a highly personalized, warm, "
        "and non-spammy LinkedIn connection request note.\n"
        "CRITICAL REQUIREMENT: The total output MUST be strictly under 280 characters "
        "including spaces so it fits LinkedIn's limits. Do not include placeholders, "
        "subject lines, or salutations like 'Dear Alex'. Write a direct message."
    )

    user_message = (
        f"Prospect Profile:\n{profile_summary}\n\n"
        f"Our Company Profile / Offering:\n{our_company}\n\n"
    )
    if custom_prompt:
        user_message += f"Guidelines for the message: {custom_prompt}\n\n"
        
    user_message += "Write the LinkedIn connection request note now (max 280 characters):"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        note = ai_client.chat_text(messages).strip()
        # Clean up any potential markdown quotes from LLM output
        if note.startswith('"') and note.endswith('"'):
            note = note[1:-1].strip()
        elif note.startswith("'") and note.endswith("'"):
            note = note[1:-1].strip()
            
        # Hard cap truncation to stay within LinkedIn note limits (max 300 characters)
        if len(note) > 300:
            note = note[:297] + "..."
            
        return note
    except Exception as e:
        logger.error(f"Error generating connection note: {e}")
        # Fallback template
        greeting = f"Hi {target_name}," if target_name != "there" else "Hi,"
        return f"{greeting} I noticed your work in {target_title} and wanted to connect. I'd love to follow your updates."


def generate_followup_message(
    target_profile: Dict[str, Any],
    chat_history: List[Dict[str, str]],
    our_company: str,
    custom_prompt: str = ""
) -> str:
    """
    Generate a personalized follow-up message when the connection is accepted
    or after N days of no response.
    """
    ai_client = get_ai_client()
    
    target_name = target_profile.get("full_name") or f"{target_profile.get('first_name', '')} {target_profile.get('last_name', '')}".strip() or "there"
    target_title = target_profile.get("title") or "Professional"
    target_org = target_profile.get("organization_name") or ""
    
    profile_summary = f"Name: {target_name}\nTitle: {target_title}\nCompany: {target_org}\n"
    if "summary" in target_profile:
        profile_summary += f"Summary: {target_profile['summary']}\n"

    history_str = ""
    for msg in chat_history:
        sender = "Prospect" if msg.get("direction") == "in" else "Us"
        content = msg.get("content") or ""
        history_str += f"{sender}: {content}\n"

    system_prompt = (
        "You are an expert sales copywriter writing a follow-up message on LinkedIn.\n"
        "Keep the tone professional, conversational, and helpful. Do not be pushy. "
        "Enforce a strict length constraint: keep the response under 600 characters."
    )

    user_message = (
        f"Prospect Profile:\n{profile_summary}\n\n"
        f"Chat History:\n{history_str}\n\n"
        f"Our Company Profile / Offering:\n{our_company}\n\n"
    )
    if custom_prompt:
        user_message += f"Guidelines for this follow-up: {custom_prompt}\n\n"
        
    user_message += "Write the personalized follow-up message now:"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]

    try:
        msg = ai_client.chat_text(messages).strip()
        if msg.startswith('"') and msg.endswith('"'):
            msg = msg[1:-1].strip()
        elif msg.startswith("'") and msg.endswith("'"):
            msg = msg[1:-1].strip()
        return msg
    except Exception as e:
        logger.error(f"Error generating follow-up message: {e}")
        return f"Hi {target_name}, thanks for connecting! I'd love to share more about how we help companies with their proposals. Let me know if you'd be open to a quick chat."


def classify_reply_intent(message_content: str) -> Dict[str, Any]:
    """
    Analyze the incoming message content to classify the prospect's intent.
    Returns:
        dict: {
            "intent": "interested" | "not_interested" | "objection" | "out_of_office" | "meeting_request" | "unclear",
            "confidence": float,
            "suggested_next_action": str
        }
    """
    ai_client = get_ai_client()

    system_prompt = (
        "You are a sales operations analyzer. Analyze the incoming message from a prospect "
        "and classify their intent into one of the following categories:\n"
        "1. 'interested' - expresses interest, asks for info.\n"
        "2. 'not_interested' - declines politely or tells us to stop.\n"
        "3. 'objection' - raises a concern or question about price, timing, etc.\n"
        "4. 'out_of_office' - automated out of office reply.\n"
        "5. 'meeting_request' - directly suggests a call, demo, or meeting.\n"
        "6. 'unclear' - neutral responses, connection acceptances without text, or ambiguous text.\n\n"
        "Return a JSON object containing:\n"
        "{\n"
        "  \"intent\": \"<category>\",\n"
        "  \"confidence\": <float between 0.0 and 1.0>,\n"
        "  \"suggested_next_action\": \"<brief suggestion of what we should do next>\"\n"
        "}"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Incoming Message: \"{message_content}\""}
    ]

    try:
        res = ai_client.chat_json(messages)
        # Validate intent output
        valid_intents = {"interested", "not_interested", "objection", "out_of_office", "meeting_request", "unclear"}
        intent = res.get("intent", "unclear").lower()
        if intent not in valid_intents:
            res["intent"] = "unclear"
        res["confidence"] = float(res.get("confidence", 0.5))
        res["suggested_next_action"] = res.get("suggested_next_action", "Review message and respond manually.")
        return res
    except Exception as e:
        logger.error(f"Error classifying reply intent: {e}")
        return {
            "intent": "unclear",
            "confidence": 0.0,
            "suggested_next_action": "Review message and respond manually."
        }
