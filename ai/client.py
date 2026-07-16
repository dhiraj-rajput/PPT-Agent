"""
ai/client.py
------------
Single shared Ollama Cloud client used by every agent in the project
(website, linkedin, google_search/external_news, compactor, RFP parsing,
RFP response generation, BidForge-style document generation).

Every other module should call the LLM through this file instead of
talking to the `ollama` package directly. That gives us, in one place:

  - a model fallback chain (primary model -> secondary models)
  - retry with exponential backoff
  - explicit detection of HTTP 429 / rate-limit errors so callers can
    decide to fall back to their rule-based path instead of retrying
    forever
  - a single spot to swap providers later if needed

Usage:
    from ai.client import get_ai_client

    client = get_ai_client()
    data = client.chat_json([
        {"role": "system", "content": "..."},
        {"role": "user", "content": "..."},
    ])
"""

from __future__ import annotations

import json
import re
import time
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import ollama as _ollama_lib
    _OLLAMA_AVAILABLE = True
except ImportError:
    _ollama_lib = None
    _OLLAMA_AVAILABLE = False


class RateLimitError(RuntimeError):
    """Raised when the Ollama Cloud API returns a 429 / rate-limit response.

    Callers (agents) should treat this distinctly from other failures:
    per project policy, a rate-limit hit means "fall back to the
    rule-based implementation for this call", not "retry forever".
    """


class AIUnavailableError(RuntimeError):
    """Raised when no AI model could service the request at all
    (package missing, all models + retries exhausted for non-429 reasons)."""


