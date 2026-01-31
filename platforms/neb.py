#!/usr/bin/env python3
"""
NEB公益站 (Simonzhu) 签到适配器

基于 NewAPIAdapter 基类，适配 NEB公益站 (ai.zzhdsgsss.xyz) 站点。
"""

from platforms.newapi_base import NewAPIAdapter


class NEBAdapter(NewAPIAdapter):
    """NEB公益站签到适配器"""
    
    PLATFORM_NAME = "NEB公益站"
    BASE_URL = "https://ai.zzhdsgsss.xyz"
    COOKIE_DOMAIN = "ai.zzhdsgsss.xyz"
    CURRENCY_UNIT = "$"
