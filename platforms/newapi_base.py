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
from utils.browser import BrowserManager, CookieRetriever, TabManager, URLMonitor, get_browser_engine
from utils.oauth_helpers import OAuthURLType, classify_oauth_url, retry_async_operation


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

        # 支持通过环境变量控制 headless 模式（用于调试）
        import os
        headless = os.environ.get("BROWSER_HEADLESS", "true").lower() != "false"
        self._browser_manager = BrowserManager(engine=engine, headless=headless)
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
        """使用 nodriver 进行 LinuxDO OAuth 登录（最强反检测）

        此方法实现了完整的 OAuth 登录流程，包括：
        1. 访问登录页面并等待 Cloudflare 验证
        2. 查找并点击 LinuxDO OAuth 按钮
        3. 处理新标签页或 URL 跳转
        4. 填写 LinuxDO 登录表单
        5. 处理授权页面
        6. 获取 session cookie

        错误处理（Requirements 7.4）：
        - 使用 try/finally 确保浏览器资源在任何失败情况下都能被清理
        - 记录清理操作的日志
        """
        tab = self.page
        oauth_success = False  # 跟踪 OAuth 流程是否成功

        try:
            # 执行 OAuth 流程核心逻辑
            oauth_success = await self._execute_nodriver_oauth_flow(tab)
            return oauth_success

        except Exception as e:
            # 记录异常信息（Requirements 7.5）
            logger.error(f"[{self.account_name}] OAuth 流程发生异常: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            # 资源清理（Requirements 7.4）
            # 如果 OAuth 流程失败，确保浏览器资源被清理
            if not oauth_success:
                logger.info(f"[{self.account_name}] OAuth 流程失败，正在清理浏览器资源...")
                try:
                    if self._browser_manager:
                        await self._browser_manager.close()
                        self._browser_manager = None
                        logger.info(f"[{self.account_name}] 浏览器资源清理完成")
                except Exception as cleanup_error:
                    logger.warning(f"[{self.account_name}] 浏览器资源清理时发生错误: {cleanup_error}")

    async def _login_to_linuxdo_first(self, tab) -> bool:
        """先登录 LinuxDO 网站，保持会话

        这样后续访问中转站点击 LinuxDO OAuth 时，会直接显示授权页面，
        不需要再输入用户名密码。

        Args:
            tab: nodriver 标签页对象

        Returns:
            bool: 登录是否成功
        """
        try:
            # 访问 LinuxDO 登录页面
            logger.info(f"[{self.account_name}] 访问 LinuxDO 登录页面...")
            await tab.get(self.LINUXDO_LOGIN_URL)
            await self._browser_manager.wait_for_cloudflare(timeout=30)
            await asyncio.sleep(3)

            # 检查是否已经登录（查找用户头像或登出按钮）
            try:
                user_menu = await tab.select('.current-user', timeout=3)
                if user_menu:
                    logger.info(f"[{self.account_name}] LinuxDO 已登录，跳过登录步骤")
                    return True
            except Exception:
                pass

            # LinuxDO 登录页面需要先点击"登录"按钮才能显示表单
            # 尝试多种方式点击登录按钮
            login_clicked = False

            # 方式1: 通过 CSS 选择器查找登录按钮
            try:
                login_btn = await tab.select('.login-button', timeout=3)
                if login_btn:
                    logger.info(f"[{self.account_name}] 通过 CSS 选择器找到登录按钮...")
                    await login_btn.click()
                    login_clicked = True
                    await asyncio.sleep(2)
            except Exception:
                pass

            # 方式2: 通过文本查找登录链接
            if not login_clicked:
                try:
                    login_link = await tab.find("登录", timeout=3)
                    if login_link:
                        logger.info(f"[{self.account_name}] 通过文本找到登录链接...")
                        await login_link.click()
                        login_clicked = True
                        await asyncio.sleep(2)
                except Exception:
                    pass

            # 方式3: 通过 header 中的登录按钮
            if not login_clicked:
                try:
                    header_buttons = await tab.select_all('header button')
                    for btn in header_buttons:
                        html = await btn.get_html()
                        if html and ('登录' in html or 'Log In' in html):
                            logger.info(f"[{self.account_name}] 通过 header 找到登录按钮...")
                            await btn.click()
                            login_clicked = True
                            await asyncio.sleep(2)
                            break
                except Exception:
                    pass

            # 等待登录模态框加载（Discourse 使用模态框显示登录表单）
            logger.info(f"[{self.account_name}] 等待登录模态框加载...")
            await asyncio.sleep(3)

            # 尝试多种选择器查找用户名输入框
            username_input = None
            selectors = [
                '#login-account-name',
                'input[name="login"]',
                'input[type="text"][autocomplete="username"]',
                '.login-modal input[type="text"]',
            ]

            for selector in selectors:
                try:
                    username_input = await tab.select(selector, timeout=5)
                    if username_input:
                        logger.info(f"[{self.account_name}] 通过选择器 '{selector}' 找到用户名输入框")
                        break
                except Exception:
                    continue

            if not username_input:
                # 打印页面内容用于调试
                try:
                    page_html = await tab.get_content()
                    if page_html:
                        if 'login-account-name' in page_html:
                            logger.info(f"[{self.account_name}] 页面包含登录表单，但选择器未匹配")
                        else:
                            logger.info(f"[{self.account_name}] 页面不包含登录表单")
                except Exception:
                    pass
                logger.warning(f"[{self.account_name}] 未找到 LinuxDO 登录表单")
                return False

            # 清空并填写用户名
            logger.info(f"[{self.account_name}] 填写 LinuxDO 用户名...")
            await username_input.clear_input()
            await asyncio.sleep(0.2)
            await username_input.send_keys(self.linuxdo_username)
            await asyncio.sleep(0.5)

            # 填写密码
            password_input = await tab.select('#login-account-password', timeout=5)
            if not password_input:
                password_input = await tab.select('input[name="password"]', timeout=3)

            if password_input:
                logger.info(f"[{self.account_name}] 填写 LinuxDO 密码...")
                await password_input.clear_input()
                await asyncio.sleep(0.2)
                await password_input.send_keys(self.linuxdo_password)
                await asyncio.sleep(0.5)

            # 点击登录按钮
            login_btn = await tab.select('#login-button', timeout=5)
            if not login_btn:
                login_btn = await tab.find("登录", timeout=3)

            if login_btn:
                logger.info(f"[{self.account_name}] 点击 LinuxDO 登录按钮...")
                await login_btn.mouse_move()
                await asyncio.sleep(0.3)
                await login_btn.mouse_click()

                # 等待登录完成（增加等待时间）
                logger.info(f"[{self.account_name}] 等待 LinuxDO 登录完成...")
                await asyncio.sleep(8)

                # 检查登录是否成功
                # 方式1: 查找用户菜单
                try:
                    user_menu = await tab.select('.current-user', timeout=5)
                    if user_menu:
                        logger.success(f"[{self.account_name}] LinuxDO 登录成功（找到用户菜单）")
                        return True
                except Exception:
                    pass

                # 方式2: 检查 URL 是否离开了登录页面
                url_monitor = URLMonitor(tab, poll_interval=0.5)
                current_url = await url_monitor.get_current_url()
                if "login" not in current_url.lower():
                    logger.success(f"[{self.account_name}] LinuxDO 登录成功（URL: {current_url}）")
                    return True

                # 方式3: 检查是否有错误提示
                try:
                    error_msg = await tab.find("用户名、电子邮件或密码无效", timeout=2)
                    if error_msg:
                        logger.error(f"[{self.account_name}] LinuxDO 登录失败：用户名或密码错误")
                        return False
                except Exception:
                    pass

            logger.warning(f"[{self.account_name}] LinuxDO 登录状态不确定，继续尝试...")
            return False

        except Exception as e:
            logger.warning(f"[{self.account_name}] LinuxDO 登录异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _handle_authorization_page(self, tab, _url_monitor) -> bool:
        """处理 OAuth 授权页面

        当用户已登录 LinuxDO 时，授权页面会显示"允许"按钮。
        如果用户未登录，需要先在授权页面登录。

        Args:
            tab: nodriver 标签页对象
            _url_monitor: URLMonitor 实例（保留用于未来扩展）

        Returns:
            bool: 授权是否成功
        """
        try:
            logger.info(f"[{self.account_name}] 处理授权页面，等待页面加载...")

            # 等待页面完全加载
            await asyncio.sleep(3)

            # 首先检查是否需要登录（授权页面可能显示登录表单）
            login_form = await tab.select('#login-account-name', timeout=3)
            if login_form:
                logger.info(f"[{self.account_name}] 授权页面需要登录，填写登录表单...")

                # 填写用户名
                await login_form.clear_input()
                await asyncio.sleep(0.2)
                await login_form.send_keys(self.linuxdo_username)
                await asyncio.sleep(0.5)

                # 填写密码
                password_input = await tab.select('#login-account-password', timeout=5)
                if password_input:
                    await password_input.clear_input()
                    await asyncio.sleep(0.2)
                    await password_input.send_keys(self.linuxdo_password)
                    await asyncio.sleep(0.5)

                # 点击登录按钮
                login_btn = await tab.select('#login-button', timeout=5)
                if login_btn:
                    logger.info(f"[{self.account_name}] 点击登录按钮...")
                    await login_btn.click()
                    await asyncio.sleep(5)
                else:
                    # 尝试通过文本查找
                    login_btn = await tab.find("登录", timeout=3)
                    if login_btn:
                        await login_btn.click()
                        await asyncio.sleep(5)

                # 登录后等待授权页面刷新
                await asyncio.sleep(2)

            logger.info(f"[{self.account_name}] 查找允许按钮...")

            # connect.linux.do 的授权页面使用"允许"按钮（红色按钮）
            authorize_btn = None

            # 方式1: 通过 CSS 选择器查找所有按钮，检查文本内容
            try:
                buttons = await tab.select_all('button')
                logger.info(f"[{self.account_name}] 找到 {len(buttons)} 个按钮")
                for btn in buttons:
                    try:
                        # 获取按钮的 HTML 和文本
                        html = await btn.get_html()
                        logger.debug(f"[{self.account_name}] 按钮 HTML: {html[:150] if html else 'N/A'}")
                        if html and '允许' in html:
                            authorize_btn = btn
                            logger.info(f"[{self.account_name}] 通过 HTML 内容找到'允许'按钮")
                            break
                    except Exception as e:
                        logger.debug(f"[{self.account_name}] 检查按钮失败: {e}")
                        continue
            except Exception as e:
                logger.debug(f"[{self.account_name}] CSS 选择器查找失败: {e}")

            # 方式2: 查找"允许"文本
            if not authorize_btn:
                try:
                    authorize_btn = await tab.find("允许", timeout=5)
                    if authorize_btn:
                        logger.info(f"[{self.account_name}] 通过 find('允许') 找到按钮")
                except Exception:
                    pass

            # 方式3: 查找"授权"按钮（备用）
            if not authorize_btn:
                try:
                    authorize_btn = await tab.find("授权", timeout=3)
                    if authorize_btn:
                        logger.info(f"[{self.account_name}] 找到'授权'按钮")
                except Exception:
                    pass

            # 方式4: 查找 "Allow" 按钮（英文版）
            if not authorize_btn:
                try:
                    authorize_btn = await tab.find("Allow", timeout=3)
                    if authorize_btn:
                        logger.info(f"[{self.account_name}] 找到'Allow'按钮")
                except Exception:
                    pass

            if authorize_btn:
                # 使用 click() 而不是 mouse_click()，更可靠
                logger.info(f"[{self.account_name}] 准备点击授权按钮...")
                try:
                    await authorize_btn.click()
                except Exception as e:
                    logger.debug(f"[{self.account_name}] click() 失败: {e}，尝试 mouse_click()...")
                    await authorize_btn.mouse_move()
                    await asyncio.sleep(0.3)
                    await authorize_btn.mouse_click()
                logger.info(f"[{self.account_name}] 已点击授权按钮，等待重定向...")
                # 增加等待时间，确保重定向完成并设置 cookie
                await asyncio.sleep(5)
                return True
            else:
                logger.warning(f"[{self.account_name}] 未找到授权按钮")
                return False

        except Exception as e:
            logger.warning(f"[{self.account_name}] 授权页面处理失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def _execute_nodriver_oauth_flow(self, tab) -> bool:
        """执行 nodriver OAuth 流程的核心逻辑

        此方法包含实际的 OAuth 登录流程，被 _login_via_linuxdo_nodriver 调用。
        将核心逻辑分离出来，使得 try/finally 资源清理更加清晰。

        流程：
        1. 先访问 linux.do 登录（保持会话）
        2. 然后访问中转站，点击 LinuxDO 按钮
        3. 此时会直接显示授权页面，点击"允许"

        Args:
            tab: nodriver 标签页对象

        Returns:
            bool: OAuth 流程是否成功
        """
        # 步骤 1: 先登录 LinuxDO（这样后续 OAuth 时就不需要再输入密码）
        logger.info(f"[{self.account_name}] 步骤1: 先登录 LinuxDO...")
        if not await self._login_to_linuxdo_first(tab):
            logger.warning(f"[{self.account_name}] LinuxDO 登录失败，继续尝试...")

        # 步骤 2: 访问中转站登录页面
        logger.info(f"[{self.account_name}] 步骤2: 访问 {self.PLATFORM_NAME} 登录页面...")
        await tab.get(self.login_url)
        await self._browser_manager.wait_for_cloudflare(timeout=30)
        await asyncio.sleep(3)

        logger.info(f"[{self.account_name}] 查找 LinuxDO 登录按钮...")

        # 特殊流程：某些 NewAPI 站点需要先访问注册页再访问登录页才能看到 LinuxDO 按钮
        # 使用直接导航而不是点击链接，避免 nodriver 的搜索会话失效问题
        try:
            # 步骤1: 导航到注册页
            register_url = self.login_url.replace("/login", "/register")
            logger.info(f"[{self.account_name}] 导航到注册页...")
            await tab.get(register_url)
            await asyncio.sleep(2)

            # 步骤2: 导航回登录页
            logger.info(f"[{self.account_name}] 导航回登录页...")
            await tab.get(self.login_url)
            await asyncio.sleep(2)
        except Exception as e:
            logger.debug(f"[{self.account_name}] 特殊流程失败: {e}")

        # 先勾选同意协议（如果有）
        try:
            agreement_area = await tab.find("我已阅读并同意", timeout=3)
            if agreement_area:
                await agreement_area.click()
                await asyncio.sleep(0.5)
                logger.info(f"[{self.account_name}] 已勾选同意协议")
        except Exception:
            try:
                checkbox = await tab.select('input[type="checkbox"]', timeout=2)
                if checkbox:
                    await checkbox.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

        # 查找 LinuxDO 按钮
        linuxdo_btn = None

        # 先打印页面上所有按钮用于调试
        try:
            all_buttons = await tab.select_all('button')
            logger.info(f"[{self.account_name}] 页面上共有 {len(all_buttons)} 个按钮")
            for i, btn in enumerate(all_buttons):
                try:
                    html = await btn.get_html()
                    if html:
                        # 只打印前100个字符
                        logger.debug(f"[{self.account_name}] 按钮 {i+1}: {html[:100]}")
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[{self.account_name}] 获取按钮列表失败: {e}")

        # 方式1: 通过 CSS 选择器查找按钮
        try:
            buttons = await tab.select_all('button')
            for btn in buttons:
                try:
                    html = await btn.get_html()
                    if html and 'LinuxDO' in html:
                        linuxdo_btn = btn
                        logger.info(f"[{self.account_name}] 通过 HTML 内容找到 LinuxDO 按钮")
                        break
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"[{self.account_name}] 通过 CSS 选择器查找按钮失败: {e}")

        # 方式2: 通过按钮文本查找
        if not linuxdo_btn:
            try:
                linuxdo_btn = await tab.find("使用 LinuxDO 继续", timeout=3)
                if linuxdo_btn:
                    logger.info(f"[{self.account_name}] 通过文本找到 LinuxDO 按钮")
            except Exception:
                pass

        # 方式3: 通过部分文本查找
        if not linuxdo_btn:
            try:
                linuxdo_btn = await tab.find("LinuxDO", timeout=3)
                if linuxdo_btn:
                    logger.info(f"[{self.account_name}] 通过 'LinuxDO' 文本找到按钮")
            except Exception:
                pass

        if not linuxdo_btn:
            # 打印页面内容用于调试
            try:
                page_html = await tab.get_content()
                if page_html:
                    if 'LinuxDO' in page_html:
                        logger.info(f"[{self.account_name}] 页面包含 'LinuxDO' 文本，但按钮未找到")
                    else:
                        logger.info(f"[{self.account_name}] 页面不包含 'LinuxDO' 文本")
            except Exception:
                pass
            logger.error(f"[{self.account_name}] 未找到 LinuxDO 登录按钮")
            return False

        # 记录点击前的标签页数量
        tab_manager = TabManager(self._browser_manager.browser)
        initial_tab_count = tab_manager.record_tab_count()
        logger.info(f"[{self.account_name}] 点击前标签页数量: {initial_tab_count}")

        # 点击 LinuxDO 按钮
        logger.info(f"[{self.account_name}] 点击 LinuxDO 登录按钮...")
        await linuxdo_btn.click()
        await asyncio.sleep(3)

        # 保存原始标签页引用，以便后续返回
        original_tab = tab

        # 检测是否打开了新标签页（OAuth 通常会打开新标签页）
        # 增加等待时间，因为新标签页可能需要一点时间才能被检测到
        new_tab = await tab_manager.detect_new_tab(timeout=8)

        if new_tab:
            # 发现新标签页，切换到新标签页
            logger.info(f"[{self.account_name}] 检测到新标签页，正在切换...")
            await tab_manager.switch_to_tab(new_tab)
            tab = new_tab
            # 等待新标签页加载
            await asyncio.sleep(2)
        else:
            # 没有新标签页，尝试查找 OAuth 相关标签页
            logger.info(f"[{self.account_name}] 未检测到新标签页，尝试查找 OAuth 相关标签页...")
            oauth_tab = await tab_manager.find_oauth_tab()
            if oauth_tab and oauth_tab != tab:
                logger.info(f"[{self.account_name}] 找到 OAuth 相关标签页，正在切换...")
                await tab_manager.switch_to_tab(oauth_tab)
                tab = oauth_tab
            else:
                # 没有新标签页也没有 OAuth 标签页，等待当前标签页 URL 变化到 LinuxDO
                logger.info(f"[{self.account_name}] 未找到新标签页，等待 URL 跳转到 LinuxDO...")
                temp_monitor = URLMonitor(tab, poll_interval=0.5)
                try:
                    await temp_monitor.wait_for_url_contains("linux.do", timeout=15)
                except TimeoutError:
                    logger.warning(f"[{self.account_name}] 等待跳转到 LinuxDO 超时，继续尝试...")

        # 等待 Cloudflare 验证（传入当前标签页）
        await self._browser_manager.wait_for_cloudflare(timeout=60, tab=tab)

        # 创建 URLMonitor 用于准确的 URL 跟踪（Requirements 1.4, 1.5, 2.1, 2.2）
        url_monitor = URLMonitor(tab, poll_interval=0.5)

        # 使用 CDP get_frame_tree() 获取准确的当前 URL（Requirements 1.5, 2.2）
        current_url = await url_monitor.get_current_url()
        logger.info(f"[{self.account_name}] 当前页面: {current_url}")

        # 使用 classify_oauth_url 检测 OAuth 状态（Requirements 2.3, 2.4, 5.1）
        url_type = classify_oauth_url(current_url, self.COOKIE_DOMAIN)
        logger.debug(f"[{self.account_name}] URL 类型: {url_type.value}")

        # 首先检查是否直接跳转到授权页面（用户已登录 LinuxDO 的情况）
        # 使用 URL 模式检测授权页面（Requirements 5.1）
        if url_type == OAuthURLType.AUTHORIZATION:
            # URL 包含 "authorize"，检测到授权页面（Requirements 5.1）
            logger.info(f"[{self.account_name}] 检测到授权页面...")

            # 处理授权页面（可能需要先登录）
            auth_result = await self._handle_authorization_page(tab, url_monitor)
            if auth_result:
                # 更新 URL 状态
                current_url = await url_monitor.get_current_url()
                url_type = classify_oauth_url(current_url, self.COOKIE_DOMAIN)
                logger.info(f"[{self.account_name}] 授权后页面: {current_url}")

        elif url_type == OAuthURLType.LINUXDO_LOGIN:
            # URL 包含 "linux.do"，需要登录 LinuxDO（Requirements 2.3）
            logger.info(f"[{self.account_name}] 需要登录 LinuxDO...")

            # 等待登录表单完全加载（Requirements 4.1）
            # 首先等待登录表单容器可见，确保整个表单已渲染
            try:
                # 等待登录表单容器加载完成
                login_form = await tab.select('#login-form', timeout=10)
                if not login_form:
                    # 备用选择器：等待登录模态框
                    login_form = await tab.select('.login-modal', timeout=5)

                if login_form:
                    logger.info(f"[{self.account_name}] 登录表单已加载")
                else:
                    logger.warning(f"[{self.account_name}] 未找到登录表单容器，继续尝试填写...")

                # 等待用户名输入框可交互（Requirements 4.1）
                username_input = await tab.select('#login-account-name', timeout=10)
                if username_input:
                    # 短暂等待确保元素完全可交互
                    await asyncio.sleep(0.3)

                    # 使用 send_keys() 填写用户名（Requirements 4.2）
                    logger.info(f"[{self.account_name}] 填写用户名...")
                    await username_input.send_keys(self.linuxdo_username)

                    # 等待输入完成，确保浏览器处理完 JS 事件
                    await asyncio.sleep(0.5)

                    # 等待密码输入框可交互（Requirements 4.1）
                    password_input = await tab.select('#login-account-password', timeout=5)
                    if password_input:
                        # 短暂等待确保元素完全可交互
                        await asyncio.sleep(0.3)

                        # 使用 send_keys() 填写密码（Requirements 4.3）
                        logger.info(f"[{self.account_name}] 填写密码...")
                        await password_input.send_keys(self.linuxdo_password)

                        # 等待输入完成
                        await asyncio.sleep(0.5)

                    # 等待登录按钮可交互并使用 mouse_click() 提交（Requirements 4.4, 4.5）
                    async def submit_login_form():
                        """提交登录表单，使用 mouse_click() 模拟真实用户点击"""
                        login_btn = await tab.select('#login-button', timeout=5)
                        if login_btn:
                            # 使用 mouse_move() + mouse_click() 模拟真实用户行为（Requirements 4.4）
                            logger.info(f"[{self.account_name}] 点击登录按钮 (使用 mouse_click)...")
                            await login_btn.mouse_move()  # 模拟鼠标移动到按钮
                            await asyncio.sleep(0.3)  # 短暂停顿，模拟人类行为
                            await login_btn.mouse_click()
                            return True
                        else:
                            # 备用方案：通过文本查找登录按钮
                            btn = await tab.find("登录")
                            if btn:
                                logger.info(f"[{self.account_name}] 通过文本查找登录按钮，点击 (使用 mouse_click)...")
                                await btn.mouse_move()
                                await asyncio.sleep(0.3)
                                await btn.mouse_click()
                                return True
                            raise Exception("未找到登录按钮")

                    # 使用重试机制提交登录表单（Requirements 4.5）
                    # 最多重试 3 次，使用指数退避延迟
                    try:
                        await retry_async_operation(
                            submit_login_form,
                            max_retries=3,
                            base_delay=1.0,
                            backoff_factor=2.0,
                            operation_name=f"[{self.account_name}] 登录表单提交"
                        )
                    except Exception as e:
                        logger.warning(f"[{self.account_name}] 登录表单提交失败: {e}")

                    await asyncio.sleep(5)

                    # 使用 URLMonitor 获取准确的 URL 检查授权页面（Requirements 2.2）
                    current_url = await url_monitor.get_current_url()
                    url_type = classify_oauth_url(current_url, self.COOKIE_DOMAIN)

                    if url_type == OAuthURLType.AUTHORIZATION:
                        # URL 包含 "authorize"，检测到授权页面（Requirements 5.1, 5.2）
                        logger.info(f"[{self.account_name}] 检测到授权页面，点击授权...")

                        # 等待页面加载
                        await asyncio.sleep(3)

                        # 先尝试查找"允许"按钮（connect.linux.do 使用这个）
                        authorize_btn = None
                        try:
                            buttons = await tab.select_all('button')
                            logger.debug(f"[{self.account_name}] 授权页面找到 {len(buttons)} 个按钮")
                            for btn in buttons:
                                try:
                                    html = await btn.get_html()
                                    if html and '允许' in html:
                                        authorize_btn = btn
                                        logger.info(f"[{self.account_name}] 通过 HTML 找到'允许'按钮")
                                        break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                        if not authorize_btn:
                            authorize_btn = await tab.find("允许", timeout=5)
                            if authorize_btn:
                                logger.info(f"[{self.account_name}] 通过 find('允许') 找到按钮")
                        if not authorize_btn:
                            authorize_btn = await tab.find("授权", timeout=3)
                            if authorize_btn:
                                logger.info(f"[{self.account_name}] 通过 find('授权') 找到按钮")

                        if authorize_btn:
                            # 使用 mouse_click() 模拟真实用户点击（Requirements 5.3）
                            logger.info(f"[{self.account_name}] 准备点击授权按钮...")
                            await authorize_btn.mouse_move()
                            await asyncio.sleep(0.3)
                            await authorize_btn.mouse_click()
                            logger.info(f"[{self.account_name}] 已点击授权按钮")
                            await asyncio.sleep(3)
                        else:
                            # 授权按钮未找到，记录警告并继续等待重定向（Requirements 5.4）
                            logger.warning(f"[{self.account_name}] 授权按钮未找到，继续等待重定向...")
            except Exception as e:
                logger.warning(f"[{self.account_name}] LinuxDO 登录表单操作失败: {e}")

        # 等待跳转回目标站点，使用 URLMonitor 进行准确的 URL 监控（Requirements 2.1, 2.2, 2.4, 2.5）
        logger.info(f"[{self.account_name}] 等待跳转回目标站点...")
        try:
            # 使用 URLMonitor 的 wait_for_url_contains 方法，以 500ms 间隔轮询（Requirements 2.1）
            # 超时时间 30 秒（Requirements 2.5）
            current_url = await url_monitor.wait_for_url_contains(self.COOKIE_DOMAIN, timeout=30)

            # 再次检查 URL 类型，确保 OAuth 完成（Requirements 2.4）
            url_type = classify_oauth_url(current_url, self.COOKIE_DOMAIN)
            if url_type == OAuthURLType.OAUTH_COMPLETE:
                logger.info(f"[{self.account_name}] 已跳转回 {self.PLATFORM_NAME}: {current_url}")
            else:
                # URL 包含目标域名但可能还在登录页面
                logger.info(f"[{self.account_name}] 当前页面: {current_url} (类型: {url_type.value})")

            # 等待页面完全加载，确保 cookie 已设置
            logger.info(f"[{self.account_name}] 等待页面完全加载...")
            await asyncio.sleep(3)

        except TimeoutError as e:
            # URL 在超时时间内没有变化，返回超时错误（Requirements 2.5）
            logger.warning(f"[{self.account_name}] 等待跳转超时: {e}")
            # 获取当前 URL 用于调试
            current_url = await url_monitor.get_current_url()
            logger.info(f"[{self.account_name}] 超时时的 URL: {current_url}")

        # 如果当前在新标签页，可能需要返回原始标签页获取 cookies（Requirements 3.4）
        # 使用 CookieRetriever 获取 session cookie（Requirements 6.1, 6.2, 6.3, 6.4）
        # CookieRetriever 使用 CDP 的 network.get_cookies() 进行准确的 cookie 获取
        # 并按 cookie 名称（"session"）和域名进行匹配，支持重试逻辑
        cookie_retriever = CookieRetriever(self._browser_manager, self.COOKIE_DOMAIN)
        self.session_cookie = await cookie_retriever.get_session_cookie(max_retries=3)

        # 如果当前标签页没有获取到 cookie，且我们切换过标签页，尝试从原始标签页获取
        if not self.session_cookie and tab != original_tab:
            logger.info(f"[{self.account_name}] 当前标签页未获取到 cookie，尝试返回原始标签页...")
            await tab_manager.switch_to_tab(original_tab)
            await asyncio.sleep(1)
            # 再次使用 CookieRetriever 获取 cookie（Requirements 6.4）
            self.session_cookie = await cookie_retriever.get_session_cookie(max_retries=3)

        if not self.session_cookie:
            logger.error(f"[{self.account_name}] 未获取到 session cookie")
            return False

        logger.info(f"[{self.account_name}] 获取到 session cookie")

        # 尝试从浏览器获取用户 ID（用于 New-Api-User header）
        # new-api 需要这个 header 才能正常调用 API
        try:
            import json as json_module
            # 等待页面 JavaScript 完全加载
            await asyncio.sleep(2)

            # 方式1: 从 localStorage 获取用户信息（new-api 使用 'user' key 存储完整用户对象）
            user_json = await tab.evaluate("localStorage.getItem('user')")
            if user_json:
                try:
                    user_data = json_module.loads(user_json)
                    if isinstance(user_data, dict) and 'id' in user_data:
                        self.api_user = str(user_data['id'])
                        logger.info(f"[{self.account_name}] 从 localStorage['user'] 获取到用户 ID: {self.api_user}")
                except (json_module.JSONDecodeError, TypeError):
                    pass

            # 方式2: 尝试其他常见的 key
            if not self.api_user:
                for key in ['user_id', 'userId', 'id']:
                    user_id = await tab.evaluate(f"localStorage.getItem('{key}')")
                    if user_id:
                        # 确保是纯数字或简单字符串
                        try:
                            # 尝试解析为 JSON（可能是 JSON 字符串）
                            parsed = json_module.loads(user_id)
                            if isinstance(parsed, dict) and 'id' in parsed:
                                self.api_user = str(parsed['id'])
                            elif isinstance(parsed, (int, str)):
                                self.api_user = str(parsed)
                        except (json_module.JSONDecodeError, TypeError):
                            # 不是 JSON，直接使用
                            self.api_user = str(user_id)
                        if self.api_user:
                            logger.info(f"[{self.account_name}] 从 localStorage['{key}'] 获取到用户 ID: {self.api_user}")
                            break

            # 方式3: 从页面 JavaScript 变量获取
            if not self.api_user:
                user_info = await tab.evaluate("window.__USER__ || window.user || window.userInfo || null")
                if user_info:
                    if isinstance(user_info, dict):
                        self.api_user = str(user_info.get('id', '') or user_info.get('user_id', ''))
                    elif isinstance(user_info, (int, str)):
                        self.api_user = str(user_info)
                    if self.api_user:
                        logger.info(f"[{self.account_name}] 从页面变量获取到用户 ID: {self.api_user}")

            # 方式4: 打印 localStorage 内容用于调试
            if not self.api_user:
                all_storage = await tab.evaluate("JSON.stringify(localStorage)")
                logger.debug(f"[{self.account_name}] localStorage 内容: {all_storage[:500] if all_storage else 'empty'}")

            # 方式4: 尝试调用 API 获取用户信息（不需要 New-Api-User header 的情况）
            if not self.api_user:
                logger.warning(f"[{self.account_name}] 未能从浏览器获取用户 ID，将尝试不带 New-Api-User header 调用 API")

        except Exception as e:
            logger.debug(f"[{self.account_name}] 获取用户 ID 失败: {e}")

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
        if checkbox and not checkbox.states.is_checked:
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
        # 设置 cookie - 使用多种方式确保 cookie 被正确发送
        # 方式1: 使用完整域名（带点前缀，适用于子域名）
        self.client.cookies.set("session", self.session_cookie, domain=f".{self.COOKIE_DOMAIN}")
        # 方式2: 使用精确域名
        self.client.cookies.set("session", self.session_cookie, domain=self.COOKIE_DOMAIN)
        logger.debug(f"[{self.account_name}] HTTP 客户端初始化完成，cookie domain: {self.COOKIE_DOMAIN}")

    async def _verify_login(self) -> bool:
        """验证登录状态"""
        try:
            headers = self._build_headers()

            logger.debug(f"[{self.account_name}] 验证登录，session cookie: {self.session_cookie[:20]}...")
            logger.debug(f"[{self.account_name}] API URL: {self.user_info_api}")

            response = self.client.get(self.user_info_api, headers=headers)
            logger.debug(f"[{self.account_name}] 响应状态: {response.status_code}")
            logger.debug(f"[{self.account_name}] 响应内容: {response.text[:200] if response.text else 'empty'}")

            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    user_data = data.get("data", {})
                    username = user_data.get("username", "Unknown")
                    logger.info(f"[{self.account_name}] 登录验证成功，用户: {username}")
                    return True

            # 如果返回 401 但有 session cookie，可能是 API 需要特殊 header
            # 尝试直接返回 True，让签到流程继续
            if response.status_code == 401 and self.session_cookie:
                error_msg = response.json().get("message", "") if response.text else ""
                if "New-Api-User" in error_msg or "access token" in error_msg:
                    logger.warning(f"[{self.account_name}] API 需要特殊认证，尝试继续签到流程...")
                    return True

            logger.error(f"[{self.account_name}] 登录验证失败: HTTP {response.status_code}")
            return False
        except Exception as e:
            logger.error(f"[{self.account_name}] 登录验证异常: {e}")
            import traceback
            traceback.print_exc()
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
        # 添加 Cookie header 作为备用方式（某些服务器可能不接受 httpx 的 cookie jar）
        if self.session_cookie:
            headers["Cookie"] = f"session={self.session_cookie}"
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
