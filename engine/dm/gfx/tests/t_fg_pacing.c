#include "../nvn/nvn_fg_pacing.h"
#include "../../host/frame_mode.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    assert(nvn_fg_even_hold(1.0/30, 1.0/60));
    assert(nvn_fg_even_hold(1.0/60, 1.0/120));
    assert(nvn_fg_even_hold(1.0/30, 1.0/120));
    assert(nvn_fg_even_hold(33333333e-9, 1.0/60));
    assert(!nvn_fg_even_hold(1.0/40, 1.0/120));
    assert(!nvn_fg_even_hold(1.0/40, 1.0/60));
    assert(!nvn_fg_even_hold(1.0/60, 1.0/60));
    assert(!nvn_fg_even_hold(1.0/30, 1.0/30));
    assert(!nvn_fg_even_hold(0, 1.0/60));
    assert(!nvn_fg_even_hold(INFINITY, 1.0/60));
    assert(nvn_fg_debt_allowed(5,5,1,0,0,0));
    assert(!nvn_fg_debt_allowed(4,5,1,0,0,0));
    assert(!nvn_fg_debt_allowed(5,5,0,0,0,0));
    assert(!nvn_fg_debt_allowed(5,5,1,1,0,0));
    assert(!nvn_fg_debt_allowed(5,5,1,0,1,0));
    assert(!nvn_fg_debt_allowed(5,5,1,0,0,1));
    assert(dm_frame_mode_override(0,"DM_FPS_TARGET")==NULL);
    assert(!strcmp(dm_frame_mode_override(1,"DM_FRAMEGEN"),"0"));
    assert(!strcmp(dm_frame_mode_override(2,"DM_FRAMEGEN"),"1"));
    assert(!strcmp(dm_frame_mode_override(2,"DM_FPS_TARGET"),"30"));
    assert(!strcmp(dm_frame_mode_override(3,"DM_FPS_TARGET"),"60"));
    assert(!strcmp(dm_frame_mode_override(3,"DM_FRAMEGEN"),"1"));
    assert(dm_frame_mode_override(3,"DM_FRAMEGEN_SCALE")==NULL);
    setenv("DM_FRAME_MODE","2",1);
    dm_frame_mode_apply();
    assert(!strcmp(getenv("DM_FRAMEGEN"),dm_frame_mode_override(2,"DM_FRAMEGEN")));
    assert(!strcmp(getenv("DM_FPS_TARGET"),dm_frame_mode_override(2,"DM_FPS_TARGET")));
    puts("Frame interpolation clock, debt invalidation, and mode dependency contract passed");
    return 0;
}
