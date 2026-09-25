"""
Generates plain-language, per-stakeholder-group impact descriptions for a
Council Bill's already-determined "stakes" (see label_schema.py facet 3 and
labeling/agent.py). One call per bill, covering every displayed stake
(CBLabel.top_stakes, i.e. up to 5) at once — the model already has the
bill's full context loaded once, which keeps its reasoning about a bill's
various affected groups internally consistent within a single pass, and
costs far less than one call per (bill, group) pair.

Deliberately a separate pass from the main labeling call rather than an
extra field bolted onto that prompt: a narrow, single-purpose prompt is
easier to keep faithful to the source text, and doesn't compete for
output-token budget with the compact classification schema the main
labeling call already has to produce.
"""

import json
import re
import typing as t

_DESCRIPTION_PROMPT = """\
You are writing a plain-language explanation of how a specific Seattle \
City Council bill affects specific groups of residents, for people who \
are not policy experts.

### Bill
Record: {record_no}
Title: {title}

### What the bill actually does
{summary}

### Groups already assessed as affected by this bill
Each group below already has a relation, valence, directness, and \
confidence score assigned by a prior analysis step. Do not re-assess or \
contradict these — your only job is to explain, in plain language, the \
concrete mechanism in the bill's text that produced each assessment.

{stakes_block}

### Instructions
- Base every description ONLY on the bill text above. Do not add outside \
knowledge, assumptions, or generic claims about what similar bills \
usually do.
- Name the specific requirement, provision, or change in the bill that \
creates the effect. "This bill affects renters" is not acceptable — say \
what specifically changes for them.
- Each description must stay consistent with that group's relation, \
valence, and directness above — do not contradict them.
- Write exactly 1-2 plain-language sentences per group. No hedging \
("may," "could potentially," "is likely to") — state plainly what the \
bill does, based on the text given.
- If the bill text doesn't give enough detail to name a specific \
mechanism for a group, say so honestly with a shorter, more general (but \
still accurate) sentence — never invent specifics that aren't there.

### Output schema — return ONLY this JSON object, no markdown fences, no \
extra keys, one entry per group listed above:
{{
  "descriptions": {{
    "<group-slug>": "<1-2 sentence description>"
  }}
}}"""


def _format_stakes_block(stakes: list[dict[str, t.Any]]) -> str:
    lines = []
    for s in stakes:
        lines.append(
            f"- {s['group']}: relation={s['relation']}, "
            f"valence={s['valence']}, directness={s['directness']}, "
            f"confidence={s['confidence']:.2f}"
        )
    return "\n".join(lines)


def _extract_json(text: str) -> dict[str, t.Any] | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{[^`]*\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def generate_stake_descriptions(
    legislation, stakes: list[dict[str, t.Any]]
) -> dict[str, str]:
    """
    Return {group_slug: description} for the given stakes, generated in a
    single call grounded in the bill's real "what_changed" summary text
    (falls back to the title if no summary exists yet). Returns {} on any
    failure — callers should treat a missing description as "not generated
    yet," not as an error to surface to readers, and should never fabricate
    a placeholder in its place.
    """
    if not stakes:
        return {}

    from server.lib.olmo_client import get_olmo_client

    summary_text = legislation.title
    try:
        leg_summary = legislation.summaries.filter(style="what_changed").first()
        if leg_summary and leg_summary.body:
            summary_text = leg_summary.body[:3000]
    except Exception:
        pass

    prompt = _DESCRIPTION_PROMPT.format(
        record_no=legislation.record_no,
        title=legislation.title,
        summary=summary_text,
        stakes_block=_format_stakes_block(stakes),
    )

    try:
        client = get_olmo_client()
        raw_response = client.generate(prompt, max_new_tokens=1000, temperature=0.1)
        parsed = _extract_json(raw_response)
        if not parsed:
            return {}
        descriptions = parsed.get("descriptions", {})
        if not isinstance(descriptions, dict):
            return {}
        known_groups = {s["group"] for s in stakes}
        return {
            group: text.strip()
            for group, text in descriptions.items()
            if group in known_groups and isinstance(text, str) and text.strip()
        }
    except Exception as e:
        print(f"    ✗ Stake description generation error: {e}")
        return {}
