from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("survey", "0025_question_group_with_previous")]

    operations = [
        migrations.AddField(
            model_name="question",
            name="header_rows",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Label rows shown above the answers of this question's group. One row per line, cells separated by commas.",
                verbose_name="Header rows",
            ),
        ),
    ]
