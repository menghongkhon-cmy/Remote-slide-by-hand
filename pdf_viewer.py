"""
pdf_viewer.py - built-in fullscreen PDF presenter.

PowerPoint files (.pptx, .ppt, .ppsx ...) are opened in PowerPoint itself.
PDF files are shown by THIS window, so slides can be changed reliably by the
same keyboard keys the app already sends (RIGHT / LEFT) - no dependence on
which PDF reader the computer happens to have.

The window title always contains "Slide Show" and the file name, so the rest of
the app (powerpoint_controller.py) finds it, focuses it and detects it exactly
like a PowerPoint slideshow window. Uses pypdfium2 and Pillow.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk

import config
from collections import OrderedDict
from typing import Optional, Tuple

NEXT_KEYS = ("<Right>", "<Down>", "<space>", "<Next>", "<Return>", "<n>")
PREVIOUS_KEYS = ("<Left>", "<Up>", "<BackSpace>", "<Prior>", "<p>")


def _load_pdfium():
    """Import pypdfium2 and PIL. Raises ImportError with the reason if it cannot be loaded."""
    try:
        import pypdfium2 as pdfium
        from PIL import Image, ImageTk
        return pdfium, Image, ImageTk
    except ImportError as exc:
        raise ImportError(f"Required PDF packages missing: {exc}") from exc


class PdfPresenter:
    """Shows one PDF, one page at a time, fullscreen on a black background."""

    def __init__(self, root: tk.Misc) -> None:
        self._root = root
        self._win: Optional[tk.Toplevel] = None
        self._label: Optional[tk.Label] = None
        self._counter: Optional[tk.Label] = None
        self._hud: Optional[tk.Label] = None
        self._doc = None
        self._pdfium = None
        self._Image = None
        self._ImageTk = None
        self._page = 0
        self._photo: Optional[tk.PhotoImage] = None
        self._cache: "OrderedDict[Tuple[int, int, int], object]" = OrderedDict()
        self._resize_job: Optional[str] = None
        self._counter_job: Optional[str] = None
        self._fullscreen = True

    # ---------------------------------------------------------------- state
    @property
    def is_open(self) -> bool:
        return self._win is not None

    @property
    def page_number(self) -> int:
        return self._page + 1

    @property
    def page_count(self) -> int:
        return len(self._doc) if self._doc is not None else 0

    # ----------------------------------------------------------------- open
    def open(self, path: str) -> Tuple[bool, str]:
        """Open a PDF fullscreen. Returns (ok, message)."""
        self.close()
        if not os.path.isfile(path):
            return False, f"File not found:\n{path}"
        try:
            self._pdfium, self._Image, self._ImageTk = _load_pdfium()
        except ImportError as exc:
            return False, (
                f"PDF support needs pypdfium2 and pillow.\n\nReason: {exc}\n\n"
                f"This app runs with:\n{sys.executable}\n\n"
                f"Install them into THAT Python:\n\"{sys.executable}\" -m pip install pypdfium2 pillow"
            )
        try:
            self._doc = self._pdfium.PdfDocument(path)
            if len(self._doc) < 1:
                raise ValueError("the PDF has no pages")
        except Exception as exc:  # noqa: BLE001
            self._doc = None
            return False, f"Could not open the PDF: {exc}"

        win = tk.Toplevel(self._root)
        win.title(f"Slide Show - {os.path.basename(path)}")  # keyword lets the app find this window
        win.configure(bg="black")
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        w, h = int(sw * 0.6), int(sh * 0.62)
        win.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 3}")
        self._win = win
        self._fullscreen = bool(getattr(config, "PDF_START_FULLSCREEN", False))
        win.attributes("-fullscreen", self._fullscreen)

        self._label = tk.Label(win, bg="black", bd=0, highlightthickness=0)
        self._label.pack(fill="both", expand=True)
        self._counter = tk.Label(
            win, text="", bg="#141831", fg="#eef1ff", font=("Segoe UI", 12, "bold"), padx=12, pady=4,
        )
        self._hud = tk.Label(
            win, text="", bg="#141831", fg="#34e0a1", font=("Segoe UI Emoji", 14, "bold"), padx=14, pady=6,
        )

        for key in NEXT_KEYS:
            win.bind(key, lambda _e: self.next())
        for key in PREVIOUS_KEYS:
            win.bind(key, lambda _e: self.previous())
        win.bind("<Home>", lambda _e: self.goto(0))
        win.bind("<End>", lambda _e: self.goto(self.page_count - 1))
        win.bind("<Escape>", lambda _e: self._set_fullscreen(False))
        win.bind("<F11>", lambda _e: self._set_fullscreen(not self._fullscreen))
        win.bind("<F5>", lambda _e: self._set_fullscreen(True))
        win.bind("<f>", lambda _e: self._set_fullscreen(not self._fullscreen))
        self._label.bind("<Configure>", self._on_resize)
        win.protocol("WM_DELETE_WINDOW", self.close)

        self._page = 0
        win.update_idletasks()
        win.lift()
        win.focus_force()
        self._render()
        self._flash_counter()
        return True, ""

    def show(self) -> None:
        """Bring the viewer to the front."""
        if self._win is not None:
            self._win.lift()
            self._win.focus_force()

    def set_hud(self, text: str) -> None:
        """Small gesture indicator in the bottom-left corner ('' hides it)."""
        if self._hud is None:
            return
        if text:
            self._hud.configure(text=text)
            self._hud.place(relx=0.0, rely=1.0, x=18, y=-18, anchor="sw")
        else:
            self._hud.place_forget()

    # ------------------------------------------------------------ navigation
    def next(self) -> None:
        self.goto(self._page + 1)

    def previous(self) -> None:
        self.goto(self._page - 1)

    def goto(self, page: int) -> None:
        if self._doc is None:
            return
        page = max(0, min(self.page_count - 1, page))
        if page != self._page:
            self._page = page
            self._render()
        self._flash_counter()

    # ---------------------------------------------------------------- render
    def _set_fullscreen(self, on: bool) -> None:
        if self._win is None:
            return
        self._fullscreen = on
        self._win.attributes("-fullscreen", on)
        self._win.focus_force()

    def _on_resize(self, _event) -> None:
        if self._win is None:
            return
        if self._resize_job is not None:
            self._win.after_cancel(self._resize_job)
        self._resize_job = self._win.after(150, self._render)  # wait until resizing stops

    def _render(self) -> None:
        self._resize_job = None
        if self._win is None or self._doc is None or self._label is None:
            return
        width, height = self._label.winfo_width(), self._label.winfo_height()
        if width < 50 or height < 50:
            width, height = self._win.winfo_screenwidth(), self._win.winfo_screenheight()

        key = (self._page, width, height)
        pil_img = self._cache.get(key)
        if pil_img is None:
            try:
                page = self._doc[self._page]
                pw, ph = page.get_size()
                scale = min(width / pw, height / ph)
                bitmap = page.render(scale=scale)
                pil_img = bitmap.to_pil().convert("RGB")  # Fixed: solid RGB background instead of transparent
            except Exception as exc:  # noqa: BLE001
                self._label.configure(image="", text=f"Could not draw page {self._page + 1}: {exc}",
                                      fg="#ff5d7a", font=("Segoe UI", 16))
                return
            self._cache[key] = pil_img
            while len(self._cache) > 6:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(key)

        self._photo = self._ImageTk.PhotoImage(pil_img)
        self._label.configure(image=self._photo, text="")
        self._update_counter()

    def _update_counter(self) -> None:
        if self._counter is not None:
            self._counter.configure(text=f"{self._page + 1} / {self.page_count}")

    def _flash_counter(self) -> None:
        """Show the page number in the corner for 1.5 s after every page change."""
        if self._win is None or self._counter is None:
            return
        self._update_counter()
        self._counter.place(relx=1.0, rely=1.0, x=-18, y=-18, anchor="se")
        if self._counter_job is not None:
            self._win.after_cancel(self._counter_job)
        self._counter_job = self._win.after(1500, self._hide_counter)

    def _hide_counter(self) -> None:
        self._counter_job = None
        if self._counter is not None:
            self._counter.place_forget()

    # ----------------------------------------------------------------- close
    def close(self) -> None:
        win, self._win = self._win, None
        if win is not None:
            try:
                win.destroy()
            except tk.TclError:
                pass
        if self._doc is not None:
            try:
                self._doc.close()
            except Exception:  # noqa: BLE001
                pass
        self._doc = None
        self._label = None
        self._counter = None
        self._hud = None
        self._photo = None
        self._cache.clear()
        self._resize_job = None
        self._counter_job = None