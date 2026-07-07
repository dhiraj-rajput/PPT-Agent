"""Business intelligence extraction from cleaned website text."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from huggingface_hub import AsyncInferenceClient
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from config.settings import Settings
from website.crawler import CleanedPageOutput

logger = logging.getLogger(__name__)


class ExtractionError(RuntimeError):
    """Raised when LLM extraction fails."""


class ProductService(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    target_audience: str | None = None


class CompanyInsight(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    confidence_score: float = Field(ge=0.0, le=1.0)


class CompanyProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_name: str = Field(min_length=1)
    website: str = Field(min_length=1)
    business_model: str = Field(min_length=1)
    value_proposition: str = Field(min_length=1)
    products_and_services: list[ProductService] = Field(default_factory=list)
    insights: list[CompanyInsight] = Field(default_factory=list)
    last_updated: float


class HuggingFaceCompanyExtractor:
    """Extract a validated company profile through Hugging Face Inference Providers."""

    def __init__(self, settings: Settings, timeout_seconds: float = 120.0) -> None:
        if not settings.hf_token:
            raise ExtractionError("HF_TOKEN is required for Hugging Face extraction.")
        self._settings = settings
        self._client = AsyncInferenceClient(
            provider=settings.hf_provider,  # type: ignore
            token=settings.hf_token,
            timeout=timeout_seconds,
        )

    async def extract_profile(
        self,
        *,
        company_name: str,
        website: str,
        pages: list[CleanedPageOutput],
        max_pages: int = 5,
    ) -> CompanyProfile:
        if not pages:
            raise ExtractionError("No cleaned pages were provided for extraction.")

        selected_pages = sorted(pages, key=lambda page: (page.depth, page.url))[:max_pages]
        prompt = _build_profile_prompt(company_name, website, selected_pages)
        schema = company_profile_schema()

        payload = await self._complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            schema=schema,
        )
        payload.setdefault("last_updated", time.time())
        payload.setdefault("website", website)
        payload.setdefault("company_name", company_name)

        try:
            return CompanyProfile.model_validate(payload)
        except ValidationError as exc:
            logger.error("company_profile_validation_failed", extra={"errors": exc.errors()})
            raise ExtractionError("Company profile response failed Pydantic validation.") from exc

    async def _complete_json(self, *, system_prompt: str, user_prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response_formats = [
            {
                "type": "json_schema",
                "json_schema": {
                    "name": "company_profile",
                    "schema": schema,
                    "strict": True,
                },
            },
            {"type": "json_object"},
            None,
        ]

        last_error: Exception | None = None
        for response_format in response_formats:
            try:
                kwargs: dict[str, Any] = {
                    "model": self._settings.hf_model_id,
                    "messages": messages,
                    "max_tokens": 2500,
                    "temperature": 0.1,
                }
                if response_format is not None:
                    kwargs["response_format"] = response_format
                response = await self._client.chat_completion(**kwargs)
                content = _extract_message_content(response)
                decoded = _decode_json_object(content)
                if isinstance(decoded, dict):
                    return decoded
                raise ExtractionError("LLM JSON response was not an object.")
            except Exception as exc:
                last_error = exc
                logger.warning("hf_json_attempt_failed", extra={"error_type": type(exc).__name__})

        raise ExtractionError(f"Hugging Face extraction failed: {last_error}") from last_error


def company_profile_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "website": {"type": "string"},
            "business_model": {"type": "string"},
            "value_proposition": {"type": "string"},
            "products_and_services": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "target_audience": {"type": ["string", "null"]},
                    },
                    "required": ["name", "description", "target_audience"],
                    "additionalProperties": False,
                },
            },
            "insights": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "description": {"type": "string"},
                        "source_url": {"type": "string"},
                        "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    },
                    "required": ["category", "description", "source_url", "confidence_score"],
                    "additionalProperties": False,
                },
            },
            "last_updated": {"type": "number"},
        },
        "required": [
            "company_name",
            "website",
            "business_model",
            "value_proposition",
            "products_and_services",
            "insights",
            "last_updated",
        ],
        "additionalProperties": False,
    }


def _build_profile_prompt(company_name: str, website: str, pages: list[CleanedPageOutput]) -> str:
    sections: list[str] = []
    for page in pages:
        markdown = page.cleaned_markdown[:6000]
        sections.append(f"SOURCE_URL: {page.url}\nDEPTH: {page.depth}\nMARKDOWN:\n{markdown}")
    joined = "\n\n---\n\n".join(sections)
    return (
        f"Company name: {company_name}\n"
        f"Website: {website}\n\n"
        "Use only the crawled source text below. Build a concise but useful CompanyProfile JSON object. "
        "Products/services may be property verticals, malls, hospitality assets, residential assets, or commercial offerings. "
        "Every insight must include the source URL that supports it.\n\n"
        f"{joined}"
    )


def _extract_message_content(response: Any) -> str:
    choice = response.choices[0]
    message = choice.message
    if isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = getattr(message, "content", "")
    if not content:
        raise ExtractionError("LLM returned an empty message.")
    return str(content)


def _decode_json_object(content: str) -> Any:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


_SYSTEM_PROMPT = """
You are a precise business-intelligence extraction engine.
Return only valid JSON matching the supplied CompanyProfile schema.
Do not invent facts. If a fact is uncertain, either omit it or mark the confidence lower.
Prefer current business facts over historical background unless history is necessary context.
""".strip()
