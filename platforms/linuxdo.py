#!/usr/bin/env python3
"""
LinuxDo 论坛签到适配器

从 main.py 迁移的 LinuxDo 签到逻辑，使用 DrissionPage + curl_cffi。

Requirements:
- 2.3: 保持 DrissionPage + curl_cffi 登录逻辑
- 2.5: 保持浏览帖子、随机点赞功能
"""

import os
import random
import sys
import time
from typing import Optional

from bs4 import BeautifulSoup
from curl_cffi import requests
from DrissionPage import Chromium, ChromiumOptions
from loguru import logger
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
    
    使用 DrissionPage 进行浏览器自动化，curl_cffi 进行 API 请求。
    支持浏览帖子和随机点赞功能。
    """
    
    def __init__(
        self,
        username: str,
        password: str,
        browse_enabled: bool = True,
        account_name: Optional[str] = None,
    ):
        """初始化 LinuxDo 适配器
        
        Args:
            username: LinuxDo 用户名
            password: LinuxDo 密码
            browse_enabled: 是否启用浏览帖子功能
            account_name: 账号显示名称（可选）
        """
        self.username = username
        self.password = password
        self.browse_enabled = browse_enabled
        self._account_name = account_name
        
        self.browser: Optional[Chromium] = None
        self.page = None
        self.session: Optional[requests.Session] = None
        self._connect_info: Optional[dict] = None
    
    @property
    def platform_name(self) -> str:
        return "LinuxDo"
    
    @property
    def account_name(self) -> str:
        return self._account_name if self._account_name else self.username
    
    def _get_platform_identifier(self) -> str:
        """获取平台标识符用于 User-Agent"""
        if sys.platform == "linux" or sys.platform == "linux2":
            return "X11; Linux x86_64"
        elif sys.platform == "darwin":
            return "Macintosh; Intel Mac OS X 10_15_7"
        elif sys.platform == "win32":
            return "Windows NT 10.0; Win64; x64"
        return "X11; Linux x86_64"
    
    def _init_browser(self) -> None:
        """初始化浏览器"""
        # 清理可能影响浏览器的环境变量
        os.environ.pop("DISPLAY", None)
        os.environ.pop("DYLD_LIBRARY_PATH", None)
        
        platform_id = self._get_platform_identifier()
        
        co = (
            ChromiumOptions()
            .headless(True)
            .incognito(True)
            .set_argument("--no-sandbox")
        )
        co.set_user_agent(
            f"Mozilla/5.0 ({platform_id}) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        
        self.browser = Chromium(co)
        self.page = self.browser.new_tab()
    
    def _init_session(self) -> None:
        """初始化 HTTP 会话"""
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
    
    async def login(self) -> bool:
        """执行登录操作"""
        logger.info("开始登录 LinuxDo")
        
        self._init_browser()
        self._init_session()
        
        # Step 1: 获取 CSRF Token
        logger.info("获取 CSRF token...")
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0"
            ),
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
        
        # Step 3: 同步 Cookie 到 DrissionPage
        logger.info("同步 Cookie 到 DrissionPage...")
        cookies_dict = self.session.cookies.get_dict()
        
        dp_cookies = [
            {
                "name": name,
                "value": value,
                "domain": ".linux.do",
                "path": "/",
            }
            for name, value in cookies_dict.items()
        ]
        
        self.page.set.cookies(dp_cookies)
        
        logger.info("Cookie 设置完成，导航至 linux.do...")
        self.page.get(HOME_URL)
        
        time.sleep(5)
        
        # 验证登录状态
        try:
            user_ele = self.page.ele("@id=current-user")
            if not user_ele:
                if "avatar" in self.page.html:
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
            if not self._click_topics():
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
                message="登录成功 + 浏览任务完成",
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
                self.page.close()
            except Exception:
                pass
            self.page = None
        
        if self.browser:
            try:
                self.browser.quit()
            except Exception:
                pass
            self.browser = None
        
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
    
    def _click_topics(self) -> bool:
        """点击并浏览主题帖"""
        try:
            topic_list = self.page.ele("@id=list-area").eles(".:title")
        except Exception:
            topic_list = []
        
        if not topic_list:
            logger.error("未找到主题帖")
            return False
        
        logger.info(f"发现 {len(topic_list)} 个主题帖，随机选择浏览")
        
        # 随机选择 10-20 个帖子
        browse_count = random.randint(10, 20)
        for topic in random.sample(topic_list, min(browse_count, len(topic_list))):
            self._click_one_topic(topic.attr("href"))
        
        return True
    
    @retry_decorator(max_retries=3, delay_range=(5.0, 10.0))
    def _click_one_topic(self, topic_url: str) -> bool:
        """点击单个主题帖"""
        new_page = self.browser.new_tab()
        try:
            new_page.get(topic_url)
            if random.random() < 0.3:
                self._click_like(new_page)
            self._browse_post(new_page)
            return True
        finally:
            try:
                new_page.close()
            except Exception:
                pass
    
    def _browse_post(self, page) -> None:
        """浏览帖子内容"""
        prev_url = None
        
        for _ in range(10):
            scroll_distance = random.randint(550, 650)
            logger.info(f"向下滚动 {scroll_distance} 像素...")
            page.run_js(f"window.scrollBy(0, {scroll_distance})")
            logger.info(f"已加载页面: {page.url}")
            
            if random.random() < 0.03:
                logger.success("随机退出浏览")
                break
            
            at_bottom = page.run_js(
                "window.scrollY + window.innerHeight >= document.body.scrollHeight"
            )
            current_url = page.url
            
            if current_url != prev_url:
                prev_url = current_url
            elif at_bottom and prev_url == current_url:
                logger.success("已到达页面底部，退出浏览")
                break
            
            wait_time = random.uniform(2, 4)
            logger.info(f"等待 {wait_time:.2f} 秒...")
            time.sleep(wait_time)
    
    def _click_like(self, page) -> None:
        """点赞帖子"""
        try:
            like_button = page.ele(".discourse-reactions-reaction-button")
            if like_button:
                logger.info("找到未点赞的帖子，准备点赞")
                like_button.click()
                logger.info("点赞成功")
                time.sleep(random.uniform(1, 2))
            else:
                logger.info("帖子可能已经点过赞了")
        except Exception as e:
            logger.error(f"点赞失败: {e}")
