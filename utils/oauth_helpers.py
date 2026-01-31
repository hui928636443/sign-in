#!/usr/bin/env python3
"""
OAuth 辅助工具模块

提供 OAuth 登录流程中的 URL 分类、重试机制和辅助功能。
"""

import asyncio
import functools
import inspect
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Tuple, Type, TypeVar
from urllib.parse import urlparse

from loguru import logger


T = TypeVar("T")


class OAuthURLType(Enum):
    """OAuth URL 类型枚举。
    
    用于分类 OAuth 流程中遇到的不同 URL 类型。
    """
    LINUXDO_LOGIN = "linuxdo_login"      # LinuxDO 登录页面
    AUTHORIZATION = "authorization"       # OAuth 授权页面
    OAUTH_COMPLETE = "oauth_complete"     # OAuth 完成（已返回目标站点）
    OTHER = "other"                        # 其他页面


class OAuthStep(Enum):
    """OAuth 流程步骤枚举。
    
    用于跟踪 OAuth 登录流程的进度，便于错误处理和调试。
    
    Requirements:
        - 7.1: 超时发生时，记录具体超时的步骤
        - 7.5: 记录错误时，包含当前 URL 和页面标题用于调试
    """
    INIT = "init"                                    # 初始化
    NAVIGATING_TO_LOGIN = "navigating_to_login"      # 导航到登录页面
    WAITING_CLOUDFLARE = "waiting_cloudflare"        # 等待 Cloudflare 验证
    FINDING_OAUTH_BUTTON = "finding_oauth_button"    # 查找 OAuth 按钮
    CLICKING_OAUTH_BUTTON = "clicking_oauth_button"  # 点击 OAuth 按钮
    WAITING_NAVIGATION = "waiting_navigation"        # 等待页面导航
    SWITCHING_TAB = "switching_tab"                  # 切换标签页
    FILLING_LOGIN_FORM = "filling_login_form"        # 填写登录表单
    SUBMITTING_LOGIN = "submitting_login"            # 提交登录
    HANDLING_AUTHORIZATION = "handling_authorization"  # 处理授权页面
    WAITING_REDIRECT = "waiting_redirect"            # 等待重定向
    RETRIEVING_COOKIE = "retrieving_cookie"          # 获取 Cookie
    COMPLETE = "complete"                            # 完成
    FAILED = "failed"                                # 失败


# ============================================================================
# OAuth Error Classes
# ============================================================================


class OAuthError(Exception):
    """OAuth 错误基类。
    
    所有 OAuth 相关错误的基类，包含错误发生时的上下文信息，
    便于调试和错误追踪。
    
    Attributes:
        message: 错误消息
        step: 错误发生时的 OAuth 步骤
        url: 错误发生时的页面 URL
        screenshot_path: 错误截图的保存路径（如果有）
        
    Requirements:
        - 7.1: 超时发生时，记录具体超时的步骤
        - 7.2: 元素未找到时，在失败前截图用于调试
        - 7.5: 记录错误时，包含当前 URL 和页面标题用于调试
        
    Example:
        >>> raise OAuthError(
        ...     message="登录按钮未找到",
        ...     step=OAuthStep.FINDING_OAUTH_BUTTON,
        ...     url="https://example.com/login",
        ...     screenshot_path="/tmp/error_screenshot.png"
        ... )
    """
    
    def __init__(
        self,
        message: str,
        step: OAuthStep,
        url: str = "",
        screenshot_path: Optional[str] = None,
    ):
        """初始化 OAuth 错误。
        
        Args:
            message: 错误描述信息
            step: 错误发生时的 OAuth 流程步骤
            url: 错误发生时的页面 URL，用于调试
            screenshot_path: 错误截图的保存路径，用于调试
        """
        self.message = message
        self.step = step
        self.url = url
        self.screenshot_path = screenshot_path
        
        # 构建完整的错误消息
        error_parts = [f"[{step.value}] {message}"]
        if url:
            error_parts.append(f"(URL: {url})")
        if screenshot_path:
            error_parts.append(f"(Screenshot: {screenshot_path})")
        
        super().__init__(" ".join(error_parts))
    
    def __repr__(self) -> str:
        """返回错误的详细表示。"""
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"step={self.step}, "
            f"url={self.url!r}, "
            f"screenshot_path={self.screenshot_path!r})"
        )


