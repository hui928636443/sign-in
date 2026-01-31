#!/usr/bin/env python3
"""
LinuxDO 论坛自动浏览帖子适配器

功能：
1. 登录 LinuxDO 论坛
2. 获取帖子列表
3. 模拟浏览帖子（发送 timings 请求标记为已读）
4. 增加在线时间

Discourse API:
- GET /latest.json - 获取最新帖子列表
- GET /t/{topic_id}.json - 获取帖子详情
- POST /topics/timings - 标记帖子为已读
"""

import asyncio
import contextlib
import random

import httpx
from loguru import logger

from platforms.base import BasePlatformAdapter, CheckinResult, CheckinStatus
from utils.browser import BrowserManager, get_browser_engine


class LinuxDOAdapter(BasePlatformAdapter):
    """LinuxDO 论坛自动浏览适配器"""

    BASE_URL = "https://linux.do"
    LATEST_URL = "https://linux.do/latest.json"
    TOP_URL = "https://linux.do/top.json"
    TIMINGS_URL = "https://linux.do/topics/timings"

    def __init__(
        self,
        username: str,
        password: str,
        browse_count: int = 10,
        account_name: str | None = None,
    ):
        """初始化 LinuxDO 适配器

        Args:
            username: LinuxDO 用户名
            password: LinuxDO 密码
            browse_count: 浏览帖子数量（默认 10）
            account_name: 账号显示名称
        """
        self.username = username
        self.password = password
        self.browse_count = browse_count
        self._account_name = account_name or username

        self._browser_manager: BrowserManager | None = None
        self.client: httpx.Client | None = None
        self._cookies: dict = {}
        self._csrf_token: str | None = None
        self._browsed_count: int = 0
        self._total_time: int = 0

    @property
    def platform_name(self) -> str:
        return "LinuxDO"

    @property
    def account_name(self) -> str:
        return self._account_name

    async def login(self) -> bool:
        """通过浏览器登录 LinuxDO"""
        engine = get_browser_engine()
        logger.info(f"[{self.account_name}] 使用浏览器引擎: {engine}")

        self._browser_manager = BrowserManager(engine=engine, headless=True)
        await self._browser_manager.start()

        try:
            if engine == "nodriver":
                return await self._login_nodriver()
            elif engine == "drissionpage":
                return await self._login_drissionpage()
            else:
                return await self._login_playwright()
        except Exception as e:
            logger.error(f"[{self.account_name}] 登录失败: {e}")
            return False

    async def _login_nodriver(self) -> bool:
        """使用 nodriver 登录"""
        tab = self._browser_manager.page

        logger.info(f"[{self.account_name}] 访问 LinuxDO 登录页面...")
        await tab.get(f"{self.BASE_URL}/login")
        await asyncio.sleep(2)

        # 等待 Cloudflare
        await self._browser_manager.wait_for_cloudflare(timeout=30)

        # 填写登录表单
        logger.info(f"[{self.account_name}] 填写登录表单...")
        try:
            username_input = await tab.select('#login-account-name', timeout=10)
            if username_input:
                await username_input.send_keys(self.username)
                await asyncio.sleep(0.5)

            password_input = await tab.select('#login-account-password', timeout=5)
            if password_input:
                await password_input.send_keys(self.password)
                await asyncio.sleep(0.5)

            # 点击登录
            login_btn = await tab.select('#login-button', timeout=5)
            if login_btn:
                await login_btn.mouse_click()
                await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"[{self.account_name}] 填写表单失败: {e}")
            return False

        # 检查登录状态
        current_url = tab.target.url if hasattr(tab, 'target') else ""
        if "login" in current_url.lower():
            logger.error(f"[{self.account_name}] 登录失败，仍在登录页面")
            return False

        # 获取 cookies
        cookies = await self._browser_manager.get_cookies()
        for cookie in cookies:
            name = getattr(cookie, 'name', cookie.get('name', ''))
            value = getattr(cookie, 'value', cookie.get('value', ''))
            if name and value:
                self._cookies[name] = value

        # 获取 CSRF token
        self._csrf_token = self._cookies.get('_forum_session')

        # 初始化 HTTP 客户端
        self._init_http_client()

        logger.success(f"[{self.account_name}] 登录成功")
        return True

    async def _login_drissionpage(self) -> bool:
        """使用 DrissionPage 登录"""
        import time
        page = self._browser_manager.page

        logger.info(f"[{self.account_name}] 访问 LinuxDO 登录页面...")
        page.get(f"{self.BASE_URL}/login")
        time.sleep(2)

        await self._browser_manager.wait_for_cloudflare(timeout=30)

        # 填写登录表单
        username_input = page.ele('#login-account-name', timeout=10)
        if username_input:
            username_input.input(self.username)
            time.sleep(0.5)

        password_input = page.ele('#login-account-password', timeout=5)
        if password_input:
            password_input.input(self.password)
            time.sleep(0.5)

        login_btn = page.ele('#login-button', timeout=5)
        if login_btn:
            login_btn.click()
            time.sleep(5)

        # 获取 cookies
        for cookie in page.cookies():
            self._cookies[cookie['name']] = cookie['value']

        self._init_http_client()
        return True

    async def _login_playwright(self) -> bool:
        """使用 Playwright 登录"""
        page = self._browser_manager.page

        await page.goto(f"{self.BASE_URL}/login", wait_until="networkidle")
        await self._browser_manager.wait_for_cloudflare(timeout=30)
        await asyncio.sleep(2)

        await page.fill('#login-account-name', self.username)
        await asyncio.sleep(0.5)
        await page.fill('#login-account-password', self.password)
        await asyncio.sleep(0.5)

        await page.click('#login-button')
        await asyncio.sleep(5)

        cookies = await self._browser_manager.context.cookies()
        for cookie in cookies:
            self._cookies[cookie['name']] = cookie['value']

        self._init_http_client()
        return True

    def _init_http_client(self):
        """初始化 HTTP 客户端"""
        self.client = httpx.Client(timeout=30.0)
        for name, value in self._cookies.items():
            self.client.cookies.set(name, value, domain="linux.do")

    def _build_headers(self) -> dict:
        """构建请求头"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.BASE_URL,
            "Origin": self.BASE_URL,
            "X-Requested-With": "XMLHttpRequest",
        }
        if self._csrf_token:
            headers["X-CSRF-Token"] = self._csrf_token
        return headers

    async def checkin(self) -> CheckinResult:
        """执行浏览帖子操作"""
        logger.info(f"[{self.account_name}] 开始浏览帖子...")

        # 获取帖子列表
        topics = self._get_topics()
        if not topics:
            return CheckinResult(
                platform=self.platform_name,
                account=self.account_name,
                status=CheckinStatus.FAILED,
                message="获取帖子列表失败",
            )

        # 随机选择帖子浏览
        browse_count = min(self.browse_count, len(topics))
        selected_topics = random.sample(topics, browse_count)

        logger.info(f"[{self.account_name}] 将浏览 {browse_count} 个帖子")

        for i, topic in enumerate(selected_topics):
            topic_id = topic.get("id")
            title = topic.get("title", "Unknown")[:30]

            logger.info(f"[{self.account_name}] [{i+1}/{browse_count}] 浏览: {title}...")

            success = self._browse_topic(topic_id)
            if success:
                self._browsed_count += 1

            # 随机延迟，模拟真实阅读
            delay = random.uniform(3, 8)
            await asyncio.sleep(delay)

        details = {
            "browsed": self._browsed_count,
            "total_time": f"{self._total_time // 1000}s",
        }

        if self._browsed_count > 0:
            return CheckinResult(
                platform=self.platform_name,
                account=self.account_name,
                status=CheckinStatus.SUCCESS,
                message=f"成功浏览 {self._browsed_count} 个帖子",
                details=details,
            )
        else:
            return CheckinResult(
                platform=self.platform_name,
                account=self.account_name,
                status=CheckinStatus.FAILED,
                message="浏览帖子失败",
                details=details,
            )

    def _get_topics(self) -> list:
        """获取帖子列表"""
        headers = self._build_headers()

        try:
            # 获取最新帖子
            response = self.client.get(self.LATEST_URL, headers=headers)
            if response.status_code == 200:
                data = response.json()
                topics = data.get("topic_list", {}).get("topics", [])
                logger.info(f"[{self.account_name}] 获取到 {len(topics)} 个帖子")
                return topics
        except Exception as e:
            logger.error(f"[{self.account_name}] 获取帖子列表失败: {e}")

        return []

    def _browse_topic(self, topic_id: int) -> bool:
        """浏览单个帖子（发送 timings 请求）

        根据 Discourse API，/topics/timings 接口参数格式：
        - topic_id: 帖子 ID
        - topic_time: 总阅读时间（毫秒）
        - timings[n]: 第 n 楼的阅读时间（毫秒）
        """
        headers = self._build_headers()
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"

        # 先获取帖子详情
        try:
            topic_url = f"{self.BASE_URL}/t/{topic_id}.json"
            response = self.client.get(topic_url, headers=headers)
            if response.status_code != 200:
                return False

            topic_data = response.json()
            posts = topic_data.get("post_stream", {}).get("posts", [])

            if not posts:
                return False

            # 构建 timings 数据
            # 模拟阅读时间：总时间 5-30 秒
            total_time = random.randint(5000, 30000)
            self._total_time += total_time

            # timings 格式: timings[post_number]=milliseconds
            timings_data = {
                "topic_id": topic_id,
                "topic_time": total_time,
            }

            # 为每个帖子分配阅读时间（最多前 5 个帖子）
            post_count = min(len(posts), 5)
            time_per_post = total_time // post_count

            for post in posts[:post_count]:
                post_number = post.get("post_number", 1)
                # 每个帖子的时间略有随机波动
                post_time = time_per_post + random.randint(-500, 500)
                timings_data[f"timings[{post_number}]"] = max(1000, post_time)

            # 发送 timings 请求
            response = self.client.post(
                self.TIMINGS_URL,
                headers=headers,
                data=timings_data,
            )

            if response.status_code == 200:
                return True
            else:
                logger.debug(f"timings 请求返回: {response.status_code}")
                return False

        except Exception as e:
            logger.debug(f"浏览帖子 {topic_id} 失败: {e}")
            return False

    async def get_status(self) -> dict:
        """获取浏览状态"""
        return {
            "browsed_count": self._browsed_count,
            "total_time": self._total_time,
        }

    async def cleanup(self) -> None:
        """清理资源"""
        if self._browser_manager:
            with contextlib.suppress(Exception):
                await self._browser_manager.close()
            self._browser_manager = None

        if self.client:
            self.client.close()
            self.client = None
