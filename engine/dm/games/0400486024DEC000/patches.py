# The Legend of Zelda: Ocarina of Time (0400486024DEC000): the rewriter's patches of this game's own code. dm/tools/patch_nso.py loads every profile's patches.py;
# MATCH_FRAME_STEP as described there ("Registered patches"). Patches of Nintendo SDK module builds are in dm/tools/sdk_patches.py
from nso_asm import ADRP, ADDI, B, BL

# The game's frame ratio. Once a frame the function at main+0x6e6be0 (v131072, ModuleSystem::moduleCalc_ by the name of its job) divides its base rate (60.0, or 30.0 while
# bit 0 of [x21+0x24f] is set) by the int frame rate at [x21+0x2c8] (fdiv s8,s1,s0 at +0xe4) and hands the result to the time object (main+0x3b4e300: ratio at +0x10, 1 / ratio
# at +0x14, ratio / 60 at +0x18, the step in seconds, round(60 / ratio) at +0x1c), which the game steps by; the frame's own time never enters it, so a frame that takes two
# vsyncs at rate 60 plays at half speed. The stub gives the ratio the host's step instead: step × base / 60, and counts the vsyncs stepped. Until the host has decided a step,
# and at fps_target 0, the division runs. s0 and x16 / x17 are free there (s0 is written again on every path before it is read; the function uses neither x16 nor x17); s1 keeps
# the base rate and x21 the framework.
# Why × base / 60 and not the step alone (PR #1996 read base 30 as a cutscene rate and took the step, twice the speed there): the ratio's unit is 1/60 s whatever the base
# (the time object's +0x18 is ratio × 1/60, the constant at main+0x3e4066c). Base 30 is the framework's half rate: bit 0 of its +0x24f is that mode and bit 1 flips each pass of
# its frame function (main+0x346c680); with both set the draw and the present return at once (main+0x2cb020, main+0x40cd20) while the calc tree runs (main+0x2cabd0). So it
# calcs twice a drawn frame, this function among them, and each calc takes half the frame's step: 30 / 30 = 1 twice a 30 fps frame on the console, step / 2 twice here. The
# vsyncs are counted once a drawn frame, at the calc that is drawn (bit 1 clear).
# Lichii (a GPL emulator; only the fact was taken) found the division (its notes: main+0x6E6CC4, 60 / [x21+0x2C8])
def frame_step(ctx):
    here, emit, fs_site, fs_put, FS_STATE_OFF, base = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state, ctx.base
    site = base + 0xe4
    fs_site(site, '2818201e')   # fdiv s8,s1,s0
    start = here()
    ORIG, COUNTED, n = 24, 13, [0]   # the original division is word 24 of the stub, the ratio starts at word 13 (both checked below); n counts the words emitted
    def put(w): emit(w); n[0] += 1
    def cbz_w17_orig(): return 0x34000000 | (((ORIG - n[0]) & 0x7FFFF) << 5) | 17   # from this word to word ORIG
    put(ADRP(16, here(), FS_STATE_OFF))
    put(0xb9400211)             # ldr w17,[x16]          target fps (0 = off)
    put(cbz_w17_orig())         # cbz w17,orig
    put(0xb9402211)             # ldr w17,[x16,#0x20]    step in vsyncs
    put(cbz_w17_orig())         # cbz w17,orig           not decided yet
    put(0x1e230220)             # ucvtf s0,w17
    put(0x39493eb0)             # ldrb w16,[x21,#0x24f]  the framework's half-rate bits
    put(0x37000000 | 1 << 19 | ((COUNTED - n[0]) & 0x3FFF) << 5 | 16)   # tbnz w16,#1,ratio: the calc of a half-rate frame that is not drawn; its vsyncs are counted at the drawn one
    put(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xf9401a10,   # ldr x16,[x16,#0x30]
              0x8b110210):  # add x16,x16,x17
        put(w)
    put(ADRP(17, here(), FS_STATE_OFF))
    put(0xf9001a30)             # str x16,[x17,#0x30]    vsyncs stepped
    assert n[0] == COUNTED, f'frame_step: the ratio starts at word {n[0]}, the tbnz goes to word {COUNTED}'
    for w in (0x1e210808,   # fmul s8,s0,s1          step × base rate
              0x52a84e10,   # mov w16,#0x42700000    60.0
              0x1e270200,   # fmov s0,w16
              0x1e201908):  # fdiv s8,s8,s0          / 60
        put(w)
    # Never below the measured frame time: with the hold off (DM_FPS_HOLD off) or past the longest step, a frame that ran long still moves the game by its real time
    # (state +0x38, seconds, the host's mean of recent present intervals; 0 at the target; +0x3c marks a main that reads it). From PR #1543, found by gunvalk (Lichii PR #216).
    # The host takes what this adds to the step off its debt (nvn_fstep_moved), or the step paid the same time back again: 9% fast at frames of 1.8 vsyncs with the hold off.
    # Every branch target above is computed: with these words inserted, main's fixed offsets (+13, +11) landed inside this block, and an iPhone 18 Pro Max faulted at
    # x17 + 0x3c with x17 = 0 on the first frame, before the host had decided a step. The page is taken again into x16, PR #1543's own sequence: in rewritten code x17 does
    # not survive a store
    put(ADRP(16, here(), FS_STATE_OFF))
    for w in (0x52800031,   # mov w17,#1
              0xb9003e11,   # str w17,[x16,#0x3c]    this main reads the frame time
              0xbd403a00,   # ldr s0,[x16,#0x38]     seconds; 0 = at the target
              0x1e210800,   # fmul s0,s0,s1          × base rate
              0x1e204908):  # fmax s8,s8,s0
        put(w)
    put(B(here(), site + 4))
    assert n[0] == ORIG, f'frame_step: the original division is word {n[0]}, the cbz branches go to word {ORIG}'
    emit(0x1e201828); emit(B(here(), site + 4))   # orig: fdiv s8,s1,s0; back
    fs_put(site, [B(site, start)], 'frame ratio: the host\'s step × base rate / 60 (never below the measured frame time) instead of base rate / the game\'s frame rate (state page target fps; 0 = the game\'s ratio)')
    dynamic_resolution(ctx)
    if ctx.base == 0x6e6be0:
        render_scale(ctx)  # working v131072 fixed-address iPhone patch
        wide_view(ctx)     # avoid competing camera hook on this build
    else:
        screen_shape(ctx)  # new original hooks for other matching builds
    half_rate(ctx)
    heap_retry(ctx)

