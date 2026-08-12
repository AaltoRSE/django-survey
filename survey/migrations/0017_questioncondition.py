import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("survey", "0016_question_other_option")]

    operations = [
        migrations.CreateModel(
            name="QuestionCondition",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                (
                    "operator",
                    models.CharField(
                        choices=[
                            ("in", "answer is one of choices"),
                            ("eq", "=="),
                            ("ne", "!="),
                            ("lt", "<"),
                            ("le", "<="),
                            ("gt", ">"),
                            ("ge", ">="),
                        ],
                        default="in",
                        max_length=2,
                    ),
                ),
                (
                    "choices",
                    models.TextField(
                        blank=True,
                        help_text="Comma-separated parent choice labels, used with the 'in' operator.",
                    ),
                ),
                (
                    "number",
                    models.FloatField(blank=True, help_text="Used with the numeric operators.", null=True),
                ),
                (
                    "depends_on",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dependent_conditions",
                        to="survey.question",
                    ),
                ),
                (
                    "question",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="condition",
                        to="survey.question",
                    ),
                ),
            ],
        ),
    ]
