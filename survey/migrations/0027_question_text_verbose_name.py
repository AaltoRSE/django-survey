from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("survey", "0026_question_header_rows")]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="text",
            field=models.TextField(blank=True, verbose_name="Title"),
        ),
    ]
