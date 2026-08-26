"""
Community setup form — staff-only, not included in the static distill build.

Flow:
  GET  /community/              → list existing profiles
  GET  /community/new/          → blank setup form
  POST /community/new/          → create profile
  GET  /community/<id>/edit/    → edit form pre-populated
  POST /community/<id>/edit/    → update profile
  POST /community/<id>/delete/  → delete profile
"""

from __future__ import annotations


from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from server.legistar.label_schema import (
    ALL_DEFAULT_CONSTITUENCIES,
    DEFAULT_CONSTITUENCIES,
)
from server.legistar.models import CommunityProfile


def _parse_form(request: HttpRequest) -> dict:
    """Extract and validate community profile fields from a POST request."""
    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()
    prompt_context = request.POST.get("prompt_context", "").strip()

    # Constituencies: checkboxes for defaults + newline-separated custom terms
    selected = request.POST.getlist("constituencies")
    custom_raw = request.POST.get("custom_constituencies", "")
    custom = [
        t.strip().lower().replace(" ", "-")
        for t in custom_raw.splitlines()
        if t.strip()
    ]
    # Deduplicate while preserving order.
    constituencies = list(dict.fromkeys(selected + custom))

    errors: list[str] = []
    if not name:
        errors.append("Community name is required.")

    return {
        "name": name,
        "description": description,
        "prompt_context": prompt_context,
        "constituencies": constituencies,
        "errors": errors,
    }


def _profile_context(profile: CommunityProfile | None = None) -> dict:
    """Build template context: grouped checkbox data with checked state."""
    existing = set(profile.constituencies) if profile else set()
    groups = []
    for group_label, terms in DEFAULT_CONSTITUENCIES.items():
        groups.append(
            {
                "label": group_label,
                "terms": [
                    {
                        "slug": t,
                        "label": t.replace("-", " ").title(),
                        "checked": t in existing,
                    }
                    for t in terms
                ],
            }
        )

    existing_constituencies = profile.constituencies if profile else []
    custom = [c for c in existing_constituencies if c not in ALL_DEFAULT_CONSTITUENCIES]

    return {
        "groups": groups,
        "custom_constituencies": "\n".join(custom),
        "profile": profile,
    }


@staff_member_required
def community_list(request: HttpRequest) -> HttpResponse:
    profiles = CommunityProfile.objects.all()
    return render(request, "community_profiles.html", {"profiles": profiles})


@staff_member_required
@require_http_methods(["GET", "POST"])
def community_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        data = _parse_form(request)
        if data["errors"]:
            ctx = _profile_context()
            ctx.update(data)
            return render(request, "community_setup.html", ctx, status=400)

        CommunityProfile.objects.create(
            name=data["name"],
            description=data["description"],
            prompt_context=data["prompt_context"],
            constituencies=data["constituencies"],
        )
        return redirect("legistar:community_list")

    ctx = _profile_context()
    ctx["errors"] = []
    return render(request, "community_setup.html", ctx)


@staff_member_required
@require_http_methods(["GET", "POST"])
def community_edit(request: HttpRequest, pk: int) -> HttpResponse:
    profile = get_object_or_404(CommunityProfile, pk=pk)

    if request.method == "POST":
        data = _parse_form(request)
        if data["errors"]:
            ctx = _profile_context(profile)
            ctx.update(data)
            return render(request, "community_setup.html", ctx, status=400)

        profile.name = data["name"]
        profile.description = data["description"]
        profile.prompt_context = data["prompt_context"]
        profile.constituencies = data["constituencies"]
        profile.save()
        return redirect("legistar:community_list")

    ctx = _profile_context(profile)
    ctx.update(
        {
            "name": profile.name,
            "description": profile.description,
            "prompt_context": profile.prompt_context,
            "errors": [],
        }
    )
    return render(request, "community_setup.html", ctx)


@staff_member_required
@require_http_methods(["POST"])
def community_delete(request: HttpRequest, pk: int) -> HttpResponse:
    profile = get_object_or_404(CommunityProfile, pk=pk)
    profile.delete()
    return redirect("legistar:community_list")
