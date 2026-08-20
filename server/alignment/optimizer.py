"""OPRO-style prompt optimizer.

Uses Claude as a meta-optimizer: given the current prompt template, the rubric
rules it should satisfy, and known issues from human corrections, it generates
an improved prompt. The improved template is saved to prompts.json.

olmo_legislation.py checks prompts.json first via _get_prompt(), so the
optimizer's changes take effect on the next summarization run.

Usage (via management command):
    python manage.py optimize_prompts
    python manage.py optimize_prompts --dry-run
    python manage.py optimize_prompts --keys original_proposal headline
"""

from __future__ import annotations

import sys
from collections import defaultdict

from .rubric import get_rubric, load_prompts, save_prompts

# Maps each prompt key to the rubric dimensions it most affects.
_KEY_TO_DIMS: dict[str, list[str]] = {
    "original_proposal": ["proposed_intent_fidelity"],
    "final_text": ["final_text_fidelity"],
    "differences": ["amendment_accuracy"],
    "headline": ["headline_accuracy"],
    "simple_summary": [
        "proposed_intent_fidelity",
        "final_text_fidelity",
        "accessibility",
    ],
}

ALL_PROMPT_KEYS = list(_KEY_TO_DIMS)


def _optimize_one(
    client,
    model: str,
    key: str,
    current_template: str,
    rubric_rules: list[str],
    example_issues: list[str],
) -> str | None:
    """Ask Claude to improve a single prompt template. Returns improved text or None."""
    rules_text = (
        "\n".join(f"- {r}" for r in rubric_rules) if rubric_rules else "(none yet)"
    )
    issues_text = (
        "\n".join(f"- {i}" for i in example_issues)
        if example_issues
        else "(none reported)"
    )

    meta_prompt = (
        f"You are optimizing a prompt template for an AI legislative summarizer "
        f"(Informed Seattle project). The prompt generates the '{key}' section "
        f"of Seattle City Council bill summaries.\n\n"
        f"CURRENT PROMPT TEMPLATE:\n```\n{current_template}\n```\n\n"
        f"RUBRIC RULES THIS SECTION MUST SATISFY:\n{rules_text}\n\n"
        f"KNOWN ISSUES FROM HUMAN REVIEWERS:\n{issues_text}\n\n"
        f"Rewrite the prompt template to better satisfy the rubric rules and fix "
        f"the known issues. Requirements:\n"
        f"- Keep the same placeholder variables (e.g. {{title}}, {{text_excerpt}})\n"
        f"- Do not make it significantly longer than the original\n"
        f"- Make the instructions specific and actionable\n\n"
        f"Return ONLY the improved prompt text, with no explanation or preamble."
    )

    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": meta_prompt}],
        )
        return response.content[0].text.strip()
    except Exception as exc:
        print(f"  [error] Optimization failed for '{key}': {exc}", file=sys.stderr)
        return None


def run_optimization(
    client,
    model: str,
    corrections_by_dim: dict[str, list],
    prompt_keys: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, str]:
    """
    Run optimization for each prompt key. Saves improved templates to prompts.json.

    Args:
        corrections_by_dim: {dimension: [SummaryCorrection instances]}
        prompt_keys: subset of ALL_PROMPT_KEYS to optimize; None means all
        dry_run: print proposed templates but do not save

    Returns:
        {prompt_key: improved_template}
    """
    if prompt_keys is None:
        prompt_keys = ALL_PROMPT_KEYS

    rubric = get_rubric()
    prompts_data = load_prompts()
    improved: dict[str, str] = {}

    for key in prompt_keys:
        current_cfg = prompts_data.get("prompts", {}).get(key)
        if current_cfg is None:
            print(f"  [skip] No config for '{key}' in prompts.json", file=sys.stderr)
            continue

        current_template = current_cfg.get("template", "")
        if not current_template:
            print(f"  [skip] Empty template for '{key}'", file=sys.stderr)
            continue

        relevant_dims = _KEY_TO_DIMS.get(key, [])
        rubric_rules: list[str] = []
        for dim in relevant_dims:
            rubric_rules.extend(
                rubric.get("dimensions", {}).get(dim, {}).get("rules", [])
            )

        issues: list[str] = []
        for dim in relevant_dims:
            for c in corrections_by_dim.get(dim, []):
                if c.issue:
                    issues.append(c.issue)

        if not rubric_rules and not issues:
            print(
                f"  [skip] No rubric rules or issues for '{key}' — nothing to optimize",
                file=sys.stderr,
            )
            continue

        print(
            f"  [optimize] {key} ({len(rubric_rules)} rules, {len(issues)} issues)",
            file=sys.stderr,
        )
        new_template = _optimize_one(
            client, model, key, current_template, rubric_rules, issues[:10]
        )
        if new_template:
            improved[key] = new_template
            if dry_run:
                print(f"\n--- IMPROVED '{key}' ---\n{new_template}\n", file=sys.stderr)

    if not dry_run and improved:
        for key, template in improved.items():
            entry = prompts_data.setdefault("prompts", {}).setdefault(key, {})
            prev = entry.get("template", "")
            if prev:
                entry["previous_template"] = prev
            entry["template"] = template
        prompts_data["version"] = prompts_data.get("version", 1) + 1
        save_prompts(prompts_data)
        print(f"Saved {len(improved)} improved prompt(s).", file=sys.stderr)

    return improved
