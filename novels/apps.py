from django.apps import AppConfig

class NovelsConfig(AppConfig):
    """
    在这个充满想象力的空间里
    每一个应用都是一个独特的艺术品
    让我们为它注入灵魂
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'novels'

    def ready(self):
        """当应用准备就绪时，确保所有模板标签都被正确加载"""
        # 导入模板标签，让它们在Django的画布上绽放
        import novels.templatetags.novel_filters
