"""
Management command: evaluate-summaries

Evaluates OLMo-generated LegislationSummary records by prompting Claude to
score each summary against a structured rubric.

For each LegislationSummary, Claude is given:
  - The source bill text (from the summary's original_text field)
  - The OLMo-generated summary (the body field, with HTML stripped)

Claude scores six rubric dimensions on completeness (1-5) and faithfulness (1-5):
  - headline_accuracy
  - proposed_intent_fidelity
  - final_text_fidelity
  - amendment_accuracy
  - accessibility
  - neutrality

Results are stored in a SummaryEvaluation record (one per LegislationSummary).
"""

import re
import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from server.legistar.models import LegislationSummary, SummaryEvaluation

_COUNCIL_BILL_KIND = "Council Bill"

RUBRIC_DIMENSIONS = [
    "headline_accuracy",
    "proposed_intent_fidelity",
    "final_text_fidelity",
    "amendment_accuracy",
    "accessibility",
    "neutrality",
]

RUBRIC_DESCRIPTIONS = {
    "headline_accuracy": (
        "Does the headline faithfully represent the bill's core change? "
        "Is it accurate and not misleading?"
    ),
    "proposed_intent_fidelity": (
        "Does the 'What Was Originally Proposed' section accurately reflect "
        "the introduced bill text? Are important details present?"
    ),
    "final_text_fidelity": (
        "Does the 'What The Final Text Does' section match the enacted or "
        "amended legislative language? Is it accurate to the final version?"
    ),
    "amendment_accuracy": (
        "Are amendments described accurately? Is the vote breakdown per council "
        "member correct and complete? Are any amendments or votes omitted or "
        "mischaracterized?"
    ),
    "accessibility": (
        "Is the language plain enough for a non-lawyer Seattle resident? "
        "Are technical terms explained? Is the structure easy to follow?"
    ),
    "neutrality": (
        "Is the summary free of editorial framing or political spin? "
        "Does it present the legislation's content without advocacy or bias?"
    ),
}

_TOOL_DEFINITION = {
    "name": "submit_evaluation",
    "description": (
        "Submit structured rubric scores evaluating a legislative bill summary. "
        "Score each dimension 1 (very poor) to 5 (very good) on two axes: "
        "completeness (nothing important omitted) and faithfulness (nothing stated "
        "that isn't in the source). Include a brief reasoning string for each."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            dim: {
                "type": "object",
                "properties": {
                    "completeness": {
                        "type": "integer",
                        "description": (
                            "Score 1-5: how complete is this dimension "
                            "(nothing omitted)?"
                        ),
                    },
                    "faithfulness": {
                        "type": "integer",
                        "description": (
                            "Score 1-5: how faithful is this dimension "
                            "(no hallucination)?"
                        ),
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "1-2 sentence explanation of the scores.",
                    },
                },
                "required": ["completeness", "faithfulness", "reasoning"],
                "additionalProperties": False,
            }
            for dim in RUBRIC_DIMENSIONS
        },
        "required": RUBRIC_DIMENSIONS,
        "additionalProperties": False,
    },
}

