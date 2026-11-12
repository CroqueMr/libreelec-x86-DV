/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Public player-led policy, not the proprietary Dolby content mapper. */
#include "cb1_hdr10_expert.h"
#include <libplacebo/shaders/custom.h>
#include <libavutil/dovi_meta.h>
#include <math.h>

static double nits(unsigned code)
{
    double v=pow(code/4095.0,32.0/2523);
    return 10000*pow(fmax(v-3424.0/4096,0)/(2413.0/128-(2392.0/128)*v),16384.0/2610);
}

float cb1_hdr10_expert_ceiling(const struct dvbridge_policy *policy)
{
    double v=pow(policy->tv.peak_nits/10000,2610.0/16384);
    double ceiling=pow((3424.0/4096+(2413.0/128)*v)/(1+(2392.0/128)*v),2523.0/32);
    if(policy->expert_output_bits){
        unsigned span=policy->expert_output_limited ? 219u<<(policy->expert_output_bits-8) :
            (1u<<policy->expert_output_bits)-1;
        ceiling=floor(span*ceiling)/span;
    }
    float result=ceiling;
    return result>ceiling?nextafterf(result,0):result;
}

static void player_led_trims(struct dvbridge_creative_plan *p,
                             struct dvbridge_cm4_coefficients *cm4)
{
    *cm4=(struct dvbridge_cm4_coefficients){0};
    if(!dvbridge_creative_cm4_coefficients(cm4,p))return;
    p->status=DVBRIDGE_CREATIVE_READY;
    p->backend=DVBRIDGE_CREATIVE_CM4;
    p->reason=cm4->detail_mix ? DVBRIDGE_CREATIVE_SPATIAL_UNQUALIFIED : DVBRIDGE_CREATIVE_OK;
    p->applied_levels=(p->applied_levels&~(1u<<2))|(1u<<8);
    p->l2_coverage.applied=0;
    p->l2_coverage.preserved=p->l2_coverage.present;
    /* Pointwise HDR controls: slope through saturation, mid contrast and clip. */
    p->l8_coverage.applied=p->l8_coverage.present&0xdfu;
    p->l8_coverage.preserved=p->l8_coverage.present&~p->l8_coverage.applied;
    for(unsigned i=0;i<5;i++)p->codes[i]=2048;
}

static bool prepare(struct cb1_hdr10_expert_plan *out,struct dvbridge_cm4_coefficients *cm4,
    const struct dvbridge_policy *policy,const void *metadata,size_t bytes,bool paired)
{
    if(!out || !policy || policy->mode!=DVBRIDGE_MODE_HDR10_EXPERT ||
       dvbridge_policy_validate(policy)!=DVBRIDGE_POLICY_VALID)return false;
    struct cb1_hdr10_expert_plan p={0};
    enum dvbridge_creative_status status=dvbridge_creative_resolve(&p.creative,metadata,bytes,policy);
    if(status==DVBRIDGE_CREATIVE_INVALID || status==DVBRIDGE_CREATIVE_UNSUPPORTED ||
       !dvbridge_map_color(&p.source,metadata,bytes,paired))return false;
    const AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    const AVDOVIMetadata *m=metadata;
    const AVDOVIDmData *l6=NULL;
    for(int i=0;i<m->num_ext_blocks;i++){
        const AVDOVIDmData *block=av_dovi_get_ext(m,i);
        if(block->level!=6)continue;
        if(l6 || !block->l6.max_luminance || block->l6.max_luminance>10000 ||
           block->l6.min_luminance/10000.0>=block->l6.max_luminance)return false;
        l6=block;
    }
    const AVDOVIDmData *l1=av_dovi_find_level(metadata,1);
    bool analysis=l1 && l1->l1.min_pq<=l1->l1.avg_pq &&
        l1->l1.avg_pq<=l1->l1.max_pq && l1->l1.max_pq<=4095;
    if(cm4 && p.creative.analysis_valid)analysis=true;
    else{
        p.creative.analysis[0]=analysis?l1->l1.min_pq:0;
        p.creative.analysis[1]=analysis?l1->l1.max_pq:0;
        p.creative.analysis[2]=analysis?l1->l1.avg_pq:0;
        p.creative.analysis_valid=analysis;
        if(!cm4)p.creative.l3_present=false;
    }
    unsigned maximum=analysis?p.creative.analysis[1]:color->source_max_pq;
    p.creative.l1_present=analysis;
    p.creative.applied_levels&=~((1u<<1)|(1u<<3)|(1u<<8));
    if(analysis){
        p.creative.applied_levels|=1u<<1;
        if(p.creative.l3_present &&
           (p.creative.analysis[1]!=l1->l1.max_pq || p.creative.analysis[2]!=l1->l1.avg_pq))
            p.creative.applied_levels|=1u<<3;
    }
    if(cm4)player_led_trims(&p.creative,cm4);
    for(unsigned i=0;i<3;i++)p.tone_shape[i]=(p.creative.codes[i]-2048)/2048;
    if(!analysis)p.creative.reason=l1?DVBRIDGE_CREATIVE_STATIC_UNUSABLE_L1:DVBRIDGE_CREATIVE_STATIC_MISSING_L1;
    else if(p.creative.reason==DVBRIDGE_CREATIVE_STATIC_UNUSABLE_L1 ||
            p.creative.reason==DVBRIDGE_CREATIVE_STATIC_MISSING_L1)
        p.creative.reason=!p.creative.anchor_present?DVBRIDGE_CREATIVE_NO_ANCHOR:
            p.creative.cm4?DVBRIDGE_CREATIVE_CM4_RENDER_PARTIAL:DVBRIDGE_CREATIVE_OK;
    double peak=policy->tv.peak_nits,black=policy->expert_black_nits;
    float target_pq=pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,peak);
    float black_pq=black?pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,black):0;
    p.tone=(struct pl_tone_map_params){
        .function=nits(maximum)<=peak?&pl_tone_map_clip:&pl_tone_map_st2094_10,
        .constants={PL_TONE_MAP_CONSTANTS},.input_scaling=PL_HDR_PQ,.output_scaling=PL_HDR_PQ,
        /* Both families map the same display-adapted domain. This is not
         * authored source minimum metadata. As compression vanishes, the
         * rational therefore tends to the same max(L,B) as native clip. */
        .input_min=black_pq,.input_max=fmaxf(maximum/4095.0f,target_pq),
        .input_avg=analysis?p.creative.analysis[2]/4095.0f:0,
        .output_min=black_pq,
        .output_max=target_pq,.lut_size=nits(maximum)<=peak?4096:1024};
    p.source.color.hdr.min_luma=PL_COLOR_HDR_BLACK;
    p.source.color.hdr.max_luma=l6?l6->l6.max_luminance:nits(color->source_max_pq);
    p.source.color.hdr.max_pq_y=p.source.color.hdr.avg_pq_y=0;
    p.source.color.hdr.max_cll=p.source.color.hdr.max_fall=0;
    p.source.color.hdr.prim=p.creative.mastering_primaries_present?p.creative.mastering_primaries:
        *pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020);
    enum pl_color_primaries prim=policy->tv.gamut==DVBRIDGE_GAMUT_BT709?PL_COLOR_PRIM_BT_709:
        policy->tv.gamut==DVBRIDGE_GAMUT_P3_D65?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020;
    p.target=(struct pl_color_space){.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=peak,.prim=*pl_raw_primaries_get(prim)}};
    /* Descriptor of the virtual rendering reference, not measured MaxCLL/FALL. */
    p.signal=(struct dvbridge_hdr10_metadata){.max_luminance=(unsigned)ceil(peak),
        .min_luminance=(unsigned)llround(black*10000)};
    *out=p;out->source.repr.dovi=&out->source.dovi;
    return true;
}

