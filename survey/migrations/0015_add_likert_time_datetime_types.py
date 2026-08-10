from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("survey", "0014_survey_redirect_url")]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="type",
            field=models.CharField(
                choices=[
                    ("text", "text (multiple line)"),
                    ("short-text", "short text (one line)"),
                    ("radio", "radio"),
                    ("select", "select"),
                    ("select-multiple", "Select Multiple"),
                    ("select_image", "Select Image"),
                    ("integer", "integer"),
                    ("float", "float"),
                    ("date", "date"),
                    ("likert-5", "5-point likert"),
                    ("time", "time"),
                    ("datetime", "date and time"),
                ],
                default="text",
                max_length=200,
                verbose_name="Type",
            ),
        )
    ]
