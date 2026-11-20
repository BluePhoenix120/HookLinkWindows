"""Windows Metal compiler admission control independent of shader job count.

Never alters the shader translation chain or compiled outputs. The budget
limits simultaneous compiler/linker operations and pauses new work when
physical RAM is scarce. Other platforms keep upstream behavior.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import os
import threading
import time


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ('dwLength', ctypes.c_ulong),
        ('dwMemoryLoad', ctypes.c_ulong),
        ('ullTotalPhys', ctypes.c_ulonglong),
        ('ullAvailPhys', ctypes.c_ulonglong),
        ('ullTotalPageFile', ctypes.c_ulonglong),
        ('ullAvailPageFile', ctypes.c_ulonglong),
        ('ullTotalVirtual', ctypes.c_ulonglong),
        ('ullAvailVirtual', ctypes.c_ulonglong),
        ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
    ]


def available_gib():
    """RAM available to Windows (not a sum of per-process working sets)."""
    if os.name != 'nt':
        return None
    info = _MemoryStatus()
    info.dwLength = ctypes.sizeof(info)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(info)):
        return None
    return info.ullAvailPhys / (1024 ** 3)


class _PerformanceInfo(ctypes.Structure):
    _fields_ = [
        ('cb', ctypes.c_ulong),
        ('CommitTotal', ctypes.c_size_t),
        ('CommitLimit', ctypes.c_size_t),
        ('CommitPeak', ctypes.c_size_t),
        ('PhysicalTotal', ctypes.c_size_t),
        ('PhysicalAvailable', ctypes.c_size_t),
        ('SystemCache', ctypes.c_size_t),
        ('KernelTotal', ctypes.c_size_t),
        ('KernelPaged', ctypes.c_size_t),
        ('KernelNonpaged', ctypes.c_size_t),
        ('PageSize', ctypes.c_size_t),
        ('HandleCount', ctypes.c_ulong),
        ('ProcessCount', ctypes.c_ulong),
        ('ThreadCount', ctypes.c_ulong),
    ]


def kernel_nonpaged_gib():
    """Optional kernel-pool diagnostic; was 3.6 GiB in the reported failure."""
    if os.name != 'nt':
        return None
    try:
        pi = _PerformanceInfo()
        pi.cb = ctypes.sizeof(pi)
        if ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(pi), ctypes.sizeof(pi)):
            return pi.KernelNonpaged * pi.PageSize / (1024 ** 3)
    except (OSError, AttributeError):
        pass
    return None


def _env_int(name, default, low, high):
    try:
        return max(low, min(high, int(os.environ.get(name, str(default)))))
    except (ValueError, OverflowError):
        return default


class MetalBudget:
    """Concurrency tokens for the expensive Metal compile AND metallib link.

    The upstream shader job pool (J, up to 61) is intentionally unchanged.
    A bounded number of compiler sessions (NXW_METAL_J) runs simultaneously.
    Admission additionally reserves free physical RAM (default 8 GiB).
    Cache hits do not consume tokens. All slots are released on exceptions.
    """

    def __init__(self, *, enabled=None, limit=None, min_available_gib=None,
                 available=None, timeout=180.0, notice=print):
        self.enabled = os.name == 'nt' if enabled is None else enabled
        self.limit = _env_int('NXW_METAL_J', 24, 1, 61) if limit is None else limit
        if not 1 <= self.limit <= 61:
            raise ValueError('Metal compiler concurrency must be 1–61')
        self.min_available_gib = (
            _env_int('NXW_METAL_MIN_FREE_GB', 8, 0, 128)
            if min_available_gib is None else min_available_gib
        )
        self.available = available or available_gib
        self.timeout = timeout
        self.notice = notice
        self._slots = threading.BoundedSemaphore(self.limit)
        self._lock = threading.Lock()
        self._active = 0
        self._high_water = 0
        self._last_report = 0.0
        self._announced = False

    def _log(self, message, *, force=False):
        with self._lock:
            now = time.monotonic()
            if force or now - self._last_report >= 30:
                self._last_report = now
                self.notice(message)

    @contextmanager
    def slot(self):
        if not self.enabled:
            yield
            return
        if not self._announced:
            with self._lock:
                if not self._announced:
                    self.notice('[METAL] shader workers unchanged; Metal compile/link cap=%d, RAM reserve=%d GiB' %
                                (self.limit, self.min_available_gib))
                    self._announced = True
        deadline = time.monotonic() + self.timeout
        active = False
        while not active:
            if self._slots.acquire(timeout=1):
                try:
                    free = self.available()
                except OSError:
                    free = None
                if free is None or free >= self.min_available_gib:
                    with self._lock:
                        self._active += 1
                        self._high_water = max(self._high_water, self._active)
                    active = True
                else:
                    self._slots.release()
                    self._log('[METAL] memory pressure: %.1f GiB available, reserve %d GiB; active compiler sessions=%d/%d; waiting without launching another compiler' %
                              (free, self.min_available_gib, self._active, self.limit))
            if not active:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        'Metal compilation paused: RAM remained below the configured reserve for %d seconds. '
                        'Completed shader cache entries are retained. Investigate memory pressure or reduce NXW_METAL_J.'
                        % self.timeout)
                time.sleep(0.25)
        free = self.available()
        nonpaged = kernel_nonpaged_gib()
        self._log('[METAL] active=%d/%d, high-water=%d; available RAM=%s GiB; kernel nonpaged=%s GiB' %
                  (self._active, self.limit, self._high_water,
                   ('%.1f' % free) if free is not None else 'unknown',
                   ('%.2f' % nonpaged) if nonpaged is not None else 'unknown'))
        try:
            yield
        finally:
            with self._lock:
                self._active -= 1
            self._slots.release()
