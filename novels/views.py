from django.shortcuts import render, get_object_or_404
from django.core.cache import cache
from django.db import DatabaseError
from .models import Novel, Chapter, Category, FilterWord
from django.core.paginator import Paginator
from django.views.generic import DetailView
from django.http import HttpResponse
import os
from urllib.parse import quote
from django.db.models import Q

def get_common_data():
    """公共上下文数据，带缓存优化"""
    from django.db.models import Count
    
    # 获取推荐小说（带缓存）
    recommend_novels = cache.get('recommend_novels')
    if not recommend_novels:
        recommend_novels = Novel.objects.filter(is_recommend=True)[:3]
        cache.set('recommend_novels', recommend_novels, 1800)
    
    # 获取分类及对应小说数量
    categories = Category.objects.annotate(
        novel_count=Count('novels')
    ).order_by('-novel_count')
    
    return {
        'categories': categories,
        'recommend_novels': recommend_novels
    }

def index(request):
    # 获取推荐小说
    recommended_novels = Novel.objects.filter(is_recommend=True).order_by('-updated_at')[:6]
    
    # 获取最新小说
    latest_novels = Novel.objects.order_by('-created_at')[:12]
    
    # 获取最新章节
    latest_chapters = Chapter.objects.select_related('novel').order_by('-created_at')[:10]
    
    # 获取所有分类
    categories = Category.objects.all()
    
    context = {
        'recommended_novels': recommended_novels,
        'latest_novels': latest_novels,
        'latest_chapters': latest_chapters,
        'categories': categories,
    }
    
    return render(request, 'novels/index.html', context)

def category(request, category_id):
    category = get_object_or_404(Category, pk=category_id)
    novel_list = Novel.objects.filter(category=category).select_related('category')
    
    # 分页逻辑
    paginator = Paginator(novel_list, 12)  # 每页12条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'category': category,
        'page_obj': page_obj,
    }
    context.update(get_common_data())
    return render(request, 'novels/category.html', context)

def novel_detail(request, novel_id):
    novel = get_object_or_404(Novel, id=novel_id)
    # 确保按order字段排序
    chapters = novel.chapters.all().order_by('order', 'id')
    
    context = {
        'novel': novel,
        'chapters': chapters,
    }
    
    return render(request, 'novels/novel_detail.html', context)

def chapter_detail(request, chapter_id):
    chapter = Chapter.objects.select_related('novel').get(id=chapter_id)
    
    # 清理内容
    chapter.content = chapter.clean_content()
    
    # 获取上一章和下一章
    prev_chapter = Chapter.objects.filter(
        novel=chapter.novel,
        id__lt=chapter.id
    ).order_by('-id').first()
    
    next_chapter = Chapter.objects.filter(
        novel=chapter.novel,
        id__gt=chapter.id
    ).order_by('id').first()
    
    context = {
        'chapter': chapter,
        'prev_chapter': prev_chapter,
        'next_chapter': next_chapter,
    }
    
    return render(request, 'novels/chapter_detail.html', context)

def latest_novels_view(request):
    # 获取最新的小说，使用 updated_at 替代 update_time
    latest_novels = Novel.objects.order_by('-updated_at')[:10]  # 取前10本最新小说
    return render(request, 'novels/latest_novels.html', {'latest_novels': latest_novels})

def filter_content(content):
    filter_words = FilterWord.objects.all()
    filtered_content = content
    for word in filter_words:
        filtered_content = filtered_content.replace(word.word, '*' * len(word.word))
    return filtered_content

class ChapterDetailView(DetailView):
    model = Chapter
    template_name = 'novels/chapter.html'
    context_object_name = 'chapter'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        chapter = self.get_object()
        # 过滤内容
        chapter.content = filter_content(chapter.content)
        # ... 其他代码 ...
        return context

def download_novel(request, novel_id):
    """下载小说"""
    try:
        novel = Novel.objects.prefetch_related('chapters').get(id=novel_id)
        
        # 生成文件内容
        content = [
            f"{novel.title}\n",
            f"作者：{novel.author}\n",
            f"简介：{novel.intro}\n",
            "=" * 50 + "\n\n"
        ]
        
        # 添加所有章节
        for chapter in novel.chapters.all():
            content.extend([
                f"{chapter.title}\n\n",
                f"{chapter.content}\n\n",
                "=" * 30 + "\n\n"
            ])
        
        # 创建响应
        response = HttpResponse(content_type='application/octet-stream')  # 修改content type
        
        # 处理中文文件名
        filename = f"{novel.title}.txt"
        encoded_filename = quote(filename)  # URL编码文件名
        
        # 添加正确的响应头
        response['Content-Disposition'] = f'attachment; filename="{encoded_filename}"; filename*=utf-8\'\'{encoded_filename}'
        response['Content-Length'] = len(''.join(content).encode('utf-8'))
        
        # 写入内容
        response.write(''.join(content))
        return response
        
    except Novel.DoesNotExist:
        return HttpResponse("小说不存在", status=404)
    except Exception as e:
        return HttpResponse(f"下载失败：{str(e)}", status=500)

def search(request):
    """搜索小说"""
    query = request.GET.get('q', '')
    
    if query:
        # 搜索小说标题和作者
        novels = Novel.objects.filter(
            Q(title__icontains=query) | 
            Q(author__icontains=query)
        ).distinct()
        
        # 搜索章节标题
        chapters = Chapter.objects.filter(
            title__icontains=query
        ).select_related('novel').distinct()
    else:
        novels = Novel.objects.none()
        chapters = Chapter.objects.none()
    
    context = {
        'query': query,
        'novels': novels,
        'chapters': chapters,
        'novel_count': novels.count(),
        'chapter_count': chapters.count(),
    }
    context.update(get_common_data())
    
    return render(request, 'novels/search_results.html', context)