class NavigationTimeoutError(OAuthError):
    """导航超时错误。
    
    当页面导航超时时抛出，例如等待页面加载、等待 URL 变化等。
    
    Requirements:
        - 7.1: 超时发生时，记录具体超时的步骤
        - 2.5: URL 在超时时间内未变化时，返回超时错误
        
    Example:
        >>> raise NavigationTimeoutError(
        ...     message="等待 LinuxDO 登录页面超时",
        ...     step=OAuthStep.WAITING_NAVIGATION,
        ...     url="https://example.com/login",
        ...     timeout=30
        ... )
    """
    
    def __init__(
        self,
        message: str,
        step: OAuthStep,
        url: str = "",
        screenshot_path: Optional[str] = None,
        timeout: Optional[float] = None,
    ):
        """初始化导航超时错误。
        
        Args:
            message: 错误描述信息
            step: 错误发生时的 OAuth 流程步骤
            url: 错误发生时的页面 URL
            screenshot_path: 错误截图的保存路径
            timeout: 超时时间（秒）
        """
        self.timeout = timeout
        
        # 如果提供了超时时间，添加到消息中
        if timeout is not None:
            message = f"{message} (timeout: {timeout}s)"
        
        super().__init__(message, step, url, screenshot_path)


class ElementNotFoundError(OAuthError):
    """元素未找到错误。
    
    当页面上找不到所需元素时抛出，例如 OAuth 按钮、登录表单等。
    
    Requirements:
        - 7.2: 元素未找到时，在失败前截图用于调试
        
    Example:
        >>> raise ElementNotFoundError(
        ...     message="找不到 LinuxDO OAuth 按钮",
        ...     step=OAuthStep.FINDING_OAUTH_BUTTON,
        ...     url="https://example.com/login",
        ...     selector="#linuxdo-oauth-btn",
        ...     screenshot_path="/tmp/error_screenshot.png"
        ... )
    """
    
    def __init__(
        self,
        message: str,
        step: OAuthStep,
        url: str = "",
        screenshot_path: Optional[str] = None,
        selector: Optional[str] = None,
    ):
        """初始化元素未找到错误。
        
        Args:
            message: 错误描述信息
            step: 错误发生时的 OAuth 流程步骤
            url: 错误发生时的页面 URL
            screenshot_path: 错误截图的保存路径
            selector: 未找到的元素选择器
        """
        self.selector = selector
        
        # 如果提供了选择器，添加到消息中
        if selector:
            message = f"{message} (selector: {selector})"
        
        super().__init__(message, step, url, screenshot_path)


class CookieNotFoundError(OAuthError):
    """Cookie 未找到错误。
    
    当 OAuth 流程完成后找不到会话 Cookie 时抛出。
    
    Requirements:
        - 6.4: OAuth 完成后找不到会话 Cookie 时，等待最多 5 秒并重试
        
    Example:
        >>> raise CookieNotFoundError(
        ...     message="找不到 session cookie",
        ...     step=OAuthStep.RETRIEVING_COOKIE,
        ...     url="https://example.com/dashboard",
        ...     cookie_name="session",
        ...     domain="example.com"
        ... )
    """
    
    def __init__(
        self,
        message: str,
        step: OAuthStep,
        url: str = "",
        screenshot_path: Optional[str] = None,
        cookie_name: Optional[str] = None,
        domain: Optional[str] = None,
    ):
        """初始化 Cookie 未找到错误。
        
        Args:
            message: 错误描述信息
            step: 错误发生时的 OAuth 流程步骤
            url: 错误发生时的页面 URL
            screenshot_path: 错误截图的保存路径
            cookie_name: 未找到的 Cookie 名称
            domain: Cookie 的目标域名
        """
        self.cookie_name = cookie_name
        self.domain = domain
        
        # 构建详细消息
        details = []
        if cookie_name:
            details.append(f"cookie: {cookie_name}")
        if domain:
            details.append(f"domain: {domain}")
        
        if details:
            message = f"{message} ({', '.join(details)})"
        
        super().__init__(message, step, url, screenshot_path)


# ============================================================================
# Screenshot Capture for Error Debugging
# ============================================================================


# Default debug directory for screenshots
DEFAULT_DEBUG_DIR = "debug"


