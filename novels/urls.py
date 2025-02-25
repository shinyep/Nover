from django.urls import path
from . import views  # 必须导入views

app_name = 'novels' 

urlpatterns = [
    path('', views.index, name='index'),
    path('novel/<int:novel_id>/', views.novel_detail, name='novel_detail'),
    path('chapter/<int:chapter_id>/', views.chapter_detail, name='chapter_detail'),
    path('category/<int:category_id>/', views.category, name='category'),
    path('latest/', views.latest_novels_view, name='latest_novels'),  # 最新小说列表
    path('novel/<int:novel_id>/download/', views.download_novel, name='download_novel'),
]
