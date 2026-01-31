#!/usr/bin/env python3
"""
WONG 公益站签到适配器

基于 NewAPIAdapter 基类，支持 LinuxDO OAuth 登录。
"""

from platforms.newapi_base import NewAPIAdapter


class WongAdapter(NewAPIAdapter):
    """WONG 公益站签到适配器
    
    继承自 NewAPIAdapter，自动支持：
    - LinuxDO OAuth 登录（优先）
    - Cookie 回退登录
    - 签到和余额查询
    """
    
    PLATFORM_NAME = "WONG公益站"
    BASE_URL = "https://wzw.pp.ua"
    COOKIE_DOMAIN = "wzw.pp.ua"
    CURRENCY_UNIT = "$"
