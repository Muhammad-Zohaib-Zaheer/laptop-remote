"""Key names, as written in config.yaml, and the codes Windows knows them by."""
from __future__ import annotations

import re

NAMES = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "pageup": 0x21, "pagedown": 0x22, "home": 0x24, "end": 0x23,
    "printscreen": 0x2C,
    "media next": 0xB0, "media previous": 0xB1, "media play": 0xB3,
}
# The same modifier keys, as RegisterHotKey counts them.
HOTKEY_MODIFIERS = {"alt": 1, "ctrl": 2, "shift": 4, "win": 8}


def code(name: str) -> int:
    """The key code for a name: "ctrl", "f5", "w"."""
    name = str(name).lower()
    if name in NAMES:
        return NAMES[name]
    if re.fullmatch(r"f\d{1,2}", name):
        return 0x6F + int(name[1:])
    if len(name) == 1:
        return ord(name.upper())
    raise ValueError(f"unknown key in config.yaml: {name!r}")
