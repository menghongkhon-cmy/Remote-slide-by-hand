"""
ui.py - the Tkinter window.

The UI knows NOTHING about MediaPipe or PowerPoint. It just:
  * asks for the latest UISnapshot ~60 times a second and draws it, and
  * calls the callbacks (start / stop / quit / next / previous) you give it.
"""

from __future__ import annotations

import os
import tkinter as tk
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

import config

FONT = "Segoe UI"
EMOJI_FONT = "Segoe UI Emoji"
MONO = "Consolas"


@dataclass
class UISnapshot:
    """Everything the UI needs to draw one moment in time."""

    frame_bgr: Any = None                 # numpy image (already has overlays)
    frame_id: int = 0                     # changes whenever frame_bgr is new
    camera_ok: bool = False
    camera_message: str = "Starting camera..."
    fatal_error: str = ""                 # e.g. MediaPipe failed to start
    gesture: str = "NONE"
    confidence: float = 0.0
    action: str = "—"
    fps: float = 0.0
    control_enabled: bool = False
    cooldown_remaining: float = 0.0
    hold_progress: float = 0.0
    status: str = ""
    warning: str = ""
    file_name: str = ""                   # presentation chosen by the user
    history: List[Tuple[str, str, str]] = field(default_factory=list)


class MainWindow:
    def __init__(
        self,
        get_snapshot: Callable[[], UISnapshot],
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_quit: Callable[[], None],
        on_next: Callable[[], None],
        on_previous: Callable[[], None],
        on_choose: Callable[[], None],
    ) -> None:
        self._get_snapshot = get_snapshot
        self._last_frame_id = -1
        self._photo: Optional[tk.PhotoImage] = None  # keep a reference!

        self.root = tk.Tk()
        self.root.title(f"{config.APP_NAME} - {config.APP_SUBTITLE}")
        self.root.configure(bg=config.COLORS["bg"])
        self.root.geometry("1120x780")
        self.root.minsize(1040, 740)
        self._set_icon()

        self._build(on_start, on_stop, on_next, on_previous, on_choose)

        # Keyboard fallback / safety keys (work while this window is focused).
        self.root.bind("<Escape>", lambda _e: on_stop())
        self.root.bind("<q>", lambda _e: on_quit())
        self.root.bind("<Q>", lambda _e: on_quit())
        self.root.bind("<Control-o>", lambda _e: on_choose())
        self.root.bind("<Right>", lambda _e: on_next())
        self.root.bind("<Left>", lambda _e: on_previous())
        self.root.protocol("WM_DELETE_WINDOW", on_quit)

    # ------------------------------------------------------------------ build
    def _set_icon(self) -> None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
        try:
            self._icon = tk.PhotoImage(file=path)
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass  # icon is optional

    def _card(self, parent: tk.Misc, **pack_kwargs) -> tk.Frame:
        """A 'rounded-looking' panel: dark card with a subtle border."""
        c = config.COLORS
        card = tk.Frame(
            parent, bg=c["card"], highlightthickness=1,
            highlightbackground=c["card_border"], highlightcolor=c["card_border"],
        )
        card.pack(**pack_kwargs)
        return card

    def _button(self, parent, text, bg, hover, command) -> tk.Button:
        button = tk.Button(
            parent, text=text, command=command, bg=bg, fg="white",
            activebackground=hover, activeforeground="white", relief="flat", bd=0,
            padx=16, pady=10, font=(FONT, 12, "bold"), cursor="hand2",
        )
        button.bind("<Enter>", lambda _e: button.configure(bg=hover))
        button.bind("<Leave>", lambda _e: button.configure(bg=bg))
        return button

    def _build(self, on_start, on_stop, on_next, on_previous, on_choose) -> None:
        c = config.COLORS
        root = self.root

        # ---- header
        header = tk.Frame(root, bg=c["bg"])
        header.pack(fill="x", pady=(16, 8))
        tk.Label(
            header, text=f"🖐️ {config.APP_NAME.upper()}", bg=c["bg"], fg=c["text"],
            font=(FONT, 24, "bold"),
        ).pack()
        tk.Label(
            header, text=config.APP_SUBTITLE, bg=c["bg"], fg=c["muted"], font=(FONT, 12),
        ).pack()

        body = tk.Frame(root, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=20)

        # ---- left column: camera
        left = self._card(body, side="left", fill="y", padx=(0, 12))
        top_row = tk.Frame(left, bg=c["card"])
        top_row.pack(fill="x", padx=14, pady=(12, 6))
        self.camera_label = tk.Label(
            top_row, text="🔴 CAMERA DISCONNECTED", bg=c["card"], fg=c["danger"],
            font=(FONT, 11, "bold"),
        )
        self.camera_label.pack(side="left")
        self.fps_label = tk.Label(
            top_row, text="FPS: --", bg=c["card"], fg=c["muted"], font=(FONT, 11, "bold"),
        )
        self.fps_label.pack(side="right")

        video_box = tk.Frame(
            left, bg="black", width=config.FRAME_WIDTH, height=config.FRAME_HEIGHT
        )
        video_box.pack(padx=14, pady=(0, 14))
        video_box.pack_propagate(False)
        self.video_label = tk.Label(
            video_box, bg="black", fg=c["muted"], font=(FONT, 16),
            text="Starting camera...", justify="center",
        )
        self.video_label.pack(fill="both", expand=True)

        # ---- right column
        right = tk.Frame(body, bg=c["bg"])
        right.pack(side="left", fill="both", expand=True)

        # Gesture indicator
        gesture_card = self._card(right, fill="x", pady=(0, 10))
        self.gesture_emoji = tk.Label(
            gesture_card, text="…", bg=c["card"], fg=c["text"], font=(EMOJI_FONT, 60),
        )
        self.gesture_emoji.pack(pady=(10, 0))
        self.gesture_name = tk.Label(
            gesture_card, text="NONE", bg=c["card"], fg=c["text"], font=(FONT, 22, "bold"),
        )
        self.gesture_name.pack()
        self.gesture_conf = tk.Label(
            gesture_card, text="Confidence: --", bg=c["card"], fg=c["muted"], font=(FONT, 11),
        )
        self.gesture_conf.pack()
        self.action_label = tk.Label(
            gesture_card, text="Action: —", bg=c["card"], fg=c["accent"], font=(FONT, 14, "bold"),
        )
        self.action_label.pack(pady=(4, 12))

        # Status
        status_card = self._card(right, fill="x", pady=(0, 10))
        self.control_label = tk.Label(
            status_card, text="● CONTROL OFF", bg=c["card"], fg=c["danger"],
            font=(FONT, 13, "bold"), anchor="w",
        )
        self.control_label.pack(fill="x", padx=14, pady=(10, 0))
        self.cooldown_label = tk.Label(
            status_card, text="Cooldown: READY", bg=c["card"], fg=c["success"],
            font=(FONT, 11), anchor="w",
        )
        self.cooldown_label.pack(fill="x", padx=14)
        tk.Label(
            status_card, text="Gesture hold", bg=c["card"], fg=c["muted"],
            font=(FONT, 9), anchor="w",
        ).pack(fill="x", padx=14, pady=(6, 0))
        self.hold_bar = tk.Canvas(
            status_card, height=8, bg=c["card_border"], highlightthickness=0,
        )
        self.hold_bar.pack(fill="x", padx=14, pady=(2, 12))
        self._hold_rect = self.hold_bar.create_rectangle(0, 0, 0, 8, fill=c["accent"], width=0)

        # Presentation file picker (the main way to start)
        file_card = self._card(right, fill="x", pady=(0, 10))
        self._button(
            file_card, "📂 CHOOSE PRESENTATION FILE", c["accent"], "#6aa0ff", on_choose
        ).pack(fill="x", padx=14, pady=(12, 6))
        self.file_label = tk.Label(
            file_card, text="No file selected", bg=c["card"], fg=c["muted"],
            font=(FONT, 10), anchor="w", wraplength=380, justify="left",
        )
        self.file_label.pack(fill="x", padx=14, pady=(0, 12))

        # Buttons
        buttons = tk.Frame(right, bg=c["bg"])
        buttons.pack(fill="x", pady=(0, 10))
        self._button(
            buttons, "🎬 START / RESTART", c["success"], c["success_hover"], on_start
        ).pack(side="left", expand=True, fill="x", padx=(0, 6))
        self._button(
            buttons, "⏹ STOP CONTROL", c["danger"], c["danger_hover"], on_stop
        ).pack(side="left", expand=True, fill="x", padx=(6, 0))

        # History
        history_card = self._card(right, fill="both", expand=True)
        tk.Label(
            history_card, text="RECENT ACTIONS", bg=c["card"], fg=c["muted"],
            font=(FONT, 10, "bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(10, 4))
        self.history_labels: List[tk.Label] = []
        for _ in range(5):
            label = tk.Label(
                history_card, text="", bg=c["card"], fg=c["text"], font=(MONO, 10), anchor="w",
            )
            label.pack(fill="x", padx=14, pady=1)
            self.history_labels.append(label)

        # ---- footer
        footer = tk.Frame(root, bg=c["bg"])
        footer.pack(fill="x", padx=20, pady=(10, 14))
        self._button(
            footer, "← Previous", c["button_neutral"], c["button_neutral_hover"], on_previous
        ).pack(side="left")
        self.message_label = tk.Label(
            footer, text="", bg=c["bg"], fg=c["muted"], font=(FONT, 11), justify="center",
        )
        self.message_label.pack(side="left", expand=True)
        self._button(
            footer, "Next →", c["button_neutral"], c["button_neutral_hover"], on_next
        ).pack(side="right")
        tk.Label(
            root, text="Keyboard:  Ctrl+O  Choose file    →  Next    ←  Previous    ESC  Stop    Q  Quit",
            bg=c["bg"], fg=c["muted"], font=(FONT, 9),
        ).pack(pady=(0, 8))

    # ------------------------------------------------------------------ loop
    def run(self) -> None:
        self.root.after(15, self._tick)
        self.root.mainloop()

    def _tick(self) -> None:
        try:
            self._render(self._get_snapshot())
        finally:
            self.root.after(15, self._tick)

    # ---------------------------------------------------------------- render
    def _render(self, snap: UISnapshot) -> None:
        c = config.COLORS

        # Camera indicator
        if snap.camera_ok and not snap.fatal_error:
            self.camera_label.configure(text="🟢 CAMERA CONNECTED", fg=c["success"])
        else:
            self.camera_label.configure(text="🔴 CAMERA DISCONNECTED", fg=c["danger"])
        self.fps_label.configure(text=f"FPS: {snap.fps:.0f}" if snap.camera_ok else "FPS: --")

        # Video area
        if snap.fatal_error:
            self._show_video_text(f"❌ {snap.fatal_error}", c["danger"])
        elif not snap.camera_ok or snap.frame_bgr is None:
            self._show_video_text(snap.camera_message, c["danger"] if "❌" in snap.camera_message else c["muted"])
        elif snap.frame_id != self._last_frame_id:
            self._show_frame(snap.frame_bgr)
            self._last_frame_id = snap.frame_id

        # Gesture panel
        emoji, name = config.GESTURE_INFO.get(snap.gesture, ("❔", snap.gesture))
        self.gesture_emoji.configure(text=emoji)
        self.gesture_name.configure(text=name)
        self.gesture_conf.configure(
            text=f"Confidence: {snap.confidence * 100:.0f}%" if snap.confidence > 0 else "Confidence: --"
        )
        self.action_label.configure(text=f"Action: {snap.action}")

        # Status panel
        if snap.control_enabled:
            self.control_label.configure(text="● CONTROL ACTIVE", fg=c["success"])
        else:
            self.control_label.configure(text="● CONTROL OFF", fg=c["danger"])
        if snap.cooldown_remaining <= 0:
            self.cooldown_label.configure(text="Cooldown: READY", fg=c["success"])
        else:
            self.cooldown_label.configure(
                text=f"Cooldown: {snap.cooldown_remaining:.1f}s", fg=c["warning"]
            )
        width = max(self.hold_bar.winfo_width(), 1)
        self.hold_bar.coords(self._hold_rect, 0, 0, width * snap.hold_progress, 8)

        # History
        for index, label in enumerate(self.history_labels):
            if index < len(snap.history):
                stamp, gesture_text, action_text = snap.history[index]
                label.configure(text=f"{stamp}  {gesture_text:<16} → {action_text}")
            else:
                label.configure(text="")

        # Chosen file
        if snap.file_name:
            self.file_label.configure(text=f"📄 {snap.file_name}", fg=c["text"])
        else:
            self.file_label.configure(text="No file selected", fg=c["muted"])

        # Message bar: warnings win over the normal status text
        if snap.warning:
            self.message_label.configure(text=f"⚠ {snap.warning}", fg=c["warning"])
        else:
            self.message_label.configure(text=snap.status, fg=c["muted"])

    def _show_video_text(self, text: str, colour: str) -> None:
        if self._photo is not None or self.video_label.cget("text") != text:
            self.video_label.configure(
                image="", text=text, fg=colour, wraplength=config.FRAME_WIDTH - 40
            )
            self._photo = None
            self._last_frame_id = -1

    def _show_frame(self, frame_bgr) -> None:
        import cv2  # local import keeps the top of the file light

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        # PPM is a trivial image format Tk understands natively (no Pillow needed).
        data = b"P6 %d %d 255\n" % (width, height) + rgb.tobytes()
        self._photo = tk.PhotoImage(data=data, format="PPM")
        self.video_label.configure(image=self._photo, text="")