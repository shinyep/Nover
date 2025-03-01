from django.core.management.base import BaseCommand
from novels.models import Chapter
import re

class Command(BaseCommand):
    help = '更新章节标题，去掉时间文本'

    def handle(self, *args, **kwargs):
        chapters = Chapter.objects.all()
        updated_count = 0

        for chapter in chapters:
            # 去掉章节标题中的时间文本
            new_title = re.sub(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', '', chapter.title).strip()
            if new_title != chapter.title:
                chapter.title = new_title
                chapter.save()
                updated_count += 1
                self.stdout.write(self.style.SUCCESS(f"更新章节标题: {chapter.id} -> {new_title}"))

        self.stdout.write(self.style.SUCCESS(f"总共更新了 {updated_count} 个章节标题")) 