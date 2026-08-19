from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('legistar', '0005_summaryevaluation'),
    ]

    operations = [
        migrations.CreateModel(
            name='SummaryCorrection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dimension', models.CharField(
                    choices=[
                        ('headline_accuracy', 'Headline Accuracy'),
                        ('proposed_intent_fidelity', 'Proposed Intent Fidelity'),
                        ('final_text_fidelity', 'Final Text Fidelity'),
                        ('amendment_accuracy', 'Amendment Accuracy'),
                        ('accessibility', 'Accessibility'),
                        ('neutrality', 'Neutrality'),
                    ],
                    max_length=50,
                )),
                ('issue', models.TextField(help_text='What is wrong with this aspect of the summary?')),
                ('correction', models.TextField(
                    blank=True,
                    help_text='What should it say instead? (leave blank to just flag the issue)',
                )),
                ('synthesized', models.BooleanField(
                    default=False,
                    help_text='Has this been picked up by the rule synthesizer?',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('legislation_summary', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='corrections',
                    to='legistar.legislationsummary',
                )),
            ],
            options={
                'verbose_name': 'Summary correction',
                'verbose_name_plural': 'Summary corrections',
                'ordering': ['-created_at'],
            },
        ),
    ]
