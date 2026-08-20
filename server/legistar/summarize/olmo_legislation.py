"""
OLMo-based legislation summarization with structured amendment tracking.

Council Bills get a 4-section structured summary:
1. What was originally proposed
2. Amendments and votes (with council member details)
3. What the final text does
4. What changed from the original

Other legislation types (Appointments, Information Items) get a simple summary.
"""

import typing as t
from dataclasses import dataclass

from server.documents.summarize import (
    SummarizationResult,
    SummarizationError,
    SummarizationSuccess,
)


def _get_prompt_template(key: str, default: str) -> str:
    """Return the prompt template from prompts.json if present, else the default."""
    try:
        from server.alignment.rubric import get_prompt

        cfg = get_prompt(key)
        if cfg and cfg.get("template"):
            return cfg["template"]
    except Exception:
        pass
    return default


@dataclass
class LegislationAnalysis:
    """Comprehensive analysis of a piece of legislation."""

    original_proposal: str
    """The original text or description of the proposed legislation."""

    amendments: list[dict[str, t.Any]]
    """List of amendments with their details and votes."""

    final_text: str
    """The final text of the legislation after all amendments."""

    final_action: str | None
    """The final action taken (passed, failed, etc.)."""

    votes_summary: list[dict[str, t.Any]]
    """Summary of votes for each action."""


def analyze_legislation_history(
    legislation_data: dict[t.Any, t.Any],
    action_details: list[dict[t.Any, t.Any]] | None = None,
) -> LegislationAnalysis:
    """
    Analyze the full history of a piece of legislation.

    Args:
        legislation_data: The crawl data for the legislation
        action_details: Optional list of action detail crawl data with votes

    Returns:
        LegislationAnalysis with comprehensive information
    """
    rows = legislation_data.get("rows", [])
    full_text = legislation_data.get("full_text", "")

    # Extract original proposal (first version or initial text)
    original_proposal = full_text if full_text else legislation_data.get("title", "")

    # Track amendments through version history
    amendments = []
    votes_summary = []

    # Group actions by version to track amendments
    version_actions = {}
    for row in rows:
        version = row.get("version", 1)
        if version not in version_actions:
            version_actions[version] = []
        version_actions[version].append(row)

    # Process each version to identify amendments
    for version in sorted(version_actions.keys()):
        actions = version_actions[version]
        for action_data in actions:
            action = action_data.get("action") or ""
            result = action_data.get("result") or ""
            action_by = action_data.get("action_by") or ""
            date = action_data.get("date", "")

            # Identify amendment-related actions
            if any(
                keyword in action.lower()
                for keyword in [
                    "amend",
                    "substitute",
                    "revised",
                    "modified",
                    "changed",
                ]
            ):
                amendments.append(
                    {
                        "version": version,
                        "action": action,
                        "action_by": action_by,
                        "result": result,
                        "date": str(date),
                    }
                )

            # Track votes
            if result and result.strip():
                votes_summary.append(
                    {
                        "version": version,
                        "action": action,
                        "result": result,
                        "date": str(date),
                        "action_by": action_by,
                    }
                )

    # Determine final action
    final_action = None
    if rows:
        last_row = rows[-1]
        final_action = last_row.get("action", "")

    return LegislationAnalysis(
        original_proposal=original_proposal,
        amendments=amendments,
        final_text=full_text,
        final_action=final_action,
        votes_summary=votes_summary,
    )


# ---------------------------------------------------------------------
# Section helpers for structured Council Bill summaries
# ---------------------------------------------------------------------


_DEFAULT_ORIGINAL_PROPOSAL = (
    "Summarize in 2-3 sentences what this Seattle City Council bill originally proposed:\n\n"
    "Title: {title}\n\nBill text (excerpt):\n{text_excerpt}\n\nWhat was originally proposed:"
)


def _summarize_original_proposal(olmo, title: str, full_text: str) -> str:
    """Summarize what was originally proposed (LLM call)."""
    text_excerpt = full_text[:1500] if full_text else title
    template = _get_prompt_template("original_proposal", _DEFAULT_ORIGINAL_PROPOSAL)
    prompt = template.format(title=title, text_excerpt=text_excerpt)
    return olmo.generate(prompt, max_new_tokens=200, temperature=0.3)


