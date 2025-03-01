
import os
import random
from django.conf import settings

def get_random_cover():
    """为每一本无面之书描绘独特的容颜"""
    covers_dir = os.path.join(settings.MEDIA_ROOT, 'covers')
    default_cover = f'{settings.STATIC_URL}css/default_cover.jpg'
    
    try:
        # 确保covers目录存在
        if not os.path.exists(covers_dir):
            os.makedirs(covers_dir, exist_ok=True)
            return default_cover
            
        # 收集所有可用的画作
        covers = [f for f in os.listdir(covers_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        if not covers:
            return default_cover
            
        # 随机选择一幅画作
        selected_cover = random.choice(covers)
        return f'{settings.MEDIA_URL}covers/{selected_cover}'
        
    except Exception as e:
        return default_cover