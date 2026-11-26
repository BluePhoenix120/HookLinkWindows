"""Regression tests for build-time code and packed RomFS mods."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine/dm/tools'))
sys.path.insert(0, str(ROOT / 'engine/win'))
sys.path.insert(0, str(ROOT / 'win'))
import romfs
import mods
from mod_romfs import overlay_image
from hooklink_gui_core import BuildConfig, make_build_environment, find_transfer_sources, prepare_transfer_folder
from hooklink_portable import SettingsStore


def synthetic_image(path):
    # Breadth-first root -> Model, System -> body, stock RESTBL.
    data = b'old' + b'original table'
    rows = [(b'', 1, 2, 0, 0),
            (b'Model', 3, 1, 0, 0),
            (b'System', 4, 1, 0, 0),
            (b'body', romfs.HEAD.size, 3, 1, 1),
            (b'table.rsizetable.zs', romfs.HEAD.size + 3, len(b'original table'), 1, 0)]
    names, index = bytearray(), bytearray()
    for name, a, b, kind, flags in rows:
        index.extend(romfs.ENT.pack(a, b, len(names), len(name), kind, flags))
        names.extend(name)
    path.write_bytes(romfs.HEAD.pack(romfs.MAGIC, romfs.HEAD.size + len(data),
                                     len(index) + len(names), len(rows)) + data + index + names)


class BuildTimeModsTests(unittest.TestCase):
    def test_packed_overlay_adds_files_preserves_restbl_and_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'stock.img'
            synthetic_image(source)
            old = source.read_bytes()
            folder = root / 'mod'
            (folder / 'Model').mkdir(parents=True)
            (folder / 'System').mkdir()
            (folder / 'Model/body').write_bytes(b'new outfit')
            (folder / 'Model/new').write_bytes(b'extra')
            (folder / 'System/table.rsizetable.zs').write_bytes(b'new table')
            result = overlay_image(source, [folder], root / 'out', log=lambda _: None)
            self.assertEqual(source.read_bytes(), old)
            image = romfs.Image(result)
            self.assertEqual(image.entry(image.find('Model/body'))[-1], 0)
            with result.open('rb') as f:
                for name, expected in [('Model/body', b'new outfit'), ('Model/new', b'extra'),
                                       ('System/table.rsizetable.zs', b'new table')]:
                    off, size, *_ = image.entry(image.find(name))
                    f.seek(off)
                    self.assertEqual(f.read(size), expected)
            self.assertEqual(overlay_image(source, [folder], root / 'out', log=lambda _: None), result)
            (folder / 'Model/body').write_bytes(b'another outfit')
            self.assertNotEqual(overlay_image(source, [folder], root / 'out', log=lambda _: None), result)
            self.assertEqual(source.read_bytes(), old)

    def test_shader_mod_and_conflicting_paths_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'stock.img'; synthetic_image(source)
            a = root / 'a'; b = root / 'b'
            (a / 'Model').mkdir(parents=True); (b / 'Model').mkdir(parents=True)
            (a / 'Model/body').write_bytes(b'a'); (b / 'Model/body').write_bytes(b'b')
            with self.assertRaisesRegex(ValueError, 'Multiple mods'):
                overlay_image(source, [a, b], root / 'out')
            (a / 'Shader').mkdir(); (a / 'Shader/change.bin').write_bytes(b'x')
            with self.assertRaisesRegex(ValueError, 'shader inputs'):
                overlay_image(source, [a], root / 'out')

    def test_ips32_and_exact_build_validation(self):
        data = b'IPS32' + (0x104).to_bytes(4, 'big') + b'\x00\x04abcdEEOF'
        self.assertEqual(mods.parse_ips(data), [(0x104, b'abcd')])
        with self.assertRaises(ValueError): mods.parse_ips(data[:-1])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bid = 'e0f3ccfaf50065ae4ea01eb5aeb13b1a'
            folder = root / 'LensPatch/exefs'; folder.mkdir(parents=True)
            p = folder / (bid + '45da3348.ips'); p.write_bytes(data)
            with patch.object(mods, 'module_images', return_value={bid: ('main', bytes(16), 16)}):
                cuts = mods.cuts_for([p], root, ['main'], log=lambda _: None)
                self.assertEqual(cuts[bid][0][:3], [4, '00000000', '61626364'])
                with self.assertRaisesRegex(ValueError, 'overlapping'):
                    mods.cuts_for([p, p], root, ['main'], log=lambda _: None)
                wrong = folder / ('a' * 40 + '.ips'); wrong.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'does not match'):
                    mods.cuts_for([wrong], root, ['main'], log=lambda _: None)
            (folder / 'subsdk1').write_bytes(b'unsupported')
            with self.assertRaisesRegex(ValueError, 'Unsupported ExeFS module'):
                mods.find(root)

    def test_gui_transfer_uses_modded_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'extract/base').mkdir(parents=True)
            (root / 'shader/ios').mkdir(parents=True)
            (root / 'extract/base/RomFS.img').write_bytes(b'stock')
            (root / 'shader/ios/b-123456789abc.img').write_bytes(b'shader')
            mod = root / 'modified.img'; mod.write_bytes(b'modded')
            env = root / 'settings.env'; env.write_text('setting=1')
            folder = prepare_transfer_folder(root, env, root / 'transfer', '123456789abc',
                                             romfs_override=mod)
            self.assertEqual((folder / 'RomFS.img').read_bytes(), b'modded')
            self.assertEqual(find_transfer_sources(root, env)['RomFS.img'].read_bytes(), b'stock')
            cfg = BuildConfig(root, root/'game.nup', root, env, root/'out.ipa', 'org.example.game',
                              mods_dir=root)
            self.assertEqual(make_build_environment(cfg)['NXW_MODS_DIR'], str(root.resolve()))
            cfg = BuildConfig(root, root/'game.nup', root, env, root/'out.ipa', 'org.example.game')
            self.assertEqual(make_build_environment(cfg)['NXW_MODS_DIR'], '')

    def test_mod_cuts_do_not_disable_function_matching(self):
        source = (ROOT / 'engine/dm/tools/patch_nso.py').read_text(encoding='utf-8')
        self.assertLess(source.index("if BUILD_ID not in PATCHES['CUTS']:"),
                        source.index("if os.environ.get('NXW_MOD_CUTS'):"))
        self.assertLess(source.index("if os.environ.get('NXW_MOD_CUTS'):"),
                        source.index('ALIAS_APPLIED ='))
        self.assertIn('mod overlaps a resolved game/SDK cut', source)
        shim = (ROOT / 'engine/win/pyshim/sitecustomize.py').read_text(encoding='utf-8')
        self.assertNotIn("mods.get('new'", shim)


if __name__ == '__main__':
    unittest.main()
