#!/usr/bin/env python3
"""
OAuth 辅助工具模块的属性测试 (Property-Based Testing)

使用 hypothesis 库进行属性测试，验证 URL 分类逻辑的正确性。

**Validates: Requirements 2.3, 2.4, 3.2, 5.1**
"""

import pytest
from hypothesis import given, strategies as st, assume, settings

from utils.oauth_helpers import (
    OAuthURLType,
    classify_oauth_url,
)


# ============================================================================
# Custom Strategies for URL Generation
# ============================================================================

# Common URL schemes
url_schemes = st.sampled_from(["http://", "https://", ""])

# Domain components
domain_parts = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
    min_size=1,
    max_size=20
).filter(lambda x: not x.startswith("-") and not x.endswith("-"))

# TLDs
tlds = st.sampled_from(["com", "org", "net", "io", "do", "dev", "co"])

# Path segments
path_segments = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=0,
    max_size=30
)

# Query parameters
query_params = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789=&_-",
    min_size=0,
    max_size=50
)


@st.composite
def random_urls(draw):
    """Generate random URL-like strings for testing."""
    scheme = draw(url_schemes)
    subdomain = draw(st.one_of(st.just(""), domain_parts.map(lambda x: x + ".")))
    domain = draw(domain_parts)
    tld = draw(tlds)
    path = draw(st.lists(path_segments, min_size=0, max_size=3).map(lambda x: "/" + "/".join(x) if x else ""))
    query = draw(query_params)
    query_str = f"?{query}" if query else ""
    
    return f"{scheme}{subdomain}{domain}.{tld}{path}{query_str}"


@st.composite
def linuxdo_urls(draw):
    """Generate URLs that contain 'linux.do'."""
    scheme = draw(url_schemes)
    subdomain = draw(st.one_of(st.just(""), st.just("connect."), st.just("www.")))
    path = draw(st.lists(path_segments, min_size=0, max_size=3).map(lambda x: "/" + "/".join(x) if x else ""))
    query = draw(query_params)
    query_str = f"?{query}" if query else ""
    
    return f"{scheme}{subdomain}linux.do{path}{query_str}"


@st.composite
def authorize_urls(draw):
    """Generate URLs that contain 'authorize' but not 'linux.do'."""
    scheme = draw(url_schemes)
    subdomain = draw(st.one_of(st.just(""), domain_parts.map(lambda x: x + ".")))
    # Ensure domain doesn't contain 'linux' or 'do' adjacent
    domain = draw(domain_parts.filter(lambda x: "linux" not in x.lower()))
    tld = draw(tlds.filter(lambda x: x != "do"))
    
    # Include 'authorize' in path
    path_before = draw(st.lists(path_segments, min_size=0, max_size=2))
    path_after = draw(st.lists(path_segments, min_size=0, max_size=2))
    path_parts = path_before + ["authorize"] + path_after
    path = "/" + "/".join(path_parts)
    
    query = draw(query_params)
    query_str = f"?{query}" if query else ""
    
    url = f"{scheme}{subdomain}{domain}.{tld}{path}{query_str}"
    # Double check it doesn't contain linux.do
    assume("linux.do" not in url.lower())
    return url


@st.composite
def target_domain_urls(draw, target_domain: str):
    """Generate URLs that contain the target domain."""
    scheme = draw(url_schemes)
    subdomain = draw(st.one_of(st.just(""), domain_parts.map(lambda x: x + ".")))
    path = draw(st.lists(path_segments, min_size=0, max_size=3).map(lambda x: "/" + "/".join(x) if x else ""))
    query = draw(query_params)
    query_str = f"?{query}" if query else ""
    
    return f"{scheme}{subdomain}{target_domain}{path}{query_str}"


# ============================================================================
# Property Tests for OAuth URL Pattern Detection
# ============================================================================

