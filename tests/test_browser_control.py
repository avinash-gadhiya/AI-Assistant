"""Regression tests for browser-session recovery and social-post actions."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from actions.browser_control import _BrowserSession, _normalize_url, browser_control


class BrowserNavigationTests(unittest.TestCase):
    def test_spoken_linkedin_name_is_normalized(self):
        self.assertEqual(_normalize_url("linkdent"), "https://linkedin.com")

    def test_interactive_navigation_uses_controlled_session_immediately(self):
        session = SimpleNamespace(
            go_to=MagicMock(return_value=object()),
            run=MagicMock(return_value="Opened: https://linkedin.com"),
        )
        with patch("actions.browser_control._registry") as registry, patch(
            "actions.browser_control._open_native"
        ) as open_native:
            registry.has.return_value = False
            registry.get.return_value = session
            result = browser_control({
                "action": "go_to",
                "browser": "chrome",
                "url": "linkdent",
                "interactive": True,
            })

        self.assertIn("Opened", result)
        registry.get.assert_called_once_with("chrome")
        session.go_to.assert_called_once_with("linkdent")
        open_native.assert_not_called()


class BrowserSessionRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_dead_context_is_discarded_before_page_is_requested(self):
        browser = SimpleNamespace(is_connected=lambda: False)
        stale_context = SimpleNamespace(
            browser=browser,
            close=AsyncMock(),
            new_page=AsyncMock(side_effect=RuntimeError(
                "BrowserContext.new_page: Target page, context or browser has been closed"
            )),
        )
        fresh_page = SimpleNamespace(is_closed=lambda: False)
        fresh_context = SimpleNamespace(
            browser=SimpleNamespace(is_connected=lambda: True),
            pages=[fresh_page],
        )

        session = _BrowserSession.__new__(_BrowserSession)
        session.browser_name = "chrome"
        session._context = stale_context
        session._page = None
        session._pw = object()

        launches = 0

        async def launch():
            nonlocal launches
            launches += 1
            if launches == 2:
                session._context = fresh_context
                session._page = fresh_page

        session._launch = AsyncMock(side_effect=launch)

        self.assertIs(await session._get_page(), fresh_page)
        stale_context.close.assert_awaited_once()
        self.assertEqual(session._launch.await_count, 2)


class SocialLikeTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _session_for(url: str):
        button = SimpleNamespace(
            is_visible=AsyncMock(return_value=True),
            scroll_into_view_if_needed=AsyncMock(),
            click=AsyncMock(),
        )
        matches = MagicMock()
        matches.count = AsyncMock(return_value=1)
        matches.nth.return_value = button
        page = SimpleNamespace(url=url, locator=MagicMock(return_value=matches))

        session = _BrowserSession.__new__(_BrowserSession)
        session._get_page = AsyncMock(return_value=page)
        return session, page, button

    async def test_linkedin_like_uses_unliked_button(self):
        session, page, button = self._session_for("https://www.linkedin.com/feed/")
        result = await session.like_post()
        self.assertIn("Liked", result)
        self.assertIn("LinkedIn", result)
        self.assertIn('aria-label^="Like"', page.locator.call_args.args[0])
        button.click.assert_awaited_once()

    async def test_x_like_uses_non_toggle_like_control(self):
        session, page, button = self._session_for("https://x.com/home")
        result = await session.like_post()
        self.assertIn("Liked", result)
        page.locator.assert_called_once_with('article [data-testid="like"]')
        button.click.assert_awaited_once()

    async def test_like_is_rejected_on_other_sites(self):
        session, page, _button = self._session_for("https://example.com/")
        result = await session.like_post()
        self.assertIn("Open LinkedIn or X", result)
        page.locator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
