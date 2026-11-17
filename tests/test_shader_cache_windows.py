"""Smoke and concurrency regressions for nxnative's Windows cache locking."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHIM = ROOT / 'engine' / 'win' / 'pyshim'
CACHE_TOOLS = ROOT / 'engine' / 'dm' / 'tools'


class ShaderCacheWindowsLockTests(unittest.TestCase):
    def test_windows_source_uses_explicit_fcntl_fallback(self):
        source = (CACHE_TOOLS / 'shader_cache.py').read_text(encoding='utf-8')
        self.assertIn('import nxw_flock as fcntl', source)
        self.assertEqual(source.count(".lock', 'a+')"), 2)

    @unittest.skipUnless(os.name == 'nt', 'Win32 locking only')
    def test_sqlite_cache_open_and_readwrite(self):
        sys.path.insert(0, str(SHIM))
        sys.path.insert(0, str(CACHE_TOOLS))
        import shader_cache
        with tempfile.TemporaryDirectory() as td:
            p = str(Path(td) / 'cas.db')
            s = shader_cache.Store(p)
            try:
                s.put('shader/test', b'content')
                self.assertEqual(s.get('shader/test'), b'content')
            finally:
                s.close()

    @unittest.skipUnless(os.name == 'nt', 'Win32 locking only')
    def test_shared_and_nonblocking_exclusive_between_processes(self):
        sys.path.insert(0, str(SHIM))
        import nxw_flock
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / 'cache.lock')
            code = ("import nxw_flock,sys; f=open(sys.argv[1], 'a+'); "
                    "nxw_flock.flock(f,nxw_flock.LOCK_SH); "
                    "print('READY',flush=True); sys.stdin.readline(); "
                    "nxw_flock.flock(f,nxw_flock.LOCK_UN); f.close()")
            env = os.environ.copy()
            env['PYTHONPATH'] = str(SHIM) + os.pathsep + env.get('PYTHONPATH', '')
            p = subprocess.Popen([sys.executable, '-B', '-c', code, path],
                                 env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(p.stdout.readline().strip(), 'READY',
                                 'Locking child could not acquire its initial shared lock')
                with open(path, 'a+') as second:
                    nxw_flock.flock(second, nxw_flock.LOCK_SH | nxw_flock.LOCK_NB)
                    nxw_flock.flock(second, nxw_flock.LOCK_UN)
                    with self.assertRaises(BlockingIOError):
                        nxw_flock.flock(second, nxw_flock.LOCK_EX | nxw_flock.LOCK_NB)
                p.stdin.write('\n'); p.stdin.flush()
                _, err = p.communicate(timeout=15)
                self.assertEqual(p.returncode, 0, err)
                with open(path, 'a+') as third:
                    nxw_flock.flock(third, nxw_flock.LOCK_EX | nxw_flock.LOCK_NB)
                    nxw_flock.flock(third, nxw_flock.LOCK_UN)
            finally:
                if p.poll() is None:
                    p.kill(); p.communicate(timeout=15)

    @unittest.skipUnless(os.name == 'nt', 'Win32 locking only')
    def test_bounded_cache_uses_lock_without_error(self):
        sys.path.insert(0, str(SHIM))
        sys.path.insert(0, str(CACHE_TOOLS))
        import shader_cache
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'cas.db'
            with shader_cache.bounded(path, 2 * 1024 * 1024):
                store = shader_cache.Store(path)
                store.put('shader/sample', b'sample')
                store.close()
            self.assertTrue(path.is_file())


if __name__ == '__main__':
    unittest.main()
