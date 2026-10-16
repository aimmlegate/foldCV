"""Continuous elapsed time, including system sleep, with an injectable deadline port."""

from __future__ import annotations

import asyncio
import ctypes
import sys
import time


def elapsed_seconds() -> float:
    if hasattr(time, "CLOCK_BOOTTIME"):
        return time.clock_gettime(time.CLOCK_BOOTTIME)
    if sys.platform == "darwin":
        return _continuous_ns() / 1_000_000_000
    raise RuntimeError("continuous elapsed clock is unsupported")


def _mac_clock():
    class Timebase(ctypes.Structure):
        _fields_ = [("numer", ctypes.c_uint32), ("denom", ctypes.c_uint32)]
    library = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    library.mach_continuous_time.restype = ctypes.c_uint64
    library.mach_continuous_time.argtypes = []
    info = Timebase()
    library.mach_timebase_info.argtypes = [ctypes.POINTER(Timebase)]
    library.mach_timebase_info.restype = ctypes.c_int
    if library.mach_timebase_info(ctypes.byref(info)) != 0 or not info.denom:
        raise RuntimeError("continuous clock timebase is unavailable")
    return lambda: library.mach_continuous_time() * info.numer // info.denom


_continuous_ns = _mac_clock() if sys.platform == "darwin" else None


class Deadlines:
    def now(self) -> float:
        return elapsed_seconds()

    async def wait(self, deadline: float):
        # Recheck continuous time when the event loop resumes after suspend.
        while self.now() < deadline:
            remaining = deadline - self.now()
            await asyncio.sleep(min(remaining, 1))


class ControlledDeadlines:
    def __init__(self):
        self.elapsed = 0.0
        self.waiters = []

    def now(self) -> float:
        return self.elapsed

    def advance(self, seconds: float):
        if seconds < 0:
            raise ValueError("elapsed clock cannot roll backwards")
        self.elapsed += seconds
        for deadline, future in list(self.waiters):
            if self.elapsed >= deadline and not future.done():
                future.set_result(None)

    async def wait(self, deadline: float):
        if self.elapsed >= deadline:
            return
        future = asyncio.get_running_loop().create_future()
        item = (deadline, future)
        self.waiters.append(item)
        try:
            await future
        finally:
            self.waiters.remove(item)

    def verify(self):
        if self.waiters:
            raise AssertionError("controlled deadline waiters leaked")
