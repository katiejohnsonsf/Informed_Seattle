#!/usr/bin/env python
"""
Labeling pipeline — classify recent Council Bills along the 4-facet schema.

Run after setup_summaries.py so summaries exist to feed the labeling agent.
If community profiles exist in the DB, each bill is labeled once per profile
(community-specific stakes). A generic pass (no profile) always runs first.

Usage:
    python setup_labels.py
    python setup_labels.py --force    # re-label even if label already exists
"""

import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
django.setup()

from django.db.models import Q

from server.legistar.label_schema import POLICY_AREA_LABELS, PARTICIPATION_WINDOW_LABELS
from server.legistar.labeling.agent import label_legislation
from server.legistar.labeling.participation import derive_participation_window
from server.legistar.models import CBLabel, CommunityProfile, Legislation

_COUNCIL_BILL_KIND = "Council Bill"
_COUNCIL_BILL_LIMIT = 40
_MODEL_VERSION = "gemma-4-31b"


def _recent_council_bills():
    return list(
        Legislation.objects.filter(
            Q(type__icontains=_COUNCIL_BILL_KIND) | Q(record_no__startswith="CB ")
        )
        .order_by("-id")[:_COUNCIL_BILL_LIMIT]
    )


def _label_one(
    legislation,
    community_profile=None,
    force: bool = False,
) -> bool:
    """
    Label a single bill for a given community (or generically if None).

    Returns True if a new label was created, False if skipped.
    """
    exists = CBLabel.objects.filter(
        legislation=legislation,
        community_profile=community_profile,
    ).exists()

    if exists and not force:
        community = community_profile.name if community_profile else "generic"
        print(f"  [{community}] already labeled — skipping")
        return False

    print(
        f"  [{community_profile.name if community_profile else 'generic'}] labeling..."
    )

    # Facets 0–2 + stakes from the agent
    label_data = label_legislation(legislation, community_profile=community_profile)

    # Facet 3 — participation_window derived deterministically
    participation_window = derive_participation_window(legislation)

    CBLabel.objects.update_or_create(
        legislation=legislation,
        community_profile=community_profile,
        defaults={
            "record_class": label_data["record_class"],
            "resident_salient": label_data["resident_salient"],
            "policy_area": label_data["policy_area"],
            "subject_terms": label_data["subject_terms"],
            "statutory_populations": label_data["statutory_populations"],
            "stakes": label_data["stakes"],
            "participation_window": participation_window,
            "model_version": _MODEL_VERSION,
        },
    )

    # Print a brief summary of what was assigned
    area_label = POLICY_AREA_LABELS.get(label_data["policy_area"], label_data["policy_area"])
    win_label = PARTICIPATION_WINDOW_LABELS.get(participation_window, participation_window)
    salient = "✓ resident-salient" if label_data["resident_salient"] else "not salient"
    n_stakes = len(label_data["stakes"])
    print(f"    → {area_label} | {win_label} | {salient} | {n_stakes} stakes")
    return True


def run_labeling_pipeline(force: bool = False):
    print("\n" + "=" * 80)
    print("Seattle City Council — CB Labeling Pipeline")
    print("=" * 80 + "\n")

    bills = _recent_council_bills()
    profiles = list(CommunityProfile.objects.all())

    print(f"Bills to label:      {len(bills)}")
    print(f"Community profiles:  {len(profiles)} (plus 1 generic pass)")
    print()

    created_total = 0

    for i, legislation in enumerate(bills, 1):
        print(f"[{i}/{len(bills)}] {legislation.record_no}: {legislation.title[:60]}...")

        # Generic pass first (no community profile)
        if _label_one(legislation, community_profile=None, force=force):
            created_total += 1

        # One pass per community profile
        for profile in profiles:
            if _label_one(legislation, community_profile=profile, force=force):
                created_total += 1

    print()
    print("=" * 80)
    print("✓ LABELING PIPELINE COMPLETE")
    print("=" * 80)
    print(f"\nNew labels created: {created_total}")
    total_labels = CBLabel.objects.count()
    generic_labels = CBLabel.objects.filter(community_profile__isnull=True).count()
    print(f"Total labels in DB: {total_labels} ({generic_labels} generic + {total_labels - generic_labels} community-specific)")

    if profiles:
        print("\nCommunity profiles:")
        for p in profiles:
            n = CBLabel.objects.filter(community_profile=p).count()
            print(f"  {p.name}: {n} labels, {len(p.constituencies)} constituencies")
    else:
        print("\nNo community profiles yet.")
        print("Run `python manage.py runserver` and visit /community/new/ to create one.")

    print()


if __name__ == "__main__":
    force = "--force" in sys.argv
    try:
        run_labeling_pipeline(force=force)
    except KeyboardInterrupt:
        print("\n\n⚠ Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
