"""
平台适配器模块

提供多平台签到支持的适配器实现。
"""

from platforms.base import BasePlatformAdapter, CheckinResult, CheckinStatus
from platforms.anyrouter import AnyRouterAdapter
from platforms.duckcoding import DuckCodingAdapter
from platforms.elysiver import ElysiverAdapter
from platforms.kfcapi import KFCAPIAdapter
from platforms.linuxdo import LinuxDOAdapter
from platforms.neb import NEBAdapter
from platforms.runanytime import RunAnytimeAdapter
from platforms.wong import WongAdapter
from platforms.manager import PlatformManager

__all__ = [
    "BasePlatformAdapter",
    "CheckinResult",
    "CheckinStatus",
    "AnyRouterAdapter",
    "DuckCodingAdapter",
    "ElysiverAdapter",
    "KFCAPIAdapter",
    "LinuxDOAdapter",
    "NEBAdapter",
    "RunAnytimeAdapter",
    "WongAdapter",
    "PlatformManager",
]
