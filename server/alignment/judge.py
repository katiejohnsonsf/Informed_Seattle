"""Constitutional judge using Claude with the evolving rubric.

Wraps evaluate_summaries logic but incorporates per-dimension rules
derived from human corrections (stored in rubric.json).
"""

from __future__ import annotations

import re

from .rubric import get_rubric, RUBRIC_DIMENSIONS


def build_system_prompt() -> str:
    """Build the judge system prompt with current rubric rules injected."""
    rubric = get_rubric()
    dimensions = rubric.get("dimensions", {})

    rules_section = ""
    for dim in RUBRIC_DIMENSIONS:
        rules = dimensions.get(dim, {}).get("rules", [])
        if rules:
            formatted = "\n".join(f"  - {r}" for r in rules)
            rules_section += f"\n{dim.upper().replace('_', ' ')}:\n{formatted}\n"

    base = (
        "You are a neutral legislative summary evaluator for the Informed Seattle project.\n\n"
        "You will be given:\n"
        "1. SOURCE TEXT — the original Seattle City Council bill text\n"
        "2. GENERATED SUMMARY — an AI-generated plain-language summary of that bill\n\n"
        "Your task is to evaluate the summary's quality across six dimensions using the\n"
        "submit_evaluation tool. Score each dimension on two axes (1 = very poor, 5 = very good):\n"
        "- completeness: important content is not omitted\n"
        "- faithfulness: nothing is stated that is not supported by the source\n\n"
        "Be precise and honest. A score of 3 means adequate with notable gaps or issues.\n"
        "Score 5 only when the dimension is handled exceptionally well."
    )

    if rules_section.strip():
        base += (
            "\n\nSPECIFIC RUBRIC RULES (derived from human corrections — "
            "weight violations heavily in scoring):\n" + rules_section
        )

    return base


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def score_summary(
    client,
    model: str,
    source_text: str,
    summary_body: str,
    headline: str,
    tool_definition: dict,
) -> dict:
    """Score a summary using the current rubric. Returns the tool-input dict."""
    from evaluate_summaries import _build_user_message  # noqa: F401 — inline import

    system = build_system_prompt()
    user_msg = (
        f"## SOURCE TEXT\n\n{source_text[:8000] if source_text else '(no source)'}\n\n"
        f"---\n\n"
        f"## GENERATED SUMMARY\n\n"
        f"**Headline:** {headline}\n\n"
        f"{strip_html(summary_body)}\n\n"
        f"---\n\n"
        f"Please evaluate the generated summary against the source text using "
        f"the submit_evaluation tool."
    )

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        tools=[tool_definition],
        tool_choice={"type": "tool", "name": "submit_evaluation"},
        messages=[{"role": "user", "content": user_msg}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_evaluation":
            return block.input

    raise ValueError("Claude did not return a submit_evaluation tool call")
