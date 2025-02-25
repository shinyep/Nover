# -*- coding: utf-8 -*-
import os
import asyncio
import random
import re
from pyppeteer import launch
from pyppeteer_stealth import stealth
from urllib.parse import urljoin
from datetime import datetime
import pymysql
from pymysql.cursors import DictCursor

CHROME_PATH = r"J:\crawler\chrome-win\chrome.exe"
BASE_URL = "https://xchina.co/"
LIST_PAGE_URL = "https://xchina.co/fictions.html"

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
]

LOG_PREFIX = "[BOOK18] "

# 修改数据库配置
DB_CONFIG = {
    'host': '127.0.0.1',  # 数据库服务器地址
    'user': 'tdnsg',      # 数据库用户名
    'password': '123456', # 数据库密码
    'db': 'novel_db',     # 数据库名
    'charset': 'utf8mb4',
    'cursorclass': DictCursor
}

def print_status(stage, message, status=None):
    symbols = {'running': '🔄', 'success': '✅', 'warning': '⚠️', 'error': '❌'}
    status_map = {
        'start': (symbols['running'], '35m'),
        'success': (symbols['success'], '32m'),
        'warning': (symbols['warning'], '33m'),
        'error': (symbols['error'], '31m')
    }

    timestamp = datetime.now().strftime("%H:%M:%S")
    if status in status_map:
        symbol, color = status_map[status]
        print(f"\033[1;{color}{LOG_PREFIX}{timestamp} {symbol} {stage}: {message}\033[0m")
    else:
        print(f"{LOG_PREFIX}{timestamp} ➡️ {stage}: {message}")


