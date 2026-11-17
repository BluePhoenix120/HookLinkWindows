import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from shader_chain_flow import ChainPreflightError, run_build_chain_preflight

DUMMY = '''import pathlib,sys
root=pathlib.Path(__file__).resolve().parents[1]
state=root/'state.txt'
flag=sys.argv[-1]
if flag=='--sync':
    if (root/'sync_should_fail').exists():
        print('[ERROR] forced sync failure'); sys.exit(2)
    state.write_text('synced')
    print('[OK] Locally synchronized shader chain: abcdef123456'); sys.exit(0)
if (root/'force_error').exists():
    print('[ERROR] missing compiler'); sys.exit(2)
if not (root/'clean').exists() and not state.exists():
    print('Computed chain: deadbeef0000')
    print('[MISMATCH] host header differs')
    sys.exit(1)
print('Computed chain: abcdef123456')
print('[OK] Shader lock, host header and installed tools agree')
sys.exit(0)
'''

class TestChainFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = self.root / 'engine'
        (self.root / 'win').mkdir()
        self.engine.mkdir()
        (self.root / 'win' / 'shader_chain_prepare.py').write_text(DUMMY, encoding='utf-8')

    def run_check(self):
        return run_build_chain_preflight(self.root, self.engine, sys.executable, {})

    def test_valid_chain_does_not_sync(self):
        (self.root / 'clean').touch()
        result = self.run_check()
        self.assertEqual(result.chain, 'abcdef123456')
        self.assertFalse(result.synchronized)
        self.assertFalse((self.root / 'state.txt').exists())

    def test_mismatch_syncs_once_and_verifies(self):
        result = self.run_check()
        self.assertTrue(result.synchronized)
        self.assertIn('[READY] Shader chain abcdef123456', result.log)
        self.assertEqual((self.root / 'state.txt').read_text(), 'synced')
        second = self.run_check()
        self.assertFalse(second.synchronized)

    def test_compiler_error_fails_closed(self):
        (self.root / 'force_error').touch()
        with self.assertRaisesRegex(ChainPreflightError, 'exit code 2'):
            self.run_check()
        self.assertFalse((self.root / 'state.txt').exists())

    def test_sync_failure_blocks_build(self):
        (self.root / 'sync_should_fail').touch()
        with self.assertRaisesRegex(ChainPreflightError, 'synchronization failed'):
            self.run_check()

    def test_missing_helper_blocks_build(self):
        (self.root / 'win' / 'shader_chain_prepare.py').unlink()
        with self.assertRaisesRegex(ChainPreflightError, 'helper missing'):
            self.run_check()

    def test_gui_build_wires_preflight_before_spawn(self):
        gui=(ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn('run_build_chain_preflight(ROOT, c.root,', gui)
        self.assertIn("self.messages.put(('chain_ready', result))", gui)
        self.assertIn("elif typ == 'chain_ready':", gui)
        self.assertIn("self._spawn(plan.command, c.root", gui)
        self.assertEqual(gui.count("self._spawn(plan.command, c.root"), 1)

if __name__=='__main__':
    unittest.main()
