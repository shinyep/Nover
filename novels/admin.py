from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html
from .models import Category, Novel, Chapter, FilterWord
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
import re
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
import os
import io

# 章节内联编辑
class ChapterInline(admin.TabularInline):
    model = Chapter
    fields = ('title', 'content_preview')  # 移除 order 字段
    readonly_fields = ('content_preview',)
    extra = 0

    def content_preview(self, obj):
        content = obj.content or ""
        return content[:50] + '...' if len(content) > 50 else content
    content_preview.short_description = "内容预览"

# 小说管理
@admin.register(Novel)
class NovelAdmin(admin.ModelAdmin):
    # 列表页配置
    list_display = ('title', 'author', 'category', 'cover_thumbnail', 'is_recommend', 'chapter_count', 'updated_at')
    search_fields = ('title', 'author')
    list_filter = ('category', 'is_recommend')
    inlines = [ChapterInline]

    # 封面缩略图显示
    def cover_thumbnail(self, obj):
        if obj.cover:
            return format_html('<img src="{}" style="max-height:80px;"/>', obj.cover.url)
        return "无封面"
    cover_thumbnail.short_description = '封面'

    # 批量操作
    actions = ['mark_recommend', 'unmark_recommend', 'delete_empty_novels']

    def mark_recommend(self, request, queryset):
        updated_count = queryset.update(is_recommend=True)
        self.message_user(request, f"{updated_count} 部作品已成功推荐！")
    mark_recommend.short_description = "批量推荐选中作品"

    def unmark_recommend(self, request, queryset):
        updated_count = queryset.update(is_recommend=False)
        self.message_user(request, f"{updated_count} 部作品已取消推荐！")
    unmark_recommend.short_description = "取消推荐选中作品"

    def delete_empty_novels(self, request, queryset):
        # 获取没有章节的小说
        empty_novels = queryset.annotate(
            chapter_count=Count('chapters')
        ).filter(chapter_count=0)
        
        # 记录删除数量
        empty_count = empty_novels.count()
        
        # 删除空小说
        empty_novels.delete()
        
        # 显示消息
        if empty_count > 0:
            self.message_user(
                request, 
                f"已删除 {empty_count} 部没有章节的小说。",
                level='SUCCESS'
            )
        else:
            self.message_user(
                request,
                "选中的小说都有章节，没有需要删除的。",
                level='INFO'
            )
    delete_empty_novels.short_description = "删除没有章节的小说"

    def chapter_count(self, obj):
        return obj.chapters.count()
    chapter_count.short_description = '章节数'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('upload-txt/', self.admin_site.admin_view(self.upload_txt_view), name='novel-upload-txt'),
        ]
        return custom_urls + urls

    def upload_txt_view(self, request):
        if request.method == 'POST':
            if 'txt_file' not in request.FILES:
                messages.error(request, '请选择TXT文件')
                return redirect('..')
            
            txt_file = request.FILES['txt_file']
            if not txt_file.name.endswith('.txt'):
                messages.error(request, '只支持TXT文件')
                return redirect('..')
            
            # 尝试不同的编码
            encodings = ['utf-8', 'gb18030', 'gbk', 'gb2312', 'big5', 'utf-16']
            content = None
            detected_encoding = None
            
            try:
                # 读取文件内容
                file_content = txt_file.read()
                
                # 尝试不同的编码解码文件内容
                for encoding in encodings:
                    try:
                        content = file_content.decode(encoding)
                        detected_encoding = encoding
                        break
                    except UnicodeDecodeError:
                        continue
                
                if content is None:
                    messages.error(request, f'无法识别文件编码，已尝试以下编码：{", ".join(encodings)}')
                    return redirect('..')
                
                # 提取书名和作者（假设文件名格式为：书名-作者.txt）
                filename = os.path.splitext(txt_file.name)[0]
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
                
                # 查找章节（支持更多章节标记格式）
                chapter_pattern = r'第[一二三四五六七八九十百千万0-9１２３４５６７８９０]+[章節回卷].*?\n'
                chapters = re.finditer(chapter_pattern, content)
                chapter_positions = [(m.start(), m.group()) for m in chapters]
                
                if not chapter_positions:
                    messages.error(request, '未找到任何章节，请确保章节标题格式正确（如：第一章、第1章）')
                    return redirect('..')
                
                # 创建小说
                novel = Novel.objects.create(
                    title=final_title,  # 使用处理后的标题
                    author=author.strip(),
                    category_id=1,  # 默认分类，可以根据需要修改
                    intro=content[:200] + '...',  # 使用开头作为简介
                    source_url='本地导入'  # 标记来源
                )
                
                # 创建章节
                used_titles = set()  # 用于跟踪已使用的标题
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
                        messages.warning(request, f'章节"{chapter_title}"导入失败：{str(e)}')
                
                messages.success(
                    request, 
                    f'成功导入小说《{novel.title}》，共 {len(chapter_positions)} 章。'
                    f'文件编码：{detected_encoding}'
                )
                
            except Exception as e:
                messages.error(request, f'处理文件时出错：{str(e)}')
            
            return redirect('..')
        
        # GET 请求显示上传表单
        return render(request, 'admin/novel/upload_txt.html')

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['show_upload_button'] = True
        return super().changelist_view(request, extra_context=extra_context)

