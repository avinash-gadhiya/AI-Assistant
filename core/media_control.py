"""Control browser media through Windows, including background YouTube tabs.

Use explicit pause and play requests, never a play/pause toggle: a repeated stop
command must not restart a song, and a repeated resume must not pause one. These
functions are called on an action worker, not on the live audio loop.
"""
from __future__ import annotations

import asyncio
import sys


_BROWSER_IDS = (
    "chrome", "chromium", "msedge", "microsoftedge", "firefox",
    "brave", "opera", "vivaldi", "youtube",
)


def _is_browser(session) -> bool:
    app_id = session.source_app_user_model_id.lower()
    return any(name in app_id for name in _BROWSER_IDS)


def _select_browser_session(manager):
    # Windows exposes the browser's media session, not its tab URL. Prefer its
    # current session; if another app is current, accept a single browser session
    # only. Never send a global media key that might affect Spotify or another app.
    current = manager.get_current_session()
    if current is not None and _is_browser(current):
        return current, None

    browsers = [s for s in manager.get_sessions() if _is_browser(s)]
    if not browsers:
        return None, "No browser media session was found. Start the YouTube song first."
    if len(browsers) != 1:
        return None, "Several browsers have media open. Select the YouTube media session and try again."
    return browsers[0], None


async def _pause_browser_session(manager, playback_status) -> str:
    target, error = _select_browser_session(manager)
    if error:
        return error

    info = target.get_playback_info()
    if info.playback_status in (playback_status.PAUSED, playback_status.STOPPED):
        return "Browser music is already paused."
    if not info.controls.is_pause_enabled:
        return "The browser is not accepting pause commands. Pause YouTube in its tab."
    if await target.try_pause_async():
        return "Paused the browser music."
    return "The browser could not pause the music."


async def _resume_browser_session(manager, playback_status) -> str:
    target, error = _select_browser_session(manager)
    if error:
        return error

    info = target.get_playback_info()
    if info.playback_status == playback_status.PLAYING:
        return "Browser music is already playing."
    if not info.controls.is_play_enabled:
        return "The browser is not accepting resume commands. Resume YouTube in its tab."
    if await target.try_play_async():
        return "Resumed the browser music."
    return "The browser could not resume the music."


async def _pause_windows_browser() -> str:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
    )

    manager = await MediaManager.request_async()
    return await _pause_browser_session(manager, PlaybackStatus)


async def _resume_windows_browser() -> str:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
    )

    manager = await MediaManager.request_async()
    return await _resume_browser_session(manager, PlaybackStatus)


def pause_browser_media() -> str:
    """Synchronous entry point for the action executor; bounded to five seconds."""
    if sys.platform != "win32":
        return "Background YouTube pause is currently supported on Windows only."

    async def pause():
        return await asyncio.wait_for(_pause_windows_browser(), timeout=5.0)

    try:
        return asyncio.run(pause())
    except ImportError:
        return (
            "YouTube pause needs the Windows media package. Install it with: "
            'python -m pip install "winrt-Windows.Media.Control>=3.2,<4" '
            '"winrt-Windows.Foundation>=3.2,<4" '
            '"winrt-Windows.Foundation.Collections>=3.2,<4"'
        )
    except asyncio.TimeoutError:
        return "The browser did not respond to the pause request in time."
    except Exception as exc:
        return f"Could not pause browser music: {exc}"


def resume_browser_media() -> str:
    """Synchronous entry point for the action executor; bounded to five seconds."""
    if sys.platform != "win32":
        return "Background YouTube resume is currently supported on Windows only."

    async def resume():
        return await asyncio.wait_for(_resume_windows_browser(), timeout=5.0)

    try:
        return asyncio.run(resume())
    except ImportError:
        return (
            "YouTube resume needs the Windows media package. Install it with: "
            'python -m pip install "winrt-Windows.Media.Control>=3.2,<4" '
            '"winrt-Windows.Foundation>=3.2,<4" '
            '"winrt-Windows.Foundation.Collections>=3.2,<4"'
        )
    except asyncio.TimeoutError:
        return "The browser did not respond to the resume request in time."
    except Exception as exc:
        return f"Could not resume browser music: {exc}"
