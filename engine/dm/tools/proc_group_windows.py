"""Windows process-tree supervision for the official NXnative builder."""
import ctypes as C
from ctypes import wintypes as W
import io
import json
import locale
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

if os.name != 'nt':
    raise ImportError("Windows backend requires Windows")
K = C.WinDLL('kernel32', use_last_error=True)

def api(name, args, result=W.BOOL):
    f = getattr(K, name)
    f.argtypes, f.restype = args, result
    return f

create = api('CreateJobObjectW', [C.c_void_p, W.LPCWSTR], W.HANDLE)
setinfo = api('SetInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD])
query = api('QueryInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)])
assign = api('AssignProcessToJobObject', [W.HANDLE, W.HANDLE])
terminate = api('TerminateJobObject', [W.HANDLE, W.UINT])
close = api('CloseHandle', [W.HANDLE])

class BasicLimit(C.Structure):
    _fields_ = [('PerProcessUserTimeLimit', C.c_int64), ('PerJobUserTimeLimit', C.c_int64),
                ('LimitFlags', W.DWORD), ('MinimumWorkingSetSize', C.c_size_t),
                ('MaximumWorkingSetSize', C.c_size_t), ('ActiveProcessLimit', W.DWORD),
                ('Affinity', C.c_size_t), ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]

class ExtendedLimit(C.Structure):
    _fields_ = [('BasicLimitInformation', BasicLimit), ('IoInfo', C.c_uint64 * 6),
                *[(n, C.c_size_t) for n in ('ProcessMemoryLimit', 'JobMemoryLimit',
                                           'PeakProcessMemoryUsed', 'PeakJobMemoryUsed')]]

class Accounting(C.Structure):
    _fields_ = [(n, C.c_int64) for n in ('TotalUserTime', 'TotalKernelTime',
                'ThisPeriodTotalUserTime', 'ThisPeriodTotalKernelTime')] + [
                (n, W.DWORD) for n in ('TotalPageFaultCount', 'TotalProcesses',
                'ActiveProcesses', 'TotalTerminatedProcesses')]

def checked(ok):
    if not ok:
        raise C.WinError(C.get_last_error())

# Gate the worker before it can spawn the tool. A deadline also bounds an
# orphaned launcher if the parent dies before assigning the process to the job.
LAUNCH = """import json,pathlib,subprocess,sys,time
p=pathlib.Path(sys.argv[1]); deadline=time.monotonic()+30
while not (p/'ready').exists():
    if time.monotonic()>deadline: sys.exit(1)
    time.sleep(.01)
sys.exit(subprocess.call(json.loads((p/'args.json').read_text(encoding='utf-8'))))
"""

class Group:
    def __init__(self, cmd, grace=None, drain=None, **popen):
        self.grace = 5.0 if grace is None else grace
        self.drain = 5.0 if drain is None else drain
        self.done, self.paused, self.stragglers = False, False, []
        self.p, self.tmp = None, None
        self.job = create(None, None)
        if not self.job: raise C.WinError(C.get_last_error())
        try:
            lim = ExtendedLimit()
            lim.BasicLimitInformation.LimitFlags = 0x2000
            checked(setinfo(self.job, 9, C.byref(lim), C.sizeof(lim)))
            self.tmp = tempfile.TemporaryDirectory(prefix='nxw-job-')
            root = Path(self.tmp.name)
            (root/'args.json').write_text(json.dumps([str(c) for c in cmd]), encoding='utf-8')
            self.p = subprocess.Popen([sys.executable, '-c', LAUNCH, str(root)], **popen)
            self.pgid = self.p.pid
            checked(assign(self.job, W.HANDLE(int(self.p._handle))))
            (root/'ready').touch()
        except BaseException:
            try:
                if self.p is not None:
                    self.p.kill()
                    self.p.wait()
                    if self.p.stdout: self.p.stdout.close()
            finally: self._close()
            raise

    def _active(self):
        if not self.job: return 0
        a = Accounting()
        checked(query(self.job, 1, C.byref(a), C.sizeof(a), None))
        return a.ActiveProcesses

    def _close(self):
        if self.job:
            h, self.job = self.job, None
            checked(close(h))
        if self.tmp is not None:
            self.tmp.cleanup()
            self.tmp = None

    def _kill(self):
        if self.job and self._active():
            checked(terminate(self.job, 1))

    def __enter__(self): return self

    def __exit__(self, kind, exc, tb):
        try:
            if kind is not None: self.stop()
            elif not self.done: self.finish()
        finally:
            if self.p.stdout: self.p.stdout.close()
            self._close()
        return False

    def stop(self, sig=None): stop_all([self], sig)

    def finish(self):
        self.p.wait()
        deadline = time.monotonic() + self.drain
        while self._active() and time.monotonic() < deadline:
            time.sleep(.05)
        if self._active():
            self.stragglers.append((None, 'descendants in Windows Job Object'))
            self.stop()
        else:
            self.done = True
            self._close()
        return self.p.returncode

    def lines(self):
        assert self.p.stdout is not None
        q = queue.Queue(maxsize=128)
        cancel = threading.Event()
        sentinel = object()
        def send(x):
            while not cancel.is_set():
                try: q.put(x, timeout=.1); return
                except queue.Full: pass
        def read():
            try:
                stream = io.TextIOWrapper(self.p.stdout, encoding=locale.getpreferredencoding(False),
                                          errors='replace', newline=None)
                try:
                    for line in stream:
                        if cancel.is_set(): break
                        send(line)
                finally: stream.detach()
            except (OSError, ValueError) as exc:
                send(exc)
            finally: send(sentinel)
        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        end = None
        try:
            while True:
                try: item = q.get(timeout=.1)
                except queue.Empty: item = None
                if item is sentinel: break
                if isinstance(item, BaseException): raise item
                if item is not None: yield item
                if self.p.poll() is not None:
                    if end is None: end = time.monotonic() + self.drain
                    if time.monotonic() >= end and self._active():
                        self.stragglers.append((None, 'descendants in Windows Job Object'))
                        self._kill()
                        end = time.monotonic() + 2
                    elif time.monotonic() >= end and item is None:
                        self.stragglers.append((None, 'process holding tool output'))
                        break
        finally:
            cancel.set()
            if thread.is_alive():
                if not self.done: self._kill()
                thread.join(timeout=2)

    def pause(self):
        raise NotImplementedError('Windows backend does not implement benchmark pause')

    def resume(self): self.paused = False

def stop_all(groups, sig=None):
    groups = list(groups)
    first = None
    for g in groups:
        try: g._kill()
        except BaseException as exc:
            if first is None: first = exc
    for g in groups:
        try:
            g._close()
            g.p.wait(timeout=10)
            g.done = True
        except BaseException as exc:
            if first is None: first = exc
    if first is not None: raise first
