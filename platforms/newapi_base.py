#!/usr/bin/env python3
"""
NewAPI 通用签到适配器基类

适用于所有基于 new-api/one-api 架构的公益站，如：
- WONG 公益站 (wzw.pp.ua)
- Elysiver (elysiver.h-e.top)
- KFC API (kfc-api.sxxe.net)

支持两种登录方式：
1. 优先使用 LinuxDO OAuth 自动登录
2. 失败时回退到用户提供的 Cookie
"""

import asyncio
from typing import Optional

import httpx
from loguru import logger
from patchright.async_api import async_playwright, Browser, Page

from platforms.base import BasePlatformAdapter, CheckinResult, CheckinStatus


class NewAPIAdapter(BasePlatformAdapter):
    """NewAPI 通用签到适配器基类
    
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
        linuxdo_username: Optional[str] = None,
        linuxdo_password: Optional[str] = None,
        fallback_cookies: Optional[str] = None,
        api_user: Optional[str] = None,
        account_name: Optional[str] = None,
    ):
        self.linuxdo_username = linuxdo_username
        self.linuxdo_password = linuxdo_password
        self.fallback_cookies = fallback_cookies
        self.api_user = api_user
        self._account_name = account_name
        
        self._playwright = None
        self.browser: Optional[Browser] = None
        self.context = None
        self.page: Optional[Page] = None
        self.client: Optional[httpx.Client] = None
        self.session_cookie: Optional[str] = None
        self._user_info: Optional[dict] = None
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
        """初始化 Patchright 浏览器"""
        self._playwright = await async_playwright().start()
        
        self.browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        
        self.page = await self.context.new_page()
    
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
        
        try:
            logger.info(f"[{self.account_name}] 访问 {self.PLATFORM_NAME} 登录页面...")
            await self.page.goto(self.login_url, wait_until="networkidle")
            await asyncio.sleep(2)
            
            logger.info(f"[{self.account_name}] 点击 LinuxDO 登录按钮...")
            
            # 先勾选同意协议（如果有）
            checkbox = await self.page.query_selector('input[type="checkbox"]')
            if checkbox:
                is_checked = await checkbox.is_checked()
                if not is_checked:
                    await checkbox.click()
                    await asyncio.sleep(0.5)
            
            # 点击 LinuxDO 登录按钮
            linuxdo_btn = await self.page.query_selector('button:has-text("使用 LinuxDO 继续")')
            if not linuxdo_btn:
                linuxdo_btn = await self.page.query_selector('button:has-text("LinuxDO")')
            
            if not linuxdo_btn:
                logger.error(f"[{self.account_name}] 未找到 LinuxDO 登录按钮")
                return False
            
            await linuxdo_btn.click()
            await asyncio.sleep(3)
            
            current_url = self.page.url
            logger.info(f"[{self.account_name}] 当前页面: {current_url}")
            
            if "linux.do" in current_url:
                logger.info(f"[{self.account_name}] 需要登录 LinuxDO...")
                
                await self.page.wait_for_selector('#login-account-name', timeout=10000)
                await self.page.fill('#login-account-name', self.linuxdo_username)
                await asyncio.sleep(0.5)
                await self.page.fill('#login-account-password', self.linuxdo_password)
                await asyncio.sleep(0.5)
                
                login_btn = await self.page.query_selector('#login-button')
                if login_btn:
                    await login_btn.click()
                else:
                    await self.page.click('button:has-text("登录")')
                
                await asyncio.sleep(5)
                
                current_url = self.page.url
                if "authorize" in current_url.lower():
                    logger.info(f"[{self.account_name}] 检测到授权页面，点击授权...")
                    authorize_btn = await self.page.query_selector('button:has-text("授权")')
                    if authorize_btn:
                        await authorize_btn.click()
                        await asyncio.sleep(3)
            
            # 等待跳转回目标站点
            for _ in range(10):
                current_url = self.page.url
                if self.COOKIE_DOMAIN in current_url and "login" not in current_url:
                    logger.info(f"[{self.account_name}] 已跳转回 {self.PLATFORM_NAME}: {current_url}")
                    break
                await asyncio.sleep(1)
            
            # 获取 session cookie
            cookies = await self.context.cookies()
            for cookie in cookies:
                if cookie["name"] == "session" and self.COOKIE_DOMAIN in cookie.get("domain", ""):
                    self.session_cookie = cookie["value"]
                    logger.info(f"[{self.account_name}] 获取到 session cookie")
                    break
            
            if not self.session_cookie:
                logger.error(f"[{self.account_name}] 未获取到 session cookie")
                return False
            
            self._init_http_client()
            return await self._verify_login()
            
        except Exception as e:
            logger.error(f"[{self.account_name}] LinuxDO OAuth 登录异常: {e}")
            return False
    
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
    
    def _parse_session_cookie(self, cookies_data) -> Optional[str]:
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
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
        
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
        
        if self.client:
            self.client.close()
            self.client = None
