"""
main.py - HandSlide Controller entry point.

Flow
----
    App starts -> camera starts -> user clicks CHOOSE PRESENTATION FILE and picks
    a .pptx -> the file opens -> 3-2-1-GO -> slideshow starts (F5) -> gesture
    control ON -> hand gestures change slides.

Usage
-----
    python main.py          desktop app (camera + PowerPoint key control)
    python main.py --web    browser app (upload .pptx/.pdf, camera in the browser)
    python main.py --remote helper so the hosted web page can control PowerPoint on this PC

Threads
-------
Exactly ONE background thread (the "worker") reads the camera, runs MediaPipe,
classifies gestures and presses keys. The Tk window (main thread) only draws
the newest snapshot the worker published.
"""

from __future__ import annotations

import importlib
import os
import queue
import sys
import threading
import time
from collections import deque
from typing import Deque, Optional, Tuple


# --------------------------------------------------------------------------
# 1. Friendly message if a package is missing (runs BEFORE importing the rest)
# --------------------------------------------------------------------------
def _check_dependencies() -> None:
    required = (
        ("cv2", "opencv-python"),
        ("mediapipe", "mediapipe"),
        ("pyautogui", "pyautogui"),
        ("numpy", "numpy"),
        ("tkinter", "tkinter (re-run the Python installer and enable 'tcl/tk')"),
    )
    missing = []
    for module_name, package in required:
        try:
            importlib.import_module(module_name)
        except Exception:  # noqa: BLE001 - ImportError or a broken install
            missing.append(package)
    if missing:
        text = (
            "Missing required packages:\n  - " + "\n  - ".join(missing) +
            "\n\nInstall everything with:\n  pip install -r requirements.txt"
        )
        print(text)
        try:
            import tkinter
            from tkinter import messagebox

            root = tkinter.Tk()
            root.withdraw()
            messagebox.showerror("HandSlide Controller - missing packages", text)
            root.destroy()
        except Exception:  # noqa: BLE001
            pass
        sys.exit(1)


# `python main.py --web` starts the browser version (app.py) instead of the desktop
# window. It needs only flask + pymupdf, not OpenCV/MediaPipe/PyAutoGUI/Tk.
if "--web" in sys.argv:
    sys.argv.remove("--web")
    from App import main as _run_web

    _run_web()
    sys.exit(0)

# `python main.py --remote` starts the helper that lets the HOSTED web page control
# PowerPoint on this PC (needs only flask + pywin32, no camera packages).
if "--remote" in sys.argv:
    sys.argv.remove("--remote")
    from remote_bridge  import main as _run_remote

    _run_remote()
    sys.exit(0)

_check_dependencies()

import cv2  # noqa: E402

import config  # noqa: E402
from gesture_detector import (  # noqa: E402
    Gesture,
    GestureDetector,
    GestureDetectorError,
    GestureStabilizer,
    HandResult,
)
from powerpoint_controller import PowerPointController  # noqa: E402
from ui import MainWindow, UISnapshot  # noqa: E402

IS_WINDOWS = sys.platform == "win32"
VK_ESCAPE = 0x1B


