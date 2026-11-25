"""Windows CI source-contract checks for NXnative #3059's audio scheduling backport.

These checks cannot establish that iOS grants Mach time-constraint scheduling
or that a compiled IPA plays without crackling; device logs are still required.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "engine" / "dm" / "host" / "hle_audren.c"


class AudioProducerRealtimeContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = AUDIO.read_text(encoding="utf-8")

    def test_mach_time_constraint_policy_uses_5ms_period_and_deadline(self):
        s = self.source
        for header in ("<mach/mach.h>", "<mach/mach_time.h>", "<mach/thread_policy.h>"):
            self.assertIn("#include " + header, s)
        self.assertIn(".period = (uint32_t)(5000000ull * tb.denom / tb.numer)", s)
        self.assertIn(".computation = (uint32_t)(1000000ull * tb.denom / tb.numer)", s)
        self.assertIn(".constraint = (uint32_t)(5000000ull * tb.denom / tb.numer), .preemptible = TRUE", s)
        self.assertIn("THREAD_TIME_CONSTRAINT_POLICY_COUNT", s)

    def test_worker_switches_policy_only_between_start_and_close(self):
        s = self.source
        start = s.index("static void render_main(void *arg) {")
        end = s.index("static void render_rt_end(void)")
        self.assertLess(end, start)
        worker = s[start:s.index("// Both OpenAudioRenderer forms", start)]
        self.assertLess(worker.index("dm_pcmout_start(out);"), worker.index("int rt = render_rt();"))
        self.assertLess(worker.index("if (rt) render_rt_end();"), worker.index("dm_pcmout_close(out);"))
        self.assertEqual(worker.count("int rt = render_rt();"), 1)
        self.assertEqual(worker.count("if (rt) render_rt_end();"), 1)

    def test_opt_out_and_fallback_do_not_block_playback(self):
        s = self.source
        self.assertIn('getenv("DM_AUDREN_RT")', s)
        self.assertIn('atoi(e) == 0', s)
        self.assertIn('failed to set; keeping default policy', s)
        self.assertIn('if (rt) render_rt_end();', s)
        self.assertIn('THREAD_STANDARD_POLICY', s)
        self.assertIn('return kr == KERN_SUCCESS;', s)

    def test_previous_audio_pacing_and_shader_path_unchanged(self):
        s = self.source
        self.assertIn("NBUF = 4", s)
        self.assertIn("RENDER_MIN_NS = 4500000", s)
        self.assertIn("if (prefill) prefill--;", s)
        self.assertIn("if (!dm_pcmout_append(out, b))", s)

    def test_audio_policy_now_matches_full_original_nxnative_source(self):
        pin = json.loads((ROOT / "ENGINE_PIN.json").read_text(encoding="utf-8"))
        manifest = json.loads((ROOT / "ENGINE_PIN_FILES.json").read_text(encoding="utf-8"))
        self.assertEqual(pin["audio_producer_patch_commit"], "2edad1828de247aaf46c53cb288357cb65e84be0")
        self.assertEqual(pin["nxnative_commit"], "5dfc86ae80c53a62262c3b3c66eab043f1fc574a")
        self.assertEqual(manifest["nxnative_commit"], pin["nxnative_commit"])
        path = "engine/dm/host/hle_audren.c"
        official = {entry["path"]: entry["sha"] for entry in manifest["changed_paths"]}
        self.assertIn(path, official)
        self.assertNotIn(path, manifest["windows_overlays"])
        self.assertNotIn(path, manifest["integration_overrides"])
        import hashlib
        raw = AUDIO.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
        self.assertEqual(actual, official[path])


if __name__ == "__main__":
    unittest.main()