async def capture_error_screenshot(
    tab,
    step: OAuthStep,
    error_type: str = "error",
    debug_dir: str = DEFAULT_DEBUG_DIR,
) -> Optional[str]:
    """Capture a screenshot when an error occurs during OAuth flow.
    
    This function captures the current browser state as a screenshot for debugging
    purposes. It generates a unique filename with timestamp and step information,
    saves the screenshot to a debug directory, and returns the path.
    
    Args:
        tab: nodriver tab instance (the browser tab to capture)
        step: Current OAuth step when error occurred (for filename)
        error_type: Type of error (e.g., "timeout", "element_not_found")
        debug_dir: Directory to save screenshots (default: "debug")
        
    Returns:
        Path to the saved screenshot as a string, or None if capture failed
        
    Requirements:
        - 7.2: WHEN an element is not found, THE Error_Handler SHALL take a 
               screenshot for debugging before failing
               
    Example:
        >>> screenshot_path = await capture_error_screenshot(
        ...     tab=browser_tab,
        ...     step=OAuthStep.FINDING_OAUTH_BUTTON,
        ...     error_type="element_not_found"
        ... )
        >>> if screenshot_path:
        ...     logger.info(f"Screenshot saved to: {screenshot_path}")
    """
    try:
        # 1. Ensure debug directory exists
        debug_path = Path(debug_dir)
        debug_path.mkdir(parents=True, exist_ok=True)
        
        # 2. Generate unique filename with timestamp and step name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milliseconds
        step_name = step.value.replace(" ", "_")
        safe_error_type = error_type.replace(" ", "_").replace("/", "_")
        filename = f"oauth_{step_name}_{safe_error_type}_{timestamp}.png"
        
        # 3. Build full path
        screenshot_path = debug_path / filename
        
        # 4. Use nodriver's screenshot capability
        # nodriver's save_screenshot() method saves the current page state
        await tab.save_screenshot(str(screenshot_path))
        
        # 5. Verify the file was created
        if screenshot_path.exists():
            logger.info(f"[OAuth] 错误截图已保存: {screenshot_path}")
            return str(screenshot_path)
        else:
            logger.warning(f"[OAuth] 截图文件未创建: {screenshot_path}")
            return None
            
    except Exception as e:
        # 6. Handle errors gracefully - return None if screenshot fails
        logger.warning(f"[OAuth] 截图捕获失败: {e}")
        return None


def get_debug_directory() -> str:
    """Get the default debug directory path.
    
    Returns:
        The default debug directory path as a string.
    """
    return DEFAULT_DEBUG_DIR


def cleanup_old_screenshots(
    debug_dir: str = DEFAULT_DEBUG_DIR,
    max_age_hours: int = 24,
    max_files: int = 50,
) -> int:
    """Clean up old screenshot files from the debug directory.
    
    This function removes old screenshots to prevent disk space issues.
    It removes files older than max_age_hours and keeps at most max_files.
    
    Args:
        debug_dir: Directory containing screenshots
        max_age_hours: Maximum age of files to keep (in hours)
        max_files: Maximum number of files to keep
        
    Returns:
        Number of files deleted
        
    Example:
        >>> deleted = cleanup_old_screenshots(max_age_hours=12, max_files=20)
        >>> logger.info(f"Cleaned up {deleted} old screenshots")
    """
    try:
        debug_path = Path(debug_dir)
        if not debug_path.exists():
            return 0
        
        # Get all PNG files in the debug directory
        screenshots = list(debug_path.glob("oauth_*.png"))
        if not screenshots:
            return 0
        
        deleted_count = 0
        current_time = datetime.now()
        
        # Sort by modification time (oldest first)
        screenshots.sort(key=lambda p: p.stat().st_mtime)
        
        for screenshot in screenshots:
            try:
                # Check file age
                file_mtime = datetime.fromtimestamp(screenshot.stat().st_mtime)
                age_hours = (current_time - file_mtime).total_seconds() / 3600
                
                # Delete if too old or if we have too many files
                remaining = len(screenshots) - deleted_count
                if age_hours > max_age_hours or remaining > max_files:
                    screenshot.unlink()
                    deleted_count += 1
                    logger.debug(f"[OAuth] 已删除旧截图: {screenshot}")
            except Exception as e:
                logger.warning(f"[OAuth] 删除截图失败 {screenshot}: {e}")
        
        if deleted_count > 0:
            logger.info(f"[OAuth] 清理了 {deleted_count} 个旧截图文件")
        
        return deleted_count
        
    except Exception as e:
        logger.warning(f"[OAuth] 清理截图目录失败: {e}")
        return 0