# The game's dynamic resolution (game__gfx__DynamicResolutionParam: LoadThreshold, ReduceCounterMax, IncreaseCounterMax and a list of levels, each a ResolutionReduceScale and a
# Priority; on v131072 levels 0..9 at 0.75..0.333 of 2048x1152, 1536x864 to 683x384). Its update (main+0x805aa0) reads the frame's GPU load (about 0.2 ms a unit) into +0x8, subtracts
# its small model of the fixed costs and divides the rest by the square of the current scale: it takes the rest of the frame's cost to grow with the pixel count, as on the Switch 2
# its constants were tuned for. The level function (main+0x8065e0) adds that back times each level's scale squared and returns the best level under the threshold (+0x10, 83 = about
# 16.4 ms). On Apple GPUs this game's cost hardly depends on the resolution (mesh, compute and the upscaler's fixed 2048x1152 dominate): 683x384 cost 14.3 ms and 1536x864 14.7 ms on
# an M4 Pro, yet at 683x384 the extrapolation put 1536x864 at about 300 units against the 83 it allows, so the controller sat at its floor for good (game note, Dynamic resolution).
# The stub replaces the level function. With DM_DYNAMIC_RESOLUTION 0 (the default; state +0x40 0) it returns 0: full resolution. With 1 it climbs on what was measured at each
# level, with no model of how the cost grows: one level down when the load (+0x8) has been over the threshold for 8 calls in a row, and that level is marked as not fitting; one level
# up when the load fits and the level above was never measured, fitted when it was last measured, or was measured more than 600 calls (about 10 s) ago; else the current level
# (+0x174). Nothing is decided or recorded until a level has held 8 calls: the load is read a few frames late, so before that it may be the previous level's. The 8 calls over in a
# row keep a single slow frame, or the first frames at a new size (its render targets), from marking a level that fits (on the full library at level 1: one burst to 90 against loads
# of 77-80 at levels 2 and 1). The game's counters still pace the steps (down after ReduceCounterMax frames, up after IncreaseCounterMax); its level count (+0x1a0) is the floor.
# The memory is in the state page: +0x200 calls, +0x204 the last call's level, +0x208 calls at it, +0x20c calls over in a row, +0x210 the load measured at each level (16 floats),
# +0x250 the call it was measured at (0 = never). Run against a model of the update (a level moves after the stub asked 5 times up or 2 times down; the load two frames late): a load
# of 70 at every level climbs from the floor to full size in 9 steps, as does Ocarina's measured 72-80 with a spike every 37 frames and a burst after each change; a load that grows
# with the pixel count settles at the highest level that fits and tries the one above once per 600 calls; a scene that gets lighter climbs again, a heavier one steps down.
# The function is a leaf: x2..x11, x16, x17 and s0..s2 are free, w0 its only result (the original also stores its predicted cost at +0x18, which only it and the update's own
# decision read). The update's fingerprint is required too: +0x8 and +0x174 are its fields
drs_controller = (   # drs_stub.s, assembled with clang; x0 the controller, x16 the state page (the ADRP before it)
    0xb9404211, 0x35000071, 0x2a1f03e0, 0xd65f03c0,                                                   # off (state +0x40 0): level 0
    0xbd400800, 0xbd401001, 0xb9417402, 0xb941a003, 0x7100005f, 0x1a9fa042, 0x528001e9, 0x6b09005f,   # load, threshold, level (0..15), count
    0x1a89d042, 0xb9420204, 0x11000484, 0xb9020204, 0xb9420605, 0xb9420a06, 0x6b0200bf, 0x1a8617e6,   # calls + 1; calls at this level
    0xb9020602, 0xb9020a06, 0x35000046, 0xb9020e1f, 0x91084207, 0x91094208, 0x710020df, 0x5400040b,   # a new level: none over; under 8 calls: stay
    0x1e212000, 0x540001ad, 0xb9420e0b, 0x1100056b, 0xb9020e0b, 0x7100217f, 0x5400032b,               # over: under 8 in a row, stay
    0xbc2258e0, 0xb8225904, 0x51000469, 0x1100044a, 0x6b09015f, 0x1a89d140, 0xd65f03c0,               # 8 in a row: record it, down one (to the floor)
    0xb9020e1f, 0xbc2258e0, 0xb8225904, 0x34000182, 0x51000449, 0xb869590a, 0x340000ea, 0x4b0a008a,   # fits: record it; at 0 stay; the level above's record
    0x7109615f, 0x54000088, 0xbc6958e2, 0x1e212040, 0x540000aa, 0x2a0903e0, 0xd65f03c0,               # never, stale or fitting: up one
    0x2a1f03e0, 0xd65f03c0, 0x2a0203e0, 0xd65f03c0)                                                   # 0; or stay
# shape_anchor.c built with the command in its header comment (__text words, little-endian hex)
_shape_anchor = (
    '484840b908530034405c40bd01103e1e0028211ee890a8520101271e0108211e2820201e0d520054203840bd0890b8520201271e0208221e0390201e4020231e'
    '03d0231e42a4231ee9090054090080520a0c40f98a5000b44b0940f94b5000b4680140b9081153511f552571c14f00546c0d40f9ac0100b40d0080d2a8b89352'
    '8823b0726e3280520e20a0728f696d38ef00003408010f4a087d0e1bad050091bfc100f141ffff54080080524d8140f94a7942794c3d0012ae0500d14a3d4092'
    '0f1680524a7daf9b707491d2d045b7f2105dd4f270d1e5f20d000dcbbf010aebaa7dd09b4afd45d34db50f9bc23140faa03940fa4a018c1a8ddb86528d9bbb72'
    '1f010d6b8d060054addb86528d9bbb721f010d6b000900542d398c522d2abc721f010d6be0090054edfc8e52ede6af721f010d6b0116005402e4006f5f290071'
    '2d0f00545f3100712d1100545f350071e01f00545f390071a02200545f510071a11400540e0080526d2d9e52ad46b272300080520f89a852e301271e2f008052'
    'a300001403102c1e4328231e6800381e63b8a15e63d8215e4020231ee913881a02e4006f001c221e28791e121f150071a04500543f190071c1f4ff54223440bd'
    '03103c1e2108031f213400bd087cb75222020014edfe8b520df0b2721f010d6ba00500546d2e9d526d6cb6721f010d6b2110005402e4006f5f4501718c070054'
    '5f4100712d0d00545f450071a01f00545f010171a02000545f450171c10e00540e0080520f0080528d4881526d4fa1726f0000145f150071e10d00540e008052'
    '0daf81524d8aa272ef008052b000805202e4006f119fa8522302271e6c00001402e4006f5f0d00712c0200545f090071601400545f0d0071e10b00540e008052'
    'add98e52ad32af722f008052500080525e00001402e4006f5f150071c00100545f7d0071c0000054530000145f110071200100545f1d0071e10900540e008052'
    '0f00805250008052cdfe88528da4bc724e0000140e0080520f008052300080528d9c93520d56aa72480000145f710171ed0600545f750171001900545f790171'
    '001a00545f7d0171610700540e008052adf29452adb6b8722f00805210018052cd0000145f1100712c0100545f090071400f00545f0d0071e10500540e008052'
    '0d8d83526d63bb72770000145f150071e00e00545f190071e10400540e008052adfc9d52cd73bd72740000145f2d0071601000545f310071e10300540e008052'
    '6dc981522d53ae722f008052d0008052110090525192a8722302271e1199a8522202271e1a0000145f2d0071601100545f410071010200540e0080520f008052'
    'cd2a86522da6ae72090000145f490171c01000545f690171e10000540e0080520f008052ad488e52ed93a972f000805206000014100080520f0080520d008052'
    '2e00805202e4006f03e4006f5f010c6b10329f1ad01e0034713940b93f020c6bcc059f1a0c3200370ca840b98c6516539f010f6b813100546c1140f94c3100b4'
    '6b1540f90b3100b48e596af8ae0100b4110080d2acb893528c23b072623280520220a072c3697138e30000348c01034a8c7d021b310600913fc200f141ffff54'
    '0c0080529f010d6be12e00546b596af8ab2e00b46c3940b98c2907539f010f6b212e00546820201e80000054643140bd8020231e812d00544820201e80000054'
    '642d40bd8020221ee12c00541f1200718c0c00540a0e00515f090071231200541f060071e01700541f0a007101180054223440bd4238211ebc0000140e008052'
    '6daa83520d91b2723000805203e4006f2f008052beffff170e0080526dbf83526d83bb72af008052050000140e0080528d659d52cd13bd722f00805270008052'
    '519fa8522302271eb1ffff170e008052cdfb81522d73ae722f008052d0008052110090525192a8722302271e11009852319ba8722202271ea5ffff170e008052'
    '0d9781522d33ae722f008052d0008052110090525192a8722302271e11008852519aa8722202271e99ffff170e0080522d2e82522d93ae722f00805250008052'
    '110090525192a8722302271ed172a8522202271e8effff170e0080526de682528d22be720a0000140e0080520f008052cd8195520dc0b5723001805283ffff17'
    '0e008052cd4096524d03a9722f00805270008052100000140e0080524daf9052cdb8a5720a0000140e0080520f0080520d3f9b52cd7db1723001805273ffff17'
    '0e0080520d1e8e522d02b3722f00805290008052f1a0a8522302271e6cffff171f1e00712c0400541f160071e00900541f1a0071c10b00545f3100710b009052'
    '2b91b8726301271e8b57a8526401271e830c231e5f2d00710a009c52ca90a8724401271e830c231e0aaea8524401271e8218221e2440211e2518462d270040fd'
    '6514071f6410a75fc328241e250c062de390820f230000fd230840bd4208231e220800bd420000141f220071a00100541f260071c1070054223040bd4a8fa852'
    '4301271e4020231e2d070054223440bd4138211e213400bd0874b752cf000014220040bd4440211e4820201e844c221e221440bd4540211e4820201ea54c221e'
    'a518241eea4d82526a50a7724601271e8020261e04e4006fa4cc241e8020261e6d0400540510201e260c051feaa0a8524701271e251c051f1f120071c50c251e'
    'a318231e6318241e241040bd6408241e4208231e2408022d221840bd6208221e221800bd12000014045c40bd2228231e8020231e61000054025c00bd441ca24e'
    '8020221e01150054223440bd03103c1e2108031f213400bd0878b7529f000014223440bd2228221e223400bd3f0d0071201300543f11007180120054a97e9452'
    '292dbe721f01096b8c020054492e9d52696cb6721f01096b6c040054c9fe8b5209f0b2721f01096bad07005469dc9c52297eb3721f01096bac0c0054e9fe8b52'
    '09f0b2721f01096b6010005409d689528914b3727b00001429648952e9e4a6721f01096bec030054e9b688520961a5721f01096bad060054a9d79c52c955a672'
    '1f01096b2c0b005409b788520961a5721f01096ba00d0054c9609e5249fba57268000014a9a38752c9a0ba721f01096b2d06005409398c52292abc721f01096b'
    '2c0a0054c9a38752c9a0ba721f01096b200c0054a9f59652e9efba7250000014695a9e5209f9ab721f01096bad05005449c1845249fcad721f01096b6c090054'
    '895a9e5209f9ab721f01096be0090054897b9752e9c6ad724a000014c9d28552a919b0721f01096b6009005429369c52695bb0721f01096b80080054c9179b52'
    'a9e0b2723f000014c97e9452292dbe721f01096ba0070054693a9a520941bf721f01096b2007005429299d52c964a27234000014692e9d52696cb6721f01096b'
    '4006005469f49852e9d1b9721f01096b20060054c98e805229ecb9722900001449648952e9e4a6721f01096be004005489168352895ca8721f01096b60040054'
    '29e186526969aa721e00001489dc9c52297eb3721f01096be0030054e9af9452a95fb67217000014c9d79c52c955a6721f01096ba0020054a9f28f52a999a672'
    '0700001429398c52292abc721f01096b20020054c9118a52e975bc721f01096ba001005410000014e9fc8e52e9e6af721f01096b0001005469c1845249fcad72'
    '1f01096b01010054081e00511f050071c80000540868b7520101271e0028211e203800bdc0035fd6223440bd080090524884a8720301271e4020231e2a010054'
    '0310221e080090524884b8720401271e4020241ec80000544138211e020000142128221e213400bd0390221e0850b7520101271e6000011feaffff17'
)

