from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("survey", "0020_integer_scale")]

    operations = [
        migrations.AddField(
            model_name="question",
            name="will_not_answer_option",
            field=models.BooleanField(
                default=False,
                help_text="Only available on integer scale questions.",
                verbose_name="Add a 'will not answer' option",
            ),
        ),
        migrations.AddField(
            model_name="question",
            name="will_not_answer_label",
            field=models.CharField(
                default="I will not answer",
                max_length=200,
                verbose_name="Label for the 'will not answer' option",
            ),
        ),
    ]
