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
    from pipeline.ai.client import get_ai_client

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

try:
    import json_repair as _json_repair_lib
    _JSON_REPAIR_AVAILABLE = True
except ImportError:
    _json_repair_lib = None
    _JSON_REPAIR_AVAILABLE = False


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
    DEFAULT_FALLBACKS = ["gemma4:e4b", "gemma3:4b", "gemma4:31b-cloud", "llama3.1:8b"]

    def __init__(self) -> None:
        import importlib
        try:
            from backend.config.settings import settings as _settings
        except ImportError:
            _settings = importlib.import_module("config.settings").settings
        self._settings = _settings

        self.model: str = getattr(_settings, "OLLAMA_MODEL", "gemma4:e4b") or "gemma4:e4b"
        self.host: str = getattr(_settings, "ollama_host", "") or ""
        self.api_key: str = getattr(_settings, "OLLAMA_API_KEY", "") or ""
        self.temperature: float = float(getattr(_settings, "OLLAMA_TEMPERATURE", 0.1) or 0.1)
        # Was hardcoded to 600.0 regardless of OLLAMA_TIMEOUT in .env — that setting
        # was silently ignored. Now actually reads it (still defaults to 600s).
        self.timeout: float = float(getattr(_settings, "OLLAMA_TIMEOUT", 600) or 600)

        raw_fallbacks = getattr(_settings, "OLLAMA_MODEL_FALLBACKS", "") or ""
        parsed_fallbacks = [m.strip() for m in raw_fallbacks.split(",") if m.strip()]
        self.fallback_models: List[str] = parsed_fallbacks or list(self.DEFAULT_FALLBACKS)

    def _is_direct_cloud_host(self) -> bool:
        """True when self.host points straight at ollama.com (no local Ollama
        daemon in between — which is what happens whenever OLLAMA_HOST is left
        blank but OLLAMA_API_KEY is set, since ollama_host then resolves to
        "https://ollama.com" itself)."""
        return bool(self.host) and "ollama.com" in self.host

    def _normalize_model_for_host(self, model: str) -> str:
        """The '-cloud' suffix (e.g. 'gemma4:31b-cloud') is a *local-daemon*
        routing convention: it tells a locally-running Ollama to proxy that
        request to Ollama Cloud. When we're calling https://ollama.com
        directly — no local daemon involved — the direct API already only
        serves cloud models and expects the bare id ('gemma4:31b'), so a
        '-cloud' suffixed name 404s. This was the actual reason the
        configured cloud Gemma model wasn't responding."""
        if self._is_direct_cloud_host() and model.endswith("-cloud"):
            return model[: -len("-cloud")]
        return model

    def ping_ollama(self) -> bool:
        """Check if Ollama is available and responding. Returns True if healthy."""
        try:
            if not _OLLAMA_AVAILABLE or _ollama_lib is None:
                return False
            client_kwargs: Dict[str, Any] = {"timeout": self.timeout}
            if self.host:
                client_kwargs["host"] = self.host
            if self.api_key:
                client_kwargs["headers"] = {"Authorization": f"Bearer {self.api_key}"}
            if client_kwargs:
                client = _ollama_lib.Client(**client_kwargs)
                client.list()
            else:
                _ollama_lib.list()
            return True
        except Exception as e:
            logger.warning(f"[AI] Ollama ping failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat_text(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_retries: int = 3,
        json_mode: bool = False,
        max_tokens: int = 8192,
    ) -> str:
        """
        Send a chat completion request, trying the primary model then
        falling back through `self.fallback_models` and finally to Gemini API.

        max_tokens controls the output-length cap sent to whichever provider
        ends up servicing the request (num_predict / maxOutputTokens /
        max_tokens depending on provider). Defaults to 8192, the same value
        every caller used before this was configurable. Callers generating
        long-form content (e.g. a single proposal section) should pass a
        value sized to what they actually asked for, instead of silently
        inheriting a cap tuned for short structured-JSON calls.

        Raises:
            RateLimitError:      every model attempted returned a 429.
            AIUnavailableError:  models failed for other reasons.
        """
        models_to_try: List[str] = []
        primary_model = model or self.model

        gemini_api_key = getattr(self._settings, "GEMINI_API_KEY", "")
        openrouter_api_key = getattr(self._settings, "OPENROUTER_API_KEY", "")

        raw_order = (getattr(self._settings, "AI_PROVIDER_ORDER", "") or "auto").strip().lower()
        # "auto" prefers fast cloud APIs over local/Codespaces Ollama, which has no GPU
        # and is typically 10-30x slower for the same request. Set AI_PROVIDER_ORDER to
        # e.g. "ollama,gemini,openrouter" to force local-first instead.
        provider_order = (
            ["gemini", "openrouter", "ollama"]
            if raw_order in ("", "auto")
            else [p.strip() for p in raw_order.split(",") if p.strip()]
        )

        for provider in provider_order:
            if provider == "gemini" and gemini_api_key and "gemini-fallback" not in models_to_try:
                models_to_try.append("gemini-fallback")
            elif provider == "openrouter" and openrouter_api_key and "openrouter-fallback" not in models_to_try:
                models_to_try.append("openrouter-fallback")
            elif provider == "ollama" and _OLLAMA_AVAILABLE and primary_model and primary_model not in models_to_try:
                models_to_try.append(primary_model)

        # Remaining Ollama fallback models stay available as a last resort even when
        # Ollama isn't first in the preference order.
        if _OLLAMA_AVAILABLE:
            for m in self.fallback_models:
                if m not in models_to_try:
                    models_to_try.append(m)

        if not models_to_try:
            raise AIUnavailableError("No AI providers (Ollama, Gemini, or OpenRouter) are configured/available.")

        last_error: Optional[Exception] = None
        saw_rate_limit = False
        all_rate_limited = True

        for candidate_model in models_to_try:
            if candidate_model == "gemini-fallback":
                for attempt in range(max_retries):
                    try:
                        return self._call_gemini(messages, json_mode=json_mode, max_tokens=max_tokens)
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
                        return self._call_openrouter(messages, json_mode=json_mode, max_tokens=max_tokens)
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
                    return self._call_ollama(messages, model=candidate_model, json_mode=json_mode, max_tokens=max_tokens)
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

    def _call_ollama(self, messages: List[Dict[str, str]], model: str, json_mode: bool, max_tokens: int = 8192) -> str:
        model = self._normalize_model_for_host(model)
        client_kwargs: Dict[str, Any] = {"timeout": self.timeout}
        if self.host:
            client_kwargs["host"] = self.host
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            client_kwargs["headers"] = headers

        chat_kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens
            },
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

    def _call_gemini(self, messages: List[Dict[str, str]], json_mode: bool, max_tokens: int = 8192) -> str:
        import httpx
        api_key = getattr(self._settings, "GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        # gemini-2.0-flash / gemini-2.0-flash-lite were retired June 1, 2026, and the
        # 1.5 family is fully shut down — both 404 if tried. gemini-flash-latest is
        # an auto-updating alias (survives Google's next migration too), so it goes
        # first; gemini-3.5-flash and gemini-3.1-flash-lite are named as a backstop.
        gemini_models = ["gemini-flash-latest", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
        
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
                "temperature": self.temperature,
                "maxOutputTokens": max_tokens
            }
            if json_mode:
                generation_config["responseMimeType"] = "application/json"

            payload["generationConfig"] = generation_config

            headers = {"Content-Type": "application/json"}
            logger.info(f"[Gemini Fallback] -> Calling Gemini API ({model})...")

            try:
                with httpx.Client(timeout=self.timeout) as client:
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

    def _call_openrouter(self, messages: List[Dict[str, str]], json_mode: bool, max_tokens: int = 8192) -> str:
        import httpx
        api_key = getattr(self._settings, "OPENROUTER_API_KEY", "")
        base_url = getattr(self._settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is not set.")

        # Primary model + fallback chain.
        # nvidia/nemotron frequently unavailable; google/gemma-3-27b-it:free and
        # llama-3.3-70b are more consistently online for structured JSON output.
        primary_model = getattr(self._settings, "OPENROUTER_MODEL", "google/gemma-3-27b-it:free")
        raw_fallbacks = getattr(self._settings, "OPENROUTER_MODEL_FALLBACKS", "") or ""
        fallback_models = [m.strip() for m in raw_fallbacks.split(",") if m.strip()] or [
            "meta-llama/llama-3.3-70b-instruct:free",
            "mistralai/mistral-7b-instruct:free",
            "openrouter/auto",
        ]
        models_to_try = [primary_model] + [m for m in fallback_models if m != primary_model]

        referer = getattr(self._settings, "CLIENT_URL", "http://localhost:5173")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": referer,
            "X-Title": "OrbitAvanya",
        }

        last_error: Exception | None = None
        for model in models_to_try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": self.temperature,
                "max_tokens": max_tokens,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            logger.info(f"[OpenRouter] -> Calling OpenRouter ({model})...")

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)

                if resp.status_code == 429:
                    raise RateLimitError(f"OpenRouter ({model}) rate limited (429).")
                if resp.status_code == 503 or resp.status_code == 404:
                    # Model unavailable or not found — try next
                    logger.warning(f"[OpenRouter] Model {model} returned {resp.status_code} — trying next.")
                    last_error = ValueError(f"OpenRouter ({model}) returned {resp.status_code}")
                    continue
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

            except RateLimitError:
                raise  # Propagate rate limit immediately
            except Exception as exc:
                last_error = exc
                logger.warning(f"[OpenRouter] Model {model} failed: {exc}. Trying next model...")
                continue

        raise last_error or ValueError("All OpenRouter models failed.")

    def _parse_json_from_response(self, text: str) -> Dict[str, Any]:
        """Robustly parse a JSON response from an LLM.
        
        Handles common LLM output quirks:
        - Markdown code fences (```json ... ```)
        - Trailing commas in objects/arrays
        - Single-line JavaScript-style comments (// ...)
        - Leading/trailing whitespace and newlines
        - Partial JSON wrapped in extra text
        - Unescaped double quotes inside string values
        """
        text = text.strip()
        
        # Strip markdown code fences
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        
        # Remove JavaScript-style single-line comments (// ...)
        text = re.sub(r"//[^\n]*\n", "\n", text)
        
        # Remove trailing commas before } or ] (common LLM mistake)
        text = re.sub(r",\s*([}\]])", r"\1", text)
        
        # Sanitize literal unescaped control characters in JSON strings
        text_clean = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", text)

        try:
            parsed = json.loads(text_clean, strict=False)
        except json.JSONDecodeError as exc:
            # 1. Try json_repair library if available
            parsed = None
            if _JSON_REPAIR_AVAILABLE and _json_repair_lib is not None:
                try:
                    repaired_str = _json_repair_lib.repair_json(text_clean, return_objects=False)
                    parsed = json.loads(repaired_str, strict=False)
                except Exception:
                    pass

            if parsed is None:
                try:
                    # 2. Try unclosed quote repair & escaping inner quotes
                    repaired = self._repair_unclosed_quotes(text_clean)
                    repaired = self._escape_inner_quotes(repaired)
                    parsed = json.loads(repaired, strict=False)
                except Exception:
                    # 3. Try to extract the first JSON object or array from the text
                    match = re.search(r"(\{.*\}|\[.*\])", text_clean, re.DOTALL)
                    if not match:
                        raise ValueError(f"No JSON found in AI response. First 500 chars: {text[:500]}") from exc
                    try:
                        repaired_match = self._repair_unclosed_quotes(match.group(1))
                        repaired_match = self._escape_inner_quotes(repaired_match)
                        parsed = json.loads(repaired_match, strict=False)
                    except json.JSONDecodeError:
                        if _JSON_REPAIR_AVAILABLE and _json_repair_lib is not None:
                            try:
                                parsed = _json_repair_lib.repair_json(match.group(1), return_objects=True)
                            except Exception as inner_exc:
                                raise ValueError(f"Extracted JSON is malformed: {inner_exc}. First 500 chars: {text[:500]}") from exc
                        else:
                            raise ValueError(f"Extracted JSON is malformed. First 500 chars: {text[:500]}") from exc
        
        # Wrap arrays in a dict for backwards compatibility
        if isinstance(parsed, list):
            return {"items": parsed}
        if not isinstance(parsed, dict):
            raise ValueError(f"AI response must be a JSON object or array, got {type(parsed).__name__}.")
        return parsed

    def _repair_unclosed_quotes(self, text_str: str) -> str:
        """Repair common LLM JSON syntax errors like unclosed quotes before newlines and truncated JSON structures."""
        # 1. Unclosed quote before a newline when followed by another key (e.g. "website": "https:\n"industry")
        text_str = re.sub(
            r'("[a-zA-Z0-9_]+\s*:\s*"[^"\r\n]*?)(?=\r?\n\s*"[a-zA-Z0-9_]+\s*:)',
            r'\1"',
            text_str
        )
        # 2. Unclosed quote before a newline when followed by a closing brace or comma
        text_str = re.sub(
            r'("[a-zA-Z0-9_]+\s*:\s*"[^"\r\n]*?)(?=\r?\n\s*[\}\],])',
            r'\1"',
            text_str
        )
        # 3. Truncated string at end of text (odd number of double quotes)
        if text_str.count('"') % 2 != 0:
            text_str = text_str.rstrip() + '"'

        # 4. Strip trailing comma before closing structural elements
        text_str = re.sub(r",\s*$", "", text_str.strip())

        # 5. Auto-close unclosed brackets/braces at the end of truncated JSON
        open_brackets = text_str.count('[') - text_str.count(']')
        open_braces = text_str.count('{') - text_str.count('}')
        if open_brackets > 0:
            text_str += '\n' + (']' * open_brackets)
        if open_braces > 0:
            text_str += '\n' + ('}' * open_braces)

        return text_str

    def _escape_inner_quotes(self, json_str: str) -> str:
        """Resiliently escape unescaped double quotes inside JSON string values.
        
        Boundary quotes are double quotes preceded or followed by JSON delimiters
        (e.g. {, }, [, ], :, ,). Non-boundary quotes inside string values are escaped.
        """
        result = []
        i = 0
        n = len(json_str)
        while i < n:
            char = json_str[i]
            if char == '"':
                # Check if this quote is already escaped
                is_escaped = False
                k = i - 1
                while k >= 0 and json_str[k] == '\\':
                    is_escaped = not is_escaped
                    k -= 1
                
                if not is_escaped:
                    # Find previous non-whitespace char
                    left_char = ""
                    k = i - 1
                    while k >= 0:
                        if not json_str[k].isspace():
                            left_char = json_str[k]
                            break
                        k -= 1
                    
                    # Find next non-whitespace char
                    right_char = ""
                    k = i + 1
                    while k < n:
                        if not json_str[k].isspace():
                            right_char = json_str[k]
                            break
                        k += 1
                    
                    # A quote is a JSON delimiter if:
                    # - left_char in ('{', '[', ',', ':') OR
                    # - right_char in ('}', ']', ',', ':') OR
                    # - start/end of the string
                    is_delimiter = (
                        left_char in ('{', '[', ',', ':') or
                        right_char in ('}', ']', ',', ':') or
                        left_char == "" or
                        right_char == ""
                    )
                    
                    if not is_delimiter:
                        result.append('\\"')
                        i += 1
                        continue
            result.append(char)
            i += 1
        return "".join(result)


_client_singleton: Optional[OllamaAIClient] = None


def get_ai_client() -> OllamaAIClient:
    """Module-level singleton accessor."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = OllamaAIClient()
    return _client_singleton