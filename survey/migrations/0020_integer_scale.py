"""Replace the fixed scale-0-10 / scale-minus5-5 types with one configurable
'integer scale' type carrying its own limits."""

from django.db import migrations, models

REPLACED_TYPES = {"scale-0-10": (0, 10), "scale-minus5-5": (-5, 5)}


def to_integer_scale(apps, schema_editor):
    Question = apps.get_model("survey", "Question")
    for old_type, (scale_min, scale_max) in REPLACED_TYPES.items():
        Question.objects.filter(type=old_type).update(
            type="integer-scale", scale_min=scale_min, scale_max=scale_max
        )


def to_fixed_scales(apps, schema_editor):
    Question = apps.get_model("survey", "Question")
    for old_type, (scale_min, scale_max) in REPLACED_TYPES.items():
        Question.objects.filter(type="integer-scale", scale_min=scale_min, scale_max=scale_max).update(type=old_type)


class Migration(migrations.Migration):
    dependencies = [("survey", "0019_add_scale_minus5_5_type")]

    operations = [
        migrations.AddField(
            model_name="question",
            name="scale_min",
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text=(
                    "The minimum and maximum are only used by the 'integer scale'\n"
                    "question type. Name the ends of the scale in the question text\n"
                    "itself; the options are shown as bare numbers."
                ),
                verbose_name="Scale minimum",
            ),
        ),
        migrations.AddField(
            model_name="question",
            name="scale_max",
            field=models.IntegerField(blank=True, null=True, verbose_name="Scale maximum"),
        ),
        migrations.RunPython(to_integer_scale, to_fixed_scales),
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
                    ("integer-scale", "integer scale"),
                    ("time", "time"),
                    ("datetime", "date and time"),
                ],
                default="text",
                max_length=200,
                verbose_name="Type",
            ),
        ),
    ]
