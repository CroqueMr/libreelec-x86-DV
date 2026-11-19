/* SPDX-License-Identifier: MIT */
#include "cb1_hdr10_filter.h"
#include <libswscale/swscale_internal.h>
#include <libavutil/cpu.h>
#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static void compare(int src,int dst,int precision,const int16_t *weights,const int32_t *positions,int size)
{
    struct cb1_hdr10_filter f={0};assert(cb1_hdr10_filter_build(src,dst,precision,&f));
    for(int i=0;i<dst;++i) for(int x=0;x<src;++x){
        int a=x>=f.positions[i]&&x<f.positions[i]+f.size?f.weights[i*f.size+x-f.positions[i]]:0;
        int b=x>=positions[i]&&x<positions[i]+size?weights[i*size+x-positions[i]]:0;
        if(a!=b)fprintf(stderr,"filter %d->%d p%d row%d x%d: %d != %d\n",src,dst,precision,i,x,a,b);
        assert(a==b);
    }
    cb1_hdr10_filter_free(&f);
}
int main(void)
{
    av_force_cpu_flags(0);
    const int widths[]={256,1920,3840,4096,128,64};
    const int heights[]={144,1080,2160,2160,72,36};
    for(unsigned n=0;n<sizeof(widths)/sizeof(*widths);++n)for(int sub=0;sub<2;++sub){
        struct SwsContext *s=sws_getContext(widths[n],heights[n],sub?AV_PIX_FMT_YUV420P10LE:AV_PIX_FMT_YUV444P10LE,
            128,72,AV_PIX_FMT_RGB48LE,SWS_BILINEAR,NULL,NULL,NULL);assert(s);
        SwsInternal *c=sws_internal(s);
        compare(widths[n],128,14,c->hLumFilter,c->hLumFilterPos,c->hLumFilterSize);
        compare(c->chrSrcW,c->chrDstW,14,c->hChrFilter,c->hChrFilterPos,c->hChrFilterSize);
        compare(heights[n],72,12,c->vLumFilter,c->vLumFilterPos,c->vLumFilterSize);
        compare(c->chrSrcH,c->chrDstH,12,c->vChrFilter,c->vChrFilterPos,c->vChrFilterSize);
        sws_freeContext(s);
    }
    puts("Native analysis filters match pinned swscale");
}
