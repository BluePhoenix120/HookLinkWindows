"""Windows compiler lifetime containment via a kill-on-close Job Object.

The builder joins its own Job Object before it starts any compiler children.
Windows automatically assigns its descendants to that job (unless a child
explicitly breaks away). When the builder exits or crashes, Windows closes
its private job handle and terminates any remaining associated processes.

This is NOT a remedy for leaks in the Windows kernel or a device driver.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import os

KILL_ON_JOB_CLOSE = 0x2000
EXTENDED_LIMIT_INFORMATION = 9
_live_job = None


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ('per_process_user_time_limit', ctypes.c_int64),
        ('per_job_user_time_limit', ctypes.c_int64),
        ('limit_flags', ctypes.c_uint32),
        ('minimum_working_set_size', ctypes.c_size_t),
        ('maximum_working_set_size', ctypes.c_size_t),
        ('active_process_limit', ctypes.c_uint32),
        ('affinity', ctypes.c_size_t),
        ('priority_class', ctypes.c_uint32),
        ('scheduling_class', ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ('read_operation_count', ctypes.c_uint64),
        ('write_operation_count', ctypes.c_uint64),
        ('other_operation_count', ctypes.c_uint64),
        ('read_transfer_count', ctypes.c_uint64),
        ('write_transfer_count', ctypes.c_uint64),
        ('other_transfer_count', ctypes.c_uint64),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ('basic_limit_information', _BasicLimit),
        ('io_info', _IoCounters),
        ('process_memory_limit', ctypes.c_size_t),
        ('job_memory_limit', ctypes.c_size_t),
        ('peak_process_memory_used', ctypes.c_size_t),
        ('peak_job_memory_used', ctypes.c_size_t),
    ]


def protect_builder_tree(kernel=None):
    """Attach this builder before children launch; keep the handle until exit.

    Failure is nonfatal because Job Object nesting/permissions can interfere
    on some hosts. A warning is emitted instead of claiming containment.
    A kernel argument supports deterministic tests on non-Windows systems.
    """
    global _live_job
    if _live_job is not None:
        return True
    if os.name != 'nt' and kernel is None:
        return False
    if kernel is None:
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = wintypes.HANDLE
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = handle
        kernel.SetInformationJobObject.argtypes = [handle, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.SetInformationJobObject.restype = wintypes.BOOL
        kernel.GetCurrentProcess.argtypes = []
        kernel.GetCurrentProcess.restype = handle
        kernel.AssignProcessToJobObject.argtypes = [handle, handle]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [handle]
        kernel.CloseHandle.restype = wintypes.BOOL
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        print('[JOB] Warning: could not create a compiler Job Object; error=%d' %
              getattr(ctypes, 'get_last_error', lambda: 0)(), flush=True)
        return False
    try:
        limits = _ExtendedLimits()
        limits.basic_limit_information.limit_flags = KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(job, EXTENDED_LIMIT_INFORMATION,
                                               ctypes.byref(limits), ctypes.sizeof(limits)):
            raise OSError('SetInformationJobObject failed')
        if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
            raise OSError('AssignProcessToJobObject failed (possibly nested job restrictions)')
    except OSError as exc:
        err = getattr(ctypes, 'get_last_error', lambda: 0)()
        kernel.CloseHandle(job)
        print('[JOB] Warning: %s; compiler process containment unavailable (error=%d)' %
              (exc, err), flush=True)
        return False
    _live_job = job
    print('[JOB] Kill-on-close containment active; builder exit automatically terminates remaining compiler descendants', flush=True)
    return True
