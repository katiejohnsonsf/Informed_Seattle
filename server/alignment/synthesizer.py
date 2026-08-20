"""Episodic rule synthesizer.

Clusters human SummaryCorrection records by rubric dimension, calls Claude to
derive new concise rules, and appends them to rubric.json. Each synthesis
increments the rubric version so changes are tracked in git history.

Usage (via management command):
    python manage.py synthesize_rules
    python manage.py synthesize_rules --dry-run
    python manage.py synthesize_rules --all   # include already-synthesized
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

from .rubric import get_rubric, save_rubric


def synthesize(
    client,
    model: str,
    corrections: list,
    dry_run: bool = False,
) -> dict[str, list[str]]:
    """
    Derive new rubric rules from corrections and write to rubric.json.

    Args:
        corrections: list of SummaryCorrection model instances
        dry_run: if True, prints proposed rules but does not save

    Returns:
        {dimension: [new_rule_strings]}
    """
    by_dim: dict[str, list] = defaultdict(list)
    for c in corrections:
        by_dim[c.dimension].append(c)

    if not by_dim:
        print("No corrections to synthesize.", file=sys.stderr)
        return {}

    rubric = get_rubric()
    new_rules_by_dim: dict[str, list[str]] = {}

    for dim, dim_corrections in by_dim.items():
        print(
            f"  [synthesize] {dim}: {len(dim_corrections)} correction(s)",
            file=sys.stderr,
        )

        correction_text = "\n\n".join(
            f"Issue: {c.issue}\nCorrection: {c.correction or '(none provided)'}"
            for c in dim_corrections
        )

        existing_rules = rubric.get("dimensions", {}).get(dim, {}).get("rules", [])
        existing_text = (
            "\n".join(f"- {r}" for r in existing_rules)
            if existing_rules
            else "(none yet)"
        )

        prompt = (
            f"You are helping improve an AI legislative summarizer for the "
            f"Informed Seattle project. Human reviewers have flagged issues in "
            f"AI-generated summaries under the '{dim}' quality dimension.\n\n"
            f"EXISTING RULES FOR THIS DIMENSION:\n{existing_text}\n\n"
            f"HUMAN CORRECTIONS (issue + suggested fix):\n{correction_text}\n\n"
            f"Based on these corrections, derive 1-5 new concise rules that the "
            f"summarizer should follow for '{dim}'. Rules must:\n"
            f"- Be actionable and specific (not vague like 'be accurate')\n"
            f"- Not duplicate existing rules\n"
            f"- Each be one sentence\n\n"
            f"Return ONLY a JSON array of rule strings, e.g. "
            f'["Rule 1.", "Rule 2."]'
        )

        try:
            response = client.messages.create(
                model=model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start == -1 or end == 0:
                print(
                    f"    [warn] Could not parse rule array for {dim}", file=sys.stderr
                )
                continue
            new_rules: list[str] = json.loads(raw[start:end])
            new_rules_by_dim[dim] = new_rules
            for r in new_rules:
                print(f"    + {r}", file=sys.stderr)
        except Exception as exc:
            print(f"    [error] {exc}", file=sys.stderr)
            continue

    if dry_run:
        print("[dry-run] Rubric not updated.", file=sys.stderr)
        return new_rules_by_dim

    if new_rules_by_dim:
        rubric["version"] = rubric.get("version", 1) + 1
        for dim, new_rules in new_rules_by_dim.items():
            rubric.setdefault("dimensions", {}).setdefault(
                dim, {"description": "", "rules": []}
            )["rules"].extend(new_rules)
        save_rubric(rubric)

    return new_rules_by_dim
