/* SPDX-License-Identifier: MIT */
#include "cb1_trim_math.h"
#include <assert.h>
#include <string.h>

int main(void)
{
    const double neutral[5]={2048,2048,2048,2048,2048};
    double decoded[5];cb1_trim_decode(decoded,neutral);
    assert(decoded[0]==1 && decoded[1]==0 && decoded[2]==1 && decoded[3]==0 && decoded[4]==0);
    const double in[3]={4,16,64};double out[3];
    assert(cb1_trim_rgb(out,in,128,neutral));assert(!memcmp(in,out,sizeof(out)));
    const double half[5]={0,2048,2048,2048,2048};
    assert(cb1_trim_rgb(out,in,128,half));assert(out[0]==2 && out[1]==8 && out[2]==32);
    const double dark[5]={2048,0,2048,2048,2048};
    assert(cb1_trim_rgb(out,in,128,dark));assert(out[0]==0 && out[1]==0 && out[2]==0);
    assert(!cb1_trim_rgb(out,(double[3]){NAN,0,0},128,neutral));
    assert(cb1_trim_weight(150,100,200)==.5);
    assert(cb1_trim_weight(50,100,200)==0 && cb1_trim_weight(250,100,200)==1);
    assert(cb1_trim_weight(100,100,100)==0 && cb1_trim_weight(101,100,100)==1);
    cb1_trim_decode(decoded,(double[5]){1024.5,2048,2048,2048,2048});
    assert(decoded[0]==.7501220703125);
    cb1_trim_blend(out,(double[3]){1000,2000,3000},(double[3]){3000,2000,1000},3,.25);
    assert(out[0]==1500 && out[1]==2000 && out[2]==2500);
    return 0;
}
