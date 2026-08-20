"""Staff-only summary review UI. Not included in the distill static build."""

from __future__ import annotations

import re

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .models import LegislationSummary, SummaryCorrection

_COUNCIL_BILL_KIND = "Council Bill"

_SECTION_HEADERS = [
    "WHAT WAS ORIGINALLY PROPOSED",
    "AMENDMENTS AND VOTES",
    "WHAT THE FINAL TEXT DOES",
    "WHAT CHANGED FROM THE ORIGINAL",
]
_SECTION_PATTERN = re.compile(
    "(" + "|".join(re.escape(h) for h in _SECTION_HEADERS) + ")"
)


def _parse_sections(body: str) -> list[dict]:
    """Split body text into labeled sections for display."""
    parts = _SECTION_PATTERN.split(body)
    sections = []
    i = 0
    while i < len(parts):
        chunk = parts[i].strip()
        if chunk in _SECTION_HEADERS and i + 1 < len(parts):
            sections.append({"header": chunk, "content": parts[i + 1].strip()})
            i += 2
        else:
            if chunk:
                sections.append({"header": None, "content": chunk})
            i += 1
    return sections or [{"header": None, "content": body}]


def _get_queue(unreviewed_first: bool = True) -> list[int]:
    """Ordered list of Council Bill LegislationSummary PKs."""
    all_ids = list(
        LegislationSummary.objects.filter(
            legislation__type__icontains=_COUNCIL_BILL_KIND
        )
        .order_by("-legislation__id")
        .values_list("id", flat=True)
    )
    if not unreviewed_first:
        return all_ids
    reviewed = set(
        SummaryCorrection.objects.values_list("legislation_summary_id", flat=True)
    )
    return [pk for pk in all_ids if pk not in reviewed] + [
        pk for pk in all_ids if pk in reviewed
    ]


@staff_member_required(login_url="/admin/login/")
def review_index(request: HttpRequest) -> HttpResponse:
    queue = _get_queue()
    if not queue:
        return render(request, "review.html", {"empty": True})
    return redirect("legistar:review_summary", pk=queue[0])


@staff_member_required(login_url="/admin/login/")
@require_http_methods(["GET", "POST"])
def review_summary(request: HttpRequest, pk: int) -> HttpResponse:
    summary = get_object_or_404(
        LegislationSummary.objects.select_related("legislation"),
        pk=pk,
    )

    queue = _get_queue(unreviewed_first=False)
    try:
        idx = queue.index(pk)
    except ValueError:
        idx = 0

    prev_pk = queue[idx - 1] if idx > 0 else None
    next_pk = queue[idx + 1] if idx < len(queue) - 1 else None

    if request.method == "POST":
        action = request.POST.get("action", "next")
        saved = 0
        i = 0
        while True:
            dimension = request.POST.get(f"dimension_{i}")
            if dimension is None:
                break
            issue = request.POST.get(f"issue_{i}", "").strip()
            correction = request.POST.get(f"correction_{i}", "").strip()
            if issue:
                SummaryCorrection.objects.create(
                    legislation_summary=summary,
                    dimension=dimension,
                    issue=issue,
                    correction=correction,
                )
                saved += 1
            i += 1

        if action == "prev" and prev_pk:
            return redirect("legistar:review_summary", pk=prev_pk)
        if action == "next" and next_pk:
            return redirect("legistar:review_summary", pk=next_pk)
        return redirect("legistar:review_summary", pk=pk)

    reviewed_ids = set(
        SummaryCorrection.objects.values_list("legislation_summary_id", flat=True)
    )
    total = len(queue)
    reviewed_count = sum(1 for q in queue if q in reviewed_ids)

    context = {
        "summary": summary,
        "legislation": summary.legislation,
        "headline": summary.headline or "(no headline)",
        "sections": _parse_sections(summary.body or ""),
        "source_text": summary.original_text or "(no source text available)",
        "existing_corrections": list(summary.corrections.order_by("-created_at")),
        "dimensions": SummaryCorrection.DIMENSIONS,
        "prev_pk": prev_pk,
        "next_pk": next_pk,
        "position": idx + 1,
        "total": total,
        "reviewed_count": reviewed_count,
        "is_reviewed": pk in reviewed_ids,
    }
    return render(request, "review.html", context)
