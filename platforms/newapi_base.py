#!/usr/bin/env python3
"""
NewAPI 通用签到适配器基类

适用于所有基于 new-api/one-api 架构的公益站，如：
- WONG 公益站 (wzw.pp.ua)
- Elysiver (elysiver.h-e.top)
- KFC API (kfc-api.sxxe.net)

支持两种登录方式：
1. 优先使用 LinuxDO OAuth 自动登录（使用反检测浏览器）
2. 失败时回退到用户提供的 Cookie

浏览器引擎：
- nodriver: 不基于 WebDriver/Selenium，直接使用 CDP，最难被检测（推荐）
- DrissionPage: 不基于 WebDriver，较难被 Cloudflare 检测
- Patchright: 基于 Chromium 的反检测浏览器（备用）
"""

import asyncio
import contextlib
import time

import httpx
from loguru import logger

from platforms.base import BasePlatformAdapter, CheckinResult, CheckinStatus
from utils.browser import BrowserManager, get_browser_engine


class NewAPIAdapter(BasePlatformAdapter):
    """NewAPI 通用签到适配器基类。

    子类只需要定义以下类属性：
    - PLATFORM_NAME: 平台显示名称
    - BASE_URL: 站点基础 URL
    - COOKIE_DOMAIN: Cookie 域名
    """

    # 子类必须重写这些属性
    PLATFORM_NAME: str = "NewAPI"
    BASE_URL: str = ""
    COOKIE_DOMAIN: str = ""

    # 通用 API 路径（new-api 标准）
    LOGIN_PATH: str = "/login"
    CONSOLE_PATH: str = "/console/personal"
    CHECKIN_API_PATH: str = "/api/user/checkin"
    USER_INFO_API_PATH: str = "/api/user/self"

    # 货币单位（可重写）
    CURRENCY_UNIT: str = "$"

    # LinuxDO URLs
    LINUXDO_LOGIN_URL = "https://linux.do/login"

    def __init__(
        self,
        linuxdo_username: str | None = None,
        linuxdo_password: str | None = None,
        fallback_cookies: str | None = None,
        api_user: str | None = None,
        account_name: str | None = None,
    ):
        self.linuxdo_username = linuxdo_username
        self.linuxdo_password = linuxdo_password
        self.fallback_cookies = fallback_cookies
        self.api_user = api_user
        self._account_name = account_name

        # 浏览器管理器
        self._browser_manager: BrowserManager | None = None
        self.client: httpx.Client | None = None
        self.session_cookie: str | None = None
        self._user_info: dict | None = None
        self._login_method: str = "unknown"

    @property
    def platform_name(self) -> str:
        return self.PLATFORM_NAME

    @property
    def account_name(self) -> str:
        if self._account_name:
            return self._account_name
        if self.linuxdo_username:
            return self.linuxdo_username
        return "Unknown"

    @property
    def login_url(self) -> str:
        return f"{self.BASE_URL}{self.LOGIN_PATH}"

    @property
    def console_url(self) -> str:
        return f"{self.BASE_URL}{self.CONSOLE_PATH}"

    @property
    def checkin_api(self) -> str:
        return f"{self.BASE_URL}{self.CHECKIN_API_PATH}"

    @property
    def user_info_api(self) -> str:
        return f"{self.BASE_URL}{self.USER_INFO_API_PATH}"

    async def _init_browser(self) -> None:
        """初始化浏览器"""
        engine = get_browser_engine()
        logger.info(f"[{self.account_name}] 使用浏览器引擎: {engine}")

        self._browser_manager = BrowserManager(engine=engine, headless=True)
        await self._browser_manager.start()

    @property
    def page(self):
        """获取当前页面"""
        return self._browser_manager.page if self._browser_manager else None

    async def login(self) -> bool:
        """执行登录操作"""
        # 尝试 LinuxDO OAuth 登录
        if self.linuxdo_username and self.linuxdo_password:
            logger.info(f"[{self.account_name}] 尝试使用 LinuxDO OAuth 登录...")
            try:
                if await self._login_via_linuxdo():
                    self._login_method = "LinuxDO OAuth"
                    logger.success(f"[{self.account_name}] LinuxDO OAuth 登录成功")
                    return True
            except Exception as e:
                logger.warning(f"[{self.account_name}] LinuxDO OAuth 登录失败: {e}")
                import traceback
                traceback.print_exc()

        # 回退到 Cookie 登录
        if self.fallback_cookies:
            logger.info(f"[{self.account_name}] 回退到 Cookie 登录...")
            if await self._login_via_cookie():
                self._login_method = "Cookie"
                logger.success(f"[{self.account_name}] Cookie 登录成功")
                return True

        logger.error(f"[{self.account_name}] 所有登录方式均失败")
        return False

    async def _login_via_linuxdo(self) -> bool:
        """通过 LinuxDO OAuth 登录"""
        await self._init_browser()
        page = self.page
        engine = get_browser_engine()

        try:
            logger.info(f"[{self.account_name}] 访问 {self.PLATFORM_NAME} 登录页面...")

            # 根据引擎选择登录方法
            if engine == "nodriver":
                return await self._login_via_linuxdo_nodriver()
            elif engine == "drissionpage":
                return await self._login_via_linuxdo_drissionpage()
            else:
                return await self._login_via_linuxdo_playwright()

        except Exception as e:
            logger.error(f"[{self.account_name}] LinuxDO OAuth 登录异常: {e}")
            return False

    async def _login_via_linuxdo_nodriver(self) -> bool:
        """使用 nodriver 进行 LinuxDO OAuth 登录（最强反检测）"""
        tab = self.page

        # 访问登录页面
        await tab.get(self.login_url)
        await self._browser_manager.wait_for_cloudflare(timeout=30)
        await asyncio.sleep(2)

        logger.info(f"[{self.account_name}] 查找 LinuxDO 登录按钮...")

        # 先勾选同意协议（如果有）
        try:
            checkbox = await tab.select('input[type="checkbox"]', timeout=2)
            if checkbox:
                await checkbox.click()
                await asyncio.sleep(0.5)
        except Exception:
            pass

        # 尝试直接找 LinuxDO 按钮
        linuxdo_btn = None
        try:
            linuxdo_btn = await tab.find("使用 LinuxDO 继续", timeout=2)
        except Exception:
            pass

        if not linuxdo_btn:
            try:
                linuxdo_btn = await tab.find("LinuxDO", timeout=2)
            except Exception:
                pass

        # 如果没找到，尝试点击"注册"按钮
        if not linuxdo_btn:
            logger.info(f"[{self.account_name}] 登录页未找到 LinuxDO 按钮，尝试切换到注册页...")
            try:
                register_btn = await tab.find("注册", timeout=2)
                if register_btn:
                    await register_btn.click()
                    await asyncio.sleep(2)

                    linuxdo_btn = await tab.find("使用 LinuxDO 继续", timeout=2)
                    if not linuxdo_btn:
                        linuxdo_btn = await tab.find("LinuxDO", timeout=2)
            except Exception:
                pass

        if not linuxdo_btn:
            logger.error(f"[{self.account_name}] 未找到 LinuxDO 登录按钮")
            return False

        logger.info(f"[{self.account_name}] 点击 LinuxDO 登录按钮...")
        await linuxdo_btn.click()
        await asyncio.sleep(3)

        # 等待 Cloudflare 验证
        await self._browser_manager.wait_for_cloudflare(timeout=30)

        current_url = tab.target.url
        logger.info(f"[{self.account_name}] 当前页面: {current_url}")

        if "linux.do" in current_url:
            logger.info(f"[{self.account_name}] 需要登录 LinuxDO...")

            # 等待登录表单
            try:
                username_input = await tab.select('#login-account-name', timeout=10)
                if username_input:
                    await username_input.send_keys(self.linuxdo_username)
                    await asyncio.sleep(0.5)

                    password_input = await tab.select('#login-account-password')
                    if password_input:
                        await password_input.send_keys(self.linuxdo_password)
                        await asyncio.sleep(0.5)

                    login_btn = await tab.select('#login-button', timeout=2)
                    if login_btn:
                        await login_btn.click()
                    else:
                        btn = await tab.find("登录")
                        if btn:
                            await btn.click()

                    await asyncio.sleep(5)

                    # 检查授权页面
                    current_url = tab.target.url
                    if "authorize" in current_url.lower():
                        logger.info(f"[{self.account_name}] 检测到授权页面，点击授权...")
                        authorize_btn = await tab.find("授权", timeout=5)
                        if authorize_btn:
                            await authorize_btn.click()
                            await asyncio.sleep(3)
            except Exception as e:
                logger.warning(f"[{self.account_name}] LinuxDO 登录表单操作失败: {e}")

        # 等待跳转回目标站点
        for _ in range(10):
            current_url = tab.target.url
            if self.COOKIE_DOMAIN in current_url and "login" not in current_url:
                logger.info(f"[{self.account_name}] 已跳转回 {self.PLATFORM_NAME}: {current_url}")
                break
            await asyncio.sleep(1)

        # 获取 session cookie
        self.session_cookie = await self._browser_manager.get_cookie("session", self.COOKIE_DOMAIN)

        if not self.session_cookie:
            logger.error(f"[{self.account_name}] 未获取到 session cookie")
            return False

        logger.info(f"[{self.account_name}] 获取到 session cookie")
        self._init_http_client()
        return await self._verify_login()

    async def _login_via_linuxdo_drissionpage(self) -> bool:
        """使用 DrissionPage 进行 LinuxDO OAuth 登录"""
        page = self.page

        # 访问登录页面
        page.get(self.login_url)
        await self._browser_manager.wait_for_cloudflare(timeout=30)
        time.sleep(2)

        logger.info(f"[{self.account_name}] 查找 LinuxDO 登录按钮...")

        # 先勾选同意协议（如果有）
        checkbox = page.ele('tag:input@type=checkbox', timeout=2)
        if checkbox:
            if not checkbox.states.is_checked:
                checkbox.click()
                time.sleep(0.5)

        # 尝试直接找 LinuxDO 按钮
        linuxdo_btn = page.ele('tag:button@@text():使用 LinuxDO 继续', timeout=2)
        if not linuxdo_btn:
            linuxdo_btn = page.ele('tag:button@@text():LinuxDO', timeout=2)

        # 如果没找到，尝试点击"注册"按钮
        if not linuxdo_btn:
            logger.info(f"[{self.account_name}] 登录页未找到 LinuxDO 按钮，尝试切换到注册页...")
            register_btn = page.ele('tag:button@@text():注册', timeout=2)
            if register_btn:
                register_btn.click()
                time.sleep(2)

                linuxdo_btn = page.ele('tag:button@@text():使用 LinuxDO 继续', timeout=2)
                if not linuxdo_btn:
                    linuxdo_btn = page.ele('tag:button@@text():LinuxDO', timeout=2)

        if not linuxdo_btn:
            logger.error(f"[{self.account_name}] 未找到 LinuxDO 登录按钮")
            return False

        logger.info(f"[{self.account_name}] 点击 LinuxDO 登录按钮...")
        linuxdo_btn.click()
        time.sleep(3)

        # 等待 Cloudflare 验证
        await self._browser_manager.wait_for_cloudflare(timeout=30)

        current_url = page.url
        logger.info(f"[{self.account_name}] 当前页面: {current_url}")

        if "linux.do" in current_url:
            logger.info(f"[{self.account_name}] 需要登录 LinuxDO...")

            # 等待登录表单
            username_input = page.ele('#login-account-name', timeout=10)
            if username_input:
                username_input.input(self.linuxdo_username)
                time.sleep(0.5)

                password_input = page.ele('#login-account-password')
                if password_input:
                    password_input.input(self.linuxdo_password)
                    time.sleep(0.5)

                login_btn = page.ele('#login-button', timeout=2)
                if login_btn:
                    login_btn.click()
                else:
                    page.ele('tag:button@@text():登录').click()

                time.sleep(5)

                # 检查授权页面
                current_url = page.url
                if "authorize" in current_url.lower():
                    logger.info(f"[{self.account_name}] 检测到授权页面，点击授权...")
                    authorize_btn = page.ele('tag:button@@text():授权', timeout=5)
                    if authorize_btn:
                        authorize_btn.click()
                        time.sleep(3)

        # 等待跳转回目标站点
        for _ in range(10):
            current_url = page.url
            if self.COOKIE_DOMAIN in current_url and "login" not in current_url:
                logger.info(f"[{self.account_name}] 已跳转回 {self.PLATFORM_NAME}: {current_url}")
                break
            time.sleep(1)

        # 获取 session cookie
        self.session_cookie = await self._browser_manager.get_cookie("session", self.COOKIE_DOMAIN)

        if not self.session_cookie:
            logger.error(f"[{self.account_name}] 未获取到 session cookie")
            return False

        logger.info(f"[{self.account_name}] 获取到 session cookie")
        self._init_http_client()
        return await self._verify_login()

    async def _login_via_linuxdo_playwright(self) -> bool:
        """使用 Playwright/Patchright 进行 LinuxDO OAuth 登录"""
        page = self.page

        await page.goto(self.login_url, wait_until="networkidle", timeout=30000)
        await self._browser_manager.wait_for_cloudflare(timeout=15)
        await asyncio.sleep(2)

        logger.info(f"[{self.account_name}] 查找 LinuxDO 登录按钮...")

        # 先勾选同意协议
        checkbox = await page.query_selector('input[type="checkbox"]')
        if checkbox:
            is_checked = await checkbox.is_checked()
            if not is_checked:
                await checkbox.click()
                await asyncio.sleep(0.5)

        # 查找 LinuxDO 按钮
        linuxdo_btn = await page.query_selector('button:has-text("使用 LinuxDO 继续")')
        if not linuxdo_btn:
            linuxdo_btn = await page.query_selector('button:has-text("LinuxDO")')

        if not linuxdo_btn:
            logger.info(f"[{self.account_name}] 登录页未找到 LinuxDO 按钮，尝试切换到注册页...")
            register_btn = await page.query_selector('button:has-text("注册")')
            if register_btn:
                await register_btn.click()
                await asyncio.sleep(2)
                linuxdo_btn = await page.query_selector('button:has-text("使用 LinuxDO 继续")')
                if not linuxdo_btn:
                    linuxdo_btn = await page.query_selector('button:has-text("LinuxDO")')

        if not linuxdo_btn:
            logger.error(f"[{self.account_name}] 未找到 LinuxDO 登录按钮")
            return False

        logger.info(f"[{self.account_name}] 点击 LinuxDO 登录按钮...")
        await linuxdo_btn.click()
        await asyncio.sleep(3)

        await self._browser_manager.wait_for_cloudflare(timeout=15)

        current_url = page.url
        logger.info(f"[{self.account_name}] 当前页面: {current_url}")

        if "linux.do" in current_url:
            logger.info(f"[{self.account_name}] 需要登录 LinuxDO...")

            await page.wait_for_selector('#login-account-name', timeout=10000)
            await page.fill('#login-account-name', self.linuxdo_username)
            await asyncio.sleep(0.5)
            await page.fill('#login-account-password', self.linuxdo_password)
            await asyncio.sleep(0.5)

            login_btn = await page.query_selector('#login-button')
            if login_btn:
                await login_btn.click()
            else:
                await page.click('button:has-text("登录")')

            await asyncio.sleep(5)

            current_url = page.url
            if "authorize" in current_url.lower():
                logger.info(f"[{self.account_name}] 检测到授权页面，点击授权...")
                authorize_btn = await page.query_selector('button:has-text("授权")')
                if authorize_btn:
                    await authorize_btn.click()
                    await asyncio.sleep(3)

        # 等待跳转回目标站点
        for _ in range(10):
            current_url = page.url
            if self.COOKIE_DOMAIN in current_url and "login" not in current_url:
                logger.info(f"[{self.account_name}] 已跳转回 {self.PLATFORM_NAME}: {current_url}")
                break
            await asyncio.sleep(1)

        self.session_cookie = await self._browser_manager.get_cookie("session", self.COOKIE_DOMAIN)

        if not self.session_cookie:
            logger.error(f"[{self.account_name}] 未获取到 session cookie")
            return False

        logger.info(f"[{self.account_name}] 获取到 session cookie")
        self._init_http_client()
        return await self._verify_login()

    async def _login_via_cookie(self) -> bool:
        """通过 Cookie 登录"""
        if not self.fallback_cookies:
            return False

        self.session_cookie = self._parse_session_cookie(self.fallback_cookies)
        if not self.session_cookie:
            logger.error(f"[{self.account_name}] 无法解析 session cookie")
            return False

        self._init_http_client()
        return await self._verify_login()

    def _parse_session_cookie(self, cookies_data) -> str | None:
        """解析 session cookie"""
        if isinstance(cookies_data, dict):
            return cookies_data.get("session")

        if isinstance(cookies_data, str):
            if cookies_data.startswith("session="):
                return cookies_data.split("=", 1)[1].split(";")[0]

            if "=" not in cookies_data or cookies_data.count("=") == 0:
                return cookies_data

            for cookie in cookies_data.split(";"):
                if "=" in cookie:
                    key, value = cookie.strip().split("=", 1)
                    if key.strip() == "session":
                        return value.strip()

            return cookies_data

        return None

    def _init_http_client(self) -> None:
        """初始化 HTTP 客户端"""
        self.client = httpx.Client(timeout=30.0)
        self.client.cookies.set("session", self.session_cookie, domain=self.COOKIE_DOMAIN)

    async def _verify_login(self) -> bool:
        """验证登录状态"""
        try:
            headers = self._build_headers()
            response = self.client.get(self.user_info_api, headers=headers)

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    user_data = data.get("data", {})
                    username = user_data.get("username", "Unknown")
                    logger.info(f"[{self.account_name}] 登录验证成功，用户: {username}")
                    return True

            logger.error(f"[{self.account_name}] 登录验证失败: HTTP {response.status_code}")
            return False
        except Exception as e:
            logger.error(f"[{self.account_name}] 登录验证异常: {e}")
            return False

    def _build_headers(self) -> dict:
        """构建请求头"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": self.console_url,
            "Origin": self.BASE_URL,
        }
        if self.api_user:
            headers["new-api-user"] = self.api_user
        return headers

    async def checkin(self) -> CheckinResult:
        """执行签到操作"""
        headers = self._build_headers()

        self._user_info = self._get_user_info(headers)

        details = {"login_method": self._login_method}
        if self._user_info and self._user_info.get("success"):
            details["balance"] = f"{self.CURRENCY_UNIT}{self._user_info['quota']}"
            details["used"] = f"{self.CURRENCY_UNIT}{self._user_info['used_quota']}"
            logger.info(f"[{self.account_name}] {self._user_info['display']}")

        success, message = self._execute_checkin(headers)

        if success:
            return CheckinResult(
                platform=self.platform_name,
                account=self.account_name,
                status=CheckinStatus.SUCCESS,
                message=message,
                details=details,
            )
        else:
            return CheckinResult(
                platform=self.platform_name,
                account=self.account_name,
                status=CheckinStatus.FAILED,
                message=message,
                details=details,
            )

    def _get_user_info(self, headers: dict) -> dict:
        """获取用户信息"""
        try:
            response = self.client.get(self.user_info_api, headers=headers)

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    user_data = data.get("data", {})
                    quota = round(user_data.get("quota", 0) / 500000, 2)
                    used_quota = round(user_data.get("used_quota", 0) / 500000, 2)
                    return {
                        "success": True,
                        "quota": quota,
                        "used_quota": used_quota,
                        "display": f"💰 当前余额: {self.CURRENCY_UNIT}{quota}, 已使用: {self.CURRENCY_UNIT}{used_quota}",
                    }
            return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _execute_checkin(self, headers: dict) -> tuple[bool, str]:
        """执行签到请求"""
        logger.info(f"[{self.account_name}] 执行签到请求...")

        checkin_headers = headers.copy()
        checkin_headers["Content-Type"] = "application/json"

        try:
            response = self.client.post(self.checkin_api, headers=checkin_headers)

            logger.info(f"[{self.account_name}] 签到响应: {response.status_code}")

            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get("success"):
                        message = result.get("message", "签到成功")
                        logger.success(f"[{self.account_name}] {message}")
                        return True, message
                    else:
                        error_msg = result.get("message", "签到失败")
                        if "已" in error_msg or "already" in error_msg.lower() or "今天" in error_msg:
                            logger.info(f"[{self.account_name}] {error_msg}")
                            return True, error_msg
                        logger.error(f"[{self.account_name}] {error_msg}")
                        return False, error_msg
                except Exception:
                    return False, "响应解析失败"
            else:
                return False, f"HTTP {response.status_code}"
        except Exception as e:
            logger.error(f"[{self.account_name}] 签到异常: {e}")
            return False, str(e)

    async def get_status(self) -> dict:
        """获取账号状态"""
        if self._user_info:
            return self._user_info

        if not self.client:
            return {"success": False, "error": "未登录"}

        headers = self._build_headers()
        self._user_info = self._get_user_info(headers)
        return self._user_info

    async def cleanup(self) -> None:
        """清理资源"""
        if self._browser_manager:
            with contextlib.suppress(Exception):
                await self._browser_manager.close()
            self._browser_manager = None

        if self.client:
            self.client.close()
            self.client = None
