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
import time
from fake_useragent import UserAgent  

# 配置信息
BASE_URL = "https://d3syerwqkywh2y.cloudfront.net/"
LIST_PAGE_URL = "https://d3syerwqkywh2y.cloudfront.net/nov/6/%E6%96%87%E5%AD%A6%E5%B0%8F%E8%AF%B4.html"

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
]

# 更新配置
WAIT_TIME = {
    'min': 2,
    'max': 5,
    'page_min': 5,
    'page_max': 10,
    'click_min': 1,  # 点击等待最小时间
    'click_max': 2   # 点击等待最大时间
}

HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Cache-Control': 'max-age=0',
    'Upgrade-Insecure-Requests': '1'
}

class Command(BaseCommand):
    help = '从 xqbj 网站爬取小说并入库'

    def __init__(self):
        super().__init__()
        self.browser = None
        self.main_page = None
        self.ua = UserAgent()
        self.last_request_time = time.time()

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

    async def random_sleep(self, min_time=None, max_time=None):
        """随机等待"""
        min_time = min_time or WAIT_TIME['min']
        max_time = max_time or WAIT_TIME['max']
        sleep_time = random.uniform(min_time, max_time)
        await asyncio.sleep(sleep_time)

    async def init_browser(self):
        """初始化浏览器"""
        self.print_status("浏览器引擎", "开始初始化", "start")
        try:
            launch_args = {
                'headless': True,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--disable-infobars',
                    '--disable-extensions',
                    '--disable-notifications',
                    '--disable-popup-blocking',
                    '--disable-blink-features=AutomationControlled',
                ]
            }

            self.browser = await launch(**launch_args)
            self.main_page = await self.browser.newPage()
            
            # 设置更多浏览器特征
            await self.main_page.setViewport({'width': random.randint(1024, 1920), 'height': random.randint(768, 1080)})
            await self.main_page.setUserAgent(self.ua.random)
            await self.main_page.setExtraHTTPHeaders(HEADERS)
            await stealth(self.main_page)
            
            # 注入 JavaScript 来模拟真实浏览器环境
            await self.main_page.evaluateOnNewDocument('''() => {
                Object.defineProperty(navigator, 'webdriver', {get: () => false});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = { runtime: {} };
            }''')
            
            self.print_status("浏览器引擎", "初始化完成", "success")
            return True
        except Exception as e:
            self.print_status("浏览器引擎", f"初始化失败: {str(e)}", "error")
            return False

    async def parse_list_page(self):
        """解析列表页并处理小说"""
        page = 1
        
        while True:
            try:
                # 等待列表加载
                await self.main_page.waitForSelector('#xqbj-container .meritvideo-list')
                
                # 获取当前页的所有小说
                novels = await self.main_page.evaluate('''() => {
                    const container = document.querySelector('#xqbj-container .meritvideo-list');
                    if (!container) return [];
                    
                    const items = container.querySelectorAll('.xqbj-list-novel-item');
                    return Array.from(items).map(item => {
                        const links = item.querySelectorAll('a');
                        return {
                            title: links[1].textContent.trim(),
                            url: links[1].href,
                            intro: links[2].textContent.trim()
                        };
                    });
                }''')
                
                if novels and len(novels) > 0:
                    self.print_status("列表解析", f"第{page}页: 找到 {len(novels)} 本小说", "success")
                    
                    # 处理当前页的所有小说
                    for idx, novel in enumerate(novels, 1):
                        self.print_status("进度", f"第{page}页 - 处理第 {idx}/{len(novels)} 本", "info")
                        await self.process_novel(novel)
                        await self.random_sleep(2, 4)  # 小说间短暂等待
                    
                    # 当前页处理完成后，检查是否有下一页
                    next_button = await self.main_page.querySelector('.van-pagination__item--next:not(.van-pagination__item--disabled)')
                    if next_button:
                        await self.random_sleep(3, 5)  # 翻页前较长等待
                        await next_button.click()
                        page += 1
                        self.print_status("页面导航", f"当前页处理完成，正在加载第{page}页", "info")
                        # 等待新页面加载
                        await self.main_page.waitForSelector('#xqbj-container .meritvideo-list')
                        continue
                    else:
                        self.print_status("页面导航", "所有页面处理完成", "success")
                        break
                else:
                    self.print_status("列表解析", "当前页面未找到小说", "warning")
                    break
                
            except Exception as e:
                self.print_status("列表解析", f"处理第{page}页失败: {str(e)}", "error")
                break

    async def process_novel(self, novel_info):
        """处理单本小说"""
        self.print_status("小说处理", f"开始处理: {novel_info['title']}", "start")
        
        try:
            page = await self.browser.newPage()
            await page.setUserAgent(self.ua.random)
            await page.setExtraHTTPHeaders(HEADERS)
            
            try:
                await page.goto(novel_info['url'], {
                    'waitUntil': 'networkidle0',
                    'timeout': 30000
                })
                
                # 等待章节列表加载
                await page.waitForSelector('.list')
                
                # 尝试从各种存储中获取章节列表
                all_chapters = await page.evaluate(r"""() => {
                    function getAllChapters() {
                        const chapters = [];
                        
                        // 1. 检查localStorage
                        try {
                            for (let i = 0; i < localStorage.length; i++) {
                                const key = localStorage.key(i);
                                if (key && (key.includes('chapter') || key.includes('novel'))) {
                                    const data = JSON.parse(localStorage.getItem(key));
                                    if (Array.isArray(data)) {
                                        chapters.push(...data);
                                    }
                                }
                            }
                        } catch (e) {
                            console.error('localStorage error:', e);
                        }
                        
                        // 2. 检查window对象上的数据
                        try {
                            if (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.chapters) {
                                chapters.push(...window.__INITIAL_STATE__.chapters);
                            }
                        } catch (e) {
                            console.error('window state error:', e);
                        }
                        
                        // 3. 检查页面上的隐藏元素
                        try {
                            document.querySelectorAll('script[type="application/json"]').forEach(script => {
                                try {
                                    const data = JSON.parse(script.textContent);
                                    if (data.chapters || data.chapterList) {
                                        chapters.push(...(data.chapters || data.chapterList));
                                    }
                                } catch (e) {}
                            });
                        } catch (e) {
                            console.error('script data error:', e);
                        }
                        
                        // 4. 获取可见章节
                        const visibleChapters = Array.from(document.querySelectorAll('.list a')).map(a => ({
                            title: a.textContent.trim(),
                            url: a.href
                        }));
                        chapters.push(...visibleChapters);
                        
                        // 格式化和去重
                        const uniqueChapters = Array.from(new Set(chapters.map(c => {
                            if (typeof c === 'string') {
                                try { c = JSON.parse(c); } catch (e) {}
                            }
                            return JSON.stringify({
                                title: c.title || c.name || '',
                                url: c.url || c.link || c.href || ''
                            });
                        }))).map(c => JSON.parse(c)).filter(c => c.title && c.url);
                        
                        // 按章节序号排序
                        return uniqueChapters.sort((a, b) => {
                            const numA = parseInt((a.title.match(/\d+/) || [0])[0]);
                            const numB = parseInt((b.title.match(/\d+/) || [0])[0]);
                            return numA - numB;
                        });
                    }
                    
                    return getAllChapters();
                }""")
                
                if not all_chapters:
                    self.print_status("章节检查", "未找到任何章节", "warning")
                    return False

                total_chapters = len(all_chapters)
                self.print_status("章节列表", f"找到 {total_chapters} 个章节", "success")
                
                # 检查小说是否已存在
                novel_exists = await sync_to_async(Novel.objects.filter(title=novel_info['title']).first)()
                
                if novel_exists:
                    # 获取现有章节数和章节标题列表
                    existing_chapters = await sync_to_async(lambda: list(Chapter.objects.filter(novel=novel_exists).values_list('title', flat=True)))()
                    self.print_status("章节信息", f"数据库中已有 {len(existing_chapters)} 章", "info")
                    
                    # 找出需要新增的章节
                    new_chapters = [chapter for chapter in all_chapters if chapter['title'] not in existing_chapters]
                    if not new_chapters:
                        self.print_status("章节对比", "无需更新章节", "info")
                        return True
                        
                    self.print_status("章节对比", f"发现 {len(new_chapters)} 章需要更新", "info")
                    chapters_to_process = new_chapters
                    novel = novel_exists
                else:
                    # 创建新小说
                    get_or_create_category = sync_to_async(Category.objects.get_or_create)
                    category, _ = await get_or_create_category(name='网络小说')
                    
                    create_novel = sync_to_async(Novel.objects.create)
                    novel = await create_novel(
                        title=novel_info['title'],
                        author='未知',
                        category=category,
                        intro=novel_info['intro'][:200],
                        source_url=novel_info['url']
                    )
                    self.print_status("小说创建", "新建小说成功", "success")
                    chapters_to_process = all_chapters

                # 处理需要更新的章节
                for idx, chapter_info in enumerate(chapters_to_process, 1):
                    chapter_page = await self.browser.newPage()
                    await chapter_page.setUserAgent(self.ua.random)
                    await chapter_page.setExtraHTTPHeaders(HEADERS)
                    
                    try:
                        await self.random_sleep()
                        await chapter_page.goto(chapter_info['url'], {
                            'waitUntil': 'networkidle0',
                            'timeout': 30000
                        })
                        
                        content = await chapter_page.evaluate('''() => {
                            const content = document.querySelector('.novel-body');
                            if (!content) return '';
                            return Array.from(content.querySelectorAll('p'))
                                .map(p => p.textContent.trim())
                                .filter(text => text.length > 0)
                                .map(text => '　　' + text)
                                .join('\\n\\n');
                        }''')

                        if content:
                            await sync_to_async(Chapter.objects.create)(
                                novel=novel,
                                title=chapter_info['title'],
                                content=content
                            )
                            self.print_status("章节下载", f"已下载：{chapter_info['title']} ({idx}/{len(chapters_to_process)})", "success")
                        else:
                            self.print_status("章节下载", f"章节内容为空：{chapter_info['title']}", "warning")

                    except Exception as e:
                        self.print_status("章节下载", f"下载失败: {str(e)}", "error")
                    finally:
                        await chapter_page.close()
                        await self.random_sleep(1, 3)

                # 更新小说信息
                current_chapter_count = await sync_to_async(lambda: Chapter.objects.filter(novel=novel).count())()
                update_novel = sync_to_async(lambda n: setattr(n, 'intro', f'共{current_chapter_count}章') or n.save())
                await update_novel(novel)
                
                return True

            finally:
                await page.close()

        except Exception as e:
            self.print_status("小说处理", f"处理失败: {str(e)}", "error")
            return False

    async def run(self):
        """运行爬虫"""
        if not await self.init_browser():
            return

        try:
            # 访问列表页前等待
            await self.random_sleep(WAIT_TIME['page_min'], WAIT_TIME['page_max'])
            await self.main_page.goto(LIST_PAGE_URL, {
                'waitUntil': 'networkidle0',
                'timeout': 30000
            })
            
            # 直接解析和处理列表页
            await self.parse_list_page()

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