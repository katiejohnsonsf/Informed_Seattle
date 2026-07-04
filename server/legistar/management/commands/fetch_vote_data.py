"""Management command: fetch and persist council vote data for Council Bills."""

import json

from django.core.management.base import BaseCommand

from server.legistar.models import Legislation

# Bodies that represent a Full Council vote (lowercased)
_FULL_COUNCIL_BODIES = frozenset(
    {"full council", "seattle city council", "city council"}
)


def _is_full_council(action_by: str) -> bool:
    low = (action_by or "").lower()
    return any(b in low for b in _FULL_COUNCIL_BODIES)


class Command(BaseCommand):
    help = "Fetch and store individual council vote data for all Council Bills."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-fetch vote data even if already stored.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        from django.db.models import Q

        bills = Legislation.objects.filter(
            Q(type__icontains="Council Bill") | Q(record_no__startswith="CB ")
        )
        total = bills.count()
        self.stdout.write(f"Processing {total} Council Bill(s)...")

        fetched = 0
        skipped = 0

        for bill in bills:
            existing = bill.vote_data or {}
            already_has_council = bool(existing.get("action_details"))
            already_has_committee = bool(existing.get("committee_action_details"))

            if not force and already_has_council and already_has_committee:
                skipped += 1
                continue

            # Collect rows with a result and action_details link
            council_rows = []
            committee_rows = []
            for row in bill.crawl_data.rows:
                if row.action_details is None or not row.result:
                    continue
                if _is_full_council(row.action_by):
                    council_rows.append(row)
                else:
                    committee_rows.append(row)

            # Skip entirely if nothing to fetch
            if not council_rows and not committee_rows:
                skipped += 1
                continue

            self.stdout.write(f"  Fetching votes for {bill.record_no}...")
            try:
                from server.legistar.lib.crawler import LegistarCalendarCrawler

                crawler = LegistarCalendarCrawler("seattle")
                updated = dict(existing)

                if council_rows and (force or not already_has_council):
                    paired = []
                    for row in council_rows:
                        action_data = crawler.get_action_for_legislation_row(row)
                        if action_data is not None:
                            paired.append(
                                {
                                    "action_by": row.action_by or "",
                                    "action": json.loads(action_data.json()),
                                }
                            )
                    if paired:
                        updated["action_details"] = paired

                if committee_rows and (force or not already_has_committee):
                    paired = []
                    for row in committee_rows:
                        action_data = crawler.get_action_for_legislation_row(row)
                        if action_data is not None:
                            paired.append(
                                {
                                    "action_by": row.action_by or "",
                                    "action": json.loads(action_data.json()),
                                }
                            )
                    if paired:
                        updated["committee_action_details"] = paired

                if updated != existing:
                    bill.vote_data = updated
                    bill.save(update_fields=["vote_data"])
                    fetched += 1
                    n_c = len(updated.get("action_details", []))
                    n_m = len(updated.get("committee_action_details", []))
                    self.stdout.write(
                        f"    Saved council={n_c} committee={n_m} "
                        f"record(s) for {bill.record_no}."
                    )
                else:
                    skipped += 1

            except Exception as exc:
                self.stderr.write(
                    f"  Warning: could not fetch votes for {bill.record_no}: {exc}"
                )
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f"Done. Fetched: {fetched}, Skipped/no votes: {skipped}")
        )
