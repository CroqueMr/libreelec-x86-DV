/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <string.h>
#include "cb1_hdr10plus_dovi.h"

static void histogram_plus(void)
{
    AVDynamicHDRPlus s={.itu_t_t35_country_code=0xb5,.application_version=1,.num_windows=1};
    AVHDRPlusColorTransformParams *w=&s.params[0];
    const unsigned points[]={1,5,10,25,50,75,90,95,99};
    const unsigned values[]={10,0,255,100,500,1000,4000,7000,10000};
    w->num_distribution_maxrgb_percentiles=9;
    for(unsigned i=0;i<9;i++){
        w->distribution_maxrgb[i].percentage=points[i];
        w->distribution_maxrgb[i].percentile=(AVRational){values[i],100000};
    }
    for(unsigned i=0;i<3;i++)w->maxscl[i]=(AVRational){1,10};
    w->average_maxrgb=(AVRational){1,100};
    struct cb1_hdr10plus_dovi_result r;
    /* Independently integrated PQ trapezoids, including constant endpoint tails.
     * The v1 entries at 5/10 describe system fields, not 0/25.5-nit quantiles. */
    assert(cb1_hdr10plus_dovi_describe(&r,&s,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(r.metadata.l1_max==3079 && r.metadata.l1_avg==1738);
    assert(r.source_fields==(CB1_HDR10PLUS_DOVI_MAX|CB1_HDR10PLUS_DOVI_AVG));
    /* Sparse upper tail: keep the estimated histogram constant, do not invent
     * a ramp to MaxSCL. MaxSCL still independently describes the source peak. */
    AVDynamicHDRPlus tail=s;
    const unsigned tail_points[]={1,50,90};
    tail.params[0].num_distribution_maxrgb_percentiles=3;
    for(unsigned i=0;i<3;i++){
        tail.params[0].distribution_maxrgb[i].percentage=tail_points[i];
        tail.params[0].distribution_maxrgb[i].percentile=(AVRational){1,100};
    }
    assert(cb1_hdr10plus_dovi_describe(&r,&tail,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(r.metadata.l1_max==3079 && r.metadata.l1_avg==2081);
    /* An identical v0 legacy pattern excludes the same two reserved entries. */
    s.application_version=0;
    assert(cb1_hdr10plus_dovi_describe(&r,&s,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(r.metadata.l1_avg==1738);
    /* Sparse statistics continue without GPU analysis, with an estimated mean.
     * Do not pretend PQ(linear average) is an original Dolby mean(PQ). */
    w->num_distribution_maxrgb_percentiles=0;
    assert(cb1_hdr10plus_dovi_describe(&r,&s,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(r.metadata.l1_max==3079 && r.metadata.l1_avg==2081);
    assert(r.source_fields==CB1_HDR10PLUS_DOVI_MAX);
    assert(r.estimated_fields==(CB1_HDR10PLUS_DOVI_MIN|CB1_HDR10PLUS_DOVI_AVG));
    /* Reporter-type contradictory distribution: mean 40.6 nits, P25=3000.
     * Reject that distribution, not the valid peak/mean and the whole DV path. */
    s.application_version=1;w->num_distribution_maxrgb_percentiles=9;
    for(unsigned i=3;i<9;i++)w->distribution_maxrgb[i].percentile=(AVRational){30000+(i-3)*2000,100000};
    for(unsigned i=0;i<3;i++)w->maxscl[i]=(AVRational){2,5};
    w->average_maxrgb=(AVRational){406,100000};
    AVDynamicHDRPlus before=s;
    assert(cb1_hdr10plus_dovi_describe(&r,&s,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(r.metadata.l1_max==3696 && r.metadata.l1_avg==1723);
    assert(r.source_fields==CB1_HDR10PLUS_DOVI_MAX &&
        r.estimated_fields==(CB1_HDR10PLUS_DOVI_MIN|CB1_HDR10PLUS_DOVI_AVG));
    assert(!memcmp(&s,&before,sizeof(s)));
}

int main(void)
{
    histogram_plus();
    AVDynamicHDRPlus source={.itu_t_t35_country_code=0xb5,.application_version=1,.num_windows=1};
    source.params[0].maxscl[0]=(AVRational){1,10}; /* 1000 nits */
    source.params[0].maxscl[1]=(AVRational){1,100};
    source.params[0].maxscl[2]=(AVRational){1,1000};
    source.params[0].average_maxrgb=(AVRational){1,100};
    source.params[0].fraction_bright_pixels=(AVRational){0,1};
    source.params[0].window_upper_left_corner_x=(AVRational){0,1};
    source.params[0].window_upper_left_corner_y=(AVRational){0,1};
    source.params[0].window_lower_right_corner_x=(AVRational){1,1};
    source.params[0].window_lower_right_corner_y=(AVRational){1,1};
    source.targeted_system_display_maximum_luminance=(AVRational){4000,1};
    const struct cb1_l1l3 estimate={12,3200,1200,2048,2048,2048};
    struct cb1_hdr10plus_dovi_result result;
    AVDynamicHDRPlus before=source;
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_max==3079 && result.metadata.l1_avg==1200);
    assert(result.metadata.l1_min==12 && result.metadata.l3_max==2048);
    assert(result.source_fields==CB1_HDR10PLUS_DOVI_MAX);
    assert(result.estimated_fields==(CB1_HDR10PLUS_DOVI_MIN|CB1_HDR10PLUS_DOVI_AVG));
    assert(!memcmp(&source,&before,sizeof(source)));
    /* A linear average is not copied into average PQ; display target is not source peak. */
    source.params[0].average_maxrgb=(AVRational){1,1000};
    source.targeted_system_display_maximum_luminance=(AVRational){10000,1};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_avg==1200 && result.metadata.l1_max==3079);
    /* A low scene peak is not forced to the AI model's 100-nit lower bound. */
    for(unsigned i=0;i<3;i++)source.params[0].maxscl[i]=(AVRational){1,10000};
    source.params[0].average_maxrgb=(AVRational){1,100000};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_max==614 && result.metadata.l1_avg==614);
    assert(result.metadata.l1_min==12);
    struct cb1_l1l3 offset=estimate;offset.l3_min=2040;offset.l3_avg=2050;
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&offset)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_min==0 && result.metadata.l3_min==2048);
    /* Source curve/saturation are explicitly not translated or applied to pixels. */
    source.params[0].tone_mapping_flag=1;source.params[0].color_saturation_mapping_flag=1;
    source.params[0].knee_point_x=source.params[0].knee_point_y=(AVRational){2048,4095};
    source.params[0].num_bezier_curve_anchors=1;
    source.params[0].bezier_curve_anchors[0]=(AVRational){512,1023};
    source.params[0].color_saturation_weight=(AVRational){1,1};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.untranslated_curve && result.untranslated_saturation);
    struct cb1_hdr10plus_dovi_result saved=result;
    source.params[0].average_maxrgb=(AVRational){1,1000}; /* 10-nit mean above 1-nit peak */
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_INVALID);
    assert(!memcmp(&saved,&result,sizeof(result)));
    source.params[0].average_maxrgb=(AVRational){1,100000};
    source.params[0].maxscl[0]=(AVRational){1,3}; /* not on the 0.00001 source grid */
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_INVALID);
    source.params[0].maxscl[0]=(AVRational){1,10000};
    source.num_windows=2;
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_UNSUPPORTED);
    assert(!memcmp(&saved,&result,sizeof(result)));
    source.num_windows=1;source.params[0].maxscl[0].den=0;
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_INVALID);
    assert(!memcmp(&saved,&result,sizeof(result)));
    source.params[0].maxscl[0]=(AVRational){2,1};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_INVALID);
    source.params[0].maxscl[0]=(AVRational){0,1};
    source.params[0].maxscl[1]=source.params[0].maxscl[2]=(AVRational){0,1};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_OK);
    assert(!result.source_fields && result.estimated_fields==7);
    assert(result.metadata.l1_max==estimate.l1_max);
    /* Constant100-nit source: mean(PQ) is exactly PQ(100), independent of AI. */
    for(unsigned i=0;i<3;i++)source.params[0].maxscl[i]=(AVRational){1,100};
    source.params[0].average_maxrgb=(AVRational){1,100};
    source.params[0].num_distribution_maxrgb_percentiles=3;
    const unsigned percentages[]={1,50,99};
    for(unsigned i=0;i<3;i++){
        source.params[0].distribution_maxrgb[i].percentage=percentages[i];
        source.params[0].distribution_maxrgb[i].percentile=(AVRational){1,100};
    }
    assert(cb1_hdr10plus_dovi_describe(&result,&source,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_min==0 && result.metadata.l1_max==2081 && result.metadata.l1_avg==2081);
    assert(result.source_fields==(CB1_HDR10PLUS_DOVI_MAX|CB1_HDR10PLUS_DOVI_AVG));
    assert(result.estimated_fields==CB1_HDR10PLUS_DOVI_MIN);
    /* A contradictory histogram is not used as statistics; a valid zero mean
     * can still describe a conservative DV continuation without GPU work. */
    saved=result;
    source.params[0].average_maxrgb=(AVRational){0,1};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_avg==0 && result.metadata.l1_max==2081);
    assert(result.source_fields==CB1_HDR10PLUS_DOVI_MAX);
    source.params[0].average_maxrgb=(AVRational){1,100};
    /* Keep the actual low peak; do not apply a 100-nit CM2.9 floor. */
    /* A nonconstant distribution has a feasible mean, fitted without an AI estimate. */
    for(unsigned i=0;i<3;i++)source.params[0].maxscl[i]=(AVRational){1,10};
    source.params[0].distribution_maxrgb[0].percentile=(AVRational){1,1000};
    source.params[0].distribution_maxrgb[1].percentile=(AVRational){1,100};
    source.params[0].distribution_maxrgb[2].percentile=(AVRational){1,10};
    source.params[0].average_maxrgb=(AVRational){3,100};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_max==3079 && result.metadata.l1_avg>1538 && result.metadata.l1_avg<3079);
    for(unsigned i=0;i<3;i++){
        source.params[0].maxscl[i]=(AVRational){1,10000};
        source.params[0].distribution_maxrgb[i].percentile=(AVRational){1,10000};
    }
    source.params[0].average_maxrgb=(AVRational){1,10000};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_max==614 && result.metadata.l1_avg==614);
    /* ApplicationVersion1 reserves entries at5/10; these are not quantiles. */
    source.params[0].num_distribution_maxrgb_percentiles=5;
    const unsigned reserved_points[]={1,5,10,50,99};
    for(unsigned i=0;i<5;i++){
        source.params[0].distribution_maxrgb[i].percentage=reserved_points[i];
        source.params[0].distribution_maxrgb[i].percentile=(AVRational){1,10000};
    }
    source.params[0].distribution_maxrgb[1].percentile=(AVRational){0,1};
    source.params[0].distribution_maxrgb[2].percentile=(AVRational){255,100000};
    assert(cb1_hdr10plus_dovi_describe(&result,&source,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.metadata.l1_max==614 && result.metadata.l1_avg==614);
    /* Coded but inconsistent quantiles use a conservative metadata estimate,
     * or the supplied AI estimate, never stale histogram statistics. */
    source.params[0].distribution_maxrgb[4].percentile=(AVRational){1,10};
    saved=result;
    assert(cb1_hdr10plus_dovi_describe(&result,&source,NULL)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.source_fields==CB1_HDR10PLUS_DOVI_MAX && result.metadata.l1_avg==614);
    assert(cb1_hdr10plus_dovi_describe(&result,&source,&estimate)==CB1_HDR10PLUS_DOVI_OK);
    assert(result.source_fields==CB1_HDR10PLUS_DOVI_MAX);
    source.params[0].distribution_maxrgb[4].percentile=(AVRational){1,10000};
    before=source;
    assert(cb1_hdr10plus_dovi_same_scene(&source,&before));
    before.itu_t_t35_country_code=0;
    assert(!cb1_hdr10plus_dovi_same_scene(&source,&before));
    saved=result;
    source.params[0].distribution_maxrgb[1].percentage=1;
    assert(cb1_hdr10plus_dovi_describe(&result,&source,NULL)==CB1_HDR10PLUS_DOVI_INVALID);
    assert(!memcmp(&saved,&result,sizeof(result)));
    return 0;
}
