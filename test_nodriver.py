#!/usr/bin/env python3
"""
测试 nodriver 浏览器是否能绕过 Cloudflare

nodriver 是 undetected-chromedriver 的继任者，
完全弃用 WebDriver，直接使用 CDP，是目前最强的反检测方案。
"""

import asyncio
import sys

from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")


async def test_nodriver():
    """测试 nodriver 浏览器"""
    from utils.browser import BrowserManager

    logger.info("=" * 50)
    logger.info("测试 nodriver 浏览器")
    logger.info("=" * 50)

    async with BrowserManager(engine="nodriver", headless=False) as browser:
        tab = browser.page

        # 测试 1: 访问百度（确认浏览器正常工作）
        logger.info("测试 1: 访问百度...")
        await tab.get("https://www.baidu.com")
        await asyncio.sleep(2)
        title = tab.target.title
        logger.success(f"百度访问成功! 页面标题: {title}")

        # 测试 2: 访问 LinuxDO
        logger.info("测试 2: 访问 LinuxDO...")
        await tab.get("https://linux.do")

        # 等待 Cloudflare 验证
        cf_passed = await browser.wait_for_cloudflare(timeout=30)

        if cf_passed:
            title = tab.target.title
            logger.success(f"LinuxDO 访问成功! 页面标题: {title}")
        else:
            logger.error("LinuxDO Cloudflare 验证失败")
            return False

        # 测试 3: 访问 WONG 公益站
        logger.info("测试 3: 访问 WONG 公益站...")
        await tab.get("https://wzw.pp.ua/login")

        cf_passed = await browser.wait_for_cloudflare(timeout=30)

        if cf_passed:
            title = tab.target.title
            logger.success(f"WONG 公益站访问成功! 页面标题: {title}")
        else:
            logger.error("WONG 公益站 Cloudflare 验证失败")
            return False

        logger.info("=" * 50)
        logger.success("所有测试通过!")
        logger.info("=" * 50)
        return True


async def main():
    """主函数"""
    logger.info("开始测试 nodriver...")

    try:
        ok = await test_nodriver()
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        ok = False

    # 总结
    logger.info("")
    logger.info("=" * 50)
    logger.info("测试总结")
    logger.info("=" * 50)
    logger.info(f"nodriver: {'✅ 通过' if ok else '❌ 失败'}")

    if ok:
        logger.success("nodriver 可以绕过 Cloudflare!")

    return 0 if ok else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