# 分类管理
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'novel_count')  # 自定义显示的字段
    search_fields = ('name',)  # 添加搜索功能

    def get_queryset(self, request):
        # 使用 annotate 添加注解字段
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(novel_count=Count('novels'))
        return queryset

    def novel_count(self, obj):
        return obj.novel_count  # 直接从注解字段获取值
    novel_count.short_description = '小说数量'
    novel_count.admin_order_field = 'novel_count'  # 支持按小说数量排序

# 章节管理
@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ('novel', 'title', 'content_preview', 'created_at')
    search_fields = ('title', 'content')
    list_filter = ('novel',)
    actions = ['clean_content', 'reprocess_paragraphs']

    def clean_content(self, request, queryset):
        for chapter in queryset:
            chapter.content = chapter.clean_content()
            chapter.save()
        self.message_user(request, f'已成功清理 {queryset.count()} 个章节的内容')
    clean_content.short_description = '清理选中章节的广告内容'

    def reprocess_paragraphs(self, request, queryset):
        success_count = 0
        for chapter in queryset:
            try:
                # 获取原始内容
                content = chapter.content
                
                # 移除所有现有的段落标记
                content = content.replace('[P]', '').replace('[/P]', '')
                
                # 规范化换行符
                content = content.replace('\r\n', '\n').replace('\r', '\n')
                
                # 分割并处理段落
                paragraphs = []
                current_paragraph = []
                
                for line in content.split('\n'):
                    line = line.strip()
                    if line:
                        # 如果是新的段落开始（以全角空格开头）
                        if line.startswith('　　'):
                            # 如果有累积的段落，先保存它
                            if current_paragraph:
                                paragraphs.append(''.join(current_paragraph))
                                current_paragraph = []
                            current_paragraph.append(line)
                        else:
                            # 如果没有缩进，添加缩进
                            if not current_paragraph:
                                line = '　　' + line
                            current_paragraph.append(line)
                
                # 处理最后一个段落
                if current_paragraph:
                    paragraphs.append(''.join(current_paragraph))
                
                # 使用双换行符连接段落
                chapter.content = '\n\n'.join(paragraphs)
                chapter.save()
                success_count += 1
                
            except Exception as e:
                self.message_user(request, f'处理章节 "{chapter.title}" 时出错: {str(e)}', level='ERROR')
        
        self.message_user(request, f'成功重新处理了 {success_count} 个章节的段落格式')
    reprocess_paragraphs.short_description = '重新处理选中章节的段落格式'

    def content_preview(self, obj):
        content = obj.content or ""
        return content[:50] + '...' if len(content) > 50 else content
    content_preview.short_description = "内容预览"

@admin.register(FilterWord)
class FilterWordAdmin(admin.ModelAdmin):
    list_display = ['word', 'created_at', 'updated_at']
    search_fields = ['word']
    list_per_page = 20
    actions = ['execute_cleaning']

    def execute_cleaning(self, request, queryset):
        if not queryset.exists():
            self.message_user(request, '请至少选择一个过滤词！', level='WARNING')
            return
        
        # 获取所有章节
        chapters = Chapter.objects.all()
        cleaned_count = 0
        total_count = chapters.count()
        
        try:
            # 获取选中的过滤词
            selected_words = list(queryset.values_list('word', flat=True))
            
            for chapter in chapters:
                original_content = chapter.content
                cleaned_content = original_content
                
                # 只应用选中的过滤词
                for word in selected_words:
                    cleaned_content = cleaned_content.replace(word, '')
                
                if original_content != cleaned_content:
                    chapter.content = cleaned_content
                    chapter.save()
                    cleaned_count += 1
            
            self.message_user(
                request, 
                f'清理完成！总共 {total_count} 个章节，清理了 {cleaned_count} 个章节的内容。',
                level='SUCCESS'
            )
        except Exception as e:
            self.message_user(
                request,
                f'清理过程中发生错误：{str(e)}',
                level='ERROR'
            )

    execute_cleaning.short_description = '使用选中的过滤词清理内容'