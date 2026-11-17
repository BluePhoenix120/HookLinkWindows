import importlib.util
import plistlib
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'win'))
from hooklink_gui_core import BuildConfig, make_build_command, make_build_environment, check_runtime_config, export_app_only_ipa, inspect_ipa, make_build_plan, default_output_name, prepare_transfer_folder, shader_chain_from_ipa, find_transfer_sources, PACKAGE_APP_ONLY, PACKAGE_FULL

class TestGui(unittest.TestCase):
    def test_gui_source_has_no_prod_keys_controls(self):
        source = (ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertNotIn('prod.keys', source.lower())
        self.assertNotIn('key_var', source)
        self.assertNotIn('_browse_keys', source)
        self.assertEqual(source.count('self._field(form,'), 4)
        self.assertIn("self._field(self.advanced_box, 0, 'iOS Bundle ID', self.bundle_var)", source)
        self.assertIn("DEFAULT_BUNDLE_ID = 'PhoenixNetwork.HookLinkWindows'", source)
        self.assertIn('def _toggle_advanced(self):', source)
        self.assertIn('build_python()', source)
        self.assertIn("ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False)", source)
        self.assertIn("kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW", source)
        self.assertIn("GUI_VERSION = 'Alpha V1.0.2'", source)
        self.assertNotIn(r'C:\\HookLinkWindowsBuild', source)
        self.assertNotIn('test0400486024dec000', source)
        self.assertNotIn('env-WORKING-1.8.5', source)
        self.assertNotIn('For personal testing only', source)
        self.assertNotIn('NOT publish the IPA', source)
        self.assertNotIn("glob('*Ocarina of Time*.nup')", source)
        self.assertIn('DEFAULT_WORK = ROOT.parent / DEFAULT_WORK_NAME', source)
        self.assertIn("self.allow_damaged = tk.BooleanVar(value=prefs.get('allow_damaged', True))", source)
        self.assertIn("self.allow_metal = tk.BooleanVar(value=prefs.get('allow_metal', True))", source)
        self.assertIn('App-only (recommended)', source)
        self.assertIn('Full (includes game data)', source)
        self.assertNotIn("text='Export app-only IPA'", source)
        self.assertNotIn("text='Build full IPA'", source)

    def test_single_prerequisite_action_includes_project_layout(self):
        source = (ROOT / 'win' / 'hooklink_gui.pyw').read_text(encoding='utf-8')
        self.assertIn("text='Check prerequisites', command=self._doctor", source)
        self.assertNotIn("text='Check project files'", source)
        self.assertNotIn('self.install_btn', source)
        self.assertNotIn('def _installation(', source)
        self.assertIn('preflight = check_project_installation(ROOT)', source)
        self.assertIn('if not preflight.ready_for_doctor:', source)

    def test_two_component_bundle_id_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            d = Path(td); (d/'win').mkdir(); (d/'win'/'build_ipa_windows.py').write_text('')
            nup = d/'Game.nup'; nup.write_bytes(b'NUP')
            env = d/'settings.env'; env.write_text('DM_NVN_BARRIER=full\n')
            cfg = BuildConfig(d,nup,d/'build',env,d/'out.ipa','PhoenixNetwork.HookLinkWindows')
            self.assertIn('PhoenixNetwork.HookLinkWindows',make_build_command(cfg,python='python'))

    def test_public_runtime_preset(self):
        preset = ROOT / 'config' / 'iphone-oot.env'
        self.assertTrue(preset.exists())
        self.assertEqual(check_runtime_config(preset), [])

    def test_nup_never_needs_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); (d/'win').mkdir(); (d/'win'/'build_ipa_windows.py').write_text('')
            (d/'Game.nup').write_bytes(b'NUP'); (d/'env.txt').write_text('DM_NVN_ENC_THREAD=0\nDM_NVN_BARRIER=full\nDM_PSO_MTL4=0\nDM_MSL_DIR=.\n')
            cfg = BuildConfig(d,d/'Game.nup',d/'work',d/'env.txt',d/'out.ipa','org.example.game')
            cmd = make_build_command(cfg,python='python')
            self.assertNotIn('-k',cmd); self.assertIn('--no-split-data',cmd); self.assertIn('--env-file',cmd)
            self.assertEqual(make_build_environment(cfg)['DMSH_PROCS'],'0')
            self.assertEqual(make_build_environment(cfg)['J'],'61')
            self.assertEqual(check_runtime_config(d/'env.txt'),[])

    def test_non_nup_inputs_are_rejected_without_key_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp); (d/'win').mkdir(); (d/'win'/'build_ipa_windows.py').write_text('')
            (d/'Game.nsp').write_bytes(b'not a NUP')
            (d/'env.txt').write_text('DM_NVN_ENC_THREAD=0\nDM_NVN_BARRIER=full\nDM_PSO_MTL4=0\nDM_MSL_DIR=.\n')
            cfg = BuildConfig(d,d/'Game.nsp',d/'work',d/'env.txt',d/'out.ipa','org.example.game')
            with self.assertRaisesRegex(ValueError, 'Other input formats are not supported'):
                make_build_command(cfg, python='python')
            folder = d/'extracted'; folder.mkdir()
            cfg = BuildConfig(d,folder,d/'work',d/'env.txt',d/'out.ipa','org.example.game')
            with self.assertRaisesRegex(ValueError, 'Other input formats are not supported'):
                make_build_command(cfg, python='python')

    def test_packages_without_external_images_and_keeps_exec_perms(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); src=d/'full.ipa'; dest=d/'AltStore.ipa'
            plist=plistlib.dumps({'CFBundleIdentifier':'org.example.game','CFBundleExecutable':'DmIOS'})
            with zipfile.ZipFile(src,'w') as z:
                z.writestr('Payload/DmIOS.app/Info.plist',plist)
                info=zipfile.ZipInfo('Payload/DmIOS.app/DmIOS'); info.create_system=3; info.external_attr=0o100755 << 16
                z.writestr(info,b'ios-executable')
                z.writestr('Payload/DmIOS.app/dm/shader_map.tsv',b'game-specific metadata kept locally')
                z.writestr('Payload/DmIOS.app/romfs.img',b'private game data')
                z.writestr('Payload/DmIOS.app/msl/b-24cf3dc20b93.img.img.0',b'private shader half')
                z.writestr('Payload/DmIOS.app/msl/b-24cf3dc20b93.img.img.1',b'private shader half 2')
            r=export_app_only_ipa(src,dest)
            self.assertEqual(r['skipped'],3)
            with zipfile.ZipFile(dest) as z:
                self.assertEqual(z.testzip(),None)
                self.assertFalse(any('romfs.img' in x or '.img.img.' in x for x in z.namelist()))
                self.assertIn('Payload/DmIOS.app/DmIOS',z.namelist())
                self.assertEqual(z.getinfo('Payload/DmIOS.app/DmIOS').external_attr>>16,0o100755)
            self.assertTrue(src.exists())
            self.assertEqual(inspect_ipa(dest)['bundle'],'org.example.game')

    def test_single_build_button_and_mode_plans(self):
        self.assertEqual(default_output_name(PACKAGE_APP_ONLY), 'HookLinkWindows-AppOnly.ipa')
        self.assertEqual(default_output_name(PACKAGE_FULL), 'HookLinkWindows-Full.ipa')
        with tempfile.TemporaryDirectory() as td:
            d = Path(td); (d/'win').mkdir(); (d/'win'/'build_ipa_windows.py').write_text('')
            (d/'Game.nup').write_bytes(b'NUP'); (d/'env.txt').write_text('DM_NVN_BARRIER=full\n')
            cfg = BuildConfig(d,d/'Game.nup',d/'work',d/'env.txt',d/'app.ipa','org.example.game')
            app = make_build_plan(cfg, PACKAGE_APP_ONLY, token='test123', python='python')
            self.assertNotEqual(app.builder_ipa, app.final_ipa)
            self.assertEqual(app.final_ipa, d/'app.ipa')
            self.assertIn(str(app.builder_ipa), app.command)
            self.assertEqual(app.transfer_dir.name, 'app-iPhone-Files')
            full = make_build_plan(cfg, PACKAGE_FULL, python='python')
            self.assertEqual(full.builder_ipa, full.final_ipa)
            self.assertIsNone(full.transfer_dir)
            self.assertIn('--no-split-data', full.command)
            with self.assertRaisesRegex(ValueError, 'IPA packaging'):
                make_build_plan(cfg,'broken')

    def test_source_ipa_shader_chain_validation_and_transfer_folder(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); work=d/'work'; out=d/'out'; out.mkdir()
            rom=work/'extract'/'v131072'/'RomFS.img'; rom.parent.mkdir(parents=True)
            rom.write_bytes(b'SELF OWNED TEST INPUT DATA')
            shader=work/'shader'/'ios'/'b-abcdef123456.img'; shader.parent.mkdir(parents=True)
            shader.write_bytes(b'SELF OWNED TEST SHADER DATA')
            env=d/'custom.txt'; env.write_text('DM_NVN_BARRIER=full\n')
            src=d/'full.ipa'
            with zipfile.ZipFile(src,'w') as z:
                z.writestr('Payload/DmIOS.app/Info.plist',plistlib.dumps({'CFBundleExecutable':'DmIOS'}))
                z.writestr('Payload/DmIOS.app/DmIOS',b'executable')
                z.writestr('Payload/DmIOS.app/msl/b-abcdef123456.img.img.0',b'externalized')
                z.writestr('Payload/DmIOS.app/romfs.img',b'externalized')
            chain=shader_chain_from_ipa(src)
            self.assertEqual(chain,'abcdef123456')
            self.assertEqual(set(find_transfer_sources(work,env,chain)),{'RomFS.img','env.txt','b-abcdef123456.img'})
            app=out/'AppOnly.ipa'; export_app_only_ipa(src,app)
            folder=prepare_transfer_folder(work,env,out/'AppOnly-iPhone-Files',chain)
            self.assertTrue((folder/'TRANSFER_README.txt').exists())
            self.assertEqual((folder/'RomFS.img').read_bytes(),rom.read_bytes())
            self.assertEqual((folder/'env.txt').read_text(),env.read_text())
            self.assertEqual((folder/'b-abcdef123456.img').read_bytes(),shader.read_bytes())
            folder2=prepare_transfer_folder(work,env,out/'AppOnly-iPhone-Files',chain)
            self.assertEqual(folder2.name,'AppOnly-iPhone-Files-2')
            self.assertEqual(rom.read_bytes(),b'SELF OWNED TEST INPUT DATA')
            self.assertTrue(src.exists())
            with self.assertRaisesRegex(ValueError,'Expected one shader archive'):
                find_transfer_sources(work,env,'other')

    def test_refuses_unidentified_large_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=Path(tmp); src=d/'full.ipa'
            with zipfile.ZipFile(src,'w',compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('Payload/DmIOS.app/Info.plist',plistlib.dumps({'CFBundleExecutable':'DmIOS'}))
                z.writestr('Payload/DmIOS.app/DmIOS',b'x')
                # Synthetic entry only 1KB; test predicate separate (no huge memory use).
            info = inspect_ipa(src)
            self.assertEqual(info['large_remaining'],[])
            with patch('hooklink_gui_core.inspect_ipa', return_value={'large_remaining': [('Payload/DmIOS.app/unknown.bin', 300*1024*1024)]}):
                with self.assertRaisesRegex(ValueError, 'Unexpected large'):
                    export_app_only_ipa(src, d/'app-only.ipa')
            self.assertFalse((d/'app-only.ipa').exists())

if __name__=='__main__': unittest.main()