def _format_amendments_and_votes(
    analysis: LegislationAnalysis,
    action_details: list[dict[str, t.Any]] | None,
    amendment_docs: list[dict[str, t.Any]] | None = None,
) -> str:
    """Format amendments and votes programmatically from structured data."""
    lines: list[str] = []

    # Format amendments — prefer structured summaries over raw action names
    if amendment_docs:
        for amend in amendment_docs:
            number = amend.get("number", "")
            label = f"Amendment {number}" if number else "Amendment"
            lines.append(label)
            summary = amend.get("summary", "")
            if summary:
                lines.append(f"  {summary}")
            sponsors = amend.get("sponsors", "")
            if sponsors:
                lines.append(f"  Sponsored by: {sponsors}")
            result = amend.get("result", "")
            if result:
                lines.append(f"  Result: {result}")
            lines.append("")
    elif analysis.amendments:
        for i, amendment in enumerate(analysis.amendments, 1):
            lines.append(
                f"Amendment {i}: {amendment['action']} "
                f"(by {amendment['action_by']}, {amendment['date']})"
            )
            if amendment["result"]:
                lines.append(f"  Result: {amendment['result']}")
    else:
        lines.append("No amendments have been proposed to this legislation.")

    lines.append("")

    # Format vote history with individual council member votes
    if analysis.votes_summary:
        lines.append("Vote History:")
        for vote_info in analysis.votes_summary:
            lines.append(
                f"- {vote_info['action_by']}: {vote_info['action']} "
                f"({vote_info['result']}, {vote_info['date']})"
            )

        # Individual council member votes from fetched action details
        if action_details:
            for detail in action_details:
                action_name = detail.get("action", "Vote")
                result = detail.get("result", "")
                rows = detail.get("rows", [])
                if rows:
                    label = f"{action_name} ({result})" if result else action_name
                    lines.append(f"\n{label}:")
                    for row in rows:
                        person = row.get("person", {})
                        person_name = (
                            person.get("name", "Unknown")
                            if isinstance(person, dict)
                            else str(person)
                        )
                        vote = row.get("vote", "Unknown")
                        lines.append(f"  - {person_name}: {vote}")
    else:
        lines.append("No votes have been recorded yet.")

    return "\n".join(lines)


_DEFAULT_FINAL_TEXT = (
    "Summarize in 3-4 sentences what this Seattle City Council bill does in its current form:\n\n"
    "{context}\n\nWhat the legislation does:"
)


def _summarize_final_text(
    olmo, title: str, full_text: str, doc_summaries: list[str]
) -> str:
    """Summarize what the final text does (LLM call)."""
    context = f"Title: {title}\n"
    if doc_summaries:
        context += "Related document summaries:\n" + "\n".join(
            f"- {s[:300]}" for s in doc_summaries[:5]
        )
    if full_text:
        context += f"\n\nBill text (excerpt):\n{full_text[:1200]}"

    template = _get_prompt_template("final_text", _DEFAULT_FINAL_TEXT)
    prompt = template.format(context=context)
    return olmo.generate(prompt, max_new_tokens=300, temperature=0.3)


_DEFAULT_DIFFERENCES = (
    "This Seattle City Council bill was amended. Summarize in 2-3 sentences "
    "how the final version differs from the original:\n\n"
    "Title: {title}\n"
    "Original proposal excerpt: {original_excerpt}\n"
    "Amendments made: {amendments_text}\n"
    "Final text excerpt: {final_excerpt}\n\n"
    "Key differences from the original:"
)


def _summarize_differences(olmo, title: str, analysis: LegislationAnalysis) -> str:
    """Summarize differences between original and final (LLM call only if amendments exist)."""
    if not analysis.amendments:
        return (
            "No amendments have been made. The current text is the same"
            " as originally proposed."
        )

    amendments_text = "\n".join(
        f"- {a['action']} by {a['action_by']} ({a['date']})"
        for a in analysis.amendments
    )
    template = _get_prompt_template("differences", _DEFAULT_DIFFERENCES)
    prompt = template.format(
        title=title,
        original_excerpt=analysis.original_proposal[:800],
        amendments_text=amendments_text,
        final_excerpt=(analysis.final_text or "")[:800],
    )
    return olmo.generate(prompt, max_new_tokens=200, temperature=0.3)


# ---------------------------------------------------------------------
# Structured Council Bill summarizer
# ---------------------------------------------------------------------


