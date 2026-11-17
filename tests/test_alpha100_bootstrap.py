"""Platform-neutral unit checks for the Alpha V1.0.0 Windows translator bootstrap.

These tests do not invoke dotnet, change the shader chain, or require Apple SDKs.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BOOT = Path(__file__).resolve().parents[1] / 'win' / 'bootstrap_translator.py'
spec = importlib.util.spec_from_file_location('hlw_alpha_bootstrap', BOOT)
bootstrap = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bootstrap)


class TestAlphaTranslatorBootstrap(unittest.TestCase):
    def test_source_fingerprint_is_ordered_raw_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder)
            (src / 'Program.cs').write_bytes(b'hello\r\n')
            (src / 'dmsh_xlate.csproj').write_bytes(b'project\n')
            import hashlib
            digest = hashlib.sha256(b'hello\r\nproject\n').hexdigest()[:16]
            self.assertEqual(bootstrap.source_sha(src), digest)

    def test_portable_root_paths(self):
        root = Path('C:/TestCheckout')
        names = bootstrap.paths(root)
        self.assertEqual(names['project'], root / 'engine/dm/gfx/tools/dmsh_xlate')
        self.assertEqual(names['header'], root / 'engine/dm/gfx/nvn/dmsh_chain.h')

    def test_explicit_spirv_tool_must_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            fake = Path(folder) / 'spirv-cross.exe'
            with self.assertRaisesRegex(RuntimeError, 'SPIRV-Cross missing'):
                bootstrap.locate_spirv(None, str(fake))
            fake.write_bytes(b'fake binary')
            self.assertEqual(bootstrap.locate_spirv(None, str(fake)), fake.resolve())

    def test_missing_consent_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with mock.patch.object(bootstrap, 'inspect', return_value=({}, {'ready': False})):
                with self.assertRaisesRegex(RuntimeError, 'accept-new-chain'):
                    bootstrap.install(root, None, False)
            self.assertEqual(list(root.iterdir()), [])

    def test_already_verified_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with mock.patch.object(bootstrap, 'inspect', return_value=({}, {'ready': True})):
                bootstrap.install(root, None, False)
            self.assertEqual(list(root.iterdir()), [])

    def test_no_git_metadata_requires_no_clean_state_check(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bootstrap.ensure_clean_tracked_state({'root': root})

    def test_hidden_process_options_windows(self):
        from types import SimpleNamespace
        startup = SimpleNamespace(dwFlags=0, wShowWindow=-1)
        with mock.patch.object(bootstrap.os, 'name', 'nt'), \
             mock.patch.object(bootstrap.subprocess, 'STARTUPINFO', return_value=startup, create=True), \
             mock.patch.object(bootstrap.subprocess, 'STARTF_USESHOWWINDOW', 1, create=True), \
             mock.patch.object(bootstrap.subprocess, 'SW_HIDE', 0, create=True), \
             mock.patch.object(bootstrap.subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True):
            options = bootstrap.hidden_process_options()
        self.assertEqual(options['creationflags'], 0x08000000)
        self.assertEqual(options['startupinfo'].dwFlags, 1)
        self.assertEqual(options['startupinfo'].wShowWindow, 0)

    def test_hidden_process_options_non_windows(self):
        with mock.patch.object(bootstrap.os, 'name', 'posix'):
            self.assertEqual(bootstrap.hidden_process_options(), {})

    def test_dotnet_build_disables_background_servers_without_global_settings(self):
        with mock.patch.dict(bootstrap.os.environ, {'SAMPLE': 'kept', 'DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER': '0'}, clear=True):
            env = bootstrap.isolated_dotnet_build_environment()
            self.assertEqual(env['SAMPLE'], 'kept')
            self.assertEqual(env['DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER'], '1')
            self.assertEqual(env['MSBUILDDISABLENODEREUSE'], '1')
            self.assertEqual(bootstrap.os.environ['DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER'], '0')

    def test_clean_git_checks_use_hidden_process_options(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.git').mkdir()
            with mock.patch.object(bootstrap.shutil, 'which', return_value='git'), \
                 mock.patch.object(bootstrap, 'hidden_process_options', return_value={'creationflags': 0x08000000}), \
                 mock.patch.object(bootstrap.subprocess, 'run') as runner:
                runner.return_value.returncode = 0
                bootstrap.ensure_clean_tracked_state({'root': root})
                self.assertEqual(runner.call_count, 2)
                self.assertTrue(all(call.kwargs.get('creationflags') == 0x08000000 for call in runner.call_args_list))


if __name__ == '__main__':
    unittest.main()
