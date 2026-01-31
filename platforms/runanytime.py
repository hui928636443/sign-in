#!/usr/bin/env python3
"""
随时跑路公益站签到适配器

基于 NewAPIAdapter 基类，适配随时跑路 (runanytime.hxi.me) 站点。
"""

from platforms.newapi_base import NewAPIAdapter


class RunAnytimeAdapter(NewAPIAdapter):
    """随时跑路公益站签到适配器"""
    
    PLATFORM_NAME = "随时跑路"
    BASE_URL = "https://runanytime.hxi.me"
    COOKIE_DOMAIN = "runanytime.hxi.me"
    CURRENCY_UNIT = "$"