bool cb1_hdr10_expert_prepare(struct cb1_hdr10_expert_plan *out,
    const struct dvbridge_policy *policy,const void *metadata,size_t bytes,bool paired)
{
    return prepare(out,NULL,policy,metadata,bytes,paired);
}

bool cb1_player_led_prepare(struct cb1_hdr10_expert_plan *out,
    struct dvbridge_cm4_coefficients *cm4,const struct dvbridge_policy *policy,
    const void *metadata,size_t bytes,bool paired)
{
    if(!cm4 || !policy)return false;
    if(policy->mode!=DVBRIDGE_MODE_PLAYER_LED)
        return prepare(out,cm4,policy,metadata,bytes,paired);
    struct dvbridge_policy mapping=*policy;
    mapping.mode=DVBRIDGE_MODE_HDR10_EXPERT;
    return prepare(out,cm4,&mapping,metadata,bytes,paired);
}

bool cb1_hdr10_expert_trim(pl_shader shader,const struct dvbridge_creative_plan *plan,
                          enum pl_color_primaries primaries)
{
    if(!shader || !plan || plan->policy.mode!=DVBRIDGE_MODE_HDR10_EXPERT ||
       dvbridge_policy_validate(&plan->policy)!=DVBRIDGE_POLICY_VALID)return false;
    float chroma[2]={plan->codes[3]/4096-.5,plan->codes[4]/4096-.5};
    pl_matrix3x3 xyz=pl_get_rgb2xyz_matrix(pl_raw_primaries_get(primaries));
    float luma[3]={xyz.m[1][0],xyz.m[1][1],xyz.m[1][2]};
    float cap=plan->policy.tv.peak_nits/203;
    if((double)cap*203>plan->policy.tv.peak_nits)cap=nextafterf(cap,0);
    struct pl_shader_var vars[]={
        {.var=pl_var_vec2("expert_chroma"),.data=chroma,.dynamic=true},
        {.var=pl_var_vec3("expert_luma"),.data=luma,.dynamic=true},
        {.var=pl_var_float("expert_cap"),.data=&cap,.dynamic=true}};
    const bool chroma_active=plan->codes[4]!=2048;
    struct pl_custom_shader trim={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .variables=vars,.num_variables=3,.description="Expert target-gamut chroma and output volume",
        .prelude=chroma_active?"#define EXPERT_CHROMA\n":"",
        .body=
          "#ifdef EXPERT_CHROMA\n"
          "color.rgb=clamp(color.rgb,0.0,expert_cap);\n"
          "vec3 rgb=color.rgb;float Y=dot(rgb,expert_luma);\n"
          "if(Y>0.0){for(int c=0;c<3;c++){if(rgb[c]>0.0)"
          "color.rgb[c]*=pow((1.0+expert_chroma.x)*rgb[c]/Y,expert_chroma.y);}}\n"
          "#endif\n"
          "color.rgb=clamp(color.rgb,0.0,expert_cap);\n"};
    return pl_shader_custom(shader,&trim);
}
