#!/usr/bin/env python3
"""测试浏览器自动签到

支持两种模式：
1. Cookie 优先模式（默认）- 先尝试 Cookie，失败后用 OAuth
2. 纯 OAuth 模式 - 直接使用 LinuxDO OAuth 登录

LinuxDO 账户格式（签到账户/签到账户linuxdo.json）：
[
    {
        "username": "email@example.com",
        "password": "password",
        "name": "显示名称"
    }
]
"""

import asyncio
import json

from loguru import logger

from platforms.newapi_browser import browser_checkin_newapi, load_linuxdo_accounts

# 测试配置
TEST_PROVIDER = "elysiver"  # 要签到的站点：hotaru, lightllm, anyrouter, techstar, elysiver 等

# 从 签到账户newAPI.json 中获取 hotaru 的 cookie 和 api_user（可选）
# 使用无效 cookie 测试 OAuth 回退
# 对于 elysiver，直接使用 OAuth（因为有 Cloudflare 保护）
TEST_COOKIES = None  # 不使用 Cookie，直接 OAuth
TEST_API_USER = None


async def main():
    logger.info("=" * 50)
    logger.info("开始测试浏览器自动签到")
    logger.info("=" * 50)
    
    # 从配置文件加载 LinuxDO 账户
    linuxdo_accounts = load_linuxdo_accounts()
    
    if not linuxdo_accounts:
        logger.error("未找到 LinuxDO 账户配置")
        return
    
    # 使用第一个账户
    account = linuxdo_accounts[0]
    linuxdo_username = account.get("username")
    linuxdo_password = account.get("password")
    account_name = account.get("name", linuxdo_username)
    
    logger.info(f"站点: {TEST_PROVIDER}")
    logger.info(f"LinuxDO 账户: {account_name}")
    logger.info(f"模式: Cookie 优先，失败后 OAuth 回退")
    logger.info("-" * 50)

    result = await browser_checkin_newapi(
        provider_name=TEST_PROVIDER,
        cookies=TEST_COOKIES,
        api_user=TEST_API_USER,
        linuxdo_username=linuxdo_username,
        linuxdo_password=linuxdo_password,
        account_name=f"{TEST_PROVIDER}_{account_name}",
    )

    logger.info("-" * 50)
    logger.info(f"签到结果:")
    logger.info(f"  平台: {result.platform}")
    logger.info(f"  账户: {result.account}")
    logger.info(f"  状态: {result.status}")
    logger.info(f"  消息: {result.message}")
    if result.details:
        logger.info(f"  详情: {result.details}")


if __name__ == "__main__":
    asyncio.run(main())
