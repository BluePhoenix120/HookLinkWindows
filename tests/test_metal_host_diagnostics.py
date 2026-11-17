"""Offline test that genuine host Metal errors survive the nested Windows subprocess."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import tempfile
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
        self.assertIn('if run_host_msl(msl_cmd, shim_env, output_path=msl,', source)
        self.assertIn('source_paths=msl_sources, staging_parent=staging', source)
        self.assertIn('see compiler diagnostics above in build_ipa.log', source)


class HostMetalWhitespaceTests(unittest.TestCase):
    """Use a fake compiler; no SDK, Metal tools, or game data required."""

    def setup_case(self, root):
        src_dir = root / 'New folder' / 'engine' / 'dm' / 'gfx' / 'msl'
        src_dir.mkdir(parents=True, exist_ok=True)
        builtin = src_dir / 'builtin.metal'
        builtin.write_text('#include "local.h"\nkernel void test() {}\n', encoding='utf-8')
        (src_dir / 'local.h').write_text('// include stays beside source\n', encoding='utf-8')
        output = root / 'New folder' / 'engine' / 'dm' / 'host' / 'gen' / 'host_msl_gen.h'
        cmd = ['python', 'host_msl.py', '--sdk', 'iphoneos', '--min', '26.0', str(output), str(builtin)]
        return cmd, output, builtin

    def test_staging_avoids_spaces_in_metal_arguments_and_temporary_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cmd, output, original = self.setup_case(root)
            original_bytes = original.read_bytes()
            recorded = []

            def fake_runner(argv, **kwargs):
                recorded.append((argv, kwargs))
                header = Path(argv[-2])
                metal_src = Path(argv[-1])
                self.assertFalse(any(c.isspace() for c in str(header)))
                self.assertFalse(any(c.isspace() for c in str(metal_src)))
                self.assertEqual(metal_src.read_bytes(), original_bytes)
                self.assertTrue((metal_src.parent / 'local.h').is_file())
                for key in ('TMP', 'TEMP', 'TMPDIR'):
                    self.assertFalse(any(c.isspace() for c in kwargs['env'][key]))
                header.write_text('// generated successful header\n', encoding='utf-8')
                return subprocess.CompletedProcess(argv, 0, 'compiled shaders')

            output_capture = io.StringIO()
            with redirect_stdout(output_capture):
                rc = run_host_msl(cmd, {'PYTHONPATH': 'shim with space'},
                                  runner=fake_runner, output_path=output,
                                  source_paths=[original],
                                  staging_parent=root / 'CleanBuild', force_stage=True)
            self.assertEqual(rc, 0)
            self.assertEqual(len(recorded), 1)
            self.assertEqual(output.read_text(encoding='utf-8'),
                             '// generated successful header\n')
            self.assertEqual(original.read_bytes(), original_bytes)
            self.assertIn('space-free staging', output_capture.getvalue())

    def test_failed_staged_compile_does_not_replace_existing_header(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cmd, output, original = self.setup_case(root)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('last good header', encoding='utf-8')

            def failing_runner(argv, **kwargs):
                # A failing helper may leave partial staged output; it must
                # never replace the working checkout's generated header.
                Path(argv[-2]).write_text('bad header', encoding='utf-8')
                return subprocess.CompletedProcess(argv, 1, 'metal.exe: invalid path')

            with redirect_stdout(io.StringIO()) as stream:
                rc = run_host_msl(cmd, {}, runner=failing_runner, output_path=output,
                                  source_paths=[original], staging_parent=root / 'CleanBuild',
                                  force_stage=True)
            self.assertEqual(rc, 1)
            self.assertEqual(output.read_text(encoding='utf-8'), 'last good header')
            self.assertIn('metal.exe: invalid path', stream.getvalue())

    def test_success_with_same_header_preserves_timestamp_for_compile_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cmd, output, original = self.setup_case(root)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('unchanged compiled header', encoding='utf-8')
            before = output.stat().st_mtime_ns

            def fake_runner(argv, **kwargs):
                Path(argv[-2]).write_text('unchanged compiled header', encoding='utf-8')
                return subprocess.CompletedProcess(argv, 0, '')

            rc = run_host_msl(cmd, {}, runner=fake_runner, output_path=output,
                              source_paths=[original], staging_parent=root / 'CleanBuild',
                              force_stage=True)
            self.assertEqual(rc, 0)
            self.assertEqual(output.stat().st_mtime_ns, before)

    def test_staging_compiler_missing_header_reports_error(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cmd, output, original = self.setup_case(root)
            def fake_runner(argv, **kwargs):
                return subprocess.CompletedProcess(argv, 0, '')
            output_capture = io.StringIO()
            with redirect_stdout(output_capture):
                rc = run_host_msl(cmd, {}, runner=fake_runner, output_path=output,
                                  source_paths=[original],
                                  staging_parent=root / 'CleanBuild', force_stage=True)
            self.assertEqual(rc, 1)
            self.assertIn('generated no header', output_capture.getvalue())
            self.assertFalse(output.exists())

    def test_no_staging_without_source_details_maintains_old_behavior(self):
        calls = []
        def fake_runner(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, 'OK')
        with redirect_stdout(io.StringIO()):
            self.assertEqual(run_host_msl(['python', 'helper.py'], {}, runner=fake_runner), 0)
        self.assertEqual(calls, [['python', 'helper.py']])


if __name__ == '__main__':
    unittest.main()
