from django.core.management.base import BaseCommand
from novels.models import Novel, Chapter, Category
from django.utils import timezone
import os
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import datetime

class Command(BaseCommand):
    help = '从本地TXT文件导入小说'

    def add_arguments(self, parser):
        parser.add_argument('folder_path', type=str, help='TXT文件所在文件夹路径')

    def safe_filename(self, text, max_length=120):
        """生成安全的文件名（支持多语言字符）"""
        # 保留中日韩文字符及其他语言字符
        text = unicodedata.normalize('NFKC', text)
        # 替换特殊字符
        text = re.sub(r'[\\/*?:"<>|()\s]', '_', text)
        # 合并连续下划线
        text = re.sub(r'_+', '_', text)
        # 截断并去除首尾无效字符
        return text.strip('_')[:max_length]

    def print_status(self, stage, message, status=None):
        """打印带颜色的状态信息"""
        symbols = {'running': '🔄', 'success': '✅', 'warning': '⚠️', 'error': '❌'}
        status_map = {
            'start': (symbols['running'], self.style.WARNING),
            'success': (symbols['success'], self.style.SUCCESS),
            'warning': (symbols['warning'], self.style.WARNING),
            'error': (symbols['error'], self.style.ERROR)
        }

        timestamp = datetime.now().strftime("%H:%M:%S")
        if status in status_map:
            symbol, style = status_map[status]
            self.stdout.write(style(f"{timestamp} {symbol} {stage}: {message}"))
        else:
            self.stdout.write(f"{timestamp} ➡️ {stage}: {message}")

    def process_file(self, file_path):
        """处理单个TXT文件"""
        self.print_status("文件处理", f"开始处理: {os.path.basename(file_path)}", "start")

        # 尝试不同的编码
        encodings = ['utf-8', 'gb18030', 'gbk', 'gb2312', 'big5', 'utf-16']
        content = None
        detected_encoding = None

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                detected_encoding = encoding
                break
            except UnicodeDecodeError:
                continue

        if content is None:
            self.print_status("文件读取", f"无法识别文件编码: {file_path}", "error")
            return False

        # 提取书名和作者
        filename = os.path.splitext(os.path.basename(file_path))[0]
        try:
            title, author = filename.split('-')
        except ValueError:
            title = filename
            author = '未知'

        # 处理重复的小说标题
        base_title = title.strip()
        final_title = base_title
        counter = 1
        while Novel.objects.filter(title=final_title).exists():
            final_title = f"{base_title}({counter})"
            counter += 1

        # 查找章节
        chapter_pattern = r'第[一二三四五六七八九十百千万0-9１２３４５６７８９０]+[章節回卷].*?\n'
        chapters = list(re.finditer(chapter_pattern, content))
        chapter_positions = [(m.start(), m.group()) for m in chapters]

        if not chapter_positions:
            self.print_status("章节识别", "未找到任何章节", "error")
            return False

        try:
            # 创建小说
            novel = Novel.objects.create(
                title=final_title,
                author=author.strip(),
                category=Category.objects.get_or_create(name='本地导入')[0],
                intro=content[:200] + '...',
                source_url=f'本地导入: {os.path.basename(file_path)}'
            )

            # 创建章节
            used_titles = set()
            for i, (pos, title) in enumerate(chapter_positions):
                # 获取章节内容
                next_pos = chapter_positions[i + 1][0] if i + 1 < len(chapter_positions) else len(content)
                chapter_content = content[pos:next_pos].strip()

                # 处理重复标题
                original_title = title.strip()
                chapter_title = original_title
                counter = 1
                while chapter_title in used_titles:
                    chapter_title = f"{original_title}({counter})"
                    counter += 1
                used_titles.add(chapter_title)

                try:
                    Chapter.objects.create(
                        novel=novel,
                        title=chapter_title,
                        content=chapter_content
                    )
                except Exception as e:
                    self.print_status("章节创建", f"章节 {chapter_title} 创建失败: {str(e)}", "warning")

            self.print_status(
                "导入完成", 
                f"《{novel.title}》导入成功，共 {len(chapter_positions)} 章 | 编码: {detected_encoding}", 
                "success"
            )
            return True

        except Exception as e:
            self.print_status("小说创建", f"创建失败: {str(e)}", "error")
            return False

    def handle(self, *args, **options):
        folder_path = options['folder_path']
        
        if not os.path.exists(folder_path):
            self.print_status("参数错误", "指定的文件夹不存在", "error")
            return

        self.print_status("开始导入", f"从文件夹 {folder_path} 导入小说", "start")
        
        # 获取所有txt文件
        txt_files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]
        
        if not txt_files:
            self.print_status("文件扫描", "未找到TXT文件", "warning")
            return

        self.print_status("文件扫描", f"找到 {len(txt_files)} 个TXT文件", "success")

        success_count = 0
        for file_name in txt_files:
            file_path = os.path.join(folder_path, file_name)
            if self.process_file(file_path):
                success_count += 1

        self.print_status(
            "导入统计", 
            f"共处理 {len(txt_files)} 个文件，成功导入 {success_count} 本小说",
            "success" if success_count > 0 else "warning"
        ) 