def _looks_like_rate_limit(exc: Exception) -> bool:
    """Best-effort detection of a 429 / rate-limit error across the
    different exception shapes the `ollama` package + underlying HTTP
    client can raise."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("429", "rate limit", "rate-limit", "ratelimit", "too many requests")
    )


class OllamaAIClient:
    """
    Thin wrapper around the `ollama` Python client that adds a model
    fallback chain, retries, and rate-limit classification.
    """

    #: Fallback chain tried (in order) whenever the configured primary
    #: model fails for a non-rate-limit reason. Overridable via
    #: settings.OLLAMA_MODEL_FALLBACKS (comma-separated).
    DEFAULT_FALLBACKS = ["gemma4:31b-cloud", "gemma3:27b", "llama3.1:8b"]

    def __init__(self) -> None:
        from config.settings import settings as _settings
        self._settings = _settings

        self.model: str = getattr(_settings, "OLLAMA_MODEL", "gemma4:31b-cloud") or "gemma4:31b-cloud"
        self.host: str = getattr(_settings, "OLLAMA_HOST", "") or ""
        self.api_key: str = getattr(_settings, "OLLAMA_API_KEY", "") or ""
        self.temperature: float = float(getattr(_settings, "OLLAMA_TEMPERATURE", 0.1) or 0.1)

        raw_fallbacks = getattr(_settings, "OLLAMA_MODEL_FALLBACKS", "") or ""
        parsed_fallbacks = [m.strip() for m in raw_fallbacks.split(",") if m.strip()]
        self.fallback_models: List[str] = parsed_fallbacks or list(self.DEFAULT_FALLBACKS)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat_text(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_retries: int = 3,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat completion request, trying the primary model then
        falling back through `self.fallback_models` and finally to Gemini API.

        Raises:
            RateLimitError:      every model attempted returned a 429.
            AIUnavailableError:  models failed for other reasons.
        """
        models_to_try: List[str] = []
        primary_model = model or self.model
        
        # 1. Primary Ollama model
        if _OLLAMA_AVAILABLE and primary_model:
            models_to_try.append(primary_model)
            
        # 2. Instant fallback: Gemini API
        gemini_api_key = getattr(self._settings, "GEMINI_API_KEY", "")
        if gemini_api_key:
            models_to_try.append("gemini-fallback")

        # 2b. OpenRouter API
        openrouter_api_key = getattr(self._settings, "OPENROUTER_API_KEY", "")
        if openrouter_api_key:
            models_to_try.append("openrouter-fallback")

        # 3. Other Ollama models
        if _OLLAMA_AVAILABLE:
            for m in self.fallback_models:
                if m not in models_to_try:
                    models_to_try.append(m)

        if not models_to_try:
            raise AIUnavailableError("No AI providers (Ollama or Gemini API key) are configured/available.")

        last_error: Optional[Exception] = None
        saw_rate_limit = False
        all_rate_limited = True

        for candidate_model in models_to_try:
            if candidate_model == "gemini-fallback":
                for attempt in range(max_retries):
                    try:
                        return self._call_gemini(messages, json_mode=json_mode)
                    except Exception as exc:
                        last_error = exc
                        if isinstance(exc, RateLimitError) or _looks_like_rate_limit(exc):
                            saw_rate_limit = True
                            logger.warning(
                                "[AI] Gemini API rate-limited (429). "
                                "Trying next fallback."
                            )
                            break
                        all_rate_limited = False
                        wait = 1.5 * (1.6 ** attempt)
                        logger.warning(
                            f"[AI] Gemini API attempt {attempt + 1}/{max_retries} failed: {exc} "
                            f"(retrying in {wait:.1f}s)"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(wait)
                continue

            if candidate_model == "openrouter-fallback":
                for attempt in range(max_retries):
                    try:
                        return self._call_openrouter(messages, json_mode=json_mode)
                    except Exception as exc:
                        last_error = exc
                        if isinstance(exc, RateLimitError) or _looks_like_rate_limit(exc):
                            saw_rate_limit = True
                            logger.warning(
                                "[AI] OpenRouter rate-limited (429). "
                                "Trying next fallback."
                            )
                            break
                        all_rate_limited = False
                        wait = 1.5 * (1.6 ** attempt)
                        logger.warning(
                            f"[AI] OpenRouter attempt {attempt + 1}/{max_retries} failed: {exc} "
                            f"(retrying in {wait:.1f}s)"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(wait)
                continue

            # Ollama Path
            for attempt in range(max_retries):
                try:
                    return self._call_ollama(messages, model=candidate_model, json_mode=json_mode)
                except Exception as exc:
                    last_error = exc
                    if _looks_like_rate_limit(exc):
                        saw_rate_limit = True
                        logger.warning(
                            f"[AI] {candidate_model} rate-limited (429). "
                            f"Not retrying this model; trying next fallback."
                        )
                        break  # don't burn retries on a model that's rate-limited — move on
                    all_rate_limited = False
                    wait = 1.5 * (1.6 ** attempt)
                    logger.warning(
                        f"[AI] {candidate_model} attempt {attempt + 1}/{max_retries} failed: {exc} "
                        f"(retrying in {wait:.1f}s)"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(wait)

        if saw_rate_limit and all_rate_limited:
            raise RateLimitError(
                f"All AI models rate-limited (429). Models tried: {models_to_try}. "
                f"Last error: {last_error}"
            )
        raise AIUnavailableError(
            f"All AI models failed. Models tried: {models_to_try}. Last error: {last_error}"
        )

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_retries: int = 3,
    ) -> Dict[str, Any]:
        """Same as chat_text, but parses the response as a JSON object."""
        raw = self.chat_text(messages, model=model, max_retries=max_retries, json_mode=True)
        return self._parse_json_from_response(raw)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _call_ollama(self, messages: List[Dict[str, str]], model: str, json_mode: bool) -> str:
        client_kwargs: Dict[str, Any] = {}
        if self.host:
            client_kwargs["host"] = self.host
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            client_kwargs["headers"] = headers

        chat_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "options": {"temperature": self.temperature},
        }
        if json_mode:
            chat_kwargs["format"] = "json"

        if not _OLLAMA_AVAILABLE or _ollama_lib is None:
            raise AIUnavailableError("Ollama package is not imported / available.")

        ollama_lib = _ollama_lib
        assert ollama_lib is not None

        if client_kwargs:
            client = ollama_lib.Client(**client_kwargs)
            response = client.chat(**chat_kwargs)
        else:
            response = ollama_lib.chat(**chat_kwargs)

        content = response.message.content
        if not content:
            raise ValueError(f"Ollama ({model}) returned an empty response.")
        return str(content)

    def _call_gemini(self, messages: List[Dict[str, str]], json_mode: bool) -> str:
        import httpx
        api_key = getattr(self._settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        # Robust list of models to try in order. Cleaned up obsolete/deprecated models.
        gemini_models = ["gemini-3.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"]
        
        last_error = None
        saw_rate_limit = False
        
        for model in gemini_models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            
            contents = []
            system_instruction = None

            for msg in messages:
                role = msg.get("role")
                content = msg.get("content")
                if role == "system":
                    system_instruction = {
                        "parts": [{"text": content}]
                    }
                elif role == "user":
                    contents.append({
                        "role": "user",
                        "parts": [{"text": content}]
                    })
                elif role in ("assistant", "model"):
                    contents.append({
                        "role": "model",
                        "parts": [{"text": content}]
                    })

            payload: Dict[str, Any] = {
                "contents": contents
            }
            if system_instruction:
                payload["systemInstruction"] = system_instruction

            generation_config: Dict[str, Any] = {
                "temperature": self.temperature
            }
            if json_mode:
                generation_config["responseMimeType"] = "application/json"

            payload["generationConfig"] = generation_config

            headers = {"Content-Type": "application/json"}
            logger.info(f"[Gemini Fallback] -> Calling Gemini API ({model})...")

            try:
                with httpx.Client(timeout=45) as client:
                    resp = client.post(url, json=payload, headers=headers)

                if resp.status_code == 429:
                    saw_rate_limit = True
                    raise RateLimitError(f"Gemini API ({model}) rate limited (429).")
                if not resp.is_success:
                    raise ValueError(f"Gemini API ({model}) returned {resp.status_code}: {resp.text}")

                res_data = resp.json()
                candidates = res_data.get("candidates", [])
                if not candidates:
                    raise ValueError(f"No candidates returned from Gemini ({model}).")
                text = candidates[0]["content"]["parts"][0]["text"]
                return str(text)
            except Exception as exc:
                last_error = exc
                logger.warning(f"[Gemini Fallback] Model {model} failed: {exc}. Trying next candidate...")

        if saw_rate_limit:
            raise RateLimitError(f"All Gemini models rate-limited. Last error: {last_error}")
        raise last_error or ValueError("All Gemini fallback models failed.")

    def _call_openrouter(self, messages: List[Dict[str, str]], json_mode: bool) -> str:
        import httpx
        api_key = getattr(self._settings, "OPENROUTER_API_KEY", "")
        model = getattr(self._settings, "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
        base_url = getattr(self._settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:3000",
            "X-Title": "PPT-Agent",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        logger.info(f"[OpenRouter Fallback] -> Calling OpenRouter ({model})...")

        with httpx.Client(timeout=45) as client:
            resp = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)

        if resp.status_code == 429:
            raise RateLimitError(f"OpenRouter ({model}) rate limited (429).")
        if not resp.is_success:
            raise ValueError(f"OpenRouter ({model}) returned {resp.status_code}: {resp.text}")

        res_data = resp.json()
        choices = res_data.get("choices", [])
        if not choices:
            raise ValueError(f"No choices returned from OpenRouter ({model}).")
        
        content = choices[0]["message"]["content"]
        if not content:
            raise ValueError(f"OpenRouter ({model}) returned an empty response.")
        return str(content)

    def _parse_json_from_response(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"(\{.*\})", text, re.DOTALL)
            if not match:
                raise ValueError(f"No JSON object found in AI response. First 500 chars: {text[:500]}")
            parsed = json.loads(match.group(1))
        if not isinstance(parsed, dict):
            raise ValueError("AI response must be a JSON object.")
        return parsed


_client_singleton: Optional[OllamaAIClient] = None


def get_ai_client() -> OllamaAIClient:
    """Module-level singleton accessor."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = OllamaAIClient()
    return _client_singleton
