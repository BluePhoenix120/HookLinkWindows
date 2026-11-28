#ifndef NVN_FG_PACING_H
#define NVN_FG_PACING_H
#include <math.h>
#include <stdint.h>
// Only synthesize a midpoint if two equal groups of counted ticks fit.
static inline int nvn_fg_even_hold(double period, double tick) {
    if (!(period > 0 && tick > 0)) return 0;
    double n = period / tick;
    if (!(n >= 1.5 && n <= 120)) return 0;
    unsigned ticks = (unsigned)(n + 0.5);
    return ticks >= 2 && !(ticks & 1) && fabs(n - ticks) <= 0.125;
}
static inline int nvn_fg_debt_allowed(uint64_t epoch, uint64_t current,
                                      int link, int rescue, int covered, int suspended) {
    return epoch == current && link && !rescue && !covered && !suspended;
}
#endif
