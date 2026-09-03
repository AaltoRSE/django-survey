from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("survey", "0023_alter_question_scale_min")]

    operations = [
        migrations.AddField(
            model_name="question",
            name="description",
            field=models.TextField(blank=True, default="", verbose_name="Description"),
        ),
        migrations.AddField(
            model_name="question",
            name="label",
            field=models.CharField(blank=True, default="", max_length=200, verbose_name="Row label"),
        ),
        migrations.AddField(
            model_name="question",
            name="grouping",
            field=models.CharField(
                choices=[
                    ("standalone", "Standalone question"),
                    ("group", "Group question (continue the previous question's card)"),
                ],
                default="standalone",
                max_length=10,
                verbose_name="Card",
            ),
        ),
        migrations.AlterField(
            model_name="question",
            name="text",
            field=models.TextField(blank=True, verbose_name="Text"),
        ),
    ]
