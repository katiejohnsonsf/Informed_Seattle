"""Alignment rubric and prompt management.

rubric.json  — evolving quality rubric with per-dimension rules derived from human
corrections. prompts.json — versioned prompt templates for each summarization section.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

_DATA_DIR = Path(__file__).parent / "data"
_RUBRIC_PATH = _DATA_DIR / "rubric.json"
_PROMPTS_PATH = _DATA_DIR / "prompts.json"

RUBRIC_DIMENSIONS = [
    "headline_accuracy",
    "proposed_intent_fidelity",
    "final_text_fidelity",
    "amendment_accuracy",
    "accessibility",
    "neutrality",
]


def get_rubric() -> dict:
    with open(_RUBRIC_PATH) as f:
        return json.load(f)


def save_rubric(rubric: dict) -> None:
    rubric["updated_at"] = str(date.today())
    with open(_RUBRIC_PATH, "w") as f:
        json.dump(rubric, f, indent=2)
    print(f"Rubric v{rubric.get('version')} saved.")


def load_prompts() -> dict:
    if not _PROMPTS_PATH.exists():
        return {"version": 1, "prompts": {}}
    with open(_PROMPTS_PATH) as f:
        return json.load(f)


def get_prompt(name: str) -> dict | None:
    """Return prompt config dict (template, max_new_tokens, temperature) or None."""
    data = load_prompts()
    return data.get("prompts", {}).get(name)


def save_prompts(prompts_data: dict) -> None:
    prompts_data["updated_at"] = str(date.today())
    with open(_PROMPTS_PATH, "w") as f:
        json.dump(prompts_data, f, indent=2)
    print(f"Prompts v{prompts_data.get('version')} saved.")
