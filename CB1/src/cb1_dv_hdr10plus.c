/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_dv_hdr10plus.h"
#include "dvbridge_creative.h"
#include <libplacebo/tone_mapping.h>
#include <math.h>
#include <string.h>

static double pq(double nits)
{
    double x=pow(fmax(0,nits)/10000,2610.0/16384);
    return pow((3424.0/4096+2413.0/128*x)/(1+2392.0/128*x),2523.0/32);
}
static double nits(unsigned code)
{
    double x=pow(code/4095.0,32.0/2523);
    return 10000*pow(fmax(0,x-3424.0/4096)/(2413.0/128-2392.0/128*x),16384.0/2610);
}

struct response {
    struct pl_tone_map_params tone;
    struct dvbridge_creative_plan plan;
    struct dvbridge_cm4_coefficients cm4;
    enum cb1_dv_hdr10plus_coverage family;
};

static bool sample_rgb(const struct response *r,const double in[3],double out[3])
{
    double maximum=fmax(in[0],fmax(in[1],in[2]));
    double mapped=maximum>0?pl_tone_map_sample((float)maximum,&r->tone):0;
    /* Bound the float PQ-to-nits round trip to the declared curve range. */
    mapped=fmax(r->tone.output_min,fmin(r->tone.output_max,mapped));
    double rgb[3];for(unsigned i=0;i<3;i++)rgb[i]=maximum>0?in[i]*mapped/maximum:0;
    if(r->family==CB1_DV_HDR10PLUS_L8)return dvbridge_creative_cm4_apply(&r->cm4,rgb,out);
    if(r->family==CB1_DV_HDR10PLUS_L2)return dvbridge_creative_trim_rgb(&r->plan,rgb,out);
    memcpy(out,rgb,sizeof(rgb));return true;
}

static bool quantized_response(struct cb1_hdr10plus_curve *curve,double *color_error,
    const struct response *r,double source_peak,unsigned target)
{
    double values[CB1_HDR10PLUS_CURVE_SAMPLES];
    for(unsigned i=0;i<CB1_HDR10PLUS_CURVE_SAMPLES;i++){
        double n=source_peak*i/1024.0,out[3];
        if(!sample_rgb(r,(double[3]){n,n,n},out))return false;
        values[i]=out[0]/target;
    }
    if(!cb1_hdr10plus_curve_fit(curve,values,target))return false;
    double worst=0;
    /* Gray-only fits cannot prove that channel-wise trims survive a maxRGB
     * curve. Check colored probes throughout the source range as well. */
    for(unsigned a=0;a<5;a++)for(unsigned b=0;b<5;b++)for(unsigned c=0;c<5;c++){
        if(a!=4 && b!=4 && c!=4)continue;
        for(unsigned i=1;i<=32;i++){
            double x=i/32.0;x*=x;
            double ratios[3]={a/4.0,b/4.0,c/4.0},rgb[3],expected[3];
            for(unsigned j=0;j<3;j++)rgb[j]=source_peak*x*ratios[j];
            if(!sample_rgb(r,rgb,expected))return false;
            double output=cb1_hdr10plus_curve_sample(curve,x)*target;
            for(unsigned j=0;j<3;j++){
                if(!isfinite(expected[j]) || expected[j]<0 || expected[j]>target)return false;
                worst=fmax(worst,fabs(pq(output*ratios[j])-pq(expected[j])));
            }
        }
    }
    *color_error=worst;return worst<=2.0/1023;
}

bool cb1_dv_hdr10plus_metadata(AVDynamicHDRPlus *out,struct cb1_dv_hdr10plus_report *report,
    const void *metadata,size_t bytes,const struct cb1_hdr10plus_statistics *statistics)
{
    return cb1_dv_hdr10plus_metadata_for_version(out,report,metadata,bytes,statistics,1);
}

