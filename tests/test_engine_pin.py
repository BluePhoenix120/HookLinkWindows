"""Offline tests for pinned NXNative base provenance displayed by the main GUI."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_engine_pin import read_engine_pin


PIN = '3a28152fe7052c9f45ede460022d39be6c91e3cf'


class EnginePinTests(unittest.TestCase):
    @staticmethod
    def create_pin(root, **changes):
        data = {
            'nxnative_commit': PIN,
            'engine_location': 'engine/',
            'nxnative_repo': 'https://github.com/dsi-hub/nxnative.git',
        }
        data.update(changes)
        (root / 'ENGINE_PIN.json').write_text(json.dumps(data), encoding='utf-8')

    def test_project_pin_matches_recorded_upstream_base(self):
        pin = read_engine_pin(ROOT)
        self.assertEqual(pin.commit, PIN)
        self.assertEqual(pin.display, PIN)
        self.assertEqual(pin.url, 'https://github.com/seedds/nxnative/commit/' + PIN)
        self.assertIn('Windows engine', pin.description)

    def test_sha_is_loaded_from_current_checkout_not_live_upstream(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            other = 'f' * 40
            self.create_pin(root, nxnative_commit=other)
            pin = read_engine_pin(root)
            self.assertEqual(pin.commit, other)
            self.assertEqual(pin.url, 'https://github.com/seedds/nxnative/commit/' + other)

    def test_absent_corrupt_or_malformed_metadata_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pin = read_engine_pin(root)
            self.assertIsNone(pin.commit)
            self.assertIsNone(pin.url)
            (root / 'ENGINE_PIN.json').write_text('not json')
            self.assertIsNone(read_engine_pin(root).commit)
            for data in ([], {'nxnative_commit': 'short', 'engine_location': 'engine/'},
                         {'nxnative_commit': '../' + PIN, 'engine_location': 'engine/'},
                         {'nxnative_commit': PIN, 'engine_location': 'other/'},
                         {'nxnative_commit': PIN.upper(), 'engine_location': 'engine/'}):
                (root / 'ENGINE_PIN.json').write_text(json.dumps(data))
                with self.subTest(data=data):
                    self.assertIsNone(read_engine_pin(root).commit)

    def test_main_gui_renders_full_readonly_sha_and_commit_link(self):
        gui = (ROOT / 'win/hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn('self.engine_pin = read_engine_pin(ROOT)', gui)
        self.assertIn('NXNative upstream base (pinned):', gui)
        self.assertIn("self.upstream_sha_var = tk.StringVar(value=self.engine_pin.display)", gui)
        self.assertIn("width=45, state='readonly'", gui)
        self.assertIn("text='View commit'", gui)
        self.assertIn('webbrowser.open_new_tab(self.engine_pin.url)', gui)
        self.assertIn("GUI_VERSION = 'Alpha V1.0.7'", gui)


if __name__ == '__main__':
    unittest.main()
