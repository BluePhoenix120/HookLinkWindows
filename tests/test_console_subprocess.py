"""Offline tests for the Windows build shim's child-console policy.

Extract and exercise the actual _popen_init function without importing the
entire monkey-patching shim into the test runner or invoking a compiler.
"""
import ast
import io
import os
from pathlib import Path
from types import SimpleNamespace
import unittest

SHIM = Path(__file__).resolve().parents[1] / 'engine' / 'win' / 'pyshim' / 'sitecustomize.py'

class ConsoleSubprocessTests(unittest.TestCase):
    def wrapper(self, platform='nt', environment=None):
        mod = ast.parse(SHIM.read_text(encoding='utf-8'), filename=str(SHIM))
        funcs = [n for n in ast.walk(mod) if isinstance(n, ast.FunctionDef) and n.name == '_popen_init']
        self.assertEqual(len(funcs), 1)
        called = []
        def capture(self_arg, args, *a, **k):
            called.append((self_arg, args, a, k))
        mocksp = SimpleNamespace(CREATE_NO_WINDOW=0x08000000, CREATE_NEW_CONSOLE=0x10, DETACHED_PROCESS=0x8)
        ns = dict(os=SimpleNamespace(name=platform, environ=environment or {}), subprocess=mocksp,
                  _map=lambda args: ['mapped-clang.exe', *args[1:]], _init=capture,
                  sys=SimpleNamespace(stderr=io.StringIO()))
        exec(compile(ast.Module(body=funcs, type_ignores=[]), str(SHIM), 'exec'), ns)
        return ns['_popen_init'], called

    def test_windows_child_is_hidden(self):
        fn, calls = self.wrapper()
        fn(object(), ['clang.exe', '-c', 'a.c'], stdout=-1, stderr=-1)
        self.assertEqual(calls[0][1], ['mapped-clang.exe', '-c', 'a.c'])
        self.assertEqual(calls[0][3]['creationflags'], 0x08000000)
        self.assertEqual(calls[0][3]['stdout'], -1)
        self.assertEqual(calls[0][3]['stderr'], -1)

    def test_existing_flags_are_preserved(self):
        fn, calls = self.wrapper()
        fn(object(), ['clang.exe'], creationflags=0x200)
        self.assertEqual(calls[0][3]['creationflags'], 0x08000200)

    def test_explicit_new_console_is_not_overridden(self):
        fn, calls = self.wrapper()
        fn(object(), ['clang.exe'], creationflags=0x10)
        self.assertEqual(calls[0][3]['creationflags'], 0x10)

    def test_explicit_detached_process_is_not_overridden(self):
        fn, calls = self.wrapper()
        fn(object(), ['clang.exe'], creationflags=0x8)
        self.assertEqual(calls[0][3]['creationflags'], 0x8)

    def test_debug_opt_out_keeps_windows_visible(self):
        fn, calls = self.wrapper(environment={'NXW_SHOW_CHILD_CONSOLES':'1'})
        fn(object(), ['clang.exe'])
        self.assertNotIn('creationflags', calls[0][3])

    def test_non_windows_behavior_is_unchanged(self):
        fn, calls = self.wrapper(platform='posix')
        fn(object(), ['clang.exe'])
        self.assertNotIn('creationflags', calls[0][3])

    def test_positional_creationflags_are_not_duplicated(self):
        fn, calls = self.wrapper()
        fn(object(), ['clang.exe'], *([None]*12 + [0x10]))
        self.assertNotIn('creationflags', calls[0][3])
        self.assertEqual(calls[0][2][12], 0x10)

    def test_source_is_valid_and_driver_propagates_shim(self):
        ast.parse(SHIM.read_text(encoding='utf-8'))
        driver=(SHIM.parent.parent/'build_ipa_windows.py').read_text(encoding='utf-8')
        self.assertIn("os.environ['PYTHONPATH']", driver)
        self.assertIn("_spec.loader.exec_module", driver)

if __name__=='__main__':
    unittest.main()
