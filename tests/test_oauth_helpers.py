#!/usr/bin/env python3
"""
OAuth 辅助工具模块的单元测试

测试 URL 分类功能的正确性。
"""


from utils.oauth_helpers import (
    OAuthURLType,
    classify_oauth_url,
    is_authorization_url,
    is_linuxdo_login_url,
    is_oauth_complete_url,
    is_oauth_related_url,
)


class TestClassifyOAuthURL:
    """测试 classify_oauth_url 函数"""

    # ========== LinuxDO 登录页面测试 ==========

    def test_linuxdo_login_basic(self):
        """测试基本的 LinuxDO 登录 URL（不包含 authorize）"""
        # connect.linux.do/oauth/authorize 应该被分类为 AUTHORIZATION
        # 因为 authorize 优先级更高
        url = "https://connect.linux.do/oauth/authorize"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.AUTHORIZATION

    def test_linuxdo_login_with_path(self):
        """测试带路径的 LinuxDO URL"""
        url = "https://linux.do/session/sso_login"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.LINUXDO_LOGIN

    def test_linuxdo_login_subdomain(self):
        """测试 LinuxDO 子域名"""
        url = "https://connect.linux.do/oauth/callback"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.LINUXDO_LOGIN

    def test_linuxdo_login_case_insensitive(self):
        """测试大小写不敏感"""
        url = "https://LINUX.DO/login"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.LINUXDO_LOGIN

    def test_linuxdo_takes_priority_over_authorize(self):
        """测试 authorize 优先级高于 linux.do"""
        # 当 URL 同时包含 linux.do 和 authorize 时，应该返回 AUTHORIZATION
        # 因为 authorize 表示授权确认页面，需要点击"允许"按钮
        url = "https://connect.linux.do/oauth/authorize?client_id=xxx"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.AUTHORIZATION

    # ========== 授权页面测试 ==========

    def test_authorization_basic(self):
        """测试基本的授权页面 URL"""
        url = "https://example.com/oauth/authorize"
        result = classify_oauth_url(url, "other.com")
        assert result == OAuthURLType.AUTHORIZATION

    def test_authorization_with_params(self):
        """测试带参数的授权 URL"""
        url = "https://api.example.com/authorize?client_id=123&redirect_uri=xxx"
        result = classify_oauth_url(url, "other.com")
        assert result == OAuthURLType.AUTHORIZATION

    def test_authorization_case_insensitive(self):
        """测试授权 URL 大小写不敏感"""
        url = "https://example.com/AUTHORIZE"
        result = classify_oauth_url(url, "other.com")
        assert result == OAuthURLType.AUTHORIZATION

    # ========== OAuth 完成测试 ==========

    def test_oauth_complete_basic(self):
        """测试基本的 OAuth 完成 URL"""
        url = "https://example.com/dashboard"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.OAUTH_COMPLETE

    def test_oauth_complete_with_path(self):
        """测试带路径的 OAuth 完成 URL"""
        url = "https://example.com/user/profile"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.OAUTH_COMPLETE

    def test_oauth_complete_subdomain(self):
        """测试子域名的 OAuth 完成"""
        url = "https://api.example.com/callback"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.OAUTH_COMPLETE

    def test_oauth_not_complete_with_login(self):
        """测试包含 login 的 URL 不算完成"""
        url = "https://example.com/login"
        result = classify_oauth_url(url, "example.com")
        # 包含 login 不算 OAuth 完成
        assert result == OAuthURLType.OTHER

    def test_oauth_not_complete_with_login_path(self):
        """测试 login 在路径中的情况"""
        url = "https://example.com/user/login/oauth"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.OTHER

    # ========== OTHER 类型测试 ==========

    def test_other_unrelated_url(self):
        """测试无关的 URL"""
        url = "https://google.com/search"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.OTHER

    def test_other_about_blank(self):
        """测试 about:blank"""
        url = "about:blank"
        result = classify_oauth_url(url, "example.com")
        assert result == OAuthURLType.OTHER

    # ========== 边界情况测试 ==========

    def test_empty_url(self):
        """测试空 URL"""
        result = classify_oauth_url("", "example.com")
        assert result == OAuthURLType.OTHER

    def test_none_url(self):
        """测试 None URL"""
        result = classify_oauth_url(None, "example.com")
        assert result == OAuthURLType.OTHER

    def test_empty_target_domain(self):
        """测试空目标域名"""
        url = "https://example.com/dashboard"
        result = classify_oauth_url(url, "")
        # 空目标域名时，无法判断 OAuth 完成
        assert result == OAuthURLType.OTHER

    def test_none_target_domain(self):
        """测试 None 目标域名"""
        url = "https://example.com/dashboard"
        result = classify_oauth_url(url, None)
        assert result == OAuthURLType.OTHER

    def test_whitespace_url(self):
        """测试空白 URL"""
        result = classify_oauth_url("   ", "example.com")
        assert result == OAuthURLType.OTHER

    def test_malformed_url(self):
        """测试格式错误的 URL"""
        result = classify_oauth_url("not-a-valid-url", "example.com")
        assert result == OAuthURLType.OTHER

    def test_target_domain_with_whitespace(self):
        """测试带空白的目标域名"""
        url = "https://example.com/dashboard"
        result = classify_oauth_url(url, "  example.com  ")
        assert result == OAuthURLType.OAUTH_COMPLETE


