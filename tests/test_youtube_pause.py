"""YouTube browser media controls must be state-aware and avoid toggles."""
import asyncio
import unittest
from enum import IntEnum
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from actions.youtube_video import youtube_video
from core.media_control import (
    _pause_browser_session,
    _resume_browser_session,
    pause_browser_media,
    resume_browser_media,
)


class Status(IntEnum):
    PLAYING = 4
    PAUSED = 5
    STOPPED = 3


def session(app="chrome.exe", state=Status.PLAYING, enabled=True, accepted=True):
    async def pause():
        if accepted:
            item.state = Status.PAUSED
        return accepted

    async def play():
        if accepted:
            item.state = Status.PLAYING
        return accepted

    item = SimpleNamespace(source_app_user_model_id=app, state=state)
    item.get_playback_info = lambda: SimpleNamespace(
        playback_status=item.state,
        controls=SimpleNamespace(
            is_pause_enabled=enabled,
            is_play_enabled=enabled,
        ),
    )
    item.try_pause_async = AsyncMock(side_effect=pause)
    item.try_play_async = AsyncMock(side_effect=play)
    return item


def manager(current, sessions):
    return SimpleNamespace(
        get_current_session=lambda: current,
        get_sessions=lambda: sessions,
    )


class BrowserPauseTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_stop_never_resumes(self):
        browser = session()
        source = manager(browser, [browser])
        self.assertEqual(await _pause_browser_session(source, Status),
                         "Paused the browser music.")
        self.assertEqual(await _pause_browser_session(source, Status),
                         "Browser music is already paused.")
        browser.try_pause_async.assert_awaited_once()

    async def test_background_browser_does_not_pause_spotify(self):
        spotify, browser = session("Spotify.exe"), session("msedge.exe")
        await _pause_browser_session(manager(spotify, [spotify, browser]), Status)
        browser.try_pause_async.assert_awaited_once()
        spotify.try_pause_async.assert_not_awaited()

    async def test_current_browser_is_selected(self):
        chrome, firefox = session(), session("firefox.exe")
        await _pause_browser_session(manager(firefox, [chrome, firefox]), Status)
        firefox.try_pause_async.assert_awaited_once()
        chrome.try_pause_async.assert_not_awaited()

    async def test_ambiguous_browsers_are_left_alone(self):
        chrome, firefox = session(), session("firefox.exe")
        result = await _pause_browser_session(manager(None, [chrome, firefox]), Status)
        self.assertIn("Several browsers", result)
        chrome.try_pause_async.assert_not_awaited()
        firefox.try_pause_async.assert_not_awaited()

    async def test_no_browser_does_not_touch_other_media(self):
        spotify = session("Spotify.exe")
        result = await _pause_browser_session(manager(spotify, [spotify]), Status)
        self.assertIn("No browser media session", result)
        spotify.try_pause_async.assert_not_awaited()

    async def test_pause_rejection_is_not_reported_as_success(self):
        browser = session(accepted=False)
        result = await _pause_browser_session(manager(browser, [browser]), Status)
        self.assertIn("could not pause", result)

    async def test_disabled_pause_is_not_sent(self):
        browser = session(enabled=False)
        result = await _pause_browser_session(manager(browser, [browser]), Status)
        self.assertIn("not accepting pause", result)
        browser.try_pause_async.assert_not_awaited()

    async def test_stopped_music_is_left_stopped(self):
        browser = session(state=Status.STOPPED)
        await _pause_browser_session(manager(browser, [browser]), Status)
        browser.try_pause_async.assert_not_awaited()


class BrowserResumeTests(unittest.IsolatedAsyncioTestCase):
    async def test_paused_browser_is_resumed(self):
        browser = session(state=Status.PAUSED)
        result = await _resume_browser_session(manager(browser, [browser]), Status)
        self.assertEqual(result, "Resumed the browser music.")
        browser.try_play_async.assert_awaited_once()

    async def test_repeated_resume_never_pauses(self):
        browser = session(state=Status.PAUSED)
        source = manager(browser, [browser])
        await _resume_browser_session(source, Status)
        result = await _resume_browser_session(source, Status)
        self.assertEqual(result, "Browser music is already playing.")
        browser.try_play_async.assert_awaited_once()

    async def test_resume_does_not_touch_spotify(self):
        spotify = session("Spotify.exe", state=Status.PAUSED)
        browser = session("msedge.exe", state=Status.PAUSED)
        await _resume_browser_session(manager(spotify, [spotify, browser]), Status)
        browser.try_play_async.assert_awaited_once()
        spotify.try_play_async.assert_not_awaited()

    async def test_disabled_resume_is_not_sent(self):
        browser = session(state=Status.PAUSED, enabled=False)
        result = await _resume_browser_session(manager(browser, [browser]), Status)
        self.assertIn("not accepting resume", result)
        browser.try_play_async.assert_not_awaited()


class YouTubeActionTests(unittest.TestCase):
    def test_stop_and_pause_need_no_query_or_url(self):
        for action in ("stop", "pause"):
            with self.subTest(action=action), patch(
                "core.media_control.pause_browser_media", return_value="Paused."
            ) as pause, patch("actions.youtube_video._open_url") as open_url:
                self.assertEqual(youtube_video({"action": action}), "Paused.")
                pause.assert_called_once_with()
                open_url.assert_not_called()

    def test_resume_and_unpause_need_no_query_or_url(self):
        for action in ("resume", "unpause"):
            with self.subTest(action=action), patch(
                "core.media_control.resume_browser_media", return_value="Resumed."
            ) as resume, patch("actions.youtube_video._open_url") as open_url:
                self.assertEqual(youtube_video({"action": action}), "Resumed.")
                resume.assert_called_once_with()
                open_url.assert_not_called()

    def test_missing_dependency_has_install_instructions(self):
        with patch("core.media_control.sys.platform", "win32"), patch(
            "core.media_control._pause_windows_browser", side_effect=ImportError
        ):
            self.assertIn("pip install", pause_browser_media())

    def test_timeout_is_reported(self):
        with patch("core.media_control.sys.platform", "win32"), patch(
            "core.media_control._pause_windows_browser", side_effect=asyncio.TimeoutError
        ):
            self.assertIn("did not respond", pause_browser_media())

    def test_resume_timeout_is_reported(self):
        with patch("core.media_control.sys.platform", "win32"), patch(
            "core.media_control._resume_windows_browser", side_effect=asyncio.TimeoutError
        ):
            self.assertIn("did not respond", resume_browser_media())


if __name__ == "__main__":
    unittest.main()
