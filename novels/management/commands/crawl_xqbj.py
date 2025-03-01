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
LIST_PAGE_URL = "https://d3syerwqkywh2y.cloudfront.net/nov/6_0_3_popular_9/%E6%96%87%E5%AD%A6%E5%B0%8F%E8%AF%B4/%E5%85%A8%E9%83%A8.html"

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
    'novel_min': 5,  # 处理每本小说前的最小等待时间
    'novel_max': 10,  # 处理每本小说前的最大等待时间
    'click_min': 1,
    'click_max': 2
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

    def clean_chapter_title(self, title):
        """清理章节标题，去除时间戳格式和多余空白"""
        # 去除时间戳格式（如：2024-10-21 21:01:22）
        title = re.sub(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', '', title)
        # 去除可能的其他时间格式
        title = re.sub(r'\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}', '', title)
        # 去除首尾空白和特殊字符
        title = title.strip().replace('\u3000', ' ')
        # 处理连续空格
        title = re.sub(r'\s+', ' ', title)
        # 去除开头结尾的特殊字符（如"|"）
        title = re.sub(r'^[\s|_\-]+|[\s|_\-]+$', '', title)
        return title
        
    def extract_chapter_number(self, title):
        """从章节标题中提取章节序号"""
        match = re.search(r'第(\d+)章', title)
        if match:
            return int(match.group(1))
        # 尝试其他可能的格式
        numbers = re.findall(r'\d+', title)
        if numbers:
            return int(numbers[0])
        return 0

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
        
        # 增加处理每本小说前的随机等待
        await self.random_sleep(WAIT_TIME['novel_min'], WAIT_TIME['novel_max'])
        
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
                
                # 获取所有章节列表
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
                            // 过滤时间戳格式（多种格式）
                            let cleanTitle = (c.title || c.name || '');
                            // 处理YYYY-MM-DD HH:MM:SS格式
                            cleanTitle = cleanTitle.replace(/\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}/g, '');
                            // 处理MM/DD/YYYY HH:MM格式
                            cleanTitle = cleanTitle.replace(/\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2}/g, '');
                            // 去除首尾空白和特殊字符
                            cleanTitle = cleanTitle.trim().replace(/^[\s|_\-]+|[\s|_\-]+$/g, '');
                            // 处理连续空格
                            cleanTitle = cleanTitle.replace(/\s+/g, ' ');
                            // 去除全角空格
                            cleanTitle = cleanTitle.replace(/\u3000/g, ' ');
                            
                            return JSON.stringify({
                                title: cleanTitle,
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

                # 记录处理失败的章节
                failed_chapters = []
                
                # 处理需要下载的章节
                for idx, chapter_info in enumerate(chapters_to_process, 1):
                    success = await self.process_chapter(novel, chapter_info, idx, len(chapters_to_process))
                    if not success:
                        # 记录失败的章节
                        failed_chapters.append(chapter_info)

                # 记录失败的章节到文件，便于后续处理
                if failed_chapters:
                    self.print_status("章节统计", f"有 {len(failed_chapters)} 章下载失败，已记录", "warning")
                    await self.save_failed_chapters(novel.title, failed_chapters)
                
                # 再次检查是否有遗漏章节
                await self.verify_chapters_completeness(novel, all_chapters)
                    
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

    async def process_chapter(self, novel, chapter_info, idx, total):
        """处理单个章节"""
        max_retries = 3
        retry_count = 0
        
        # 清理章节标题
        clean_title = self.clean_chapter_title(chapter_info['title'])
        
        # 首先检查章节是否已存在 (使用清理后的标题)
        existing_chapter = await sync_to_async(lambda: Chapter.objects.filter(
            novel=novel,
            title=clean_title
        ).first())()
        
        if existing_chapter:
            # 如果章节已存在，直接跳过
            self.print_status("章节处理", f"章节已存在，跳过：{clean_title} ({idx}/{total})", "info")
            return True
            
        # 更新章节标题为清理后的标题
        chapter_info['title'] = clean_title
        
        while retry_count < max_retries:
            try:
                chapter_page = await self.browser.newPage()
                await chapter_page.setUserAgent(self.ua.random)
                await chapter_page.setExtraHTTPHeaders(HEADERS)
                
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
                    # 使用章节信息中的order值（如果有）
                    chapter_order = chapter_info.get('order', self.extract_chapter_number(chapter_info['title']))
                    
                    # 清理章节标题
                    clean_title = self.clean_chapter_title(chapter_info['title'])
                    
                    # 创建新章节
                    await sync_to_async(Chapter.objects.create)(
                        novel=novel,
                        title=clean_title,
                        content=content,
                        order=chapter_order  # 使用正确的排序值
                    )
                    self.print_status("章节下载", f"已下载：{chapter_info['title']} ({idx}/{total})", "success")
                    break  # 成功处理，跳出重试循环
                else:
                    self.print_status("章节下载", f"章节内容为空：{chapter_info['title']}", "warning")
                    retry_count += 1
                    
            except Exception as e:
                retry_count += 1
                self.print_status("章节下载", f"下载失败: {chapter_info['title']}\n                                    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {str(e)} (重试 {retry_count}/{max_retries})", "error")
                
                # 如果是唯一性约束错误，说明章节已存在但前面的检查没有捕获到
                # 这可能是因为并发问题或数据库同步延迟
                if "UNIQUE constraint failed" in str(e) and "novels_chapter.novel_id, novels_chapter.title" in str(e):
                    self.print_status("章节处理", f"章节已存在（并发检测）：{chapter_info['title']}", "info")
                    return True  # 视为成功，直接返回
                
                await self.random_sleep(2, 5)  # 失败后等待时间更长
                
            finally:
                await chapter_page.close()
        
        # 如果所有重试都失败，记录到失败列表
        if retry_count >= max_retries:
            self.print_status("章节下载", f"章节 {chapter_info['title']} 下载失败，已达到最大重试次数", "error")
            return False
        
        return True

    async def save_failed_chapters(self, novel_title, failed_chapters):
        """保存失败的章节信息到文件"""
        import json
        import os
        
        # 创建失败记录目录
        os.makedirs('failed_chapters', exist_ok=True)
        
        # 文件名使用小说标题
        safe_title = re.sub(r'[\\/*?:"<>|]', "_", novel_title)
        filename = f'failed_chapters/{safe_title}.json'
        
        # 读取现有失败记录
        existing_data = []
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except:
                    pass
        
        # 合并新的失败记录
        existing_urls = [item['url'] for item in existing_data]
        for chapter in failed_chapters:
            if chapter['url'] not in existing_urls:
                existing_data.append(chapter)
        
        # 保存到文件
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)

    async def verify_chapters_completeness(self, novel, all_chapters):
        """验证章节完整性并按顺序补充缺失章节"""
        # 获取数据库中的章节
        db_chapters = await sync_to_async(lambda: list(Chapter.objects.filter(novel=novel).values('title', 'id', 'order')))()
        
        # 创建章节标题到ID的映射
        db_chapter_map = {c['title']: c for c in db_chapters}
        db_chapter_titles = set(db_chapter_map.keys())
        
        # 比较章节数量
        self.print_status("章节信息", f"数据库中已有 {len(db_chapters)} 章", "info")
        self.print_status("章节对比", f"发现 {len(all_chapters) - len(db_chapters)} 章需要更新", "info")
        
        # 清理all_chapters中的标题
        cleaned_all_chapters = []
        for chapter in all_chapters:
            cleaned_chapter = chapter.copy()
            cleaned_chapter['title'] = self.clean_chapter_title(chapter['title'])
            cleaned_chapter['original_title'] = chapter['title']  # 保留原始标题用于调试
            cleaned_all_chapters.append(cleaned_chapter)
        
        # 如果章节数量相同，可能不需要更新
        if len(cleaned_all_chapters) == len(db_chapters) and all(c['title'] in db_chapter_titles for c in cleaned_all_chapters):
            self.print_status("章节完整性", "章节数量相同且标题匹配，无需更新", "success")
            return
        
        # 找出缺失的章节
        missing_chapters = []
        for chapter in cleaned_all_chapters:
            if chapter['title'] not in db_chapter_titles:
                chapter['number'] = self.extract_chapter_number(chapter['title'])
                # 检查是否是番外章节
                chapter['is_special'] = any(keyword in chapter['title'] for keyword in 
                                           ['番外', '后记', '附录', '特别篇', '外传'])
                missing_chapters.append(chapter)
        
        if not missing_chapters:
            self.print_status("章节完整性", "所有章节已完整下载", "success")
            return
        
        # 按章节类型和序号排序：正常章节在前，番外在后
        missing_chapters.sort(key=lambda x: (1 if x['is_special'] else 0, x['number']))
        
        self.print_status("章节完整性", f"发现 {len(missing_chapters)} 章缺失，尝试补充下载", "warning")
        
        # 下载缺失的章节
        failed_chapters = []
        for idx, chapter_info in enumerate(missing_chapters, 1):
            # 设置正确的order值
            if chapter_info['is_special']:
                # 番外章节使用大序号，确保排在最后
                chapter_info['order'] = 1000000 + chapter_info['number']
            else:
                # 正常章节使用提取的序号
                chapter_info['order'] = chapter_info['number']
            
            success = await self.process_chapter(novel, chapter_info, idx, len(missing_chapters))
            if not success:
                failed_chapters.append(chapter_info)

    async def process_failed_chapters(self):
        """处理之前失败的章节"""
        import json
        import os
        import glob
        
        # 查找所有失败记录文件
        failed_files = glob.glob('failed_chapters/*.json')
        if not failed_files:
            self.print_status("失败章节", "没有找到失败章节记录", "info")
            return
        
        self.print_status("失败章节", f"找到 {len(failed_files)} 个小说有失败章节记录", "info")
        
        for file_path in failed_files:
            try:
                # 读取失败记录
                with open(file_path, 'r', encoding='utf-8') as f:
                    failed_chapters = json.load(f)
                
                if not failed_chapters:
                    continue
                    
                # 从文件名获取小说标题
                novel_title = os.path.basename(file_path).replace('.json', '')
                novel_title = re.sub(r'_+', " ", novel_title).strip()
                
                # 查找小说
                novel = await sync_to_async(Novel.objects.filter(title__icontains=novel_title).first)()
                if not novel:
                    self.print_status("失败章节", f"找不到小说: {novel_title}", "warning")
                    continue
                    
                self.print_status("失败章节", f"处理小说 '{novel.title}' 的 {len(failed_chapters)} 个失败章节", "info")
                
                # 获取已有章节
                existing_chapters = await sync_to_async(lambda: list(Chapter.objects.filter(novel=novel).values_list('title', flat=True)))()
                
                # 过滤出尚未下载的章节
                chapters_to_process = [c for c in failed_chapters if c['title'] not in existing_chapters]
                
                if not chapters_to_process:
                    self.print_status("失败章节", f"小说 '{novel.title}' 的所有章节已下载完成", "success")
                    # 删除空记录文件
                    os.remove(file_path)
                    continue
                    
                # 下载失败的章节
                remaining_failed = []
                for chapter_info in chapters_to_process:
                    try:
                        chapter_page = await self.browser.newPage()
                        await chapter_page.setUserAgent(self.ua.random)
                        await chapter_page.setExtraHTTPHeaders(HEADERS)
                        
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
                            # 清理章节标题
                            clean_title = self.clean_chapter_title(chapter_info['title'])
                            
                            # 提取章节序号（使用清理后的标题）
                            chapter_num = self.extract_chapter_number(clean_title)
                            
                            await sync_to_async(Chapter.objects.create)(
                                novel=novel,
                                title=clean_title,
                                content=content,
                                order=chapter_num  # 设置排序值
                            )
                            self.print_status("章节恢复", f"已下载：{chapter_info['title']}", "success")
                        else:
                            self.print_status("章节恢复", f"章节内容为空：{chapter_info['title']}", "warning")
                            remaining_failed.append(chapter_info)

                    except Exception as e:
                        self.print_status("章节恢复", f"下载失败: {chapter_info['title']} - {str(e)}", "error")
                        remaining_failed.append(chapter_info)
                    finally:
                        await chapter_page.close()
                        await self.random_sleep(1, 3)
                
                # 更新失败记录
                if remaining_failed:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(remaining_failed, f, ensure_ascii=False, indent=2)
                    self.print_status("失败章节", f"小说 '{novel.title}' 还有 {len(remaining_failed)} 章下载失败", "warning")
                else:
                    # 删除空记录文件
                    os.remove(file_path)
                    self.print_status("失败章节", f"小说 '{novel.title}' 的所有失败章节已恢复", "success")
                    
            except Exception as e:
                self.print_status("失败章节处理", f"处理文件 {file_path} 时出错: {str(e)}", "error")

    async def run(self, process_failed=False):
        """运行爬虫"""
        if not await self.init_browser():
            return

        try:
            if process_failed:
                # 处理之前失败的章节
                await self.process_failed_chapters()
            else:
                # 正常爬取流程
                await self.random_sleep(WAIT_TIME['page_min'], WAIT_TIME['page_max'])
                await self.main_page.goto(LIST_PAGE_URL, {
                    'waitUntil': 'networkidle0',
                    'timeout': 30000
                })
                
                await self.parse_list_page()

        finally:
            if self.browser:
                await self.browser.close()

    def add_arguments(self, parser):
        parser.add_argument(
            '--failed',
            action='store_true',
            help='处理之前失败的章节'
        )

    def handle(self, *args, **options):
        """命令入口"""
        self.print_status("爬虫启动", "开始运行", "start")
        try:
            process_failed = options.get('failed', False)
            if process_failed:
                self.print_status("运行模式", "处理失败章节模式", "info")
            else:
                self.print_status("运行模式", "正常爬取模式", "info")
            
            asyncio.run(self.run(process_failed=process_failed))
        except KeyboardInterrupt:
            self.print_status("系统中断", "用户终止操作", "warning")
        except Exception as e:
            self.print_status("系统错误", f"未处理的异常: {str(e)}", "error")
        finally:
            self.print_status("爬虫结束", "任务完成", "success") 