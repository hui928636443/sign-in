#!/usr/bin/env python3
"""
LinuxDo 论坛签到适配器

使用 Patchright (反检测 Playwright) + curl_cffi 实现自动签到。

Requirements:
- 2.3: 使用 Patchright 替代 DrissionPage 提升反检测能力
- 2.5: 保持浏览帖子、随机点赞功能
"""

import asyncio
import random
import time
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests
from loguru import logger
from patchright.async_api import async_playwright, Browser, Page
from tabulate import tabulate

from platforms.base import BasePlatformAdapter, CheckinResult, CheckinStatus
from utils.retry import retry_decorator

# LinuxDo URLs
HOME_URL = "https://linux.do/"
LOGIN_URL = "https://linux.do/login"
SESSION_URL = "https://linux.do/session"
CSRF_URL = "https://linux.do/session/csrf"


class LinuxDoAdapter(BasePlatformAdapter):
    """LinuxDo 论坛签到适配器
    
    使用 Patchright 进行浏览器自动化（反检测），curl_cffi 进行 API 请求。
    支持浏览帖子和随机点赞功能。
    """
    
    def __init__(
        self,
        username: str,
        password: str,
        browse_enabled: bool = True,
        browse_duration: int = 120,
        account_name: Optional[str] = None,
    ):
        """初始化 LinuxDo 适配器
        
        Args:
            username: LinuxDo 用户名
            password: LinuxDo 密码
            browse_enabled: 是否启用浏览帖子功能
            browse_duration: 浏览时长（秒），默认 120 秒（2分钟）
            account_name: 账号显示名称（可选）
        """
        self.username = username
        self.password = password
        self.browse_enabled = browse_enabled
        self.browse_duration = browse_duration
        self._account_name = account_name
        
        self._playwright = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.page: Optional[Page] = None
        self.session: Optional[requests.Session] = None
        self._connect_info: Optional[dict] = None
        self._hot_topics: list[dict] = []
        
        # 随机化的 User-Agent（在初始化时生成，保持一致性）
        self._user_agent: Optional[str] = None
    
    @property
    def platform_name(self) -> str:
        return "LinuxDo"
    
    @property
    def account_name(self) -> str:
        return self._account_name if self._account_name else self.username
    
    def _get_random_user_agent(self) -> str:
        """生成随机 User-Agent（模拟不同的 Chrome 版本和系统）"""
        chrome_versions = [
            "120.0.0.0", "121.0.0.0", "122.0.0.0", "123.0.0.0", "124.0.0.0",
            "125.0.0.0", "126.0.0.0", "127.0.0.0", "128.0.0.0", "129.0.0.0",
            "130.0.0.0", "131.0.0.0", "132.0.0.0",
        ]
        
        # Windows 10/11 的不同版本
        windows_versions = [
            "Windows NT 10.0; Win64; x64",
            "Windows NT 10.0; WOW64",
        ]
        
        chrome_ver = random.choice(chrome_versions)
        win_ver = random.choice(windows_versions)
        
        return (
            f"Mozilla/5.0 ({win_ver}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{chrome_ver} Safari/537.36"
        )
    
    def _get_random_viewport(self) -> dict:
        """生成随机 viewport 尺寸（模拟不同的屏幕分辨率）"""
        viewports = [
            {"width": 1920, "height": 1080},  # 1080p
            {"width": 1366, "height": 768},   # 常见笔记本
            {"width": 1536, "height": 864},   # 缩放后的 1080p
            {"width": 1440, "height": 900},   # MacBook
            {"width": 1600, "height": 900},   # 16:9 宽屏
            {"width": 1680, "height": 1050},  # 16:10 宽屏
            {"width": 1280, "height": 720},   # 720p
            {"width": 1280, "height": 800},   # 常见笔记本
        ]
        return random.choice(viewports)
    
    async def _init_browser(self) -> None:
        """初始化 Patchright 浏览器"""
        self._playwright = await async_playwright().start()
        
        # Patchright 自带反检测，使用 chromium
        self.browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        
        # 随机化 User-Agent 和 viewport（每个账户不同）
        self._user_agent = self._get_random_user_agent()
        viewport = self._get_random_viewport()
        
        logger.debug(f"使用 UA: {self._user_agent}")
        logger.debug(f"使用 viewport: {viewport['width']}x{viewport['height']}")
        
        # 创建上下文，设置随机化的 viewport 和 user agent
        self.context = await self.browser.new_context(
            viewport=viewport,
            user_agent=self._user_agent,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        
        self.page = await self.context.new_page()
    
    def _init_session(self) -> None:
        """初始化 HTTP 会话（使用与浏览器相同的 User-Agent）"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self._user_agent or self._get_random_user_agent(),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
    
    async def login(self) -> bool:
        """执行登录操作"""
        logger.info("开始登录 LinuxDo")
        
        await self._init_browser()
        self._init_session()
        
        # Step 1: 获取 CSRF Token
        logger.info("获取 CSRF token...")
        headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": LOGIN_URL,
        }
        
        try:
            resp_csrf = self.session.get(CSRF_URL, headers=headers, impersonate="chrome136")
            csrf_data = resp_csrf.json()
            csrf_token = csrf_data.get("csrf")
            logger.info(f"CSRF Token 获取成功: {csrf_token[:10]}...")
        except Exception as e:
            logger.error(f"获取 CSRF Token 失败: {e}")
            return False
        
        # Step 2: 登录
        logger.info("正在登录...")
        headers.update({
            "X-CSRF-Token": csrf_token,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://linux.do",
        })
        
        data = {
            "login": self.username,
            "password": self.password,
            "second_factor_method": "1",
            "timezone": "Asia/Shanghai",
        }
        
        try:
            resp_login = self.session.post(
                SESSION_URL, data=data, impersonate="chrome136", headers=headers
            )
            
            if resp_login.status_code == 200:
                response_json = resp_login.json()
                if response_json.get("error"):
                    logger.error(f"登录失败: {response_json.get('error')}")
                    return False
                logger.info("登录成功!")
            else:
                logger.error(f"登录失败，状态码: {resp_login.status_code}")
                return False
        except Exception as e:
            logger.error(f"登录请求异常: {e}")
            return False
        
        # 获取 Connect 信息
        self._fetch_connect_info()
        
        # Step 3: 同步 Cookie 到 Patchright
        logger.info("同步 Cookie 到 Patchright...")
        cookies_dict = self.session.cookies.get_dict()
        
        cookies_list = [
            {
                "name": name,
                "value": value,
                "domain": ".linux.do",
                "path": "/",
            }
            for name, value in cookies_dict.items()
        ]
        
        await self.context.add_cookies(cookies_list)
        
        logger.info("Cookie 设置完成，导航至 linux.do...")
        await self.page.goto(HOME_URL, wait_until="domcontentloaded")
        
        # 等待页面加载
        await asyncio.sleep(5)
        
        # 验证登录状态
        try:
            user_ele = await self.page.query_selector("#current-user")
            if not user_ele:
                content = await self.page.content()
                if "avatar" in content:
                    logger.info("登录验证成功 (通过 avatar)")
                    return True
                logger.error("登录验证失败 (未找到 current-user)")
                return False
            logger.info("登录验证成功")
            return True
        except Exception as e:
            logger.warning(f"登录验证异常: {e}")
            return True  # 继续执行
    
    async def checkin(self) -> CheckinResult:
        """执行签到操作（浏览帖子）"""
        details = {}
        
        # 添加 Connect 信息到详情
        if self._connect_info:
            details["connect_info"] = self._connect_info
        
        # 收集热门话题
        await self._collect_hot_topics()
        if self._hot_topics:
            details["hot_topics"] = self._hot_topics
        
        if not self.browse_enabled:
            return CheckinResult(
                platform=self.platform_name,
                account=self.account_name,
                status=CheckinStatus.SUCCESS,
                message="登录成功（浏览功能已禁用）",
                details=details if details else None,
            )
        
        # 浏览帖子
        try:
            browse_count = await self._click_topics()
            if browse_count == 0:
                return CheckinResult(
                    platform=self.platform_name,
                    account=self.account_name,
                    status=CheckinStatus.FAILED,
                    message="浏览帖子失败",
                    details=details if details else None,
                )
            
            return CheckinResult(
                platform=self.platform_name,
                account=self.account_name,
                status=CheckinStatus.SUCCESS,
                message=f"登录成功，浏览了 {browse_count} 个帖子",
                details=details if details else None,
            )
        except Exception as e:
            logger.error(f"浏览帖子异常: {e}")
            return CheckinResult(
                platform=self.platform_name,
                account=self.account_name,
                status=CheckinStatus.FAILED,
                message=f"浏览帖子异常: {str(e)}",
                details=details if details else None,
            )
    
    async def get_status(self) -> dict:
        """获取 Connect 信息"""
        if self._connect_info:
            return self._connect_info
        self._fetch_connect_info()
        return self._connect_info or {}
    
    async def cleanup(self) -> None:
        """清理浏览器资源"""
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
            self.page = None
        
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None
        
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
            self.browser = None
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        
        if self.session:
            self.session = None
    
    def _fetch_connect_info(self) -> None:
        """获取 Connect 信息"""
        logger.info("获取 Connect 信息")
        try:
            headers = {
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,image/apng,*/*;q=0.8,"
                    "application/signed-exchange;v=b3;q=0.7"
                ),
            }
            resp = self.session.get(
                "https://connect.linux.do/",
                headers=headers,
                impersonate="chrome136",
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select("table tr")
            
            info = {}
            table_data = []
            
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 3:
                    project = cells[0].text.strip()
                    current = cells[1].text.strip() or "0"
                    requirement = cells[2].text.strip() or "0"
                    info[project] = {"current": current, "requirement": requirement}
                    table_data.append([project, current, requirement])
            
            if table_data:
                print("--------------Connect Info-----------------")
                print(tabulate(table_data, headers=["项目", "当前", "要求"], tablefmt="pretty"))
            
            self._connect_info = info
        except Exception as e:
            logger.warning(f"获取 Connect 信息失败: {e}")
            self._connect_info = {}
    
    async def _click_topics(self) -> int:
        """点击并浏览主题帖，返回浏览数量"""
        try:
            # 获取所有话题行
            topic_rows = await self.page.query_selector_all("#list-area tr")
        except Exception:
            topic_rows = []
        
        if not topic_rows:
            logger.error("未找到主题帖")
            return 0
        
        # 获取所有 href，过滤掉公告和运营反馈
        topic_urls = []
        for row in topic_rows:
            try:
                # 获取整行文本，检查是否包含屏蔽分类
                row_text = await row.inner_text()
                should_skip = False
                for blocked in self.BLOCKED_CATEGORIES:
                    if blocked in row_text:
                        should_skip = True
                        break
                if should_skip:
                    continue
                
                # 获取链接
                title_link = await row.query_selector(".title")
                if not title_link:
                    continue
                    
                href = await title_link.get_attribute("href")
                if href:
                    if not href.startswith("http"):
                        href = f"https://linux.do{href}"
                    topic_urls.append(href)
            except Exception:
                continue
        
        if not topic_urls:
            logger.error("过滤后没有可浏览的帖子")
            return 0
        
        logger.info(f"发现 {len(topic_urls)} 个可浏览帖子，开始按时间浏览（目标 {self.browse_duration} 秒）")
        
        # 按时间浏览，而不是按数量
        start_time = time.time()
        browsed_count = 0
        random.shuffle(topic_urls)  # 打乱顺序
        
        for url in topic_urls:
            # 检查是否已达到目标时间
            elapsed = time.time() - start_time
            if elapsed >= self.browse_duration:
                logger.info(f"已达到目标浏览时间 {self.browse_duration} 秒")
                break
            
            remaining = self.browse_duration - elapsed
            logger.info(f"浏览第 {browsed_count + 1} 个帖子，已用时 {elapsed:.0f}s，剩余 {remaining:.0f}s")
            
            await self._click_one_topic(url)
            browsed_count += 1
        
        total_time = time.time() - start_time
        logger.info(f"浏览完成，共浏览 {browsed_count} 个帖子，用时 {total_time:.0f} 秒")
        return browsed_count
    
    async def _click_one_topic(self, topic_url: str) -> bool:
        """点击单个主题帖"""
        new_page = await self.context.new_page()
        start_time = time.time()
        try:
            await new_page.goto(topic_url, wait_until="domcontentloaded")
            
            # 获取帖子 ID 用于 timings 接口
            topic_id = self._extract_topic_id(topic_url)
            
            # 浏览帖子
            await self._browse_post(new_page)
            
            # 计算阅读时间并发送 timings
            elapsed_time = int((time.time() - start_time) * 1000)  # 毫秒
            if topic_id:
                await self._send_timings(new_page, topic_id, elapsed_time)
            
            # 30% 概率点赞
            if random.random() < 0.3:
                await self._click_like(new_page)
            
            return True
        except Exception as e:
            logger.warning(f"浏览帖子失败: {e}")
            return False
        finally:
            try:
                await new_page.close()
            except Exception:
                pass
    
    def _extract_topic_id(self, url: str) -> Optional[int]:
        """从 URL 提取帖子 ID"""
        try:
            # URL 格式: https://linux.do/t/topic/123456 或 https://linux.do/t/topic/123456/1
            import re
            match = re.search(r'/t/topic/(\d+)', url)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return None
    
    async def _send_timings(self, page: Page, topic_id: int, time_ms: int) -> None:
        """发送阅读时间到 Discourse timings 接口
        
        会自动获取页面上所有楼层的 post_number，并为每个楼层发送阅读时间
        """
        try:
            # 通过浏览器发送 timings 请求，自动携带 cookies 和 CSRF token
            # 获取所有楼层的 post_number 并构建 timings 参数
            await page.evaluate(f"""
                (async () => {{
                    try {{
                        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
                        if (!csrfToken) return;
                        
                        // 获取所有楼层的 post_number
                        const posts = document.querySelectorAll('.topic-post');
                        const timingsParams = [];
                        const timePerPost = Math.floor({time_ms} / Math.max(posts.length, 1));
                        
                        posts.forEach((post, index) => {{
                            // Discourse 的 post_number 从 1 开始
                            const postNumber = index + 1;
                            // 每个楼层至少 2000ms 的阅读时间
                            const postTime = Math.max(timePerPost, 2000);
                            timingsParams.push(`timings%5B${{postNumber}}%5D=${{postTime}}`);
                        }});
                        
                        // 如果没有找到楼层，至少发送第一楼的时间
                        if (timingsParams.length === 0) {{
                            timingsParams.push(`timings%5B1%5D={time_ms}`);
                        }}
                        
                        const body = `topic_id={topic_id}&topic_time={time_ms}&${{timingsParams.join('&')}}`;
                        
                        await fetch('/topics/timings', {{
                            method: 'POST',
                            headers: {{
                                'Content-Type': 'application/x-www-form-urlencoded',
                                'X-CSRF-Token': csrfToken,
                                'X-Requested-With': 'XMLHttpRequest'
                            }},
                            body: body
                        }});
                    }} catch (e) {{}}
                }})();
            """)
            logger.debug(f"已发送 timings: topic_id={topic_id}, time={time_ms}ms")
        except Exception as e:
            logger.debug(f"发送 timings 失败: {e}")
    
    async def _browse_post(self, page: Page) -> None:
        """浏览帖子内容，逐个楼层停留确保标记为已读
        
        Discourse 论坛的阅读标记机制：
        - 每个楼层需要在视口内停留约 1 秒才会触发 timings
        - 右侧蓝点消失表示该楼层已被标记为已读
        - 我们停留 2 秒以上确保稳定触发
        
        反检测策略：
        - 随机停留时间（2-4秒）
        - 偶尔回滚模拟回看
        - 随机鼠标移动
        - 不规则的浏览节奏
        """
        # 等待帖子内容加载（随机时间）
        await asyncio.sleep(random.uniform(0.8, 1.5))
        
        # 获取所有楼层
        posts = await page.query_selector_all(".topic-post")
        
        if not posts:
            logger.warning("未找到楼层元素，使用滚动模式")
            await self._browse_post_fallback(page)
            return
        
        post_count = len(posts)
        logger.info(f"帖子共有 {post_count} 个楼层，开始逐个浏览")
        
        # 随机决定浏览多少楼层（避免每次都浏览固定数量）
        max_posts_to_read = min(post_count, random.randint(15, 25))
        browsed_count = 0
        last_scroll_back_index = -5  # 记录上次回滚的位置，避免频繁回滚
        
        for i, post in enumerate(posts[:max_posts_to_read]):
            try:
                # 滚动到该楼层
                await post.scroll_into_view_if_needed()
                
                # 随机鼠标移动到帖子区域（模拟真实阅读）
                if random.random() < 0.6:
                    await self._random_mouse_move(page, post)
                
                # 停留时间：基础 2-4 秒，偶尔更长（模拟仔细阅读）
                if random.random() < 0.15:
                    # 15% 概率仔细阅读，停留更久
                    wait_time = random.uniform(4.0, 7.0)
                    logger.debug(f"楼层 {i+1}，仔细阅读 {wait_time:.1f} 秒")
                else:
                    wait_time = random.uniform(2.0, 4.0)
                    logger.debug(f"楼层 {i+1}/{max_posts_to_read}，停留 {wait_time:.1f} 秒")
                
                await asyncio.sleep(wait_time)
                browsed_count += 1
                
                # 8% 概率回滚查看之前的内容（模拟回看）
                if i > 3 and i - last_scroll_back_index > 3 and random.random() < 0.08:
                    scroll_back = random.randint(1, min(3, i))
                    logger.debug(f"回滚查看第 {i+1-scroll_back} 楼")
                    await posts[i - scroll_back].scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(1.5, 3.0))
                    last_scroll_back_index = i
                    # 滚回当前位置
                    await post.scroll_into_view_if_needed()
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                
                # 6% 概率提前退出（模拟失去兴趣）
                if i > 5 and random.random() < 0.06:
                    logger.info(f"随机退出，已浏览 {browsed_count} 个楼层")
                    break
                
                # 偶尔短暂停顿（模拟思考或分心）
                if random.random() < 0.1:
                    await asyncio.sleep(random.uniform(0.3, 0.8))
                    
            except Exception as e:
                logger.debug(f"浏览楼层 {i+1} 失败: {e}")
                continue
        
        logger.info(f"完成楼层浏览，共浏览 {browsed_count} 个楼层")
    
    async def _random_mouse_move(self, page: Page, element) -> None:
        """随机移动鼠标到元素区域内（模拟真实阅读行为）"""
        try:
            box = await element.bounding_box()
            if not box:
                return
            
            # 在元素区域内随机选择一个点（不是正中心）
            x = box["x"] + random.uniform(box["width"] * 0.1, box["width"] * 0.9)
            y = box["y"] + random.uniform(box["height"] * 0.2, box["height"] * 0.8)
            
            # 移动鼠标（带有轻微的随机偏移模拟手抖）
            jitter_x = random.uniform(-3, 3)
            jitter_y = random.uniform(-3, 3)
            
            await page.mouse.move(x + jitter_x, y + jitter_y)
        except Exception:
            pass  # 鼠标移动失败不影响主流程
    
    async def _browse_post_fallback(self, page: Page) -> None:
        """回退的滚动浏览模式（当无法获取楼层元素时使用）
        
        使用随机滚动距离和停留时间，偶尔回滚模拟真实用户
        """
        start_time = time.time()
        min_browse_time = random.uniform(8, 15)
        scroll_count = 0
        
        for _ in range(15):
            # 随机滚动距离（模拟不同的滚动习惯）
            scroll_distance = random.randint(300, 800)
            await page.evaluate(f"window.scrollBy(0, {scroll_distance})")
            scroll_count += 1
            
            # 随机停留时间
            if random.random() < 0.2:
                # 20% 概率停留更久（仔细阅读）
                await asyncio.sleep(random.uniform(3.5, 6.0))
            else:
                await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # 10% 概率回滚一点（模拟回看）
            if scroll_count > 2 and random.random() < 0.1:
                back_distance = random.randint(150, 400)
                await page.evaluate(f"window.scrollBy(0, -{back_distance})")
                await asyncio.sleep(random.uniform(1.0, 2.5))
            
            # 随机鼠标移动
            if random.random() < 0.4:
                viewport = await page.evaluate("({w: window.innerWidth, h: window.innerHeight})")
                x = random.uniform(100, viewport["w"] - 100)
                y = random.uniform(100, viewport["h"] - 100)
                await page.mouse.move(x, y)
            
            elapsed = time.time() - start_time
            at_bottom = await page.evaluate(
                "window.scrollY + window.innerHeight >= document.body.scrollHeight - 50"
            )
            
            if at_bottom and elapsed >= min_browse_time:
                break
            
            # 5% 概率提前退出
            if elapsed > 6 and random.random() < 0.05:
                break
    
    async def _dismiss_dialog(self, page: Page) -> None:
        """关闭页面上可能存在的弹窗"""
        for _ in range(3):  # 最多尝试 3 次
            try:
                # 检查是否有 dialog 弹窗
                dialog_holder = await page.query_selector("#dialog-holder.dialog-container")
                if not dialog_holder:
                    return
                
                # 检查弹窗是否可见
                is_visible = await dialog_holder.is_visible()
                if not is_visible:
                    return
                
                logger.info("检测到弹窗，尝试关闭...")
                
                # 方法1: 点击 overlay 背景关闭
                overlay = await page.query_selector(".dialog-overlay[data-a11y-dialog-hide]")
                if overlay:
                    await overlay.click(force=True, timeout=2000)
                    await asyncio.sleep(0.5)
                    continue
                
                # 方法2: 点击关闭按钮
                close_btn = await page.query_selector(".dialog-close")
                if close_btn:
                    await close_btn.click(force=True, timeout=2000)
                    await asyncio.sleep(0.5)
                    continue
                
                # 方法3: 按 Escape 键
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.debug(f"关闭弹窗尝试失败: {e}")
                # 最后手段：用 JS 直接移除弹窗
                try:
                    await page.evaluate("document.querySelector('#dialog-holder')?.remove()")
                    logger.info("用 JS 移除了弹窗")
                except Exception:
                    pass
                break

    async def _click_like(self, page: Page) -> None:
        """点赞帖子"""
        try:
            # 先关闭可能存在的弹窗
            await self._dismiss_dialog(page)
            
            like_button = await page.query_selector(".discourse-reactions-reaction-button")
            if like_button:
                logger.info("找到未点赞的帖子，准备点赞")
                # 使用 force=True 强制点击，跳过可操作性检查
                await like_button.click(timeout=5000, force=True)
                logger.info("点赞成功")
                await asyncio.sleep(random.uniform(1, 2))
            else:
                logger.info("帖子可能已经点过赞了")
        except Exception as e:
            logger.warning(f"点赞失败（不影响签到）: {e}")
    
    # 需要屏蔽的分类
    BLOCKED_CATEGORIES = {"公告", "运营反馈"}
    
    async def _collect_hot_topics(self) -> None:
        """收集热门话题（按浏览量排序的新帖子）"""
        logger.info("收集热门话题...")
        self._hot_topics = []
        
        try:
            # 获取所有话题行
            topic_rows = await self.page.query_selector_all("#list-area tr")
            
            for row in topic_rows:
                try:
                    # 获取标题链接
                    title_link = await row.query_selector(".title")
                    if not title_link:
                        continue
                    
                    title = await title_link.inner_text()
                    title = title.strip()
                    url = await title_link.get_attribute("href")
                    if url and not url.startswith("http"):
                        url = f"https://linux.do{url}"
                    
                    # 获取整行文本，检查是否包含屏蔽分类
                    row_text = await row.inner_text()
                    should_skip = False
                    for blocked in self.BLOCKED_CATEGORIES:
                        if blocked in row_text:
                            should_skip = True
                            break
                    if should_skip:
                        continue
                    
                    # 获取浏览量
                    views_ele = await row.query_selector(".views")
                    views_text = await views_ele.inner_text() if views_ele else "0"
                    views = self._parse_number(views_text.strip())
                    
                    # 获取回复数
                    replies_ele = await row.query_selector(".replies")
                    replies_text = await replies_ele.inner_text() if replies_ele else "0"
                    replies = self._parse_number(replies_text.strip())
                    
                    if title and views > 0:
                        self._hot_topics.append({
                            "title": title[:50] + "..." if len(title) > 50 else title,
                            "url": url,
                            "views": views,
                            "replies": replies,
                        })
                except Exception:
                    continue
            
            # 按浏览量排序，取 Top 10
            self._hot_topics.sort(key=lambda x: x["views"], reverse=True)
            self._hot_topics = self._hot_topics[:10]
            
            logger.info(f"收集到 {len(self._hot_topics)} 个热门话题")
            
        except Exception as e:
            logger.warning(f"收集热门话题失败: {e}")
    
    def _parse_number(self, text: str) -> int:
        """解析数字文本（支持 1.2k, 3.5万 等格式）"""
        text = text.strip().lower()
        if not text:
            return 0
        
        try:
            if "k" in text:
                return int(float(text.replace("k", "")) * 1000)
            if "万" in text:
                return int(float(text.replace("万", "")) * 10000)
            if "m" in text:
                return int(float(text.replace("m", "")) * 1000000)
            return int(text.replace(",", ""))
        except (ValueError, AttributeError):
            return 0
