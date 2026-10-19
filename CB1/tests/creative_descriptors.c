/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "task3_fixture.h"
#include "dvbridge_placebo.h"
#include "dvbridge_creative.h"
#include <string.h>
#include <math.h>
#include <stdio.h>

int main(void)
{
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.min_pq=20,.max_pq=3000,.avg_pq=1500}};
    AVDOVIDmData *l9=av_dovi_get_ext(m,1);
    *l9=(AVDOVIDmData){.level=9,.dvbridge_raw_magic=0x41424456,.dvbridge_original_length=1};
    struct dvbridge_policy p={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={800,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_P3_D65}};
    struct dvbridge_color color;struct pl_color_space target;struct dvbridge_hdr10_metadata signal;
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(color.color.primaries==PL_COLOR_PRIM_BT_2020);
    assert(!memcmp(&color.color.hdr.prim,pl_raw_primaries_get(PL_COLOR_PRIM_DISPLAY_P3),sizeof(color.color.hdr.prim)));
    l9->l9.source_primary_index=l9->dvbridge_original_bytes[0]=2;
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(!memcmp(&color.color.hdr.prim,pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),sizeof(color.color.hdr.prim)));
    l9->l9.source_primary_index=l9->dvbridge_original_bytes[0]=1;
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(!memcmp(&color.color.hdr.prim,pl_raw_primaries_get(PL_COLOR_PRIM_BT_709),sizeof(color.color.hdr.prim)));
    l9->l9.source_primary_index=l9->dvbridge_original_bytes[0]=99;
    struct dvbridge_creative_plan unknown;
    assert(dvbridge_creative_resolve(&unknown,m,bytes,&p)==DVBRIDGE_CREATIVE_UNSUPPORTED);
    assert(unknown.reason!=DVBRIDGE_CREATIVE_OK && !unknown.mastering_primaries_present);
    assert(!dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(dvbridge_map_color(&color,m,bytes,false));
    struct dvbridge_policy enhanced=p;
    enhanced.mode=DVBRIDGE_MODE_ENHANCED_DV;
    dvbridge_creative_resolve(&unknown,m,bytes,&enhanced);
    assert(unknown.reason!=DVBRIDGE_CREATIVE_MASTERING_UNSUPPORTED);
    // Custom L9 coordinates use the original signed 16-bit raw descriptor.
    *l9=(AVDOVIDmData){.level=9,.l9={.source_primary_index=255},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=17,
        .dvbridge_original_bytes={255,0x51,0xeb,0x28,0xf5,0x26,0x66,0x4c,0xcc,
                                     0x13,0x33,0x07,0xae,0x28,0x06,0x2a,0x1c}};
    l9->l9.source_display_primaries=(AVColorPrimariesDesc){
        .prim={.r={{0x51eb,32767},{0x28f5,32767}},.g={{0x2666,32767},{0x4ccc,32767}},
            .b={{0x1333,32767},{0x07ae,32767}}},.wp={{0x2806,32767},{0x2a1c,32767}}};
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(fabs(color.color.hdr.prim.red.x-0x51eb/32767.0)<1e-7);
    assert(fabs(color.color.hdr.prim.green.y-0x4ccc/32767.0)<1e-7);
    l9->l9.source_display_primaries.prim.r.x.num++;
    assert(!dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(dvbridge_map_color(&color,m,bytes,false));
    assert(dvbridge_creative_resolve(&unknown,m,bytes,&p)==DVBRIDGE_CREATIVE_INVALID);
    assert(unknown.reason==DVBRIDGE_CREATIVE_MASTERING_INCONSISTENT);
    *l9=(AVDOVIDmData){.level=9,.l9={.source_primary_index=2},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=1,.dvbridge_original_bytes={2}};
    m->num_ext_blocks=3;AVDOVIDmData *l3=av_dovi_get_ext(m,2);
    *l3=(AVDOVIDmData){.level=3,.l3={2058,2068,2078},.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=5,.dvbridge_original_bytes={0x80,0xa8,0x14,0x81,0xe0}};
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(fabs(color.color.hdr.max_pq_y-3040/4095.0)<1e-7);
    assert(fabs(color.color.hdr.avg_pq_y-1560/4095.0)<1e-7);
    /* Quantization stays within half a 12-bit PQ code. */
    assert(fabs(color.color.hdr.max_pq_y-(3000/4095.0+20/2048.0))<.5/4095);
    assert(fabs(color.color.hdr.avg_pq_y-(1500/4095.0+30/2048.0))<.5/4095);
    struct dvbridge_creative_plan decoded;
    assert(dvbridge_creative_resolve(&decoded,m,bytes,&p)==DVBRIDGE_CREATIVE_NEUTRAL);
    assert(decoded.analysis[0]==40 && decoded.analysis[1]==3040 && decoded.analysis[2]==1560);
    *l3=(AVDOVIDmData){.level=3,.l3={2048,2048,2048},.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=5,.dvbridge_original_bytes={0x80,0x08,0x00,0x80,0x00}};
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(fabs(color.color.hdr.max_pq_y-3000/4095.0)<1e-7);
    assert(fabs(color.color.hdr.avg_pq_y-1500/4095.0)<1e-7);
    *l3=(AVDOVIDmData){.level=3,.l3={2048,2028,2018},.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=5,.dvbridge_original_bytes={0x80,0x07,0xec,0x7e,0x20}};
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(fabs(color.color.hdr.max_pq_y-2960/4095.0)<1e-7);
    assert(fabs(color.color.hdr.avg_pq_y-1440/4095.0)<1e-7);
    /* Invalid near-black statistics may straddle zero through L1/L3 rounding. */
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={0,2081,1229}};
    *l3=(AVDOVIDmData){.level=3,.l3={2048,1007,1434},.dvbridge_raw_magic=0x41424456,
        .dvbridge_original_length=5,.dvbridge_original_bytes={0x80,0x03,0xef,0x59,0xa0}};
    void *black_source=av_memdup(m,bytes);assert(black_source);
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(dvbridge_creative_resolve(&decoded,m,bytes,&p)==DVBRIDGE_CREATIVE_NEUTRAL);
    assert(decoded.analysis[0]==0 && decoded.analysis[1]==0 && decoded.analysis[2]==0);
    assert(!memcmp(m,black_source,bytes));
    assert(dvbridge_creative_resolve(&unknown,m,bytes,&enhanced)==DVBRIDGE_CREATIVE_INVALID);
    av_free(black_source);
    /* Adjacent representable values inside and outside the error bound. */
    av_dovi_get_ext(m,0)->l1.max_pq=2048;l3->l3.max_pq_offset=1023;
    l3->dvbridge_original_bytes[2]=0xff;
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    av_dovi_get_ext(m,0)->l1.max_pq=2046;l3->l3.max_pq_offset=1024;
    l3->dvbridge_original_bytes[1]=0x04;l3->dvbridge_original_bytes[2]=0;
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(color.color.hdr.max_pq_y==0 && color.color.hdr.avg_pq_y==0);
    av_dovi_get_ext(m,0)->l1.max_pq=2081;l3->l3.max_pq_offset=1007;
    l3->dvbridge_original_bytes[1]=0x03;l3->dvbridge_original_bytes[2]=0xef;
    av_dovi_get_ext(m,0)->l1.min_pq=1230;l3->l3.min_pq_offset=1433;
    l3->dvbridge_original_bytes[0]=0x59;l3->dvbridge_original_bytes[1]=0x93;
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(color.color.hdr.max_pq_y==0 && color.color.hdr.avg_pq_y==0);
    av_dovi_get_ext(m,0)->l1.min_pq=0;l3->l3.min_pq_offset=2048;
    l3->dvbridge_original_bytes[0]=0x80;l3->dvbridge_original_bytes[1]=0x03;
    l3->l3.avg_pq_offset=1534;
    l3->dvbridge_original_bytes[3]=0x5f;l3->dvbridge_original_bytes[4]=0xe0;
    assert(dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    assert(color.color.hdr.max_pq_y==0 && color.color.hdr.avg_pq_y==0);
    // Retired HDR10 Enhanced is not a rendering policy.
    p.mode=(enum dvbridge_mode)5;
    assert(!dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    av_free(m);puts("PASS source mastering gamut and once-only L3 in Expert descriptors");
}
