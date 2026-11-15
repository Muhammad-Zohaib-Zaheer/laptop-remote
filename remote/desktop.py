"""Reaches into the Windows desktop: finds a program's windows, brings one to
the front, presses keys, and closes windows the polite way."""
from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

import psutil

from .text import clean, close

user32 = ctypes.windll.user32
KEY_UP = 2
RESTORE = 9                          # ShowWindow: un-minimise
PLEASE_CLOSE = 0x0010                # WM_CLOSE: what the X button sends
SETTLE_S = 0.15                      # time Windows needs to hand over the keyboard
BIN_QUIETLY = 7                      # SHEmptyRecycleBin: no question, no progress window, no sound
# The desktop and the taskbar are windows too. Closing them asks Windows to shut down.
NEVER_CLOSE = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


def press(codes: tuple[int, ...], times: int = 1) -> None:
    """Press keys together, as on a keyboard, `times` times."""
    for _ in range(times):
        for key in codes:
            user32.keybd_event(key, 0, 0, 0)
        for key in reversed(codes):
            user32.keybd_event(key, 0, KEY_UP, 0)


def title(window: int) -> str:
    text = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(window, text, 512)
    return text.value


def kind(window: int) -> str:
    """The window's class: what sort of window it is ("Progman" is the desktop)."""
    text = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(window, text, 256)
    return text.value


def all_windows() -> list[tuple[int, str, str]]:
    """Every visible, titled window, front-most first: (window, program, title).

    `program` is the name in Task Manager without ".exe", in small letters.
    The desktop, the taskbar and Sarah's own window are left out.
    """
    found: list[tuple[int, str, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def look(window, _):
        if (user32.IsWindowVisible(window) and user32.GetWindowTextLengthW(window)
                and kind(window) not in NEVER_CLOSE):
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
            try:
                if owner.value != os.getpid():
                    program = psutil.Process(owner.value).name().lower().removesuffix(".exe")
                    found.append((window, program, title(window)))
            except psutil.Error:
                pass                     # the program closed while we were looking
        return True

    user32.EnumWindows(look, 0)
    return found


def windows_of(program: str) -> list[int]:
    """The windows of one program ("uc.exe"), front-most first."""
    wanted = program.lower().removesuffix(".exe")
    return [window for window, name, _ in all_windows() if name == wanted]


def windows_named(words: list[str]) -> list[int]:
    """The windows of the app that is called by these words.

    A program whose own name is one of the words comes first ("chrome"). Else
    the app's name is looked for where windows carry it, at the end of the
    title: "report.docx - Word". A browser tab about a word is not Word.
    """
    everything = all_windows()
    by_program = [window for window, program, _ in everything
                  if any(close(word, program) for word in words)]
    if by_program:
        return by_program
    return [window for window, _, name in everything
            if all(word in clean(name.rsplit(" - ", 1)[-1]) for word in words)]


class _BinInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("bytes", ctypes.c_int64), ("items", ctypes.c_int64)]


def bin_items() -> int:
    """How many things lie in the recycle bin, on all drives together."""
    info = _BinInfo(size=ctypes.sizeof(_BinInfo))
    ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    return info.items


def empty_bin() -> None:
    """Delete what is in the recycle bin for good, without Windows' own question and sound."""
    ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, BIN_QUIETLY)


SHOW = {"minimize": 6, "maximize": 3, "restore": 9}     # ShowWindow commands


def show(window: int, how: str) -> None:
    """Minimise, maximise or restore a window."""
    user32.ShowWindow(window, SHOW[how])


def ask_to_close(window: int) -> None:
    """The same as clicking the X: the program may still ask to save your work."""
    user32.PostMessageW(window, PLEASE_CLOSE, 0, 0)


def in_front() -> int:
    return user32.GetForegroundWindow()


def bring_to_front(window: int) -> bool:
    """Give a window the keyboard. True only if it really is in front afterwards.

    Windows refuses this to programs that do not own the keyboard at the
    moment, unless they are attached to the one that does.
    """
    if user32.IsIconic(window):
        user32.ShowWindow(window, RESTORE)
    ours = ctypes.windll.kernel32.GetCurrentThreadId()
    theirs = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    user32.AttachThreadInput(ours, theirs, True)
    user32.SetForegroundWindow(window)
    user32.BringWindowToTop(window)
    user32.AttachThreadInput(ours, theirs, False)
    time.sleep(SETTLE_S)
    return user32.GetForegroundWindow() == window
