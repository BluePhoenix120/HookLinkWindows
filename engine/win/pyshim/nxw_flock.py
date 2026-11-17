"""Windows implementation of the subset of fcntl.flock used by shader_cache.

Uses real Windows byte-range locks (LockFileEx/UnlockFileEx), including shared,
exclusive and non-blocking modes.  Lock bytes [0, 1) of the .lock file; callers
must open lock files with read/write access (a+), to permit shared locks.
Do not replace this with a no-op: several builders may share one cache.
"""

import ctypes
import msvcrt
from ctypes import wintypes

LOCK_SH = 1
LOCK_EX = 2
LOCK_NB = 4
LOCK_UN = 8

_LOCKFILE_FAIL_IMMEDIATELY = 0x00000001
_LOCKFILE_EXCLUSIVE_LOCK = 0x00000002
_ERROR_LOCK_VIOLATION = 33
_ERROR_IO_PENDING = 997


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ('Internal', ctypes.c_size_t),
        ('InternalHigh', ctypes.c_size_t),
        ('Offset', wintypes.DWORD),
        ('OffsetHigh', wintypes.DWORD),
        ('hEvent', wintypes.HANDLE),
    ]


_kernel = ctypes.WinDLL('kernel32', use_last_error=True)
_lock_file = _kernel.LockFileEx
_lock_file.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                       wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
_lock_file.restype = wintypes.BOOL
_unlock_file = _kernel.UnlockFileEx
_unlock_file.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                         wintypes.DWORD, ctypes.POINTER(_OVERLAPPED)]
_unlock_file.restype = wintypes.BOOL


def flock(file, operation):
    """Advisory cross-process shared/exclusive lock on the first byte of file."""
    fd = file if isinstance(file, int) else file.fileno()
    handle = msvcrt.get_osfhandle(fd)
    overlap = _OVERLAPPED()  # Offset=0, OffsetHigh=0, hEvent=NULL
    if operation == LOCK_UN:
        if not _unlock_file(handle, 0, 1, 0, ctypes.byref(overlap)):
            raise ctypes.WinError(ctypes.get_last_error())
        return
    mode = operation & (LOCK_SH | LOCK_EX)
    if mode not in (LOCK_SH, LOCK_EX):
        raise ValueError('Expected LOCK_SH, LOCK_EX or LOCK_UN')
    if operation & ~(LOCK_SH | LOCK_EX | LOCK_NB):
        raise ValueError('Unrecognized lock flags')
    flags = (_LOCKFILE_EXCLUSIVE_LOCK if mode == LOCK_EX else 0)
    if operation & LOCK_NB:
        flags |= _LOCKFILE_FAIL_IMMEDIATELY
    if not _lock_file(handle, flags, 0, 1, 0, ctypes.byref(overlap)):
        error = ctypes.get_last_error()
        if operation & LOCK_NB and error in (_ERROR_LOCK_VIOLATION, _ERROR_IO_PENDING):
            raise BlockingIOError(11, 'Shader cache lock is held by another process')
        raise ctypes.WinError(error)
