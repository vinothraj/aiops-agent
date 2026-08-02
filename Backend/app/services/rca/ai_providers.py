import logging
from typing import Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings as app_settings
from app.repositories.repositories import app_setting_repo

logger = logging.getLogger(__name__)

AI_PROVIDER_KEY = "ai_provider"
OLLAMA_BASE_URL_KEY = "ollama_base_url"
OLLAMA_MODEL_KEY = "ollama_model"
AUTO_RCA_ENABLED_KEY = "auto_rca_enabled"
CLAUDE_API_KEY_SETTING = "claude_api_key"
GEMINI_API_KEY_SETTING = "gemini_api_key"

DEFAULT_PROVIDER = "claude"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"

VALID_PROVIDERS = {"claude", "gemini", "ollama"}

# Generous timeout: local models (esp. on CPU) can be slow, and RCA prompts
# (full log context + RAG docs) are much larger than a typical Ask AI prompt.
OLLAMA_TIMEOUT_SECONDS = 300.0


class AiProviderError(Exception):
    """Raised for any provider-side configuration or call failure; the caller
    turns this into a 400 so the UI shows a clear, actionable message."""
    pass


def get_provider_config(db: Session) -> dict:
    return {
        "provider": app_setting_repo.get(db, AI_PROVIDER_KEY) or DEFAULT_PROVIDER,
        "ollama_base_url": app_setting_repo.get(db, OLLAMA_BASE_URL_KEY) or DEFAULT_OLLAMA_BASE_URL,
        "ollama_model": app_setting_repo.get(db, OLLAMA_MODEL_KEY) or DEFAULT_OLLAMA_MODEL,
        "auto_rca_enabled": (app_setting_repo.get(db, AUTO_RCA_ENABLED_KEY) or "false").lower() == "true",
    }


def get_claude_api_key(db: Session) -> Optional[str]:
    """DB-stored key (set via Settings) takes precedence; falls back to CLAUDE_API_KEY in .env."""
    return app_setting_repo.get(db, CLAUDE_API_KEY_SETTING) or app_settings.CLAUDE_API_KEY


def get_gemini_api_key(db: Session) -> Optional[str]:
    """DB-stored key (set via Settings) takes precedence; falls back to GEMINI_API_KEY in .env."""
    return app_setting_repo.get(db, GEMINI_API_KEY_SETTING) or app_settings.GEMINI_API_KEY


def is_claude_configured(db: Session) -> bool:
    return bool(get_claude_api_key(db))


def is_gemini_configured(db: Session) -> bool:
    return bool(get_gemini_api_key(db))


def get_ai_suggestion(db: Session, prompt: str, system_prompt: Optional[str] = None) -> Tuple[str, str, str]:
    """
    Dispatches to whichever provider is currently configured. Returns
    (provider, model, response_text). system_prompt is optional -- used by
    RCA generation (which needs strict JSON-schema instructions) but not by
    the simpler Ask AI fix-suggestion prompt.
    """
    config = get_provider_config(db)
    provider = config["provider"]

    if provider == "claude":
        model, text = _call_claude(db, prompt, system_prompt)
    elif provider == "gemini":
        model, text = _call_gemini(db, prompt, system_prompt)
    elif provider == "ollama":
        model, text = _call_ollama(prompt, config["ollama_base_url"], config["ollama_model"], system_prompt)
    else:
        raise AiProviderError(f"Unknown AI provider configured: {provider}")

    return provider, model, text


def _call_claude(db: Session, prompt: str, system_prompt: Optional[str] = None) -> Tuple[str, str]:
    api_key = get_claude_api_key(db)
    if not api_key:
        raise AiProviderError("Claude API key is not configured. Set it in Settings → AI Provider, or CLAUDE_API_KEY in the backend .env file.")

    import anthropic
    try:
        client = anthropic.Anthropic(api_key=api_key)
        kwargs = dict(model=app_settings.CLAUDE_MODEL, max_tokens=4096, messages=[{"role": "user", "content": prompt}])
        if system_prompt:
            kwargs["system"] = system_prompt
        response = client.messages.create(**kwargs)
        text = "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        raise AiProviderError(f"Claude API call failed: {str(e)}")

    return app_settings.CLAUDE_MODEL, text


def _call_gemini(db: Session, prompt: str, system_prompt: Optional[str] = None) -> Tuple[str, str]:
    api_key = get_gemini_api_key(db)
    if not api_key:
        raise AiProviderError("Gemini API key is not configured. Set it in Settings → AI Provider, or GEMINI_API_KEY in the backend .env file.")

    import google.generativeai as genai
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(model_name=app_settings.GEMINI_MODEL, system_instruction=system_prompt)
        response = model.generate_content(prompt)
        # .text is a property that can itself raise (e.g. no candidates
        # returned because the prompt was safety-blocked) -- keep it inside
        # this try block so that failure is wrapped as AiProviderError too,
        # not left to leak out as whatever raw exception type the SDK uses.
        text = response.text
    except Exception as e:
        raise AiProviderError(f"Gemini API call failed: {str(e)}")

    if not text:
        raise AiProviderError("Gemini returned an empty response.")
    return app_settings.GEMINI_MODEL, text


def _call_ollama(prompt: str, base_url: str, model: str, system_prompt: Optional[str] = None) -> Tuple[str, str]:
    url = f"{base_url.rstrip('/')}/api/chat"
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = httpx.post(
            url,
            json={"model": model, "messages": messages, "stream": False},
            timeout=OLLAMA_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
        text = (resp.json().get("message") or {}).get("content", "")
    except httpx.ConnectError:
        raise AiProviderError(f'Could not reach Ollama at {base_url}. Is it running? (try "ollama serve")')
    except httpx.HTTPStatusError as e:
        raise AiProviderError(f"Ollama returned an error ({e.response.status_code}): {e.response.text[:200]}")
    except httpx.TimeoutException:
        raise AiProviderError(f"Ollama timed out after {int(OLLAMA_TIMEOUT_SECONDS)}s -- the model may be too slow for this hardware.")
    except Exception as e:
        raise AiProviderError(f"Ollama request failed: {str(e)}")

    if not text:
        raise AiProviderError("Ollama returned an empty response.")
    return model, text
