from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('novels', '0006_alter_chapter_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='novel',
            name='default_cover_path',
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name='默认封面路径'),
        ),
    ]