screen_shape_functions = {
    'graphics init': {'size': 0x570, 'fingerprints': ['f2c5558922a471ab585d374cc9293013d48da1562d43169367efdc8ea90a3fe8']},   # main+0x1202ce0
    'scene app init': {'size': 0x273c, 'fingerprints': ['2227b93a9fa9dd0fd9aeb64359649df6e2ade519a8e47fa560f840efcdb5d7e7']},   # main+0x31f3890
    'base scene defaults': {'size': 0x3cc, 'fingerprints': ['4d34ae0b1d0fa05603a24e64aae393040502bdfda2fc053a5c3c02ffda42053e']},   # main+0x108b300
    'display mgr defaults': {'size': 0x4e0, 'fingerprints': ['871e4f9e24b2007d3a9ddbb061b6d1a3709c05f623b356daba35fe1dfeb2004c']},   # main+0x36b2bc0
    'base res read': {'size': 0x1a0, 'fingerprints': ['c49c68fad34b6fce5c0dc0f519f5ddda261ad56778917dc2a711553a10cf4db1']},   # main+0xe82f30
    'display target a': {'size': 0x58, 'fingerprints': ['125411e6b2df56ae4e8c0f9c16f134b4ed9247aca4e426c72b406b1f838bfbb9']},   # main+0xd565a0
    'display target b': {'size': 0x1a8, 'fingerprints': ['212c9a344038bdcf99e4a462ecbe1bb58a2b6374d364debd0d0a0664e1dc1175']},   # main+0xebf370
    'display target c': {'size': 0x188, 'fingerprints': ['0b669aaafc4c17cef5c96ac9e4054895152937e9c780f0c72893973256e9dca7']},   # main+0xf96310
    'layout ortho': {'size': 0x7b0, 'fingerprints': ['fed0ce1f2ad6c8f6118a974ec7d5d5a346194a4c10a0fc01f894cfec3d0a1b68']},   # main+0x1520c80
    'layout view ortho': {'size': 0x62c, 'fingerprints': ['103de33fb929cda858c2fbd57b726e6e1bca705bad66de872701819fbf5c6089']},   # main+0x773b90
    'perspective proj': {'size': 0xb8, 'fingerprints': ['e36f61aa83e94dfacc860ab4dd60dd1362cdab40fa490aee9e921a7ae0f3156d']},   # main+0x3485cc0
    'camera update': {'size': 0x1648, 'fingerprints': ['66a50abf2237dee694c40d6a2371071d62e91379d40b643869d680f597bfab02']},   # main+0x33a8c0
    'device proj': {'size': 0x3b0, 'fingerprints': ['ab5c2809cdbc7f9e30b966872350ac69301aa246a9169610d038ea9480bde910']},   # main+0x23b910
    'layout calc matrix': {'size': 0x208, 'fingerprints': ['0e057804c3c8c7d14ff833983335d834e0bd7505e05263e9c065472b9d206c74']},   # main+0x14e9980
    'pane global matrix': {'size': 0x46c, 'fingerprints': ['4eba5ac4bdf9d227e40612fa426d39fbe1abaf00fc069d5d6ba382809b5c5a5c']},   # main+0x152caa0
    # shape_anchor.c reads the array bounds and class fields written by these two functions.
    'layout pane array': {'size': 0x1d0, 'fingerprints': ['cbf1ceccfe3fca0e81ff2f0c4013e728f16c16de2ee4fc928ec2e9f848d2be8f']},   # main+0x1525d60
    'pane constructor': {'size': 0xfbc, 'fingerprints': ['48ccdf26b4c9a8212e6f4b169b89bb834b3c32f8804bb07a172f37b52f8535ef']},   # main+0x1529620
    'movie draw': {'size': 0x158, 'fingerprints': ['cc1ca04feb1ca4e553a6c7a4f36f99b13f56977185eea8ef5cd8dd3dbbdcdbcd']},  # main+0x3b5c710
}


