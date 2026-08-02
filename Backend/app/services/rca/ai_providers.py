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

DEFAULT_PROVIDER = "claude"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.1:8b"

VALID_PROVIDERS = {"claude", "gemini", "ollama"}

OLLAMA_TIMEOUT_SECONDS = 120.0


class AiProviderError(Exception):
    """Raised for any provider-side configuration or call failure; the caller
    turns this into a 400 so the UI shows a clear, actionable message."""
    pass


def get_provider_config(db: Session) -> dict:
    return {
        "provider": app_setting_repo.get(db, AI_PROVIDER_KEY) or DEFAULT_PROVIDER,
        "ollama_base_url": app_setting_repo.get(db, OLLAMA_BASE_URL_KEY) or DEFAULT_OLLAMA_BASE_URL,
        "ollama_model": app_setting_repo.get(db, OLLAMA_MODEL_KEY) or DEFAULT_OLLAMA_MODEL,
    }


def get_ai_suggestion(db: Session, prompt: str) -> Tuple[str, str, str]:
    """Dispatches to whichever provider is currently configured. Returns (provider, model, suggestion_text)."""
    config = get_provider_config(db)
    provider = config["provider"]

    if provider == "claude":
        model, text = _call_claude(prompt)
    elif provider == "gemini":
        model, text = _call_gemini(prompt)
    elif provider == "ollama":
        model, text = _call_ollama(prompt, config["ollama_base_url"], config["ollama_model"])
    else:
        raise AiProviderError(f"Unknown AI provider configured: {provider}")

    return provider, model, text


def _call_claude(prompt: str) -> Tuple[str, str]:
    if not app_settings.CLAUDE_API_KEY:
        raise AiProviderError("CLAUDE_API_KEY is not configured. Set it in the backend .env file.")

    import anthropic
    try:
        client = anthropic.Anthropic(api_key=app_settings.CLAUDE_API_KEY)
        response = client.messages.create(
            model=app_settings.CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )
    except Exception as e:
        raise AiProviderError(f"Claude API call failed: {str(e)}")

    text = "".join(block.text for block in response.content if block.type == "text")
    return app_settings.CLAUDE_MODEL, text


def _call_gemini(prompt: str) -> Tuple[str, str]:
    if not app_settings.GEMINI_API_KEY:
        raise AiProviderError("GEMINI_API_KEY is not configured. Set it in the backend .env file.")

    import google.generativeai as genai
    try:
        genai.configure(api_key=app_settings.GEMINI_API_KEY)
        model = genai.GenerativeModel(model_name=app_settings.GEMINI_MODEL)
        response = model.generate_content(prompt)
    except Exception as e:
        raise AiProviderError(f"Gemini API call failed: {str(e)}")

    if not response.text:
        raise AiProviderError("Gemini returned an empty response.")
    return app_settings.GEMINI_MODEL, response.text


def _call_ollama(prompt: str, base_url: str, model: str) -> Tuple[str, str]:
    url = f"{base_url.rstrip('/')}/api/chat"
    try:
        resp = httpx.post(
            url,
            json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False},
            timeout=OLLAMA_TIMEOUT_SECONDS
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        raise AiProviderError(f'Could not reach Ollama at {base_url}. Is it running? (try "ollama serve")')
    except httpx.HTTPStatusError as e:
        raise AiProviderError(f"Ollama returned an error ({e.response.status_code}): {e.response.text[:200]}")
    except Exception as e:
        raise AiProviderError(f"Ollama request failed: {str(e)}")

    text = (resp.json().get("message") or {}).get("content", "")
    if not text:
        raise AiProviderError("Ollama returned an empty response.")
    return model, text
