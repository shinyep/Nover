from django.core.management.base import BaseCommand
from novels.models import Novel, Chapter
import re

class Command(BaseCommand):
    help = '处理章节标题中的指定内容'

    def add_arguments(self, parser):
        parser.add_argument('--novel', type=str, help='指定小说标题（可选）')
        parser.add_argument('--pattern', type=str, required=True, help='要匹配的标题模式（正则表达式）')
        parser.add_argument('--replace', type=str, help='替换为的内容')
        parser.add_argument('--remove', action='store_true', help='移除匹配的内容')
        parser.add_argument('--preview', action='store_true', help='预览模式，不实际修改')

    def handle(self, *args, **options):
        pattern = options['pattern']
        replace = options['replace']
        remove = options['remove']
        preview = options['preview']
        novel_title = options.get('novel')
        
        if remove and replace:
            self.stderr.write(self.style.ERROR('--remove 和 --replace 不能同时使用'))
            return
            
        if not (remove or replace):
            self.stderr.write(self.style.ERROR('必须指定 --remove 或 --replace 参数'))
            return
            
        # 构建查询
        chapters_query = Chapter.objects.all()
        if novel_title:
            novels = Novel.objects.filter(title__icontains=novel_title)
            if not novels.exists():
                self.stderr.write(self.style.ERROR(f'找不到标题包含 "{novel_title}" 的小说'))
                return
            chapters_query = chapters_query.filter(novel__in=novels)
            
        # 找出匹配的章节
        matching_chapters = []
        for chapter in chapters_query:
            if re.search(pattern, chapter.title):
                matching_chapters.append(chapter)
                
        if not matching_chapters:
            self.stdout.write(self.style.WARNING(f'没有找到匹配模式 "{pattern}" 的章节标题'))
            return
            
        self.stdout.write(f'找到 {len(matching_chapters)} 个匹配的章节')
        
        # 处理章节标题
        updated_count = 0
        for chapter in matching_chapters:
            old_title = chapter.title
            if remove:
                new_title = re.sub(pattern, '', old_title)
            else:
                new_title = re.sub(pattern, replace, old_title)
                
            if old_title != new_title:
                if preview:
                    self.stdout.write(f'预览: "{old_title}" -> "{new_title}"')
                else:
                    chapter.title = new_title
                    chapter.save(update_fields=['title'])
                    updated_count += 1
                    self.stdout.write(f'已更新: "{old_title}" -> "{new_title}"')
        
        if preview:
            self.stdout.write(self.style.SUCCESS(f'预览完成，共有 {len(matching_chapters)} 个章节标题将被修改'))
        else:
            self.stdout.write(self.style.SUCCESS(f'处理完成，共更新了 {updated_count} 个章节标题')) 