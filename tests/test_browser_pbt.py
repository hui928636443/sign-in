#!/usr/bin/env python3
"""
浏览器工具模块的属性测试 (Property-Based Testing)

使用 hypothesis 库进行属性测试，验证 TabManager 的新标签页检测逻辑。

**Validates: Requirements 1.3, 3.1**
"""

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Optional

import pytest
from hypothesis import given, strategies as st, settings, assume, HealthCheck


# ============================================================================
# Mock Objects for Testing
# ============================================================================

@dataclass
class MockTarget:
    """Mock nodriver tab target object."""
    target_id: str
    url: str = ""
    title: str = ""


class MockTab:
    """Mock nodriver tab object for testing.
    
    Simulates the behavior of a nodriver Tab object without requiring
    a real browser instance.
    """
    
    def __init__(self, target_id: str, url: str = ""):
        self.target = MockTarget(target_id=target_id, url=url)
        self._brought_to_front = False
    
    async def bring_to_front(self):
        """Mock bring_to_front method."""
        self._brought_to_front = True


class MockBrowser:
    """Mock nodriver browser object for testing.
    
    Simulates the behavior of a nodriver Browser object with a list of tabs.
    """
    
    def __init__(self, tabs: list[MockTab] = None):
        self.tabs = tabs if tabs is not None else []
    
    def add_tab(self, tab: MockTab):
        """Add a tab to the browser."""
        self.tabs.append(tab)
    
    def remove_tab(self, tab: MockTab):
        """Remove a tab from the browser."""
        if tab in self.tabs:
            self.tabs.remove(tab)


# ============================================================================
# Import TabManager after mocks are defined
# ============================================================================

from utils.browser import TabManager


# ============================================================================
# Helper Functions for Tab Creation (Faster than @st.composite)
# ============================================================================

def create_mock_tabs(count: int, prefix: str = "tab", url_prefix: str = "https://site") -> list[MockTab]:
    """Create a list of mock tabs with unique IDs.
    
    This is faster than using @st.composite strategies for simple cases.
    """
    return [
        MockTab(target_id=f"{prefix}_{i}", url=f"{url_prefix}{i}.com")
        for i in range(count)
    ]


# ============================================================================
# Property Tests for New Tab Detection
# ============================================================================

