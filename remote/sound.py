"""The speaker volume, through Windows' own audio interface (Core Audio).

No extra package is used: the three interfaces are called through their
function tables. Each number below is that function's position in its table,
taken from the Windows SDK headers mmdeviceapi.h and endpointvolume.h.
"""
from __future__ import annotations

import ctypes
from contextlib import contextmanager
from ctypes import POINTER, byref, c_float, c_int, c_long, c_void_p, wintypes
from uuid import UUID

EVERYWHERE = 23                      # CLSCTX_ALL
SPEAKERS, MUSIC = 0, 1               # eRender, eMultimedia
RELEASE = 2
GET_DEFAULT_DEVICE, ACTIVATE = 4, 3
SET_VOLUME, GET_VOLUME, SET_MUTE, GET_MUTE = 7, 9, 14, 15
GET_PEAK = 3


class GUID(ctypes.Structure):
    _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                ("d", ctypes.c_ubyte * 8)]

    def __init__(self, text: str):
        u = UUID(text)
        super().__init__(u.time_low, u.time_mid, u.time_hi_version,
                         (ctypes.c_ubyte * 8)(*u.bytes[8:]))


DEVICE_ENUMERATOR = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
I_DEVICE_ENUMERATOR = GUID("A95664D2-9614-4F35-A746-DE8DB63617E6")
I_ENDPOINT_VOLUME = GUID("5CDF2C82-841E-4546-9722-0CF74078229A")
I_METER = GUID("C02216F6-8C67-4B5B-9D00-D008E73E0064")


def _call(thing: c_void_p, position: int, *args, types=()) -> None:
    """Call the function at `position` in a COM object's table; raise if it fails."""
    table = ctypes.cast(thing, POINTER(POINTER(c_void_p))).contents
    function = ctypes.WINFUNCTYPE(c_long, c_void_p, *types)(table[position])
    result = function(thing, *args)
    if result < 0:
        raise OSError(f"Windows audio call {position} failed: {result & 0xFFFFFFFF:#x}")


@contextmanager
def _speakers(interface: GUID):
    """The default speakers, seen through one interface; everything is released after."""
    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)             # needed once per thread; harmless when repeated
    enumerator, device, wanted = c_void_p(), c_void_p(), c_void_p()
    held = []
    try:
        result = ole32.CoCreateInstance(byref(DEVICE_ENUMERATOR), None, EVERYWHERE,
                                        byref(I_DEVICE_ENUMERATOR), byref(enumerator))
        if result < 0:
            raise OSError(f"no Windows audio service: {result & 0xFFFFFFFF:#x}")
        held.append(enumerator)
        _call(enumerator, GET_DEFAULT_DEVICE, SPEAKERS, MUSIC, byref(device),
              types=(c_int, c_int, POINTER(c_void_p)))
        held.append(device)
        _call(device, ACTIVATE, byref(interface), EVERYWHERE, None, byref(wanted),
              types=(POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p)))
        held.append(wanted)
        yield wanted
    finally:
        for thing in reversed(held):
            _call(thing, RELEASE)


def volume() -> int:
    """The speaker volume, 0-100."""
    level = c_float()
    with _speakers(I_ENDPOINT_VOLUME) as speakers:
        _call(speakers, GET_VOLUME, byref(level), types=(POINTER(c_float),))
    return round(level.value * 100)


def set_volume(percent: int) -> None:
    with _speakers(I_ENDPOINT_VOLUME) as speakers:
        _call(speakers, SET_VOLUME, c_float(min(100, max(0, percent)) / 100), None,
              types=(c_float, c_void_p))


def muted() -> bool:
    flag = wintypes.BOOL()
    with _speakers(I_ENDPOINT_VOLUME) as speakers:
        _call(speakers, GET_MUTE, byref(flag), types=(POINTER(wintypes.BOOL),))
    return bool(flag.value)


def set_muted(mute: bool) -> None:
    with _speakers(I_ENDPOINT_VOLUME) as speakers:
        _call(speakers, SET_MUTE, wintypes.BOOL(mute), None, types=(wintypes.BOOL, c_void_p))


def loudness() -> float:
    """How loud the speakers are playing right now, 0-1. 0 means silence.

    Measured before the mute switch, so it also shows that something is
    playing while the laptop is muted.
    """
    peak = c_float()
    with _speakers(I_METER) as meter:
        _call(meter, GET_PEAK, byref(peak), types=(POINTER(c_float),))
    return peak.value
