"""
lib/llm.py — the LLM translation call  (TODO: you implement)
============================================================
One job: turn an English string into Mexican Spanish using an LLM.

Provider is your choice. The default example below is Anthropic Claude
(`pip install anthropic`, set ANTHROPIC_API_KEY). Hamza's launched version
used Google Gemini — either is fine. Whatever you pick:

  - Write a PROMPT that pins the register to Mexican Spanish (es-MX), not
    generic/Castilian Spanish. Ask for ONLY the translation, no preamble.
  - Keep numbers, prices ($), and product/model codes unchanged.
  - Return a clean string (strip quotes/whitespace the model may add).

FAIL LOUD: do NOT wrap the call in a try/except that returns `text` on error.
If the provider fails, let the exception propagate so the caller returns a 502.
Silently returning the untranslated input is an automatic fail on this
assignment (and a real production bug — it ships English while looking healthy).
"""
import os
from typing import Optional

from anthropic import AsyncAnthropic

# NOTE: the assignment's placeholder default ("claude-sonnet-4-6") is not a
# valid model string as of this writing — use a real current Claude model.
# Swap via MODEL in .env; provider/key are never hard-coded.
MODEL_DEFAULT = os.getenv("MODEL", "claude-sonnet-5")

# Human-readable names for the locales this widget is likely to target, used
# to make the prompt's register instruction explicit rather than relying on
# the model to infer "es-MX" == Mexican Spanish.
_TARGET_NAMES = {
    "es-MX": "Mexican Spanish",
    "es-ES": "Castilian (Spain) Spanish",
    "es": "Spanish",
    "pt-BR": "Brazilian Portuguese",
    "fr": "French",
}

SYSTEM_PROMPT_TEMPLATE = (
    "You are a professional translator specializing in {language} for retail "
    "and e-commerce web content. Translate the user's English text into natural, "
    "fluent {language} the way it is actually written and spoken in that market "
    "— not a generic or neighboring-dialect register. For Mexican Spanish "
    "specifically: use Latin American vocabulary and grammar (e.g. 'carrito' not "
    "'cesta', 'computadora' not 'ordenador', 'ustedes' not 'vosotros'), never "
    "Castilian/European Spanish forms.\n\n"
    "Rules — follow all of them:\n"
    "1. Return ONLY the translated text. No preamble, no explanation, no notes, "
    "no wrapping quotes or markdown.\n"
    "2. Preserve numbers, prices (with currency symbols, e.g. $19.99), percentages, "
    "dates, units, and product/model/SKU codes exactly as written — do not "
    "translate, reformat, or localize them.\n"
    "3. Preserve HTML tags, entities, or template placeholders (e.g. {{name}}) "
    "unchanged if present.\n"
    "4. If the input is a proper noun, brand name, or already in the target "
    "language, return it unchanged.\n"
)

_client: Optional[AsyncAnthropic] = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


def _clean(raw: str) -> str:
    """Strip whitespace and a single layer of wrapping quotes the model may add."""
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'“”":
        s = s[1:-1].strip()
    return s


async def translate_text(text: str, target: str = "es-MX", model: str = MODEL_DEFAULT) -> str:
    """Return `text` translated into `target` (Mexican Spanish by default).

    FAILS LOUD: any provider error (auth, rate limit, network) propagates as an
    exception. Never catch it here and return `text` unchanged — that would
    silently ship untranslated English while looking healthy.
    """
    language = _TARGET_NAMES.get(target, target)
    client = _get_client()

    msg = await client.messages.create(
        model=model,
        max_tokens=1024,
        # NOTE: no `temperature` param — some current Claude models reject it
        # outright ("`temperature` is deprecated for this model"). Translation
        # doesn't need explicit sampling control; omit it for model portability.
        system=SYSTEM_PROMPT_TEMPLATE.format(language=language),
        messages=[{"role": "user", "content": text}],
    )

    # Some current models emit a ThinkingBlock ahead of the actual answer, so
    # content[0] isn't reliably the text — scan for the first text block
    # instead. Fail loud (don't guess/return empty) if there isn't one.
    text_block = next((b for b in msg.content if getattr(b, "type", None) == "text"), None)
    if text_block is None:
        raise RuntimeError(f"LLM response had no text block (got: {[getattr(b, 'type', b) for b in msg.content]})")
    return _clean(text_block.text)