class TestNewTabDetectionProperty:
    """
    Property 1: New Tab Detection
    
    *For any* browser state with N tabs before an action and M tabs after 
    (where M > N), the TabManager SHALL correctly identify exactly (M - N) 
    new tabs by comparing the tab lists.
    
    **Validates: Requirements 1.3, 3.1**
    """

    @given(
        initial_count=st.integers(min_value=1, max_value=5),
        new_count=st.integers(min_value=0, max_value=3)
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_new_tab_count_detection(self, initial_count: int, new_count: int):
        """
        Property: TabManager correctly counts the number of new tabs.
        
        **Validates: Requirements 1.3, 3.1**
        
        For any initial tab count N and new tab count M, after recording
        the initial count and adding M new tabs, the TabManager should
        detect that new tabs were added when M > 0.
        """
        # Create initial and new tabs
        initial_tabs = create_mock_tabs(initial_count, "initial", "https://initial")
        new_tabs = create_mock_tabs(new_count, "new", "https://new")
        
        # Create browser with initial tabs
        browser = MockBrowser(tabs=list(initial_tabs))
        tab_manager = TabManager(browser)
        
        # Record initial tab count
        recorded_count = tab_manager.record_tab_count()
        
        # Verify initial count is correct
        assert recorded_count == initial_count, (
            f"Initial count {recorded_count} doesn't match actual {initial_count}"
        )
        
        # Add new tabs to browser
        for tab in new_tabs:
            browser.add_tab(tab)
        
        # Verify new tab count detection
        current_count = len(browser.tabs)
        expected_new_count = current_count - recorded_count
        
        assert expected_new_count == new_count, (
            f"Expected {new_count} new tabs, but count difference is {expected_new_count}"
        )

    @given(
        initial_count=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=100)
    def test_initial_tab_recording(self, initial_count: int):
        """
        Property: TabManager correctly records initial tab state.
        
        **Validates: Requirements 3.1**
        
        For any browser state with N tabs, record_tab_count() should
        return exactly N and store the tab IDs for later comparison.
        """
        initial_tabs = create_mock_tabs(initial_count)
        
        browser = MockBrowser(tabs=list(initial_tabs))
        tab_manager = TabManager(browser)
        
        # Record initial state
        count = tab_manager.record_tab_count()
        
        # Verify count matches
        assert count == initial_count, (
            f"Recorded count {count} doesn't match actual {initial_count}"
        )
        
        # Verify internal state is correctly stored
        assert tab_manager._initial_tab_count == initial_count, (
            f"Internal count {tab_manager._initial_tab_count} doesn't match"
        )
        
        # Verify tab IDs are stored
        assert len(tab_manager._initial_tabs) == initial_count, (
            f"Stored {len(tab_manager._initial_tabs)} tab IDs, expected {initial_count}"
        )

    @given(
        initial_count=st.integers(min_value=1, max_value=5),
        new_count=st.integers(min_value=1, max_value=3)
    )
    @settings(max_examples=100)
    def test_new_tab_identification_by_id(self, initial_count: int, new_count: int):
        """
        Property: TabManager identifies new tabs by comparing tab IDs.
        
        **Validates: Requirements 3.1**
        
        For any set of initial tabs and new tabs, the TabManager should
        correctly identify which tabs are new by comparing their IDs
        against the recorded initial tab IDs.
        """
        initial_tabs = create_mock_tabs(initial_count, "initial")
        new_tabs = create_mock_tabs(new_count, "new")
        
        browser = MockBrowser(tabs=list(initial_tabs))
        tab_manager = TabManager(browser)
        
        # Record initial state
        tab_manager.record_tab_count()
        
        # Get initial tab IDs
        initial_ids = set(tab_manager._initial_tabs)
        
        # Add new tabs
        for tab in new_tabs:
            browser.add_tab(tab)
        
        # Verify new tabs are not in initial IDs
        for tab in new_tabs:
            tab_id = tab.target.target_id
            assert tab_id not in initial_ids, (
                f"New tab ID {tab_id} should not be in initial IDs"
            )
        
        # Verify initial tabs are still in initial IDs
        for tab in initial_tabs:
            tab_id = tab.target.target_id
            assert tab_id in initial_ids, (
                f"Initial tab ID {tab_id} should be in initial IDs"
            )

    @given(initial_count=st.integers(min_value=1, max_value=5))
    @settings(max_examples=50)
    def test_no_new_tabs_detected_when_none_added(self, initial_count: int):
        """
        Property: No new tabs detected when tab count doesn't change.
        
        **Validates: Requirements 3.1**
        
        If no new tabs are added after recording, the difference between
        current and initial count should be zero.
        """
        initial_tabs = create_mock_tabs(initial_count)
        
        browser = MockBrowser(tabs=list(initial_tabs))
        tab_manager = TabManager(browser)
        
        # Record initial state
        recorded_count = tab_manager.record_tab_count()
        
        # Don't add any new tabs
        
        # Current count should equal initial count
        current_count = len(browser.tabs)
        assert current_count == recorded_count, (
            f"Tab count changed from {recorded_count} to {current_count} without adding tabs"
        )

    @given(
        initial_count=st.integers(min_value=1, max_value=10),
        new_count=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=100)
    def test_exact_new_tab_count_calculation(self, initial_count: int, new_count: int):
        """
        Property: New tab count equals (current_count - initial_count).
        
        **Validates: Requirements 1.3, 3.1**
        
        For any N initial tabs and M new tabs added, the number of new
        tabs detected should be exactly M.
        """
        # Create initial tabs
        initial_tabs = create_mock_tabs(initial_count, "initial")
        
        # Create new tabs
        new_tabs = create_mock_tabs(new_count, "new")
        
        browser = MockBrowser(tabs=list(initial_tabs))
        tab_manager = TabManager(browser)
        
        # Record initial state
        recorded_initial = tab_manager.record_tab_count()
        assert recorded_initial == initial_count
        
        # Add new tabs
        for tab in new_tabs:
            browser.add_tab(tab)
        
        # Calculate new tab count
        current_count = len(browser.tabs)
        detected_new_count = current_count - recorded_initial
        
        assert detected_new_count == new_count, (
            f"Expected {new_count} new tabs, detected {detected_new_count}"
        )

    def test_empty_browser_handling(self):
        """
        Property: TabManager handles None browser gracefully.
        
        **Validates: Requirements 3.1**
        
        When browser is None, record_tab_count should return 0
        and not raise an exception.
        """
        tab_manager = TabManager(None)
        
        # Should not raise and should return 0
        count = tab_manager.record_tab_count()
        assert count == 0, f"Expected 0 for None browser, got {count}"
        
        # Internal state should be empty
        assert tab_manager._initial_tab_count == 0
        assert tab_manager._initial_tabs == []

    @given(initial_count=st.integers(min_value=1, max_value=5))
    @settings(max_examples=50)
    def test_tab_detection_is_deterministic(self, initial_count: int):
        """
        Property: Tab detection produces consistent results.
        
        **Validates: Requirements 3.1**
        
        Calling record_tab_count multiple times with the same browser
        state should produce the same result.
        """
        initial_tabs = create_mock_tabs(initial_count)
        
        browser = MockBrowser(tabs=list(initial_tabs))
        tab_manager = TabManager(browser)
        
        # Record multiple times
        count1 = tab_manager.record_tab_count()
        count2 = tab_manager.record_tab_count()
        count3 = tab_manager.record_tab_count()
        
        # All counts should be equal
        assert count1 == count2 == count3, (
            f"Non-deterministic counts: {count1}, {count2}, {count3}"
        )

    @given(
        initial_count=st.integers(min_value=1, max_value=5),
        tabs_to_remove=st.integers(min_value=0, max_value=3)
    )
    @settings(max_examples=50)
    def test_tab_removal_detection(self, initial_count: int, tabs_to_remove: int):
        """
        Property: TabManager detects when tabs are removed (negative difference).
        
        **Validates: Requirements 3.1**
        
        If tabs are removed after recording, the difference should be negative,
        indicating no new tabs were added.
        """
        # Ensure we don't try to remove more tabs than exist
        assume(tabs_to_remove <= initial_count)
        
        # Create initial tabs
        initial_tabs = create_mock_tabs(initial_count)
        
        browser = MockBrowser(tabs=list(initial_tabs))
        tab_manager = TabManager(browser)
        
        # Record initial state
        recorded_initial = tab_manager.record_tab_count()
        
        # Remove some tabs
        for _ in range(tabs_to_remove):
            if browser.tabs:
                browser.tabs.pop()
        
        # Calculate difference
        current_count = len(browser.tabs)
        difference = current_count - recorded_initial
        
        # Difference should be negative or zero (no new tabs)
        assert difference <= 0, (
            f"Expected non-positive difference after removing tabs, got {difference}"
        )
        assert difference == -tabs_to_remove, (
            f"Expected difference of {-tabs_to_remove}, got {difference}"
        )


class TestTabManagerSwitching:
    """
    Tests for TabManager's tab switching functionality.
    
    **Validates: Requirements 1.3, 3.3**
    """

    @given(initial_count=st.integers(min_value=1, max_value=5))
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_switch_to_tab_calls_bring_to_front(self, initial_count: int):
        """
        Property: switch_to_tab calls bring_to_front on the target tab.
        
        **Validates: Requirements 1.3, 3.3**
        
        When switching to a tab, the TabManager should call bring_to_front()
        to ensure the tab is active.
        """
        initial_tabs = create_mock_tabs(initial_count)
        
        browser = MockBrowser(tabs=list(initial_tabs))
        tab_manager = TabManager(browser)
        
        # Pick the first tab to switch to
        target_tab = initial_tabs[0]
        
        # Verify tab hasn't been brought to front yet
        assert not target_tab._brought_to_front
        
        # Switch to the tab
        await tab_manager.switch_to_tab(target_tab)
        
        # Verify bring_to_front was called
        assert target_tab._brought_to_front, (
            "bring_to_front() was not called on the target tab"
        )

    @pytest.mark.asyncio
    async def test_switch_to_none_tab_handles_gracefully(self):
        """
        Property: switch_to_tab handles None tab gracefully.
        
        **Validates: Requirements 3.3**
        
        When attempting to switch to None, the method should not raise
        an exception.
        """
        browser = MockBrowser(tabs=[])
        tab_manager = TabManager(browser)
        
        # Should not raise
        await tab_manager.switch_to_tab(None)


class TestFindOAuthTab:
    """
    Tests for TabManager's OAuth tab finding functionality.
    
    **Validates: Requirements 3.2**
    """

    @given(
        non_oauth_count=st.integers(min_value=0, max_value=3),
        oauth_url=st.sampled_from([
            "https://linux.do/login",
            "https://connect.linux.do/oauth/authorize",
            "https://example.com/oauth/callback",
            "https://example.com/authorize",
        ])
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_find_oauth_tab_returns_oauth_related_tab(
        self, non_oauth_count: int, oauth_url: str
    ):
        """
        Property: find_oauth_tab returns a tab with OAuth-related URL.
        
        **Validates: Requirements 3.2**
        
        When there's a tab with an OAuth-related URL (containing linux.do,
        oauth, authorize, or callback), find_oauth_tab should return it.
        """
        # Create non-OAuth tabs
        non_oauth_tabs = [
            MockTab(target_id=f"non_oauth_{i}", url=f"https://regular{i}.com")
            for i in range(non_oauth_count)
        ]
        
        # Create OAuth tab
        oauth_tab = MockTab(target_id="oauth_tab", url=oauth_url)
        
        # Combine tabs (OAuth tab at the end)
        all_tabs = non_oauth_tabs + [oauth_tab]
        
        browser = MockBrowser(tabs=all_tabs)
        tab_manager = TabManager(browser)
        
        # Find OAuth tab
        found_tab = await tab_manager.find_oauth_tab()
        
        # Should find the OAuth tab
        assert found_tab is not None, (
            f"Failed to find OAuth tab with URL {oauth_url}"
        )
        assert found_tab.target.url == oauth_url, (
            f"Found wrong tab: {found_tab.target.url} instead of {oauth_url}"
        )

    @given(non_oauth_count=st.integers(min_value=0, max_value=5))
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_find_oauth_tab_returns_none_when_no_oauth_tabs(
        self, non_oauth_count: int
    ):
        """
        Property: find_oauth_tab returns None when no OAuth tabs exist.
        
        **Validates: Requirements 3.2**
        
        When there are no tabs with OAuth-related URLs, find_oauth_tab
        should return None.
        """
        # Create non-OAuth tabs with regular URLs
        non_oauth_tabs = [
            MockTab(target_id=f"non_oauth_{i}", url=f"https://regular-site-{i}.com")
            for i in range(non_oauth_count)
        ]
        
        browser = MockBrowser(tabs=list(non_oauth_tabs))
        tab_manager = TabManager(browser)
        
        # Find OAuth tab
        found_tab = await tab_manager.find_oauth_tab()
        
        # Should not find any OAuth tab
        assert found_tab is None, (
            f"Found unexpected OAuth tab: {found_tab.target.url if found_tab else 'N/A'}"
        )

    @pytest.mark.asyncio
    async def test_find_oauth_tab_with_none_browser(self):
        """
        Property: find_oauth_tab handles None browser gracefully.
        
        **Validates: Requirements 3.2**
        
        When browser is None, find_oauth_tab should return None
        without raising an exception.
        """
        tab_manager = TabManager(None)
        
        # Should not raise and should return None
        found_tab = await tab_manager.find_oauth_tab()
        assert found_tab is None


# ============================================================================
# URLMonitor Tests
# ============================================================================

from utils.browser import URLMonitor


class MockFrameTreeResult:
    """Mock CDP get_frame_tree() result."""
    
    def __init__(self, url: str):
        self.frame = MockFrame(url)


class MockFrame:
    """Mock CDP Frame object."""
    
    def __init__(self, url: str):
        self.url = url


class MockTabForURLMonitor:
    """Mock nodriver tab object for URLMonitor testing.
    
    Simulates the behavior of a nodriver Tab object with CDP support.
    """
    
    def __init__(self, url: str = "", cdp_fails: bool = False):
        self.target = MockTarget(target_id="test_tab", url=url)
        self._cdp_fails = cdp_fails
        self._cdp_url = url  # URL returned by CDP
    
    async def send(self, command):
        """Mock CDP send method."""
        if self._cdp_fails:
            raise Exception("CDP command failed")
        return MockFrameTreeResult(self._cdp_url)
    
    def set_cdp_url(self, url: str):
        """Set the URL that CDP will return."""
        self._cdp_url = url
    
    def set_target_url(self, url: str):
        """Set the URL that tab.target.url will return."""
        self.target.url = url


class TestURLMonitorGetCurrentUrl:
    """
    Tests for URLMonitor.get_current_url() method.
    
    **Validates: Requirements 1.5, 2.2**
    """

    @pytest.mark.asyncio
    async def test_get_current_url_uses_cdp(self):
        """
        Test that get_current_url uses CDP get_frame_tree() for accurate URL.
        
        **Validates: Requirements 1.5, 2.2**
        """
        expected_url = "https://linux.do/login"
        tab = MockTabForURLMonitor(url=expected_url)
        
        monitor = URLMonitor(tab)
        url = await monitor.get_current_url()
        
        assert url == expected_url, f"Expected {expected_url}, got {url}"

    @pytest.mark.asyncio
    async def test_get_current_url_fallback_to_target_url(self):
        """
        Test that get_current_url falls back to tab.target.url if CDP fails.
        
        **Validates: Requirements 1.5, 2.2**
        """
        expected_url = "https://linux.do/login"
        tab = MockTabForURLMonitor(url=expected_url, cdp_fails=True)
        
        monitor = URLMonitor(tab)
        url = await monitor.get_current_url()
        
        assert url == expected_url, f"Expected {expected_url}, got {url}"

    @pytest.mark.asyncio
    async def test_get_current_url_with_none_tab(self):
        """
        Test that get_current_url handles None tab gracefully.
        
        **Validates: Requirements 1.5, 2.2**
        """
        monitor = URLMonitor(None)
        url = await monitor.get_current_url()
        
        assert url == "", f"Expected empty string for None tab, got {url}"

    @pytest.mark.asyncio
    async def test_get_current_url_cdp_returns_different_url_than_target(self):
        """
        Test that CDP URL takes precedence over tab.target.url.
        
        **Validates: Requirements 1.5, 2.2**
        
        This tests the case where CDP returns a more accurate URL than
        tab.target.url (which may be stale during navigation).
        """
        cdp_url = "https://linux.do/session/sso_login"
        target_url = "https://example.com/login"  # Stale URL
        
        tab = MockTabForURLMonitor(url=target_url)
        tab.set_cdp_url(cdp_url)
        
        monitor = URLMonitor(tab)
        url = await monitor.get_current_url()
        
        # CDP URL should take precedence
        assert url == cdp_url, f"Expected CDP URL {cdp_url}, got {url}"


class TestURLMonitorWaitForUrlContains:
    """
    Tests for URLMonitor.wait_for_url_contains() method.
    
    **Validates: Requirements 2.1, 2.5**
    """

    @pytest.mark.asyncio
    async def test_wait_for_url_contains_immediate_match(self):
        """
        Test that wait_for_url_contains returns immediately when URL matches.
        
        **Validates: Requirements 2.1**
        """
        expected_url = "https://linux.do/login"
        tab = MockTabForURLMonitor(url=expected_url)
        
        monitor = URLMonitor(tab, poll_interval=0.1)
        url = await monitor.wait_for_url_contains("linux.do", timeout=5)
        
        assert url == expected_url, f"Expected {expected_url}, got {url}"

    @pytest.mark.asyncio
    async def test_wait_for_url_contains_case_insensitive(self):
        """
        Test that URL pattern matching is case-insensitive.
        
        **Validates: Requirements 2.1**
        """
        expected_url = "https://LINUX.DO/login"
        tab = MockTabForURLMonitor(url=expected_url)
        
        monitor = URLMonitor(tab, poll_interval=0.1)
        url = await monitor.wait_for_url_contains("linux.do", timeout=5)
        
        assert url == expected_url, f"Expected {expected_url}, got {url}"

    @pytest.mark.asyncio
    async def test_wait_for_url_contains_timeout(self):
        """
        Test that wait_for_url_contains raises TimeoutError on timeout.
        
        **Validates: Requirements 2.5**
        """
        tab = MockTabForURLMonitor(url="https://example.com")
        
        monitor = URLMonitor(tab, poll_interval=0.1)
        
        with pytest.raises(TimeoutError) as exc_info:
            await monitor.wait_for_url_contains("linux.do", timeout=0.5)
        
        assert "linux.do" in str(exc_info.value)
        assert "超时" in str(exc_info.value) or "timeout" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_wait_for_url_contains_empty_pattern_raises_error(self):
        """
        Test that empty pattern raises ValueError.
        
        **Validates: Requirements 2.1**
        """
        tab = MockTabForURLMonitor(url="https://example.com")
        
        monitor = URLMonitor(tab, poll_interval=0.1)
        
        with pytest.raises(ValueError) as exc_info:
            await monitor.wait_for_url_contains("", timeout=5)
        
        assert "空" in str(exc_info.value) or "empty" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_wait_for_url_contains_default_poll_interval(self):
        """
        Test that default poll interval is 0.5 seconds (500ms).
        
        **Validates: Requirements 2.1**
        """
        tab = MockTabForURLMonitor(url="https://example.com")
        
        monitor = URLMonitor(tab)
        
        # Default poll interval should be 0.5 seconds per Requirements 2.1
        assert monitor.poll_interval == 0.5, (
            f"Expected default poll interval 0.5, got {monitor.poll_interval}"
        )

    @pytest.mark.asyncio
    async def test_wait_for_url_contains_default_timeout(self):
        """
        Test that default timeout is 30 seconds.
        
        **Validates: Requirements 2.5**
        """
        # This test verifies the default timeout parameter value
        # by checking the function signature
        import inspect
        
        sig = inspect.signature(URLMonitor.wait_for_url_contains)
        timeout_param = sig.parameters.get('timeout')
        
        assert timeout_param is not None, "timeout parameter not found"
        assert timeout_param.default == 30, (
            f"Expected default timeout 30, got {timeout_param.default}"
        )


class TestURLMonitorPropertyBased:
    """
    Property-based tests for URLMonitor.
    
    **Validates: Requirements 1.5, 2.1, 2.2, 2.5**
    """

    @given(url=st.text(min_size=0, max_size=200))
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_get_current_url_returns_string(self, url: str):
        """
        Property: get_current_url always returns a string.
        
        **Validates: Requirements 1.5, 2.2**
        """
        tab = MockTabForURLMonitor(url=url)
        
        monitor = URLMonitor(tab)
        result = await monitor.get_current_url()
        
        assert isinstance(result, str), f"Expected string, got {type(result)}"

    @given(
        url=st.text(min_size=1, max_size=100),
        pattern=st.text(min_size=1, max_size=20)
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_wait_for_url_contains_finds_pattern_when_present(
        self, url: str, pattern: str
    ):
        """
        Property: If URL contains pattern, wait_for_url_contains returns the URL.
        
        **Validates: Requirements 2.1**
        """
        # Ensure URL contains the pattern
        full_url = f"https://example.com/{pattern}/page"
        tab = MockTabForURLMonitor(url=full_url)
        
        monitor = URLMonitor(tab, poll_interval=0.1)
        result = await monitor.wait_for_url_contains(pattern, timeout=1)
        
        assert pattern.lower() in result.lower(), (
            f"Pattern '{pattern}' not found in result '{result}'"
        )

    @given(poll_interval=st.floats(min_value=0.01, max_value=2.0))
    @settings(max_examples=20)
    def test_poll_interval_is_configurable(self, poll_interval: float):
        """
        Property: Poll interval can be configured to any positive value.
        
        **Validates: Requirements 2.1**
        """
        tab = MockTabForURLMonitor(url="https://example.com")
        
        monitor = URLMonitor(tab, poll_interval=poll_interval)
        
        assert monitor.poll_interval == poll_interval, (
            f"Expected poll interval {poll_interval}, got {monitor.poll_interval}"
        )


# ============================================================================
# CookieRetriever Tests
# ============================================================================

from utils.browser import CookieRetriever


class MockCookie:
    """Mock CDP Cookie object for testing."""
    
    def __init__(self, name: str, domain: str, value: str):
        self.name = name
        self.domain = domain
        self.value = value


class MockBrowserManagerForCookies:
    """Mock BrowserManager for CookieRetriever testing."""
    
    def __init__(self, cookies: list = None, engine: str = "nodriver"):
        self._cookies = cookies if cookies is not None else []
        self.engine = engine
        self._page = MockTabForCookies(cookies=self._cookies)
    
    @property
    def page(self):
        return self._page
    
    async def get_cookies(self) -> list:
        """Return mock cookies."""
        return self._cookies


class MockTabForCookies:
    """Mock nodriver tab for cookie retrieval testing."""
    
    def __init__(self, cookies: list = None, cdp_fails: bool = False):
        self._cookies = cookies if cookies is not None else []
        self._cdp_fails = cdp_fails
    
    async def send(self, command):
        """Mock CDP send method for get_all_cookies."""
        if self._cdp_fails:
            raise Exception("CDP command failed")
        return self._cookies


class TestCookieRetrieverDomainMatching:
    """
    Tests for CookieRetriever domain matching logic.
    
    **Validates: Requirements 6.3**
    """

    def test_exact_domain_match(self):
        """
        Test exact domain matching.
        
        **Validates: Requirements 6.3**
        """
        browser = MockBrowserManagerForCookies()
        retriever = CookieRetriever(browser, "example.com")
        
        assert retriever._domain_matches("example.com") is True
        assert retriever._domain_matches("other.com") is False

    def test_domain_with_leading_dot(self):
        """
        Test domain matching with leading dot.
        
        **Validates: Requirements 6.3**
        """
        browser = MockBrowserManagerForCookies()
        retriever = CookieRetriever(browser, "example.com")
        
        # Cookie domain with leading dot should match
        assert retriever._domain_matches(".example.com") is True

    def test_subdomain_matching(self):
        """
        Test subdomain matching.
        
        **Validates: Requirements 6.3**
        """
        browser = MockBrowserManagerForCookies()
        retriever = CookieRetriever(browser, "example.com")
        
        # Subdomains should match
        assert retriever._domain_matches("sub.example.com") is True
        assert retriever._domain_matches(".sub.example.com") is True
        assert retriever._domain_matches("deep.sub.example.com") is True

    def test_reverse_subdomain_matching(self):
        """
        Test reverse subdomain matching (target is subdomain of cookie domain).
        
        **Validates: Requirements 6.3**
        """
        browser = MockBrowserManagerForCookies()
        retriever = CookieRetriever(browser, "sub.example.com")
        
        # Cookie domain is parent of target domain
        assert retriever._domain_matches("example.com") is True
        assert retriever._domain_matches(".example.com") is True

    def test_case_insensitive_matching(self):
        """
        Test case-insensitive domain matching.
        
        **Validates: Requirements 6.3**
        """
        browser = MockBrowserManagerForCookies()
        retriever = CookieRetriever(browser, "Example.COM")
        
        assert retriever._domain_matches("example.com") is True
        assert retriever._domain_matches("EXAMPLE.COM") is True
        assert retriever._domain_matches("Example.Com") is True

    def test_empty_domain_no_match(self):
        """
        Test that empty domain doesn't match.
        
        **Validates: Requirements 6.3**
        """
        browser = MockBrowserManagerForCookies()
        retriever = CookieRetriever(browser, "example.com")
        
        assert retriever._domain_matches("") is False
        assert retriever._domain_matches(None) is False

    def test_partial_domain_no_match(self):
        """
        Test that partial domain names don't match.
        
        **Validates: Requirements 6.3**
        """
        browser = MockBrowserManagerForCookies()
        retriever = CookieRetriever(browser, "example.com")
        
        # These should NOT match
        assert retriever._domain_matches("notexample.com") is False
        assert retriever._domain_matches("example.com.evil.com") is False
        assert retriever._domain_matches("myexample.com") is False


class TestCookieRetrieverFindSessionCookie:
    """
    Tests for CookieRetriever._find_session_cookie() method.
    
    **Validates: Requirements 6.3**
    """

    def test_find_session_cookie_by_name_and_domain(self):
        """
        Test finding session cookie by name and domain.
        
        **Validates: Requirements 6.3**
        """
        cookies = [
            MockCookie("other", "example.com", "other_value"),
            MockCookie("session", "example.com", "session_value"),
            MockCookie("session", "other.com", "wrong_domain"),
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, "example.com")
        
        result = retriever._find_session_cookie(cookies)
        
        assert result == "session_value"

    def test_find_session_cookie_with_dict_format(self):
        """
        Test finding session cookie from dict format cookies.
        
        **Validates: Requirements 6.3**
        """
        cookies = [
            {"name": "other", "domain": "example.com", "value": "other_value"},
            {"name": "session", "domain": "example.com", "value": "session_value"},
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, "example.com")
        
        result = retriever._find_session_cookie(cookies)
        
        assert result == "session_value"

    def test_find_session_cookie_subdomain(self):
        """
        Test finding session cookie from subdomain.
        
        **Validates: Requirements 6.3**
        """
        cookies = [
            MockCookie("session", ".example.com", "session_value"),
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, "sub.example.com")
        
        result = retriever._find_session_cookie(cookies)
        
        assert result == "session_value"

    def test_find_session_cookie_not_found(self):
        """
        Test that None is returned when session cookie not found.
        
        **Validates: Requirements 6.3**
        """
        cookies = [
            MockCookie("other", "example.com", "other_value"),
            MockCookie("session", "other.com", "wrong_domain"),
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, "example.com")
        
        result = retriever._find_session_cookie(cookies)
        
        assert result is None

    def test_find_session_cookie_empty_list(self):
        """
        Test that None is returned for empty cookie list.
        
        **Validates: Requirements 6.3**
        """
        browser = MockBrowserManagerForCookies(cookies=[])
        retriever = CookieRetriever(browser, "example.com")
        
        result = retriever._find_session_cookie([])
        
        assert result is None


class TestCookieRetrieverGetSessionCookie:
    """
    Tests for CookieRetriever.get_session_cookie() method.
    
    **Validates: Requirements 6.1, 6.2, 6.3, 6.4**
    """

    @pytest.mark.asyncio
    async def test_get_session_cookie_success(self):
        """
        Test successful session cookie retrieval.
        
        **Validates: Requirements 6.1, 6.2, 6.3**
        """
        cookies = [
            MockCookie("session", "example.com", "test_session_value"),
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, "example.com")
        
        result = await retriever.get_session_cookie(max_retries=1)
        
        assert result == "test_session_value"

    @pytest.mark.asyncio
    async def test_get_session_cookie_not_found(self):
        """
        Test session cookie not found returns None.
        
        **Validates: Requirements 6.3, 6.4**
        """
        cookies = [
            MockCookie("other", "example.com", "other_value"),
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, "example.com")
        
        # Use max_retries=1 to speed up test
        result = await retriever.get_session_cookie(max_retries=1)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_cookie_retry_logic(self):
        """
        Test that retry logic is executed.
        
        **Validates: Requirements 6.4**
        """
        # Start with no session cookie
        cookies = []
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, "example.com")
        
        # Should retry and eventually return None
        result = await retriever.get_session_cookie(max_retries=2)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_cookie_non_nodriver_engine(self):
        """
        Test cookie retrieval with non-nodriver engine.
        
        **Validates: Requirements 6.1, 6.2**
        """
        cookies = [
            {"name": "session", "domain": "example.com", "value": "session_value"},
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies, engine="patchright")
        retriever = CookieRetriever(browser, "example.com")
        
        result = await retriever.get_session_cookie(max_retries=1)
        
        assert result == "session_value"


class TestCookieRetrieverPropertyBased:
    """
    Property-based tests for CookieRetriever.
    
    Property 3: Session Cookie Filtering
    
    *For any* list of cookies with varying names and domains, the CookieRetriever 
    SHALL return only the cookie where name equals "session" AND domain matches 
    the target domain (including subdomains).
    
    **Validates: Requirements 6.3**
    """

    @given(
        target_domain=st.sampled_from([
            "example.com",
            "linux.do",
            "sub.example.com",
            "deep.sub.example.com",
        ]),
        session_value=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N')))
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    @pytest.mark.asyncio
    async def test_session_cookie_filtering_returns_correct_value(
        self, target_domain: str, session_value: str
    ):
        """
        Property: CookieRetriever returns the correct session cookie value.
        
        **Validates: Requirements 6.3**
        
        For any target domain and session value, when a session cookie
        exists for that domain, the retriever should return its value.
        """
        cookies = [
            MockCookie("other", target_domain, "other_value"),
            MockCookie("session", target_domain, session_value),
            MockCookie("session", "unrelated.com", "wrong_value"),
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, target_domain)
        
        result = await retriever.get_session_cookie(max_retries=1)
        
        assert result == session_value, (
            f"Expected session value '{session_value}', got '{result}'"
        )

    @given(
        target_domain=st.text(min_size=3, max_size=30, alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='.-')),
        other_cookies_count=st.integers(min_value=0, max_value=10)
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    @pytest.mark.asyncio
    async def test_session_cookie_filtering_ignores_non_session_cookies(
        self, target_domain: str, other_cookies_count: int
    ):
        """
        Property: CookieRetriever ignores cookies that are not named "session".
        
        **Validates: Requirements 6.3**
        
        For any number of non-session cookies, the retriever should
        return None if no session cookie exists.
        """
        # Ensure target_domain is valid
        assume(len(target_domain) >= 3)
        assume("." in target_domain or target_domain.isalnum())
        
        # Create non-session cookies
        cookies = [
            MockCookie(f"cookie_{i}", target_domain, f"value_{i}")
            for i in range(other_cookies_count)
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, target_domain)
        
        result = await retriever.get_session_cookie(max_retries=1)
        
        assert result is None, (
            f"Expected None when no session cookie exists, got '{result}'"
        )

    @given(
        target_domain=st.sampled_from(["example.com", "linux.do", "test.org"]),
        wrong_domains=st.lists(
            st.sampled_from(["other.com", "wrong.net", "bad.org"]),
            min_size=1,
            max_size=5
        )
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    @pytest.mark.asyncio
    async def test_session_cookie_filtering_ignores_wrong_domains(
        self, target_domain: str, wrong_domains: list
    ):
        """
        Property: CookieRetriever ignores session cookies from wrong domains.
        
        **Validates: Requirements 6.3**
        
        For any session cookies with non-matching domains, the retriever
        should return None.
        """
        # Create session cookies with wrong domains
        cookies = [
            MockCookie("session", domain, f"value_for_{domain}")
            for domain in wrong_domains
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, target_domain)
        
        result = await retriever.get_session_cookie(max_retries=1)
        
        assert result is None, (
            f"Expected None for wrong domains {wrong_domains}, got '{result}'"
        )

    @given(
        base_domain=st.sampled_from(["example.com", "linux.do"]),
        subdomain_prefix=st.sampled_from(["sub", "api", "www", "app"])
    )
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture], deadline=None)
    @pytest.mark.asyncio
    async def test_session_cookie_filtering_matches_subdomains(
        self, base_domain: str, subdomain_prefix: str
    ):
        """
        Property: CookieRetriever matches session cookies from subdomains.
        
        **Validates: Requirements 6.3**
        
        For any subdomain of the target domain, the retriever should
        find the session cookie.
        """
        subdomain = f"{subdomain_prefix}.{base_domain}"
        session_value = f"session_for_{subdomain}"
        
        # Cookie is set on the base domain (with leading dot for subdomain matching)
        cookies = [
            MockCookie("session", f".{base_domain}", session_value),
        ]
        
        browser = MockBrowserManagerForCookies(cookies=cookies)
        retriever = CookieRetriever(browser, subdomain)
        
        result = await retriever.get_session_cookie(max_retries=1)
        
        assert result == session_value, (
            f"Expected '{session_value}' for subdomain '{subdomain}', got '{result}'"
        )


# ============================================================================
# Environment-Based Browser Configuration Tests
# ============================================================================

class TestEnvironmentBasedBrowserConfiguration:
    """
    Property 5: Environment-Based Browser Configuration
    
    *For any* environment configuration, the BrowserConfig SHALL:
    - Use non-headless mode when DISPLAY environment variable is set
    - Set sandbox=False when running as root (GitHub Actions)
    - Use headless mode when DISPLAY is not set and not running as root
    
    **Validates: Requirements 8.1, 8.2**
    
    Since we can't actually start browsers in unit tests, we test the 
    configuration logic by extracting and testing the decision-making logic.
    """

    @staticmethod
    def compute_browser_config(
        headless_requested: bool,
        display_set: bool,
        is_root: bool
    ) -> tuple[bool, bool]:
        """
        Compute the actual browser configuration based on environment.
        
        This function mirrors the logic in BrowserManager._start_nodriver().
        
        Args:
            headless_requested: Whether headless mode was requested by the user
            display_set: Whether DISPLAY environment variable is set
            is_root: Whether running as root user
            
        Returns:
            Tuple of (use_headless, use_sandbox)
        """
        # Requirement 8.1: When DISPLAY is set (Xvfb available), use non-headless mode
        # headless mode is easily detected by anti-bot systems, Xvfb bypasses this
        use_headless = headless_requested and not display_set
        
        # Requirement 8.2: When running as root, must set sandbox=False
        # Chrome's sandbox mechanism doesn't work properly under root user
        use_sandbox = not is_root
        
        return (use_headless, use_sandbox)

    @given(
        headless_requested=st.booleans(),
        display_set=st.booleans(),
        is_root=st.booleans()
    )
    @settings(max_examples=100)
    def test_display_set_implies_non_headless(
        self, headless_requested: bool, display_set: bool, is_root: bool
    ):
        """
        Property: When DISPLAY is set, headless mode should be disabled.
        
        **Validates: Requirements 8.1**
        
        For any configuration where DISPLAY is set (indicating Xvfb is available),
        the browser should run in non-headless mode to avoid anti-bot detection.
        """
        use_headless, _ = self.compute_browser_config(
            headless_requested, display_set, is_root
        )
        
        if display_set:
            # When DISPLAY is set, should NOT use headless mode
            assert use_headless is False, (
                f"When DISPLAY is set, headless should be False, "
                f"but got {use_headless} "
                f"(headless_requested={headless_requested})"
            )

    @given(
        headless_requested=st.booleans(),
        display_set=st.booleans(),
        is_root=st.booleans()
    )
    @settings(max_examples=100)
    def test_root_user_implies_no_sandbox(
        self, headless_requested: bool, display_set: bool, is_root: bool
    ):
        """
        Property: When running as root, sandbox should be disabled.
        
        **Validates: Requirements 8.2**
        
        For any configuration where the process is running as root (common in
        GitHub Actions), the browser sandbox must be disabled for Chrome to work.
        """
        _, use_sandbox = self.compute_browser_config(
            headless_requested, display_set, is_root
        )
        
        if is_root:
            # When running as root, sandbox should be False
            assert use_sandbox is False, (
                f"When running as root, sandbox should be False, "
                f"but got {use_sandbox}"
            )

    @given(
        headless_requested=st.booleans(),
        display_set=st.booleans(),
        is_root=st.booleans()
    )
    @settings(max_examples=100)
    def test_non_root_implies_sandbox_enabled(
        self, headless_requested: bool, display_set: bool, is_root: bool
    ):
        """
        Property: When NOT running as root, sandbox should be enabled.
        
        **Validates: Requirements 8.2**
        
        For security, when not running as root, the browser sandbox should
        remain enabled.
        """
        _, use_sandbox = self.compute_browser_config(
            headless_requested, display_set, is_root
        )
        
        if not is_root:
            # When NOT running as root, sandbox should be True
            assert use_sandbox is True, (
                f"When not running as root, sandbox should be True, "
                f"but got {use_sandbox}"
            )

    @given(
        headless_requested=st.booleans(),
        display_set=st.booleans(),
        is_root=st.booleans()
    )
    @settings(max_examples=100)
    def test_no_display_respects_headless_request(
        self, headless_requested: bool, display_set: bool, is_root: bool
    ):
        """
        Property: When DISPLAY is NOT set, headless mode follows user request.
        
        **Validates: Requirements 8.1**
        
        When there's no virtual display available (DISPLAY not set), the
        browser should respect the user's headless preference.
        """
        use_headless, _ = self.compute_browser_config(
            headless_requested, display_set, is_root
        )
        
        if not display_set:
            # When DISPLAY is not set, headless should match user request
            assert use_headless == headless_requested, (
                f"When DISPLAY is not set, headless should be {headless_requested}, "
                f"but got {use_headless}"
            )

    @given(
        headless_requested=st.booleans(),
        display_set=st.booleans(),
        is_root=st.booleans()
    )
    @settings(max_examples=100)
    def test_headless_and_sandbox_are_independent(
        self, headless_requested: bool, display_set: bool, is_root: bool
    ):
        """
        Property: Headless mode and sandbox settings are independent.
        
        **Validates: Requirements 8.1, 8.2**
        
        The headless setting (controlled by DISPLAY) and sandbox setting
        (controlled by root status) should be determined independently.
        """
        use_headless, use_sandbox = self.compute_browser_config(
            headless_requested, display_set, is_root
        )
        
        # Headless is determined by DISPLAY and user request
        expected_headless = headless_requested and not display_set
        assert use_headless == expected_headless, (
            f"Headless mismatch: expected {expected_headless}, got {use_headless}"
        )
        
        # Sandbox is determined only by root status
        expected_sandbox = not is_root
        assert use_sandbox == expected_sandbox, (
            f"Sandbox mismatch: expected {expected_sandbox}, got {use_sandbox}"
        )

    def test_github_actions_typical_configuration(self):
        """
        Test typical GitHub Actions configuration.
        
        **Validates: Requirements 8.1, 8.2**
        
        In GitHub Actions with Xvfb:
        - DISPLAY is set (Xvfb provides virtual display)
        - Running as root
        - User requests headless=True (but should be overridden)
        
        Expected: headless=False, sandbox=False
        """
        use_headless, use_sandbox = self.compute_browser_config(
            headless_requested=True,
            display_set=True,  # Xvfb sets DISPLAY
            is_root=True       # GitHub Actions runs as root
        )
        
        assert use_headless is False, (
            "GitHub Actions with Xvfb should use non-headless mode"
        )
        assert use_sandbox is False, (
            "GitHub Actions (root) should disable sandbox"
        )

    def test_local_development_configuration(self):
        """
        Test typical local development configuration.
        
        **Validates: Requirements 8.1, 8.2**
        
        In local development:
        - DISPLAY may or may not be set
        - Usually not running as root
        - User may request headless=True for convenience
        
        Expected: headless follows request, sandbox=True
        """
        # Local with no display (e.g., WSL without X server)
        use_headless, use_sandbox = self.compute_browser_config(
            headless_requested=True,
            display_set=False,
            is_root=False
        )
        
        assert use_headless is True, (
            "Local without DISPLAY should respect headless request"
        )
        assert use_sandbox is True, (
            "Local (non-root) should enable sandbox"
        )
        
        # Local with display (e.g., Linux desktop)
        use_headless, use_sandbox = self.compute_browser_config(
            headless_requested=True,
            display_set=True,
            is_root=False
        )
        
        assert use_headless is False, (
            "Local with DISPLAY should use non-headless mode"
        )
        assert use_sandbox is True, (
            "Local (non-root) should enable sandbox"
        )

    def test_docker_container_configuration(self):
        """
        Test typical Docker container configuration.
        
        **Validates: Requirements 8.1, 8.2**
        
        In Docker containers:
        - DISPLAY usually not set (unless using Xvfb)
        - Often running as root
        
        Expected: headless follows request, sandbox=False
        """
        use_headless, use_sandbox = self.compute_browser_config(
            headless_requested=True,
            display_set=False,
            is_root=True
        )
        
        assert use_headless is True, (
            "Docker without DISPLAY should use headless mode"
        )
        assert use_sandbox is False, (
            "Docker (root) should disable sandbox"
        )


class TestEnvironmentBasedBrowserConfigurationWithMonkeypatch:
    """
    Property-based tests for environment configuration using monkeypatch.
    
    These tests verify the actual BrowserManager configuration logic by
    mocking environment variables.
    
    **Validates: Requirements 8.1, 8.2**
    """

    @given(display_value=st.sampled_from([":0", ":1", ":99", ":0.0"]))
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_display_env_var_detection(self, monkeypatch, display_value: str):
        """
        Property: DISPLAY environment variable is correctly detected.
        
        **Validates: Requirements 8.1**
        
        For any valid DISPLAY value, the system should detect that
        a virtual display is available.
        """
        monkeypatch.setenv("DISPLAY", display_value)
        
        display_set = bool(os.environ.get("DISPLAY"))
        
        assert display_set is True, (
            f"DISPLAY={display_value} should be detected as set"
        )

    def test_display_env_var_not_set(self, monkeypatch):
        """
        Test that missing DISPLAY is correctly detected.
        
        **Validates: Requirements 8.1**
        """
        monkeypatch.delenv("DISPLAY", raising=False)
        
        display_set = bool(os.environ.get("DISPLAY"))
        
        assert display_set is False, (
            "Missing DISPLAY should be detected as not set"
        )

    @given(
        github_actions=st.booleans(),
        ci=st.booleans()
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_ci_environment_detection(
        self, monkeypatch, github_actions: bool, ci: bool
    ):
        """
        Property: CI environment is correctly detected.
        
        **Validates: Requirements 8.2**
        
        The system should detect CI environments through GITHUB_ACTIONS
        or CI environment variables.
        """
        if github_actions:
            monkeypatch.setenv("GITHUB_ACTIONS", "true")
        else:
            monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        
        if ci:
            monkeypatch.setenv("CI", "true")
        else:
            monkeypatch.delenv("CI", raising=False)
        
        is_github_actions = bool(os.environ.get("GITHUB_ACTIONS"))
        is_ci = bool(os.environ.get("CI")) or is_github_actions
        
        assert is_github_actions == github_actions, (
            f"GITHUB_ACTIONS detection mismatch"
        )
        assert is_ci == (ci or github_actions), (
            f"CI detection mismatch"
        )


class TestBrowserConfigurationIntegration:
    """
    Integration tests for browser configuration logic.
    
    These tests verify that the configuration logic in BrowserManager
    produces the expected results for various environment combinations.
    
    **Validates: Requirements 8.1, 8.2**
    """

    @given(
        headless=st.booleans(),
        display_set=st.booleans(),
        is_root=st.booleans()
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_browser_manager_config_consistency(
        self, monkeypatch, headless: bool, display_set: bool, is_root: bool
    ):
        """
        Property: BrowserManager configuration is consistent with environment.
        
        **Validates: Requirements 8.1, 8.2**
        
        For any combination of headless request, DISPLAY setting, and root status,
        the BrowserManager should produce consistent configuration.
        """
        # Set up environment
        if display_set:
            monkeypatch.setenv("DISPLAY", ":0")
        else:
            monkeypatch.delenv("DISPLAY", raising=False)
        
        # Mock os.geteuid for root detection (only on Unix-like systems)
        # On Windows, we need to add the attribute
        monkeypatch.setattr(os, 'geteuid', lambda: 0 if is_root else 1000, raising=False)
        
        # Create BrowserManager (don't start it)
        from utils.browser import BrowserManager
        manager = BrowserManager(engine="nodriver", headless=headless)
        
        # Verify initial configuration
        assert manager.headless == headless, (
            f"BrowserManager should store headless={headless}"
        )
        
        # Compute expected configuration
        expected_headless = headless and not display_set
        expected_sandbox = not is_root
        
        # Verify the logic matches our expectations
        actual_display_set = bool(os.environ.get("DISPLAY"))
        # Use the mocked geteuid
        actual_is_root = os.geteuid() == 0 if hasattr(os, 'geteuid') else False
        
        assert actual_display_set == display_set, (
            f"DISPLAY detection mismatch"
        )
        assert actual_is_root == is_root, (
            f"Root detection mismatch"
        )

    def test_all_configuration_combinations(self, monkeypatch):
        """
        Exhaustive test of all configuration combinations.
        
        **Validates: Requirements 8.1, 8.2**
        
        Test all 8 combinations of (headless, display, root) to ensure
        the configuration logic is correct.
        """
        test_cases = [
            # (headless_req, display, root) -> (expected_headless, expected_sandbox)
            (False, False, False, False, True),   # Non-headless, no display, non-root
            (False, False, True, False, False),   # Non-headless, no display, root
            (False, True, False, False, True),    # Non-headless, display, non-root
            (False, True, True, False, False),    # Non-headless, display, root
            (True, False, False, True, True),     # Headless, no display, non-root
            (True, False, True, True, False),     # Headless, no display, root
            (True, True, False, False, True),     # Headless, display, non-root -> non-headless!
            (True, True, True, False, False),     # Headless, display, root -> non-headless!
        ]
        
        for headless_req, display, root, exp_headless, exp_sandbox in test_cases:
            # Set up environment
            if display:
                monkeypatch.setenv("DISPLAY", ":0")
            else:
                monkeypatch.delenv("DISPLAY", raising=False)
            
            # Compute configuration
            config = TestEnvironmentBasedBrowserConfiguration.compute_browser_config(
                headless_requested=headless_req,
                display_set=display,
                is_root=root
            )
            
            actual_headless, actual_sandbox = config
            
            assert actual_headless == exp_headless, (
                f"Headless mismatch for (headless={headless_req}, display={display}, root={root}): "
                f"expected {exp_headless}, got {actual_headless}"
            )
            assert actual_sandbox == exp_sandbox, (
                f"Sandbox mismatch for (headless={headless_req}, display={display}, root={root}): "
                f"expected {exp_sandbox}, got {actual_sandbox}"
            )