class Book18Crawler:
    def __init__(self):
        self.browser = None
        self.main_page = None
        self.db = None
        self.cursor = None

    async def init_browser(self):
        print_status("浏览器引擎", "开始初始化", "start")
        try:
            launch_args = {
                'executablePath': CHROME_PATH,
                'headless': True,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--window-size=1920,1080',
                    '--disable-infobars',
                    '--disable-dev-shm-usage',
                    '--disable-application-cache',
                    '--disable-gpu',
                    '--single-process'
                ],
                'ignoreHTTPSErrors': True
            }

            print_status("浏览器参数", f"启动参数: {launch_args['args']}")
            self.browser = await launch(**launch_args)

            self.main_page = await self.browser.newPage()
            await self.main_page.setViewport({'width': 1920, 'height': 1080})

            ua = random.choice(USER_AGENTS)
            await self.main_page.setUserAgent(ua)
            await stealth(self.main_page)
            print_status("用户代理", f"已设置: {ua[:50]}...")
            print_status("浏览器引擎", "初始化完成", "success")
            return True

        except Exception as e:
            print_status("浏览器引擎", f"初始化失败: {str(e)}", "error")
            return False

    async def navigate_page(self, url, page_type="列表页", page=None):
        if page is None:
            page = self.main_page
        print_status(page_type, f"开始访问 {url}", "start")
        try:
            start_time = datetime.now()
            await page.goto(url, {'waitUntil': 'networkidle2', 'timeout': 60000})
            cost = (datetime.now() - start_time).total_seconds()
            print_status(page_type, f"加载完成 | 耗时 {cost:.1f}s", "success")
            return True

        except Exception as e:
            print_status(page_type, f"加载失败: {type(e).__name__}", "error")
            return False

    async def parse_list_page(self):
        print_status("列表解析", "开始分析页面结构", "start")
        all_articles = []
        max_pages = 5

        try:
            visited_urls = set()
            while max_pages > 0:
                current_url = await self.main_page.evaluate('window.location.href')
                if current_url in visited_urls:
                    print_status("分页终止", "检测到重复页面", "warning")
                    break
                visited_urls.add(current_url)

                await self.main_page.waitForFunction(
                    'document.querySelectorAll("div.left a[href*=\'/fiction/id-\']").length > 0 || document.querySelectorAll("div.recommend a[href*=\'/fiction/id-\']").length > 0',
                    {'timeout': 60000}
                )
                await self.main_page.screenshot({'path': 'list_page_debug.png'})

                book_items = await self.main_page.querySelectorAll('a[href*="/fiction/id-"]')
                if not book_items:
                    print_status("列表解析", "未找到书籍条目", "error")
                    return []

                articles = []
                for item in book_items:
                    try:
                        title_element = await item.querySelector('div > div:nth-child(2) > div:nth-child(1)')
                        if title_element:
                            title = await self.main_page.evaluate('(el) => el.textContent.trim()', title_element)
                        else:
                            title = await self.main_page.evaluate(r'(el) => el.textContent.trim().replace(/^\d+\s*/, "")', item)

                        url = await self.main_page.evaluate('(el) => el.href', item)

                        if title and '/fiction/id-' in url:
                            articles.append({'title': title[:200], 'url': url})
                            print_status("列表解析", f"发现书籍: {title[:20]}... | URL: {url}")
                    except Exception as e:
                        print_status("列表解析", f"解析单个条目失败: {str(e)}", "warning")
                        continue

                all_articles.extend(articles)

                next_btn = await self.main_page.querySelector('a[href*="page="]')
                if next_btn:
                    next_url = await self.main_page.evaluate('(el) => el.href', next_btn)
                    max_pages -= 1
                    await self.navigate_page(next_url, "分页")
                else:
                    print_status("分页终止", "未找到下一页按钮", "success")
                    break

            print_status("列表解析", f"共发现 {len(all_articles)} 个有效条目", "success")
            return all_articles

        except Exception as e:
            print_status("列表解析", f"解析失败: {str(e)}", "error")
            return []

    async def process_article(self, article):
        title, url = article['title'], article['url']
        print_status("文章处理", f"开始处理: {title[:15]}...", "start")

        page = None
        try:
            page = await self.browser.newPage()
            await page.setUserAgent(random.choice(USER_AGENTS))

            if not await self.navigate_page(url, "章节列表页", page):
                return

            # 等待章节列表加载
            await page.waitForSelector('div.chapters', {'timeout': 30000})

            # 提取所有章节链接
            chapter_links = await page.querySelectorAll('div.chapters a[href*="/fiction/id-"]')
            if not chapter_links:
                print_status("章节提取", "未找到章节链接", "warning")
                return

            full_content = []
            for i, chapter in enumerate(chapter_links, 1):
                chapter_url = await page.evaluate('(el) => el.href', chapter)
                chapter_title = await page.evaluate('(el) => el.textContent.trim()', chapter)
                print_status("章节处理", f"处理章节 {i}: {chapter_title}", "start")

                chapter_page = None
                try:
                    # 访问章节页面
                    chapter_page = await self.browser.newPage()
                    await chapter_page.setUserAgent(random.choice(USER_AGENTS))
                    
                    success = await self.navigate_page(chapter_url, "章节页", chapter_page)
                    if not success:
                        print_status("章节处理", f"章节 {i}: 加载失败，跳过", "warning")
                        continue

                    # 等待正文加载
                    try:
                        await chapter_page.waitForSelector('div.fiction-body div.content', {'timeout': 30000})
                    except Exception as e:
                        print_status("章节处理", f"章节 {i}: 等待超时，跳过 - {str(e)}", "warning")
                        continue

                    # 提取章节正文并分段
                    try:
                        content = await chapter_page.evaluate('''() => {
                            const contentElement = document.querySelector('div.fiction-body div.content');
                            if (!contentElement) return '';

                            const paragraphs = contentElement.getElementsByTagName('p');
                            if (!paragraphs || paragraphs.length === 0) return '';

                            let result = [];
                            for (let p of paragraphs) {
                                const text = p.innerText.trim();
                                if (text.length > 0) {
                                    result.push('  ' + text);
                                }
                            }
                            return result.join('\\n\\n');
                        }''')
                    except Exception as e:
                        print_status("章节处理", f"章节 {i}: 内容提取失败 - {str(e)}", "warning")
                        continue

                    if content:
                        content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
                        content = re.sub(r'^关注.*?下载APP$|^广告.*?$|^看精彩成人小说上《小黄书》：https://xchina\.store$|^看精彩成人小说上《小黄书》.*?$', '', content, flags=re.MULTILINE)
                        content = re.sub(r'\n{4,}', '\n\n', content)
                        full_content.append(f"{chapter_title}\n\n{content}")
                        print_status("章节处理", f"章节 {i}: {chapter_title} 提取成功（段落数: {content.count('\n\n') + 1}）", "success")
                    else:
                        print_status("章节处理", f"章节 {i}: {chapter_title} 未找到正文", "warning")

                except Exception as e:
                    print_status("章节处理", f"章节 {i}: 处理异常 - {str(e)}", "error")
                    continue
                finally:
                    if chapter_page:
                        try:
                            await chapter_page.close()
                        except Exception as e:
                            print_status("页面关闭", f"章节页面关闭异常: {str(e)}", "warning")
                    await asyncio.sleep(random.uniform(2, 4))  # 增加延迟时间

            # 修改保存逻辑部分
            if full_content:
                chapter_data = []
                for chapter_content in full_content:
                    # 分离章节标题和内容
                    parts = chapter_content.split('\n\n', 1)
                    if len(parts) == 2:
                        chapter_data.append({
                            'title': parts[0].strip(),
                            'content': parts[1].strip()
                        })
                
                # 保存到数据库
                if chapter_data:
                    await self.save_to_db(article, chapter_data)
                else:
                    print_status("文章处理", "未提取到有效章节数据", "warning")
            else:
                print_status("文章处理", "未提取到任何章节内容", "warning")

        except Exception as e:
            print_status("文章处理", f"处理失败: {type(e).__name__} - {str(e)}", "error")
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    print_status("页面关闭", f"主页面关闭异常: {str(e)}", "warning")
            await asyncio.sleep(2)

    async def init_db(self):
        print_status("数据库", "开始连接数据库", "start")
        try:
            self.db = pymysql.connect(**DB_CONFIG)
            self.cursor = self.db.cursor()
            print_status("数据库", "连接成功", "success")
            return True
        except Exception as e:
            print_status("数据库", f"连接失败: {str(e)}", "error")
            return False
            
    async def save_to_db(self, article, chapter_data):
        try:
            # 检查小说是否已存在
            check_novel_sql = "SELECT id FROM novels WHERE title = %s"
            self.cursor.execute(check_novel_sql, (article['title'],))
            novel = self.cursor.fetchone()
            
            if not novel:
                # 插入小说信息
                insert_novel_sql = """
                INSERT INTO novels (title, source_url, created_at, updated_at) 
                VALUES (%s, %s, %s, %s)
                """
                now = datetime.now()
                self.cursor.execute(insert_novel_sql, (
                    article['title'],
                    article['url'],
                    now,
                    now
                ))
                novel_id = self.cursor.lastrowid
                print_status("数据入库", f"新增小说: {article['title']}", "success")
            else:
                novel_id = novel['id']
                print_status("数据入库", f"更新小说: {article['title']}", "start")

            # 插入章节内容
            for chapter in chapter_data:
                # 检查章节是否存在
                check_chapter_sql = """
                SELECT id FROM chapters 
                WHERE novel_id = %s AND title = %s
                """
                self.cursor.execute(check_chapter_sql, (novel_id, chapter['title']))
                existing_chapter = self.cursor.fetchone()
                
                if not existing_chapter:
                    insert_chapter_sql = """
                    INSERT INTO chapters (novel_id, title, content, created_at) 
                    VALUES (%s, %s, %s, %s)
                    """
                    self.cursor.execute(insert_chapter_sql, (
                        novel_id,
                        chapter['title'],
                        chapter['content'],
                        datetime.now()
                    ))
                    print_status("数据入库", f"新增章节: {chapter['title']}", "success")

            self.db.commit()
            return True
            
        except Exception as e:
            self.db.rollback()
            print_status("数据入库", f"入库失败: {str(e)}", "error")
            return False

    async def get_chapter_content(self, chapter_url):
        chapter_page = None
        try:
            chapter_page = await self.browser.newPage()
            await chapter_page.setUserAgent(random.choice(USER_AGENTS))
            
            if not await self.navigate_page(chapter_url, "章节页", chapter_page):
                return None

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
                        result.push('  ' + text);
                    }
                }
                return result.join('\\n\\n');
            }''')

            if content:
                content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', content)
                content = re.sub(r'^关注.*?下载APP$|^广告.*?$|^看精彩成人小说上《小黄书》：https://xchina\.store$|^看精彩成人小说上《小黄书》.*?$', '', content, flags=re.MULTILINE)
                content = re.sub(r'\n{4,}', '\n\n', content)
                return content

        except Exception as e:
            print_status("章节处理", f"内容提取失败: {str(e)}", "warning")
            return None
        finally:
            if chapter_page:
                await chapter_page.close()
            await asyncio.sleep(random.uniform(2, 4))  # 增加延迟时间

    async def run(self):
        print("\n" + "=" * 50)
        print_status("爬虫系统", "启动 Book18 爬虫", "start")

        if not await self.init_browser() or not await self.init_db():
            return

        try:
            if not await self.navigate_page(LIST_PAGE_URL):
                return

            articles = await self.parse_list_page()
            if not articles:
                print_status("流程终止", "未找到有效文章", "warning")
                return

            print("\n" + "=" * 50)
            print_status("任务队列", f"开始处理 {len(articles)} 篇文章", "start")
            for idx, article in enumerate(articles, 1):
                print(f"\n{LOG_PREFIX}▶ 文章进度 ({idx}/{len(articles)})")
                await self.process_article(article)

        finally:
            print_status("资源清理", "关闭数据库连接", "start")
            if self.cursor:
                self.cursor.close()
            if self.db:
                self.db.close()
            print_status("资源清理", "关闭浏览器实例", "start")
            if self.browser:
                try:
                    await self.browser.close()
                    await asyncio.sleep(1)
                except Exception as e:
                    print_status("资源清理", f"关闭异常: {str(e)}", "warning")


if __name__ == "__main__":
    crawler = Book18Crawler()
    try:
        if hasattr(asyncio, 'run'):
            asyncio.run(crawler.run())
        else:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(crawler.run())
    except KeyboardInterrupt:
        print_status("系统中断", "用户主动终止操作", "warning")