#!/usr/bin/env python3
"""
平台管理器

协调所有平台的签到任务，汇总结果并发送通知。

Requirements:
- 6.2: 支持运行所有平台签到
- 6.3: 支持运行指定平台签到
- 6.4: 发送汇总通知
"""

import asyncio
from typing import Optional

from loguru import logger

from platforms.anyrouter import AnyRouterAdapter
from platforms.base import CheckinResult, CheckinStatus
from platforms.linuxdo import LinuxDoAdapter
from utils.config import AppConfig
from utils.notify import NotificationManager


class PlatformManager:
    """平台管理器
    
    协调所有签到任务，支持按平台筛选和汇总通知。
    """
    
    def __init__(self, config: AppConfig):
        """初始化平台管理器
        
        Args:
            config: 应用配置
        """
        self.config = config
        self.notify = NotificationManager()
        self.results: list[CheckinResult] = []
    
    async def run_all(self) -> list[CheckinResult]:
        """运行所有平台签到
        
        Returns:
            list[CheckinResult]: 所有签到结果
        """
        self.results = []
        
        # LinuxDo (多账号)
        linuxdo_results = await self._run_all_linuxdo()
        self.results.extend(linuxdo_results)
        
        # AnyRouter
        anyrouter_results = await self._run_all_anyrouter()
        self.results.extend(anyrouter_results)
        
        return self.results
    
    async def run_platform(self, platform: str) -> list[CheckinResult]:
        """运行指定平台签到
        
        Args:
            platform: 平台名称 ("linuxdo" 或 "anyrouter")
        
        Returns:
            list[CheckinResult]: 签到结果
        
        Raises:
            ValueError: 未知平台名称
        """
        self.results = []
        
        platform_lower = platform.lower()
        
        if platform_lower == "linuxdo":
            linuxdo_results = await self._run_all_linuxdo()
            self.results.extend(linuxdo_results)
        elif platform_lower == "anyrouter":
            anyrouter_results = await self._run_all_anyrouter()
            self.results.extend(anyrouter_results)
        else:
            raise ValueError(f"未知平台: {platform}")
        
        return self.results
    
    async def _run_all_linuxdo(self) -> list[CheckinResult]:
        """运行所有 LinuxDo 账号签到（并发执行，最多同时 3 个）"""
        if not self.config.linuxdo_accounts:
            logger.warning("LinuxDo 未配置")
            return []
        
        # 并发限制：最多同时 3 个账号
        semaphore = asyncio.Semaphore(3)
        
        async def run_with_semaphore(account, index: int) -> CheckinResult:
            async with semaphore:
                logger.info(f"开始执行 LinuxDo 账号 {index + 1}: {account.get_display_name(index)}")
                adapter = LinuxDoAdapter(
                    username=account.username,
                    password=account.password,
                    browse_enabled=account.browse_enabled,
                    account_name=account.get_display_name(index),
                )
                return await adapter.run()
        
        # 并发执行所有账号
        tasks = [
            run_with_semaphore(account, i)
            for i, account in enumerate(self.config.linuxdo_accounts)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 处理异常结果
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"LinuxDo 账号 {i + 1} 执行异常: {result}")
                final_results.append(CheckinResult(
                    platform="LinuxDo",
                    account=self.config.linuxdo_accounts[i].get_display_name(i),
                    status=CheckinStatus.FAILED,
                    message=f"执行异常: {str(result)}",
                ))
            else:
                final_results.append(result)
        
        return final_results
    
    async def _run_linuxdo(self) -> CheckinResult:
        """运行 LinuxDo 签到（向后兼容，运行第一个账号）"""
        results = await self._run_all_linuxdo()
        if results:
            return results[0]
        return CheckinResult(
            platform="LinuxDo",
            account="N/A",
            status=CheckinStatus.SKIPPED,
            message="未配置 LinuxDo 账号",
        )
    
    async def _run_all_anyrouter(self) -> list[CheckinResult]:
        """运行所有 AnyRouter 账号签到"""
        results = []
        
        for i, account in enumerate(self.config.anyrouter_accounts):
            provider = self.config.providers.get(account.provider)
            if not provider:
                logger.warning(f"Provider '{account.provider}' 未找到，跳过账号 {i + 1}")
                results.append(CheckinResult(
                    platform=f"AnyRouter ({account.provider})",
                    account=account.get_display_name(i),
                    status=CheckinStatus.SKIPPED,
                    message=f"Provider '{account.provider}' 未配置",
                ))
                continue
            
            adapter = AnyRouterAdapter(
                account=account,
                provider_config=provider,
                account_index=i,
            )
            
            result = await adapter.run()
            results.append(result)
        
        return results
    
    def send_summary_notification(self, force: bool = False) -> None:
        """发送签到汇总通知
        
        Args:
            force: 是否强制发送（即使全部成功）
        """
        if not self.results:
            logger.info("没有签到结果，跳过通知")
            return
        
        # 格式化通知内容
        results_dicts = [r.to_dict() for r in self.results]
        title, text_content, html_content = NotificationManager.format_summary_message(results_dicts)
        
        # 发送通知（使用 HTML 格式）
        with self.notify:
            self.notify.push_message(title, html_content, msg_type="html")
    
    def _check_balance_change(self) -> bool:
        """检查是否有余额变化
        
        TODO: 实现余额变化检测逻辑（需要持久化上次余额）
        """
        # 暂时返回 False，后续可以实现余额变化检测
        return False
    
    def get_exit_code(self) -> int:
        """获取退出码
        
        Returns:
            int: 0 表示至少有一个成功，1 表示全部失败或无配置
        """
        if not self.results:
            return 1
        
        success_count = sum(1 for r in self.results if r.is_success)
        return 0 if success_count > 0 else 1
    
    @property
    def success_count(self) -> int:
        """成功数量"""
        return sum(1 for r in self.results if r.is_success)
    
    @property
    def failed_count(self) -> int:
        """失败数量"""
        return sum(1 for r in self.results if r.status == CheckinStatus.FAILED)
    
    @property
    def skipped_count(self) -> int:
        """跳过数量"""
        return sum(1 for r in self.results if r.status == CheckinStatus.SKIPPED)
    
    @property
    def total_count(self) -> int:
        """总数量"""
        return len(self.results)
