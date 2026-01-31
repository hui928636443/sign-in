#!/usr/bin/env python3
"""
Elysiver 签到适配器

基于 NewAPIAdapter 基类，适配 Elysiver (elysiver.h-e.top) 站点。
"""

from platforms.newapi_base import NewAPIAdapter


class ElysiverAdapter(NewAPIAdapter):
    """Elysiver 签到适配器"""
    
    PLATFORM_NAME = "Elysiver"
    BASE_URL = "https://elysiver.h-e.top"
    COOKIE_DOMAIN = "h-e.top"
    CURRENCY_UNIT = "E "
