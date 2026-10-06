/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_features.h"
#include "cb1_native_prefix_fixtures.h"
#include <assert.h>
#include <fenv.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void reject(const struct cb1_hdr10_descriptor *samples, size_t count, double boundary)
{
    uint16_t result[]={37,41,43}, saved[3]; double peak=.125;
    memcpy(saved,result,sizeof(saved));
    assert(!cb1_hdr10_baseline(samples,count,boundary,result,&peak));
    assert(!memcmp(result,saved,sizeof(saved)) && peak==.125);
}

int main(void)
{
    unsigned checked=0;
    for (size_t i=0; i<sizeof(cb1_prefix_fixtures)/sizeof(*cb1_prefix_fixtures); ++i) {
        const struct cb1_prefix_fixture *f=&cb1_prefix_fixtures[i];
        uint16_t result[3]; double peak;
        assert(cb1_hdr10_baseline(f->samples,f->count,f->boundary_pts,result,&peak));
        assert(!memcmp(result,f->base,sizeof(result)));
        ++checked;
    }
    assert(checked==18);
    struct cb1_hdr10_descriptor samples[2]={
        {.pts=0,.global={0.f,.8f,.25f}},
        {.pts=.5,.global={0.f,.8f,.75f}}};
    uint16_t result[3]; double peak;
    assert(cb1_hdr10_baseline(samples,2,.75,result,&peak));
    /* The observed boundary changes only the final picture's duration. */
    assert(result[0]==0 && result[1]==1706 && result[2]==3276);
    assert(peak==(double).8f);
    const int modes[]={FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO,FE_TONEAREST};
    for (unsigned i=0; i<sizeof(modes)/sizeof(*modes); ++i) {
        assert(!fesetround(modes[i]));
        assert(cb1_hdr10_baseline(samples,2,.75,result,&peak));
        assert(result[1]==1706 && result[2]==3276 && fegetround()==modes[i]);
    }
    assert(!fesetround(FE_TONEAREST));
    reject(NULL,2,NAN); reject(samples,0,NAN);
    reject(samples,2,.5); reject(samples,2,INFINITY); reject(samples,2,1.51);
    samples[1].global[2]=1.f; reject(samples,2,NAN);
    samples[1].global[2]=.75f; samples[1].pts=1.01; reject(samples,2,NAN);
    printf("Exact bounded L1 baseline: %u independent prefixes\n",checked);
}