class Application:
    """Owns the window, the worker thread and all shared state."""

    def __init__(self, headless: bool = False) -> None:
        self.ppt = PowerPointController()
        self.stabilizer = GestureStabilizer()
        self.headless = headless

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._control_enabled = threading.Event()

        self._snapshot = UISnapshot()
        self._frame_id = 0
        self._history: Deque[Tuple[str, str, str]] = deque(maxlen=5)
        self._status = "Camera starting... Click CHOOSE PRESENTATION FILE to begin."
        self._warning = ""
        self._warning_until = 0.0
        self._fatal_error = ""
        self._countdown_text = ""
        self._countdown_token = 0
        self._last_action_time = -1e9
        self._last_debug_gesture: Optional[str] = None
        self._esc_was_down = False
        self._selected_file = ""
        self._file_name = ""
        self._ui_queue: "queue.Queue[Tuple[str, int]]" = queue.Queue()  # worker -> Tk thread

        self.window = None
        if not headless:
            self.window = MainWindow(
                get_snapshot=self._get_snapshot,
                on_start=self.start_presentation,
                on_stop=self.stop_control,
                on_quit=self.quit,
                on_next=self.manual_next,
                on_previous=self.manual_previous,
                on_choose=self.choose_presentation,
            )
        self._worker = threading.Thread(target=self._worker_loop, name="camera-worker", daemon=True)

    # ------------------------------------------------------------ lifecycle
    def start_worker(self) -> None:
        if not self._worker.is_alive():
            self._worker.start()

    def run(self) -> None:
        self.start_worker()
        if self.window is None:
            while not self._stop_event.is_set():
                self._stop_event.wait(0.2)
            return

        self.window.root.after(50, self._poll_hotkeys)
        try:
            self.window.run()
        finally:
            self._shutdown()

    def quit(self) -> None:
        self._control_enabled.clear()
        self._stop_event.set()
        if self.window is not None:
            self.window.root.quit()  # ends mainloop -> run() calls _shutdown()
        else:
            self._shutdown()

    def _shutdown(self) -> None:
        self._stop_event.set()
        self._control_enabled.clear()
        if self._worker.is_alive():
            self._worker.join(timeout=3.0)  # worker releases the camera itself
        cv2.destroyAllWindows()
        try:
            self.window.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------- UI-thread callbacks
    def choose_presentation(self) -> None:
        """Main button: pick a file, open it, then run the countdown automatically."""
        if self._fatal_error:
            return
        from tkinter import filedialog  # imported here so `--web` mode needs no Tk
        path = filedialog.askopenfilename(
            parent=self.window.root,
            title="Choose the presentation you want to present",
            filetypes=config.PRESENTATION_FILE_TYPES,
        )
        if not path:
            return  # user cancelled the dialog
        path = os.path.normpath(path)
        with self._lock:
            self._selected_file = path
            self._file_name = os.path.basename(path)
        self._debug(f"File chosen: {path}")
        self.start_presentation()

    def start_presentation(self) -> None:
        """Open the chosen file (if any), then 3-2-1-GO, slideshow and gesture control."""
        if self._fatal_error:
            return
        self._countdown_token += 1
        token = self._countdown_token
        self._control_enabled.clear()
        self.stabilizer.reset()
        if not self._selected_file:
            self._set_status("Get ready...")
            self._countdown_step(config.COUNTDOWN_SECONDS, token)
            return
        self._set_status(f"Opening {self._file_name} ... please wait.")
        threading.Thread(
            target=self._open_file_then_countdown, args=(self._selected_file, token),
            name="open-file", daemon=True,
        ).start()

    def _open_file_then_countdown(self, path: str, token: int) -> None:
        """Runs in a helper thread so the window never freezes while PowerPoint loads."""
        cancelled = lambda: token != self._countdown_token  # noqa: E731
        ok, message = self.ppt.open_file(path)
        if not ok:
            self._set_warning(message)
            self._set_status("Could not open the file. Choose another one.")
            return
        if not self.ppt.wait_for_presentation(path, config.OPEN_FILE_TIMEOUT, cancelled):
            if not cancelled():
                self._set_warning("The presentation window did not appear.\nOpen it manually, then click START / RESTART.")
                self._set_status("Presentation did not open in time.")
            return
        if not cancelled():
            self._ui_queue.put(("countdown", token))  # Tk work must happen on the Tk thread

    def _countdown_step(self, remaining: int, token: int) -> None:
        if token != self._countdown_token:
            return  # cancelled by STOP or a newer START
        if remaining > 0:
            self._set_countdown(str(remaining))
            self.window.root.after(1000, lambda: self._countdown_step(remaining - 1, token))
            return

        self._set_countdown("GO!")
        ok, message = self.ppt.start_slideshow()
        if not ok:
            self._set_warning(message)
        self._last_action_time = time.monotonic()  # no gesture fires instantly
        self.stabilizer.reset()
        self._control_enabled.set()
        self._set_status("Gesture control ACTIVE - show your hand to the camera.")
        self._debug("Control ENABLED (START button)")
        self.window.root.after(800, lambda: self._set_countdown(""))

    def stop_control(self) -> None:
        """STOP button / ESC: disable gesture commands (webcam keeps running)."""
        self._countdown_token += 1  # cancels a running countdown
        self._set_countdown("")
        was_enabled = self._control_enabled.is_set()
        self._control_enabled.clear()
        self.stabilizer.reset()
        self._set_status("Gesture control disabled. Click START (or show a thumbs up) to resume.")
        if was_enabled:
            self._debug("Control DISABLED")

    def manual_next(self) -> None:
        ok, message = self.ppt.next_slide(focus_first=True)
        self._manual_result(ok, message, "Keyboard →", "NEXT")

    def manual_previous(self) -> None:
        ok, message = self.ppt.previous_slide(focus_first=True)
        self._manual_result(ok, message, "Keyboard ←", "PREVIOUS")

    def _manual_result(self, ok: bool, message: str, label: str, action: str) -> None:
        if ok:
            self._add_history(label, config.ACTION_LABELS[action])
        else:
            self._set_warning(message)

    def _poll_hotkeys(self) -> None:
        """Global ESC emergency stop (Windows): works even while PowerPoint has focus."""
        if IS_WINDOWS:
            import ctypes

            down = bool(ctypes.windll.user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)
            if down and not self._esc_was_down and self._control_enabled.is_set():
                self.stop_control()
                self._set_warning("Emergency stop (ESC): gesture control disabled.")
            self._esc_was_down = down
        self._drain_ui_queue()
        self.window.root.after(50, self._poll_hotkeys)

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                kind, token = self._ui_queue.get_nowait()
            except queue.Empty:
                return
            if kind == "countdown" and token == self._countdown_token:
                self._set_status("Get ready...")
                self._countdown_step(config.COUNTDOWN_SECONDS, token)

    # ------------------------------------------------------- shared state
    def _get_snapshot(self) -> UISnapshot:
        with self._lock:
            return self._snapshot

    def _set_status(self, text: str) -> None:
        with self._lock:
            self._status = text

    def _set_warning(self, text: str) -> None:
        with self._lock:
            self._warning = text
            self._warning_until = time.monotonic() + config.WARNING_DISPLAY_SECONDS

    def _set_countdown(self, text: str) -> None:
        with self._lock:
            self._countdown_text = text

    def _add_history(self, gesture_text: str, action_text: str) -> None:
        with self._lock:
            self._history.appendleft((time.strftime("%H:%M:%S"), gesture_text, action_text))

    def _debug(self, text: str) -> None:
        if config.DEBUG:
            print(f"[DEBUG] {text}", flush=True)

    def _publish(self, **fields) -> None:
        """Build a new snapshot from the worker's latest results."""
        with self._lock:
            if fields.get("frame_bgr") is not None:
                self._frame_id += 1
            warning = self._warning if time.monotonic() < self._warning_until else ""
            self._snapshot = UISnapshot(
                frame_id=self._frame_id,
                fatal_error=self._fatal_error,
                control_enabled=self._control_enabled.is_set(),
                status=self._status,
                warning=warning,
                file_name=self._file_name,
                history=list(self._history),
                **fields,
            )

    # ------------------------------------------------------ worker thread
    def _open_camera(self) -> Optional["cv2.VideoCapture"]:
        backend = cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_ANY  # DSHOW opens faster
        cap = cv2.VideoCapture(config.CAMERA_INDEX, backend)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, config.TARGET_FPS)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # always the freshest frame
        return cap

    def _worker_loop(self) -> None:
        try:
            detector = GestureDetector()
        except GestureDetectorError as exc:
            self._fatal_error = str(exc)  # show the REAL reason in the window
            print(f"[ERROR] {exc}", flush=True)
            self._publish(camera_ok=False, camera_message=self._fatal_error)
            return

        cap = None
        failed_reads = 0
        fps = 0.0
        last_time = time.monotonic()
        try:
            while not self._stop_event.is_set():
                # ---- (re)connect to the camera
                if cap is None:
                    cap = self._open_camera()
                    if cap is None:
                        self._publish(
                            camera_ok=False,
                            camera_message="❌ Camera not available\nPlease check your webcam.",
                        )
                        self._stop_event.wait(1.5)
                        continue
                    failed_reads = 0

                ok, frame = cap.read()
                if not ok or frame is None:
                    failed_reads += 1
                    if failed_reads > 10:  # camera unplugged / taken by another app
                        cap.release()
                        cap = None
                        self._publish(
                            camera_ok=False,
                            camera_message="❌ Camera not available\nUnable to access camera.",
                        )
                    else:
                        time.sleep(0.02)
                    continue
                failed_reads = 0

                if frame.shape[1] != config.FRAME_WIDTH or frame.shape[0] != config.FRAME_HEIGHT:
                    frame = cv2.resize(frame, (config.FRAME_WIDTH, config.FRAME_HEIGHT))
                frame = cv2.flip(frame, 1)  # mirror view: feels natural, and left/right match

                result = detector.process(frame)
                now = time.monotonic()

                action_label, hold_progress, cooldown_remaining = self._handle_gesture(result, now)

                detector.draw(frame, result)
                fps = 0.9 * fps + 0.1 / max(now - last_time, 1e-6) if fps else 1.0 / max(now - last_time, 1e-6)
                last_time = now
                self._draw_overlay(frame, result, action_label, fps, hold_progress)

                self._publish(
                    frame_bgr=frame,
                    camera_ok=True,
                    camera_message="",
                    gesture=result.gesture,
                    confidence=result.confidence,
                    action=action_label,
                    fps=fps,
                    cooldown_remaining=cooldown_remaining,
                    hold_progress=hold_progress,
                )
        finally:
            if cap is not None:
                cap.release()  # always give the webcam back
            detector.close()

    # -------------------------------------------------- gesture -> action
    def _handle_gesture(self, result: HandResult, now: float) -> Tuple[str, float, float]:
        """Returns (action text for display, hold progress, cooldown remaining)."""
        gesture = result.gesture
        enabled = self._control_enabled.is_set()
        cooldown_remaining = max(0.0, config.GESTURE_COOLDOWN - (now - self._last_action_time))
        ready = cooldown_remaining <= 0.0

        # While control is OFF, only THUMBS_UP (if allowed) is listened to.
        thumbs_enable = (
            not enabled and config.ALLOW_THUMBS_UP_ENABLE and gesture == Gesture.THUMBS_UP
        )
        considered = gesture if (enabled or thumbs_enable) else Gesture.NONE

        fired = self.stabilizer.update(considered, now, ready)
        if fired:
            self._execute(fired, now)
            enabled = self._control_enabled.is_set()
            cooldown_remaining = max(0.0, config.GESTURE_COOLDOWN - (now - self._last_action_time))

        # What to show as "Action:"
        if gesture in (Gesture.NONE, Gesture.UNKNOWN):
            action_label = "—"
        elif not enabled and not thumbs_enable:
            action_label = "Control disabled"
        else:
            action_label = config.ACTION_LABELS.get(config.GESTURE_ACTIONS.get(gesture, "NONE"), "—")

        if gesture != self._last_debug_gesture:
            self._last_debug_gesture = gesture
            if result.hand_detected:
                self._debug(
                    f"Gesture: {gesture} | Action: {config.GESTURE_ACTIONS.get(gesture, 'NONE')} | "
                    f"Cooldown: {'READY' if ready else f'{cooldown_remaining:.1f}s'} | "
                    f"Confidence: {result.confidence:.2f}"
                )
        return action_label, self.stabilizer.progress, cooldown_remaining

    def _execute(self, gesture: str, now: float) -> None:
        action = config.GESTURE_ACTIONS.get(gesture, "NONE")
        ok, message = True, ""

        if action == "NEXT":
            ok, message = self.ppt.next_slide()
        elif action == "PREVIOUS":
            ok, message = self.ppt.previous_slide()
        elif action == "ENABLE":
            if self._control_enabled.is_set():
                return
            self._control_enabled.set()
            self._set_status("Gesture control ACTIVE (thumbs up).")
        else:
            return  # NONE (e.g. fist): deliberately do nothing

        self._last_action_time = now  # start the cooldown
        emoji, name = config.GESTURE_INFO.get(gesture, ("", gesture))
        if ok:
            self._add_history(f"{emoji} {name.title()}", config.ACTION_LABELS[action].title())
        else:
            self._set_warning(message)
        self._debug(
            f"FIRED {gesture} -> {action} ({'ok' if ok else 'blocked: ' + message.splitlines()[0]}) "
            f"| Cooldown: {config.GESTURE_COOLDOWN}s started"
        )

    # ----------------------------------------------------------- overlay
    def _draw_overlay(self, frame, result: HandResult, action_label: str, fps: float, hold: float) -> None:
        """Draw status text onto the camera image."""
        height, width = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX

        # Semi-transparent panel behind the text
        panel = frame[0:112, 0:290].copy()
        cv2.rectangle(frame, (0, 0), (290, 112), (20, 24, 36), -1)
        cv2.addWeighted(panel, 0.35, frame[0:112, 0:290], 0.65, 0, frame[0:112, 0:290])

        if result.hand_detected:
            _, name = config.GESTURE_INFO.get(result.gesture, ("", result.gesture))
            lines = [
                ("Hand detected", (80, 220, 120)),
                (f"Gesture: {name}", (255, 255, 255)),
                (f"Confidence: {result.confidence * 100:.0f}%" if result.confidence > 0 else "Confidence: --",
                 (255, 255, 255)),
                (f"Action: {action_label}", (255, 170, 80)),
            ]
        else:
            lines = [
                ("No hand", (150, 150, 255)),
                ("Gesture: None", (255, 255, 255)),
                ("Status: Waiting for hand...", (200, 200, 200)),
            ]
        for index, (text, colour) in enumerate(lines):
            cv2.putText(frame, text, (10, 26 + index * 26), font, 0.6, colour, 1, cv2.LINE_AA)

        cv2.putText(frame, f"FPS: {fps:.0f}", (width - 100, 26), font, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        # Hold-progress bar along the bottom edge
        if hold > 0:
            cv2.rectangle(frame, (0, height - 8), (int(width * hold), height), (255, 140, 60), -1)

        # Big countdown text in the middle
        with self._lock:
            countdown = self._countdown_text
        if countdown:
            scale = 5.0 if countdown != "GO!" else 4.0
            (text_w, text_h), _ = cv2.getTextSize(countdown, font, scale, 8)
            origin = ((width - text_w) // 2, (height + text_h) // 2)
            cv2.putText(frame, countdown, origin, font, scale, (0, 0, 0), 14, cv2.LINE_AA)
            cv2.putText(frame, countdown, origin, font, scale, (80, 230, 120), 8, cv2.LINE_AA)


def main() -> None:
    Application().run()


if __name__ == "__main__":
    main()