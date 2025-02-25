from django.core.management.base import BaseCommand
from novels.models import Novel, Chapter
import re

class Command(BaseCommand):
    help = '修复章节排序问题，确保番外排在正常章节之后'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('开始修复章节排序...'))
        
        # 提取章节序号的函数
        def extract_chapter_info(title):
            # 检查是否是番外或特殊章节
            is_special = any(keyword in title for keyword in ['番外', '后记', '附录', '特别篇', '外传'])
            
            # 提取章节序号
            match = re.search(r'第(\d+)章', title)
            if match:
                return (0 if is_special else 1, int(match.group(1)))
            
            # 尝试其他可能的格式
            numbers = re.findall(r'\d+', title)
            if numbers:
                return (0 if is_special else 1, int(numbers[0]))
            
            # 如果没有数字，给番外一个很大的序号
            return (0, 999999) if is_special else (1, 999999)
        
        # 获取所有小说
        novels = Novel.objects.all()
        self.stdout.write(f'找到 {novels.count()} 本小说')
        
        total_updated = 0
        
        # 处理每本小说的章节
        for novel in novels:
            self.stdout.write(f'处理小说: {novel.title}')
            
            # 获取所有章节并提取序号信息
            chapters = []
            for chapter in Chapter.objects.filter(novel=novel):
                chapter_type, order = extract_chapter_info(chapter.title)
                chapters.append((chapter, chapter_type, order))
            
            # 按章节类型和序号排序：正常章节(1)在前，番外(0)在后
            chapters.sort(key=lambda x: (x[1], -x[2] if x[1] == 0 else x[2]))
            
            # 更新排序值，确保连续
            for i, (chapter, chapter_type, order) in enumerate(chapters):
                # 正常章节使用原始序号，番外使用大序号
                new_order = order if chapter_type == 1 else 1000000 + i
                
                if chapter.order != new_order:
                    chapter.order = new_order
                    chapter.save(update_fields=['order'])
                    total_updated += 1
                    chapter_type_str = "正常章节" if chapter_type == 1 else "番外/特殊章节"
                    self.stdout.write(f'  更新: {chapter.title} -> order={new_order} ({chapter_type_str})')
        
        self.stdout.write(self.style.SUCCESS(f'完成! 共更新了 {total_updated} 个章节的排序')) 