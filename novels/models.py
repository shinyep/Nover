from django.db import models
from django.utils import timezone
import re

# 分类模型
class Category(models.Model):
    name = models.CharField(max_length=20, verbose_name="分类名称")

    def __str__(self):
        return self.name  # 返回分类名称

# 小说模型
class Novel(models.Model):
    title = models.CharField(max_length=255, unique=True, verbose_name='标题')
    author = models.CharField(max_length=50, verbose_name="作者")
    cover = models.URLField(max_length=500, null=True, blank=True, verbose_name='封面')
    _default_cover_cache = None  # 内存中的封面缓存
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='novels', verbose_name="分类")
    intro = models.TextField(verbose_name="简介")
    is_recommend = models.BooleanField(default=False, verbose_name="是否推荐")
    source_url = models.URLField(max_length=500, verbose_name='来源链接')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '小说'
        verbose_name_plural = '小说'
        ordering = ['-updated_at']

    def __str__(self):
        return self.title

    def chapter_count(self):
        return self.chapters.count()
    chapter_count.short_description = '章节数'

# 章节模型
class Chapter(models.Model):
    novel = models.ForeignKey(Novel, on_delete=models.CASCADE, related_name='chapters', verbose_name='小说')
    title = models.CharField(max_length=255, verbose_name='章节标题')
    content = models.TextField(verbose_name='章节内容')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    order = models.IntegerField(default=0, verbose_name='排序', db_index=True)

    class Meta:
        verbose_name = '章节'
        verbose_name_plural = '章节'
        ordering = ['order', 'id']
        unique_together = ['novel', 'title']

    def __str__(self):
        return f"{self.novel.title} - {self.title}"

    def content_preview(self):
        return self.content[:50] + "..." if len(self.content) > 50 else self.content
    content_preview.short_description = "内容预览"

    def clean_content(self):
        """清理章节内容中的广告"""
        content = self.content
        
        # 获取用户添加的过滤词
        from django.apps import apps
        FilterWord = apps.get_model('novels', 'FilterWord')
        filter_words = FilterWord.objects.values_list('word', flat=True)
        
        # 应用用户添加的过滤词
        for word in filter_words:
            content = content.replace(word, '')
        
        # 规范化换行符
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        
        # 处理段落
        paragraphs = []
        for line in content.split('\n'):
            line = line.strip()
            if line:  # 只保留非空行
                # 确保每个段落都有缩进（只用一个全角空格）
                if not line.startswith('　'):
                    line = '　' + line
                paragraphs.append(line)
        
        # 返回处理后的内容
        return '\n'.join(paragraphs)

    def save(self, *args, **kwargs):
        # 保存前自动清理内容
        self.content = self.clean_content()
        super().save(*args, **kwargs)

class FilterWord(models.Model):
    word = models.CharField(max_length=100, unique=True, verbose_name='过滤词')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '过滤词'
        verbose_name_plural = '过滤词管理'
        ordering = ['-created_at']

    def __str__(self):
        return self.word
