#!/usr/bin/env python3
"""
NewAPI 站点适配器集合

基于 NewAPIAdapter 基类，为所有 LinuxDO OAuth 站点创建适配器。
"""

from platforms.newapi_base import NewAPIAdapter


class ZeroLiyaAdapter(NewAPIAdapter):
    """小呆公益站签到适配器"""
    PLATFORM_NAME = "小呆公益站"
    BASE_URL = "https://new.184772.xyz"
    COOKIE_DOMAIN = "new.184772.xyz"
    CURRENCY_UNIT = "$"


class MitchllAdapter(NewAPIAdapter):
    """Mitchll-api公益站签到适配器"""
    PLATFORM_NAME = "Mitchll-api公益站"
    BASE_URL = "https://api.mitchll.com"
    COOKIE_DOMAIN = "api.mitchll.com"
    CURRENCY_UNIT = "$"


class KingoAdapter(NewAPIAdapter):
    """Kingo API公益站签到适配器"""
    PLATFORM_NAME = "Kingo API公益站"
    BASE_URL = "https://new-api-bxhm.onrender.com"
    COOKIE_DOMAIN = "new-api-bxhm.onrender.com"
    CURRENCY_UNIT = "$"


class TechStarAdapter(NewAPIAdapter):
    """TechnologyStar签到适配器"""
    PLATFORM_NAME = "TechnologyStar"
    BASE_URL = "https://aidrouter.qzz.io"
    COOKIE_DOMAIN = "aidrouter.qzz.io"
    CURRENCY_UNIT = "$"


class LightLLMAdapter(NewAPIAdapter):
    """轻のLLM签到适配器"""
    PLATFORM_NAME = "轻のLLM"
    BASE_URL = "https://lightllm.online"
    COOKIE_DOMAIN = "lightllm.online"
    CURRENCY_UNIT = "$"


class HotaruAdapter(NewAPIAdapter):
    """Hotaru API签到适配器"""
    PLATFORM_NAME = "Hotaru API"
    BASE_URL = "https://api.hotaruapi.top"
    COOKIE_DOMAIN = "api.hotaruapi.top"
    CURRENCY_UNIT = "$"


class DEV88Adapter(NewAPIAdapter):
    """DEV88公益站签到适配器"""
    PLATFORM_NAME = "DEV88公益站"
    BASE_URL = "https://api.dev88.tech"
    COOKIE_DOMAIN = "api.dev88.tech"
    CURRENCY_UNIT = "$"


class HuanAdapter(NewAPIAdapter):
    """huan公益站签到适配器"""
    PLATFORM_NAME = "huan公益站"
    BASE_URL = "https://ai.huan666.de"
    COOKIE_DOMAIN = "ai.huan666.de"
    CURRENCY_UNIT = "$"
