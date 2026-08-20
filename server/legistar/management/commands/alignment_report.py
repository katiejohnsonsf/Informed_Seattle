"""
Management command: alignment-report

Prints the current alignment state:
  - Rubric version and per-dimension rules
  - Prompts version
  - Pending correction count
  - Recent evaluation score averages

Usage:
    python manage.py alignment_report
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Print current alignment state: rubric rules, correction counts, eval scores."
    )

    def handle(self, *args, **options):
        from server.alignment.rubric import get_rubric, load_prompts
        from server.legistar.models import SummaryCorrection, SummaryEvaluation

        rubric = get_rubric()
        prompts = load_prompts()

        self.stdout.write("\n=== ALIGNMENT REPORT ===\n")
        self.stdout.write(
            f"Rubric  v{rubric.get('version', 1)} — updated {rubric.get('updated_at', 'unknown')}"
        )
        self.stdout.write(
            f"Prompts v{prompts.get('version', 1)} — updated {prompts.get('updated_at', 'unknown')}\n"
        )

        # Rubric rules per dimension
        self.stdout.write("--- RUBRIC RULES ---")
        dimensions = rubric.get("dimensions", {})
        for dim, data in dimensions.items():
            rules = data.get("rules", [])
            label = f"{dim} ({len(rules)} rule{'s' if len(rules) != 1 else ''})"
            self.stdout.write(f"\n{label}:")
            if rules:
                for r in rules:
                    self.stdout.write(f"  • {r}")
            else:
                self.stdout.write(
                    "  (no rules yet — add corrections and run synthesize_rules)"
                )

        # Correction counts
        total_corrections = SummaryCorrection.objects.count()
        pending_corrections = SummaryCorrection.objects.filter(
            synthesized=False
        ).count()
        self.stdout.write(f"\n--- CORRECTIONS ---")
        self.stdout.write(
            f"Total: {total_corrections}  |  Pending synthesis: {pending_corrections}"
        )
        if pending_corrections:
            self.stdout.write("  → Run: python manage.py synthesize_rules")

        # Recent evaluation scores
        evals = list(
            SummaryEvaluation.objects.order_by("-created_at").values(
                "overall_completeness", "overall_faithfulness"
            )[:20]
        )
        self.stdout.write(f"\n--- EVALUATION SCORES (last {len(evals)}) ---")
        if evals:
            c_vals = [
                e["overall_completeness"]
                for e in evals
                if e["overall_completeness"] is not None
            ]
            f_vals = [
                e["overall_faithfulness"]
                for e in evals
                if e["overall_faithfulness"] is not None
            ]
            if c_vals:
                self.stdout.write(
                    f"Avg completeness : {sum(c_vals)/len(c_vals):.2f}/5.0"
                )
            if f_vals:
                self.stdout.write(
                    f"Avg faithfulness : {sum(f_vals)/len(f_vals):.2f}/5.0"
                )
        else:
            self.stdout.write(
                "  No evaluations yet — run: python manage.py evaluate_summaries"
            )

        # Prompt versions
        self.stdout.write(f"\n--- PROMPT VERSIONS ---")
        for key, cfg in prompts.get("prompts", {}).items():
            has_prev = "previous_template" in cfg
            flag = " [optimized]" if has_prev else ""
            self.stdout.write(f"  {key}{flag}")

        self.stdout.write("")
