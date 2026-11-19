// SPDX-License-Identifier: MIT
#include "cb1_lldv_cpu.h"

#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

enum { WIDTH=3840, HEIGHT=2160 };

static unsigned expected_y(float nits, unsigned bits)
{
    const double v=pow(nits/10000.0,2610.0/16384);
    const double pq=pow((3424.0/4096+2413.0/128*v)/(1+2392.0/128*v),2523.0/32);
    const unsigned step=1u<<(12-bits);
    return (unsigned)floor((256+3504*pq)/step+0.5)*step;
}

static unsigned carrier_y(uint32_t pixel, bool xrgb)
{
    const unsigned blue=(pixel>>(xrgb?0:16))&255;
    return ((pixel>>8)&255)*16+(blue&15);
}

int main(void)
{
    struct cb1_lldv_cpu *cpu=cb1_lldv_cpu_create(2);
    if(!cpu)return 77;
    const size_t stride=WIDTH*sizeof(uint32_t)+32;
    float *linear=calloc((size_t)WIDTH*HEIGHT*4,sizeof(float));
    uint32_t *carrier=aligned_alloc(32,stride*HEIGHT);
    assert(linear && carrier);

    for(int x=0;x<WIDTH;x++){
        float *sample=linear+((size_t)7*WIDTH+x)*4;
        sample[0]=sample[1]=sample[2]=0.25f;
    }
    const float half[9]={.5f,0,0,0,.5f,0,0,0,.5f};
    for(unsigned bits=10;bits<=12;bits+=2){
        for(unsigned xrgb=0;xrgb<=1;xrgb++){
            memset(carrier,0xcc,stride*HEIGHT);
            const struct cb1_lldv_cpu_frame frame={.linear=linear,.carrier=carrier,.stride=stride,
                .to_bt2020=xrgb?half:NULL,.peak_nits=2300,.bits=bits,.xrgb=xrgb,.flip_y=xrgb};
            assert(cb1_lldv_cpu_submit(cpu,&frame));
            assert(cb1_lldv_cpu_ready(cpu,true));
            const uint32_t *row=carrier+(size_t)(xrgb?HEIGHT-8:7)*stride/sizeof(*carrier);
            const unsigned y=expected_y(xrgb?287.5f:575.0f,bits);
            const unsigned step=1u<<(12-bits);
            for(unsigned x=0;x<WIDTH;x++){
                const unsigned actual=carrier_y(row[x],xrgb);
                assert(abs((int)actual-(int)y)<=(int)step);
                const unsigned red=(row[x]>>(xrgb?16:0))&255;
                assert(red==128 && (row[x]>>24)==255);
            }
            assert(row[WIDTH]==0xcccccccc);
            assert(carrier[0]==(xrgb?0xff801000u:0xff001080u));
            const uint32_t active=row[0];
            struct cb1_lldv_cpu_frame cropped=frame;
            cropped.first_row=7;
            cropped.end_row=8;
            /* A producer that proved the L5 bars need not initialize their host rows. */
            linear[0]=1;
            linear[(size_t)(HEIGHT-1)*WIDTH*4]=1;
            assert(cb1_lldv_cpu_submit(cpu,&cropped));
            assert(cb1_lldv_cpu_ready(cpu,true));
            assert(row[0]==active && row[WIDTH]==0xcccccccc);
            assert(carrier[0]==(xrgb?0xff801000u:0xff001080u));
            assert(carrier[(size_t)(HEIGHT-1)*stride/sizeof(*carrier)]==carrier[0]);
            linear[0]=linear[(size_t)(HEIGHT-1)*WIDTH*4]=0;
            cropped.end_row=HEIGHT+1;
            assert(!cb1_lldv_cpu_submit(cpu,&cropped));
        }
    }
    cb1_lldv_cpu_destroy(cpu);
    cpu=cb1_lldv_cpu_create(1);
    assert(cpu && cb1_lldv_cpu_ready(cpu,false));
    cb1_lldv_cpu_destroy(cpu);
    free(linear);
    free(carrier);
    return 0;
}
