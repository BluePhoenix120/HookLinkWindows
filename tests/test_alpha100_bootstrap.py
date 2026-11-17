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


if __name__ == '__main__':
    unittest.main()
