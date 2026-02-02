#!/usr/bin/env python3
"""
NewAPI 站点浏览器自动签到模块

使用 nodriver 浏览器自动化来处理：
1. Cloudflare 验证
2. LinuxDO OAuth 登录
3. 自动签到

适用于 session 过期时间短的站点，每次签到时实时获取新 session。
"""

import asyncio
import json

import nodriver as uc
from loguru import logger

from platforms.base import CheckinResult, CheckinStatus
from utils.config import DEFAULT_PROVIDERS, ProviderConfig


class NewAPIBrowserCheckin:
    """NewAPI 站点浏览器自动签到"""

    # LinuxDO 登录相关
    LINUXDO_URL = "https://linux.do"
    LINUXDO_LOGIN_URL = "https://linux.do/login"

    def __init__(
        self,
        provider_name: str,
        linuxdo_username: str,
        linuxdo_password: str,
        account_name: str | None = None,
    ):
        """初始化

        Args:
            provider_name: 站点名称（如 hotaru, lightllm, techstar）
            linuxdo_username: LinuxDO 用户名
            linuxdo_password: LinuxDO 密码
            account_name: 账号显示名称
        """
        self.provider_name = provider_name
        self.linuxdo_username = linuxdo_username
        self.linuxdo_password = linuxdo_password
        self._account_name = account_name or f"{provider_name}_{linuxdo_username}"

        # 获取 provider 配置
        if provider_name in DEFAULT_PROVIDERS:
            self.provider = ProviderConfig.from_dict(provider_name, DEFAULT_PROVIDERS[provider_name])
        else:
            raise ValueError(f"未知的 provider: {provider_name}")

        self.browser = None
        self.tab = None

    @property
    def account_name(self) -> str:
        return self._account_name

    async def _wait_for_cloudflare(self, timeout: int = 30) -> bool:
        """等待 Cloudflare 挑战完成"""
        logger.info(f"[{self.account_name}] 检测 Cloudflare 挑战...")

        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                title = await self.tab.evaluate("document.title")

                cf_indicators = [
                    "just a moment",
                    "checking your browser",
                    "please wait",
                    "verifying",
                    "请稍候",
                ]

                title_lower = title.lower() if title else ""
                is_cf_page = any(ind in title_lower for ind in cf_indicators)

                if not is_cf_page and title:
                    logger.success(f"[{self.account_name}] Cloudflare 验证通过！")
                    return True

                if is_cf_page:
                    logger.debug(f"[{self.account_name}] 等待 Cloudflare... 标题: {title}")

            except Exception as e:
                logger.debug(f"[{self.account_name}] 检查页面状态出错: {e}")

            await asyncio.sleep(2)

        logger.warning(f"[{self.account_name}] Cloudflare 验证超时")
        return False

    async def _login_linuxdo(self) -> bool:
        """登录 LinuxDO"""
        logger.info(f"[{self.account_name}] 访问 LinuxDO 首页...")
        await self.tab.get(self.LINUXDO_URL)

        # 等待 Cloudflare
        if not await self._wait_for_cloudflare(timeout=30):
            await self.tab.reload()
            if not await self._wait_for_cloudflare(timeout=20):
                return False

        # 检查是否已经登录（通过检查页面上是否有用户头像或通知按钮）
        try:
            is_logged_in = await self.tab.evaluate("""
                (function() {
                    // 检查是否有用户菜单或通知按钮（已登录的标志）
                    const userMenu = document.querySelector('.current-user, .header-dropdown-toggle.current-user');
                    const notifications = document.querySelector('button[aria-label*="通知"], .ring-bell-icon');
                    return !!(userMenu || notifications);
                })()
            """)
            if is_logged_in:
                logger.success(f"[{self.account_name}] LinuxDO 已登录（检测到用户菜单）")
                return True
        except Exception:
            pass

        # 访问登录页
        logger.info(f"[{self.account_name}] 访问 LinuxDO 登录页...")
        await self.tab.get(self.LINUXDO_LOGIN_URL)
        await asyncio.sleep(3)

        # 等待登录表单
        for _ in range(10):
            try:
                has_input = await self.tab.evaluate("""
                    !!document.querySelector('#login-account-name, input[name="login"]')
                """)
                if has_input:
                    break
            except Exception:
                pass
            await asyncio.sleep(1)

        # 输入用户名
        try:
            # 等待输入框出现
            await asyncio.sleep(1)
            
            username_input = await self.tab.select('#login-account-name', timeout=5)
            if not username_input:
                username_input = await self.tab.select('input[name="login"]', timeout=3)

            if username_input:
                await username_input.click()
                await asyncio.sleep(0.3)
                await username_input.send_keys(self.linuxdo_username)
                logger.info(f"[{self.account_name}] 已输入用户名")
                await asyncio.sleep(0.5)
            else:
                logger.error(f"[{self.account_name}] 未找到用户名输入框")
                return False
        except Exception as e:
            logger.error(f"[{self.account_name}] 输入用户名失败: {e}")
            return False

        # 输入密码
        try:
            password_input = await self.tab.select('#login-account-password', timeout=5)
            if not password_input:
                password_input = await self.tab.select('input[type="password"]', timeout=3)

            if password_input:
                await password_input.click()
                await asyncio.sleep(0.3)
                await password_input.send_keys(self.linuxdo_password)
                logger.info(f"[{self.account_name}] 已输入密码")
                await asyncio.sleep(0.5)
            else:
                logger.error(f"[{self.account_name}] 未找到密码输入框")
                return False
        except Exception as e:
            logger.error(f"[{self.account_name}] 输入密码失败: {e}")
            return False

        # 点击登录
        logger.info(f"[{self.account_name}] 点击登录按钮...")
        try:
            await asyncio.sleep(1)
            clicked = await self.tab.evaluate("""
                (function() {
                    const btn = document.querySelector('#login-button, button[type="submit"]');
                    if (btn) { btn.click(); return true; }
                    return false;
                })()
            """)
            if not clicked:
                logger.warning(f"[{self.account_name}] 未找到登录按钮")
                return False
        except Exception as e:
            logger.error(f"[{self.account_name}] 点击登录失败: {e}")
            return False

        # 等待登录完成（简化检测逻辑，参考 linuxdo.py 的成功实现）
        logger.info(f"[{self.account_name}] 等待登录完成...")
        for i in range(60):  # 增加到 60 秒
            await asyncio.sleep(1)

            # 主要通过 URL 变化来判断登录状态（最可靠的方式）
            current_url = self.tab.target.url if hasattr(self.tab, 'target') else ""

            # 如果 URL 不再包含 login，说明登录成功
            if current_url and "login" not in current_url.lower() and "linux.do" in current_url:
                logger.info(f"[{self.account_name}] 页面已跳转: {current_url}")
                break

            # 检查是否有错误提示（每 5 秒检查一次）
            if i % 5 == 0:
                try:
                    error_msg = await self.tab.evaluate("""
                        (function() {
                            const selectors = ['.alert-error', '.error', '.login-error', '#login-error'];
                            for (const sel of selectors) {
                                const el = document.querySelector(sel);
                                if (el && el.innerText && el.innerText.trim()) {
                                    return el.innerText.trim();
                                }
                            }
                            return '';
                        })()
                    """)
                    if error_msg:
                        logger.error(f"[{self.account_name}] 登录错误: {error_msg}")
                        return False
                except Exception:
                    pass

            if i % 10 == 0:
                logger.debug(f"[{self.account_name}] 等待登录... ({i}s)")

        await asyncio.sleep(2)

        # 最终检查登录状态
        current_url = self.tab.target.url if hasattr(self.tab, 'target') else ""
        logger.info(f"[{self.account_name}] 当前 URL: {current_url}")

        if "login" in current_url.lower():
            logger.error(f"[{self.account_name}] 登录失败，仍在登录页面")
            return False

        logger.success(f"[{self.account_name}] LinuxDO 登录成功！")
        return True

    async def _oauth_login_to_site(self) -> bool:
        """通过 LinuxDO OAuth 登录到目标站点"""
        login_url = f"{self.provider.domain}{self.provider.login_path}"
        logger.info(f"[{self.account_name}] 访问站点登录页: {login_url}")

        await self.tab.get(login_url)
        await asyncio.sleep(3)

        # 等待 Cloudflare（如果有）
        await self._wait_for_cloudflare(timeout=15)

        # 检查是否已经登录（直接跳转到控制台）
        current_url = self.tab.target.url if hasattr(self.tab, 'target') else ""
        if self.provider.domain in current_url and "login" not in current_url.lower():
            logger.success(f"[{self.account_name}] 已登录，直接进入控制台")
            return True

        # 查找并点击 LinuxDO OAuth 按钮
        logger.info(f"[{self.account_name}] 查找 LinuxDO OAuth 登录按钮...")

        # 等待页面加载
        await asyncio.sleep(2)

        for attempt in range(5):
            try:
                # 尝试多种选择器
                clicked = await self.tab.evaluate("""
                    (function() {
                        // 先尝试包含 LinuxDO 文字的按钮/链接
                        const clickables = document.querySelectorAll('button, a, div[role="button"]');
                        for (const el of clickables) {
                            const text = (el.innerText || el.textContent || '').toLowerCase();
                            // 匹配各种可能的文字
                            if (text.includes('linuxdo') || text.includes('linux do') || 
                                text.includes('使用 linuxdo') || text.includes('linuxdo 继续')) {
                                el.click();
                                return 'linuxdo_button: ' + text.substring(0, 30);
                            }
                        }

                        // 尝试通过 class 或 href 查找
                        const selectors = [
                            '[class*="linuxdo"]',
                            '[class*="oauth"]',
                            'a[href*="linuxdo"]',
                            'a[href*="oauth"]',
                        ];
                        for (const sel of selectors) {
                            try {
                                const el = document.querySelector(sel);
                                if (el) {
                                    el.click();
                                    return 'selector: ' + sel;
                                }
                            } catch (e) {}
                        }

                        return null;
                    })()
                """)

                if clicked:
                    logger.info(f"[{self.account_name}] 点击了 OAuth 按钮: {clicked}")
                    break
                else:
                    logger.debug(f"[{self.account_name}] 第 {attempt + 1} 次尝试未找到 OAuth 按钮")

            except Exception as e:
                logger.debug(f"[{self.account_name}] 查找 OAuth 按钮出错: {e}")

            await asyncio.sleep(1)

        # 等待 OAuth 跳转和授权
        logger.info(f"[{self.account_name}] 等待 OAuth 授权...")
        await asyncio.sleep(3)

        # 记录原始标签页（NewAPI 登录页）
        original_tab = self.tab
        auth_tab = None

        # 检查是否需要授权确认（最多等待 30 秒）
        for i in range(30):
            # 检查是否有新标签页打开（OAuth 可能在新标签页打开）
            if len(self.browser.tabs) > 1 and auth_tab is None:
                logger.info(f"[{self.account_name}] 检测到 {len(self.browser.tabs)} 个标签页")
                
                # 找到授权页面标签页
                for tab in self.browser.tabs:
                    tab_url = tab.target.url if hasattr(tab, 'target') else ""
                    if "connect.linux.do" in tab_url or "authorize" in tab_url.lower():
                        logger.info(f"[{self.account_name}] 找到授权标签页: {tab_url}")
                        await tab.bring_to_front()
                        auth_tab = tab
                        self.tab = tab
                        await asyncio.sleep(1)
                        break

            current_url = self.tab.target.url if hasattr(self.tab, 'target') else ""

            # 如果当前标签页已经是目标站点且不是登录页，说明授权成功
            if self.provider.domain in current_url and "login" not in current_url.lower():
                logger.success(f"[{self.account_name}] OAuth 登录成功！当前页面: {current_url}")
                return True

            # 如果在 LinuxDO 授权页面，点击允许
            if "linux.do" in current_url and ("authorize" in current_url.lower() or "oauth" in current_url.lower()):
                logger.info(f"[{self.account_name}] 检测到授权页面，尝试点击允许按钮...")
                await asyncio.sleep(2)

                try:
                    clicked = await self.tab.evaluate("""
                        (function() {
                            const clickables = document.querySelectorAll('button, a, input[type="submit"]');
                            for (const el of clickables) {
                                const text = (el.innerText || el.textContent || el.value || '').trim();
                                if (text === '允许' || text.includes('允许')) {
                                    el.click();
                                    return 'clicked: ' + text + ' (' + el.tagName + ')';
                                }
                            }
                            return null;
                        })()
                    """)

                    if clicked:
                        logger.info(f"[{self.account_name}] {clicked}")
                        # 点击允许后，等待授权完成和页面跳转
                        await asyncio.sleep(3)
                        
                        # 授权完成后，查找已登录的目标站点标签页
                        for _ in range(10):  # 最多等待 10 秒
                            for tab in self.browser.tabs:
                                tab_url = tab.target.url if hasattr(tab, 'target') else ""
                                # 找到目标站点且不是登录页、不是 OAuth 回调页的标签页
                                if (self.provider.domain in tab_url and 
                                    "login" not in tab_url.lower() and
                                    "oauth" not in tab_url.lower() and
                                    "code=" not in tab_url):
                                    logger.info(f"[{self.account_name}] 找到已登录的目标站点: {tab_url}")
                                    await tab.bring_to_front()
                                    self.tab = tab
                                    await asyncio.sleep(1)
                                    return True
                            await asyncio.sleep(1)
                        
                        # 如果没找到完全跳转的页面，检查是否有 OAuth 回调页面（会自动跳转）
                        for tab in self.browser.tabs:
                            tab_url = tab.target.url if hasattr(tab, 'target') else ""
                            if self.provider.domain in tab_url:
                                logger.info(f"[{self.account_name}] 切换到目标站点标签页: {tab_url}")
                                await tab.bring_to_front()
                                self.tab = tab
                                # 等待 OAuth 回调完成跳转
                                for _ in range(10):
                                    await asyncio.sleep(1)
                                    new_url = self.tab.target.url if hasattr(self.tab, 'target') else ""
                                    if "login" not in new_url.lower() and "oauth" not in new_url.lower() and "code=" not in new_url:
                                        logger.success(f"[{self.account_name}] OAuth 回调完成: {new_url}")
                                        return True
                                break
                    else:
                        logger.warning(f"[{self.account_name}] 未找到允许按钮")

                except Exception as e:
                    logger.debug(f"[{self.account_name}] 点击授权按钮出错: {e}")

            # 每隔一段时间检查所有标签页，看是否有已登录的
            if i % 3 == 0:
                for tab in self.browser.tabs:
                    tab_url = tab.target.url if hasattr(tab, 'target') else ""
                    if self.provider.domain in tab_url and "login" not in tab_url.lower():
                        logger.info(f"[{self.account_name}] 发现已登录标签页: {tab_url}")
                        await tab.bring_to_front()
                        self.tab = tab
                        return True

            await asyncio.sleep(1)

            if i % 5 == 0 and i > 0:
                logger.debug(f"[{self.account_name}] 等待 OAuth 完成... ({i}s)")

        # 最终检查
        current_url = self.tab.target.url if hasattr(self.tab, 'target') else ""
        if self.provider.domain in current_url:
            logger.success(f"[{self.account_name}] 已进入目标站点")
            return True

        logger.error(f"[{self.account_name}] OAuth 登录失败，当前 URL: {current_url}")
        return False

    async def _do_checkin(self) -> tuple[bool, str, dict]:
        """执行签到

        Returns:
            (成功与否, 消息, 详情)
        """
        import json
        details = {}

        # 等待页面完全加载
        await asyncio.sleep(2)

        # 先获取 new-api-user 值（从 cookie 或 localStorage）
        api_user = None
        try:
            # 从 cookie 获取
            import nodriver.cdp.network as cdp_network
            all_cookies = await self.tab.send(cdp_network.get_all_cookies())
            for c in all_cookies:
                if c.name == self.provider.api_user_key:
                    api_user = c.value
                    logger.info(f"[{self.account_name}] 从 cookie 获取到 api_user: {api_user}")
                    break
            
            # 如果 cookie 中没有，尝试从 localStorage 获取
            if not api_user:
                api_user = await self.tab.evaluate(f'''
                    localStorage.getItem("{self.provider.api_user_key}") || 
                    localStorage.getItem("user_id") || 
                    localStorage.getItem("userId")
                ''')
                if api_user:
                    logger.info(f"[{self.account_name}] 从 localStorage 获取到 api_user: {api_user}")
        except Exception as e:
            logger.warning(f"[{self.account_name}] 获取 api_user 失败: {e}")

        # 使用同步 XMLHttpRequest 发送请求
        # 1. 先获取用户信息
        user_info_url = f"{self.provider.domain}{self.provider.user_info_path}"
        logger.info(f"[{self.account_name}] 获取用户信息: {user_info_url}")

        # 构建请求头 JS
        api_user_header = f'xhr.setRequestHeader("{self.provider.api_user_key}", "{api_user}");' if api_user else ''

        try:
            user_info_result = await self.tab.evaluate(f'''
                (function() {{
                    var xhr = new XMLHttpRequest();
                    xhr.open("GET", "{user_info_url}", false);
                    xhr.setRequestHeader("Accept", "application/json");
                    {api_user_header}
                    xhr.withCredentials = true;
                    try {{
                        xhr.send();
                        return JSON.stringify({{status: xhr.status, data: JSON.parse(xhr.responseText)}});
                    }} catch (e) {{
                        return JSON.stringify({{error: e.message, status: xhr.status}});
                    }}
                }})()
            ''')

            logger.debug(f"[{self.account_name}] 用户信息响应: {user_info_result}")
            
            if user_info_result:
                result = json.loads(user_info_result)
                if result.get("status") == 200 and result.get("data", {}).get("success"):
                    user_data = result["data"].get("data", {})
                    quota = round(user_data.get("quota", 0) / 500000, 2)
                    used_quota = round(user_data.get("used_quota", 0) / 500000, 2)
                    details["balance"] = f"${quota}"
                    details["used"] = f"${used_quota}"
                    logger.info(f"[{self.account_name}] 余额: ${quota}, 已用: ${used_quota}")
                else:
                    logger.warning(f"[{self.account_name}] 获取用户信息失败: {result}")
        except Exception as e:
            logger.warning(f"[{self.account_name}] 获取用户信息失败: {e}")

        # 2. 执行签到（如果需要）
        if self.provider.needs_manual_check_in():
            checkin_url = f"{self.provider.domain}{self.provider.sign_in_path}"
            logger.info(f"[{self.account_name}] 执行签到: {checkin_url}")

            try:
                checkin_result = await self.tab.evaluate(f'''
                    (function() {{
                        var xhr = new XMLHttpRequest();
                        xhr.open("POST", "{checkin_url}", false);
                        xhr.setRequestHeader("Accept", "application/json");
                        xhr.setRequestHeader("Content-Type", "application/json");
                        {api_user_header}
                        xhr.withCredentials = true;
                        try {{
                            xhr.send();
                            return JSON.stringify({{status: xhr.status, data: JSON.parse(xhr.responseText)}});
                        }} catch (e) {{
                            return JSON.stringify({{error: e.message, status: xhr.status}});
                        }}
                    }})()
                ''')

                logger.debug(f"[{self.account_name}] 签到响应: {checkin_result}")

                if checkin_result:
                    result = json.loads(checkin_result)

                    if result.get("status") == 200:
                        data = result.get("data", {})
                        msg = data.get("message") or data.get("msg") or ""

                        if data.get("success") or "已签到" in msg or "签到成功" in msg:
                            msg = msg or "签到成功"
                            logger.success(f"[{self.account_name}] {msg}")
                            return True, msg, details
                        else:
                            if "已签到" in msg or "already" in msg.lower():
                                logger.info(f"[{self.account_name}] {msg}")
                                return True, msg, details
                            return False, msg or "签到失败", details
                    elif result.get("status") == 401:
                        return False, "未授权，请检查登录状态", details
                    elif result.get("error"):
                        return False, f"请求错误: {result.get('error')}", details
                    else:
                        return False, f"HTTP {result.get('status')}", details

            except Exception as e:
                logger.error(f"[{self.account_name}] 签到请求失败: {e}")
                return False, f"签到失败: {e}", details
        else:
            # 不需要手动签到
            return True, "签到成功（自动触发）", details

        return False, "签到失败", details

    async def run(self) -> CheckinResult:
        """执行完整的签到流程"""
        try:
            # 启动浏览器
            logger.info(f"[{self.account_name}] 启动浏览器...")
            self.browser = await uc.start(
                headless=False,  # 非 headless 更不容易被检测
                browser_args=[
                    "--disable-dev-shm-usage",
                    "--no-first-run",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            self.tab = await self.browser.get("about:blank")

            # 1. 登录 LinuxDO
            if not await self._login_linuxdo():
                return CheckinResult(
                    platform=f"NewAPI ({self.provider_name})",
                    account=self.account_name,
                    status=CheckinStatus.FAILED,
                    message="LinuxDO 登录失败",
                )

            # 2. OAuth 登录到目标站点
            if not await self._oauth_login_to_site():
                return CheckinResult(
                    platform=f"NewAPI ({self.provider_name})",
                    account=self.account_name,
                    status=CheckinStatus.FAILED,
                    message="OAuth 登录失败",
                )

            # 3. 执行签到
            success, message, details = await self._do_checkin()

            return CheckinResult(
                platform=f"NewAPI ({self.provider_name})",
                account=self.account_name,
                status=CheckinStatus.SUCCESS if success else CheckinStatus.FAILED,
                message=message,
                details=details if details else None,
            )

        except Exception as e:
            logger.error(f"[{self.account_name}] 签到异常: {e}")
            return CheckinResult(
                platform=f"NewAPI ({self.provider_name})",
                account=self.account_name,
                status=CheckinStatus.FAILED,
                message=f"签到异常: {str(e)}",
            )

        finally:
            # 关闭浏览器
            if self.browser:
                logger.info(f"[{self.account_name}] 关闭浏览器...")
                self.browser.stop()
                await asyncio.sleep(1)


async def browser_checkin_newapi(
    provider_name: str,
    linuxdo_username: str,
    linuxdo_password: str,
    account_name: str | None = None,
) -> CheckinResult:
    """便捷函数：使用浏览器签到 NewAPI 站点

    Args:
        provider_name: 站点名称
        linuxdo_username: LinuxDO 用户名
        linuxdo_password: LinuxDO 密码
        account_name: 账号显示名称

    Returns:
        签到结果
    """
    checker = NewAPIBrowserCheckin(
        provider_name=provider_name,
        linuxdo_username=linuxdo_username,
        linuxdo_password=linuxdo_password,
        account_name=account_name,
    )
    return await checker.run()
