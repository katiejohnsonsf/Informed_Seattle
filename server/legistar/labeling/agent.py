"""
Gemma-powered labeling agent for the Council Bill taxonomy.

One call per bill produces all four facets (triage, topic, groups, stakes).
Stakes are scoped to the community's declared constituencies so the output
is community-specific rather than a generic population scan.
"""

import json
import re
import typing as t

from server.legistar.label_schema import (
    DIRECTNESS_CHOICES,
    POLICY_AREAS,
    RECORD_CLASSES,
    RELATIONS,
    STATUTORY_POPULATION_DEFINITIONS,
    STATUTORY_POPULATIONS,
    VALENCES,
)

_POLICY_AREAS_STR = "\n  ".join(POLICY_AREAS)
_STATUTORY_POPS_STR = "\n  ".join(
    f"{slug} — {STATUTORY_POPULATION_DEFINITIONS[slug]}"
    for slug in STATUTORY_POPULATIONS
)

_LABEL_PROMPT = """\
You are classifying a Seattle City Council bill into a structured taxonomy.
Return ONLY a valid JSON object — no explanation, no markdown fences, no prose.

### Bill
Record: {record_no}
Title: {title}
Type: {bill_type}

### Summary
{summary}

### Community context
{community_context}

### Constituencies to assess
Only include stakes entries for groups genuinely affected (confidence ≥ 0.4).
Constituencies: {constituencies}

### Legally recognized populations
Each has a precise Census/ACS or legal definition below. Match a population
only if the bill's actual provisions fit that definition — not because the
bill's subject sounds thematically related.
  {statutory_pops}

### Output schema — return exactly this JSON shape, no extra keys:
{{
  "record_class": "<one of: {record_classes}>",
  "resident_salient": <true or false>,
  "policy_area": "<one of:\n  {policy_areas}>",
  "statutory_populations": ["<zero or more slugs (the part before the — ) from the Legally recognized populations list above whose definition the bill actually fits>"],
  "stakes": [
    {{
      "group": "<constituency name from the list above>",
      "relation": "<one of: {relations}>",
      "valence": "<one of: {valences}>",
      "directness": "<one of: {directness}>",
      "confidence": <0.0–1.0 float>
    }}
  ]
}}"""

_FALLBACK_LABEL: dict[str, t.Any] = {
    "record_class": "other_administrative",
    "resident_salient": False,
    "policy_area": "governance-elections-and-ethics",
    "statutory_populations": [],
    "stakes": [],
}


def _extract_json(text: str) -> dict[str, t.Any] | None:
    """Try several strategies to extract a JSON object from model output."""
    text = text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown code fences
    fenced = re.search(r"```(?:json)?\s*(\{[^`]*\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass

    # Strategy 3: find the outermost {...} block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _validate_label(raw: dict[str, t.Any]) -> dict[str, t.Any]:
    """Coerce and bound-check model output against the schema."""
    label: dict[str, t.Any] = {}

    label["record_class"] = (
        raw.get("record_class", "other_administrative")
        if raw.get("record_class") in RECORD_CLASSES
        else "other_administrative"
    )

    label["resident_salient"] = bool(raw.get("resident_salient", False))

    label["policy_area"] = (
        raw.get("policy_area", "governance-elections-and-ethics")
        if raw.get("policy_area") in POLICY_AREAS
        else "governance-elections-and-ethics"
    )

    # statutory_populations — filter to known values only
    pops = raw.get("statutory_populations", [])
    label["statutory_populations"] = [
        p for p in pops if p in STATUTORY_POPULATIONS
    ]

    # stakes — validate each entry
    stakes_raw = raw.get("stakes", [])
    stakes = []
    for s in stakes_raw:
        if not isinstance(s, dict):
            continue
        group = str(s.get("group", "")).strip()
        relation = s.get("relation", "")
        valence = s.get("valence", "")
        directness = s.get("directness", "")
        try:
            confidence = float(s.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.5

        if (
            group
            and relation in RELATIONS
            and valence in VALENCES
            and directness in DIRECTNESS_CHOICES
            and confidence >= 0.4
        ):
            stakes.append(
                {
                    "group": group,
                    "relation": relation,
                    "valence": valence,
                    "directness": directness,
                    "confidence": confidence,
                }
            )
    label["stakes"] = stakes

    return label


def label_legislation(
    legislation,
    community_profile=None,
    constituencies: list[str] | None = None,
) -> dict[str, t.Any]:
    """
    Run the full labeling pass for a single piece of legislation.

    Args:
        legislation: Legislation model instance.
        community_profile: CommunityProfile model instance (optional).
            When provided, its constituencies and prompt_context shape the
            stakes assessment so results are community-specific.
        constituencies: Explicit constituency list override. Useful when
            calling without a saved CommunityProfile.

    Returns:
        Dict matching the label schema (facets 0-3, minus participation_window
        which is added by the caller from derive_participation_window).
    """
    from server.lib.olmo_client import get_olmo_client

    # Build constituency list
    if constituencies is not None:
        active_constituencies = constituencies
    elif community_profile is not None:
        active_constituencies = list(community_profile.constituencies or [])
    else:
        # Default: use a compact representative set when no community is specified
        from server.legistar.label_schema import DEFAULT_CONSTITUENCIES

        active_constituencies = [
            t
            for terms in DEFAULT_CONSTITUENCIES.values()
            for t in terms
        ]

    # Build community context string
    if community_profile is not None:
        community_context = (
            f"Community: {community_profile.name}\n"
            f"{community_profile.prompt_context or ''}"
        ).strip()
    else:
        community_context = (
            "General Seattle resident — no specific community focus. "
            "Assess stakes broadly across all listed constituencies."
        )

    # Gather the bill's summary text (prefer structured body, fall back to title)
    summary_text = legislation.title
    try:
        leg_summary = legislation.summaries.filter(style="what_changed").first()
        if leg_summary and leg_summary.body:
            summary_text = leg_summary.body[:2000]
    except Exception:
        pass

    # Build the prompt
    prompt = _LABEL_PROMPT.format(
        record_no=legislation.record_no,
        title=legislation.title,
        bill_type=legislation.type,
        summary=summary_text,
        community_context=community_context,
        constituencies=(
            ", ".join(active_constituencies)
            if active_constituencies
            else "general public"
        ),
        record_classes="|".join(RECORD_CLASSES),
        policy_areas=_POLICY_AREAS_STR,
        statutory_pops=_STATUTORY_POPS_STR,
        relations="|".join(RELATIONS),
        valences="|".join(VALENCES),
        directness="|".join(DIRECTNESS_CHOICES),
    )

    try:
        client = get_olmo_client()
        raw_response = client.generate(
            prompt,
            max_new_tokens=800,
            temperature=0.1,
        )
        parsed = _extract_json(raw_response)
        if parsed is None:
            print("    ⚠ Could not parse JSON from model response; using fallback")
            return dict(_FALLBACK_LABEL)
        return _validate_label(parsed)
    except Exception as e:
        print(f"    ✗ Labeling error: {e}")
        return dict(_FALLBACK_LABEL)
