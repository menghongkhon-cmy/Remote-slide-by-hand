"""
powerpoint_controller.py - sends keyboard commands to PowerPoint.

The project never opens or edits .pptx files. It only "presses keys" with
PyAutoGUI, exactly as if you pressed them yourself:

    NEXT      -> RIGHT ARROW
    PREVIOUS  -> LEFT ARROW
    START     -> F5

On Windows it also checks (with the standard ctypes module, no extra package)
which window is in front, and can bring the PowerPoint window to the front.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import List, Tuple

import pyautogui

import config

IS_WINDOWS = sys.platform == "win32"

# Do not add PyAutoGUI's default 0.1 s pause after each key press.
pyautogui.PAUSE = 0.0

NOT_ACTIVE_MESSAGE = (
    "PowerPoint may not be the active window.\nPlease click your presentation."
)
NOT_FOUND_MESSAGE = "PowerPoint window not found.\nOpen your presentation first."

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_ENUM_PROC, wintypes.LPARAM]

    def _window_title(hwnd) -> str:
        length = _user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def _foreground_title() -> str:
        return _window_title(_user32.GetForegroundWindow())

    def _find_presentation_windows() -> List[Tuple[int, str]]:
        found: List[Tuple[int, str]] = []

        def callback(hwnd, _lparam):
            if _user32.IsWindowVisible(hwnd):
                title = _window_title(hwnd)
                if any(k in title for k in config.PRESENTATION_WINDOW_KEYWORDS):
                    found.append((hwnd, title))
            return True

        _user32.EnumWindows(_ENUM_PROC(callback), 0)
        return found

    def _bring_to_front(hwnd) -> None:
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        # Tapping ALT lets SetForegroundWindow succeed on modern Windows.
        _user32.keybd_event(0x12, 0, 0, 0)
        _user32.SetForegroundWindow(hwnd)
        _user32.keybd_event(0x12, 0, 2, 0)


class PowerPointController:
    """Slide control through keyboard shortcuts. Every method returns (ok, message)."""

    # -- window helpers ------------------------------------------------------
    def is_powerpoint_active(self) -> bool:
        """True if a presentation window is in front (always True off Windows)."""
        if not IS_WINDOWS:
            return True
        title = _foreground_title()
        return any(k in title for k in config.PRESENTATION_WINDOW_KEYWORDS)

    def focus_powerpoint(self) -> bool:
        """Bring the presentation window to the front. Returns False if not found."""
        if not IS_WINDOWS:
            return True
        windows = _find_presentation_windows()
        if not windows:
            return False
        # Prefer a running slideshow window over the editor window.
        windows.sort(key=lambda item: "Slide Show" not in item[1])
        _bring_to_front(windows[0][0])
        time.sleep(0.4)
        return True

    # -- key sending ---------------------------------------------------------
    @staticmethod
    def _press(key: str) -> Tuple[bool, str]:
        try:
            pyautogui.press(key)
            return True, ""
        except pyautogui.FailSafeException:
            return False, "PyAutoGUI fail-safe triggered (mouse in a screen corner)."
        except Exception as exc:  # noqa: BLE001
            return False, f"Could not send key '{key}': {exc}"

    def _send(self, key: str, focus_first: bool) -> Tuple[bool, str]:
        if focus_first:
            if not self.focus_powerpoint():
                return False, NOT_FOUND_MESSAGE
        elif config.REQUIRE_POWERPOINT_ACTIVE and not self.is_powerpoint_active():
            return False, NOT_ACTIVE_MESSAGE
        return self._press(key)

    def next_slide(self, focus_first: bool = False) -> Tuple[bool, str]:
        return self._send(config.NEXT_KEY, focus_first)

    def previous_slide(self, focus_first: bool = False) -> Tuple[bool, str]:
        return self._send(config.PREVIOUS_KEY, focus_first)

    def start_slideshow(self) -> Tuple[bool, str]:
        """Bring PowerPoint forward and press F5 (unless a show is already running)."""
        if not self.focus_powerpoint():
            return False, NOT_FOUND_MESSAGE
        if IS_WINDOWS and "Slide Show" in _foreground_title():
            return True, "Slideshow already running."
        ok, message = self._press(config.START_SLIDESHOW_KEY)
        return ok, message or "Slideshow started."

    # -- open a file chosen by the user --------------------------------------
    def open_file(self, path: str) -> Tuple[bool, str]:
        """Open a presentation file with the program Windows associates with it."""
        if not os.path.isfile(path):
            return False, f"File not found:\n{path}"
        try:
            if IS_WINDOWS:
                os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # noqa: BLE001
            return False, f"Could not open the file: {exc}"
        return True, ""

    def wait_for_presentation(self, path: str, timeout: float, cancelled=lambda: False) -> bool:
        """Wait until a window for this file shows up (Windows). True when found."""
        if not IS_WINDOWS:
            time.sleep(3.0)
            return True
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not cancelled():
            for _hwnd, title in _find_presentation_windows():
                if stem in title.lower():
                    time.sleep(1.5)  # let PowerPoint finish loading
                    return True
            time.sleep(0.4)
        return False