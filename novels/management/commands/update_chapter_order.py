from django.core.management.base import BaseCommand
from novels.models import Novel, Chapter
import re

class Command(BaseCommand):
    help = '更新所有章节的排序值'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('开始更新章节排序...'))
        
        # 提取章节序号的函数
        def extract_chapter_number(title):
            match = re.search(r'第(\d+)章', title)
            if match:
                return int(match.group(1))
            # 尝试其他可能的格式
            numbers = re.findall(r'\d+', title)
            if numbers:
                return int(numbers[0])
            return 0
        
        # 获取所有小说
        novels = Novel.objects.all()
        self.stdout.write(f'找到 {novels.count()} 本小说')
        
        total_updated = 0
        
        # 处理每本小说的章节
        for novel in novels:
            self.stdout.write(f'处理小说: {novel.title}')
            chapters = Chapter.objects.filter(novel=novel)
            
            # 更新每个章节的排序值
            for chapter in chapters:
                order = extract_chapter_number(chapter.title)
                if chapter.order != order:
                    chapter.order = order
                    chapter.save(update_fields=['order'])
                    total_updated += 1
        
        self.stdout.write(self.style.SUCCESS(f'完成! 共更新了 {total_updated} 个章节的排序')) 