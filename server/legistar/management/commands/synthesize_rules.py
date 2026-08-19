"""
Management command: synthesize-rules

Reads unsynthesized SummaryCorrection records, clusters them by rubric
dimension, asks Claude to derive concise new rules, and appends those rules
to server/alignment/data/rubric.json. Marks each processed correction as
synthesized=True.

The updated rubric.json is committed to git like any other source file, so
rule changes are fully versioned.

Usage:
    python manage.py synthesize_rules
    python manage.py synthesize_rules --dry-run      # print rules, don't save
    python manage.py synthesize_rules --all          # include already-synthesized
"""

import sys

from django.conf import settings
from django.core.management.base import BaseCommand

from server.legistar.models import SummaryCorrection


class Command(BaseCommand):
    help = (
        "Derive new rubric rules from SummaryCorrection records and update "
        "server/alignment/data/rubric.json."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print proposed rules without updating rubric.json or the database.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            dest="include_all",
            help="Include corrections already marked synthesized.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        include_all = options["include_all"]

        qs = SummaryCorrection.objects.select_related(
            "legislation_summary__legislation"
        )
        if not include_all:
            qs = qs.filter(synthesized=False)

        total = qs.count()
        if total == 0:
            self.stderr.write("No pending corrections to synthesize.")
            return

        self.stderr.write(f"Synthesizing {total} correction(s)...")

        from server.alignment.synthesizer import synthesize
        from server.lib.anthropic_client import get_anthropic_client

        client = get_anthropic_client()
        model = getattr(settings, "ANTHROPIC_MODEL", "claude-opus-4-6")
        self.stderr.write(f"Using model: {model}")

        new_rules = synthesize(client, model, list(qs), dry_run=dry_run)

        if not dry_run and new_rules:
            updated = qs.update(synthesized=True)
            self.stderr.write(f"Marked {updated} correction(s) as synthesized.")

        total_rules = sum(len(v) for v in new_rules.values())
        if dry_run:
            self.stderr.write(f"[dry-run] Would add {total_rules} rule(s).")
        else:
            self.stderr.write(f"Done. Added {total_rules} new rule(s) across {len(new_rules)} dimension(s).")
