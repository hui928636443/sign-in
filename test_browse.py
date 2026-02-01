#!/usr/bin/env python3
"""测试新的浏览行为"""
import asyncio
import os
import sys

os.environ["BROWSER_HEADLESS"] = "false"
os.environ["BROWSER_ENGINE"] = "nodriver"

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")

async def test():
    from platforms.linuxdo import LinuxDOAdapter
    
    # 测试 L1 模式（慢速浏览）- 只浏览 2 个帖子用于测试
    adapter = LinuxDOAdapter(
        username="15021912101@139.com",
        password="Hu20100416",
        browse_count=2,  # 只浏览 2 个用于测试
        account_name="139",
        level=1,  # L1 慢速模式
    )
    
    try:
        result = await adapter.run()
        logger.info(f"结果: {result.status} - {result.message}")
        if result.details:
            logger.info(f"详情: {result.details}")
    finally:
        await adapter.cleanup()

if __name__ == "__main__":
    asyncio.run(test())
