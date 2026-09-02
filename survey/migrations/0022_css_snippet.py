from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("survey", "0021_question_will_not_answer")]

    operations = [
        migrations.CreateModel(
            name="CssSnippet",
            fields=[
                ("id", models.AutoField(verbose_name="ID", serialize=False, auto_created=True, primary_key=True)),
                ("name", models.CharField(max_length=200, unique=True, verbose_name="Name")),
                ("css", models.TextField(verbose_name="CSS")),
            ],
            options={
                "verbose_name": "CSS snippet",
                "verbose_name_plural": "CSS snippets",
            },
        ),
    ]