# ============================================================================
# URL Classification Functions
# ============================================================================


def classify_oauth_url(url: str, target_domain: str) -> OAuthURLType:
    """分类 OAuth 流程中的 URL。
    
    根据 URL 内容判断当前处于 OAuth 流程的哪个阶段。
    
    分类规则（按优先级）：
    1. 授权页面：URL 包含 "authorize"（包括 connect.linux.do/oauth2/authorize）
    2. LinuxDO 登录页面：URL 包含 "linux.do" 但不包含 "authorize"
    3. OAuth 完成：URL 包含目标域名且不包含 "login"
    4. 其他：以上都不满足
    
    Args:
        url: 要分类的 URL 字符串
        target_domain: 目标站点域名（如 "example.com"）
        
    Returns:
        OAuthURLType 枚举值，表示 URL 的类型
        
    Examples:
        >>> classify_oauth_url("https://connect.linux.do/oauth2/authorize", "example.com")
        OAuthURLType.AUTHORIZATION
        
        >>> classify_oauth_url("https://linux.do/login", "example.com")
        OAuthURLType.LINUXDO_LOGIN
        
        >>> classify_oauth_url("https://example.com/dashboard", "example.com")
        OAuthURLType.OAUTH_COMPLETE
        
        >>> classify_oauth_url("https://google.com", "example.com")
        OAuthURLType.OTHER
    """
    # 处理空 URL 或非字符串输入
    if not url or not isinstance(url, str):
        return OAuthURLType.OTHER
    
    # 处理空目标域名
    if not target_domain or not isinstance(target_domain, str):
        target_domain = ""
    
    # 转换为小写进行比较（URL 不区分大小写）
    url_lower = url.lower()
    target_domain_lower = target_domain.lower().strip()
    
    # 规则 1: 授权页面 - URL 包含 "authorize"（最高优先级）
    # 这包括 connect.linux.do/oauth2/authorize 等授权确认页面
    if "authorize" in url_lower:
        return OAuthURLType.AUTHORIZATION
    
    # 规则 2: LinuxDO 登录页面 - URL 包含 "linux.do"
    # 这是 OAuth 提供者的登录页面
    if "linux.do" in url_lower:
        return OAuthURLType.LINUXDO_LOGIN
    
    # 规则 3: OAuth 完成 - URL 包含目标域名且不包含 "login"
    # 表示已成功返回目标站点
    if target_domain_lower and target_domain_lower in url_lower:
        if "login" not in url_lower:
            return OAuthURLType.OAUTH_COMPLETE
    
    # 规则 4: 其他 - 以上都不满足
    return OAuthURLType.OTHER


def is_linuxdo_login_url(url: str) -> bool:
    """检查 URL 是否为 LinuxDO 登录页面。
    
    Args:
        url: 要检查的 URL
        
    Returns:
        如果是 LinuxDO 登录页面返回 True，否则返回 False
    """
    return classify_oauth_url(url, "") == OAuthURLType.LINUXDO_LOGIN


def is_authorization_url(url: str) -> bool:
    """检查 URL 是否为授权页面。
    
    Args:
        url: 要检查的 URL
        
    Returns:
        如果是授权页面返回 True，否则返回 False
    """
    if not url or not isinstance(url, str):
        return False
    # 注意：如果 URL 同时包含 linux.do 和 authorize，
    # 应该优先识别为 LinuxDO 登录页面
    if "linux.do" in url.lower():
        return False
    return "authorize" in url.lower()


def is_oauth_complete_url(url: str, target_domain: str) -> bool:
    """检查 URL 是否表示 OAuth 流程完成。
    
    Args:
        url: 要检查的 URL
        target_domain: 目标站点域名
        
    Returns:
        如果 OAuth 流程完成返回 True，否则返回 False
    """
    return classify_oauth_url(url, target_domain) == OAuthURLType.OAUTH_COMPLETE


