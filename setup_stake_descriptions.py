#!/usr/bin/env python
"""
Generate plain-language "how does this affect X" descriptions for each
Council Bill's already-determined stakeholder groups.

Run after setup_labels.py, since it needs each bill's stakes to already
exist. By default, only stakes missing a description are filled in — a
normal run only does real work on bills that are newly labeled or newly
gained a stake since the last run.

Usage:
    python setup_stake_descriptions.py
    python setup_stake_descriptions.py --force   # regenerate existing descriptions too
    COUNCIL_BILL_LABEL_LIMIT=10 python setup_stake_descriptions.py
"""

import os
import sys
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
django.setup()

from server.legistar.labeling.stake_descriptions import generate_stake_descriptions
from server.legistar.models import CBLabel

_COUNCIL_BILL_LABEL_LIMIT = (
    int(os.environ["COUNCIL_BILL_LABEL_LIMIT"])
    if os.environ.get("COUNCIL_BILL_LABEL_LIMIT")
    else None
)


def _labels_with_stakes() -> list[CBLabel]:
    qs = (
        CBLabel.objects.filter(community_profile__isnull=True)
        .order_by("-id")
        .select_related("legislation")
    )
    labels = [label for label in qs if label.stakes]
    if _COUNCIL_BILL_LABEL_LIMIT:
        labels = labels[:_COUNCIL_BILL_LABEL_LIMIT]
    return labels


def _needs_description(stakes: list[dict], force: bool) -> bool:
    if not stakes:
        return False
    return force or any(not s.get("description") for s in stakes)


def run(force: bool = False):
    print("\n" + "=" * 80)
    print("Seattle City Council — Stakeholder Impact Description Pipeline")
    print("=" * 80 + "\n")

    labels = _labels_with_stakes()
    print(f"Labeled bills with stakes: {len(labels)}\n")

    updated_total = 0
    for i, label in enumerate(labels, 1):
        top = label.top_stakes
        if not _needs_description(top, force):
            continue

        print(
            f"[{i}/{len(labels)}] {label.legislation.record_no}: "
            f"generating descriptions for {len(top)} group(s)..."
        )
        descriptions = generate_stake_descriptions(label.legislation, top)
        if not descriptions:
            print("    ✗ No descriptions generated — skipping")
            continue

        # Write into the full stored stakes list (not just top_stakes) so
        # top_stakes recomputes correctly from what's actually persisted.
        changed = False
        for s in label.stakes:
            desc = descriptions.get(s["group"])
            if desc and s.get("description") != desc:
                s["description"] = desc
                changed = True

        if changed:
            label.save(update_fields=["stakes"])
            updated_total += 1
            print(f"    → wrote {len(descriptions)} description(s)")
        else:
            print("    (nothing new)")

    print()
    print("=" * 80)
    print(f"✓ COMPLETE — {updated_total} bill(s) updated")
    print("=" * 80)
    print()


if __name__ == "__main__":
    force = "--force" in sys.argv
    try:
        run(force=force)
    except KeyboardInterrupt:
        print("\n\n⚠ Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Pipeline failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
