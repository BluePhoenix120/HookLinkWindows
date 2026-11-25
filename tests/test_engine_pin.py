"""Offline tests for the pinned NXNative source and commit shown in the GUI."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_engine_pin import github_repository_url, read_engine_pin


_PROJECT_PIN = json.loads((ROOT / 'ENGINE_PIN.json').read_text(encoding='utf-8'))
PIN = _PROJECT_PIN['nxnative_commit']
FORK = github_repository_url(_PROJECT_PIN['nxnative_repo'])
ORIGINAL = ('https://github.com/seedds/nxnative'
            if FORK == 'https://github.com/dsi-hub/nxnative'
            else 'https://github.com/dsi-hub/nxnative')
_ALLOWED_PINS = {
    '7ba845ab8b7e8f04639f179ee2adc6aad17ddfdf',
    '0b5fd6020093407af8bb5ad166e78e00bd2b7242',
    'd2fd78b402f92d5a83b78987e49aba22e8626719',
    '3ec5b785f37f8c87d78433f152914d89c4ef93c9',
    '3e1ada5b96acb61293ac790bd6dd093a947abed6',
    '5dfc86ae80c53a62262c3b3c66eab043f1fc574a',
}
assert PIN in _ALLOWED_PINS
assert FORK in ('https://github.com/dsi-hub/nxnative',
                'https://github.com/seedds/nxnative')


class EnginePinTests(unittest.TestCase):
    @staticmethod
    def create_pin(root, **changes):
        data = {
            'nxnative_commit': PIN,
            'engine_location': 'engine/',
            'nxnative_repo': FORK + '.git',
        }
        data.update(changes)
        (root / 'ENGINE_PIN.json').write_text(json.dumps(data), encoding='utf-8')

    def test_project_pin_matches_recorded_fork_and_base(self):
        pin = read_engine_pin(ROOT)
        self.assertEqual(pin.commit, PIN)
        self.assertEqual(pin.display, PIN)
        self.assertEqual(pin.repository, FORK)
        self.assertEqual(pin.url, FORK + '/commit/' + PIN)
        self.assertIn('Windows engine', pin.description)

    def test_repo_and_sha_are_loaded_from_current_checkout_not_hardcoded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            other = 'f' * 40
            self.create_pin(root, nxnative_commit=other,
                            nxnative_repo=ORIGINAL + '.git')
            pin = read_engine_pin(root)
            self.assertEqual(pin.commit, other)
            self.assertEqual(pin.repository, ORIGINAL)
            self.assertEqual(pin.url, ORIGINAL + '/commit/' + other)

    def test_github_https_clone_and_web_urls_normalized(self):
        self.assertEqual(github_repository_url(FORK + '.git'), FORK)
        self.assertEqual(github_repository_url(ORIGINAL), ORIGINAL)
        self.assertEqual(github_repository_url(FORK + '/'), FORK)

    def test_untrusted_or_invalid_repo_link_is_disabled_not_replaced(self):
        invalid_urls = (
            '', None, 123, 'https://evil.example/dsi-hub/nxnative.git',
            'https://github.com.evil.example/dsi-hub/nxnative',
            'http://github.com/dsi-hub/nxnative',
            'https://github.com/dsi-hub/nxnative/commit/ff',
            'https://github.com/dsi-hub/nxnative?redirect=1',
            'https://github.com/dsi-hub/nxnative#anchor',
            'https://user@github.com/dsi-hub/nxnative',
            'https://github.com:443/dsi-hub/nxnative',
            'https://github.com/dsi-hub/../nxnative',
            'https://github.com/dsi-hub/nxnative%2fevil',
            'https://github.com/dsi-hub/nxnative.git/other',
            'javascript:alert(1)',
        )
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for candidate in invalid_urls:
                with self.subTest(candidate=candidate):
                    self.assertIsNone(github_repository_url(candidate))
                    self.create_pin(root, nxnative_repo=candidate)
                    pin = read_engine_pin(root)
                    self.assertEqual(pin.commit, PIN)
                    self.assertIsNone(pin.url)
                    self.assertIn('invalid or unsupported', pin.description)

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

    def test_main_gui_renders_full_readonly_sha_and_validated_commit_link(self):
        gui = (ROOT / 'win/hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn('self.engine_pin = read_engine_pin(ROOT)', gui)
        self.assertIn('NXNative upstream base (pinned):', gui)
        self.assertIn("self.upstream_sha_var = tk.StringVar(value=self.engine_pin.display)", gui)
        self.assertIn("width=45, state='readonly'", gui)
        self.assertIn("text='View commit'", gui)
        self.assertIn('webbrowser.open_new_tab(self.engine_pin.url)', gui)
        self.assertIn("upstream_button.configure(state='disabled')", gui)

        release = json.loads((ROOT / 'ENGINE_PIN.json').read_text(encoding='utf-8'))['release']
        self.assertIn(f"GUI_VERSION = {release!r}", gui)


if __name__ == '__main__':
    unittest.main()
