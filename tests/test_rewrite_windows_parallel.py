"""Synthetic scanner equivalence and automatic GUI-worker policy regression tests."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    instance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(instance)
    return instance


class AutoWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workers = module(ROOT / 'win/auto_workers.py', 'hlw_auto_workers')

    def test_cpu_limits(self):
        self.assertEqual(self.workers.logical_workers(32), 61)
        self.assertEqual(self.workers.logical_workers(64), 61)
        self.assertEqual(self.workers.logical_workers(1), 2)
        self.assertEqual(self.workers.logical_workers(None if False else 0), 1)

    def test_detected_count(self):
        with mock.patch.object(self.workers.os, 'cpu_count', return_value=20):
            self.assertEqual(self.workers.logical_workers(), 40)


class WindowsRewriteScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scan = module(ROOT / 'engine/win/rewrite_parallel.py', 'hlw_rewrite_scan')

    def test_scan_rejects_invalid_ranges(self):
        with self.assertRaises(ValueError):
            self.scan.scan_x18(bytearray(128), [(0, 129)], 2)
        with self.assertRaises(ValueError):
            self.scan.scan_x18(bytearray(128), [(0, 20)], 0)

    def test_scan_matches_sequential_with_independent_workers(self):
        with tempfile.TemporaryDirectory() as td:
            # A fake subset of the capstone disasm_lite API makes this test independent
            # of SDK installs. The real build uses its installed Capstone 5.
            fake = '''CS_ARCH_ARM64=1\nCS_MODE_ARM=0\nclass Cs:\n    def __init__(self,*args): pass\n    def disasm_lite(self,data,base):\n        for i in range(0,len(data)-3,4):\n            word=data[i:i+4]\n            operand='x18' if word == b"\\x12\\x34\\x56\\x78" else 'x0'\n            yield base+i,4,'mov',operand\n'''
            Path(td, 'capstone.py').write_text(fake, encoding='utf-8')
            old = os.environ.get('PYTHONPATH')
            os.environ['PYTHONPATH'] = td + (os.pathsep + old if old else '')
            try:
                word_x18 = bytes.fromhex('12345678')
                regular = bytes.fromhex('00000000')
                image = bytearray((regular * 4095 + word_x18) * 4)
                ranges = [(i, i + 16384) for i in range(0, len(image), 16384)]
                serial = self.scan.scan_x18(image, ranges, 1)
                multi = self.scan.scan_x18(image, ranges, 4)
                self.assertEqual(serial, multi)
                self.assertEqual(multi, {16380, 32764, 49148, 65532})
            finally:
                if old is None: os.environ.pop('PYTHONPATH', None)
                else: os.environ['PYTHONPATH'] = old


if __name__ == '__main__':
    unittest.main()
