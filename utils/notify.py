#!/usr/bin/env python3
"""
统一通知管理模块

支持多种推送渠道的统一通知管理器。

Requirements:
- 4.1: 支持 Email, Gotify, Server酱³, wxpush, Telegram, PushPlus, 钉钉, 飞书, 企业微信, Bark
- 4.2: 发送通知时尝试所有配置的渠道并记录结果
- 4.3: 如果某个渠道失败，记录错误并继续其他渠道
- 4.4: 统一消息格式，包含平台名称、状态和时间戳
- 4.5: AnyRouter 余额变化时包含余额信息
- 4.6: 支持文本和 HTML 消息格式
"""

import os
import re
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Literal, Optional

import httpx
from loguru import logger


class NotificationManager:
    """统一通知管理器
    
    支持 11 种通知渠道:
    - Email: 邮件推送
    - Gotify: 自托管推送服务
    - Server酱³: 微信推送服务 (新版)
    - wxpush: 微信推送服务
    - Telegram: Telegram Bot 推送
    - PushPlus: 微信推送服务
    - Server酱: 微信推送服务 (旧版)
    - 钉钉: 钉钉机器人
    - 飞书: 飞书机器人
    - 企业微信: 企业微信机器人
    - Bark: iOS 推送服务
    """
    
    def __init__(self):
        """初始化通知管理器，从环境变量加载所有渠道配置"""
        # Email 配置
        self.email_user = os.getenv("EMAIL_USER")
        self.email_pass = os.getenv("EMAIL_PASS")
        self.email_to = os.getenv("EMAIL_TO")
        self.email_sender = os.getenv("EMAIL_SENDER")
        self.smtp_server = os.getenv("CUSTOM_SMTP_SERVER")
        
        # Gotify 配置
        self.gotify_url = os.getenv("GOTIFY_URL")
        self.gotify_token = os.getenv("GOTIFY_TOKEN")
        gotify_priority_str = os.getenv("GOTIFY_PRIORITY") or "9"
        self.gotify_priority = int(gotify_priority_str) if gotify_priority_str else 9
        
        # Server酱³ 配置
        self.sc3_push_key = os.getenv("SC3_PUSH_KEY")
        
        # wxpush 配置
        self.wxpush_url = os.getenv("WXPUSH_URL")
        self.wxpush_token = os.getenv("WXPUSH_TOKEN")
        
        # Telegram 配置
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_USERID")
        
        # PushPlus 配置
        self.pushplus_token = os.getenv("PUSHPLUS_TOKEN")
        
        # Server酱 (旧版) 配置
        self.server_push_key = os.getenv("SERVERPUSHKEY")
        
        # 钉钉配置
        self.dingding_webhook = os.getenv("DINGDING_WEBHOOK")
        
        # 飞书配置
        self.feishu_webhook = os.getenv("FEISHU_WEBHOOK")
        
        # 企业微信配置
        self.weixin_webhook = os.getenv("WEIXIN_WEBHOOK")
        
        # Bark 配置
        self.bark_key = os.getenv("BARK_KEY")
        self.bark_server = os.getenv("BARK_SERVER", "https://api.day.app")
        
        # HTTP 客户端
        self._client: Optional[httpx.Client] = None
    
    @property
    def client(self) -> httpx.Client:
        """获取 HTTP 客户端（懒加载）"""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client
    
    def close(self):
        """关闭 HTTP 客户端"""
        if self._client is not None:
            self._client.close()
            self._client = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    def push_message(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ) -> dict[str, bool]:
        """发送通知到所有配置的渠道
        
        Args:
            title: 通知标题
            content: 通知内容
            msg_type: 消息类型，"text" 或 "html"
        
        Returns:
            dict: 各渠道发送结果，key 为渠道名称，value 为是否成功
        """
        channels = [
            ("Email", self._send_email),
            ("Gotify", self._send_gotify),
            ("Server酱³", self._send_sc3),
            ("wxpush", self._send_wxpush),
            ("Telegram", self._send_telegram),
            ("PushPlus", self._send_pushplus),
            ("Server酱", self._send_server_push),
            ("钉钉", self._send_dingtalk),
            ("飞书", self._send_feishu),
            ("企业微信", self._send_wecom),
            ("Bark", self._send_bark),
        ]
        
        results: dict[str, bool] = {}
        
        for name, func in channels:
            try:
                func(title, content, msg_type)
                logger.success(f"[{name}] 推送成功")
                results[name] = True
            except ValueError:
                # 未配置该渠道，跳过（不记录到结果中）
                pass
            except Exception as e:
                logger.error(f"[{name}] 推送失败: {e}")
                results[name] = False
        
        return results
    
    def _send_email(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送邮件通知
        
        环境变量:
        - EMAIL_USER: 发件邮箱账号
        - EMAIL_PASS: 发件邮箱密码/授权码
        - EMAIL_TO: 收件邮箱地址
        - EMAIL_SENDER: 发件人显示名称（可选）
        - CUSTOM_SMTP_SERVER: 自定义 SMTP 服务器（可选）
        """
        if not self.email_user or not self.email_pass or not self.email_to:
            raise ValueError("Email 配置不完整")
        
        sender = self.email_sender or self.email_user
        
        # 创建邮件
        if msg_type == "html":
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(content, "html", "utf-8"))
        else:
            msg = MIMEText(content, "plain", "utf-8")
        
        msg["From"] = f"{sender} <{self.email_user}>"
        msg["To"] = self.email_to
        msg["Subject"] = title
        
        # 确定 SMTP 服务器
        smtp_server = self.smtp_server
        if not smtp_server:
            domain = self.email_user.split("@")[1]
            smtp_server = f"smtp.{domain}"
        
        # 发送邮件
        with smtplib.SMTP_SSL(smtp_server, 465) as server:
            server.login(self.email_user, self.email_pass)
            server.send_message(msg)
    
    def _send_gotify(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送 Gotify 通知
        
        环境变量:
        - GOTIFY_URL: Gotify 服务器地址
        - GOTIFY_TOKEN: Gotify 应用的 API Token
        - GOTIFY_PRIORITY: 消息优先级（可选，默认 9）
        """
        if not self.gotify_url or not self.gotify_token:
            raise ValueError("Gotify 配置不完整")
        
        url = f"{self.gotify_url.rstrip('/')}/message"
        
        # Gotify 支持 markdown 格式
        extras = {}
        if msg_type == "html":
            extras = {"client::display": {"contentType": "text/html"}}
        
        payload = {
            "title": title,
            "message": content,
            "priority": self.gotify_priority,
        }
        if extras:
            payload["extras"] = extras
        
        response = self.client.post(
            url,
            params={"token": self.gotify_token},
            json=payload,
        )
        response.raise_for_status()
    
    def _send_sc3(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送 Server酱³ 通知
        
        环境变量:
        - SC3_PUSH_KEY: Server酱³ SendKey (格式: sct{uid}t...)
        """
        if not self.sc3_push_key:
            raise ValueError("Server酱³ 配置不完整")
        
        # 从 SendKey 中提取 UID
        match = re.match(r"sct(\d+)t", self.sc3_push_key, re.I)
        if not match:
            raise ValueError("SC3_PUSH_KEY 格式错误，无法提取 UID")
        
        uid = match.group(1)
        url = f"https://{uid}.push.ft07.com/send/{self.sc3_push_key}"
        
        params = {
            "title": title,
            "desp": content,
        }
        
        response = self.client.get(url, params=params)
        response.raise_for_status()
    
    def _send_wxpush(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送 wxpush 通知
        
        环境变量:
        - WXPUSH_URL: wxpush 服务器地址
        - WXPUSH_TOKEN: wxpush 的 token
        """
        if not self.wxpush_url or not self.wxpush_token:
            raise ValueError("wxpush 配置不完整")
        
        url = f"{self.wxpush_url.rstrip('/')}/wxsend"
        
        response = self.client.post(
            url,
            headers={
                "Authorization": self.wxpush_token,
                "Content-Type": "application/json",
            },
            json={
                "title": title,
                "content": content,
            },
        )
        response.raise_for_status()
    
    def _send_telegram(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送 Telegram 通知
        
        环境变量:
        - TELEGRAM_BOT_TOKEN 或 TELEGRAM_TOKEN: Telegram Bot Token
        - TELEGRAM_CHAT_ID 或 TELEGRAM_USERID: 目标 Chat ID
        """
        if not self.telegram_bot_token or not self.telegram_chat_id:
            raise ValueError("Telegram 配置不完整")
        
        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        
        # 组合标题和内容
        text = f"*{title}*\n\n{content}" if msg_type == "text" else f"<b>{title}</b>\n\n{content}"
        
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML" if msg_type == "html" else "Markdown",
        }
        
        response = self.client.post(url, json=payload)
        response.raise_for_status()
    
    def _send_pushplus(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送 PushPlus 通知
        
        环境变量:
        - PUSHPLUS_TOKEN: PushPlus Token
        """
        if not self.pushplus_token:
            raise ValueError("PushPlus 配置不完整")
        
        url = "https://www.pushplus.plus/send"
        
        payload = {
            "token": self.pushplus_token,
            "title": title,
            "content": content,
            "template": "html" if msg_type == "html" else "txt",
        }
        
        response = self.client.post(url, json=payload)
        response.raise_for_status()
    
    def _send_server_push(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送 Server酱 (旧版) 通知
        
        环境变量:
        - SERVERPUSHKEY: Server酱 SCKEY
        """
        if not self.server_push_key:
            raise ValueError("Server酱 配置不完整")
        
        url = f"https://sctapi.ftqq.com/{self.server_push_key}.send"
        
        payload = {
            "title": title,
            "desp": content,
        }
        
        response = self.client.post(url, data=payload)
        response.raise_for_status()
    
    def _send_dingtalk(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送钉钉机器人通知
        
        环境变量:
        - DINGDING_WEBHOOK: 钉钉机器人 Webhook URL
        """
        if not self.dingding_webhook:
            raise ValueError("钉钉 配置不完整")
        
        # 钉钉支持 markdown 格式
        if msg_type == "html":
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "title": title,
                    "text": f"## {title}\n\n{content}",
                },
            }
        else:
            payload = {
                "msgtype": "text",
                "text": {
                    "content": f"{title}\n\n{content}",
                },
            }
        
        response = self.client.post(self.dingding_webhook, json=payload)
        response.raise_for_status()
    
    def _send_feishu(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送飞书机器人通知
        
        环境变量:
        - FEISHU_WEBHOOK: 飞书机器人 Webhook URL
        """
        if not self.feishu_webhook:
            raise ValueError("飞书 配置不完整")
        
        # 飞书支持富文本格式
        if msg_type == "html":
            payload = {
                "msg_type": "post",
                "content": {
                    "post": {
                        "zh_cn": {
                            "title": title,
                            "content": [[{"tag": "text", "text": content}]],
                        }
                    }
                },
            }
        else:
            payload = {
                "msg_type": "text",
                "content": {
                    "text": f"{title}\n\n{content}",
                },
            }
        
        response = self.client.post(self.feishu_webhook, json=payload)
        response.raise_for_status()
    
    def _send_wecom(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送企业微信机器人通知
        
        环境变量:
        - WEIXIN_WEBHOOK: 企业微信机器人 Webhook URL
        """
        if not self.weixin_webhook:
            raise ValueError("企业微信 配置不完整")
        
        # 企业微信支持 markdown 格式
        if msg_type == "html":
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": f"## {title}\n\n{content}",
                },
            }
        else:
            payload = {
                "msgtype": "text",
                "text": {
                    "content": f"{title}\n\n{content}",
                },
            }
        
        response = self.client.post(self.weixin_webhook, json=payload)
        response.raise_for_status()
    
    def _send_bark(
        self,
        title: str,
        content: str,
        msg_type: Literal["text", "html"] = "text"
    ):
        """发送 Bark 通知 (iOS)
        
        环境变量:
        - BARK_KEY: Bark 推送 Key
        - BARK_SERVER: Bark 服务器地址（可选，默认 https://api.day.app）
        """
        if not self.bark_key:
            raise ValueError("Bark 配置不完整")
        
        server = self.bark_server.rstrip("/")
        url = f"{server}/{self.bark_key}"
        
        payload = {
            "title": title,
            "body": content,
        }
        
        # Bark 支持 HTML 格式（通过 isArchive 参数）
        if msg_type == "html":
            payload["isArchive"] = 1
        
        response = self.client.post(url, json=payload)
        response.raise_for_status()
    
    @staticmethod
    def format_checkin_message(
        platform: str,
        account: str,
        status: str,
        message: str,
        details: Optional[dict] = None,
        timestamp: Optional[datetime] = None
    ) -> tuple[str, str]:
        """格式化签到结果消息
        
        Args:
            platform: 平台名称
            account: 账号标识
            status: 签到状态 (success/failed/skipped)
            message: 状态消息
            details: 额外信息（如余额）
            timestamp: 时间戳
        
        Returns:
            tuple: (标题, 内容)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # 状态图标
        status_icons = {
            "success": "✅",
            "failed": "❌",
            "skipped": "⏭️",
        }
        icon = status_icons.get(status, "ℹ️")
        
        # 标题
        title = f"{icon} {platform} 签到结果"
        
        # 内容
        lines = [
            f"平台: {platform}",
            f"账号: {account}",
            f"状态: {status}",
            f"消息: {message}",
            f"时间: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        
        # 添加余额信息（如果有）
        if details:
            if "balance" in details:
                lines.append(f"余额: {details['balance']}")
            if "balance_change" in details:
                change = details["balance_change"]
                change_str = f"+{change}" if change > 0 else str(change)
                lines.append(f"余额变化: {change_str}")
            # 添加其他详情
            for key, value in details.items():
                if key not in ("balance", "balance_change"):
                    lines.append(f"{key}: {value}")
        
        content = "\n".join(lines)
        
        return title, content
    
    @staticmethod
    def format_summary_message(
        results: list[dict],
        timestamp: Optional[datetime] = None
    ) -> tuple[str, str]:
        """格式化签到汇总消息
        
        Args:
            results: 签到结果列表，每个元素包含 platform, account, status, message, details
            timestamp: 时间戳
        
        Returns:
            tuple: (标题, 内容)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        success_count = sum(1 for r in results if r.get("status") == "success")
        failed_count = sum(1 for r in results if r.get("status") == "failed")
        total_count = len(results)
        
        # 标题
        if failed_count == 0:
            title = f"✅ 多平台签到完成 ({success_count}/{total_count})"
        else:
            title = f"⚠️ 多平台签到完成 ({success_count}/{total_count})"
        
        # 内容
        lines = [
            f"签到时间: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"成功: {success_count} | 失败: {failed_count} | 总计: {total_count}",
            "",
            "--- 详细结果 ---",
        ]
        
        for result in results:
            status = result.get("status", "unknown")
            icon = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(status, "ℹ️")
            platform = result.get("platform", "Unknown")
            account = result.get("account", "Unknown")
            message = result.get("message", "")
            
            lines.append(f"{icon} [{platform}] {account}: {message}")
            
            # 添加余额信息
            details = result.get("details", {})
            if details and "balance" in details:
                lines.append(f"   余额: {details['balance']}")
        
        content = "\n".join(lines)
        
        return title, content


# 便捷函数
def get_notification_manager() -> NotificationManager:
    """获取通知管理器实例"""
    return NotificationManager()


def push_message(
    title: str,
    content: str,
    msg_type: Literal["text", "html"] = "text"
) -> dict[str, bool]:
    """发送通知到所有配置的渠道（便捷函数）
    
    Args:
        title: 通知标题
        content: 通知内容
        msg_type: 消息类型，"text" 或 "html"
    
    Returns:
        dict: 各渠道发送结果
    """
    with NotificationManager() as manager:
        return manager.push_message(title, content, msg_type)