def screen_shape(ctx):
    # Render sizes, projections, panes and movies must agree on the output shape.
    if any(ctx.others.get(name) is None for name in screen_shape_functions):
        return
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    def patch_height(site, orig_hex, state_off, kind, why):
        fs_site(site, orig_hex)
        start = here()
        emit(int.from_bytes(bytes.fromhex(orig_hex), 'little'))
        emit(ADRP(16, here(), FS_STATE_OFF))
        emit(0xb9400210 | ((state_off // 4) << 10))   # ldr w16, [x16, #state_off]
        if kind == 'hi32_4_3':
            body = (0x340000b0,   # cbz w16, +20
                    0x531e7610,   # lsl w16, w16, #2
                    0x52800071,   # mov w17, #3
                    0x1ad10a10,   # udiv w16, w16, w17
                    0xb3607e08)   # bfi x8, x16, #32, #32
        elif kind == 'hi32':
            body = (0x34000050,   # cbz w16, +8
                    0xb3607e08)   # bfi x8, x16, #32, #32
        elif kind == 'w10':
            body = (0x34000050,   # cbz w16, +8
                    0x2a1003ea)   # mov w10, w16
        elif kind == 'f32_w8':
            body = (0x34000070,   # cbz w16, +12
                    0x1e230200,   # ucvtf s0, w16 (s0 overwritten at site+4)
                    0x1e260008)   # fmov w8, s0
        for w in body: emit(w)
        emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], why)

    # All 1920x1080, 2560x1440, 1280x720, and 1080.0f height sites across InitializeGraphicsSystem, scene defaults, and display manager.
    sites = [
        ('graphics init',        0x204, '08b4c0f2', 0x48, 'hi32_4_3', 'swapchain height = host oh * 4 / 3'),
        ('graphics init',        0x3c0, '8886e8f2', 0x50, 'hi32',     'virtual screen height = host layout height'),
        ('scene app init',       0x168, '08b4c0f2', 0x48, 'hi32_4_3', 'scene app RT height (2560x1440 -> 2560 x oh*4/3)'),
        ('scene app init',       0x174, '0887c0f2', 0x48, 'hi32',     'scene app RT height (1920x1080 -> 1920 x oh)'),
        ('base scene defaults',  0x38c, '0887c0f2', 0x48, 'hi32',     'base scene full height (1920x1080 -> 1920 x oh)'),
        ('base scene defaults',  0x39c, '085ac0f2', 0x4c, 'hi32',     'base scene layout height (1280x720 -> 1280 x lh)'),
        ('display mgr defaults', 0x00c, '0a878052', 0x48, 'w10',      'display mgr table height (1080 -> oh)'),
        ('base res read',        0x114, 'e890a852', 0x48, 'f32_w8',   'base res reference height (1080.0f -> (float)oh)'),
        ('display target a',     0x044, '0887c0f2', 0x48, 'hi32',     'display target height a (1920x1080 -> 1920 x oh)'),
        ('display target b',     0x110, '0887c0f2', 0x48, 'hi32',     'display target height b (1920x1080 -> 1920 x oh)'),
        ('display target c',     0x130, '0887c0f2', 0x48, 'hi32',     'display target height c (1920x1080 -> 1920 x oh)'),
    ]
    for key, off, orig_hex, state_off, kind, why in sites:
        patch_height(ctx.others[key] + off, orig_hex, state_off, kind, why)

    # Layout2 ortho projection builder: scales 16:9 canvas height (>= 1000 wide, e.g. 1920x1080 or 1280x720) by state +0x5c (k = (16/9) / aspect) so UI widgets keep 1:1 pixel aspect.
    # At +0x208 (orig ldr q6, [sp, #0xa0]), x16/x17, v0..v3 and nzcv are free; stores updated {W, H'} back to [sp, #0xa0] for both ortho blocks (x19+0xbf0 and x19+0xca0).
    ortho_fn = ctx.others['layout ortho']
    ortho_site = ortho_fn + 0x208
    fs_site(ortho_site, 'e62bc03d')   # ldr q6, [sp, #0xa0]
    start = here()
    emit(0x3dc02be6)
    emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9404a11, 0x34000291, 0x52a88f51, 0x1e270222, 0x5e0404c0, 0x1e222000, 0x540001eb,
              0x5e0c04c1, 0x1e245002, 0x1e261003, 0x1e220800, 0x1e230822, 0x1e223800, 0x1e20c000,
              0x1e221002, 0x1e222000, 0x540000aa, 0xbd405e02, 0x1e220821, 0x6e0c0426, 0x3d802be6):
        emit(w)
    emit(B(here(), ortho_site + 4))
    fs_put(ortho_site, [B(ortho_site, start)], 'Layout2 ortho canvas height scaled by (16/9) / aspect when screen aspect is active')

    # Layout view draw (main+0x773b90): builds the screen-space OrthoProjection (-W/2..W/2, -H/2..H/2) at +0x398 (orig ldp s0, s1, [x0]) into the 0x90-byte UBO copied to Layout2.
    # Scales 16:9 viewport height s1 (W >= 1000) by state +0x5c (k = (16/9) / aspect) so 2D HUD widgets render 1:1 without vertical stretch. x16/x17, s2..s4 and nzcv are free there.
    vo_fn = ctx.others['layout view ortho']
    vo_site = vo_fn + 0x398
    fs_site(vo_site, '0004402d')   # ldp s0, s1, [x0]
    start = here()
    emit(0x2d400400)
    emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9404a11, 0x34000211, 0x52a88f51, 0x1e270222, 0x1e222000, 0x5400018b,
              0x1e245002, 0x1e261003, 0x1e220804, 0x1e230822, 0x1e223884, 0x1e20c084,
              0x1e221002, 0x1e222080, 0x5400006a, 0xbd405e02, 0x1e220821):
        emit(w)
    emit(B(here(), vo_site + 4))
    fs_put(vo_site, [B(vo_site, start)], 'Layout view ortho height scaled by (16/9) / aspect when screen aspect is active')

    # sead::PerspectiveProjection::doUpdateMatrixImpl_ (main+0x3485cc0): for ~16:9 projections (|aspect - 16/9| <= 0.01), divides aspect by k (to host r = 1920/oh) and widens fovyTan by k (when <= state +0x60 tol) for true Vert+ 3D.
    proj_fn = ctx.others['perspective proj']
    proj_site = proj_fn
    fs_site(proj_site, '0084552d')   # ldp s0, s1, [x0, #0xac]
    start = here()
    emit(0x2d558400)
    emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9404a11, 0x34000231, 0xbd405e03, 0xbd406204, 0x5291c731, 0x72a7fc71, 0x1e270225, 0x1e253825,
              0x1e20c0a5, 0x529ae151, 0x72a78471, 0x1e270226, 0x1e2620a0, 0x540000ac, 0x1e231821, 0x1e2420a0,
              0x5400004c, 0x1e230800):
        emit(w)
    emit(B(here(), proj_site + 4))
    fs_put(proj_site, [B(proj_site, start)], 'PerspectiveProjection aspect and Vert+ fovyTan scaled by (16/9) / aspect when screen aspect is active')
    # Camera projection update (main+0x33a8c0): inlined sead::PerspectiveProjection update at +0xf6c (main+0x33b82c, orig ldp s0, s1, [x2, #0xac]).
    # Scales aspect and fovyTan for ~16:9 projections (|aspect - 16/9| <= 0.01) so gameplay 3D view maintains 1:1 circular aspect on any screen ratio.
    cam_fn = ctx.others['camera update']
    cam_site = cam_fn + 0xf6c
    fs_site(cam_site, '4084552d')   # ldp s0, s1, [x2, #0xac]
    start = here()
    emit(0x2d558440)
    emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9404a11, 0x34000231, 0xbd405e03, 0xbd406204, 0x5291c731, 0x72a7fc71, 0x1e270225, 0x1e253825,
              0x1e20c0a5, 0x529ae151, 0x72a78471, 0x1e270226, 0x1e2620a0, 0x540000ac, 0x1e231821, 0x1e2420a0,
              0x5400004c, 0x1e230800):
        emit(w)
    emit(B(here(), cam_site + 4))
    fs_put(cam_site, [B(cam_site, start)], 'Camera update projection aspect and Vert+ fovyTan scaled by (16/9) / aspect when screen aspect is active')

    # Device projection matrix (main+0x23b910): inlined sead::PerspectiveProjection update at +0x98 (main+0x23b9a8, orig ldp s0, s3, [x0, #0xac]).
    # Scales aspect (s3) and fovyTan (s0) for ~16:9 projections.
    dev_fn = ctx.others['device proj']
    dev_site = dev_fn + 0x98
    fs_site(dev_site, '008c552d')   # ldp s0, s3, [x0, #0xac]
    start = here()
    emit(0x2d558c00)
    emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9404a11, 0x34000231, 0xbd405e07, 0xbd406206, 0x5291c731, 0x72a7fc71, 0x1e270222, 0x1e223862,
              0x1e20c042, 0x529ae151, 0x72a78471, 0x1e270221, 0x1e212040, 0x540000ac, 0x1e271863, 0x1e262040,
              0x5400004c, 0x1e270800):
        emit(w)
    emit(B(here(), dev_site + 4))
    fs_put(dev_site, [B(dev_site, start)], 'Device projection aspect and Vert+ fovyTan scaled by (16/9) / aspect when screen aspect is active')

    # The movie's draw (main+0x3b5c710, the title screen's background and the opening): its sead::Viewport at x29 - 0x28 (min x, y at +0x8, +0xc, max x, y at +0x10, +0x14) is
    # the whole frame buffer, so the 16:9 movie (1920x1080, 2560x1440 after the upscale) filled a 2560x1920 frame at 4:3, 1.33x taller (an oval moon). At +0x64, after the viewport
    # is built and before main+0x2846e0 applies it (viewport and scissor), a rect taller than 16:9 becomes 16:9 about its centre; the frame is already cleared to black above and
    # below. x16 / x17 and s0-s7 are free there (x8 / x9 are loaded by the original instruction, the next call's arguments after it)
    movie_fn = ctx.others['movie draw']
    movie_site = movie_fn + 0x64
    fs_site(movie_site, '69a241a9')   # ldp x9, x8, [x19, #0x18]
    start = here()
    emit(0xa941a269)
    emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9404a11,   # ldr w17, [x16, #0x48]   oh (0 = 16:9)
              0x34000271,   # cbz w17, out
              0xd100a3b1,   # sub x17, x29, #0x28     the viewport
              0x2d410620,   # ldp s0, s1, [x17, #0x8]
              0x2d420e22,   # ldp s2, s3, [x17, #0x10]
              0x1e203844,   # fsub s4, s2, s0         width
              0x1e213865,   # fsub s5, s3, s1         height
              0x52a7e210,   # mov w16, #0x3f100000    9 / 16
              0x1e270206,   # fmov s6, w16
              0x1e260886,   # fmul s6, s4, s6         the 16:9 height
              0x1e2620a0,   # fcmp s5, s6
              0x5400012d,   # b.le out                not taller
              0x1e2638a7,   # fsub s7, s5, s6
              0x52a7e010,   # mov w16, #0x3f000000    0.5
              0x1e270204,   # fmov s4, w16
              0x1e2408e7,   # fmul s7, s7, s4         half the extra height
              0x1e272821,   # fadd s1, s1, s7
              0x1e273863,   # fsub s3, s3, s7
              0xbd000e21,   # str s1, [x17, #0xc]
              0xbd001623):  # str s3, [x17, #0x14]
        emit(w)
    emit(B(here(), movie_site + 4))   # out
    fs_put(movie_site, [B(movie_site, start)], 'Movie draw viewport kept 16:9 about its centre on a taller screen when screen aspect is active')


    # Layout2 pane matrix (main+0x14e9980): for fullscreen PicturePanes (width >= 1000, height >= 700, ~16:9), scales Y matrix row by state +0x5c (k = (16/9) / aspect) so full-screen faders cover the expanded canvas without letterboxing.
    calc_fn = ctx.others['layout calc matrix']
    calc_site = calc_fn + 0x19c
    fs_site(calc_site, '6042883c')   # stur q0, [x19, #0x84]
    start = here()
    emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xb9404a11, 0x34000351, 0xb940aab1, 0x53166631, 0x7100063f, 0x540002c1, 0x2d4b0ea2,
              0x52a88f51, 0x1e270224, 0x1e242040, 0x54000224, 0x52a885f1, 0x1e270224, 0x1e242060,
              0x540001a4, 0x1e245004, 0x1e261005, 0x1e240844, 0x1e250865, 0x1e253884, 0x1e20c084,
              0x52a86911, 0x1e270225, 0x1e252080, 0x5400006a, 0xbd405e02, 0x4f829000, 0x3c884260):
        emit(w)
    emit(B(here(), calc_site + 4))
    fs_put(calc_site, [B(calc_site, start)], 'Layout2 fullscreen picture panes scaled by (16/9) / aspect when screen aspect is active')

    # The HUD and the menu bars at the taller screen's edges (shape_anchor.c, which says what moves). The pane global matrix function (main+0x152caa0) has the new
    # matrix in v0-v3 at +0x3b0 on both paths. At 16:9 skip the stack and call. Otherwise save v0-v3, call shape_calc, reload v0-v3 and run the original instruction.
    # x0-x17 are written before they are read after this point, and x30 is reloaded by the epilogue. The helper leaves x18 alone.
    pane_fn = ctx.others['pane global matrix']
    site = pane_fn + 0x3b0
    fs_site(site, '68c20091')   # add x8,x19,#0x30
    start = here()
    original = start + 13 * 4
    emit(ADRP(16, here(), FS_STATE_OFF))
    emit(0xb9404a11)   # ldr w17, [x16, #0x48]
    emit(0x34000011 | ((original - here()) // 4 << 5))   # cbz w17, original
    for w in (0xd10103ff,    # sub sp,sp,#0x40
              0xad0007e0,    # stp q0,q1,[sp]
              0xad010fe2,    # stp q2,q3,[sp,#0x20]
              0xaa1303e0,    # mov x0,x19            the pane
              0x910003e1,    # mov x1,sp             its matrix (q0-q3)
              0xaa1003e2):  # mov x2,x16            the state page
        emit(w)
    emit(BL(here(), original + 8))   # shape_calc follows the original instruction and its return branch
    for w in (0xad4007e0,    # ldp q0,q1,[sp]
              0xad410fe2,    # ldp q2,q3,[sp,#0x20]
              0x910103ff):  # add sp,sp,#0x40
        emit(w)
    assert here() == original
    emit(0x9100c268)                     # add x8,x19,#0x30      (the original)
    emit(B(here(), site + 4))
    for k in range(0, len(_shape_anchor), 8): emit(int.from_bytes(bytes.fromhex(_shape_anchor[k:k + 8]), 'little'))
    fs_put(site, [B(site, start)], 'Layout2 pane global matrix: HUD panes past the 16:9 edge region and the menu bars moved to the taller screen\'s edges with their subtrees (shape_anchor.c)')
    ctx.capabilities.add('SCREEN_ASPECT')


def dynamic_resolution(ctx):
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    site = ctx.others.get('dynamic resolution')
    if site is None or ctx.others.get('dynamic resolution update') is None: return   # not both found in this build (a red line from the locator): the game's own dynamic resolution
    fs_site(site, '017c40bd')   # ldr s1,[x0,#0x7c]
    start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in drs_controller: emit(w)
    fs_put(site, [B(site, start)], 'dynamic resolution level: 0 (full resolution), or with state +0x40 (DM_DYNAMIC_RESOLUTION) a climb on the load measured at each level')
    ctx.capabilities.add('DYNAMIC_RESOLUTION')

# Render scale (DM_RENDER_SCALE, state +0x10, dm/host/loader.c; from kid-with-sword-remake's FF line, HookLink VX1: the launcher's Render scale and Resolution dial, Cool mode and Potato mode). The 3D views' sizes come from the scale the engine stores at main+0x31d3f48 (str s0,[x20,#0xe5c], found by
# upstream PR #1497), but that store and the size loop after it (main+0x31d3fd8, which clears the "scale changed" bit 3 of [x20+0xe2c] at main+0x31d40b4) run only in a frame
# where the dynamic-resolution controller (bl main+0x805aa0) answers status 0, a new scale: at a steady 60 fps it never does, so a stub at the store alone changed nothing until
# the game came under load. Two stubs: at the controller's answer (main+0x31d3ee4, ubfx of its status byte) a host scale below 1.0 that is not the stored one makes the status 0, so
# that frame recomputes the sizes; at the store the host scale replaces the game's (seedds' fixed form of #1497's ceiling). The scale is then fixed and the dynamic resolution off;
# 0, unset or over 1.0 run the game's own code; 1.0 itself is fixed at the full base (this game's slider, game.tsv render_scale). Registers and flags are kept but x8 (the status, as the game reads it next) and s0 (dead after the store: main+0x31d3f84 reloads it).
# The scale is a fraction of the output (the size loop's cap at main+0x31d3fe8 is skipped on this path, bit 0x13 of +0xe20): docked, 0.75 is the game's usual 1920x1080 and 0.5
# draws 1280x720, 0.9 2328x1310. The game picks its NDSR network by the ratio, and nvn_mtl.m's DM_NDSR replacement takes whichever follows the chain's third dispatch
_scale_status, _scale_store = 0x31d3ee4, 0x31d3f48

def _bcond(frm, to, cond): return 0x54000000 | (((to - frm) >> 2) & 0x7ffff) << 5 | cond
def _cbz_w(frm, to, rt): return 0x34000000 | (((to - frm) >> 2) & 0x7ffff) << 5 | rt

def render_scale(ctx):
    here, emit = ctx.here, ctx.emit
    ctx.site(_scale_status, '089c60d3')   # ubfx x8,x0,#32,#8: the controller's status byte
    s = here(); at = lambda k: s + 4 * k   # the stub's k-th word; done is word 16
    for k, w in enumerate((
            0xd3609c08,                       # ubfx x8,x0,#32,#8     the original
            0xa9be47f0,                       # stp x16,x17,[sp,#-32]!
            0xd53b4210,                       # mrs x16,nzcv
            0xf9000bf0,                       # str x16,[sp,#16]
            ADRP(16, at(4), ctx.state),
            0xb9401211,                       # ldr w17,[x16,#0x10]  the host scale's bits
            _cbz_w(at(6), at(16), 17),        # cbz w17,done         unset
            0x52a7f010,                       # mov w16,#0x3f800000
            0x6b10023f,                       # cmp w17,w16
            _bcond(at(9), at(16), 0x8),       # b.hi done            over 1.0, negative or NaN: the game's own
            0x7100051f,                       # cmp w8,#1
            _bcond(at(11), at(16), 0x0),      # b.eq done            status 1, the game's other request (main+0x31d3f4c), is left alone
            0xb94e5e90,                       # ldr w16,[x20,#0xe5c] the stored scale
            0x6b11021f,                       # cmp w16,w17
            _bcond(at(14), at(16), 0x0),      # b.eq done            already the host's
            0x52800008,                       # mov w8,#0            status 0: a new scale, so the sizes are recomputed
            0xf9400bf0,                       # done: ldr x16,[sp,#16]
            0xd51b4210,                       # msr nzcv,x16
            0xa8c247f0)):                     # ldp x16,x17,[sp],#32
        assert here() == at(k); emit(w)
    emit(B(here(), _scale_status + 4))
    ctx.put(_scale_status, [B(_scale_status, s)], 'dynamic-resolution status: a host render scale not yet stored asks for new 3D sizes (state +0x10)')

    ctx.site(_scale_store, '805e0ebd')    # str s0,[x20,#0xe5c]
    s = here()   # original is word 11
    for k, w in enumerate((
            0xadbf7ffe,                       # stp q30,q31,[sp,#-32]!
            0xa9bf47f0,                       # stp x16,x17,[sp,#-16]!
            ADRP(16, at(2), ctx.state),
            0xd53b4211,                       # mrs x17,nzcv
            0xbd40121e,                       # ldr s30,[x16,#0x10]  the host scale
            0x1e2023c8,                       # fcmp s30,#0.0
            _bcond(at(6), at(11), 0xd),       # b.le original        unset, negative or NaN
            0x1e2e101f,                       # fmov s31,#1.0
            0x1e3f23c0,                       # fcmp s30,s31
            _bcond(at(9), at(11), 0xc),       # b.gt original        over 1.0
            0x1e2043c0,                       # fmov s0,s30          the host's fixed scale
            0xbd0e5e80,                       # original: str s0,[x20,#0xe5c]
            0xd51b4211,                       # msr nzcv,x17
            0xa8c147f0,                       # ldp x16,x17,[sp],#16
            0xacc17ffe)):                     # ldp q30,q31,[sp],#32
        assert here() == at(k); emit(w)
    emit(B(here(), _scale_store + 4))
    ctx.put(_scale_store, [B(_scale_store, s)], 'final 3D view scale: the host render scale fixes it, up to 1.0 (over 1.0 = the game\'s own)')

    ctx.render_scale = 1   # the loader takes DM_RENDER_SCALE up to 1.0 and the launcher offers the row (patch_nso.py RENDER_SCALE)

# Wide view (DM_WIDE_VIEW, a launcher setting): the game sizes its output from fixed constants, so a screen wider than 16:9 shows bars. These stubs take the widths from the state page,
# written at each start from the screen's shape (loader.c), so the view widens and nothing stretches, and 0 there (16:9, or the setting off) runs the game's own constant. Sites from
# nxnative PR 1460 by vladbondarenko97, which cut them at build time; v131072 only, by the frame-ratio function's address. Each stub writes only the register the constant loads
wide_sites = [(0x1202ee0, 0xD2814008, 0x100, 8, 'graphics setup output width'), (0x31f39f4, 0xD2814008, 0x100, 8, 'docked render width'),
              (0x31f3a00, 0xD280F008, 0x104, 8, 'handheld render width'), (0xecbc80, 0x52A8A409, 0x108, 9, 'output width as a float'),
              # The view size the game lays its screen out by: main+0xe8303c stores a fixed 1920.0 x 1080.0 unless its screen object's +0x1a9 / +0x1aa flags are set (docked takes the
              # render size there, and nxnative PR 1460 was only played docked). Handheld took the fixed size, so the HUD and menus were laid out for 16:9 and spread over the wider
              # picture. The width comes from the state page (+0x118, a float: the handheld render width; DM_WIDE_VIEW_SIZE=0 leaves 0 there and the game's own 1920)
              (0xe8303c, 0x52A89E08, 0x118, 8, 'view size width as a float')]
def wide_view(ctx):
    if ctx.base != 0x6e6be0: return
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    for site, orig, off, rd, what in wide_sites:
        fs_site(site, orig.to_bytes(4, 'little').hex())
        start = here(); emit(ADRP(rd, here(), FS_STATE_OFF))
        emit(0xB9400000 | (off // 4) << 10 | rd << 5 | rd)      # ldr w<rd>,[x<rd>,#off]
        emit(0x35000040 | rd)                                   # cbnz w<rd>,the branch back
        emit(orig); emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], f'wide view: {what} from the state page (0: the game\'s own)')
    # The output resolution table (main+0x3f58540, read here by the display mode, a leaf ending in ret: x9..x11 are free): each entry's width from its height and the screen's ratio
    site = 0x112c604
    fs_site(site, '287968f8')   # ldr x8,[x9,x8,lsl #3]: width in the low word, height in the high one
    start = here(); emit(0xF8687928); emit(ADRP(9, here(), FS_STATE_OFF))
    for w in (0xB9410D2A, 0x340000EA, 0xD360FD0B, 0x9B0B7D4A, 0x9142014A, 0xD354FD4A, 0xD37CED4A, 0xB3407D48): emit(w)   # ratio (16.16); if 0 skip; height * ratio, to a multiple of 16; width
    emit(B(here(), site + 4))
    fs_put(site, [B(site, start)], 'wide view: output resolution table width from its height')
    # The 3D view: the render targets follow the wider size, but the game's cameras keep a 16:9 aspect, so the picture was stretched. sead::PerspectiveProjection::doUpdateMatrix (main+0x3485cc0, a
    # leaf: vtable main+0x4bf8c70 slot 11; near +0x98, far +0x9c, tan of the half angle +0xac, aspect +0xb0) gives a 16:9 projection (within 0.01) the picture's ratio (state +0x110, float; 0 = off)
    # and stores it, so what reads the aspect back agrees with the matrix: the vertical angle stays and the sides show more. Every 16:9 projection takes it: sead's default near 1 / far 10000
    # (main+0xea5480) is the shape the game's own cameras keep, and leaving it at 16:9 left the picture stretched on the phone. Views of another ratio (cube maps, shadow maps) stay as they are.
    # The state page counts the matrices built (+0x120) and widened (+0x124) and keeps the last other ratio seen (+0x128), for the log (hle_nvn.c). x9, x16, s2..s4 and the flags are free at the entry
    site = 0x3485cc0
    fs_site(site, '0084552d')   # ldp s0,s1,[x0,#0xac]
    start = here(); emit(0x2D558400); emit(ADRP(16, here(), FS_STATE_OFF))
    for w in (0xB9412209, 0x11000529, 0xB9012209,                                                   # +0x120 += 1
              0xBD411202, 0x1E202048, 0x54000240,                                                   # ldr s2,[x16,#0x110]; fcmp s2,#0; b.eq back
              0x5291C729, 0x72A7FC69, 0x1E270123, 0x1E233823, 0x1E20C063, 0x529AE149, 0x72A78469, 0x1E270124, 0x1E242060, 0x540000EA,   # |aspect - 16/9| >= 0.01: b.ge other
              0x1E204041, 0xBD00B001,                                                               # fmov s1,s2; str s1,[x0,#0xb0]
              0xB9412609, 0x11000529, 0xB9012609, 0x14000002,                                       # +0x124 += 1; b back
              0xBD012A01):                                                                          # other: str s1,[x16,#0x128]
        emit(w)
    emit(B(here(), site + 4))
    fs_put(site, [B(site, start)], 'wide view: a 16:9 camera takes the picture\'s ratio (the sides show more, nothing stretched)')
    # The game's code holds copies of that matrix code (getProjectionMatrix main+0x23b910 checks the vtable slot and builds it in place), so the stub above was never reached: the phone's log
    # counted 0 projections in 1,200 frames. The ratio is changed where the game sets it instead: each store of a perspective projection's aspect (+0xb0, with its changed flag +8) whose value is
    # 16:9 (within 2 ulps of 1920/1080) stores the picture's ratio when wide view is on. Viewport ratios of the camera list (main+0x3b50988, +0x3b50b50, +0x28e72a4), sead's set (main+0xea4b20, the
    # aspect in s8) and constructor (main+0x3485c64, s3), and the game's cameras' own parameter (+0x140: main+0x4c533c, +0x2e1bb6c, +0x2e1c7d0). x16 and x17 are dead at each site (a call or a
    # write follows) and the test is cbnz, as two sites carry live flags. Each site counts its passes at state +0x130 + 4 * index and the widened ones at +0x124, for the log (hle_nvn.c)
    for k, (site, orig, n) in enumerate(((0x3485c64, 0xBD00B003, 3), (0xEA4B20, 0x2D15A260, 8), (0x4C533C, 0xBD00B280, 0), (0x653BD4, 0xBD00B100, 0), (0x6545F4, 0xBD00B340, 0),
                                         (0x28E72A4, 0xBD00B100, 0), (0x2DD7164, 0xBD00B2C0, 0), (0x2E1BB6C, 0xBD00B2E0, 0), (0x2E1C7D0, 0xBD00B2A0, 0), (0x3B50988, 0xBD00B000, 0),
                                         (0x3B50B50, 0xBD00B300, 0))):
        fs_site(site, orig.to_bytes(4, 'little').hex())
        c = (0x130 + 4 * k) // 4
        start = here(); emit(ADRP(16, here(), FS_STATE_OFF))
        if site in (0x4C533C, 0x2E1BB6C, 0x2E1C7D0):
            # The game's cameras' own aspect parameter (+0x140, copied from +0xc8): main+0x4c533c stores it every frame, 1.7778 on the phone (15,302 stores in one run). It is not
            # 1920/1080 to the bit (the exact test above left it alone), so a value within about 0.01 of 16:9 takes the picture's ratio, tested on its bits as these sites carry live
            # flags. A value already wide is left as it is: with the view size above the game may set the wide ratio itself, and it must not be widened twice. The value the game
            # came with is kept at +0x128 for the log
            for w in (0xB9400211 | c << 10, 0x11000631, 0xB9000211 | c << 10, 0xBD012A00,      # this site's passes += 1; +0x128 = the aspect as the game set it
                      0x1E260011, 0x52800010 | 0x4E39 << 5, 0x72A00010 | 0x3FE2 << 5,            # w17 = its bits; w16 = the bits of 16/9 - 0.0098
                      0x4B100231, 0x53127E31, 0x35000011 | 8 << 5):                              # (w17 - w16) >> 18 != 0: not 16:9, store as is
                emit(w)
            emit(ADRP(16, here(), FS_STATE_OFF))
            for w in (0xB9411211, 0x34000011 | 5 << 5, 0x1E270220,                              # the picture's ratio (+0x110), 0: store as is; s0 = ratio
                      0xB9412611, 0x11000631, 0xB9012611, orig):                                 # widened += 1; the game's store
                emit(w)
            emit(B(here(), site + 4))
            fs_put(site, [B(site, start)], f'wide view: the game camera\'s 16:9 aspect parameter takes the picture\'s ratio (site {k})')
            continue
        for w in (0xB9400211 | c << 10, 0x11000631, 0xB9000211 | c << 10,                    # this site's passes += 1
                  0x1E260011 | n << 5, 0x52800010 | 0x8E37 << 5, 0x72A00010 | 0x3FE3 << 5,      # w17 = the aspect's bits; w16 = 16:9's bits - 2
                  0x4B100231, 0x53027E31, 0x35000011 | 8 << 5):                                  # (w17 - w16) >> 2 != 0: not 16:9, store as is
            emit(w)
        emit(ADRP(16, here(), FS_STATE_OFF))
        for w in (0xB9411211, 0x34000011 | 5 << 5, 0x1E270220 | n,                              # ratio (+0x110), 0: store as is; s<n> = ratio
                  0xB9412611, 0x11000631, 0xB9012611, orig):                                     # widened += 1; the game's store
            emit(w)
        emit(B(here(), site + 4))
        fs_put(site, [B(site, start)], f'wide view: a 16:9 camera aspect set here takes the picture\'s ratio (site {k})')
    wide_hud(ctx)

# Wide view's HUD, menus and movies in the middle 16:9 (DM_WIDE_HUD, on with Wide view). The sites are Ivan0xFF's (MIT, "The matrix-update, UI and movie sites: Copyright (c)
# 2026 Ivan0xFF"), from NX2navi's recomp/patches-v111.txt, for this same build (e0f3ccfa); written here as stubs of our own, which change no flags.
# - The 2D canvas setup (main+0x774330) loads a layout's projection rows at main+0x774368 (ldp q1, q4, [x2]; the canvas is x0, its screen 0x1b8 before it). When the projection is
#   the full-screen orthographic one of the 3840x2160 layout grid (m00 = 2/3840, m11 = 2/2160, compared by their bits), its first row is multiplied by the squeeze (state +0x160:
#   16:9 over the picture's ratio, 0 = off), so the UI keeps its shape in the middle of the wider picture and the markers that follow the 3D world stay on their targets. Four
#   screens keep the whole picture, by their vtable: the item-wheel background (main+0x4bed098) and the pause and system menu backgrounds (main+0x4be4fb0) redraw a capture of the
#   whole picture, and the event and loading fades (main+0x4be61c8, main+0x4be7b30) must cover it all. Count at state +0x168. x16, x17 and v16 are free there (a leaf; v16..v19 are
#   written next).
# - The movie layer's draw (main+0x3b5c71c) builds a viewport over the whole picture at x29 - 40 (min x +8, max x +16); after ldp x9, x8, [x19, #0x18] (main+0x3b5c758) it moves in
#   by the margin on each side (state +0x164: (1 - squeeze) / 2 of the width), the middle 16:9. Count at state +0x16c. x16, x17 and s16..s19 are free there.
# The stubs' words were assembled with clang from the source in this comment's commit; nop placeholders are the patch-relative instructions written below
hud_words = (0xAD401041, 0xD503201F, 0xBD416210, 0x1E260211, 0x34000451, 0x1E260031, 0x52911130, 0x72A74110, 0x4A110210, 0x350003B0, 0x0E0C3C91, 0x52973AD0, 0x72A74E50,
             0x4A110210, 0x35000310, 0xD106E011, 0xF9400231, 0xD503201F, 0xD503201F, 0xCA110210, 0xB4000250, 0xD503201F, 0xD503201F, 0xCA110210, 0xB40001D0, 0xD503201F,
             0xD503201F, 0xCA110210, 0xB4000150, 0xD503201F, 0xD503201F, 0xCA110210, 0xB40000D0, 0x4F909021, 0xD503201F, 0xB9416A11, 0x11000631, 0xB9016A11, 0xD503201F)
hud_keep = (0x4bed098, 0x4be4fb0, 0x4be61c8, 0x4be7b30)   # item wheel background, pause / system menu backgrounds, event fade, loading fade
movie_words = (0xD503201F, 0xBD416633, 0x1E260270, 0x340001B0, 0xD100A3B0, 0xBD400A10, 0xBD401211, 0x1E303A32, 0x1E330A52, 0x1E322A10, 0x1E323A31, 0xBD000A10,
               0xBD001211, 0xB9416E30, 0x11000610, 0xB9016E30, 0xA941A269, 0xD503201F)
def wide_hud(ctx):
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    site = 0x774368
    fs_site(site, (0xAD401041).to_bytes(4, 'little').hex())   # ldp q1, q4, [x2]
    start = here(); keep = iter(hud_keep); pending = None
    for i, w in enumerate(hud_words):
        if i in (1, 34): w = ADRP(16, here(), FS_STATE_OFF)                       # the state page
        elif i in (17, 21, 25, 29): pending = next(keep); w = ADRP(16, here(), pending)   # a vtable that keeps the whole picture: its page
        elif i in (18, 22, 26, 30): w = ADDI(16, 16, pending & 0xFFF)               # ... and its offset in the page
        elif i == 38: w = B(here(), site + 4)                                         # back
        emit(w)
    fs_put(site, [B(site, start)], 'wide view: the HUD and menus keep 16:9 in the middle of the picture (Ivan0xFF\'s site, via NX2navi)')
    site = 0x3b5c758
    fs_site(site, (0xA941A269).to_bytes(4, 'little').hex())   # ldp x9, x8, [x19, #0x18]
    start = here()
    for i, w in enumerate(movie_words):
        if i == 0: w = ADRP(17, here(), FS_STATE_OFF)
        elif i == 17: w = B(here(), site + 4)
        emit(w)
    fs_put(site, [B(site, start)], 'wide view: movies in the middle 16:9 (Ivan0xFF\'s site, via NX2navi)')

# A full model heap (DM_HEAP_RETRY, on by default). The game's OptimizeChangeBank thread rebuilds a model's material block (main+0x4366e0) with memory from small
# heaps of the model's own ("Model/....bfres", tens of KB), children of a large one, and checks none of these allocations: two CPU buffers made with the heap's
# tryAlloc (vtable +0x30; lr main+0x436910 and main+0x436da4, sized in x21 and x22) and two blocks of GPU memory (main+0x502050 with a descriptor at sp+0x40 whose
# heap is at +8; lr main+0x436f1c and main+0x437098). When the heap is full the game goes on with a null block: on the iPhone (test28-2) "BufferInitialize: pool
# has no storage" and a crash in h_nvnMemoryPoolGetFlags 11 minutes in, backtrace main+0x436fb4. Hookshot found the same (NotRexed/Hookshot issue 1697, PR 2451):
# its layout of these sead heaps (+0x28 memory, +0x30 size, +0x38 parent) and this function's sites are the ones used here; the stubs are our own. Each failure
# is tried again in the heap's parents (at most 16), the first with room; the GPU memory last in the game's default heap (no heap named). The block goes back to
# the heap whose range holds it when freed (the game frees by address). Each stub runs after the game's call has returned, so x0-x18 are free; the CPU stub saves
# x19 / x20 for its walk. State +0x170 counts CPU blocks made in a parent, +0x174 GPU blocks made elsewhere; +0x17c != 0 (DM_HEAP_RETRY=0) leaves the game as shipped.
# The words were assembled with clang; brk #n marks the patch-relative words written here (1 the state page, 2 back, 3 the game's failure path, 4 the call, 9 the
# game's own instruction)
heap_cpu_words = (0xb5000300, 0xd4200020, 0xb9417e11, 0x350002b1, 0xa9bf53f3, 0xf94027f3, 0xf9400673, 0x52800214, 0xf9401e73, 0xb40001d3, 0x71000694, 0x54000180,
                  0xaa1303e0, 0xaa1503e1, 0x52800102, 0xf9400268, 0xf9401908, 0xd63f0100, 0xb4fffec0, 0xd4200020, 0xb9417211, 0x11000631, 0xb9017211, 0xa8c153f3,
                  0xd4200120, 0xd4200040)
heap_gpu_words = (0x370002a0, 0xb40002b3, 0xd4200020, 0xb9417e11, 0x35000231, 0xaa1303e9, 0xf9401d29, 0xf90027e9, 0x91038360, 0x910103e1, 0x52800022, 0xd4200080,
                  0x37000080, 0xf94027e9, 0xb5ffff09, 0x14000005, 0xd4200020, 0xb9417611, 0x11000631, 0xb9017611, 0xf90027f3, 0xd4200040, 0xd4200060)
def heap_retry(ctx):
    if ctx.base != 0x6e6be0: return   # this build (v131072) only
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    def stub(words, site, orig, subst, back, fail=None):
        fs_site(site, orig.to_bytes(4, 'little').hex())
        start = here()
        for i, w in enumerate(words):
            w = subst.get(i, w)
            if w == 0xd4200020: w = ADRP(16, here(), FS_STATE_OFF)
            elif w == 0xd4200040: w = B(here(), back)
            elif w == 0xd4200060: w = B(here(), fail)
            elif w == 0xd4200080: w = BL(here(), 0x502050)
            elif w == 0xd4200120: w = orig
            emit(w)
        return start
    for site, orig, size_mov in ((0x436910, 0xa90d577f, 0xaa1503e1), (0x436da4, 0x52800f13, 0xaa1603e1)):   # mov x1, x21 / x22: the size
        start = stub(heap_cpu_words, site, orig, {13: size_mov}, site + 4)
        fs_put(site, [B(site, start)], 'full model heap: a CPU buffer the heap had no room for is made in its parents (Hookshot issue 1697)')
    for site, obj, fail in ((0x436f1c, 0x91038360, 0x437be4), (0x437098, 0xaa1503e0, 0x437c04)):            # add x0, x27, #0xe0 / mov x0, x21: the object
        start = stub(heap_gpu_words, site, 0x37000040, {8: obj}, site + 8, fail)
        fs_put(site, [B(site, start)], 'full model heap: GPU memory the heap had no room for is made in its parents or the default heap (Hookshot issue 1697)')

# The framework's half rate, asked for by the host. Some of this game counts calcs, not time: the timeline that fires its subtitles (PlaySubtitleWithVoice trigger events) and
# its movie player, which takes one picture a calc (the limit at the player's +0x20 is 1 for the creation argument the game passes, main+0x3b5c55c). The frame ratio above
# moves what reads the time object by real time, so below 60 fps the two fall apart: on an iPhone at 33 fps with the player let take two pictures a calc, the opening's
# picture kept time and "However, there was one particular boy..." came up 98 s into it, over the nightmare's castle gate; at 53 fps the narration was over by 61 s, over
# Link asleep. The game's own answer to a frame of two vsyncs is its half rate: two calcs a drawn frame (bit 0 of the framework's +0x24f; frame_step's note), 60 calcs a second
# at 30 fps. It asks for it once a calc from bit 0 of [ModuleSystem+0xa30]: 2 (enter) or 1 (leave) into the framework's +0x24e (main+0x650ea4..0x650eb4, v131072; the frame
# function main+0x346c680 acts on it at the end of a pass, and while the mode is on the request is written only at the calc that is drawn). The stub ORs the host's ask into that
# bit: state +0x44, 1 while the host holds 2 vsyncs or more under DM_FPS_HALF_RATE=1 (hle_nvn.c fstep_tick). x16 and x17 are free there (the function uses x16 only as a
# local temporary far from the site, x17 nowhere).
def half_rate(ctx):
    here, emit, fs_site, fs_put, FS_STATE_OFF = ctx.here, ctx.emit, ctx.site, ctx.put, ctx.state
    f = ctx.others.get('half rate request')
    if f is None: return   # not found in this build (a red line from the locator): the game's own choice
    site = f + 0x1a4
    fs_site(site, '68324ab9')   # ldr w8,[x19,#0xa30]
    start = here()
    emit(0xb94a3268)                        # ldr w8,[x19,#0xa30]   the game's own flags
    emit(ADRP(16, here(), FS_STATE_OFF))
    emit(0xb9404610)                        # ldr w16,[x16,#0x44]   the host's ask, 0 or 1
    emit(0x2a100108)                        # orr w8,w8,w16
    emit(B(here(), site + 4))
    fs_put(site, [B(site, start)], 'half rate request: the game\'s own flag or the host\'s ask (state +0x44, DM_FPS_HALF_RATE)')
    ctx.capabilities.add('HALF_RATE')

MATCH_FRAME_STEP = {'main': [
    {'name': 'frame ratio from the host\'s step', 'size': 0x9b4, 'fingerprints': ['6ae2aff5344d14568e4dbaf93455e2d8278384bf892ed6c6eca87fef98fbcd1d'], 'stub': frame_step,   # v131072 main+0x6e6be0
     'others': {'dynamic resolution': {'size': 0x294, 'fingerprints': ['7af6ceb0aedf8e0c17dc08ce17fcd6a7cba6d394a0d09e3b504c6d668dc418e7']},   # v131072 main+0x8065e0
                'dynamic resolution update': {'size': 0xb24, 'fingerprints': ['5a423697838976baf286cffa5e2ceef0d4e037abbcd9d371e90e9e702d61b3d4']},   # main+0x805aa0
                'half rate request': {'size': 0x938, 'fingerprints': ['cf27987b41456695ce0447d7b711f9a4f2d6424d4f3c04744252ca2cfb47dc2c']},   # main+0x650d00
                **screen_shape_functions}},
]}

# Movie pictures: no cut. The movies are AV1 at 60 pictures a second (Event/Movie/*.webm, no sound track: the opening's Dm_Kokiri_0000 is 9,254 pictures, 154.2 s), and the
# player takes one picture a calc (main+0x3b5ca60 clamps to its limit at +0x20, 1 + (the creation argument >= 2) at main+0x3b5d084; the game passes 1). A cut that made the
# limit 2 (cinc w8,w28,ge → add w8,w28,#1) kept the picture's time at 33 fps on an iPhone (9,254 pictures in about 156 s, against 262 s) and left the subtitles behind it, which
# count calcs as the player did: worse to watch than a movie that is slow as a whole. The half rate above keeps both in step
BINDING = [
    {'what': 'wide view: output and render widths from the state page', 'now': 'build', 'goal': 'game', 'purpose': 'rendering',
     'why': "the game's own size constants, at fixed addresses of v131072; a function-matched rule could carry them over the game's updates"},
    {'what': 'half rate request: the game\'s own flag or the host\'s ask', 'now': 'game', 'goal': 'game', 'purpose': 'frame rate',
     'why': "the game's own half-rate request, found by its function's fingerprint on any build that keeps the function; switchable (DM_FPS_HALF_RATE)",
     'checked': 'v131072 main: one function with this fingerprint, the site, the request byte and the frame function that acts on it read by disassembly (2026-11-09)'},
    {'what': 'frame ratio from the host\'s step', 'now': 'game', 'goal': 'game', 'purpose': 'frame rate',
     'why': "the game's own frame-ratio division, found by its function's fingerprint on any build that keeps the function",
     'checked': 'v131072 main: one function with this fingerprint, the site and its free registers read by disassembly (2026-11-08)'},
    {'what': 'dynamic resolution: full size, or a climb on the load measured at each level', 'now': 'game', 'goal': 'game', 'purpose': 'rendering',
     'why': "the game's own dynamic-resolution level function and update, found by their functions' fingerprints on any build that keeps both; switchable (DM_DYNAMIC_RESOLUTION)",
     'checked': 'v131072 main: one function with each fingerprint (the level function a leaf, x2..x11 / x16 / x17 / s0..s2 free), its callers, the update and the controller fields read by disassembly, the fields read in play (2026-11-08); the climb run natively against a model of the update and in play to full size (2026-11-09)'},
    {'what': 'screen shape: taller render targets, cameras, Layout2 panes and a 16:9 movie viewport (DM_SCREEN_ASPECT)', 'now': 'game', 'goal': 'game', 'purpose': 'rendering',
     'why': "the game's own display setup, camera, pane and movie code; installed together after every function matches. Indexed pane edits verify the authored name, class and dimensions they use",
     'checked': 'v131072 main: one function per fingerprint, free registers read at each site; indexed pane names, classes and dimensions checked against the UIL records. PR #3037 measured Vert+ framing and the movie aspect on Mac; final iPad title retest pending'},
]
