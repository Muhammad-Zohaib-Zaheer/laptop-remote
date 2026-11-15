"""The screen as JPEG frames, and the mouse and keyboard driven from the phone."""
from __future__ import annotations

import ctypes
import io
import logging
from ctypes import wintypes

from PIL import Image, ImageGrab

log = logging.getLogger("remote")
user32 = ctypes.windll.user32
# Real pixels, not scaled ones: the frame and the mouse then use the same numbers.
ctypes.windll.shcore.SetProcessDpiAwareness(2)

# mouse_event flags, per button: (down, up)
BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}
WHEEL = 0x0800
KEY_UP, UNICODE = 0x0002, 0x0004
INPUT_KEYBOARD = 1


def grab(max_side: int) -> Image.Image:
    """The main screen now, shrunk to `max_side` pixels."""
    image = ImageGrab.grab()
    image.thumbnail((max_side, max_side), Image.Resampling.BILINEAR)
    return image


def jpeg(image: Image.Image, quality: int) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=quality)
    return out.getvalue()


def png() -> bytes:
    """A full-size screenshot."""
    out = io.BytesIO()
    ImageGrab.grab().save(out, "PNG")
    return out.getvalue()


def _point(x: float, y: float) -> None:
    """Move the mouse to a place given as 0-1 of the screen's width and height."""
    user32.SetCursorPos(round(x * (user32.GetSystemMetrics(0) - 1)),
                        round(y * (user32.GetSystemMetrics(1) - 1)))


# --------------------------------------------------------------- keyboard

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    # The real union also holds mouse input, which is larger; padding keeps the size right.
    _fields_ = [("type", wintypes.DWORD), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 8)]


def type_text(text: str) -> None:
    """Type any text, letters of every language included, into the window in front."""
    keys, data = [], text.encode("utf-16-le")
    for i in range(0, len(data), 2):
        scan = int.from_bytes(data[i:i + 2], "little")
        for flags in (UNICODE, UNICODE | KEY_UP):
            keys.append(INPUT(INPUT_KEYBOARD, KEYBDINPUT(0, scan, flags, 0, 0)))
    if keys:
        user32.SendInput(len(keys), (INPUT * len(keys))(*keys), ctypes.sizeof(INPUT))


class Hands:
    """Mouse and keyboard. `dry_run` = only log what would be done."""

    def __init__(self, key_code, press, extra_codes: dict[str, int], dry_run: bool):
        self.key_code, self.press, self.extra, self.dry_run = key_code, press, extra_codes, dry_run

    def code(self, name: str) -> int:
        return self.extra.get(str(name).lower()) or self.key_code(name)

    def do(self, event: dict) -> None:
        """One event from the phone: {"t": "click", "x": 0.5, "y": 0.2, "b": "left"} ..."""
        kind = event["t"]
        if self.dry_run:
            log.info("dry run: %s", event)
            return
        if "x" in event:
            _point(event["x"], event["y"])
        down, up = BUTTONS[event.get("b", "left")]
        if kind == "click":
            user32.mouse_event(down, 0, 0, 0, 0)
            user32.mouse_event(up, 0, 0, 0, 0)
        elif kind == "down":
            user32.mouse_event(down, 0, 0, 0, 0)
        elif kind == "up":
            user32.mouse_event(up, 0, 0, 0, 0)
        elif kind == "scroll":                   # dy > 0 = down, like a finger on a phone
            user32.mouse_event(WHEEL, 0, 0, ctypes.c_uint32(-round(event["dy"])).value, 0)
        elif kind == "keys":
            self.press(tuple(self.code(name) for name in event["keys"]))
        elif kind == "text":
            type_text(event["s"])
