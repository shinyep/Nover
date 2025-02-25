from django.core.management.base import BaseCommand
from novels.models import Category

class Command(BaseCommand):
    help = '初始化小说分类'

    def handle(self, *args, **options):
        Category.objects.get_or_create(name='默认分类')
        self.stdout.write(self.style.SUCCESS('成功创建默认分类')) 