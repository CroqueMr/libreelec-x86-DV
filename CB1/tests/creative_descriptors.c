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
    assert(fabs(color.color.hdr.max_pq_y-3020/4095.0)<1e-7);
    assert(fabs(color.color.hdr.avg_pq_y-1530/4095.0)<1e-7);
    // Retired HDR10 Enhanced is not a rendering policy.
    p.mode=(enum dvbridge_mode)5;
    assert(!dvbridge_reference_map(&color,&target,&signal,&p,m,bytes,false));
    av_free(m);puts("PASS source mastering gamut and once-only L3 in Expert descriptors");
}
