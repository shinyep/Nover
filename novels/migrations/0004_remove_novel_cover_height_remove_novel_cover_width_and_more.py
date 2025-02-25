# Generated by Django 5.1.6 on 2025-02-24 12:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('novels', '0003_novel_cover_height_novel_cover_width_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='novel',
            name='cover_height',
        ),
        migrations.RemoveField(
            model_name='novel',
            name='cover_width',
        ),
        migrations.AlterField(
            model_name='novel',
            name='cover',
            field=models.URLField(blank=True, max_length=500, null=True, verbose_name='封面'),
        ),
        migrations.AlterField(
            model_name='novel',
            name='title',
            field=models.CharField(max_length=255, unique=True, verbose_name='标题'),
        ),
    ]