class TestOAuthURLPatternDetectionProperty:
    """
    Property 2: OAuth URL Pattern Detection
    
    *For any* URL string, the URL pattern detection logic SHALL correctly 
    classify the URL into one of the following categories:
    - LinuxDO login required: URL contains "linux.do"
    - Authorization page: URL contains "authorize"
    - OAuth complete: URL contains target domain AND does not contain "login"
    - Other: none of the above
    
    The classification must be mutually exclusive (each URL belongs to exactly 
    one category) and exhaustive (every URL is classified).
    
    **Validates: Requirements 2.3, 2.4, 3.2, 5.1**
    """

    @given(url=st.text(min_size=0, max_size=500), target_domain=st.text(min_size=0, max_size=100))
    @settings(max_examples=200)
    def test_classification_is_exhaustive(self, url: str, target_domain: str):
        """
        Property: Every URL is classified into exactly one category.
        
        **Validates: Requirements 2.3, 2.4, 3.2, 5.1**
        
        For any URL and target domain, classify_oauth_url must return
        one of the four valid OAuthURLType values.
        """
        result = classify_oauth_url(url, target_domain)
        
        # Result must be one of the valid enum values
        assert result in [
            OAuthURLType.LINUXDO_LOGIN,
            OAuthURLType.AUTHORIZATION,
            OAuthURLType.OAUTH_COMPLETE,
            OAuthURLType.OTHER,
        ], f"URL '{url}' was not classified into a valid category"

    @given(url=st.text(min_size=0, max_size=500), target_domain=st.text(min_size=0, max_size=100))
    @settings(max_examples=200)
    def test_classification_is_mutually_exclusive(self, url: str, target_domain: str):
        """
        Property: Each URL belongs to exactly one category (mutual exclusivity).
        
        **Validates: Requirements 2.3, 2.4, 3.2, 5.1**
        
        The function must return a single, deterministic result.
        Calling it multiple times with the same input must yield the same result.
        """
        result1 = classify_oauth_url(url, target_domain)
        result2 = classify_oauth_url(url, target_domain)
        
        # Same input must always produce same output (deterministic)
        assert result1 == result2, f"Classification is not deterministic for URL '{url}'"
        
        # Result must be exactly one type (enum ensures this, but verify)
        assert isinstance(result1, OAuthURLType), f"Result is not an OAuthURLType enum"

    @given(url=linuxdo_urls())
    @settings(max_examples=100)
    def test_linuxdo_urls_classified_as_linuxdo_login(self, url: str):
        """
        Property: URLs containing 'linux.do' are classified as LINUXDO_LOGIN.
        
        **Validates: Requirements 2.3**
        
        This is the highest priority rule - any URL with 'linux.do' should
        be classified as LinuxDO login, regardless of other content.
        """
        result = classify_oauth_url(url, "example.com")
        
        assert result == OAuthURLType.LINUXDO_LOGIN, (
            f"URL '{url}' contains 'linux.do' but was classified as {result}"
        )

    @given(url=authorize_urls())
    @settings(max_examples=100)
    def test_authorize_urls_classified_as_authorization(self, url: str):
        """
        Property: URLs containing 'authorize' (but not 'linux.do') are 
        classified as AUTHORIZATION.
        
        **Validates: Requirements 5.1**
        
        Authorization pages are detected by the 'authorize' keyword,
        but LinuxDO URLs take priority.
        """
        # Ensure URL doesn't contain linux.do (handled by strategy)
        assume("linux.do" not in url.lower())
        
        result = classify_oauth_url(url, "other-domain.com")
        
        assert result == OAuthURLType.AUTHORIZATION, (
            f"URL '{url}' contains 'authorize' but was classified as {result}"
        )

    @given(
        target_domain=domain_parts,
        tld=tlds,
        path=st.lists(path_segments.filter(lambda x: "login" not in x.lower()), min_size=0, max_size=3)
    )
    @settings(max_examples=100)
    def test_target_domain_without_login_classified_as_complete(
        self, target_domain: str, tld: str, path: list
    ):
        """
        Property: URLs containing target domain without 'login' are 
        classified as OAUTH_COMPLETE.
        
        **Validates: Requirements 2.4, 3.2**
        
        OAuth completion is detected when the URL contains the target domain
        and does not contain 'login'.
        """
        full_domain = f"{target_domain}.{tld}"
        path_str = "/" + "/".join(path) if path else ""
        url = f"https://{full_domain}{path_str}"
        
        # Ensure URL doesn't contain linux.do or authorize
        assume("linux.do" not in url.lower())
        assume("authorize" not in url.lower())
        assume("login" not in url.lower())
        
        result = classify_oauth_url(url, full_domain)
        
        assert result == OAuthURLType.OAUTH_COMPLETE, (
            f"URL '{url}' with target domain '{full_domain}' and no 'login' "
            f"was classified as {result} instead of OAUTH_COMPLETE"
        )

    @given(
        target_domain=domain_parts,
        tld=tlds,
    )
    @settings(max_examples=100)
    def test_target_domain_with_login_not_classified_as_complete(
        self, target_domain: str, tld: str
    ):
        """
        Property: URLs containing target domain WITH 'login' are NOT 
        classified as OAUTH_COMPLETE.
        
        **Validates: Requirements 2.4**
        
        The presence of 'login' in the URL indicates the OAuth flow
        is not yet complete.
        """
        full_domain = f"{target_domain}.{tld}"
        url = f"https://{full_domain}/login"
        
        # Ensure URL doesn't contain linux.do or authorize
        assume("linux.do" not in url.lower())
        assume("authorize" not in url.lower())
        
        result = classify_oauth_url(url, full_domain)
        
        assert result != OAuthURLType.OAUTH_COMPLETE, (
            f"URL '{url}' contains 'login' but was classified as OAUTH_COMPLETE"
        )

    @given(url=random_urls(), target_domain=st.text(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_priority_order_linuxdo_over_authorize(self, url: str, target_domain: str):
        """
        Property: LinuxDO classification takes priority over authorization.
        
        **Validates: Requirements 2.3, 5.1**
        
        If a URL contains both 'linux.do' and 'authorize', it should be
        classified as LINUXDO_LOGIN, not AUTHORIZATION.
        """
        result = classify_oauth_url(url, target_domain)
        
        url_lower = url.lower()
        
        if "linux.do" in url_lower:
            assert result == OAuthURLType.LINUXDO_LOGIN, (
                f"URL '{url}' contains 'linux.do' but was classified as {result}"
            )

    @given(url=random_urls(), target_domain=st.text(min_size=1, max_size=50))
    @settings(max_examples=200)
    def test_priority_order_authorize_over_complete(self, url: str, target_domain: str):
        """
        Property: Authorization classification takes priority over OAuth complete.
        
        **Validates: Requirements 5.1, 2.4**
        
        If a URL contains 'authorize' (and not 'linux.do'), it should be
        classified as AUTHORIZATION, even if it also contains the target domain.
        """
        result = classify_oauth_url(url, target_domain)
        
        url_lower = url.lower()
        target_lower = target_domain.lower().strip() if target_domain else ""
        
        if "linux.do" not in url_lower and "authorize" in url_lower:
            assert result == OAuthURLType.AUTHORIZATION, (
                f"URL '{url}' contains 'authorize' (no linux.do) but was classified as {result}"
            )

    @given(url=st.text(min_size=0, max_size=500))
    @settings(max_examples=100)
    def test_empty_target_domain_never_returns_complete(self, url: str):
        """
        Property: Empty target domain never results in OAUTH_COMPLETE.
        
        **Validates: Requirements 2.4**
        
        Without a valid target domain, we cannot determine if OAuth is complete.
        """
        # Test with empty string
        result_empty = classify_oauth_url(url, "")
        assert result_empty != OAuthURLType.OAUTH_COMPLETE or "linux.do" in url.lower() or "authorize" in url.lower(), (
            f"URL '{url}' with empty target domain was classified as OAUTH_COMPLETE"
        )
        
        # Test with None
        result_none = classify_oauth_url(url, None)
        assert result_none != OAuthURLType.OAUTH_COMPLETE or "linux.do" in url.lower() or "authorize" in url.lower(), (
            f"URL '{url}' with None target domain was classified as OAUTH_COMPLETE"
        )

    @given(url=st.sampled_from(["", None, "   ", "\t\n"]))
    @settings(max_examples=10)
    def test_empty_or_invalid_urls_classified_as_other(self, url):
        """
        Property: Empty or invalid URLs are classified as OTHER.
        
        **Validates: Requirements 2.3, 2.4, 3.2, 5.1**
        
        Edge case handling - empty, None, or whitespace-only URLs
        should be safely classified as OTHER.
        """
        result = classify_oauth_url(url, "example.com")
        
        assert result == OAuthURLType.OTHER, (
            f"Empty/invalid URL '{url}' was classified as {result} instead of OTHER"
        )

    @given(
        url=st.text(min_size=0, max_size=500),
        target_domain=st.text(min_size=0, max_size=100)
    )
    @settings(max_examples=200)
    def test_classification_rules_are_consistent(self, url: str, target_domain: str):
        """
        Property: Classification rules are applied consistently.
        
        **Validates: Requirements 2.3, 2.4, 3.2, 5.1**
        
        Verify that the classification follows the documented priority order:
        1. LinuxDO (highest priority)
        2. Authorization
        3. OAuth Complete
        4. Other (lowest priority)
        """
        result = classify_oauth_url(url, target_domain)
        url_lower = url.lower() if url else ""
        target_lower = target_domain.lower().strip() if target_domain else ""
        
        # Verify classification matches expected rules
        if "linux.do" in url_lower:
            expected = OAuthURLType.LINUXDO_LOGIN
        elif "authorize" in url_lower:
            expected = OAuthURLType.AUTHORIZATION
        elif target_lower and target_lower in url_lower and "login" not in url_lower:
            expected = OAuthURLType.OAUTH_COMPLETE
        else:
            expected = OAuthURLType.OTHER
        
        assert result == expected, (
            f"URL '{url}' with target '{target_domain}' was classified as {result}, "
            f"expected {expected}"
        )


# ============================================================================
# Property Tests for Retry Mechanism with Backoff
# ============================================================================


class TestRetryMechanismProperty:
    """
    Property 4: Retry Mechanism with Backoff
    
    *For any* operation that fails, the retry mechanism SHALL:
    - Attempt the operation up to max_retries times
    - Increase the delay between retries (backoff)
    - Return failure only after all retries are exhausted
    
    **Validates: Requirements 4.5**
    """

    @given(
        max_retries=st.integers(min_value=1, max_value=5),
        base_delay=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
        backoff_factor=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_retry_attempts_exactly_max_retries_times_on_failure(
        self, max_retries: int, base_delay: float, backoff_factor: float
    ):
        """
        Property: The retry mechanism attempts exactly max_retries times before failing.
        
        **Validates: Requirements 4.5**
        
        For any max_retries value, when an operation always fails,
        the retry mechanism should attempt exactly max_retries times.
        """
        from unittest.mock import AsyncMock, patch
        from utils.oauth_helpers import retry_async_operation
        
        # Track call count
        call_count = 0
        
        async def always_failing_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Simulated failure")
        
        # Mock asyncio.sleep to avoid actual delays
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            with pytest.raises(ValueError, match="Simulated failure"):
                await retry_async_operation(
                    operation=always_failing_operation,
                    max_retries=max_retries,
                    base_delay=base_delay,
                    backoff_factor=backoff_factor,
                    max_delay=100.0,  # High max_delay to not interfere
                    operation_name="test_operation",
                )
        
        # Verify exactly max_retries attempts were made
        assert call_count == max_retries, (
            f"Expected {max_retries} attempts, but got {call_count}"
        )

    @given(
        max_retries=st.integers(min_value=2, max_value=5),
        base_delay=st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
        backoff_factor=st.floats(min_value=1.5, max_value=3.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_delay_follows_exponential_backoff_pattern(
        self, max_retries: int, base_delay: float, backoff_factor: float
    ):
        """
        Property: The delay between retries follows exponential backoff pattern.
        
        **Validates: Requirements 4.5**
        
        For any base_delay and backoff_factor, the delay should increase
        exponentially: delay_i = base_delay * (backoff_factor ^ (i-1))
        """
        from unittest.mock import AsyncMock, patch
        from utils.oauth_helpers import retry_async_operation
        
        recorded_delays = []
        
        async def mock_sleep(delay):
            recorded_delays.append(delay)
        
        async def always_failing_operation():
            raise ValueError("Simulated failure")
        
        with patch("asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await retry_async_operation(
                    operation=always_failing_operation,
                    max_retries=max_retries,
                    base_delay=base_delay,
                    backoff_factor=backoff_factor,
                    max_delay=1000.0,  # High max_delay to not interfere
                    operation_name="test_operation",
                )
        
        # Verify delays follow exponential backoff pattern
        # Number of sleeps should be max_retries - 1 (no sleep after last attempt)
        expected_sleep_count = max_retries - 1
        assert len(recorded_delays) == expected_sleep_count, (
            f"Expected {expected_sleep_count} sleep calls, got {len(recorded_delays)}"
        )
        
        # Verify each delay follows the formula: base_delay * (backoff_factor ^ attempt)
        for i, delay in enumerate(recorded_delays):
            expected_delay = base_delay * (backoff_factor ** i)
            # Use approximate comparison due to floating point
            assert abs(delay - expected_delay) < 0.001, (
                f"Delay {i} was {delay}, expected {expected_delay} "
                f"(base={base_delay}, factor={backoff_factor})"
            )

    @given(
        max_retries=st.integers(min_value=2, max_value=5),
        success_on_attempt=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_success_on_any_attempt_returns_immediately(
        self, max_retries: int, success_on_attempt: int
    ):
        """
        Property: Success on any attempt returns immediately without further retries.
        
        **Validates: Requirements 4.5**
        
        When an operation succeeds on attempt N (where N <= max_retries),
        the retry mechanism should return immediately without further attempts.
        """
        from unittest.mock import AsyncMock, patch
        from utils.oauth_helpers import retry_async_operation
        
        # Ensure success_on_attempt is within valid range
        actual_success_attempt = min(success_on_attempt, max_retries)
        
        call_count = 0
        expected_result = f"success_on_attempt_{actual_success_attempt}"
        
        async def succeeds_on_nth_attempt():
            nonlocal call_count
            call_count += 1
            if call_count < actual_success_attempt:
                raise ValueError(f"Failure on attempt {call_count}")
            return expected_result
        
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await retry_async_operation(
                operation=succeeds_on_nth_attempt,
                max_retries=max_retries,
                base_delay=0.01,
                backoff_factor=2.0,
                max_delay=100.0,
                operation_name="test_operation",
            )
        
        # Verify the result is correct
        assert result == expected_result, (
            f"Expected result '{expected_result}', got '{result}'"
        )
        
        # Verify exactly actual_success_attempt calls were made (no extra retries)
        assert call_count == actual_success_attempt, (
            f"Expected {actual_success_attempt} attempts, but got {call_count}. "
            f"Operation should stop after success."
        )

    @given(
        max_retries=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_correct_exception_raised_after_all_retries_exhausted(
        self, max_retries: int
    ):
        """
        Property: The correct exception is raised after all retries are exhausted.
        
        **Validates: Requirements 4.5**
        
        When all retries fail, the last exception should be raised,
        preserving the original exception type and message.
        """
        from unittest.mock import AsyncMock, patch
        from utils.oauth_helpers import retry_async_operation
        
        last_error_message = f"Final failure after {max_retries} attempts"
        call_count = 0
        
        async def always_failing_with_different_messages():
            nonlocal call_count
            call_count += 1
            if call_count == max_retries:
                raise ValueError(last_error_message)
            raise ValueError(f"Failure on attempt {call_count}")
        
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ValueError) as exc_info:
                await retry_async_operation(
                    operation=always_failing_with_different_messages,
                    max_retries=max_retries,
                    base_delay=0.01,
                    backoff_factor=2.0,
                    max_delay=100.0,
                    operation_name="test_operation",
                )
        
        # Verify the last exception is raised
        assert last_error_message in str(exc_info.value), (
            f"Expected last error message '{last_error_message}', "
            f"got '{exc_info.value}'"
        )

    @given(
        max_retries=st.integers(min_value=2, max_value=5),
        base_delay=st.floats(min_value=0.1, max_value=1.0, allow_nan=False, allow_infinity=False),
        backoff_factor=st.floats(min_value=2.0, max_value=3.0, allow_nan=False, allow_infinity=False),
        max_delay=st.floats(min_value=0.5, max_value=2.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_delay_capped_by_max_delay(
        self, max_retries: int, base_delay: float, backoff_factor: float, max_delay: float
    ):
        """
        Property: The delay is capped by max_delay.
        
        **Validates: Requirements 4.5**
        
        No matter how large the exponential backoff grows,
        the actual delay should never exceed max_delay.
        """
        from unittest.mock import AsyncMock, patch
        from utils.oauth_helpers import retry_async_operation
        
        recorded_delays = []
        
        async def mock_sleep(delay):
            recorded_delays.append(delay)
        
        async def always_failing_operation():
            raise ValueError("Simulated failure")
        
        with patch("asyncio.sleep", side_effect=mock_sleep):
            with pytest.raises(ValueError):
                await retry_async_operation(
                    operation=always_failing_operation,
                    max_retries=max_retries,
                    base_delay=base_delay,
                    backoff_factor=backoff_factor,
                    max_delay=max_delay,
                    operation_name="test_operation",
                )
        
        # Verify all delays are capped by max_delay
        for i, delay in enumerate(recorded_delays):
            assert delay <= max_delay + 0.001, (  # Small tolerance for floating point
                f"Delay {i} was {delay}, which exceeds max_delay {max_delay}"
            )

    @given(
        max_retries=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_only_specified_exceptions_trigger_retry(
        self, max_retries: int
    ):
        """
        Property: Only specified exception types trigger retry.
        
        **Validates: Requirements 4.5**
        
        When exceptions parameter is specified, only those exception types
        should trigger retries. Other exceptions should propagate immediately.
        """
        from unittest.mock import AsyncMock, patch
        from utils.oauth_helpers import retry_async_operation
        
        call_count = 0
        
        async def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("This should not be retried")
        
        with patch("asyncio.sleep", new_callable=AsyncMock):
            # Only retry on ValueError, not TypeError
            with pytest.raises(TypeError, match="This should not be retried"):
                await retry_async_operation(
                    operation=raises_type_error,
                    max_retries=max_retries,
                    base_delay=0.01,
                    backoff_factor=2.0,
                    max_delay=100.0,
                    operation_name="test_operation",
                    exceptions=(ValueError,),  # Only retry ValueError
                )
        
        # Should only be called once since TypeError is not in retry list
        assert call_count == 1, (
            f"Expected 1 attempt (no retry for TypeError), but got {call_count}"
        )

    @given(
        max_retries=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_async_retry_decorator_attempts_exactly_max_retries(
        self, max_retries: int
    ):
        """
        Property: The async_retry decorator attempts exactly max_retries times.
        
        **Validates: Requirements 4.5**
        
        The decorator version should have the same retry behavior
        as the function version.
        """
        from unittest.mock import AsyncMock, patch
        from utils.oauth_helpers import async_retry
        
        call_count = 0
        
        @async_retry(max_retries=max_retries, base_delay=0.01, backoff_factor=2.0)
        async def decorated_failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Decorated function failure")
        
        with patch("asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(ValueError, match="Decorated function failure"):
                await decorated_failing_function()
        
        assert call_count == max_retries, (
            f"Decorator: Expected {max_retries} attempts, but got {call_count}"
        )

    @given(
        max_retries=st.integers(min_value=2, max_value=5),
        success_on_attempt=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_async_retry_decorator_returns_on_success(
        self, max_retries: int, success_on_attempt: int
    ):
        """
        Property: The async_retry decorator returns immediately on success.
        
        **Validates: Requirements 4.5**
        
        The decorator should return the result as soon as the function succeeds.
        """
        from unittest.mock import AsyncMock, patch
        from utils.oauth_helpers import async_retry
        
        actual_success_attempt = min(success_on_attempt, max_retries)
        call_count = 0
        expected_result = f"decorator_success_{actual_success_attempt}"
        
        @async_retry(max_retries=max_retries, base_delay=0.01, backoff_factor=2.0)
        async def decorated_succeeds_on_nth():
            nonlocal call_count
            call_count += 1
            if call_count < actual_success_attempt:
                raise ValueError(f"Failure on attempt {call_count}")
            return expected_result
        
        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await decorated_succeeds_on_nth()
        
        assert result == expected_result, (
            f"Expected '{expected_result}', got '{result}'"
        )
        assert call_count == actual_success_attempt, (
            f"Decorator: Expected {actual_success_attempt} attempts, got {call_count}"
        )
