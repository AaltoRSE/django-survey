from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("survey", "0015_add_likert_time_datetime_types")]

    operations = [
        migrations.AddField(
            model_name="question",
            name="other_option",
            field=models.BooleanField(
                default=False,
                help_text="Only available on radio and select questions.",
                verbose_name="Add an 'other' free-text option",
            ),
        ),
        migrations.AddField(
            model_name="question",
            name="other_label",
            field=models.CharField(
                default="Other, please specify",
                max_length=200,
                verbose_name="Label for the 'other' option",
            ),
        ),
    ]
