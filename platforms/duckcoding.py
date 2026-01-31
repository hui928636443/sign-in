#!/usr/bin/env python3
"""
Free DuckCoding 签到适配器

基于 NewAPIAdapter 基类，适配 Free DuckCoding (free.duckcoding.com) 站点。
"""

from platforms.newapi_base import NewAPIAdapter


class DuckCodingAdapter(NewAPIAdapter):
    """Free DuckCoding 签到适配器"""
    
    PLATFORM_NAME = "Free DuckCoding"
    BASE_URL = "https://free.duckcoding.com"
    COOKIE_DOMAIN = "free.duckcoding.com"
    CURRENCY_UNIT = "¥"
