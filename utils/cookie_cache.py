#!/usr/bin/env python3
"""
NewAPI Cookie 缓存模块

OAuth 登录成功后自动缓存 Cookie（session + api_user），
下次签到时优先使用缓存的 Cookie+API 方式（速度快），
Cookie 过期时自动回退到 OAuth 重新获取并刷新缓存。

缓存目录: .newapi_cookies/
缓存格式: JSON 文件，每个 provider+account 一个文件
"""

import json
import time
from pathlib import Path

from loguru import logger

DEFAULT_CACHE_DIR = ".newapi_cookies"
DEFAULT_EXPIRY_DAYS = 30  # 默认 30 天过期


class CookieCache:
    """NewAPI Cookie 缓存管理器"""

    def __init__(self, cache_dir: str = DEFAULT_CACHE_DIR, expiry_days: int = DEFAULT_EXPIRY_DAYS):
        self.cache_dir = Path(cache_dir)
        self.expiry_days = expiry_days
        self.cache_dir.mkdir(exist_ok=True)

    def _sanitize_key(self, provider: str, account_name: str) -> str:
        """生成安全的缓存文件名"""
        raw = f"{provider}_{account_name}"
        return "".join(c if c.isalnum() or c in "-_." else "_" for c in raw)

    def _get_cache_path(self, provider: str, account_name: str) -> Path:
        """获取缓存文件路径"""
        return self.cache_dir / f"{self._sanitize_key(provider, account_name)}.json"

    def get(self, provider: str, account_name: str) -> dict | None:
        """获取缓存的 Cookie

        Returns:
            dict with keys: session, api_user, provider, account_name, cached_at
            None if not found or expired
        """
        path = self._get_cache_path(provider, account_name)
        if not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            # 检查是否过期
            cached_at = data.get("cached_at", 0)
            age_days = (time.time() - cached_at) / 86400

            if age_days > self.expiry_days:
                logger.info(
                    f"[CookieCache] 缓存已过期({age_days:.1f}天 > {self.expiry_days}天): "
                    f"{provider}/{account_name}"
                )
                path.unlink(missing_ok=True)
                return None

            # 验证必要字段
            if not data.get("session") or not data.get("api_user"):
                logger.debug(f"[CookieCache] 缓存数据不完整，已清除: {provider}/{account_name}")
                path.unlink(missing_ok=True)
                return None

            logger.debug(
                f"[CookieCache] 命中缓存({age_days:.1f}天): {provider}/{account_name}"
            )
            return data

        except Exception as e:
            logger.debug(f"[CookieCache] 读取缓存失败: {e}")
            path.unlink(missing_ok=True)
            return None

    def save(self, provider: str, account_name: str, session: str, api_user: str) -> None:
        """保存 Cookie 到缓存"""
        path = self._get_cache_path(provider, account_name)
        data = {
            "session": session,
            "api_user": api_user,
            "provider": provider,
            "account_name": account_name,
            "cached_at": time.time(),
        }
        try:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"[CookieCache] Cookie已缓存: {provider}/{account_name}")
        except Exception as e:
            logger.warning(f"[CookieCache] 保存缓存失败: {e}")

    def invalidate(self, provider: str, account_name: str) -> None:
        """清除指定账户的缓存（Cookie 过期时调用）"""
        path = self._get_cache_path(provider, account_name)
        if path.exists():
            path.unlink(missing_ok=True)
            logger.info(f"[CookieCache] 已清除缓存: {provider}/{account_name}")
