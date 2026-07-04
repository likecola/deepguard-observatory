"""Uses the Claude API to decide whether a scanned item is genuinely harmful.

Two-tier analysis keeps API costs low:
1. Every candidate is screened with a small model (default: Haiku 4.5).
2. Only items the screen flags as harmful — or is unsure about — are
   re-checked with a stronger model (default: Opus 4.8) before anything
   is treated as harmful.
"""

import json
import os

import anthropic

SCREEN_MODEL = os.environ.get("SCREEN_MODEL", "claude-haiku-4-5")
CONFIRM_MODEL = os.environ.get("CONFIRM_MODEL", "claude-opus-4-8")

# Reddit posts can be arbitrarily long; cap what we send to the API.
MAX_BODY_CHARS = 1500

# Approximate USD per 1M tokens (input, output). Used only for the run summary.
PRICING = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
}

_client = None
_usage = {}  # model -> {"input": int, "output": int}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _record_usage(model: str, usage) -> None:
    entry = _usage.setdefault(model, {"input": 0, "output": 0})
    entry["input"] += usage.input_tokens
    entry["output"] += usage.output_tokens


def usage_summary() -> str:
    """Human-readable token usage and estimated cost for this run."""
    if not _usage:
        return "API usage: none"

    lines = ["API usage this run:"]
    total_cost = 0.0
    for model, tokens in _usage.items():
        in_price, out_price = PRICING.get(model, (0.0, 0.0))
        cost = tokens["input"] / 1e6 * in_price + tokens["output"] / 1e6 * out_price
        total_cost += cost
        lines.append(
            f"  {model}: {tokens['input']} in / {tokens['output']} out"
            f" (~${cost:.4f})"
        )
    lines.append(f"  Estimated total: ~${total_cost:.4f}")
    return "\n".join(lines)


RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_harmful": {"type": "boolean"},
        "category": {
            "type": "string",
            "enum": [
                "nonconsensual_generation_tool",
                "tutorial_or_guide",
                "harmful_model_collection",
                "safety_filter_bypass",
                "research_or_detection",
                "licensed_or_disclaimed",
                "unrelated",
            ],
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasoning": {"type": "string"},
        "recommended_action": {"type": "string"},
    },
    "required": [
        "is_harmful",
        "category",
        "confidence",
        "reasoning",
        "recommended_action",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """You are a content moderation assistant for DeepGuard Observatory, \
a project that monitors public Reddit and GitHub content for tools and content that \
enable non-consensual deepfake / synthetic media (e.g. "nudify" apps, face-swap tools \
targeting real people without consent, tutorials for bypassing safety filters).

Flag as harmful (is_harmful: true) only:
- Tools or models built to generate non-consensual synthetic media of real people
- Tutorials or guides for creating non-consensual deepfakes
- Collections of models or techniques assembled for this purpose
- Explicit methods for bypassing safety filters on generation tools

Do NOT flag:
- Academic deepfake detection research
- Licensed entertainment, or clearly disclaimed satire/parody
- Theoretical security discussion with no working implementation
- Properly licensed or consent-documented projects

Be conservative: if genuinely unsure, prefer is_harmful: false with confidence "low" \
and explain the ambiguity in reasoning."""


def analyze_content(item: dict, model: str) -> dict:
    """Ask Claude whether a scanned item is genuinely harmful deepfake content."""
    body = (item.get("body") or "")[:MAX_BODY_CHARS]
    content = (
        f"Source: {item.get('source', 'unknown')}\n"
        f"Title: {item.get('title', '')}\n"
        f"Body/Description: {body}\n"
        f"URL: {item.get('url', '')}"
    )

    response = _get_client().messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    _record_usage(model, response.usage)

    text = next(block.text for block in response.content if block.type == "text")
    result = json.loads(text)
    result["item"] = item
    result["model"] = model
    return result


def analyze_batch(items: list) -> list:
    """Screen every item cheaply, then confirm flagged/uncertain ones with the strong model."""
    results = []
    for item in items:
        screened = analyze_content(item, SCREEN_MODEL)

        needs_confirmation = screened["is_harmful"] or screened["confidence"] == "low"
        if needs_confirmation and CONFIRM_MODEL != SCREEN_MODEL:
            confirmed = analyze_content(item, CONFIRM_MODEL)
            confirmed["screen_result"] = {
                k: screened[k] for k in ("is_harmful", "category", "confidence")
            }
            results.append(confirmed)
        else:
            results.append(screened)

    return results
