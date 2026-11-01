#ifndef Z15_DIRECTION_POLICY_H
#define Z15_DIRECTION_POLICY_H
#include <math.h>
#include <stdbool.h>
/* center, left, right: local anchors, not an applied Tobii screen model. */
static inline bool direction_fit_valid(const double a[3],const double mad[3]) {
    for(int i=0;i<3;i++)if(!isfinite(a[i])||!isfinite(mad[i])||mad[i]<0)return false;
    double sign=a[2]>a[1]?1:-1;
    double lc=sign*(a[0]-a[1]),cr=sign*(a[2]-a[0]);
    return lc>=.05 && cr>=.05 && lc>=3*(mad[0]+mad[1]) && cr>=3*(mad[0]+mad[2]);
}
static inline double direction_x(const double a[3],double x) {
    double sign=a[2]>a[1]?1:-1;
    double left=sign*a[1],center=sign*a[0],right=sign*a[2];
    x*=sign;
    /* Do not clamp: extrapolated coordinates outside [0,1] cannot select. */
    return x<center?1.0/6+(x-left)/(center-left)/3:.5+(x-center)/(right-center)/3;
}
#endif