_SYSTEM_PROMPT = """\
You are a neutral legislative summary evaluator for the Informed Seattle project.

You will be given:
1. SOURCE TEXT — the original Seattle City Council bill text
2. GENERATED SUMMARY — an AI-generated plain-language summary of that bill

Your task is to evaluate the summary's quality across six dimensions using the
submit_evaluation tool. Score each dimension on two axes (1 = very poor, 5 = very good):
- completeness: important content is not omitted
- faithfulness: nothing is stated that is not supported by the source

Be precise and honest. A score of 3 means adequate but with notable gaps or issues.
Score 5 only when the dimension is handled exceptionally well."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    return re.sub(r"<[^>]+>", " ", text).strip()


def _build_user_message(source_text: str, summary_body: str, headline: str) -> str:
    """Build the user message containing source text and summary."""
    source_excerpt = source_text[:8000] if source_text else "(no source text available)"
    summary_clean = _strip_html(summary_body)
    return (
        f"## SOURCE TEXT\n\n{source_excerpt}\n\n"
        f"---\n\n"
        f"## GENERATED SUMMARY\n\n"
        f"**Headline:** {headline}\n\n"
        f"{summary_clean}\n\n"
        f"---\n\n"
        f"Please evaluate the generated summary against the source text using "
        f"the submit_evaluation tool."
    )


def _call_claude(
    client, model: str, source_text: str, summary_body: str, headline: str
) -> dict:
    """
    Call Claude with the evaluation prompt and return the parsed tool input.

    Uses tool_choice to force the submit_evaluation tool.
    """
    user_message = _build_user_message(source_text, summary_body, headline)

    response = client.messages.create(
        model=model,
        max_tokens=2048,
        system=_SYSTEM_PROMPT,
        tools=[_TOOL_DEFINITION],
        tool_choice={"type": "tool", "name": "submit_evaluation"},
        messages=[{"role": "user", "content": user_message}],
    )

    # Extract the tool use block
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_evaluation":
            return block.input

    raise ValueError("Claude did not return a submit_evaluation tool call")


def _compute_averages(scores: dict) -> tuple[float | None, float | None]:
    """Return (mean_completeness, mean_faithfulness) across all rubric dimensions."""
    completeness_vals = []
    faithfulness_vals = []
    for dim in RUBRIC_DIMENSIONS:
        dim_scores = scores.get(dim, {})
        if "completeness" in dim_scores:
            completeness_vals.append(dim_scores["completeness"])
        if "faithfulness" in dim_scores:
            faithfulness_vals.append(dim_scores["faithfulness"])

    avg_c = (
        sum(completeness_vals) / len(completeness_vals) if completeness_vals else None
    )
    avg_f = (
        sum(faithfulness_vals) / len(faithfulness_vals) if faithfulness_vals else None
    )
    return avg_c, avg_f


def _process_summary(legislation_summary, force: bool, client, model: str) -> None:
    """Evaluate a single LegislationSummary and create/update a SummaryEvaluation."""
    if not force and hasattr(legislation_summary, "evaluation"):
        print(
            f"  [skip] Already evaluated: {legislation_summary.legislation.record_no}",
            file=sys.stderr,
        )
        return

    source_text = legislation_summary.original_text or ""
    summary_body = legislation_summary.body or ""
    headline = legislation_summary.headline or ""

    if not summary_body or summary_body == "(SUMMARIZATION FAILED)":
        print(
            f"  [skip] No valid summary for: "
            f"{legislation_summary.legislation.record_no}",
            file=sys.stderr,
        )
        return

    print(
        f"  [evaluate] {legislation_summary.legislation.record_no}: {headline[:60]}",
        file=sys.stderr,
    )

    try:
        scores = _call_claude(client, model, source_text, summary_body, headline)
    except Exception as exc:
        print(f"    [error] Claude call failed: {exc}", file=sys.stderr)
        return

    overall_completeness, overall_faithfulness = _compute_averages(scores)

    SummaryEvaluation.objects.update_or_create(
        legislation_summary=legislation_summary,
        defaults={
            "scores": scores,
            "overall_completeness": overall_completeness,
            "overall_faithfulness": overall_faithfulness,
            "claude_model": model,
        },
    )
    print(
        f"    [saved] completeness={overall_completeness:.2f}, "
        f"faithfulness={overall_faithfulness:.2f}",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------


class Command(BaseCommand):
    help = (
        "Evaluate OLMo-generated LegislationSummary records using Claude as a "
        "rubric-based quality scorer. Stores results in SummaryEvaluation."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-evaluate even if a SummaryEvaluation already exists.",
        )
        parser.add_argument(
            "--pk",
            type=int,
            default=None,
            help="Evaluate only the LegislationSummary with this primary key.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Evaluate only the N most recently created LegislationSummary "
                "records for Council Bills (ordered by id descending)."
            ),
        )

    def handle(self, *args, **options):
        force = options["force"]
        pk = options["pk"]
        limit = options["limit"]

        if pk is not None:
            summaries = LegislationSummary.objects.filter(pk=pk).select_related(
                "legislation"
            )
        else:
            summaries = (
                LegislationSummary.objects.filter(
                    legislation__type__icontains=_COUNCIL_BILL_KIND
                )
                .select_related("legislation")
                .order_by("-id")
            )
            if limit is not None:
                summaries = summaries[:limit]

        total = summaries.count()
        self.stderr.write(f"Evaluating {total} LegislationSummary record(s)...")

        # Import client lazily (avoids loading anthropic at module import time)
        from server.lib.anthropic_client import get_anthropic_client

        client = get_anthropic_client()
        model = getattr(settings, "ANTHROPIC_MODEL", "claude-opus-4-6")

        self.stderr.write(f"Using Claude model: {model}")

        for i, summary in enumerate(summaries.iterator(), start=1):
            self.stderr.write(
                f"[{i}/{total}] {summary.legislation.record_no}: "
                f"{summary.legislation.truncated_title}"
            )
            try:
                _process_summary(summary, force=force, client=client, model=model)
            except Exception as exc:
                self.stderr.write(f"  [error] {exc}")

        self.stderr.write("Done.")
