"""
Masks customer/order/account/site identifiers and email addresses out of any
text before it leaves this system for an external AI provider.

Applied at the two points where raw log content (which, in this app's
ecommerce log format, routinely embeds tokens like
"(customer:1569260120) (order:30060948) (site:27379)") is handed to a
third-party API:
  - app.services.rca.ai_providers.get_ai_suggestion (Claude / Gemini / Ollama)
  - app.services.rag.rag_service.generate_embedding (Gemini embeddings)

Only the network-bound text is masked -- the raw log content already stored
in Postgres/Qdrant is left as-is, since that never leaves this deployment.
"""
import re

from app.core.config import settings

_MASK = "***MASKED***"
_EMAIL_MASK = "***EMAIL_MASKED***"

# Fields this ecommerce platform's logs embed directly in the message text,
# e.g. "(customer:1569260120)", "(order:30060948)", "(site:27379)", or the
# same without parentheses (siteId=27379, customer_id: 1569260120).
_SENSITIVE_KEYS = (
    r"customer(?:_?id)?|order(?:_?id)?|account(?:_?id)?|site(?:_?id)?|user(?:_?id)?"
)

_PAREN_TOKEN_RE = re.compile(
    rf"\(\s*({_SENSITIVE_KEYS})\s*[:=]\s*[^)]*\)", re.IGNORECASE
)
_BARE_TOKEN_RE = re.compile(
    rf"\b({_SENSITIVE_KEYS})\s*[:=]\s*[\w.-]+", re.IGNORECASE
)
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def mask_sensitive_data(text: str) -> str:
    """Redacts customer/order/account/site/user identifiers and email
    addresses from `text`. No-op if masking is disabled via settings."""
    if not text or not settings.MASK_SENSITIVE_DATA_IN_AI_REQUESTS:
        return text
    text = _PAREN_TOKEN_RE.sub(lambda m: f"({m.group(1)}:{_MASK})", text)
    text = _BARE_TOKEN_RE.sub(lambda m: f"{m.group(1)}:{_MASK}", text)
    text = _EMAIL_RE.sub(_EMAIL_MASK, text)
    return text
