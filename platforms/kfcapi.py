#!/usr/bin/env python3
"""
KFC API 签到适配器

基于 NewAPIAdapter 基类，适配 KFC API (kfc-api.sxxe.net) 站点。
"""

from platforms.newapi_base import NewAPIAdapter


class KFCAPIAdapter(NewAPIAdapter):
    """KFC API 签到适配器"""
    
    PLATFORM_NAME = "KFC API"
    BASE_URL = "https://kfc-api.sxxe.net"
    COOKIE_DOMAIN = "kfc-api.sxxe.net"
    CURRENCY_UNIT = "$"
