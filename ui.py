"""
ui.py - the Tkinter window (modern redesign).

The UI knows NOTHING about MediaPipe or PowerPoint. It just:
  * asks for the latest UISnapshot ~60 times a second and draws it, and
  * calls the callbacks (start / stop / quit / next / previous / choose) you give it.

Public API is unchanged (UISnapshot, MainWindow(...), .root, .run()), so
main.py works without any edits.

Look & feel
-----------
  * rounded "glass" cards, pill status badges, rounded buttons
  * smooth progress bars for confidence, gesture hold and cooldown
  * colour-coded recent-actions list
All colours come from config.COLORS (a few extra shades are derived here).
"""

from __future__ import annotations

import os
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Tuple

import config

FONT = "Segoe UI"
EMOJI_FONT = "Segoe UI Emoji"
MONO = "Consolas"
# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(a: str, b: str, t: float) -> str:
    """Blend colour a into colour b. t=0 -> b, t=1 -> a."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#%02x%02x%02x" % (
        round(rb + (ra - rb) * t),
        round(gb + (ga - gb) * t),
        round(bb + (ba - bb) * t),
    )


def _round_points(x1: float, y1: float, x2: float, y2: float, r: float) -> List[float]:
    """Polygon points of a rounded rectangle (draw with smooth=True)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def _gradient_strip(canvas: tk.Canvas, c1: str, c2: str) -> None:
    """Fill a canvas with a left->right colour gradient."""
    canvas.delete("all")
    w, h = max(canvas.winfo_width(), 2), canvas.winfo_height()
    for x in range(w):
        canvas.create_line(x, 0, x, h, fill=_mix(c2, c1, x / (w - 1)))


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


# ---------------------------------------------------------------------------
# Custom widgets (Canvas based, so we can have rounded corners)
# ---------------------------------------------------------------------------
class Card(tk.Canvas):
    """A rounded panel. Put your widgets in `card.inner`."""

    def __init__(self, parent: tk.Misc, radius: int = 20, pad: int = 16,
                 fixed_width: bool = False) -> None:
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self._radius = radius
        self._pad = pad
        self._fixed_width = fixed_width
        c = config.COLORS
        self.inner = tk.Frame(self, bg=c["card"])
        self._win = self.create_window(pad, pad, window=self.inner, anchor="nw")
        self.bind("<Configure>", self._on_resize)
        self.inner.bind("<Configure>", self._on_inner)

    def _on_resize(self, event) -> None:
        c = config.COLORS
        self.delete("shape")
        self.create_polygon(
            _round_points(1, 1, event.width - 1, event.height - 1, self._radius),
            smooth=True, fill=c["card"], outline=c["card_border"], width=1, tags="shape",
        )
        self.tag_lower("shape")
        if not self._fixed_width:  # fixed-width cards keep their natural width (never clipped)
            self.itemconfigure(self._win, width=max(event.width - 2 * self._pad, 1))

    def _on_inner(self, event) -> None:
        self.configure(height=self.inner.winfo_reqheight() + 2 * self._pad)
        if self._fixed_width:
            self.configure(width=self.inner.winfo_reqwidth() + 2 * self._pad)


class RoundedButton(tk.Canvas):
    """A flat rounded button with hover and press feedback."""

    def __init__(self, parent: tk.Misc, text: str, bg: str, hover: str,
                 command: Callable[[], None], fg: str = "white",
                 size: int = 12, height: int = 46, radius: int = 14, padx: int = 24) -> None:
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0,
                         height=height, cursor="hand2")
        self._text = text
        self._bg = bg
        self._hover = hover
        self._fg = fg
        self._command = command
        self._radius = radius
        self._current = bg
        self._font = tkfont.Font(family=FONT, size=size, weight="bold")
        self.configure(width=self._font.measure(text) + 2 * padx)
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", lambda _e: self._set(self._hover))
        self.bind("<Leave>", lambda _e: self._set(self._bg))
        self.bind("<ButtonPress-1>", lambda _e: self._set(_mix("#000000", self._hover, 0.18)))
        self.bind("<ButtonRelease-1>", self._release)

    def _set(self, colour: str) -> None:
        self._current = colour
        self._draw()

    def _release(self, event) -> None:
        self._set(self._hover)
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self._command()

    def _draw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.create_polygon(_round_points(1, 1, w - 1, h - 1, self._radius),
                            smooth=True, fill=self._current, outline=self._current)
        self.create_text(w / 2, h / 2, text=self._text, fill=self._fg, font=self._font)


