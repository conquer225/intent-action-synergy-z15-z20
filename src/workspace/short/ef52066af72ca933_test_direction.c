#include "direction_policy.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    double a[3]={.54,.32,.72},mad[3]={.002,.004,.005};
    assert(direction_fit_valid(a,mad));
    assert(fabs(direction_x(a,.32)-1.0/6)<1e-9);
    assert(fabs(direction_x(a,.54)-.5)<1e-9);
    assert(fabs(direction_x(a,.72)-5.0/6)<1e-9);
    assert(fabs(direction_x(a,.43)-1.0/3)<1e-9);
    assert(fabs(direction_x(a,.63)-2.0/3)<1e-9);
    assert(direction_x(a,-1)<0 && direction_x(a,2)>1);
    double reversed[3]={.54,.72,.32};
    assert(direction_fit_valid(reversed,mad));
    assert(fabs(direction_x(reversed,.72)-1.0/6)<1e-9);
    assert(fabs(direction_x(reversed,.32)-5.0/6)<1e-9);
    double constant[3]={.5,.5,.5},wrong_center[3]={.8,.32,.72};
    assert(!direction_fit_valid(constant,mad));
    assert(!direction_fit_valid(wrong_center,mad));
    double jitter[3]={.08,.04,.04};assert(!direction_fit_valid(a,jitter));
    double bad[3]={NAN,.32,.72};assert(!direction_fit_valid(bad,mad));
    mad[0]=-1;assert(!direction_fit_valid(a,mad));
    puts("direction boundaries, reversed axis, noise and invalid inputs: PASS");
    return 0;
}
