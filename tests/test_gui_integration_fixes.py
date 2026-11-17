"""Source-only regression checks for HookLinkWindows GUI fixes."""
import pathlib, tempfile, unittest, zipfile, plistlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'win'))
from hooklink_gui_core import (read_host_shader_chain, verified_shader_chain_from_ipa, find_transfer_sources,
    prepare_transfer_folder, oot_runtime_errors, inspect_ipa, export_app_only_ipa, verify_native_split_ipa)

C='24cf3dc20b93'
GOOD='DM_MSL_DIR=.\nDM_NVN_ENC_THREAD=0\nDM_PSO_MTL4=0\nDM_NVN_BARRIER=full\n'


def make_ipa(path, chain=None):
    props={'CFBundleDisplayName':'The Legend of Zelda: Ocarina of Time', 'CFBundleName':'DmIOS',
           'CFBundleIdentifier':'PhoenixNetwork.HookLinkWindows', 'CFBundleExecutable':'DmIOS'}
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('Payload/DmIOS.app/Info.plist', plistlib.dumps(props, fmt=plistlib.FMT_XML))
        z.writestr('Payload/DmIOS.app/DmIOS', b'BINARY')
        z.writestr('Payload/DmIOS.app/RomFS.img', b'ROM')
        if chain:
            z.writestr('Payload/DmIOS.app/msl/b-'+chain+'.img',b'SHADER')
    return path

class TestWorkflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.d=pathlib.Path(self.tmp.name)
        self.header=self.d/'dmsh_chain.h';self.header.write_text('#define DMSH_CHAIN "'+C+'"\n')
        self.env=self.d/'oot.env';self.env.write_text(GOOD)
        self.work=self.d/'work';self.work.mkdir()
        self.rom=self.work/'extract'/'game'/'RomFS.img';self.rom.parent.mkdir(parents=True);self.rom.write_bytes(b'ROM-data')
        self.donor=self.d/'donor'; archive=self.donor/'shader'/'ios'/f'b-{C}.img';archive.parent.mkdir(parents=True);archive.write_bytes(b'MSL-data')
        self.ipa=make_ipa(self.d/'full.ipa')
    def test_header_fallback_and_conflict(self):
        self.assertEqual(read_host_shader_chain(self.header), C)
        self.assertEqual(verified_shader_chain_from_ipa(self.ipa,self.header), C)
        other=make_ipa(self.d/'bad.ipa', '000000000000')
        with self.assertRaisesRegex(ValueError,'disagrees'):verified_shader_chain_from_ipa(other,self.header)
    def test_verified_donor_required(self):
        with self.assertRaisesRegex(ValueError,'verified donor'):
            find_transfer_sources(self.work,self.env,C,donor_shader_work=self.donor)
        sources=find_transfer_sources(self.work,self.env,C,donor_shader_work=self.donor,donor_verified=True)
        self.assertEqual(sources[f'b-{C}.img'].read_bytes(),b'MSL-data')
        folder=prepare_transfer_folder(self.work,self.env,self.d/'transfer',C,donor_shader_work=self.donor,donor_verified=True)
        self.assertTrue((folder/f'b-{C}.img').is_file())
        self.assertFalse((folder/f'b-{C}.img').samefile(sources[f'b-{C}.img']), 'Donor must be copied, not hard-linked')
        self.assertTrue((folder/'RomFS.img').is_file())
        self.assertEqual(oot_runtime_errors(folder/'env.txt'), [])
    def test_runtime_fails_closed(self):
        self.assertFalse(oot_runtime_errors(self.env))
        self.env.write_text('DM_NVN_BARRIER=game\n')
        self.assertEqual(len(oot_runtime_errors(self.env)),4)
    def test_export_name_and_data(self):
        dest=self.d/'app-only.ipa'; rep=export_app_only_ipa(self.ipa,dest)
        self.assertLess(rep['size'], self.ipa.stat().st_size)
        info=inspect_ipa(dest)
        self.assertEqual(info['external_names'],[])
        with zipfile.ZipFile(dest) as z:
            name=plistlib.loads(z.read('Payload/DmIOS.app/Info.plist'))
            self.assertEqual(name['CFBundleDisplayName'],'HookLinkWindows')
            self.assertEqual(name['CFBundleName'],'HookLinkWindows')
            self.assertEqual(name['CFBundleIdentifier'],'PhoenixNetwork.HookLinkWindows')
            self.assertEqual(z.read('Payload/DmIOS.app/DmIOS'),b'BINARY')
        folder=prepare_transfer_folder(self.work,self.env,self.d/'transfer',C,donor_shader_work=self.donor,donor_verified=True)
        verify_native_split_ipa(dest,folder,C)
    def test_existing_local_archive_allowed(self):
        local=self.work/'shader'/'ios'/f'b-{C}.img';local.parent.mkdir(parents=True);local.write_bytes(b'LOCAL')
        sources=find_transfer_sources(self.work,self.env,C,donor_shader_work=self.donor,donor_verified=False)
        self.assertEqual(sources[f'b-{C}.img'], local)

if __name__=='__main__': unittest.main(verbosity=2)
