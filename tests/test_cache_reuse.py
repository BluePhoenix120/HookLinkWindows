"""Self-contained offline integration tests for 0.8.3 cache safety and native packaging."""
import ast
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import zipfile
import plistlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'win'))
from hooklink_gui_core import (BuildConfig, PACKAGE_APP_ONLY, PACKAGE_FULL, make_build_environment,
                                make_build_plan, verify_native_split_ipa)

# Extract the actual production functions from the large upstream scripts without running
# macOS-only top-level imports or requiring a Nintendo game file.
def isolate(rel, names, values):
    code=(ROOT/rel).read_text(encoding='utf-8')
    module=ast.parse(code)
    func=[n for n in module.body if isinstance(n,ast.FunctionDef) and n.name in names]
    ns=dict(values)
    exec(compile(ast.Module(body=func,type_ignores=[]),str(ROOT/rel),'exec'),ns)
    return ns

class NativeAndReuseTests(unittest.TestCase):
    def test_native_plan_avoids_full_ipa_and_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); (d/'win').mkdir();(d/'win'/'build_ipa_windows.py').write_text('')
            (d/'game.nup').write_bytes(b'test');(d/'settings.env').write_text('DM_MSL_DIR=.\n')
            cfg=BuildConfig(d,d/'game.nup',d/'work',d/'settings.env',d/'app.ipa','org.test.oot', native_app_only=True)
            native=make_build_plan(cfg,PACKAGE_APP_ONLY,python='python')
            self.assertTrue(native.native_split)
            self.assertEqual(native.builder_ipa,native.final_ipa)
            self.assertIn('--split-data='+str(native.transfer_dir),native.command)
            self.assertNotIn('--no-split-data',native.command)
            legacy=make_build_plan(BuildConfig(d,d/'game.nup',d/'work',d/'settings.env',d/'app.ipa','org.test.oot'),PACKAGE_APP_ONLY,python='python')
            self.assertFalse(legacy.native_split)
            self.assertNotEqual(legacy.builder_ipa,legacy.final_ipa)
            self.assertIn('--no-split-data',legacy.command)
            full=make_build_plan(cfg,PACKAGE_FULL,python='python')
            self.assertIn('--no-split-data',full.command)

    def test_external_path_only_in_explicit_build_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); (d/'win').mkdir();(d/'win'/'build_ipa_windows.py').write_text('')
            (d/'game.nup').write_bytes(b'x');(d/'settings.env').write_text('x')
            old=d/'old';old.mkdir()
            cfg=BuildConfig(d,d/'game.nup',d/'work',d/'settings.env',d/'out.ipa','org.test.oot',reuse_shader_work=old)
            self.assertEqual(make_build_environment(cfg)['NXW_REUSE_SHADER_WORK'],str(old.resolve()))
            self.assertNotIn('NXW_REUSE_SHADER_WORK',make_build_environment(BuildConfig(d,d/'game.nup',d/'work',d/'settings.env',d/'out.ipa','org.test.oot')))

    def test_native_split_preserves_source_images_without_linking_protected_donor(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); imgs=d/'inputs'; imgs.mkdir()
            original=imgs/'b-abcdef123456.img';original.write_bytes(b'old shader archive')
            rom=imgs/'RomFS.img';rom.write_bytes(b'game rom')
            env=imgs/'env.txt';env.write_text('DM_NVN_ENC_THREAD=0\n')
            ns=isolate('engine/win/build_app.py',['split_data'],dict(Path=Path,os=os,shutil=shutil,hashlib=hashlib,t=lambda *a:None,list_files=lambda a:[],__name__='test'))
            dst=d/'out'
            ns['split_data'](dst,{'RomFS.img':rom,'b-abcdef123456.img':original,'env.txt':env},'chain\tabcdef123456\n','Demo',copy_files=('b-abcdef123456.img',))
            self.assertEqual((dst/'b-abcdef123456.img').read_bytes(),b'old shader archive')
            self.assertNotEqual(os.stat(original).st_ino, os.stat(dst/'b-abcdef123456.img').st_ino)
            (dst/'b-abcdef123456.img').write_bytes(b'changed transfer')
            self.assertEqual(original.read_bytes(),b'old shader archive')
            # A missing source is not silently accepted as a cached-success output.
            (dst/'env.txt').unlink()
            ns['split_data'](dst,{'RomFS.img':rom,'b-abcdef123456.img':original,'env.txt':env},'chain\tabcdef123456\n','Demo',copy_files=('b-abcdef123456.img',))
            self.assertTrue((dst/'env.txt').is_file())

    def test_2_0_shader_stage_verifies_input_and_output_fingerprints(self):
        # The 1.9.1 external donor API is deliberately not part of 2.0.
        # Verify new 2.0 stage proof instead; functional reuse tests live in
        # test_allow_damaged_external_reuse.py.
        source=(ROOT/'engine/scripts/build_ipa_from_nsp.py').read_text(encoding='utf-8')
        tree=ast.parse(source)
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='split_shaders')
        body=ast.get_source_segment(source,fn)
        self.assertIn("key = fingerprint(*inputs, *split_profile_inputs(g))",body)
        self.assertIn("('stat' if provisional or ALLOW_DAMAGED else 'tree', r)",body)
        self.assertIn('RomFS.img.formats',body)
        if 'write_tables' in {arg.arg for arg in fn.args.args}:
            self.assertIn('pkg_key = package_key(pkg)',body)
            self.assertIn('reused(outputkf, split_output_key(pkg, g, pkg_key))',body)
            self.assertIn('outputkf.write_text(split_output_key(pkg, g, pkg_key)',body)
        else:
            self.assertIn('reused(outputkf, split_output_key(pkg, g))',body)
        self.assertNotIn('verified_external_ios_shaders',body)


    def test_native_split_output_verification_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp);ipa=d/'app.ipa'; files=d/'files';files.mkdir()
            with zipfile.ZipFile(ipa,'w') as z:
                z.writestr('Payload/DmIOS.app/Info.plist',plistlib.dumps({'CFBundleExecutable':'DmIOS','CFBundleIdentifier':'org.test.game'}))
                z.writestr('Payload/DmIOS.app/DmIOS',b'arm binary placeholder')
            (files/'RomFS.img').write_bytes(b'img');(files/'b-abcdef123456.img').write_bytes(b'img')
            with self.assertRaisesRegex(ValueError,'missing required file'):
                verify_native_split_ipa(ipa,files,'abcdef123456')
            (files/'env.txt').write_text('DM_MSL_DIR=.\n')
            self.assertEqual(verify_native_split_ipa(ipa,files,'abcdef123456')['bundle'],'org.test.game')
            with zipfile.ZipFile(ipa,'a') as z:z.writestr('Payload/DmIOS.app/romfs.img',b'not app only')
            with self.assertRaisesRegex(ValueError,'still contains game data'):
                verify_native_split_ipa(ipa,files,'abcdef123456')

if __name__=='__main__': unittest.main()
