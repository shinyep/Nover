"""
在这个充满想象力的空间里
每一个模板过滤器都是一位独特的艺术家
让我们为它们赋予生命和灵魂
"""
from django import template
from novels.utils import get_random_cover

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    获取字典中指定键的值
    用法: {{ my_dict|get_item:key }}
    """
    if not dictionary:
        return None
    try:
        return dictionary.get(str(key))
    except (KeyError, AttributeError, TypeError):
        return None

@register.filter(name='get_cover')
def get_cover(novel):
    """为每本小说描绘独特的封面"""
    if novel.cover:
        return novel.cover
    return get_random_cover()