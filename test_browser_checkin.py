#!/usr/bin/env python3
"""测试浏览器自动签到"""

import asyncio

from loguru import logger

from platforms.newapi_browser import browser_checkin_newapi

# 测试配置 - 使用 签到账户linuxdo.json 中的账户
TEST_CONFIG = {
    "provider": "hotaru",  # 要签到的站点
    "linuxdo_username": "wangwingzero@qq.com",
    "linuxdo_password": "Hu20100416",
}


async def main():
    logger.info("开始测试浏览器自动签到...")

    result = await browser_checkin_newapi(
        provider_name=TEST_CONFIG["provider"],
        linuxdo_username=TEST_CONFIG["linuxdo_username"],
        linuxdo_password=TEST_CONFIG["linuxdo_password"],
    )

    logger.info(f"签到结果: {result}")
    logger.info(f"  状态: {result.status}")
    logger.info(f"  消息: {result.message}")
    if result.details:
        logger.info(f"  详情: {result.details}")


if __name__ == "__main__":
    asyncio.run(main())