def is_oauth_related_url(url: str) -> bool:
    """检查 URL 是否与 OAuth 流程相关。
    
    用于识别 OAuth 相关的标签页。
    
    Args:
        url: 要检查的 URL
        
    Returns:
        如果 URL 与 OAuth 相关返回 True，否则返回 False
    """
    if not url or not isinstance(url, str):
        return False
    
    url_lower = url.lower()
    
    # 检查是否包含 OAuth 相关关键词
    oauth_keywords = ["linux.do", "oauth", "authorize", "callback"]
    return any(keyword in url_lower for keyword in oauth_keywords)


# ============================================================================
# Retry Mechanism for OAuth Flow
# ============================================================================


def async_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    exceptions: Optional[Tuple[Type[Exception], ...]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """异步重试装饰器，支持指数退避。
    
    用于 OAuth 流程中的异步操作重试，如网络请求、页面导航等。
    
    Args:
        max_retries: 最大重试次数，默认 3 次
        base_delay: 基础延迟时间（秒），默认 1.0 秒
        backoff_factor: 退避因子，每次重试延迟乘以此因子，默认 2.0
        max_delay: 最大延迟时间（秒），默认 30.0 秒
        exceptions: 需要重试的异常类型元组，默认所有 Exception
        
    Returns:
        装饰后的异步函数
        
    Example:
        @async_retry(max_retries=3, base_delay=1.0, backoff_factor=2.0)
        async def fetch_page():
            ...
            
    Requirements:
        - 4.5: 登录表单提交失败时，最多重试 3 次，使用递增延迟
        - 7.1: 超时发生时，记录具体超时的步骤
    """
    retry_exceptions = exceptions or (Exception,)
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError(f"async_retry 只能用于异步函数，但 {func.__name__} 不是异步函数")
        
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            
            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        # 计算指数退避延迟
                        delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                        
                        logger.warning(
                            f"[{func.__name__}] 第 {attempt}/{max_retries} 次尝试失败: {e}. "
                            f"将在 {delay:.2f} 秒后重试..."
                        )
                        
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"[{func.__name__}] 所有 {max_retries} 次重试均失败. "
                            f"最后错误: {e}"
                        )
            
            # 所有重试失败，抛出最后一个异常
            if last_exception:
                raise last_exception
            
            # 理论上不会到达这里
            raise RuntimeError(f"[{func.__name__}] 重试逻辑异常")
        
        return wrapper
    
    return decorator


async def retry_async_operation(
    operation: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    operation_name: str = "operation",
    exceptions: Optional[Tuple[Type[Exception], ...]] = None,
) -> T:
    """执行异步操作并在失败时重试。
    
    这是一个函数式的重试工具，适用于不方便使用装饰器的场景。
    
    Args:
        operation: 要执行的异步操作（无参数的 callable）
        max_retries: 最大重试次数，默认 3 次
        base_delay: 基础延迟时间（秒），默认 1.0 秒
        backoff_factor: 退避因子，默认 2.0
        max_delay: 最大延迟时间（秒），默认 30.0 秒
        operation_name: 操作名称，用于日志记录
        exceptions: 需要重试的异常类型元组
        
    Returns:
        操作的返回值
        
    Raises:
        最后一次失败的异常
        
    Example:
        result = await retry_async_operation(
            lambda: page.click("#button"),
            max_retries=3,
            operation_name="click_button"
        )
        
    Requirements:
        - 4.5: 登录表单提交失败时，最多重试 3 次，使用递增延迟
        - 7.1: 超时发生时，记录具体超时的步骤
    """
    retry_exceptions = exceptions or (Exception,)
    last_exception: Optional[Exception] = None
    
    for attempt in range(1, max_retries + 1):
        try:
            if inspect.iscoroutinefunction(operation):
                return await operation()
            else:
                # 如果 operation 返回 coroutine
                result = operation()
                if inspect.iscoroutine(result):
                    return await result
                return result
        except retry_exceptions as e:
            last_exception = e
            
            if attempt < max_retries:
                # 计算指数退避延迟
                delay = min(base_delay * (backoff_factor ** (attempt - 1)), max_delay)
                
                logger.warning(
                    f"[{operation_name}] 第 {attempt}/{max_retries} 次尝试失败: {e}. "
                    f"将在 {delay:.2f} 秒后重试..."
                )
                
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"[{operation_name}] 所有 {max_retries} 次重试均失败. "
                    f"最后错误: {e}"
                )
    
    # 所有重试失败，抛出最后一个异常
    if last_exception:
        raise last_exception
    
    raise RuntimeError(f"[{operation_name}] 重试逻辑异常")
