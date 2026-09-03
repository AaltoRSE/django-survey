from django.db import migrations, models


def grouping_to_boolean(apps, schema_editor):
    Question = apps.get_model("survey", "Question")
    Question.objects.filter(grouping="group").update(group_with_previous=True)


def boolean_to_grouping(apps, schema_editor):
    Question = apps.get_model("survey", "Question")
    Question.objects.filter(group_with_previous=True).update(grouping="group")


class Migration(migrations.Migration):
    dependencies = [("survey", "0024_question_cards")]

    operations = [
        migrations.AddField(
            model_name="question",
            name="group_with_previous",
            field=models.BooleanField(
                default=False,
                help_text="Show this question inside the preceding question's group, without a title of its own.",
                verbose_name="Group with preceding question",
            ),
        ),
        migrations.RunPython(grouping_to_boolean, boolean_to_grouping),
        migrations.RemoveField(model_name="question", name="grouping"),
    ]
