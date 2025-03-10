# Generated by Django 3.2 on 2021-06-14 14:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('survey', '0015_auto_20210614_1241'),
    ]

    operations = [
        migrations.AlterField(
            model_name='answer',
            name='id',
            field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='category',
            name='id',
            field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='question',
            name='id',
            field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='response',
            name='id',
            field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
        migrations.AlterField(
            model_name='response',
            name='user_id',
            field=models.CharField(blank=True, default='', max_length=32, verbose_name='User_ID'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='survey',
            name='id',
            field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID'),
        ),
    ]