def summarize_council_bill_structured(
    title: str,
    document_summary_texts: list[str],
    legislation_data: dict[str, t.Any] | None = None,
    action_details: list[dict[str, t.Any]] | None = None,
    amendment_docs: list[dict[str, t.Any]] | None = None,
) -> SummarizationResult:
    """
    Produce a 4-section structured summary for a Council Bill.

    Sections:
    1. WHAT WAS ORIGINALLY PROPOSED
    2. AMENDMENTS AND VOTES
    3. WHAT THE FINAL TEXT DOES
    4. WHAT CHANGED FROM THE ORIGINAL
    """
    from server.lib.olmo_client import get_olmo_client

    if legislation_data is None:
        legislation_data = {}

    try:
        olmo = get_olmo_client()
        analysis = analyze_legislation_history(legislation_data, action_details)

        # Section 1: Original proposal (LLM)
        print("    Generating section 1: Original Proposal...")
        section_1 = _summarize_original_proposal(
            olmo, title, analysis.original_proposal
        )

        # Section 2: Amendments and votes (programmatic)
        print("    Generating section 2: Amendments and Votes...")
        section_2 = _format_amendments_and_votes(
            analysis, action_details, amendment_docs
        )

        # Section 3: Final text (LLM)
        print("    Generating section 3: Final Text...")
        section_3 = _summarize_final_text(
            olmo, title, analysis.final_text, document_summary_texts
        )

        # Section 4: Differences (LLM only if amendments exist)
        print("    Generating section 4: Changes from Original...")
        section_4 = _summarize_differences(olmo, title, analysis)

        # Assemble body with section headers
        body = (
            f"WHAT WAS ORIGINALLY PROPOSED\n{section_1}\n\n"
            f"AMENDMENTS AND VOTES\n{section_2}\n\n"
            f"WHAT THE FINAL TEXT DOES\n{section_3}\n\n"
            f"WHAT CHANGED FROM THE ORIGINAL\n{section_4}"
        )

        # Headline (short LLM call)
        print("    Generating headline...")
        _default_headline = (
            "Create a concise headline (under 15 words) for: {title}\nHeadline:"
        )
        headline_template = _get_prompt_template("headline", _default_headline)
        headline_prompt = headline_template.format(title=title)
        headline = olmo.generate(headline_prompt, max_new_tokens=30, temperature=0.3)

        context_text = (
            f"Title: {title}\n"
            f"Full text available: {'yes' if analysis.final_text else 'no'}\n"
            f"Amendments: {len(analysis.amendments)}\n"
            f"Votes: {len(analysis.votes_summary)}"
        )

        return SummarizationSuccess(
            original_text=context_text,
            body=body,
            headline=headline.strip(),
            chunks=(context_text,),
            chunk_summaries=(body,),
        )

    except Exception as e:
        import traceback

        print(f"  ERROR in Council Bill summarization: {e}")
        traceback.print_exc()
        return SummarizationError(
            original_text=title,
            message=f"Council Bill summarization failed: {str(e)}",
        )


# ---------------------------------------------------------------------
# Simple summarizer for non-Council Bill legislation
# ---------------------------------------------------------------------


def summarize_legislation_olmo_concise(
    title: str,
    document_summary_texts: list[str],
    legislation_data: dict[str, t.Any] | None = None,
    action_details: list[dict[str, t.Any]] | None = None,
) -> SummarizationResult:
    """
    Simple summary for non-Council Bill legislation (Appointments, Info Items).
    """
    from server.lib.olmo_client import get_olmo_client

    try:
        context = f"Title: {title}\n\nDocument Summaries:\n"
        context += "\n".join(
            f"{i}. {summary}" for i, summary in enumerate(document_summary_texts, 1)
        )

        _default_simple = (
            "Summarize this Seattle City Council legislation:\n\n{context}\n\n"
            "Provide a comprehensive summary that explains what this legislation does."
        )
        _default_simple_headline = (
            "Create a brief headline (under 15 words) for: {title}"
        )

        olmo = get_olmo_client()
        body = olmo.generate(
            _get_prompt_template("simple_summary", _default_simple).format(
                context=context
            ),
            max_new_tokens=512,
            temperature=0.3,
        )
        headline = olmo.generate(
            _get_prompt_template("headline", _default_simple_headline).format(
                title=title
            ),
            max_new_tokens=30,
            temperature=0.3,
        )

        return SummarizationSuccess(
            original_text=context,
            body=body,
            headline=headline.strip(),
            chunks=(context,),
            chunk_summaries=(body,),
        )
    except Exception as e:
        import traceback

        print(f"  ERROR in legislation summarization: {e}")
        traceback.print_exc()
        return SummarizationError(
            original_text=title,
            message=f"Legislation summarization failed: {str(e)}",
        )
