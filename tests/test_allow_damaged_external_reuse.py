"""HookLink X1/2.0 regression: damaged-extraction shader stage cache safety.

The 1.9.1 tests expected --allow-damaged to suppress cache creation. nxnative 2.0
intentionally changed that policy: reusing is allowed when the *exact* extraction
(and its damage manifest) and completed shader package are fingerprint-verified.
This test executes actual production split_shaders and fingerprint functions on
synthetic files. No copyrighted game files, network, or Metal SDK required.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'engine' / 'scripts' / 'build_ipa_from_nsp.py'
TABLES = ('shader_facts_manual.tsv', 'shader_map.tsv', 'shader_facts.tsv', 'shader_pairs.tsv', 'pso_pairs.tsv')


def production_functions(source, ns):
    tree = ast.parse(source.read_text(encoding='utf-8'))
    names = {'files_under', 'fingerprint', 'reused', 'package_key',
             'split_output_key', 'split_profile_inputs', 'split_shaders'}
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    found = {n.name for n in funcs}
    if names != found:
        raise AssertionError(f'missing production functions: {names - found}')
    ns['SPLIT_TABLES'] = TABLES
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(source), 'exec'), ns)
    return ns


class DamagedExtractionCachingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        profile = self.root / 'profile'
        profile.mkdir()
        for name in TABLES:
            (profile / name).write_text('synthetic shader rows\n', encoding='utf-8')
        self.game = types.SimpleNamespace(
            id='0400486024DEC000', dir=profile,
            table=lambda name: profile / name,
            get=lambda name, default='': default,
            modules_in=lambda folder: ['main'],
        )
        self.rom = self.root / 'extract' / 'RomFS'
        self.rom.mkdir(parents=True)
        self.content = self.rom / 'content.bin'
        self.content.write_bytes(b'original shader source')
        self.damage_manifest = self.rom.with_name('RomFS.img.formats')
        self.damage_manifest.write_text('damaged-texture.zs\n', encoding='utf-8')
        self.main = self.root / 'extract' / 'ExeFS' / 'main'
        self.main.parent.mkdir()
        self.main.write_bytes(b'synthetic-arm64-module')
        self.pkg = self.root / 'work' / 'shader' / 'pkg'
        self.pkg.parent.mkdir(parents=True)
        self.logs = self.root / 'work' / 'logs'
        self.logs.mkdir(parents=True)
        self.calls = []
        self.shaders = b'synthetic-shader-record-1'

    def run_split(self, allow_damaged=True, env=None):
        def run(args, logfile, env=None, on_line=None):
            self.calls.append(list(args))
            partial_pkg = Path(args[4])
            partial_pkg.mkdir(parents=True, exist_ok=True)
            (partial_pkg / 'shader.bin').write_bytes(self.shaders)
            tables = partial_pkg.parent / 'tables'
            for name in TABLES:
                shutil.copyfile(self.game.table(name), tables / name)
            Path(logfile).write_text('shaders: 1 (synthetic)\n', encoding='utf-8')

        def remove(path):
            path = Path(path)
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

        def swap(source, target):
            remove(target)
            os.replace(source, target)

        ns = production_functions(SOURCE, {
            'os': os, 'Path': Path, 'rfs': types.SimpleNamespace(os=os, Path=Path),
            'hashlib': hashlib, 're': re, 'subprocess': subprocess, 'shutil': shutil,
            'ALLOW_DAMAGED': allow_damaged, 'PROG': Mock(),
            'python_tool_files': lambda *a: [], 'run': run, 'rmtree': remove,
            'swap_in': swap, 'data_rows': lambda b: b.splitlines(),
            'table_difference': lambda *a: 'synthetic difference', 'say': lambda *a: None,
        })
        return ns['split_shaders']('python', self.root, [self.rom], [self.main],
                                   self.pkg, env or {}, self.logs, self.game)

    def test_damaged_mode_writes_stage_proof_and_reuses_identical_inputs(self):
        key1 = self.run_split(True)
        self.assertEqual(len(self.calls), 1)
        self.assertTrue((self.pkg.parent / 'pkg.key').is_file())
        self.assertTrue((self.pkg.parent / 'pkg.outputs.key').is_file())
        self.assertEqual(len(key1), 64, 'the completed package gets a SHA-256 key')
        self.assertEqual(key1, self.run_split(True))
        self.assertEqual(len(self.calls), 1, 'unchanged damaged extraction must reuse its package')

    def test_damage_manifest_change_invalidates_stage_reuse(self):
        self.run_split(True)
        self.damage_manifest.write_text('another-damaged-file.zs\n', encoding='utf-8')
        self.run_split(True)
        self.assertEqual(len(self.calls), 2, 'different damaged-file manifest must invalidate cache')

    def test_damaged_mode_checks_romfs_timestamps_and_output_integrity(self):
        self.run_split(True)
        stat = self.content.stat()
        os.utime(self.content, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
        self.run_split(True)
        self.assertEqual(len(self.calls), 2, 'new extraction timestamps must invalidate damaged cache')
        (self.pkg / 'shader.bin').write_bytes(b'corrupted shader cache')
        self.run_split(True)
        self.assertEqual(len(self.calls), 3, 'modified output package must invalidate cache')
        self.assertEqual((self.pkg / 'shader.bin').read_bytes(), self.shaders)

    def test_undamaged_mode_retains_normal_stage_cache(self):
        first = self.run_split(False)
        self.assertTrue(first)
        self.run_split(False)
        self.assertEqual(len(self.calls), 1)


if __name__ == '__main__':
    unittest.main()