bool cb1_dv_hdr10plus_metadata_for_version(AVDynamicHDRPlus *out,
    struct cb1_dv_hdr10plus_report *report,const void *metadata,size_t bytes,
    const struct cb1_hdr10plus_statistics *statistics,unsigned version)
{
    if(!out || !report)return false;
    const unsigned target=992;
    AVDynamicHDRPlus m;
    if(!cb1_hdr10plus_describe_for_version(&m,statistics,target,version))return false;
    const struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={target,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct response r={0};
    enum dvbridge_creative_status status=dvbridge_creative_resolve(&r.plan,metadata,bytes,&policy);
    if(status==DVBRIDGE_CREATIVE_INVALID)return false;
    struct cb1_dv_hdr10plus_report result={.reason=CB1_DV_HDR10PLUS_NO_ANALYSIS};
    memcpy(result.effective_l1,r.plan.analysis,sizeof(result.effective_l1));
    if(!r.plan.l1_present || !r.plan.analysis[1])goto done;
    /* VSIF does not carry MaxSCL. Its top distribution entry supplies the
     * normalization visible to the HDMI receiver. Do not fit against a
     * different, untransmitted peak. */
    double source_peak=av_q2d(m.params[0].distribution_maxrgb[8].percentile)*10000;
    if(source_peak<=0)goto done;
    double scene_peak=fmax(source_peak,nits(r.plan.analysis[1]));
    r.tone=(struct pl_tone_map_params){.function=&pl_tone_map_spline,
        .constants={PL_TONE_MAP_CONSTANTS},.input_scaling=PL_HDR_NITS,.output_scaling=PL_HDR_NITS,
        .input_min=0,.input_max=(float)scene_peak,
        .input_avg=(float)fmin(scene_peak,nits(r.plan.analysis[2])),
        .output_min=0,.output_max=(float)fmin(scene_peak,target)};
    r.family=CB1_DV_HDR10PLUS_L1;
    result.reason=CB1_DV_HDR10PLUS_OK;
    bool rejected_trim=false;
    if(dvbridge_creative_cm4_coefficients(&r.cm4,&r.plan)){
        rejected_trim=r.cm4.chroma_base!=1 || r.cm4.saturation_gain!=1 || r.cm4.detail_mix!=0 ||
            (r.cm4.present&((1u<<8)|(1u<<9)));
        if(!rejected_trim)r.family=CB1_DV_HDR10PLUS_L8;
    }else if(r.plan.anchor_present){
        rejected_trim=r.plan.codes[3]!=2048 || r.plan.codes[4]!=2048 ||
            r.plan.reason==DVBRIDGE_CREATIVE_SPATIAL_UNQUALIFIED;
        if(!rejected_trim)r.family=CB1_DV_HDR10PLUS_L2;
    }else if(r.plan.cm4 && r.plan.cm4_targets!=DVBRIDGE_CM4_NO_CONTROLS){
        result.reason=CB1_DV_HDR10PLUS_UNRESOLVED_TRIMS;
    }
    struct cb1_hdr10plus_curve curve;
    bool fitted=!rejected_trim && quantized_response(&curve,&result.maximum_color_pq_error,&r,source_peak,target);
    if(rejected_trim || (!fitted && r.family>CB1_DV_HDR10PLUS_L1)){
        result.reason=CB1_DV_HDR10PLUS_UNREPRESENTABLE_TRIMS;
        r.family=CB1_DV_HDR10PLUS_L1;
        fitted=quantized_response(&curve,&result.maximum_color_pq_error,&r,source_peak,target);
    }
    if(fitted){
        if(!cb1_hdr10plus_curve_apply(&m,&curve))return false;
        result.coverage=r.family;result.l3_used=r.plan.l3_present;
        result.maximum_curve_pq_error=curve.maximum_pq_error;
    }else if(result.reason==CB1_DV_HDR10PLUS_OK){
        result.reason=CB1_DV_HDR10PLUS_UNREPRESENTABLE_CURVE;
    }
done:
    *out=m;*report=result;return true;
}