class Pill(tk.Canvas):
    """Small rounded status badge with a coloured dot: ● TEXT."""

    def __init__(self, parent: tk.Misc, text: str = "", colour: str = "#8a94ad") -> None:
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0, height=32)
        self._font = tkfont.Font(family=FONT, size=10, weight="bold")
        self._text = ""
        self._colour = ""
        self.set(text, colour)

    def set(self, text: str, colour: str) -> None:
        if text == self._text and colour == self._colour:
            return
        self._text, self._colour = text, colour
        width = self._font.measure(text) + 50
        self.configure(width=width)
        self.delete("all")
        base = self.cget("bg")
        fill = _mix(colour, base, 0.16)
        self.create_polygon(_round_points(1, 1, width - 1, 31, 15), smooth=True,
                            fill=fill, outline=_mix(colour, base, 0.45))
        self.create_oval(14, 12, 22, 20, fill=colour, outline=colour)
        self.create_text(30, 16, text=text, fill=colour, font=self._font, anchor="w")


class Bar(tk.Canvas):
    """Thin rounded progress bar. set(fraction, colour)."""

    def __init__(self, parent: tk.Misc, height: int = 10) -> None:
        super().__init__(parent, bg=parent.cget("bg"), highlightthickness=0, bd=0, height=height)
        self._h = height
        self._fraction = 0.0
        self._colour = config.COLORS["accent"]
        self.bind("<Configure>", lambda _e: self._draw())

    def set(self, fraction: float, colour: Optional[str] = None) -> None:
        fraction = max(0.0, min(1.0, fraction))
        colour = colour or self._colour
        if abs(fraction - self._fraction) < 0.004 and colour == self._colour:
            return
        self._fraction, self._colour = fraction, colour
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self._h
        if w < 4:
            return
        r = h / 2
        self.create_line(r, r, w - r, r, width=h, capstyle="round",
                         fill=config.COLORS["card_border"])
        if self._fraction > 0.001:
            end = max(r + 0.5, r + (w - 2 * r) * self._fraction)
            self.create_line(r, r, end, r, width=h, capstyle="round", fill=self._colour)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
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
        self._fit_text_scale()
        self._set_icon()

        self._build(on_start, on_stop, on_next, on_previous, on_choose)
        self._fit_to_screen()

        # Keyboard fallback / safety keys (work while this window is focused).
        self.root.bind("<Escape>", lambda _e: on_stop())
        self.root.bind("<q>", lambda _e: on_quit())
        self.root.bind("<Q>", lambda _e: on_quit())
        self.root.bind("<Control-o>", lambda _e: on_choose())
        self.root.bind("<Right>", lambda _e: on_next())
        self.root.bind("<Left>", lambda _e: on_previous())
        self.root.protocol("WM_DELETE_WINDOW", on_quit)

    # --------------------------------------------------------- screen fitting
    def _fit_text_scale(self) -> None:
        """On high-DPI screens (125-200 % scaling) Windows makes every font bigger and the
        window no longer fits the screen. Limit the text scaling so everything stays visible."""
        try:
            current = float(self.root.tk.call("tk", "scaling"))
            screen_h = self.root.winfo_screenheight()
            fit = 1.333 * (((screen_h - 110) / 900.0) - 0.6) / 0.4
            self.root.tk.call("tk", "scaling", min(current, max(1.0, fit)))
        except tk.TclError:
            pass

    def _fit_to_screen(self) -> None:
        """Size the window to its content, but never bigger than the screen."""
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w = min(max(self.root.winfo_reqwidth(), 1100), sw - 20)
        h = min(max(self.root.winfo_reqheight(), 700), sh - 90)
        self.root.geometry(f"{w}x{h}+{max((sw - w) // 2, 0)}+10")
        self.root.minsize(min(w, 1000), min(h, 650))

    # ------------------------------------------------------------------ build
    def _set_icon(self) -> None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icon.png")
        try:
            self._icon = tk.PhotoImage(file=path)
            self.root.iconphoto(True, self._icon)
        except tk.TclError:
            pass  # icon is optional

    def _label(self, parent, text="", fg=None, size=11, weight="normal", font=None, **kw) -> tk.Label:
        c = config.COLORS
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=fg or c["text"],
                        font=font or (FONT, size, weight), **kw)

    def _build(self, on_start, on_stop, on_next, on_previous, on_choose) -> None:
        c = config.COLORS
        root = self.root

        # ---- header: logo badge + title (left), control pill (right)
        header = tk.Frame(root, bg=c["bg"])
        header.pack(fill="x", padx=28, pady=(22, 12))

        badge = tk.Canvas(header, width=56, height=56, bg=c["bg"], highlightthickness=0)
        badge.create_polygon(_round_points(1, 1, 55, 55, 16), smooth=True,
                             fill=c["accent"], outline=c["accent2"], width=2)
        badge.create_text(28, 29, text="🖐️", font=(EMOJI_FONT, 24), fill="white")
        badge.pack(side="left")

        titles = tk.Frame(header, bg=c["bg"])
        titles.pack(side="left", padx=(14, 0))
        self._label(titles, config.APP_NAME.upper(), size=21, weight="bold", anchor="w").pack(anchor="w")
        self._label(titles, config.APP_SUBTITLE, fg=c["muted"], size=11, anchor="w").pack(anchor="w")

        self.control_pill = Pill(header, "CONTROL OFF", c["danger"])
        self.control_pill.pack(side="right")

        line = tk.Canvas(root, height=3, bg=c["bg"], highlightthickness=0)
        line.pack(fill="x", padx=28, pady=(0, 16))
        line.bind("<Configure>", lambda _e: _gradient_strip(line, c["accent"], c["accent2"]))

        body = tk.Frame(root, bg=c["bg"])
        body.pack(fill="both", expand=True, padx=28)

        # ---- left column: camera
        left = Card(body, fixed_width=True)
        left.pack(side="left", fill="y", padx=(0, 16))
        top_row = tk.Frame(left.inner, bg=c["card"])
        top_row.pack(fill="x", pady=(0, 10))
        self.camera_pill = Pill(top_row, "CAMERA DISCONNECTED", c["danger"])
        self.camera_pill.pack(side="left")
        self.fps_label = self._label(top_row, "FPS --", fg=c["muted"], size=11, weight="bold")
        self.fps_label.pack(side="right")

        video_box = tk.Frame(left.inner, bg="black", width=config.FRAME_WIDTH,
                             height=config.FRAME_HEIGHT, highlightthickness=1,
                             highlightbackground=c["card_border"])
        video_box.pack()
        video_box.pack_propagate(False)
        self.video_label = tk.Label(video_box, bg="black", fg=c["muted"], font=(FONT, 15),
                                    text="Starting camera...", justify="center")
        self.video_label.pack(fill="both", expand=True)

        # Gesture legend, built from config.GESTURE_ACTIONS (so it always matches your settings)
        chips = tk.Frame(left.inner, bg=c["card"])
        chips.pack(pady=(14, 0))
        short = {"NEXT": "Next", "PREVIOUS": "Back", "NONE": "Rest", "ENABLE": "On"}
        tint = {"NEXT": c["success"], "PREVIOUS": c["danger"], "NONE": c["muted"], "ENABLE": c["accent"]}
        for gesture_key, action_key in config.GESTURE_ACTIONS.items():
            emoji = config.GESTURE_INFO.get(gesture_key, ("", ""))[0]
            colour = tint.get(action_key, c["muted"])
            tk.Label(
                chips, text=f"{emoji} {short.get(action_key, action_key.title())}",
                bg=_mix(colour, c["card"], 0.16), fg=colour,
                font=(EMOJI_FONT, 10, "bold"), padx=9, pady=4,
            ).pack(side="left", padx=3)

        self._label(left.inner, "Show one hand 40-100 cm away, or smile at the camera to go back",
                    fg=c["muted"], size=10).pack(pady=(10, 0))

        # ---- right column
        right = tk.Frame(body, bg=c["bg"])
        right.pack(side="left", fill="both", expand=True)

        # Gesture card
        gesture_card = Card(right)
        gesture_card.pack(fill="x", pady=(0, 12))
        g = gesture_card.inner
        self.gesture_emoji = self._label(g, "…", font=(EMOJI_FONT, 54))
        self.gesture_emoji.pack(pady=(0, 0))
        self.gesture_name = self._label(g, "NONE", size=21, weight="bold")
        self.gesture_name.pack()
        conf_row = tk.Frame(g, bg=c["card"])
        conf_row.pack(fill="x", pady=(10, 0))
        self._label(conf_row, "Confidence", fg=c["muted"], size=10).pack(side="left")
        self.gesture_conf = self._label(conf_row, "--", fg=c["muted"], size=10, weight="bold")
        self.gesture_conf.pack(side="right")
        self.conf_bar = Bar(g, height=8)
        self.conf_bar.pack(fill="x", pady=(4, 10))
        self.action_label = self._label(g, "Action: —", fg=c["accent"], size=13, weight="bold")
        self.action_label.pack()

        # Status card
        status_card = Card(right)
        status_card.pack(fill="x", pady=(0, 12))
        s = status_card.inner
        hold_row = tk.Frame(s, bg=c["card"])
        hold_row.pack(fill="x")
        self._label(hold_row, "Gesture hold", fg=c["muted"], size=10).pack(side="left")
        self.hold_label = self._label(hold_row, "0%", fg=c["muted"], size=10, weight="bold")
        self.hold_label.pack(side="right")
        self.hold_bar = Bar(s, height=10)
        self.hold_bar.pack(fill="x", pady=(4, 12))
        cool_row = tk.Frame(s, bg=c["card"])
        cool_row.pack(fill="x")
        self._label(cool_row, "Cooldown", fg=c["muted"], size=10).pack(side="left")
        self.cooldown_label = self._label(cool_row, "READY", fg=c["success"], size=10, weight="bold")
        self.cooldown_label.pack(side="right")
        self.cool_bar = Bar(s, height=10)
        self.cool_bar.pack(fill="x", pady=(4, 0))

        # Presentation file picker
        file_card = Card(right)
        file_card.pack(fill="x", pady=(0, 12))
        RoundedButton(file_card.inner, "📂  CHOOSE PRESENTATION FILE", c["accent"], c["accent_hover"],
                      on_choose).pack(fill="x")
        self.file_label = self._label(file_card.inner, "No file selected", fg=c["muted"], size=10,
                                      anchor="w", wraplength=380, justify="left")
        self.file_label.pack(fill="x", pady=(10, 0))

        # Start / Stop
        buttons = tk.Frame(right, bg=c["bg"])
        buttons.pack(fill="x", pady=(0, 12))
        RoundedButton(buttons, "🎬  START / RESTART", c["success"], c["success_hover"],
                      on_start, fg="#06241a").pack(side="left", expand=True, fill="x", padx=(0, 6))
        RoundedButton(buttons, "⏹  STOP CONTROL", c["danger"], c["danger_hover"],
                      on_stop).pack(side="left", expand=True, fill="x", padx=(6, 0))

        # History
        history_card = Card(right)
        history_card.pack(fill="both", expand=True)
        h = history_card.inner
        self._label(h, "RECENT ACTIONS", fg=c["muted"], size=10, weight="bold", anchor="w").pack(fill="x", pady=(0, 6))
        self.history_rows: List[Tuple[tk.Label, tk.Label, tk.Label, tk.Label]] = []
        for _ in range(5):
            row = tk.Frame(h, bg=c["card"])
            row.pack(fill="x", pady=2)
            dot = tk.Label(row, text="●", bg=c["card"], fg=c["card"], font=(FONT, 9))
            dot.pack(side="left")
            stamp = tk.Label(row, text="", bg=c["card"], fg=c["muted"], font=(MONO, 10))
            stamp.pack(side="left", padx=(6, 10))
            gesture = tk.Label(row, text="", bg=c["card"], fg=c["text"], font=(MONO, 10), width=14, anchor="w")
            gesture.pack(side="left")
            action = tk.Label(row, text="", bg=c["card"], fg=c["accent"], font=(MONO, 10, "bold"), anchor="w")
            action.pack(side="left")
            self.history_rows.append((dot, stamp, gesture, action))

        # ---- footer
        footer = tk.Frame(root, bg=c["bg"])
        footer.pack(fill="x", padx=28, pady=(14, 6))
        RoundedButton(footer, "←  Previous", c["button_neutral"], c["button_neutral_hover"],
                      on_previous, height=42).pack(side="left")
        self.message_label = tk.Label(footer, text="", bg=c["bg"], fg=c["muted"],
                                      font=(FONT, 11), justify="center", wraplength=600)
        self.message_label.pack(side="left", expand=True)
        RoundedButton(footer, "Next  →", c["button_neutral"], c["button_neutral_hover"],
                      on_next, height=42).pack(side="right")

        tk.Label(
            root, text="Ctrl+O  Choose file    →  Next    ←  Previous    ESC  Stop    Q  Quit",
            bg=c["bg"], fg=_mix(c["muted"], c["bg"], 0.8), font=(FONT, 9),
        ).pack(pady=(0, 10))

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

        # Camera pill + FPS
        if snap.camera_ok and not snap.fatal_error:
            self.camera_pill.set("CAMERA CONNECTED", c["success"])
        else:
            self.camera_pill.set("CAMERA DISCONNECTED", c["danger"])
        self.fps_label.configure(text=f"FPS {snap.fps:.0f}" if snap.camera_ok else "FPS --")

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
        if snap.confidence > 0:
            self.gesture_conf.configure(text=f"{snap.confidence * 100:.0f}%", fg=c["text"])
            level = c["success"] if snap.confidence >= config.CONFIDENCE_THRESHOLD else c["warning"]
            self.conf_bar.set(snap.confidence, level)
        else:
            self.gesture_conf.configure(text="--", fg=c["muted"])
            self.conf_bar.set(0.0)
        self.action_label.configure(text=f"Action: {snap.action}")

        # Control pill
        if snap.control_enabled:
            self.control_pill.set("CONTROL ACTIVE", c["success"])
        else:
            self.control_pill.set("CONTROL OFF", c["danger"])

        # Hold + cooldown bars
        self.hold_bar.set(snap.hold_progress, c["success"] if snap.hold_progress >= 0.98 else c["accent"])
        self.hold_label.configure(text=f"{snap.hold_progress * 100:.0f}%")
        if snap.cooldown_remaining <= 0:
            self.cooldown_label.configure(text="READY", fg=c["success"])
            self.cool_bar.set(0.0)
        else:
            self.cooldown_label.configure(text=f"{snap.cooldown_remaining:.1f}s", fg=c["warning"])
            self.cool_bar.set(snap.cooldown_remaining / max(config.GESTURE_COOLDOWN, 0.1), c["warning"])

        # History
        for index, (dot, stamp, gesture, action) in enumerate(self.history_rows):
            if index < len(snap.history):
                when, gesture_text, action_text = snap.history[index]
                colour = c["danger"] if "PREV" in action_text.upper() else c["success"] \
                    if "NEXT" in action_text.upper() else c["accent"]
                dot.configure(fg=colour)
                stamp.configure(text=when)
                gesture.configure(text=gesture_text)
                action.configure(text=f"→ {action_text}", fg=colour)
            else:
                dot.configure(fg=c["card"])
                stamp.configure(text="")
                gesture.configure(text="")
                action.configure(text="")

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