from django.core.management.base import BaseCommand
from novels.models import Novel, Chapter, Category  # 请根据您的实际模型导入
from datetime import datetime
from django.utils import timezone  # 添加这个导入
import asyncio
from xchina import Book18Crawler, print_status, LIST_PAGE_URL, USER_AGENTS  # 添加 USER_AGENTS
from asgiref.sync import sync_to_async  # 添加这个导入
import random
import re

class Command(BaseCommand):
    help = '从xchina爬取小说内容'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('开始爬取小说...'))
        
        # 运行爬虫
        crawler = Book18Crawler()
        try:
            if hasattr(asyncio, 'run'):
                asyncio.run(self._run_crawler(crawler))
            else:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._run_crawler(crawler))
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('用户中断爬虫操作'))
        
        self.stdout.write(self.style.SUCCESS('爬虫任务完成'))

    async def _run_crawler(self, crawler):
        if not await crawler.init_browser():
            return

        try:
            # 使用导入的 LIST_PAGE_URL
            if not await crawler.navigate_page(LIST_PAGE_URL):
                return

            articles = await crawler.parse_list_page()
            if not articles:
                print_status("流程终止", "未找到有效文章", "warning")
                return

            for idx, article in enumerate(articles, 1):
                print(f"\n▶ 文章进度 ({idx}/{len(articles)})")
                await self.process_article(crawler, article)

        finally:
            if crawler.browser:
                await crawler.browser.close()

    async def process_article(self, crawler, article):
        try:
            now = timezone.now()
            get_or_create_category = sync_to_async(Category.objects.get_or_create)
            default_category, _ = await get_or_create_category(name='默认分类')
            
            # 创建或获取小说
            get_or_create_novel = sync_to_async(Novel.objects.get_or_create)
            novel, created = await get_or_create_novel(
                title=article['title'],
                defaults={
                    'source_url': article['url'],
                    'created_at': now,
                    'author': '未知',
                    'category': default_category,
                    'intro': '暂无简介',
                }
            )

            if not created:
                novel.updated_at = now
                save_novel = sync_to_async(novel.save)
                await save_novel()
                print_status("数据入库", f"更新小说: {article['title']}", "start")
            else:
                print_status("数据入库", f"新增小说: {article['title']}", "success")

            # 获取章节内容
            page = await crawler.browser.newPage()
            try:
                await page.setUserAgent(random.choice(USER_AGENTS))

                if not await crawler.navigate_page(article['url'], "章节列表页", page):
                    return

                # 等待章节列表加载
                await page.waitForSelector('div.chapters', {'timeout': 30000})

                # 提取所有章节链接
                chapter_links = await page.querySelectorAll('div.chapters a[href*="/fiction/id-"]')
                if not chapter_links:
                    print_status("章节提取", "未找到章节链接", "warning")
                    return

                for i, chapter in enumerate(chapter_links, 1):
                    chapter_url = await page.evaluate('(el) => el.href', chapter)
                    chapter_title = await page.evaluate('(el) => el.textContent.trim()', chapter)
                    print_status("章节处理", f"处理章节 {i}: {chapter_title}", "start")

                    # 检查章节是否已存在
                    chapter_exists = sync_to_async(Chapter.objects.filter(novel=novel, title=chapter_title).exists)
                    if await chapter_exists():
                        print_status("章节处理", f"章节已存在: {chapter_title}", "warning")
                        continue

                    chapter_page = None
                    try:
                        chapter_page = await crawler.browser.newPage()
                        await chapter_page.setUserAgent(random.choice(USER_AGENTS))
                        
                        if not await crawler.navigate_page(chapter_url, "章节页", chapter_page):
                            print_status("章节处理", f"章节 {i}: 加载失败，跳过", "warning")
                            continue

                        # 等待正文加载
                        await chapter_page.waitForSelector('div.fiction-body div.content', {'timeout': 30000})

                        # 提取章节正文
                        content = await chapter_page.evaluate('''() => {
                            const contentElement = document.querySelector('div.fiction-body div.content');
                            if (!contentElement) return '';

                            const paragraphs = contentElement.getElementsByTagName('p');
                            if (!paragraphs || paragraphs.length === 0) return '';

                            let result = [];
                            for (let p of paragraphs) {
                                const text = p.innerText.trim();
                                if (text.length > 0) {
                                    result.push('　　' + text);
                                }
                            }
                            return result.join('\\n\\n');
                        }''')

                        if content:
                            content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
                            content = re.sub(r'^关注.*?下载APP$|^广告.*?$|^看精彩成人小说上《小黄书》：https://xchina\.store$|^看精彩成人小说上《小黄书》.*?$', '', content, flags=re.MULTILINE)
                            content = re.sub(r'\n{4,}', '\n\n', content)
                            
                            # 保存到数据库
                            create_chapter = sync_to_async(Chapter.objects.create)
                            await create_chapter(
                                novel=novel,
                                title=chapter_title,
                                content=content,
                                created_at=now
                            )
                            print_status("数据入库", f"新增章节: {chapter_title}", "success")
                        else:
                            print_status("章节处理", f"章节 {i}: {chapter_title} 未找到正文", "warning")

                    except Exception as e:
                        print_status("章节处理", f"章节 {i}: 处理异常 - {str(e)}", "error")
                        continue
                    finally:
                        if chapter_page:
                            await chapter_page.close()
                        await asyncio.sleep(random.uniform(2, 4))

            finally:
                if page:
                    await page.close()

        except Exception as e:
            print_status("文章处理", f"处理失败: {str(e)}", "error") 