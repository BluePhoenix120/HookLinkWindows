"""Enforce the pinned X2 NXNative delta against the vendored Windows engine.

A complete upstream commit is too broad to compare byte-for-byte with this
Windows port because Windows-only files and edits intentionally exist.
Instead, exact upstream Git object hashes are checked for every file changed
by the pinned X2 import. No network or Git executable is needed by this test.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
OLD_PIN = '3a28152fe7052c9f45ede460022d39be6c91e3cf'
X2_PIN = '7ba845ab8b7e8f04639f179ee2adc6aad17ddfdf'


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()


class PinnedEngineDeltaTests(unittest.TestCase):
    def test_engine_x2_delta_is_fully_present_when_pin_is_x2(self):
        pin = json.loads((ROOT / 'ENGINE_PIN.json').read_text(encoding='utf-8'))
        sha = pin['nxnative_commit']
        manifest_path = ROOT / 'ENGINE_PIN_FILES.json'
        if sha == OLD_PIN and not manifest_path.exists():
            self.skipTest('Pre-X2 source snapshot; engine sync workflow has not run yet')
        self.assertEqual(sha, X2_PIN)
        self.assertTrue(manifest_path.is_file(), 'X2 engine manifest missing')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(manifest['nxnative_commit'], sha)
        self.assertEqual(manifest['from_commit'], OLD_PIN)
        self.assertEqual(manifest['nxnative_repo'], pin['nxnative_repo'])
        files = manifest['changed_paths']
        self.assertEqual(len(files), 25)
        self.assertEqual(len({x['path'] for x in files}), len(files))
        for row in files:
            path = row['path']
            self.assertTrue(path.startswith('engine/dm/') or path.startswith('engine/docs/'))
            full = ROOT / path
            self.assertTrue(full.is_file(), path)
            raw_bytes = full.read_bytes()
            committed_hash = git_blob_sha(raw_bytes)
            if committed_hash != row['sha']:
                # Git for Windows commonly expands LF to CRLF in the working
                # tree, while the committed upstream Git blob retains LF.
                # Validate the canonical bytes as well, without weakening
                # the test for any content changes other than line endings.
                committed_hash = git_blob_sha(raw_bytes.replace(b'\r\n', b'\n'))
            self.assertEqual(committed_hash, row['sha'], path)

    def test_launcher_uses_live_engine_pin_for_commit_button(self):
        source = (ROOT / 'win/hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn('self.engine_pin = read_engine_pin(ROOT)', source)
        self.assertIn('webbrowser.open_new_tab(self.engine_pin.url)', source)
        self.assertNotIn('3a28152fe7052c9f45ede460022d39be6c91e3cf/commit/', source)


if __name__ == '__main__':
    unittest.main()
