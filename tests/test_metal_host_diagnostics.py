"""Offline test that genuine host Metal errors survive the nested Windows subprocess."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine' / 'win'))
from metal_host_diagnostics import run_host_msl


class HostMetalDiagnosticsTests(unittest.TestCase):
    def run_helper(self, stdout, rc=1):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append((cmd, kwargs))
            return subprocess.CompletedProcess(cmd, rc, stdout)

        sink = io.StringIO()
        with redirect_stdout(sink):
            result = run_host_msl(['python', 'host_msl.py', '--sdk', 'iphoneos'],
                                  {'PYTHONPATH': 'win/pyshim'}, runner=fake_runner)
        return result, sink.getvalue(), calls

    def test_compiler_error_is_visible_in_build_log(self):
        code, output, calls = self.run_helper(
            "metal.exe: error: failed to compile dm/gfx/msl/present.metal\n"
            "host_msl.py: shader failed to compile\n", 1)
        self.assertEqual(code, 1)
        self.assertIn('metal.exe: error: failed to compile', output)
        self.assertIn('host_msl.py: shader failed', output)
        self.assertIn('helper exited with code 1', output)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]['stderr'], subprocess.STDOUT)
        self.assertEqual(calls[0][1]['stdout'], subprocess.PIPE)
        self.assertEqual(calls[0][1]['env']['PYTHONPATH'], 'win/pyshim')
        self.assertTrue(calls[0][1]['text'])
        self.assertEqual(calls[0][1]['errors'], 'replace')

    def test_failure_without_subprocess_text_is_explicit(self):
        code, output, _ = self.run_helper('', 2)
        self.assertEqual(code, 2)
        self.assertIn('exited without diagnostic output', output)
        self.assertIn('code 2', output)

    def test_success_prints_summary_once(self):
        code, output, _ = self.run_helper('host_msl.py: 8 libraries for iphoneos', 0)
        self.assertEqual(code, 0)
        self.assertIn('8 libraries', output)
        self.assertNotIn('diagnostics ----', output)

    def test_excessive_log_keeps_error_at_end(self):
        code, output, _ = self.run_helper('x' * 30000 + 'REAL ERROR AT END', 1)
        self.assertEqual(code, 1)
        self.assertIn('Showing the last 24,000', output)
        self.assertIn('REAL ERROR AT END', output)
        self.assertNotIn('x' * 30000, output)

    def test_windows_build_app_uses_diagnostic_wrapper(self):
        source = (ROOT / 'engine/win/build_app.py').read_text(encoding='utf-8')
        self.assertIn('from metal_host_diagnostics import run_host_msl', source)
        self.assertIn('if run_host_msl(msl_cmd, shim_env):', source)
        self.assertIn('see compiler diagnostics above in build_ipa.log', source)


if __name__ == '__main__':
    unittest.main()
