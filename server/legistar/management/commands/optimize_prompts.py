"""
Management command: optimize-prompts

Reads rubric rules and synthesized SummaryCorrection records, then asks Claude
to rewrite each prompt template to better satisfy the rubric. Improved prompts
are saved to server/alignment/data/prompts.json, which olmo_legislation.py
reads at runtime — changes take effect on the next summarization run.

Usage:
    python manage.py optimize_prompts
    python manage.py optimize_prompts --dry-run
    python manage.py optimize_prompts --keys original_proposal headline
"""

from collections import defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand

from server.legistar.models import SummaryCorrection


class Command(BaseCommand):
    help = (
        "Generate improved summarization prompt templates using Claude and save "
        "them to server/alignment/data/prompts.json."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print improved prompts without saving to prompts.json.",
        )
        parser.add_argument(
            "--keys",
            nargs="+",
            metavar="KEY",
            help=(
                "Optimize only the specified prompt keys "
                "(original_proposal, final_text, differences, headline, simple_summary). "
                "Defaults to all."
            ),
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        keys = options.get("keys") or None

        corrections = list(
            SummaryCorrection.objects.select_related("legislation_summary__legislation")
        )

        by_dim: dict[str, list] = defaultdict(list)
        for c in corrections:
            by_dim[c.dimension].append(c)

        self.stderr.write(
            f"{len(corrections)} total correction(s) across {len(by_dim)} dimension(s)."
        )

        from server.alignment.optimizer import run_optimization
        from server.lib.anthropic_client import get_anthropic_client

        client = get_anthropic_client()
        model = getattr(settings, "ANTHROPIC_MODEL", "claude-opus-4-6")
        self.stderr.write(f"Using model: {model}")

        improved = run_optimization(
            client,
            model,
            dict(by_dim),
            prompt_keys=keys,
            dry_run=dry_run,
        )

        if dry_run:
            self.stderr.write(f"[dry-run] Would update {len(improved)} prompt(s).")
        else:
            self.stderr.write(f"Done. Updated {len(improved)} prompt(s): {list(improved)}")
