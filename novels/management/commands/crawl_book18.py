from django.core.management.base import BaseCommand
from novels.models import Novel, Chapter, Category
from django.utils import timezone
import asyncio
import random
import re
from datetime import datetime
from pyppeteer import launch
from pyppeteer_stealth import stealth
from asgiref.sync import sync_to_async

# 配置信息
CHROME_PATH = r"J:\crawler\chrome-win\chrome.exe"  # 请修改为您的 Chrome 路径
BASE_URL = "https://www.book18.org/"
LIST_PAGE_URL = "https://www.book18.org/zh-hans/category/7"

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
]

class Command(BaseCommand):
    help = '从 book18 网站爬取小说并入库'

    def __init__(self):
        super().__init__()
        self.browser = None
        self.main_page = None

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

    async def init_browser(self):
        """初始化浏览器"""
        self.print_status("浏览器引擎", "开始初始化", "start")
        try:
            launch_args = {
                'executablePath': CHROME_PATH,
                'headless': True,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                ]
            }

            self.browser = await launch(**launch_args)
            self.main_page = await self.browser.newPage()
            await self.main_page.setViewport({'width': 1920, 'height': 1080})
            await self.main_page.setUserAgent(random.choice(USER_AGENTS))
            await stealth(self.main_page)
            
            self.print_status("浏览器引擎", "初始化完成", "success")
            return True
        except Exception as e:
            self.print_status("浏览器引擎", f"初始化失败: {str(e)}", "error")
            return False

    async def navigate_page(self, url, page_type="列表页", page=None):
        """页面导航"""
        if page is None:
            page = self.main_page
            
        self.print_status(page_type, f"开始访问: {url}", "start")
        try:
            await page.goto(url, {'waitUntil': 'networkidle0', 'timeout': 30000})
            self.print_status(page_type, "页面加载完成", "success")
            return True
        except Exception as e:
            self.print_status(page_type, f"页面加载失败: {str(e)}", "error")
            return False

    async def process_novel(self, novel_url, title):
        """处理单本小说"""
        self.print_status("小说处理", f"开始处理: {title[:15]}...", "start")

        page = None
        try:
            # ================= 检查现有小说 =================
            novel_exists = await sync_to_async(Novel.objects.filter(title=title).first)()
            novel = novel_exists

            if novel_exists:
                # 获取现有章节数
                chapter_count = await sync_to_async(
                    lambda: Chapter.objects.filter(novel=novel_exists).count()
                )()
                self.print_status("章节信息", f"当前章节数：{chapter_count}", "info")
            else:
                # 创建新小说
                get_or_create_category = sync_to_async(Category.objects.get_or_create)
                category, _ = await get_or_create_category(name='网络小说')
                
                create_novel = sync_to_async(Novel.objects.create)
                novel = await create_novel(
                    title=title,
                    author='未知',
                    category=category,
                    intro="正在获取...",
                    source_url=novel_url
                )
                chapter_count = 0

            # ================= 页面初始化和导航 =================
            page = await self.browser.newPage()
            await page.setUserAgent(random.choice(USER_AGENTS))
            await page.setExtraHTTPHeaders({
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br'
            })
            await stealth(page)

            if not await self.navigate_page(novel_url, "小说页面", page):
                return False

            try:
                # 先尝试获取章节列表
                chapter_links = await page.evaluate('''() => {
                    const links = document.querySelectorAll('.chapters a[href*="/fiction/"]');
                    return Array.from(links).map(a => ({
                        title: a.textContent.trim(),
                        url: a.href
                    }));
                }''')

                # 如果没有找到章节列表，尝试直接获取内容
                if not chapter_links:
                    self.print_status("章节检查", "未找到章节列表，尝试直接获取内容", "warning")
                    
                    # 检查是否有内容
                    content_js = '''() => {
                        const content = document.querySelector('#content');
                        if (!content) return '';
                        
                        // 移除所有广告 span
                        content.querySelectorAll('span').forEach(span => {
                            if (span.textContent.includes('广告') || 
                                span.textContent.includes('APP') || 
                                span.textContent.includes('http') ||
                                span.textContent.includes('小黄书')) {
                                span.remove();
                            }
                        });
                        
                        // 获取并过滤段落
                        return Array.from(content.querySelectorAll('p'))
                            .map(p => {
                                // 克隆节点以避免修改原始DOM
                                const pClone = p.cloneNode(true);
                                
                                // 移除所有广告相关的 span
                                pClone.querySelectorAll('span').forEach(span => {
                                    if (span.textContent.includes('广告') || 
                                        span.textContent.includes('APP') || 
                                        span.textContent.includes('http') ||
                                        span.textContent.includes('小黄书')) {
                                        span.remove();
                                    }
                                });
                                
                                const text = pClone.textContent.trim();
                                
                                // 过滤掉广告文本
                                if (text.includes('广告') || 
                                    text.includes('APP') || 
                                    text.includes('http') || 
                                    text.includes('小黄书') ||
                                    text.includes('下载') ||
                                    text.includes('关注')) {
                                    return '';
                                }
                                
                                return text;
                            })
                            .filter(text => text.length > 20)  // 过滤掉太短的段落
                            .map(text => '　　' + text)
                            .join('\\n\\n');
                    }'''

                    content = await page.evaluate(content_js)

                    if content:
                        # 如果是新小说或没有章节的小说，创建第一章
                        if chapter_count == 0:
                            create_chapter = sync_to_async(Chapter.objects.create)
                            await create_chapter(
                                novel=novel,
                                title='第1章',
                                content=content
                            )
                            self.print_status("章节创建", "创建第1章", "success")
                        return True
                    else:
                        self.print_status("内容检查", "未找到有效内容", "error")
                        return False

                # 如果找到了章节列表
                total_chapters = len(chapter_links)
                self.print_status("章节检查", f"发现 {total_chapters} 个章节", "info")

                # 确定开始下载的章节索引
                start_index = chapter_count
                create_chapter = sync_to_async(Chapter.objects.create)

                # 下载新章节
                for idx, chapter_info in enumerate(chapter_links[start_index:], start=start_index + 1):
                    chapter_page = await self.browser.newPage()
                    try:
                        await chapter_page.goto(chapter_info['url'], {'waitUntil': 'networkidle0'})
                        content = await chapter_page.evaluate(content_js)

                        if content:
                            await create_chapter(
                                novel=novel,
                                title=f'第{idx}章',
                                content=content
                            )
                            self.print_status("章节下载", f"已下载：第{idx}/{total_chapters}章", "success")
                    except Exception as e:
                        self.print_status("章节下载", f"第{idx}章下载失败: {str(e)}", "error")
                    finally:
                        await chapter_page.close()
                        await asyncio.sleep(1)

                # 更新小说信息
                update_novel = sync_to_async(lambda n: setattr(n, 'intro', f'共{total_chapters}章') or n.save())
                await update_novel(novel)
                
                return True

            except Exception as e:
                self.print_status("内容处理", f"处理失败: {str(e)}", "error")
                return False

        except Exception as e:
            self.print_status("处理流程", f"处理失败: {str(e)}", "error")
            return False
        finally:
            if page:
                try:
                    await asyncio.shield(page.close())
                except Exception as e:
                    self.print_status("页面关闭", f"关闭异常: {str(e)}", "warning")
                await asyncio.sleep(1)

    async def run(self):
        """运行爬虫"""
        if not await self.init_browser():
            return

        try:
            if not await self.navigate_page(LIST_PAGE_URL):
                return

            # 获取小说列表
            novels = await self.main_page.evaluate('''() => {
                return Array.from(document.querySelectorAll('ul.list-group li a[href*="/zh-hans/article/"]'))
                    .map(a => ({
                        title: a.textContent.trim(),
                        url: a.href
                    }));
            }''')

            self.print_status("小说列表", f"找到 {len(novels)} 本小说", "success")

            # 处理每本小说
            for idx, novel in enumerate(novels, 1):
                self.print_status("进度", f"处理第 {idx}/{len(novels)} 本", "start")
                await self.process_novel(novel['url'], novel['title'])
                await asyncio.sleep(random.uniform(2, 5))

        finally:
            if self.browser:
                await self.browser.close()

    def handle(self, *args, **options):
        """命令入口"""
        self.print_status("爬虫启动", "开始运行", "start")
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            self.print_status("系统中断", "用户终止操作", "warning")
        except Exception as e:
            self.print_status("系统错误", f"未处理的异常: {str(e)}", "error")
        finally:
            self.print_status("爬虫结束", "任务完成", "success") 