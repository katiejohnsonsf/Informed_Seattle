from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("legistar", "0006_summarycorrection"),
    ]

    operations = [
        migrations.CreateModel(
            name="CommunityProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=200, unique=True)),
                ("description", models.TextField(blank=True)),
                (
                    "prompt_context",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Additional context fed to the labeling agent. "
                            "Describe your geographic focus, key concerns, or member demographics."
                        ),
                    ),
                ),
                (
                    "constituencies",
                    models.JSONField(
                        default=list,
                        help_text="Flat list of constituency slugs this community cares about.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Community Profile",
                "verbose_name_plural": "Community Profiles",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="CBLabel",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "legislation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="labels",
                        to="legistar.legislation",
                    ),
                ),
                (
                    "community_profile",
                    models.ForeignKey(
                        blank=True,
                        help_text="The community whose constituencies shaped this label. Null = generic pass.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="labels",
                        to="legistar.communityprofile",
                    ),
                ),
                (
                    "record_class",
                    models.CharField(default="other_administrative", max_length=60),
                ),
                ("resident_salient", models.BooleanField(default=False)),
                ("policy_area", models.CharField(blank=True, max_length=80)),
                (
                    "subject_terms",
                    models.JSONField(
                        default=list,
                        help_text="Seattle City Clerk Thesaurus terms.",
                    ),
                ),
                ("statutory_populations", models.JSONField(default=list)),
                ("stakes", models.JSONField(default=list)),
                ("participation_window", models.CharField(blank=True, max_length=40)),
                ("labeled_at", models.DateTimeField(auto_now_add=True)),
                ("model_version", models.CharField(blank=True, max_length=100)),
            ],
            options={
                "verbose_name": "CB Label",
                "verbose_name_plural": "CB Labels",
            },
        ),
        migrations.AddConstraint(
            model_name="cblabel",
            constraint=models.UniqueConstraint(
                fields=["legislation", "community_profile"],
                name="unique_cblabel_per_legislation_community",
            ),
        ),
    ]