class TestIsLinuxdoLoginURL:
    """测试 is_linuxdo_login_url 函数"""

    def test_true_for_linuxdo_url(self):
        """测试 LinuxDO URL 返回 True"""
        assert is_linuxdo_login_url("https://linux.do/login") is True

    def test_false_for_other_url(self):
        """测试其他 URL 返回 False"""
        assert is_linuxdo_login_url("https://example.com/login") is False

    def test_false_for_empty_url(self):
        """测试空 URL 返回 False"""
        assert is_linuxdo_login_url("") is False


class TestIsAuthorizationURL:
    """测试 is_authorization_url 函数"""

    def test_true_for_authorize_url(self):
        """测试授权 URL 返回 True"""
        assert is_authorization_url("https://example.com/authorize") is True

    def test_false_for_linuxdo_authorize(self):
        """测试 LinuxDO 授权 URL 返回 False（LinuxDO 优先）"""
        assert is_authorization_url("https://linux.do/authorize") is False

    def test_false_for_other_url(self):
        """测试其他 URL 返回 False"""
        assert is_authorization_url("https://example.com/dashboard") is False

    def test_false_for_empty_url(self):
        """测试空 URL 返回 False"""
        assert is_authorization_url("") is False

    def test_false_for_none_url(self):
        """测试 None URL 返回 False"""
        assert is_authorization_url(None) is False


class TestIsOAuthCompleteURL:
    """测试 is_oauth_complete_url 函数"""

    def test_true_for_complete_url(self):
        """测试完成 URL 返回 True"""
        assert is_oauth_complete_url("https://example.com/dashboard", "example.com") is True

    def test_false_for_login_url(self):
        """测试登录 URL 返回 False"""
        assert is_oauth_complete_url("https://example.com/login", "example.com") is False

    def test_false_for_different_domain(self):
        """测试不同域名返回 False"""
        assert is_oauth_complete_url("https://other.com/dashboard", "example.com") is False


class TestIsOAuthRelatedURL:
    """测试 is_oauth_related_url 函数"""

    def test_true_for_linuxdo(self):
        """测试 LinuxDO URL 返回 True"""
        assert is_oauth_related_url("https://linux.do/login") is True

    def test_true_for_oauth(self):
        """测试包含 oauth 的 URL 返回 True"""
        assert is_oauth_related_url("https://example.com/oauth/callback") is True

    def test_true_for_authorize(self):
        """测试包含 authorize 的 URL 返回 True"""
        assert is_oauth_related_url("https://example.com/authorize") is True

    def test_true_for_callback(self):
        """测试包含 callback 的 URL 返回 True"""
        assert is_oauth_related_url("https://example.com/callback") is True

    def test_false_for_unrelated(self):
        """测试无关 URL 返回 False"""
        assert is_oauth_related_url("https://google.com/search") is False

    def test_false_for_empty(self):
        """测试空 URL 返回 False"""
        assert is_oauth_related_url("") is False

    def test_false_for_none(self):
        """测试 None URL 返回 False"""
        assert is_oauth_related_url(None) is False
