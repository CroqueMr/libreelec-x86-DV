/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Replacement kernels and retained original engine integration:
 * docs/GPL2-MIGRATION.md. Historical sources remain attributed. */
/* Reconstruct video at full precision, then pack the HDMI transport with frame-matched metadata. */
#include "dvbridge_render.h"
#include "cb1_hdr10plus_analysis.h"
#include <dlfcn.h>
#include "dvbridge_placebo.h"
#include "dvbridge_metadata.h"
#include "dvbridge_gl_pack.h"
#include "dvbridge_pack_sources.h"
#include "cb1_hdr10_ai.h"
#include "cb1_hdr10_ingress.h"
#include "cb1_dv_enhanced.h"
#include "cb1_trim_math.h"
#include "cb1_trim_glsl.h"
#include "cb1_transport_glsl.h"
#include "cb1_master_ipt.h"
#include "cb1_master_ipt_shader.h"
#include "cb1_composite_glsl.h"
#include "cb1_dv_enhanced_shader.h"
#define CB1_DVE_GPU 1
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#ifndef CM29_GPU_MAP_GRID
#define CM29_GPU_MAP_GRID 160
#endif
#if CM29_GPU_MAP_GRID != 160
#error "CM2.9 HDR10 mapping requires the qualified 160-point grid"
#endif
#define CM29_STR_INNER(v) #v
#define CM29_STR(v) CM29_STR_INNER(v)
#include <libplacebo/shaders/custom.h>
#include <libplacebo/shaders/colorspace.h>
#include <libplacebo/shaders/sampling.h>
#include <libplacebo/filters.h>
#include <libplacebo/dispatch.h>
#include <libplacebo/opengl.h>
#include <GLES3/gl31.h>
#include <GLES2/gl2ext.h>
#include <EGL/egl.h>
#include <math.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

struct dvbridge_dv_slot {
    bool active, retiring, ready, quarantined;
    bool borrowed_storage, ordered_handoff;
    GLsync fence;
    PFNGLCLIENTWAITSYNCPROC wait_sync;
    PFNGLDELETESYNCPROC delete_sync;
    PFNGLFENCESYNCPROC fence_sync;
    struct dvbridge_gl_packer *packer;
    AVDOVIMetadata *output_metadata;
    size_t output_bytes;
    struct dvbridge_dv_policy_output output;
    double pts;
    PFNGLBUFFERSTORAGEEXTPROC buffer_storage;
    GLuint buffers[3], program, sampler;
    const uint32_t *mapped;
    void *source_metadata;
    unsigned groups;
    pl_tex packed_target;
    pl_tex ai_direct_target;
    unsigned ai_direct_framebuffer;
    bool ai_direct_flip;
    bool ai_direct_lean;
    bool prepacked;
    bool packed_flip;
    bool enhanced_pixels, enhanced_overlay, overlay_dirty, ai_source;
    struct cb1_dv_enhanced_plan enhanced_plan;
    struct dvbridge_native_overlay overlay;
};
struct dvbridge_analysis_storage {
    GLuint buffers[3],sampler;
    const uint32_t *mapped;
    size_t scratch_bytes,result_bytes;
};
struct dvbridge_retirement_owner {
    pl_gpu gpu;
    struct dvbridge_renderer *attached, *lease;
};

struct reference_resolve {
    float span, offset, maximum;
    bool called, failed;
    pl_shader scaled_shader, output_shader;
};
struct direct_output {
    pl_tex texture;
    bool flip, custom_quantize, limited, early_l5_black;
    unsigned bits;
    struct reference_resolve quantize;
    struct pl_hook hook;
};
static struct pl_hook_res reference_quantize(void *priv, const struct pl_hook_params *p);

#include "cb1_processing.h"

struct cm29_tail_cache_key {
    double chroma[2], peak_nits;
    struct pl_color_space input, output;
    struct pl_color_map_params mapper;
    pl_matrix3x3 to_xyz, to_bt2020;
    pl_tex pq_encoder;
    pl_shader_obj *gamut_state;
};

struct dvbridge_renderer {
    pl_gpu gpu;
    pl_renderer renderer;
    pl_tex rgb, ai_rgb, enhanced_rgb, enhanced_input, p5_native, native_picture;
    pl_tex ipt_pq[2];
    pl_tex cm29_tail_atlas;
    pl_tex cm29_tail_axis;
    struct cm29_tail_cache_key cm29_tail_key;
    bool cm29_tail_key_valid;
    bool expert_warp_lookup;
    struct dvbridge_context *context;
    struct dvbridge_candidate *pending;
    bool ready, direct_output, overlay_visible;
    bool p5_native_pending;
    bool packed, fragment_quad, exact_scaler_cache, optimized_dv, fast_chroma;
    bool enhanced_linear;
    unsigned enhanced_margins[4];
    bool enhanced_fast_pq, enhanced_authored, enhanced_skip_aux, enhanced_authored_curve;
    bool enhanced_prepack, ai_enhanced_fused, ai_fusion_failed;
    unsigned enhanced_program_key;
    bool ai_enhanced_prepack;
    GLuint ai_enhanced_stats_texture;
    pl_tex ai_enhanced_stats;
    GLuint ai_enhanced_native_texture;
    pl_tex ai_enhanced_native, ai_enhanced_packed;
    bool processing_optimizations;
    bool fel_nearest;
    uint32_t processing_failed_groups;
    struct cb1_processing processing;
    struct pl_color_space reconstructed_color;
    struct dvbridge_hdr10_policy_output policy_pending, policy_committed;
    bool policy_ready, policy_has_committed;
    struct dvbridge_retirement_owner *owner;
    struct dvbridge_dv_slot dv, retired_packed;
    struct dvbridge_analysis_storage analysis_storage;
    bool reuse_authored_storage;
    bool authored_p5_analytic;
    bool master_ipt_compact;
#ifdef CB1_TEST_LEGACY_ANALYSIS
    GLuint dv_analysis_program;
#endif
    GLuint enhanced_program, enhanced_texture;
    GLuint enhanced_packed_texture, enhanced_packed_fbo;
    bool enhanced_pq_lookup;
    struct dvbridge_gl_packer *dv_transport_packer;
    struct dvbridge_dv_policy_snapshot dv_committed;
    bool dv_has_committed;
    struct cb1_dv_enhanced_plan enhanced_committed;
    uint64_t enhanced_stream;
    double enhanced_pts;
    bool enhanced_has_committed;
    uint64_t resolve_serial;
    pl_shader_obj creative_state, creative_gamut_state;
    pl_shader_obj creative_detail_lut[2];
};

static void renderer_free(struct dvbridge_renderer *r);
static bool dve_requirements(pl_gpu gpu);
static double dv_ideal_pq(double nits);
static enum dvbridge_dv_policy_status dv_retire(struct dvbridge_renderer *r);
static void dv_delete_storage(GLuint buffers[3],GLuint sampler,const void *mapped);

struct reference_hook {
    float rect[4];
    float enhancement[4]; /* peak/203, brightness, chroma, scene mask */
    bool enhanced;
    pl_matrix3x3 to_xyz, to_bt2020;
    bool composed_matrix;
    pl_shader scaled_shader;
    struct reference_resolve *quantize;
    bool early_l5_black;
    bool called, failed;
    bool creative;
    bool neutral_cm29;
    bool limit_untrimmed_volume;
    struct dvbridge_creative_plan creative_plan;
    struct pl_color_space creative_source, creative_target;
    struct pl_color_space neutral_target;
    struct pl_color_map_params creative_mapper;
    struct pl_color_map_params final_mapper;
    pl_shader_obj *creative_state;
    pl_shader_obj *creative_gamut_state;
    bool cm4;
    struct dvbridge_cm4_coefficients cm4_coefficients;
    pl_shader_obj *detail_lut;
    pl_tex feature_map;
    pl_tex pq_encoder;
    bool gpu_map_eligible, gpu_map_building, gpu_map_used;
    pl_tex gpu_map_atlas;
    struct pl_color_space gpu_map_container;
    struct dvbridge_renderer *renderer;
};
#ifdef DVBRIDGE_PQ_ENCODER_TEST
static unsigned cm29_gpu_map_build_count;
#endif
static double cm29_tail_warp_phi(double x);
static void cm29_tail_warp_axis(float axis[CM29_GPU_MAP_GRID]);
static bool cm29_gpu_map_build(struct reference_hook *h,const struct pl_hook_params *p,pl_tex atlas);
static bool cm29_gpu_map_cache(struct reference_hook *h,const struct pl_hook_params *p);
static bool cm29_add_sop(pl_shader sh,const struct reference_hook *h);
static bool cm29_add_chroma(pl_shader sh,const struct reference_hook *h);

bool dvbridge_creative_cm4_shader(pl_shader sh,const struct dvbridge_cm4_coefficients *c)
{
    if(!sh || !c || !isfinite(c->peak_nits) || c->peak_nits<=0 || c->peak_nits>10000 ||
       !(c->chroma_base>0) || !(c->saturation_gain>0) || !(c->mid_exponent>0))return false;
    float sop[4]={c->sop[0],c->sop[1],c->sop[2],c->peak_nits};
    float shape[4]={c->mid_exponent,c->clip_strength,log2(c->chroma_base),log2(c->saturation_gain)};
    int secondary_active=0;
    float luma[3],forward[9],inverse[9],residual[9],centres[6],gains[6],turns[6];
    float flags[4]={c->sop[0]!=1 || c->sop[1]!=0 || c->sop[2]!=1,
        c->mid_exponent!=1,c->clip_strength!=0,c->chroma_base!=1 || c->saturation_gain!=1};
    for(int i=0;i<3;i++){
        luma[i]=c->luma[i];
        for(int j=0;j<3;j++){
            forward[j*3+i]=c->rgb_to_lms[i*3+j];inverse[j*3+i]=c->lms_to_rgb[i*3+j];
            double v=0;for(int k=0;k<3;k++)v+=c->lms_to_rgb[i*3+k]*c->rgb_to_lms[k*3+j];
            residual[j*3+i]=v-(i==j);
        }
    }
    for(int i=0;i<6;i++){
        if(!(c->secondary_gain[i]>0))return false;
        centres[i]=c->hue_centres[i];gains[i]=log(c->secondary_gain[i]);turns[i]=c->secondary_rotation[i];
        secondary_active|=c->secondary_gain[i]!=1 || turns[i]!=0;
        flags[3]=flags[3] || secondary_active;
    }
    const float *fields[]={sop,shape,luma,forward,inverse,residual,centres,gains,turns};
    const unsigned counts[]={4,4,3,9,9,9,6,6,6};
    for(unsigned i=0;i<9;i++)for(unsigned j=0;j<counts[i];j++)if(!isfinite(fields[i][j]))return false;
    if(!flags[0] && !flags[1] && !flags[2] && !flags[3])return true;
    struct pl_shader_var vars[]={
        {.var=pl_var_vec4("cm4_sop"),.data=sop,.dynamic=true},
        {.var=pl_var_vec4("cm4_shape"),.data=shape,.dynamic=true},
        {.var=pl_var_vec4("cm4_flags"),.data=flags,.dynamic=true},
        {.var=pl_var_vec3("cm4_luma"),.data=luma,.dynamic=true},
        {.var=pl_var_mat3("cm4_rgb_lms"),.data=forward,.dynamic=true},
        {.var=pl_var_mat3("cm4_lms_rgb"),.data=inverse,.dynamic=true},
        {.var=pl_var_mat3("cm4_basis_residual"),.data=residual,.dynamic=true},
        {.var=pl_var_vec3("cm4_centres_a"),.data=centres,.dynamic=true},
        {.var=pl_var_vec3("cm4_centres_b"),.data=centres+3,.dynamic=true},
        {.var=pl_var_vec3("cm4_gains_a"),.data=gains,.dynamic=true},
        {.var=pl_var_vec3("cm4_gains_b"),.data=gains+3,.dynamic=true},
        {.var=pl_var_vec3("cm4_turns_a"),.data=turns,.dynamic=true},
        {.var=pl_var_vec3("cm4_turns_b"),.data=turns+3,.dynamic=true},
        {.var=pl_var_int("cm4_secondary_active"),.data=&secondary_active,.dynamic=true}};
    const struct pl_custom_shader trim={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .variables=vars,.num_variables=14,.description="Independent CB1 CM4 linear-nits controls",
        /* Relative ST.2084 evaluation retains small chromatic differences. */
        .header="#if __VERSION__ >= 400 || (defined(GL_ES) && __VERSION__ >= 320)\n#define CB1_CM4_FMA fma\n#else\n#define CB1_CM4_FMA(a,b,c) ((a)*(b)+(c))\n#endif\n"
            "vec3 cb1_cm4_log1p(vec3 x){vec3 v=x*(vec3(1.0)-x*(vec3(0.5)-x*(vec3(1.0/3.0)-x*(vec3(0.25)-x*(vec3(0.2)-x*(vec3(1.0/6.0)-x*(vec3(1.0/7.0)-x/8.0)))))));"
            "if(all(lessThanEqual(abs(x),vec3(0.125))))return v;"
            "return mix(v,log(max(vec3(1.0)+x,vec3(1e-30))),greaterThan(abs(x),vec3(0.125)));}\n"
            "vec3 cb1_cm4_expm1(vec3 x){vec3 v=x*(vec3(1.0)+x*(vec3(0.5)+x*(vec3(1.0/6.0)+x*(vec3(1.0/24.0)+x*(vec3(1.0/120.0)+x*(vec3(1.0/720.0)+x*(vec3(1.0/5040.0)+x/40320.0)))))));"
            "if(all(lessThanEqual(abs(x),vec3(0.25))))return v;"
            "return mix(v,exp(x)-vec3(1.0),greaterThan(abs(x),vec3(0.25)));}\n"
            "vec3 cb1_cm4_pq_u(vec3 n){vec3 v=pow(max(n,0.0)/10000.0,vec3(2610.0/16384.0));"
            "return (21.0/128.0)*(vec3(1.0)-v)/CB1_CM4_FMA(vec3(2392.0/128.0),v,vec3(1.0));}\n"
            "vec3 cb1_cm4_pq(vec3 n){vec3 u=cb1_cm4_pq_u(n);return exp((2523.0/32.0)*cb1_cm4_log1p(-u));}\n"
            "vec3 cb1_cm4_ipt(vec3 rgb,out vec3 lms,out vec3 q,out vec3 u){lms=CB1_CM4_FMA(cm4_rgb_lms[2],vec3(rgb.b),CB1_CM4_FMA(cm4_rgb_lms[1],vec3(rgb.g),cm4_rgb_lms[0]*rgb.r));u=cb1_cm4_pq_u(lms);"
            "float g=exp((2523.0/32.0)*cb1_cm4_log1p(vec3(-u.g)).x);"
            "vec3 delta=g*cb1_cm4_expm1((2523.0/32.0)*cb1_cm4_log1p((vec3(u.g)-u)/(1.0-u.g)));"
            "q=vec3(g)+delta;return vec3(g+0.4*delta.r+0.2*delta.b,4.455*delta.r+0.396*delta.b,0.8056*delta.r-1.1628*delta.b);}\n"
            /* Apply the colour delta around the input, not a large neutral RGB sum. */
            "vec3 cb1_cm4_rgb(vec3 rgb,vec2 change,vec3 n,vec3 q,vec3 w){"
            "vec3 d=vec3(dot(change,vec2(0.0975689,0.205226)),dot(change,vec2(-0.113876,0.133217)),dot(change,vec2(0.0326151,-0.676887)));"
            "d+=vec3(dot(q,vec3(-4.849e-7,-6.7e-9,4.916e-7)),dot(q,vec3(2.0352e-6,-2.4116e-6,3.764e-7)),dot(q,vec3(1.033e-7,1.135e-7,-2.168e-7)));"
            "d=clamp(d,vec3(1e-30)-q,vec3(1.0)-q);"
            "vec3 dw=-(vec3(1.0)-w)*cb1_cm4_expm1((32.0/2523.0)*cb1_cm4_log1p(d/q));"
            "float a=21.0/128.0,b=2392.0/128.0;"
            "vec3 delta=n*cb1_cm4_expm1((16384.0/2610.0)*(cb1_cm4_log1p(-dw/max(vec3(a)-w,vec3(1e-30)))-cb1_cm4_log1p(b*dw/(vec3(a)+b*w))));"
            "return CB1_CM4_FMA(cm4_lms_rgb[2],vec3(delta.b),CB1_CM4_FMA(cm4_lms_rgb[1],vec3(delta.g),CB1_CM4_FMA(cm4_lms_rgb[0],vec3(delta.r),rgb+cm4_basis_residual*rgb)));}\n",
        .body="{vec3 rgb=color.rgb*203.0;float peak=cm4_sop.w;\n"
            "if(cm4_flags.x!=0.0)rgb=peak*pow(clamp(rgb/peak*cm4_sop.x+cm4_sop.y,0.0,1.0),vec3(cm4_sop.z));\n"
            "bool gray=rgb.r==rgb.g && rgb.g==rgb.b;float Y=gray?rgb.r:dot(rgb,cm4_luma);\n"
            "if(Y>0.0 && cm4_flags.y!=0.0){float x=clamp(Y/peak,0.0,1.0);"
            "float a=pow(x,cm4_shape.x),b=pow(1.0-x,cm4_shape.x),v=peak*a/(a+b);rgb=gray?vec3(v):rgb*(v/Y);}\n"
            "Y=gray?rgb.r:dot(rgb,cm4_luma);\n"
            "if(Y>0.0 && cm4_flags.z!=0.0){float x=clamp(Y/peak,0.0,1.0),t=clamp((x-0.5)/0.5,0.0,1.0);"
            "float v=peak*clamp(x+cm4_shape.y*x*t*t*(3.0-2.0*t),0.0,1.0);rgb=gray?vec3(v):rgb*(v/Y);}\n"
            "if(cm4_flags.w!=0.0 && max(rgb.r,max(rgb.g,rgb.b))-min(rgb.r,min(rgb.g,rgb.b))>1e-12){\n"
            "vec3 lms,q,u;vec3 ipt=cb1_cm4_ipt(rgb,lms,q,u);vec2 authored=ipt.yz;\n"
            "if(length(ipt.yz)>=1e-7){float z=clamp(ipt.x/cb1_cm4_pq(vec3(peak)).x,0.0,1.0);"
            "float primary_log=log(2.0)*(cm4_shape.w+cm4_shape.z*(2.0*z-1.0));float g=0.0,turn=0.0;"
            "if(cm4_secondary_active!=0){float h=atan(ipt.z,ipt.y);\n"
            "float centres[6]=float[6](cm4_centres_a.x,cm4_centres_a.y,cm4_centres_a.z,cm4_centres_b.x,cm4_centres_b.y,cm4_centres_b.z);\n"
            "float gains[6]=float[6](cm4_gains_a.x,cm4_gains_a.y,cm4_gains_a.z,cm4_gains_b.x,cm4_gains_b.y,cm4_gains_b.z);\n"
            "float turns[6]=float[6](cm4_turns_a.x,cm4_turns_a.y,cm4_turns_a.z,cm4_turns_b.x,cm4_turns_b.y,cm4_turns_b.z);\n"
            "float sum=0.0;for(int i=0;i<6;i++){float w=exp(4.0*(cos(h-centres[i])-1.0));sum+=w;g+=w*gains[i];turn+=w*turns[i];}g/=sum;turn/=sum;}\n"
            /* Evaluate the adjustment directly; subtracting rotated IPT loses dark-channel precision. */
            "float gm=cb1_cm4_expm1(vec3(primary_log+g)).x,scale=gm+1.0;"
            "float sn=scale*sin(turn),half_sin=sin(turn*0.5),cc=CB1_CM4_FMA(scale,-2.0*half_sin*half_sin,gm);"
            "vec2 change=vec2(CB1_CM4_FMA(cc,authored.x,-sn*authored.y),CB1_CM4_FMA(cc,authored.y,sn*authored.x));\n"
            "rgb=cb1_cm4_rgb(rgb,change,lms,q,u);}}color.rgb=rgb/203.0;}\n"};
    return pl_shader_custom(sh,&trim);
}

static struct pl_hook_res reference_output(void *priv, const struct pl_hook_params *p)
{
    struct reference_hook *h = priv;
    if (p->stage == PL_HOOK_SCALED) {
        /* Capture exact reconstructed/scaled black before IPT packing bias.
         * Color management must stay on this shader; otherwise fail closed. */
        h->scaled_shader = p->sh;
        if (h->quantize)
            h->quantize->scaled_shader = p->sh;
        const float zero=0;
        struct pl_shader_var black_zero={.var=pl_var_float("reference_black_zero"),.data=&zero,.dynamic=true};
        struct pl_custom_shader capture = {.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
            .header=h->enhanced ? "bool dvbridge_signal_black;\n"
                "vec3 dvbridge_reference_m2(vec3 v){vec3 v2=v*v,v4=v2*v2,v8=v4*v4,v16=v8*v8,v32=v16*v16,v64=v32*v32;"
                "return ((v64*v8)*v4)*v2*pow(v,vec3(0.84375));}\n" :
                "bool dvbridge_signal_black;\n"
                "vec3 dvbridge_reference_m2(vec3 v){return pow(v,vec3(78.84375));}\n",
            .variables=&black_zero,.num_variables=1,
            .body=p->color.transfer==PL_COLOR_TRC_PQ ?
                "vec3 z=pow(vec3(reference_black_zero),vec3(0.1593017578125));\n"
                "z=vec3(1.0)-0.1640625*(vec3(1.0)-z)/(vec3(1.0)+18.6875*z);\n"
                "dvbridge_signal_black=all(lessThanEqual(color.rgb,dvbridge_reference_m2(z)));\n" :
                "dvbridge_signal_black=all(lessThanEqual(color.rgb,vec3(0.0)));\n",
            .description="Retain exact signal black before Expert mapping"};
        h->failed = !pl_shader_custom(p->sh, &capture);
        if (h->early_l5_black) {
            float black=h->quantize->offset/h->quantize->maximum;
            struct pl_shader_var vars[]={
                {.var=pl_var_vec4("reference_early_area"),.data=h->rect,.dynamic=true},
                {.var=pl_var_float("reference_early_black"),.data=&black,.dynamic=true},
            };
            struct pl_custom_shader early_black={
                .input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
                .variables=vars,.num_variables=2,
                .description="Early exact limited/full-range L5 black return",
                .body="if(gl_FragCoord.x<reference_early_area.x || gl_FragCoord.y<reference_early_area.y || "
                     "gl_FragCoord.x>=reference_early_area.z || gl_FragCoord.y>=reference_early_area.w) "
                     "return vec4(vec3(reference_early_black),1.0);\n",
            };
            h->failed|=!pl_shader_custom(p->sh,&early_black);
        }
        if(h->creative){
            if(h->gpu_map_building){
                struct pl_custom_shader domain={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
                    .output_w=abs(p->dst_rect.x1-p->dst_rect.x0),
                    .output_h=abs(p->dst_rect.y1-p->dst_rect.y0),.body="",
                    .description="CM29 tail-atlas post-SOP input"};
                h->failed|=!pl_shader_custom(p->sh,&domain);
                return (struct pl_hook_res){.failed=h->failed,.output=PL_HOOK_SIG_COLOR,.sh=p->sh,
                    .color=h->creative_target,.repr=p->repr,.components=p->components,.rect=p->rect};
            }
            if(h->neutral_cm29){
                if(p->color.transfer==PL_COLOR_TRC_LINEAR &&
                   h->neutral_target.transfer==PL_COLOR_TRC_LINEAR){
                    struct pl_color_map_params fused=h->creative_mapper;
                    fused.cb1_neutral_cm29=true;
                    fused.cb1_neutral_cm29_peak=h->creative_plan.policy.tv.peak_nits;
                    fused.gamut_expansion=true;
                    pl_shader_color_map_ex(p->sh,&fused,pl_color_map_args(
                        .src=h->creative_source,.dst=h->neutral_target,.state=h->creative_state,
                        .prelinearized=true));
                    struct pl_custom_shader domain={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
                        .output_w=abs(p->dst_rect.x1-p->dst_rect.x0),
                        .output_h=abs(p->dst_rect.y1-p->dst_rect.y0),.body="",
                        .description="Neutral CM29 fused linear carrier domain"};
                    h->failed|=!pl_shader_custom(p->sh,&domain);
                    return (struct pl_hook_res){.failed=h->failed,.output=PL_HOOK_SIG_COLOR,.sh=p->sh,
                        .color=h->neutral_target,.repr=p->repr,.components=p->components,.rect=p->rect};
                }
            }
            if(h->cm4){
                struct pl_color_map_params native=h->creative_mapper;native.gamut_mapping=&pl_gamut_map_clip;
                if(h->feature_map)native.contrast_recovery=h->cm4_coefficients.detail_mix;
                pl_shader_color_map_ex(p->sh,&native,pl_color_map_args(
                    .src=h->creative_source,.dst=h->creative_target,.state=h->creative_state,
                    .prelinearized=p->color.transfer==PL_COLOR_TRC_LINEAR,.feature_map=h->feature_map));
                h->failed|=!dvbridge_creative_cm4_shader(p->sh,&h->cm4_coefficients);
                /* A conservative working hull enables native output clipping.
                 * It is not a source mastering descriptor or transport metadata. */
                struct pl_color_space working=h->creative_target;
                working.hdr.prim=*pl_raw_primaries_get(PL_COLOR_PRIM_ACES_AP0);
                struct pl_color_map_params gamut=h->creative_mapper;
                gamut.tone_mapping_function=&pl_tone_map_clip;gamut.metadata=PL_HDR_METADATA_HDR10;
                gamut.gamut_mapping=&pl_gamut_map_perceptual;
                pl_shader_color_map(p->sh,&gamut,working,h->creative_target,h->creative_gamut_state,true);
                struct pl_custom_shader domain={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
                    .output_w=abs(p->dst_rect.x1-p->dst_rect.x0),.output_h=abs(p->dst_rect.y1-p->dst_rect.y0),
                    .body="",.description="CM4 linear carrier domain"};
                h->failed|=!pl_shader_custom(p->sh,&domain);
                return (struct pl_hook_res){.failed=h->failed,.output=PL_HOOK_SIG_COLOR,.sh=p->sh,
                    .color=h->creative_target,.repr=p->repr,.components=p->components,.rect=p->rect};
            }else{
            if(h->gpu_map_eligible && !h->gpu_map_building){
                if(!cm29_gpu_map_cache(h,p)){
                    h->failed=true;return (struct pl_hook_res){.failed=true};
                }
                pl_shader_color_map(p->sh,&h->creative_mapper,h->creative_source,
                    h->creative_target,h->creative_state,p->color.transfer==PL_COLOR_TRC_LINEAR);
                h->failed|=!cm29_add_sop(p->sh,h);
                float peak_scale=h->creative_plan.policy.tv.peak_nits/203.0f;
                struct pl_shader_var var={.var=pl_var_float("cm29_tail_peak_scale"),
                    .data=&peak_scale,.dynamic=true};
                struct pl_shader_desc atlas={
                    .desc={.name="cm29_tail_atlas",.type=PL_DESC_SAMPLED_TEX},
                    .binding={.object=h->gpu_map_atlas,.sample_mode=PL_TEX_SAMPLE_LINEAR},
                };
                const bool warp_lookup=h->renderer->expert_warp_lookup && h->pq_encoder;
                struct pl_shader_desc descriptors[]={atlas,{
                    .desc={.name="cm29_warp_encoder",.type=PL_DESC_SAMPLED_TEX},
                    .binding={.object=h->pq_encoder,.sample_mode=PL_TEX_SAMPLE_LINEAR},
                }};
                struct pl_custom_shader lookup={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
                    .output_w=abs(p->dst_rect.x1-p->dst_rect.x0),
                    .output_h=abs(p->dst_rect.y1-p->dst_rect.y0),
                    .variables=&var,.num_variables=1,.descriptors=descriptors,.num_descriptors=warp_lookup?2:1,
                    .prelude=warp_lookup?"#define CB1_CM29_WARP_LOOKUP 1\n":"",
                    .header="vec2 cm29_tail_uv(float b,vec2 rg){vec2 tile=vec2(mod(b,8.0),floor(b/8.0));"
                            "return (tile*" CM29_STR(CM29_GPU_MAP_GRID) ".0+rg+vec2(0.5))/vec2(" CM29_STR(CM29_GPU_MAP_GRID) ".0*8.0," CM29_STR(CM29_GPU_MAP_GRID) ".0*" CM29_STR(CM29_GPU_MAP_GRID) ".0/8.0);}\n",
                    .description="Cached CM2.9 HDR10 chroma and output mapping",
                    .body="vec3 x=clamp(color.rgb/cm29_tail_peak_scale,0.0,1.0);\n"
                          "bvec3 tail_zero=lessThanEqual(x,vec3(0.0));\n"
                          "#ifdef CB1_CM29_WARP_LOOKUP\n"
                          "vec3 u=sqrt(sqrt(x));\n"
                          "vec3 pq=vec3(texture(cm29_warp_encoder,vec2((u.r*4095.0+0.5)/4096.0,0.5)).r,"
                          "texture(cm29_warp_encoder,vec2((u.g*4095.0+0.5)/4096.0,0.5)).r,"
                          "texture(cm29_warp_encoder,vec2((u.b*4095.0+0.5)/4096.0,0.5)).r);\n"
                          "#else\n"
                          "vec3 v=pow(x,vec3(2610.0/16384.0));\n"
                          "v=(vec3(3424.0/4096.0)+vec3(2413.0/128.0)*v)/(vec3(1.0)+vec3(2392.0/128.0)*v);\n"
                          "vec3 pq=clamp(pow(v,vec3(2523.0/32.0)),0.0,1.0);\n"
                          "#endif\n"
                          "vec3 q=(0.5*pq+0.5*x)*(" CM29_STR(CM29_GPU_MAP_GRID) ".0-1.0);\n"
                          "q=mix(q,vec3(0.0),tail_zero);\n"
                          "vec2 rg=q.rg;float b0=floor(q.b),b1=min(b0+1.0," CM29_STR(CM29_GPU_MAP_GRID) ".0-1.0);\n"
                          "vec3 lo=texture(cm29_tail_atlas,cm29_tail_uv(b0,rg)).rgb;\n"
                          "vec3 hi=texture(cm29_tail_atlas,cm29_tail_uv(b1,rg)).rgb;\n"
                          "color.rgb=mix(lo,hi,fract(q.b));\n"};
                h->failed|=!pl_shader_custom(p->sh,&lookup);
                if(h->failed)return (struct pl_hook_res){.failed=true};
                h->gpu_map_used=true;
                return (struct pl_hook_res){.output=PL_HOOK_SIG_COLOR,.sh=p->sh,
                    .color=h->gpu_map_container,.repr=p->repr,.components=p->components,.rect=p->rect};
            }
            pl_shader_color_map(p->sh,&h->creative_mapper,h->creative_source,
                h->creative_target,h->creative_state,p->color.transfer==PL_COLOR_TRC_LINEAR);
            h->failed|=!cm29_add_sop(p->sh,h);
            h->failed|=!cm29_add_chroma(p->sh,h);
            struct pl_custom_shader domain={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
                .output_w=abs(p->dst_rect.x1-p->dst_rect.x0),
                .output_h=abs(p->dst_rect.y1-p->dst_rect.y0),
                .body="",.description="CM2.9 linear carrier domain"};
            h->failed|=!pl_shader_custom(p->sh,&domain);
            return (struct pl_hook_res){.failed=h->failed,.output=PL_HOOK_SIG_COLOR,.sh=p->sh,
                .color=h->creative_target,.repr=p->repr,.components=p->components,.rect=p->rect};
            }
        }
        return (struct pl_hook_res){.failed=h->failed,.output=PL_HOOK_SIG_NONE};
    }
    h->called = true;
    if(p->stage==PL_HOOK_PRE_OUTPUT && h->gpu_map_used){
        if(p->color.transfer!=PL_COLOR_TRC_PQ ||
           p->color.primaries!=PL_COLOR_PRIM_BT_2020 || p->sh!=h->scaled_shader){
            h->failed=true;return (struct pl_hook_res){.failed=true};
        }
        const int keep_black=!h->creative || h->creative_plan.codes[1]<=2048;
        struct pl_shader_var vars[]={
            {.var=pl_var_vec4("reference_area"),.data=h->rect,.dynamic=true},
            {.var=pl_var_int("reference_keep_black"),.data=&keep_black,.dynamic=true},
        };
        struct pl_custom_shader mask={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
            .variables=vars,.num_variables=2,.description="Exact black and original-coordinate L5 mask after CM29 tail",
            .body="if((dvbridge_signal_black && reference_keep_black!=0) || gl_FragCoord.x<reference_area.x || "
                  "gl_FragCoord.x>=reference_area.z || gl_FragCoord.y<reference_area.y || "
                  "gl_FragCoord.y>=reference_area.w)color=vec4(0.0,0.0,0.0,1.0);\n"};
        h->failed=!pl_shader_custom(p->sh,&mask);
        return (struct pl_hook_res){.failed=h->failed,.output=PL_HOOK_SIG_NONE};
    }
    if (p->stage != PL_HOOK_PRE_OUTPUT || (!h->cm4 && p->sh != h->scaled_shader) ||
        p->color.transfer != PL_COLOR_TRC_LINEAR) {
        h->failed = true;
        return (struct pl_hook_res){.failed=true};
    }
    if(h->limit_untrimmed_volume){
        float peak=h->neutral_target.hdr.max_luma/203.0f;
        struct pl_shader_var var={.var=pl_var_float("reference_volume_peak"),.data=&peak,.dynamic=true};
        struct pl_custom_shader begin={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
            .variables=&var,.num_variables=1,.description="Limit only out-of-volume Expert colours",
            .header="vec3 reference_volume_original;bool reference_volume_outside;\n",
            .body="reference_volume_original=color.rgb;\n"
                  "reference_volume_outside=any(lessThan(color.rgb,vec3(0.0))) || "
                  "any(greaterThan(color.rgb,vec3(reference_volume_peak)));\n"};
        h->failed|=!pl_shader_custom(p->sh,&begin);
        /* Reuse CM4's native gamut limiter without reapplying scene tone mapping. */
        struct pl_color_space working=h->neutral_target;
        working.hdr.prim=*pl_raw_primaries_get(PL_COLOR_PRIM_ACES_AP0);
        struct pl_color_map_params gamut=h->final_mapper;
        gamut.tone_mapping_function=&pl_tone_map_clip;gamut.metadata=PL_HDR_METADATA_HDR10;
        pl_shader_color_map(p->sh,&gamut,working,h->neutral_target,h->creative_gamut_state,true);
        struct pl_custom_shader end={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
            .body="if(!reference_volume_outside)color.rgb=reference_volume_original;\n"};
        h->failed|=!pl_shader_custom(p->sh,&end);
    }
    if (h->enhanced) {
        struct pl_shader_var params={.var=pl_var_vec4("enhanced_policy"),.data=h->enhancement,.dynamic=true};
        struct pl_custom_shader enhance={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
            .variables=&params,.num_variables=1,.description="Selective Adaptive nominal LINEAR policy",
            .header="#define CB1_ONSET vec2(0.02,0.25)\n",
            .body=
                "vec3 ev=color.rgb/enhanced_policy.x;\n"
                "float elo=min(ev.r,min(ev.g,ev.b)),ehi=max(ev.r,max(ev.g,ev.b));\n"
                /* Common-neutral contraction, not independent channel clipping. */
                "bool projected=elo<0.0 || ehi>1.0;\n"
                "if(projected){float a=clamp((elo+ehi)*0.5,0.0,1.0);vec3 d=ev-vec3(a);\n"
                "vec3 bound=vec3(1.0);for(int i=0;i<3;i++){if(d[i]>0.0)bound[i]=(1.0-a)/d[i];else if(d[i]<0.0)bound[i]=-a/d[i];}\n"
                "float t=min(1.0,min(bound.r,min(bound.g,bound.b)));ev=vec3(a)+t*d;\n"
                "for(int i=0;i<3;i++){if(bound[i]==t && d[i]!=0.0)ev[i]=d[i]>0.0?1.0:0.0;}\n"
                "elo=min(ev.r,min(ev.g,ev.b));ehi=max(ev.r,max(ev.g,ev.b));color.rgb=ev*enhanced_policy.x;}\n"
                "if(ehi>0.01){float shadow=smoothstep(0.01,0.02,ehi),onset=smoothstep(CB1_ONSET.x,CB1_ONSET.y,ehi);\n"
                "float m=ehi+enhanced_policy.y*enhanced_policy.w*shadow*onset*ehi*(1.0-ehi);\n"
                /* Keep neutral/no-brightness-change values untouched. */
                "if(m!=ehi || elo!=ehi){ev*=m/ehi;\n"
                "float lo=min(ev.r,min(ev.g,ev.b)),hi=max(ev.r,max(ev.g,ev.b)),g=(lo+hi)*0.5,c=(hi-lo)*0.5,h=min(g,1.0-g);\n"
                "if(c>0.0 && h>0.0){float t=min(1.0,c/h);float f=min(1.0+enhanced_policy.z*shadow*enhanced_policy.w*4.0*t*(1.0-t),h/c);ev=vec3(g)+f*(ev-vec3(g));}\n"
                "color.rgb=ev*enhanced_policy.x;}}\n"};
        h->failed = h->failed || !pl_shader_custom(p->sh,&enhance);
    }
    const int keep_black=!h->creative || (h->cm4?h->cm4_coefficients.sop[1]<=0:h->creative_plan.codes[1]<=2048);
    struct pl_shader_var vars[] = {
        {.var=pl_var_mat3("reference_bt2020"),.data=&h->to_bt2020,.dynamic=true},
        {.var=pl_var_vec4("reference_area"),.data=h->rect,.dynamic=true},
        {.var=pl_var_int("reference_keep_black"),.data=&keep_black,.dynamic=true},
        {.var=pl_var_mat3("reference_xyz"),.data=&h->to_xyz,.dynamic=true},
    };
    struct pl_shader_desc encoder_desc={
        .desc={.name="reference_pq_encoder",.type=PL_DESC_SAMPLED_TEX},
        .binding={.object=h->pq_encoder,.sample_mode=PL_TEX_SAMPLE_LINEAR},
    };
    const char *conversion_body = h->pq_encoder ?
        "color.rgb=CB1_REFERENCE_TRANSFORM(color.rgb);\n"
        "bvec3 zero=lessThanEqual(color.rgb,vec3(0.0));\n"
        "vec3 linear=clamp(color.rgb*(203.0/10000.0),0.0,1.0);\n"
        "vec3 u=sqrt(sqrt(linear));\n"
        "vec3 encoded=vec3(\n"
        " texture(reference_pq_encoder,vec2((u.r*4095.0+0.5)/4096.0,0.5)).r,\n"
        " texture(reference_pq_encoder,vec2((u.g*4095.0+0.5)/4096.0,0.5)).r,\n"
        " texture(reference_pq_encoder,vec2((u.b*4095.0+0.5)/4096.0,0.5)).r);\n"
        "color.rgb=mix(encoded,vec3(0.0),zero);\n"
        "if((dvbridge_signal_black && reference_keep_black!=0) || gl_FragCoord.x<reference_area.x || gl_FragCoord.x>=reference_area.z || "
        "gl_FragCoord.y<reference_area.y || gl_FragCoord.y>=reference_area.w)color=vec4(0,0,0,1);\n" :
        "color.rgb=CB1_REFERENCE_TRANSFORM(color.rgb);\n"
        "bvec3 zero=lessThanEqual(color.rgb,vec3(0.0));\n"
        "vec3 v=pow(clamp(color.rgb*(203.0/10000.0),0.0,1.0),vec3(2610.0/16384.0));\n"
        "v=vec3(1.0)-(21.0/128.0)*(vec3(1.0)-v)/(vec3(1.0)+(2392.0/128.0)*v);\n"
        "color.rgb=mix(dvbridge_reference_m2(v),vec3(0.0),zero);\n"
        "if((dvbridge_signal_black && reference_keep_black!=0) || gl_FragCoord.x<reference_area.x || gl_FragCoord.x>=reference_area.z || "
        "gl_FragCoord.y<reference_area.y || gl_FragCoord.y>=reference_area.w)color=vec4(0,0,0,1);\n";
    struct pl_custom_shader conversion = {.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .variables=vars,.num_variables=h->composed_matrix?3:4,
        .header=h->neutral_cm29 && h->composed_matrix ? "#define CB1_REFERENCE_TRANSFORM(v) (v)\n" :
            h->composed_matrix ? "#define CB1_REFERENCE_TRANSFORM(v) (reference_bt2020*(v))\n" :
            "#define CB1_REFERENCE_TRANSFORM(v) (reference_bt2020*(reference_xyz*(v)))\n",
        .description="Expert nominal LINEAR to BT2020 PQ before caller overlays",
        .body=conversion_body,.descriptors=h->pq_encoder?&encoder_desc:NULL,
        .num_descriptors=h->pq_encoder?1:0};
    h->failed = h->failed || !pl_shader_custom(p->sh, &conversion);
    return (struct pl_hook_res){.failed=h->failed,.output=PL_HOOK_SIG_NONE};
}

static pl_tex detail_texture(const struct pl_hook_params *p,int w,int h)
{
    pl_tex tex=p->get_tex(p->priv,w,h);
    if(!tex || tex->params.format->type!=PL_FMT_FLOAT)return NULL;
    for(int c=0;c<tex->params.format->num_components;c++)
        if(tex->params.format->component_depth[c]!=32)return NULL;
    return tex;
}

static bool cm29_add_sop(pl_shader sh,const struct reference_hook *h)
{
    double controls[5];cb1_trim_decode(controls,h->creative_plan.codes);
    float sop[4]={controls[0],controls[1],controls[2],
        h->creative_plan.policy.tv.peak_nits/203};
    struct pl_shader_var var={.var=pl_var_vec4("creative_sop"),.data=sop,.dynamic=true};
    struct pl_custom_shader shader={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .variables=&var,.num_variables=1,.description="Original CM2.9 SOP before tail lookup",
        .body=h->creative_plan.codes[0]==2048 && h->creative_plan.codes[1]==2048 &&
            h->creative_plan.codes[2]==2048 ?
            "color.rgb=clamp(color.rgb,0.0,creative_sop.w);\n" : CB1_TRIM_SOP_GLSL};
    if(!pl_shader_custom(sh,&shader))return false;
    return true;
}

static bool cm29_add_chroma(pl_shader sh,const struct reference_hook *h)
{
    if(h->creative_plan.codes[4]==2048)return true;
    double controls[5];cb1_trim_decode(controls,h->creative_plan.codes);
    float cg[2]={controls[3],controls[4]};
    struct pl_shader_var var={.var=pl_var_vec2("creative_color"),.data=cg,.dynamic=true};
    struct pl_custom_shader shader={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .variables=&var,.num_variables=1,.description="Original CM2.9 chroma controls",
        .body=CB1_TRIM_CHROMA_GLSL};
    return pl_shader_custom(sh,&shader);
}

static void cm29_gpu_map_make_key(struct cm29_tail_cache_key *key,const struct reference_hook *h)
{
    memset(key,0,sizeof(*key));
    key->chroma[0]=h->creative_plan.codes[3];
    key->chroma[1]=h->creative_plan.codes[4];
    key->peak_nits=h->creative_plan.policy.tv.peak_nits;
    memcpy(&key->input,&h->creative_target,sizeof(key->input));
    memcpy(&key->output,&h->neutral_target,sizeof(key->output));
    memcpy(&key->mapper,&h->final_mapper,sizeof(key->mapper));
    memcpy(&key->to_xyz,&h->to_xyz,sizeof(key->to_xyz));
    memcpy(&key->to_bt2020,&h->to_bt2020,sizeof(key->to_bt2020));
    key->pq_encoder=h->pq_encoder;
    key->gamut_state=h->creative_gamut_state;
}

static bool cm29_gpu_map_key_equal(const struct cm29_tail_cache_key *a,
                                   const struct cm29_tail_cache_key *b)
{
    /* Compare colorspaces semantically; retain exact cache checks elsewhere. */
    return !memcmp(a->chroma,b->chroma,sizeof(a->chroma)) &&
        a->peak_nits==b->peak_nits &&
        pl_color_space_equal(&a->input,&b->input) &&
        pl_color_space_equal(&a->output,&b->output) &&
        !memcmp(&a->mapper,&b->mapper,sizeof(a->mapper)) &&
        !memcmp(&a->to_xyz,&b->to_xyz,sizeof(a->to_xyz)) &&
        !memcmp(&a->to_bt2020,&b->to_bt2020,sizeof(a->to_bt2020)) &&
        a->pq_encoder==b->pq_encoder && a->gamut_state==b->gamut_state;
}

static double cm29_tail_warp_phi(double x)
{
    const double m1=2610.0/16384.0,m2=2523.0/32.0;
    const double c1=3424.0/4096.0,c2=2413.0/128.0,c3=2392.0/128.0;
    double p=pow(x,m1);
    double pq=pow((c1+c2*p)/(1.0+c3*p),m2);
    return 0.5*pq+0.5*x;
}

static void cm29_tail_warp_axis(float axis[CM29_GPU_MAP_GRID])
{
    for(int i=0;i<CM29_GPU_MAP_GRID;i++){
        double target=(double)i/(CM29_GPU_MAP_GRID-1),lo=0.0,hi=1.0;
        if(i==0){axis[i]=0.0f;continue;}
        if(i==CM29_GPU_MAP_GRID-1){axis[i]=1.0f;continue;}
        for(int j=0;j<64;j++){
            double mid=0.5*(lo+hi);
            if(cm29_tail_warp_phi(mid)<target)lo=mid;else hi=mid;
        }
        axis[i]=(float)(0.5*(lo+hi));
    }
}

static bool cm29_gpu_map_cache(struct reference_hook *h,const struct pl_hook_params *p)
{
    struct dvbridge_renderer *r=h->renderer;
    if(!r)return false;
    /* This table contains only CM2.9 chroma plus final mapping/PQ. The authored
     * first map and SOP remain per-frame work on the reconstructed raster. */
    struct cm29_tail_cache_key key;
    cm29_gpu_map_make_key(&key,h);
    if(r->cm29_tail_key_valid && r->cm29_tail_atlas && r->cm29_tail_axis &&
       cm29_gpu_map_key_equal(&r->cm29_tail_key,&key)){
        h->gpu_map_atlas=r->cm29_tail_atlas;
        return true;
    }

    /* A failed replacement must never leave the previous atlas valid for this key. */
    r->cm29_tail_key_valid=false;
    const int n=CM29_GPU_MAP_GRID,w=8*n,height=n*n/8;
    if(!r->cm29_tail_atlas){
        const int caps=PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_LINEAR;
        /* The atlas stores bounded PQ, not scene-linear HDR values. */
        pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_UNORM,4,16,16,caps);
        if(!fmt)return false;
        r->cm29_tail_atlas=pl_tex_create(r->gpu,pl_tex_params(.w=w,.h=height,
            .format=fmt,.sampleable=true,.renderable=true));
        if(!r->cm29_tail_atlas)return false;
    }
    if(!cm29_gpu_map_build(h,p,r->cm29_tail_atlas))return false;
    r->cm29_tail_key=key;
    r->cm29_tail_key_valid=true;
    h->gpu_map_atlas=r->cm29_tail_atlas;
    return true;
}

static bool cm29_gpu_map_build(struct reference_hook *h,const struct pl_hook_params *p,pl_tex atlas)
{
    const int n=CM29_GPU_MAP_GRID,w=8*n,height=n*n/8;
    struct dvbridge_renderer *r=h->renderer;
    if(!atlas || atlas->params.w!=w || atlas->params.h!=height ||
       !atlas->params.sampleable || !atlas->params.renderable ||
       (atlas->params.format->caps&(PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_LINEAR))!=
           (PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_LINEAR))return false;
    if(!r)return false;
    if(!r->cm29_tail_axis){
        float axis[CM29_GPU_MAP_GRID];
        cm29_tail_warp_axis(axis);
        pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_FLOAT,1,32,32,
                               PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR);
        if(!fmt)return false;
        r->cm29_tail_axis=pl_tex_create(r->gpu,pl_tex_params(.w=n,.h=1,.format=fmt,
            .sampleable=true,.initial_data=axis));
        if(!r->cm29_tail_axis)return false;
    }
    pl_shader sh=pl_dispatch_begin(p->dispatch);
    if(!sh)return false;
    float peak_scale=h->creative_plan.policy.tv.peak_nits/203.0f;
    struct pl_shader_var peak={.var=pl_var_float("tail_peak_scale"),.data=&peak_scale,.dynamic=true};
    struct pl_shader_desc axis={
        .desc={.name="cm29_tail_axis",.type=PL_DESC_SAMPLED_TEX},
        .binding={.object=r->cm29_tail_axis,.sample_mode=PL_TEX_SAMPLE_NEAREST},
    };
    struct pl_custom_shader grid={.input=PL_SHADER_SIG_NONE,.output=PL_SHADER_SIG_COLOR,
        .variables=&peak,.num_variables=1,.descriptors=&axis,.num_descriptors=1,
        .description="Peak-normalized phi-warped CM29 lattice",
        .body="vec2 xy=floor(gl_FragCoord.xy);float tx=floor(xy.x/" CM29_STR(CM29_GPU_MAP_GRID) ".0);"
              "float ty=floor(xy.y/" CM29_STR(CM29_GPU_MAP_GRID) ".0);\n"
              "vec3 i=vec3(mod(xy," CM29_STR(CM29_GPU_MAP_GRID) ".0),ty*8.0+tx);\n"
              "vec3 x=vec3(texture(cm29_tail_axis,vec2((i.x+0.5)/" CM29_STR(CM29_GPU_MAP_GRID) ".0,0.5)).r,"
              "texture(cm29_tail_axis,vec2((i.y+0.5)/" CM29_STR(CM29_GPU_MAP_GRID) ".0,0.5)).r,"
              "texture(cm29_tail_axis,vec2((i.z+0.5)/" CM29_STR(CM29_GPU_MAP_GRID) ".0,0.5)).r);\n"
              "color=vec4(x*tail_peak_scale,1.0);\n"};
    if(!pl_shader_custom(sh,&grid))goto abort;
    struct reference_hook clone=*h;
    clone.gpu_map_building=true;clone.gpu_map_used=false;clone.gpu_map_atlas=atlas;
    clone.failed=false;clone.called=false;clone.quantize=NULL;clone.early_l5_black=false;
    clone.rect[0]=clone.rect[1]=0;clone.rect[2]=w;clone.rect[3]=height;
    struct pl_hook_params synthetic=*p;
    synthetic.stage=PL_HOOK_SCALED;synthetic.sh=sh;synthetic.tex=NULL;
    synthetic.color=clone.creative_target;synthetic.repr=pl_color_repr_rgb;synthetic.components=3;
    synthetic.rect=(pl_rect2df){0,0,w,height};synthetic.dst_rect=(pl_rect2d){0,0,w,height};
    struct pl_hook_res result=reference_output(&clone,&synthetic);
    if(result.failed || clone.failed || !cm29_add_chroma(sh,&clone))goto abort;
    struct pl_color_map_params tail=clone.final_mapper;
    tail.gamut_expansion=true;tail.tone_mapping_function=&pl_tone_map_clip;
    tail.metadata=PL_HDR_METADATA_HDR10;
    pl_shader_color_map(sh,&tail,clone.creative_target,clone.neutral_target,
                        clone.creative_gamut_state,true);
    synthetic.stage=PL_HOOK_PRE_OUTPUT;synthetic.color=clone.neutral_target;
    result=reference_output(&clone,&synthetic);
    if(result.failed || clone.failed || !pl_dispatch_finish(p->dispatch,
            pl_dispatch_params(.shader=&sh,.target=atlas)))goto abort;
#ifdef DVBRIDGE_PQ_ENCODER_TEST
    cm29_gpu_map_build_count++;
#endif
    return true;
abort:
    pl_dispatch_abort(p->dispatch,&sh);
    return false;
}

/* Native intensity and bicubic reduction, with L5 excluded before filtering. */
static pl_tex cm4_features(struct reference_hook *h,const struct pl_hook_params *p)
{
    int w=abs(p->dst_rect.x1-p->dst_rect.x0),height=abs(p->dst_rect.y1-p->dst_rect.y0);
    if(w<=0 || height<=0 || p->rect.x1<=p->rect.x0 || p->rect.y1<=p->rect.y0)return NULL;
    float sx=(p->rect.x1-p->rect.x0)/w,sy=(p->rect.y1-p->rect.y0)/height;
    pl_rect2df active={p->rect.x0+(h->rect[0]-p->dst_rect.x0)*sx,
        p->rect.y0+(h->rect[1]-p->dst_rect.y0)*sy,
        p->rect.x0+(h->rect[2]-p->dst_rect.x0)*sx,
        p->rect.y0+(h->rect[3]-p->dst_rect.y0)*sy};
    if(active.x0<p->rect.x0 || active.y0<p->rect.y0 || active.x1>p->rect.x1 ||
       active.y1>p->rect.y1 || active.x1<=active.x0 || active.y1<=active.y0)return NULL;
    /* Match the final mask's pixel-centre inclusion after scaling L5. */
    active.x0=ceilf(active.x0-.5f);active.y0=ceilf(active.y0-.5f);
    active.x1=ceilf(active.x1-.5f);active.y1=ceilf(active.y1-.5f);
    if(active.x1<=active.x0 || active.y1<=active.y0)return NULL;
    int aw=ceilf(active.x1-active.x0),ah=ceilf(active.y1-active.y0);
    int low_w=ceilf(w/3.5f),low_h=ceilf(height/3.5f);
    pl_tex full=detail_texture(p,aw,ah),vertical=detail_texture(p,w,low_h),low=detail_texture(p,low_w,low_h);
    if(!full || !vertical || !low)return NULL;
    pl_shader sh=pl_dispatch_begin(p->dispatch);
    struct pl_sample_src crop={.tex=p->tex,.rect=active,.new_w=aw,.new_h=ah};
    bool aligned=active.x0==floorf(active.x0) && active.y0==floorf(active.y0) &&
        active.x1==floorf(active.x1) && active.y1==floorf(active.y1);
    if(!(aligned?pl_shader_sample_nearest(sh,&crop):pl_shader_sample_direct(sh,&crop)))goto error;
    struct pl_color_space csp=h->creative_source;csp.transfer=p->color.transfer;
    pl_shader_extract_features(sh,csp);
    if(!pl_dispatch_finish(p->dispatch,pl_dispatch_params(.shader=&sh,.target=full)))goto error;
    float left=(active.x0-p->rect.x0)/sx,top=(active.y0-p->rect.y0)/sy;
    for(int axis=0;axis<2;axis++){
        sh=pl_dispatch_begin(p->dispatch);
        pl_tex input=axis?vertical:full,output=axis?low:vertical;
        struct pl_sample_src src={.tex=input,.components=1,.address_mode=PL_TEX_ADDRESS_MIRROR,
            .rect=axis?(pl_rect2df){0,0,w,low_h}:(pl_rect2df){-left,-top,w-left,height-top},
            .new_w=output->params.w,.new_h=output->params.h};
        struct pl_sample_filter_params filter={.filter=pl_filter_bicubic,
            .lut=&h->detail_lut[axis],.no_compute=true,.cb1_fp32_lut=true};
        if(!pl_shader_sample_ortho2(sh,&src,&filter) ||
           !pl_dispatch_finish(p->dispatch,pl_dispatch_params(.shader=&sh,.target=output)))goto error;
    }
    return low;
error:
    pl_dispatch_abort(p->dispatch,&sh);return NULL;
}

static struct pl_hook_res cm4_spatial_output(void *priv,const struct pl_hook_params *p)
{
    struct reference_hook *h=priv;
    if(p->stage!=PL_HOOK_SCALED || !p->tex || p->components<3 ||
       p->color.primaries!=h->creative_source.primaries ||
       (p->color.transfer!=PL_COLOR_TRC_LINEAR && p->color.transfer!=PL_COLOR_TRC_PQ))goto error;
    h->feature_map=cm4_features(h,p);
    if(!h->feature_map)goto error;
    pl_shader sh=pl_dispatch_begin(p->dispatch);
    struct pl_sample_src src={.tex=p->tex,.rect=p->rect,
        .new_w=abs(p->dst_rect.x1-p->dst_rect.x0),.new_h=abs(p->dst_rect.y1-p->dst_rect.y0)};
    bool identity=p->rect.x0==floorf(p->rect.x0) && p->rect.y0==floorf(p->rect.y0) &&
        p->rect.x1-p->rect.x0==src.new_w && p->rect.y1-p->rect.y0==src.new_h;
    if(!(identity?pl_shader_sample_nearest(sh,&src):pl_shader_sample_direct(sh,&src))){
        pl_dispatch_abort(p->dispatch,&sh);goto error;
    }
    struct pl_hook_params color=*p;color.sh=sh;
    struct pl_hook_res result=reference_output(priv,&color);
    if(result.failed)pl_dispatch_abort(p->dispatch,&sh);
    return result;
error:
    h->failed=true;return (struct pl_hook_res){.failed=true};
}

static bool reference_area(float rect[4], const void *metadata,
                           struct dvbridge_geometry g)
{
    if (g.source_width<=0 || g.source_width>3840 || g.source_height<=0 || g.source_height>2160 ||
        g.x<0 || g.x>3840 || g.y<0 || g.y>2160 || g.width<=0 || g.width>3840-g.x ||
        g.height<=0 || g.height>2160-g.y) return false;
    unsigned l=0,r=0,t=0,b=0,count=0;
    const AVDOVIMetadata *m=metadata;
    for (int i=0;i<m->num_ext_blocks;i++) {
        const AVDOVIDmData *e=av_dovi_get_ext(m,i);
        if (e->level!=5) continue;
        if (++count>1) return false;
        l=e->l5.left_offset;r=e->l5.right_offset;t=e->l5.top_offset;b=e->l5.bottom_offset;
    }
    if (l>=(unsigned)g.source_width || r>=(unsigned)g.source_width-l ||
        t>=(unsigned)g.source_height || b>=(unsigned)g.source_height-t) return false;
    double sx=(double)g.width/g.source_width,sy=(double)g.height/g.source_height;
    rect[0]=g.x+l*sx;rect[1]=g.y+t*sy;
    rect[2]=g.x+g.width-r*sx;rect[3]=g.y+g.height-b*sy;
    return true;
}

/* Allocate full-size RGB backing only for an actual consumer. */
static bool ensure_rgb(struct dvbridge_renderer *r)
{
    if(r->rgb)return true;
    pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,32,32,
        PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);
    if(fmt)r->rgb=pl_tex_create(r->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,
        .sampleable=true,.renderable=true,.blit_dst=true));
    return r->rgb!=NULL;
}

static bool p5_preserve_backing(struct dvbridge_renderer *r)
{
    if(!r->p5_native_pending)return true;
    if(!ensure_rgb(r))return false;
    pl_rect3d rect={.x1=r->p5_native->params.w,.y1=r->p5_native->params.h};
    pl_tex_blit(r->gpu,pl_tex_blit_params(.src=r->p5_native,.dst=r->rgb,.src_rc=rect,.dst_rc=rect));
    r->p5_native_pending=false;
    return true;
}

struct active_mask {
    struct dvbridge_renderer *ai_renderer;
    float rect[4];
    float maximum_pq;
    bool called, failed;
    const uint32_t *packets;
    uint32_t count, flip;
    pl_shader native_shader;
    bool early_mask, source_domain, source_overlay, straight_overlay, linear_output;
    bool reference_transport, profile5_transport, scaled_quad;
    bool ipt_quad;
    const struct cb1_master_ipt *ipt;
    const pl_tex *ipt_pq;
    pl_tex reference_target;
    pl_tex reference_source;
    pl_tex scaled_reference;
    float scaled_rect[4];
    const struct dvbridge_native_overlay *overlay;
    float nonlinear[9], offset[3], linear[9];
};

static bool invert_overlay_matrix(pl_matrix3x3 *m)
{
    const float (*v)[3]=m->m;
    double d=(double)v[0][0]*(v[1][1]*v[2][2]-v[1][2]*v[2][1])-
             (double)v[0][1]*(v[1][0]*v[2][2]-v[1][2]*v[2][0])+
             (double)v[0][2]*(v[1][0]*v[2][1]-v[1][1]*v[2][0]);
    if (!isfinite(d) || fabs(d)<1e-8) return false;
    pl_matrix3x3_invert(m);
    for(int i=0;i<3;i++)for(int j=0;j<3;j++)
        if(!isfinite(m->m[i][j]))return false;
    return true;
}

/* Inverse of libplacebo's source-YCC to linear BT.2020 decode. */
static bool source_overlay_coefficients(struct active_mask *mask,
                                        const struct dvbridge_color *mapped)
{
    struct pl_color_repr post=mapped->repr;
    pl_color_repr_normalize(&post);
    pl_transform3x3 tr=pl_color_repr_decode(&post,NULL);
    pl_matrix3x3 linear={{{3.06441879f,-2.16597676f,.10155818f},
        {-.65612108f,1.78554118f,-.12943749f},{.01736321f,-.04725154f,1.03004253f}}};
    pl_matrix3x3_mul(&linear,&mapped->dovi.linear);
    if(!invert_overlay_matrix(&tr.mat) || !invert_overlay_matrix(&linear))return false;
    for(int i=0;i<3;i++) {
        mask->offset[i]=tr.c[i];
        for(int j=0;j<3;j++) {
            mask->nonlinear[j*3+i]=tr.mat.m[i][j];
            mask->linear[j*3+i]=linear.m[i][j];
        }
    }
    return true;
}

static struct pl_hook_res skip_inactive_area(struct active_mask *mask,
                                             const struct pl_hook_params *p)
{
    mask->native_shader = p->sh;
    struct pl_shader_var vars[] = {
        {.var=pl_var_vec4("early_area"), .data=mask->rect, .dynamic=true},
        {.var={.name="early_words", .type=PL_VAR_UINT, .dim_v=4, .dim_m=1, .dim_a=32*(mask->count ? mask->count : 1)},
         .data=mask->packets, .dynamic=true},
        {.var=pl_var_uint("early_count"), .data=&mask->count, .dynamic=true},
        {.var=pl_var_uint("early_flip"), .data=&mask->flip, .dynamic=true},
        {.var=pl_var_vec4("early_overlay"), .data=mask->overlay ? mask->overlay->rect : mask->rect,
         .dynamic=true}};
    struct pl_custom_shader shader = {
        .input=PL_SHADER_SIG_COLOR, .output=PL_SHADER_SIG_COLOR,
        .description="Skip reconstruction outside the DV active picture",
        .header=
            mask->linear_output ? "#define CB1_LINEAR_EARLY_OUTPUT 1\n" :
            (mask->profile5_transport || mask->ipt_quad) ? (mask->overlay ?
                "#define CB1_PROFILE5_TRANSPORT 1\n#define CB1_NATIVE_OVERLAY 1\n" :
                "#define CB1_PROFILE5_TRANSPORT 1\n") :
            mask->overlay ? "#define CB1_NATIVE_OVERLAY 1\n" : "",
        .variables=vars, .num_variables=5,
        .body=
        "ivec2 ep=ivec2(gl_FragCoord.xy); if(early_flip!=0u) ep.y=2159-ep.y;\n"
        // Keep boundary pairs together: their chroma also uses the active neighbor.
        "int ex=ep.x&~1;\n"
        "#ifdef CB1_LINEAR_EARLY_OUTPUT\n"
        "int ey=ep.y&~1;\n"
        "bool outside=float(ex+1)<early_area.x || float(ex)>=early_area.z || float(ey+1)<early_area.y || float(ey)>=early_area.w;\n"
        "#else\n"
        "bool outside=float(ex+1)<early_area.x || float(ex)>=early_area.z || float(ep.y)<early_area.y || float(ep.y)>=early_area.w;\n"
        "#endif\n"
        "#ifdef CB1_NATIVE_OVERLAY\n"
        "outside=outside && !(float(ex)>=early_overlay.x && float(ex)<early_overlay.z && float(ep.y)>=early_overlay.y && float(ep.y)<early_overlay.w);\n"
        "#endif\n"
        "if(outside){\n"
        "#ifdef CB1_LINEAR_EARLY_OUTPUT\n"
        "return vec4(0.0,0.0,0.0,1.0);\n"
        "#else\n"
        "uint ei=uint(ep.y*3840+ep.x), ek=ei/3072u, ev=0u;\n"
        "if(ek<early_count){uint eb=ei%1024u, ew=ek*128u+eb/8u;\n"
        "ev=(early_words[ew/4u][int(ew%4u)]>>(7u-eb%8u))&1u;}\n"
        "#ifdef CB1_PROFILE5_TRANSPORT\n"
        "if(ek<early_count)ev^=1u;\n"
        "return vec4(128.0,0.0,float(ev*16u),255.0)/255.0;\n"
        "#else\n"
        "return vec4(128.0,16.0,float(ev*16u),255.0)/255.0;\n"
        "#endif\n"
        "#endif\n}\n"};
    mask->failed = pl_shader_is_compute(p->sh) || !pl_shader_custom(p->sh, &shader);
    return (struct pl_hook_res){.failed=mask->failed, .output=PL_HOOK_SIG_NONE};
}

static bool clamp_picture(pl_shader shader,float maximum)
{
    if(maximum<=0)return true;
    struct pl_shader_var limit={.var=pl_var_float("picture_ceiling"),.data=&maximum,.dynamic=true};
    return pl_shader_custom(shader,&(struct pl_custom_shader){
        .input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,.variables=&limit,.num_variables=1,
        .body="color.rgb=clamp(color.rgb,0.0,picture_ceiling);\n"
              "color.rgb=mix(color.rgb,vec3(0),lessThanEqual(color.rgb,vec3(7.30956e-7)));\n",
        .description="Retain the HDR envelope after picture enlargement"});
}

/* Public libplacebo hook/resource adapter for the replacement fused kernels. */
static struct pl_hook_res pack_active_area(void *priv, const struct pl_hook_params *p)
{
    struct active_mask *mask = priv;
    if(p->stage==PL_HOOK_RGB){
        pl_shader sh=p->sh;
        pl_dispatch_abort(p->dispatch,&sh);
        return (struct pl_hook_res){.output=PL_HOOK_SIG_TEX,.tex=mask->reference_source,
            .repr=p->repr,.color=p->color,.components=p->components,.rect=p->rect};
    }
    if (p->stage == PL_HOOK_NATIVE)
        return skip_inactive_area(mask, p);
    mask->called = true;
    if(!clamp_picture(p->sh,mask->maximum_pq))
        return (struct pl_hook_res){.failed=mask->failed=true};
    float ipt_decode[9]={0},ipt_linear[9]={0},ipt_encode[9]={0},ipt_offset[3]={0};
    if(mask->ipt)for(int i=0;i<3;i++) {
        ipt_offset[i]=mask->ipt->offset[i];
        for(int j=0;j<3;j++) {
            ipt_decode[j*3+i]=mask->ipt->decode[i*3+j];
            ipt_linear[j*3+i]=mask->ipt->linear[i*3+j];
            ipt_encode[j*3+i]=mask->ipt->encode[i*3+j];
        }
    }
    struct pl_shader_var vars[] = {
        {.var = pl_var_vec4("active_area"), .data = mask->rect, .dynamic = true},
        {.var = {.name="metadata_words", .type=PL_VAR_UINT, .dim_v=4, .dim_m=1, .dim_a=32*(mask->count ? mask->count : 1)},
         .data=mask->packets, .dynamic=true},
        {.var=pl_var_uint("packet_count"), .data=&mask->count, .dynamic=true},
        {.var=pl_var_uint("flip_y"), .data=&mask->flip, .dynamic=true},
        {.var=pl_var_vec4("overlay_area"), .data=mask->overlay ? mask->overlay->rect : mask->rect, .dynamic=true},
        {.var=pl_var_mat3("overlay_decode"), .data=mask->nonlinear, .dynamic=true},
        {.var=pl_var_vec3("overlay_offset"), .data=mask->offset, .dynamic=true},
        {.var=pl_var_mat3("overlay_linear"), .data=mask->linear, .dynamic=true},
        {.var=pl_var_vec4("scaled_rect"), .data=mask->scaled_rect, .dynamic=true},
        {.var=pl_var_mat3("ipt_decode"), .data=ipt_decode, .dynamic=true},
        {.var=pl_var_mat3("ipt_linear"), .data=ipt_linear, .dynamic=true},
        {.var=pl_var_mat3("ipt_encode"), .data=ipt_encode, .dynamic=true},
        {.var=pl_var_vec3("ipt_offset"), .data=ipt_offset, .dynamic=true},
    };
    struct pl_shader_desc desc[6]={0};
    if(mask->overlay) {
        const char *names[]={"subtitle_gui","subtitle_degamma","subtitle_pq"};
        pl_tex textures[]={mask->overlay->texture,mask->overlay->degamma,mask->overlay->pq};
        for(int i=0;i<3;i++) {
            desc[i].desc.name=names[i];desc[i].desc.type=PL_DESC_SAMPLED_TEX;
            desc[i].binding.object=textures[i];
            desc[i].binding.sample_mode=PL_TEX_SAMPLE_LINEAR;
            desc[i].binding.address_mode=PL_TEX_ADDRESS_CLAMP;
        }
    }
    if(mask->scaled_reference){
        unsigned i=mask->overlay?3:0;
        desc[i]=(struct pl_shader_desc){.desc={.name="scaled_reference",.type=PL_DESC_SAMPLED_TEX},
            .binding={.object=mask->scaled_reference,.sample_mode=PL_TEX_SAMPLE_NEAREST}};
    }
    unsigned descriptors=(mask->overlay?3:0)+(mask->scaled_reference?1:0);
    if(mask->ipt)for(int i=0;i<2;i++)
        desc[descriptors++]=(struct pl_shader_desc){
            .desc={.name=i?"ipt_oetf":"ipt_eotf",.type=PL_DESC_SAMPLED_TEX},
            .binding={.object=mask->ipt_pq[i],.sample_mode=PL_TEX_SAMPLE_NEAREST}};
    char header[sizeof(CB1_CARRIER_GLSL CB1_PACKET_GLSL CB1_SOURCE_CODES_GLSL CB1_RGB_PIXEL_GLSL CB1_COMPOSITE_HEADER_GLSL CB1_MASTER_IPT_GLSL CB1_IPT_CODES_GLSL)+512];
    snprintf(header,sizeof(header),"%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s%s",
        mask->source_domain ? "#define CB1_SOURCE_DOMAIN 1\n" : "",
        mask->overlay ? "#define CB1_NATIVE_OVERLAY 1\n" : "",
        mask->overlay && mask->overlay->input_pq ? "#define CB1_OVERLAY_PQ 1\n" : "",
        mask->source_overlay ? "#define CB1_SOURCE_OVERLAY 1\n" : "",
        mask->straight_overlay ? "#define CB1_STRAIGHT_OVERLAY 1\n" : "",
        mask->reference_transport ? "#define CB1_REFERENCE_TRANSPORT 1\n" : "",
        mask->scaled_reference ? "#define CB1_SCALED_REFERENCE 1\n" : "",
        mask->profile5_transport ? "#define CB1_SOURCE_BLACK 0.0\n" :
            "#define CB1_SOURCE_BLACK .0625\n",
        mask->scaled_quad || mask->ipt_quad ? "#define CB1_SCALED_QUAD 1\n" : "",
        mask->ipt_quad ? "#define CB1_IPT_QUAD 1\n" : "",
        mask->ipt && mask->ipt_pq[0]->params.format->num_components==1 ? "#define CB1_IPT_COMPACT 1\n" : "",
        mask->ipt ? CB1_MASTER_IPT_GLSL : "",
        mask->ipt ? "#define CB1_SOURCE_NEUTRAL (ipt_offset*(4096.0/4095.0))\n" :
            "#define CB1_SOURCE_NEUTRAL vec3(CB1_SOURCE_BLACK,.5,.5)\n",
        CB1_CARRIER_GLSL CB1_PACKET_GLSL CB1_RGB_PIXEL_GLSL,
        mask->ipt ? CB1_IPT_CODES_GLSL : CB1_SOURCE_CODES_GLSL,
        CB1_COMPOSITE_HEADER_GLSL
    );
    struct pl_custom_shader shader = {
        .prelude=!mask->scaled_quad && !mask->ipt_quad && (mask->ai_renderer || mask->reference_transport) ? NULL : "#extension GL_KHR_shader_subgroup_basic : require\n"
                 "#extension GL_KHR_shader_subgroup_quad : require\n",
        .header=header,
        .input=mask->scaled_reference?PL_SHADER_SIG_NONE:PL_SHADER_SIG_COLOR, .output=PL_SHADER_SIG_COLOR,
        .description="Exact full-raster DV transport without intermediate image",
        .output_w=mask->scaled_reference?3840:0,.output_h=mask->scaled_reference?2160:0,
        .variables=vars, .num_variables=
            mask->ipt ? 13 : mask->scaled_reference ? 9 : mask->overlay ? 8 : 4,
        .descriptors=desc, .num_descriptors=descriptors,
        .body=CB1_COMPOSITE_BODY_GLSL};
    // An early return must reach the transport target, never an intermediate image.
    mask->failed = mask->failed || p->stage != PL_HOOK_OUTPUT ||
                   (mask->early_mask && mask->native_shader != p->sh) || pl_shader_is_compute(p->sh) ||
                   !pl_shader_custom(p->sh, &shader);
    return (struct pl_hook_res){.failed=mask->failed, .output=PL_HOOK_SIG_NONE};
}

/* Materialize resized reference codes so both packed pixels share chroma. */
static struct pl_hook_res pack_scaled_reference(void *priv,const struct pl_hook_params *p)
{
    struct active_mask *mask=priv;
    if(!p->tex || fabsf(p->rect.x1-p->rect.x0)!=3840 || fabsf(p->rect.y1-p->rect.y0)!=2160)
        return (struct pl_hook_res){.failed=true};
    mask->scaled_reference=p->tex;
    mask->scaled_rect[0]=p->rect.x0;mask->scaled_rect[1]=p->rect.y0;
    mask->scaled_rect[2]=(p->rect.x1-p->rect.x0)/3840;
    mask->scaled_rect[3]=(p->rect.y1-p->rect.y0)/2160;
    pl_shader sh=pl_dispatch_begin(p->dispatch);
    struct pl_hook_params sampled=*p;sampled.sh=sh;
    struct pl_hook_res result=pack_active_area(priv,&sampled);
    if(result.failed){pl_dispatch_abort(p->dispatch,&sh);return result;}
    return (struct pl_hook_res){.output=PL_HOOK_SIG_COLOR,.sh=sh,
        .repr=p->repr,.color=p->color,.components=4,.rect=p->rect};
}

/* Initialize the carrier before fused reconstruction into an unscaled viewport. */
static struct pl_hook_res pack_placed_reference(void *priv,const struct pl_hook_params *p)
{
    struct active_mask *mask=priv;
    if(p->stage==PL_HOOK_OUTPUT)return pack_active_area(priv,p);
    struct active_mask blank=*mask;
    pl_shader sh=pl_dispatch_begin(p->dispatch);
    bool ok=pl_shader_custom(sh,&(struct pl_custom_shader){
        .input=PL_SHADER_SIG_NONE,.output=PL_SHADER_SIG_COLOR,
        .output_w=3840,.output_h=2160,.body=mask->profile5_transport ?
            "color=vec4(0.0,.5,.5,1.0);" : "color=vec4(.0625,.5,.5,1.0);"});
    struct pl_hook_params output=*p;output.stage=PL_HOOK_OUTPUT;output.sh=sh;
    if(ok)ok=!pack_active_area(&blank,&output).failed;
    if(ok)ok=pl_dispatch_finish(p->dispatch,pl_dispatch_params(.shader=&sh,.target=mask->reference_target));
    pl_dispatch_abort(p->dispatch,&sh);
    mask->failed=!ok;
    return (struct pl_hook_res){.failed=!ok,.output=PL_HOOK_SIG_NONE};
}

static struct pl_hook_res mask_active_area(void *priv, const struct pl_hook_params *p)
{
    struct active_mask *mask = priv;
    if (p->stage == PL_HOOK_NATIVE)
        return skip_inactive_area(mask,p);
    mask->called = true;
    if(!clamp_picture(p->sh,mask->maximum_pq))
        return (struct pl_hook_res){.failed=mask->failed=true};
    struct pl_shader_var variable = {
        .var = pl_var_vec4("dvbridge_active"), .data = mask->rect, .dynamic = true};
    struct pl_custom_shader shader = {
        .input = PL_SHADER_SIG_COLOR, .output = PL_SHADER_SIG_COLOR,
        .header = mask->linear_output ? "#define CB1_LINEAR_OUTPUT 1\n" :
            mask->ai_renderer && mask->ai_renderer->dv.ai_direct_flip ? "#define CB1_AI_FLIP 1\n" : "",
        .body = "vec2 active_pos=gl_FragCoord.xy;\n#ifdef CB1_AI_FLIP\nactive_pos.y=2160.0-active_pos.y;\n#endif\n"
                "if(active_pos.x < dvbridge_active.x || active_pos.x >= dvbridge_active.z || "
                "active_pos.y < dvbridge_active.y || active_pos.y >= dvbridge_active.w) "
                "color = vec4(0.0, 0.0, 0.0, 1.0);\n"
                "#ifdef CB1_LINEAR_OUTPUT\ncolor.rgb *= 203.0/10000.0;\n#endif\n",
        .variables = &variable, .num_variables = 1,
        .description = "DV active picture blanking before target overlays"};
    mask->failed = p->stage != PL_HOOK_OUTPUT ||
        (mask->early_mask && (mask->native_shader != p->sh || pl_shader_is_compute(p->sh))) ||
        !pl_shader_custom(p->sh, &shader);
    return (struct pl_hook_res){.failed = mask->failed, .output = PL_HOOK_SIG_NONE};
}

struct dvbridge_renderer *dvbridge_renderer_create(pl_gpu gpu)
{
    if (!gpu || pl_cb1_processing_abi()!=PL_CB1_PROCESSING_ABI ||
        pl_cb1_chroma_filter_abi()!=PL_CB1_CHROMA_FILTER_API)
        return NULL;
    struct dvbridge_renderer *r = calloc(1, sizeof(*r));
    if (!r)
        return NULL;
    r->gpu = gpu;
    // Query just the operation used here. libplacebo's global subgroup flag
    // requires arithmetic/clustered features that this fragment hook never uses.
    pl_opengl gl = pl_opengl_get(gpu);
    if (gl) {
        const char *vendor = (const char *)glGetString(GL_VENDOR);
        const char *renderer = (const char *)glGetString(GL_RENDERER);
        const bool intel=vendor && !strcmp(vendor,"Intel");
        /* Retain storage/overlap only on the driver with a measured gain. */
        r->reuse_authored_storage=intel;
        /* Analytic P5 expansion saves work on Intel; radeonsi retains its LUT. */
        r->authored_p5_analytic=intel;
        /* The existing encoder saves ALU work on radeonsi, not on Intel. */
        r->expert_warp_lookup=renderer && strstr(renderer,"radeonsi");
        /* Scalar tables retain exact samples; use them only on radeonsi. */
        r->master_ipt_compact=renderer && strstr(renderer,"radeonsi");
        // ADL-N RGBA16F conversion/interpolation was verified by GPU readback.
        r->exact_scaler_cache = intel &&
                                renderer && strstr(renderer, "(ADL-N)");
    }
    if (gl && pl_opengl_has_ext(gl, "GL_KHR_shader_subgroup")) {
        GLint size=0, stages=0, features=0;
        glGetIntegerv(0x9532, &size);
        glGetIntegerv(0x9533, &stages);
        glGetIntegerv(0x9534, &features);
        r->fragment_quad = size >= 4 && size <= 128 && !(size & (size-1)) &&
                           (stages & GL_FRAGMENT_SHADER_BIT) && (features & 0x81) == 0x81;
    }
    r->renderer = pl_renderer_create(NULL, gpu);
    r->context = dvbridge_create();
    pl_fmt fmt = pl_find_fmt(gpu, PL_FMT_FLOAT, 4, 32, 32,
                             PL_FMT_CAP_RENDERABLE | PL_FMT_CAP_SAMPLEABLE);
    if (!r->renderer || !r->context || !fmt) {
        dvbridge_renderer_destroy(r);
        return NULL;
    }
    return r;
}

void dvbridge_renderer_reset(struct dvbridge_renderer *r)
{
    if (!r)
        return;
    r->cm29_tail_key_valid=false;
    dvbridge_render_dv_policy_cancel(r);
    r->dv_has_committed=false;
    r->enhanced_has_committed=false;
    dvbridge_candidate_destroy(r->pending);
    r->pending = NULL;
    r->ready = false;
    r->direct_output = false;
    r->packed = false;
    r->policy_ready = r->policy_has_committed = false;
    dvbridge_reset(r->context);
    if (r->renderer && !r->dv.active && !r->retired_packed.active) {
        cb1_processing_reset(&r->processing,r->gpu);
        pl_renderer_flush_cache(r->renderer);
        pl_renderer_reset_errors(r->renderer, NULL);
    }
}

void dvbridge_renderer_set_optimized_dv(struct dvbridge_renderer *r, bool enabled)
{
    if (r) r->optimized_dv = enabled;
}

void dvbridge_renderer_set_fast_chroma(struct dvbridge_renderer *r, bool enabled)
{
    if (r) r->fast_chroma = enabled;
}

void dvbridge_renderer_set_fel_nearest(struct dvbridge_renderer *r, bool enabled)
{
    if (r) r->fel_nearest = enabled;
}

void dvbridge_renderer_set_processing_optimizations(struct dvbridge_renderer *r, bool enabled)
{
    if (r) r->processing_optimizations = enabled;
}

void dvbridge_renderer_set_overlay_visible(struct dvbridge_renderer *r, bool visible)
{
    if (r) { r->overlay_visible=visible; dvbridge_set_overlay_visible(r->context, visible); }
}

void dvbridge_renderer_destroy(struct dvbridge_renderer *r)
{
    if (!r)
        return;
    dvbridge_render_dv_policy_cancel(r);
    if (r->owner) {
        struct dvbridge_retirement_owner *owner=r->owner;
        owner->attached=NULL;
        if (r->dv.active || r->retired_packed.active) { owner->lease=r;return; }
    }
    renderer_free(r);
}

/* Destroy wrappers before the immutable GL storage they borrow. */
static void dve_release_images(struct dvbridge_renderer *r)
{
    pl_tex_destroy(r->gpu,&r->ai_enhanced_stats);
    pl_tex_destroy(r->gpu,&r->ai_enhanced_native);
    pl_tex_destroy(r->gpu,&r->ai_enhanced_packed);
    glDeleteTextures(1,&r->ai_enhanced_stats_texture);r->ai_enhanced_stats_texture=0;
    glDeleteTextures(1,&r->ai_enhanced_native_texture);r->ai_enhanced_native_texture=0;
    pl_tex_destroy(r->gpu,&r->enhanced_rgb);
    glDeleteTextures(1,&r->enhanced_texture);r->enhanced_texture=0;
    glDeleteTextures(1,&r->enhanced_packed_texture);r->enhanced_packed_texture=0;
    glDeleteFramebuffers(1,&r->enhanced_packed_fbo);r->enhanced_packed_fbo=0;
}

static void renderer_free(struct dvbridge_renderer *r)
{
    if(r->analysis_storage.mapped)
        dv_delete_storage(r->analysis_storage.buffers,r->analysis_storage.sampler,r->analysis_storage.mapped);
    cb1_processing_reset(&r->processing,r->gpu);
#ifdef CB1_TEST_LEGACY_ANALYSIS
    glDeleteProgram(r->dv_analysis_program);
#endif
    glDeleteProgram(r->enhanced_program);
    dvbridge_gl_packer_destroy(r->dv_transport_packer);
    dvbridge_candidate_destroy(r->pending);
    dvbridge_destroy(r->context);
    pl_tex_destroy(r->gpu, &r->rgb);
    for(int i=0;i<2;i++)pl_tex_destroy(r->gpu,&r->ipt_pq[i]);
    pl_tex_destroy(r->gpu, &r->p5_native);
    pl_tex_destroy(r->gpu, &r->native_picture);
    pl_tex_destroy(r->gpu, &r->ai_rgb);
    pl_tex_destroy(r->gpu, &r->enhanced_input);
    dve_release_images(r);
    pl_tex_destroy(r->gpu, &r->cm29_tail_atlas);
    pl_tex_destroy(r->gpu, &r->cm29_tail_axis);
    pl_renderer_destroy(&r->renderer);
    pl_shader_obj_destroy(&r->creative_state);
    pl_shader_obj_destroy(&r->creative_gamut_state);
    for(int i=0;i<2;i++)pl_shader_obj_destroy(&r->creative_detail_lut[i]);
    free(r);
}

static bool render_image(struct dvbridge_renderer *r,const struct pl_frame *image,
    const struct pl_frame *target,struct pl_render_params *params,
    struct active_mask *mask,struct reference_hook *reference,bool active_rows)
{
    uint32_t optional=params->cb1_processing?params->cb1_processing->groups:0;
    for(unsigned attempt=0;attempt<2;attempt++){
        if(mask){mask->called=mask->failed=false;mask->native_shader=NULL;}
        if(reference){reference->called=reference->failed=false;
            reference->scaled_shader=NULL;reference->feature_map=NULL;}
        if(attempt && reference){
            reference->gpu_map_eligible=false;
            reference->gpu_map_used=false;
        }
        unsigned top=active_rows?(unsigned)mask->rect[1]:0;
        unsigned bottom=active_rows?(unsigned)mask->rect[3]:0;
        bool ok=active_rows?
            pl_render_image_cb1_active_rows(r->renderer,image,target,params,
                top,bottom):
            pl_render_image(r->renderer,image,target,params);
        struct pl_render_errors errors=pl_renderer_get_errors(r->renderer);
        ok=ok && !errors.errors && !errors.num_disabled_hooks &&
            (reference?reference->called && !reference->failed:mask->called && !mask->failed);
        if(ok){
            if(attempt)r->processing_failed_groups|=optional;
            return true;
        }
        if(!optional || attempt || (reference && reference->gpu_map_eligible) ||
           r->dv.quarantined || r->retired_packed.quarantined ||
           pl_gpu_is_failed(r->gpu))return false;
        /* Same-context ordered retry, before publication. Keep every lease;
         * the caller's completion fence covers both attempts. */
        params->cb1_processing=NULL;
        pl_renderer_reset_errors(r->renderer,NULL);
    }
    return false;
}

static bool cm29_tail_gain_eligible(double gain_code)
{
    return gain_code >= 2048.0;
}

static bool render_picture(struct dvbridge_renderer *r, const struct pl_frame *source,
                        const void *metadata, size_t bytes, double pts, double el_pts,
                        struct dvbridge_geometry geometry, pl_tex packed, bool flip,
                        const struct dvbridge_hdr10_session *session,
                        const struct dvbridge_policy *policy,
                        const struct dvbridge_native_overlay *overlay,bool force_refresh,
                        struct direct_output *direct,bool enhanced_reconstruction,
                        const struct pl_cb1_dovi_reference *master,bool p5_fast,
                        const struct cb1_master_ipt *ipt,bool native_stage)
{
    if (!r)
        return false;
    if (r->dv.active) {
        dvbridge_render_dv_policy_cancel(r);
        return false;
    }
    r->ready = false;
    r->direct_output = false;
    r->policy_ready = false;
    r->packed = packed != NULL;
    dvbridge_candidate_destroy(r->pending);
    r->pending = NULL;
    if (!source || !isfinite(pts) || source->num_planes < 1 || source->num_planes > 4 || source->rotation ||
        source->crop.x0 != 0 || source->crop.y0 != 0 ||
        source->crop.x1 != geometry.source_width || source->crop.y1 != geometry.source_height)
        return false;
    for (int p = 0; p < source->num_planes; ++p)
        if (!source->planes[p].texture)
            return false;
    const struct pl_frame *el = source->enhancement_layer;
    if (el) {
        if (el->num_planes < 1 || el->num_planes > 4 || el->rotation || el->enhancement_layer)
            return false;
        for (int p = 0; p < el->num_planes; ++p)
            if (!el->planes[p].texture)
                return false;
    }
    bool paired = source->enhancement_layer && isfinite(el_pts) && fabs(pts - el_pts) < 0.00001;
    struct dvbridge_color mapped;
    struct pl_color_space nominal;
    struct dvbridge_hdr10_metadata signal;
    struct dvbridge_creative_plan creative={0};
    if (policy) {
        paired = source->enhancement_layer && pts == el_pts;
        if (!dvbridge_reference_map(&mapped, &nominal, &signal, policy, metadata, bytes, paired))
            return false;
        if(policy->mode==DVBRIDGE_MODE_HDR10_EXPERT &&
           dvbridge_creative_resolve(&creative,metadata,bytes,policy)==DVBRIDGE_CREATIVE_INVALID)return false;
    } else if (!dvbridge_map_color(&mapped, metadata, bytes, paired)) return false;
    // Other pipelines retain their FP32 backing; native direct transport needs none.
    if((session || policy || enhanced_reconstruction || native_stage || (!packed && !direct)) &&
       !(enhanced_reconstruction && r->reuse_authored_storage && r->enhanced_authored && r->enhanced_input) &&
       !ensure_rgb(r))return false;
    mapped.dovi.cb1_native_bounds=!session && !policy && !enhanced_reconstruction;
    unsigned margins[4]={0};
    float policy_area[4];
    if (policy) {
        if (policy->mode==DVBRIDGE_MODE_ENHANCED_DV) {
            if (!dvbridge_frame_area(margins,metadata,bytes,geometry)) return false;
            policy_area[0]=margins[0];policy_area[1]=margins[2];
            policy_area[2]=3840-margins[1];policy_area[3]=2160-margins[3];
        } else if (!reference_area(policy_area,metadata,geometry)) return false;
    }
    if (session) {
        if (!dvbridge_frame_area(margins, metadata, bytes, geometry))
            return false;
        const AVDOVIMetadata *m = metadata;
        unsigned l1_count = 0;
        for (int i = 0; i < m->num_ext_blocks; ++i)
            if (av_dovi_get_ext(m, i)->level == 1 && ++l1_count > 1)
                return false;
    } else if (!policy) {
        if (!dvbridge_frame_area(margins,metadata,bytes,geometry))
            return false;
    }
    struct pl_frame image = *source;
    mapped.repr.bits = source->repr.bits;
    mapped.repr.alpha = source->repr.alpha;
    image.repr = mapped.repr;
    image.color = mapped.color;
    image.profile = (struct pl_icc_profile){0};
    image.icc = NULL;
    image.lut = NULL;
    struct pl_frame target = {
        .num_planes = 1,
        .planes = {{.texture = native_stage ? r->native_picture : direct ? direct->texture : packed ? packed :
                    enhanced_reconstruction && r->enhanced_input ? r->enhanced_input : r->rgb,
                    .flipped = direct ? direct->flip : packed && flip,
                    .components = 4, .component_mapping = {0, 1, 2, 3}}},
        .repr = pl_color_repr_rgb,
        .color = mapped.color,
        .crop = {geometry.x, geometry.y, geometry.x + geometry.width, geometry.y + geometry.height},
    };
    if(direct && !direct->custom_quantize) {
        target.repr.levels=direct->limited?PL_COLOR_LEVELS_LIMITED:PL_COLOR_LEVELS_FULL;
        target.repr.bits.sample_depth=direct->bits;
        target.repr.bits.color_depth=direct->bits;
    }
    struct pl_render_params params = pl_render_default_params;
    params.cb1_dovi_reference=master;
    params.cb1_fast_chroma = master ? p5_fast : r->fast_chroma;
    params.cb1_fel_nearest = !master && r->fel_nearest && paired && mapped.dovi.nlq_active;
    uint32_t processing=master?0:r->processing_optimizations?CB1_PROCESSING_ALL:
        enhanced_reconstruction?CB1_PROCESSING_COLOUR:0;
    /* Analytic PQ avoids decoder lookups in authored Fast FEL reconstruction. */
    if (!master && enhanced_reconstruction && r->enhanced_linear && r->fast_chroma &&
        paired && mapped.dovi.nlq_active)
        processing &= ~CB1_PROCESSING_COLOUR;
    struct pl_color_map_params color_map = pl_color_map_default_params;
    if (session) {
        params.cb1_nearest_identity = true;
        target.color = session->target;
        /* Pin the accepted Basic policy independently of upstream defaults. */
        color_map = (struct pl_color_map_params){
            .gamut_mapping = &pl_gamut_map_perceptual,
            .tone_mapping_function = &pl_tone_map_spline,
            .gamut_constants = {
                .colorimetric_gamma = 1.80f, .softclip_knee = 0.70f,
                .softclip_desat = 0.35f, .perceptual_deadzone = 0.30f,
                .perceptual_strength = 0.80f,
            },
            .tone_constants = {
                .knee_adaptation = 0.4f, .knee_minimum = 0.1f,
                .knee_maximum = 0.8f, .knee_default = 0.4f,
                .knee_offset = 1.0f, .slope_tuning = 1.5f,
                .slope_offset = 0.2f, .spline_contrast = 0.5f,
                .reinhard_contrast = 0.5f, .linear_knee = 0.3f,
                .exposure = 1.0f,
            },
            .lut3d_size = {48, 32, 256}, .lut_size = 256,
            .contrast_smoothness = 3.5f,
            .inverse_tone_mapping = false,
        };
        const AVDOVIDmData *l1 = av_dovi_find_level(metadata, 1);
        if (l1 && l1->l1.min_pq <= l1->l1.avg_pq &&
            l1->l1.avg_pq <= l1->l1.max_pq && l1->l1.max_pq <= 4095 && l1->l1.max_pq) {
            color_map.metadata = PL_HDR_METADATA_CIE_Y;
        } else {
            image.color.hdr.max_pq_y = image.color.hdr.avg_pq_y = 0;
            color_map.metadata = PL_HDR_METADATA_HDR10;
        }
        params.color_map_params = &color_map;
    }
    if (policy) {
        target.color = nominal;
        params.cb1_nearest_identity = true;
        params.cb1_stable_pq = policy->mode != DVBRIDGE_MODE_HDR10_EXPERT;
        params.cb1_fp32_scaler_lut = true;
        params.sigmoid_params = NULL;
        color_map = (struct pl_color_map_params){
            .gamut_mapping=&pl_gamut_map_perceptual,.tone_mapping_function=&pl_tone_map_spline,
            .gamut_constants={.colorimetric_gamma=1.8f,.softclip_knee=.7f,.softclip_desat=.35f,
                .perceptual_deadzone=.3f,.perceptual_strength=.8f},
            .tone_constants={.knee_adaptation=.4f,.knee_minimum=.1f,.knee_maximum=.8f,.knee_default=.4f,
                .knee_offset=1,.slope_tuning=1.5f,.slope_offset=.2f,.spline_contrast=.5f,
                .reinhard_contrast=.5f,.linear_knee=.3f,.exposure=1},
            .lut3d_size={48,32,256},.lut_size=256,.contrast_smoothness=3.5f,
            .metadata=PL_HDR_METADATA_CIE_Y,.inverse_tone_mapping=false,
            .gamut_expansion=true,.cb1_fp32_tone_lut=true,
        };
        params.color_map_params = &color_map;
    }
    if(policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT && !creative.l1_present)
        color_map.metadata=PL_HDR_METADATA_HDR10;
    if(enhanced_reconstruction && r->enhanced_linear){
        params.cb1_nearest_identity=r->fast_chroma && paired && mapped.dovi.nlq_active;
        /* Explicit luminance prevents an intermediate linear surface from
         * being inferred as an SDR target. Storage is normalized to 10000 nits. */
        image.color.transfer=PL_COLOR_TRC_LINEAR;
        image.color.hdr.min_luma=PL_COLOR_HDR_BLACK;image.color.hdr.max_luma=10000;
        target.color=image.color;
    }
    r->reconstructed_color = target.color;
    params.min_fbo_precision = 32;
    params.peak_detect_params = NULL;
    params.dither_params = NULL;
    if(direct && !direct->custom_quantize)params.dither_params=&pl_dither_default_params;
    params.frame_mixer = NULL;
    params.skip_caching_single_frame = true;
    // Own exact PQ-zero borders below. Do not translate an sRGB clear color
    // through the output transfer function or clear a full-raster frame twice.
    params.border = PL_CLEAR_SKIP;
    struct active_mask mask = {.rect = {margins[0], margins[2],
                                       3840 - margins[1], 2160 - margins[3]}};
    mask.linear_output=enhanced_reconstruction && r->enhanced_linear;
    if(direct && direct->flip){
        float top=mask.rect[1],bottom=mask.rect[3];
        mask.rect[1]=2160-bottom;mask.rect[3]=2160-top;
    }
    mask.overlay=overlay;
    mask.reference_transport=master!=NULL;
    mask.profile5_transport=master && dvbridge_dv_profile5_transport(metadata);
    mask.ipt=ipt;
    mask.ipt_pq=r->ipt_pq;
    mask.straight_overlay=r->optimized_dv && overlay && !overlay->input_pq;
    bool full_transport=packed && (!ipt || r->fragment_quad) && !session && !policy && !source->num_overlays &&
        (!el || !el->num_overlays) &&
        geometry.source_width==3840 && geometry.source_height==2160 && !geometry.x && !geometry.y &&
        geometry.width==3840 && geometry.height==2160;
    bool placed_reference=master && !ipt && !full_transport && !source->num_overlays &&
        (!el || !el->num_overlays) && geometry.width==geometry.source_width &&
        geometry.height==geometry.source_height && !(geometry.x&1);
    bool direct_reference=master && (full_transport || placed_reference);
    mask.ipt_quad=ipt && direct_reference;
    /* P5 keeps the same FP32 scaler; exchange its neighbour before packing. */
    mask.scaled_quad=mask.profile5_transport && !direct_reference && r->fragment_quad;
    mask.reference_target=placed_reference?packed:NULL;
    bool reuse_p5=mask.profile5_transport && r->fragment_quad && !direct_reference && !geometry.x && !geometry.y &&
        geometry.width==3840 && geometry.height==2160 &&
        geometry.source_width*9==geometry.source_height*16 && !source->num_overlays;
    if(r->p5_native_pending && (!reuse_p5 || r->p5_native->params.w!=geometry.source_width ||
        r->p5_native->params.h!=geometry.source_height)){
        if(!p5_preserve_backing(r))return false;
    }
    bool packed_picture=packed && !session && !policy && !source->num_overlays &&
        (!el || !el->num_overlays);
    bool source_transport=packed_picture && r->optimized_dv && !mapped.dovi.nlq_active &&
        dvbridge_dv_source_transport(metadata);
    bool canonical_transport=packed_picture && paired && mapped.dovi.nlq_active &&
        dvbridge_dv_source_matches_output(metadata);
    if(master){
        if(!packed || !cb1_master_reference_transport(metadata,bytes) ||
           (margins[0]&1) || (margins[1]&1))return false;
        source_transport=true;
        if(!direct_reference){
            /* Reconstruct on the original sampling grid before fitting the carrier. */
            struct pl_frame native=target;
            native.planes[0].flipped=false;
            if(reuse_p5){
                pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,32,32,
                    PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);
                if(!fmt)return false;
                if(!pl_tex_recreate(r->gpu,&r->p5_native,pl_tex_params(
                        .w=geometry.source_width,.h=geometry.source_height,
                        .format=fmt,.sampleable=true,.renderable=true,.blit_src=true)))return false;
                native.planes[0].texture=mask.reference_source=r->p5_native;
            }else{
                if(!ensure_rgb(r))return false;
                native.planes[0].texture=r->rgb;
            }
            native.crop=(struct pl_rect2df){0,0,geometry.source_width,geometry.source_height};
            struct pl_render_params reconstruction=params;
            reconstruction.cb1_dovi_transport=true;reconstruction.disable_linear_scaling=true;
            reconstruction.sigmoid_params=NULL;
            if(!pl_render_image(r->renderer,&image,&native,&reconstruction))return false;
            if(reuse_p5)r->p5_native_pending=true;
            image=native;image.repr=pl_color_repr_rgb;
            if(mask.profile5_transport){
                image.repr.alpha=PL_ALPHA_NONE;
                params.cb1_nearest_identity=true;
            }
            double sx=(double)geometry.source_width/geometry.width,sy=(double)geometry.source_height/geometry.height;
            image.crop=(struct pl_rect2df){-geometry.x*sx,-geometry.y*sy,
                (3840-geometry.x)*sx,(2160-geometry.y)*sy};
            target.crop=(struct pl_rect2df){0,0,3840,2160};
            params.cb1_dovi_reference=NULL;
        }
    }
    if(packed_picture && !master &&
       (geometry.x || geometry.y || geometry.width!=3840 || geometry.height!=2160)){
        /* Fit the picture, then pack the complete carrier, including its borders. */
        double sx=(double)geometry.source_width/geometry.width;
        double sy=(double)geometry.source_height/geometry.height;
        image.crop=(struct pl_rect2df){-geometry.x*sx,-geometry.y*sy,
            (3840-geometry.x)*sx,(2160-geometry.y)*sy};
        target.crop=(struct pl_rect2df){0,0,3840,2160};
    }
    mask.source_domain=source_transport || canonical_transport;
    if(overlay && mask.source_domain) {
        struct pl_color_repr post=mapped.repr;
        pl_color_repr_normalize(&post);
        pl_transform3x3 tr=pl_color_repr_decode(&post,NULL);
        pl_matrix3x3 linear={{{3.06441879f,-2.16597676f,.10155818f},
            {-.65612108f,1.78554118f,-.12943749f},{.01736321f,-.04725154f,1.03004253f}}};
        pl_matrix3x3_mul(&linear,&mapped.dovi.linear);
        for(int i=0;i<3;i++) {
            mask.offset[i]=tr.c[i];
            for(int j=0;j<3;j++) {
                mask.nonlinear[j*3+i]=tr.mat.m[i][j];
                mask.linear[j*3+i]=linear.m[i][j];
            }
        }
        if(master || (r->optimized_dv && !overlay->input_pq))
            mask.source_overlay=source_overlay_coefficients(&mask,&mapped);
        /* A canonical RGB GUI cannot be mixed into a noncanonical source tunnel. */
        if(source_transport && !mask.source_overlay) {
            if(master)return false;
            source_transport=false;
            mask.source_domain=canonical_transport;
        }
    }
    params.cb1_dovi_transport=mask.source_domain;
    /* Source-domain transport reshapes without PQ decoding or encoding. */
    if(mask.source_domain)processing &= ~CB1_PROCESSING_COLOUR;
    if(processing && cb1_processing_prepare(&r->processing,r->gpu,
            source,metadata,bytes,paired,processing&~r->processing_failed_groups))
        params.cb1_processing=&r->processing.view;
    params.cb1_dovi_linear=(enhanced_reconstruction && r->enhanced_linear) ||
        ((session || (policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT)) &&
         (native_stage || (geometry.source_width==3840 && geometry.source_height==2160 &&
         !geometry.x && !geometry.y && geometry.width==3840 && geometry.height==2160)));
    if(enhanced_reconstruction && r->enhanced_input)
        params.min_fbo_precision=r->enhanced_input->params.format->component_depth[0];
    params.cb1_exact_scaler_cache=mask.source_domain && r->exact_scaler_cache;
    if(!session && !policy) {
        r->pending=
            ipt ?
            dvbridge_prepare_ipt_output(r->context,metadata,bytes,pts,geometry,
                paired && mapped.dovi.nlq_active,force_refresh) :
            master ?
            dvbridge_prepare_master_source_output(r->context,metadata,bytes,pts,geometry,
                paired && mapped.dovi.nlq_active,force_refresh) :
            source_transport ?
            dvbridge_prepare_source_output(r->context,metadata,bytes,pts,geometry,
                paired && mapped.dovi.nlq_active,force_refresh) :
            dvbridge_prepare_output(r->context,metadata,bytes,pts,geometry,
                paired && mapped.dovi.nlq_active,force_refresh);
        if(!r->pending)return false;
    }
    if(mask.source_domain) {
        params.disable_linear_scaling=true;
        params.sigmoid_params=NULL;
    }
    mask.flip = flip;
    mask.packets = dvbridge_packets(r->pending, &mask.count);
    bool authored_linear = enhanced_reconstruction && r->enhanced_linear && r->fast_chroma &&
                           paired && mapped.dovi.nlq_active;
    mask.early_mask = (!ipt || mask.ipt_quad) && !(master && !full_transport) && (packed || authored_linear) && geometry.source_width == 3840 && geometry.source_height == 2160 &&
                      (margins[0] || margins[1] || margins[2] || margins[3]);
    const struct pl_hook hook = {
        .stages = PL_HOOK_OUTPUT | (mask.early_mask || placed_reference ? PL_HOOK_NATIVE : 0) |
            (mask.reference_source?PL_HOOK_RGB:0),
        .input = master && !direct_reference && !mask.scaled_quad ? PL_HOOK_SIG_TEX : PL_HOOK_SIG_COLOR,
        .priv = &mask, .hook = placed_reference ? pack_placed_reference :
            master && !direct_reference && !mask.scaled_quad ? pack_scaled_reference : packed ? pack_active_area : mask_active_area,
        .signature = ipt ? 0x4342314950540001ULL : packed ? 0x4456425246555302ULL : 0x445642524c350001ULL};
    const struct pl_hook *hooks[] = {&hook};
    params.hooks = hooks;
    params.num_hooks = 1;
    struct reference_hook reference = {
        .to_xyz=pl_get_rgb2xyz_matrix(pl_raw_primaries_get(target.color.primaries)),
        .to_bt2020=pl_get_xyz2rgb_matrix(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020)),
        .renderer=r,
    };
    if(policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT)
        reference.pq_encoder=cb1_processing_pq_encoder(&r->processing,r->gpu);
    struct dvbridge_cm4_coefficients cm4;
    bool use_cm4=policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT &&
        dvbridge_creative_cm4_coefficients(&cm4,&creative);
    bool neutral_cm29=false;
    if(policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT){
        const struct pl_raw_primaries *bt2020=pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020);
        struct pl_color_space first_source=mapped.color;
        struct pl_color_space first_target={.primaries=PL_COLOR_PRIM_BT_2020,
            .transfer=PL_COLOR_TRC_LINEAR,.hdr={.min_luma=PL_COLOR_HDR_BLACK,
                .max_luma=nominal.hdr.max_luma,.prim=*bt2020}};
        pl_color_space_infer_map(&first_source,&first_target);
        const struct pl_gamut_map_function *first_function=color_map.gamut_mapping ?
            color_map.gamut_mapping : &pl_gamut_map_clip;
        struct pl_gamut_map_params first_gamut={.function=first_function,
            .input_gamut=first_source.hdr.prim,.output_gamut=first_target.hdr.prim};
        if(first_function->bidirectional &&
           pl_primaries_compatible(&first_gamut.input_gamut,&first_gamut.output_gamut))
            first_gamut.output_gamut=pl_primaries_clip(&first_gamut.output_gamut,
                                                       &first_gamut.input_gamut);
        /* Equal primaries can skip gamut mapping despite highlight compression. */
        reference.limit_untrimmed_volume=!creative.anchor_present && !use_cm4 &&
            nominal.primaries==PL_COLOR_PRIM_BT_2020 && pl_gamut_map_params_noop(&first_gamut);
        if(reference.limit_untrimmed_volume){
            reference.neutral_target=nominal;reference.final_mapper=color_map;
            reference.creative_gamut_state=&r->creative_gamut_state;
        }
        neutral_cm29=creative.status==DVBRIDGE_CREATIVE_READY &&
            (creative.backend==DVBRIDGE_CREATIVE_CM29 ||
             creative.backend==DVBRIDGE_CREATIVE_CM29_COMPATIBILITY) && creative.anchor_present &&
            creative.codes[0]==2048 && creative.codes[1]==2048 &&
            creative.codes[2]==2048 && creative.codes[4]==2048 &&
            mapped.color.primaries==PL_COLOR_PRIM_BT_2020 &&
            params.cb1_dovi_linear &&
            color_map.gamut_mode==PL_GAMUT_CLIP &&
            (color_map.intent==PL_INTENT_AUTO ||
             color_map.intent==PL_INTENT_PERCEPTUAL ||
             color_map.intent==PL_INTENT_RELATIVE_COLORIMETRIC) &&
            pl_gamut_map_params_noop(&first_gamut);
    }
    bool spatial=false;
    params.cb1_hook_color_space=use_cm4 || params.cb1_dovi_linear;
    if(policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT && (creative.anchor_present || use_cm4)){
        params.cb1_hook_color_space=true;
        reference.creative=true;reference.creative_plan=creative;
        reference.cm4=use_cm4;
        if(use_cm4){
            reference.cm4_coefficients=cm4;
            reference.detail_lut=r->creative_detail_lut;
            creative.backend=DVBRIDGE_CREATIVE_CM4;creative.status=DVBRIDGE_CREATIVE_READY;
            if(creative.l1_present)creative.reason=DVBRIDGE_CREATIVE_OK;
            creative.applied_levels&=~(1u<<2);creative.applied_levels|=1u<<8;
            creative.l2_coverage.applied=0;creative.l2_coverage.preserved=creative.l2_coverage.present;
            creative.l8_coverage.applied=cm4.present&~((1u<<5)|(3u<<8));
            creative.l8_coverage.preserved=cm4.present&~creative.l8_coverage.applied;
        }
        reference.creative_state=&r->creative_state;reference.creative_gamut_state=&r->creative_gamut_state;
        reference.creative_mapper=color_map;
        reference.creative_mapper.gamut_expansion=false;
        reference.neutral_cm29=neutral_cm29 && !use_cm4;
        reference.neutral_target=nominal;
        if(reference.neutral_cm29){
            /* Keep the P3 volume constraint, not a redundant P3 pixel carrier. */
            reference.neutral_target.primaries=target.color.primaries=PL_COLOR_PRIM_BT_2020;
            reference.to_xyz=pl_get_rgb2xyz_matrix(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
        }
        reference.creative_source=mapped.color;
        if(creative.l1_present){
            reference.creative_source.hdr.max_pq_y=creative.analysis[1]/4095.0f;
            reference.creative_source.hdr.avg_pq_y=creative.analysis[2]/4095.0f;
        }
        reference.creative_target=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,
            .transfer=PL_COLOR_TRC_LINEAR,.hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=nominal.hdr.max_luma,
                .prim=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020)}};
        if(use_cm4)reference.creative_target=nominal;
        if(use_cm4 && cm4.detail_mix!=0){
            struct pl_color_space from=reference.creative_source,to=reference.creative_target;
            pl_color_space_infer_map(&from,&to);
            float in_peak=0,out_peak=0;
            pl_color_space_nominal_luma_ex(pl_nominal_luma_params(.color=&from,
                .metadata=reference.creative_mapper.metadata,.scaling=PL_HDR_PQ,.out_max=&in_peak));
            pl_color_space_nominal_luma_ex(pl_nominal_luma_params(.color=&to,
                .metadata=PL_HDR_METADATA_HDR10,.scaling=PL_HDR_PQ,.out_max=&out_peak));
            spatial=in_peak>out_peak+1e-6f;
            if(spatial){creative.l8_coverage.applied|=1u<<5;creative.l8_coverage.preserved&=~(1u<<5);}
            else if(creative.l1_present)creative.reason=DVBRIDGE_CREATIVE_DETAIL_NO_COMPRESSION;
        }
        // The SCALED hook owns tone mapping. The remaining map only changes gamut.
        image.color.hdr=reference.creative_target.hdr;
        color_map.tone_mapping_function=&pl_tone_map_clip;color_map.metadata=PL_HDR_METADATA_HDR10;
        reference.final_mapper=color_map;
    }
    bool early_l5_black=policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT &&
        direct && direct->custom_quantize && params.cb1_dovi_linear && !spatial &&
        geometry.source_width==3840 && geometry.source_height==2160 &&
        !geometry.x && !geometry.y && geometry.width==3840 && geometry.height==2160 &&
        source->num_overlays==0 &&
        (!source->enhancement_layer || source->enhancement_layer->num_overlays==0) &&
        (policy_area[0]>0 || policy_area[1]>0 || policy_area[2]<3840 || policy_area[3]<2160);
    if(direct)
        direct->early_l5_black=early_l5_black;
    reference.quantize=direct && direct->custom_quantize ? &direct->quantize : NULL;
    reference.early_l5_black=early_l5_black;
    /* Retain dense mapping beyond the lattice's qualified 2500-nit range. */
    const bool cache_neutral=reference.neutral_cm29 && nominal.primaries!=PL_COLOR_PRIM_BT_2020 &&
        nominal.hdr.max_luma<=2500.0f;
    bool tail_scope=policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT &&
        cm29_tail_gain_eligible(creative.codes[4]) &&
        !use_cm4 && creative.status==DVBRIDGE_CREATIVE_READY &&
        creative.anchor_present &&
        (creative.backend==DVBRIDGE_CREATIVE_CM29 ||
         creative.backend==DVBRIDGE_CREATIVE_CM29_COMPATIBILITY) &&
        mapped.color.transfer==PL_COLOR_TRC_PQ &&
        mapped.color.primaries==PL_COLOR_PRIM_BT_2020 && params.cb1_dovi_linear &&
        ((paired && mapped.dovi.nlq_active) || cache_neutral) && direct && direct->custom_quantize && !overlay &&
        !source->num_overlays && (!el || !el->num_overlays) && !spatial &&
        geometry.source_width==3840 && geometry.source_height==2160 &&
        !geometry.x && !geometry.y && geometry.width==3840 && geometry.height==2160;
    if(tail_scope && cache_neutral)reference.neutral_cm29=false;
    reference.gpu_map_eligible=tail_scope && !reference.neutral_cm29;
    if(reference.gpu_map_eligible){
        const struct pl_raw_primaries *bt2020=pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020);
        reference.gpu_map_container=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,
            .transfer=PL_COLOR_TRC_PQ,.hdr={.prim=*bt2020,.min_luma=PL_COLOR_HDR_BLACK,
                .max_luma=nominal.hdr.max_luma}};
        target.color=reference.gpu_map_container;
    }
    if(policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT){
        pl_matrix3x3_mul(&reference.to_bt2020,&reference.to_xyz);
        reference.composed_matrix=true;
    }
    /* Public matrices are row-major; shader uniforms consume column-major. */
    for (int i=0;i<3;i++) for (int j=i+1;j<3;j++) {
        float v=reference.to_xyz.m[i][j];reference.to_xyz.m[i][j]=reference.to_xyz.m[j][i];reference.to_xyz.m[j][i]=v;
        v=reference.to_bt2020.m[i][j];reference.to_bt2020.m[i][j]=reference.to_bt2020.m[j][i];reference.to_bt2020.m[j][i]=v;
    }
    const struct pl_hook ref_hook = {.stages=PL_HOOK_SCALED|PL_HOOK_PRE_OUTPUT,
        .input=PL_HOOK_SIG_COLOR,.priv=&reference,.hook=reference_output,.signature=0x4342315245460001ULL};
    const struct pl_hook spatial_hook={.stages=PL_HOOK_SCALED,.input=PL_HOOK_SIG_TEX,
        .priv=&reference,.hook=cm4_spatial_output,.signature=0x434231434d340001ULL};
    struct pl_hook spatial_tail=ref_hook;spatial_tail.stages=PL_HOOK_PRE_OUTPUT;
    const struct pl_hook *ref_hooks[] = {spatial?&spatial_hook:&ref_hook,&spatial_tail};
    if (policy) {
        memcpy(reference.rect,policy_area,sizeof(policy_area));
        if(direct && direct->flip){
            reference.rect[1]=2160-policy_area[3];
            reference.rect[3]=2160-policy_area[1];
        }
        reference.enhanced=policy->mode==DVBRIDGE_MODE_ENHANCED_DV;
        if (reference.enhanced) {
            /* Decode immutable source hints with the pinned public API, divide
             * in binary64. This is a scene proxy, not measured luminance/FALL. */
            double maximum=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,mapped.color.hdr.max_pq_y);
            double average=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,mapped.color.hdr.avg_pq_y);
            if (!isfinite(maximum) || maximum<=0 || !isfinite(average)) return false;
            double x=fmax(0,fmin(1,(average/maximum-.1)/.4));
            reference.enhancement[0]=policy->tv.peak_nits/203.0;
            reference.enhancement[1]=.35f;
            reference.enhancement[2]=.08f;
            reference.enhancement[3]=1-.5*x*x*(3-2*x);
        }
        params.hooks=ref_hooks;
        params.num_hooks=spatial?2:1;
    }
    const struct pl_hook *direct_hooks[4];
    if (direct) {
        unsigned count=0;
        if(policy) {
            for(unsigned i=0;i<params.num_hooks;i++)direct_hooks[count++]=params.hooks[i];
        } else {
            direct_hooks[count++]=&hook;
        }
        if(direct->custom_quantize)direct_hooks[count++]=&direct->hook;
        params.hooks=direct_hooks;
        params.num_hooks=count;
    }
    if (!packed && (geometry.x || geometry.y || geometry.width != target.planes[0].texture->params.w ||
                    geometry.height != target.planes[0].texture->params.h)) {
        float black=direct?direct->quantize.offset/direct->quantize.maximum:0.0f;
        pl_tex_clear(r->gpu, target.planes[0].texture, (float[4]){black,black,black,1});
    }
    for(unsigned attempt=0;attempt<2;attempt++){
        r->ready=render_image(r,&image,&target,&params,&mask,policy?&reference:NULL,
            mask.source_domain && mask.early_mask);
        if(r->ready && direct && direct->custom_quantize)
            r->ready=direct->quantize.called && !direct->quantize.failed;
        bool early_l5_same_shader=direct && direct->quantize.scaled_shader &&
            direct->quantize.scaled_shader==direct->quantize.output_shader;
        if(r->ready && direct && direct->early_l5_black)
            r->ready=early_l5_same_shader;
        if(r->ready || attempt || !reference.gpu_map_eligible || pl_gpu_is_failed(r->gpu))
            break;
        /* Retry the dense map before publishing, retaining the same frame leases. */
        target.color=reference.neutral_target;
        reference.gpu_map_eligible=reference.gpu_map_used=false;
        if(cache_neutral)reference.neutral_cm29=true;
        reference.gpu_map_atlas=NULL;
        r->cm29_tail_key_valid=false;
        if(direct){
            direct->quantize.called=direct->quantize.failed=false;
            direct->quantize.scaled_shader=direct->quantize.output_shader=NULL;
        }
        pl_renderer_reset_errors(r->renderer,NULL);
    }
    if (!r->ready) {
        dvbridge_candidate_destroy(r->pending);
        r->pending = NULL;
    }
    if (r->ready && policy) {
        r->reconstructed_color = (struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
            .hdr={.prim=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020),.min_luma=PL_COLOR_HDR_BLACK,.max_luma=nominal.hdr.max_luma}};
        r->policy_pending = (struct dvbridge_hdr10_policy_output){.policy=*policy,.nominal_target=nominal,
            .container=r->reconstructed_color,.hdr10=signal,.geometry=geometry,.creative=creative,
            .fel_reconstructed=paired&&mapped.dovi.nlq_active};
        r->policy_ready = true;
    }
    if(r->ready && direct)r->direct_output=true;
    return r->ready;
}

static bool render(struct dvbridge_renderer *r, const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,
    struct dvbridge_geometry geometry,pl_tex packed,bool flip,
    const struct dvbridge_hdr10_session *session,const struct dvbridge_policy *policy,
    const struct dvbridge_native_overlay *overlay,bool force_refresh,
    struct direct_output *direct,bool enhanced_reconstruction,
    const struct pl_cb1_dovi_reference *master,bool p5_fast,const struct cb1_master_ipt *ipt)
{
    bool hdr10=session || (policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT);
    bool scaled=geometry.width!=geometry.source_width || geometry.height!=geometry.source_height;
    if(!hdr10 || !scaled || master || enhanced_reconstruction || (r && r->dv.active))
        return render_picture(r,source,metadata,bytes,pts,el_pts,geometry,packed,flip,
            session,policy,overlay,force_refresh,direct,enhanced_reconstruction,master,p5_fast,ipt,false);
    if(!r)return false;
    r->ready=r->direct_output=r->policy_ready=false;
    unsigned margins[4]={0};float area[4];
    if(!source || !dvbridge_metadata_bounds(metadata,bytes) ||
       !(policy?reference_area(area,metadata,geometry):dvbridge_frame_area(margins,metadata,bytes,geometry)) ||
       geometry.source_width<=0 || geometry.source_width>3840 ||
       geometry.source_height<=0 || geometry.source_height>2160)return false;
    pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,32,32,
        PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
    if(!fmt || !pl_tex_recreate(r->gpu,&r->native_picture,pl_tex_params(
        .w=geometry.source_width,.h=geometry.source_height,.format=fmt,
        .sampleable=true,.renderable=true)))return false;
    struct dvbridge_geometry native={geometry.source_width,geometry.source_height,0,0,
        geometry.source_width,geometry.source_height};
    if(!render_picture(r,source,metadata,bytes,pts,el_pts,native,NULL,false,
        session,policy,NULL,force_refresh,NULL,false,NULL,false,NULL,true))return false;
    struct pl_frame image={.num_planes=1,
        .planes={{.texture=r->native_picture,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color=r->reconstructed_color,
        .crop={0,0,geometry.source_width,geometry.source_height}};
    struct pl_frame target=image;
    target.planes[0].texture=direct?direct->texture:r->rgb;
    target.planes[0].flipped=direct && direct->flip;
    double sx=(double)geometry.source_width/geometry.width,sy=(double)geometry.source_height/geometry.height;
    image.crop=(pl_rect2df){-geometry.x*sx,-geometry.y*sy,
        (3840-geometry.x)*sx,(2160-geometry.y)*sy};
    target.crop=(pl_rect2df){0,0,3840,2160};
    if(direct && !direct->custom_quantize){
        target.repr.levels=direct->limited?PL_COLOR_LEVELS_LIMITED:PL_COLOR_LEVELS_FULL;
        target.repr.bits.sample_depth=target.repr.bits.color_depth=direct->bits;
    }
    struct active_mask mask={.rect={margins[0],margins[2],3840-margins[1],2160-margins[3]}};
    if(policy)memcpy(mask.rect,area,sizeof(area));
    mask.maximum_pq=dv_ideal_pq(policy?r->policy_pending.nominal_target.hdr.max_luma:session->target.hdr.max_luma);
    if(direct && direct->flip){float top=mask.rect[1];mask.rect[1]=2160-mask.rect[3];mask.rect[3]=2160-top;}
    const struct pl_hook blank={.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&mask,.hook=mask_active_area,.signature=0x4342314853430001ULL};
    const struct pl_hook *hooks[]={&blank,direct?&direct->hook:NULL};
    struct pl_render_params params=pl_render_default_params;
    params.min_fbo_precision=32;params.peak_detect_params=NULL;
    params.dither_params=direct && !direct->custom_quantize?&pl_dither_default_params:NULL;
    params.frame_mixer=NULL;params.sigmoid_params=NULL;params.cb1_nearest_identity=true;
    params.cb1_stable_pq=true;
    params.cb1_fp32_scaler_lut=policy!=NULL;params.hooks=hooks;
    params.num_hooks=direct && direct->custom_quantize?2:1;
    if(!p5_preserve_backing(r))return false;
    r->ready=render_image(r,&image,&target,&params,&mask,NULL,false);
    if(direct && direct->custom_quantize)
        r->ready=r->ready && direct->quantize.called && !direct->quantize.failed;
    r->direct_output=r->ready && direct;
    if(policy){r->policy_pending.geometry=geometry;r->policy_ready=r->ready;}
    return r->ready;
}

bool dvbridge_render_rgb(struct dvbridge_renderer *r, const struct pl_frame *source,
                        const void *metadata, size_t bytes, double pts, double el_pts,
                        struct dvbridge_geometry geometry)
{
    return render(r, source, metadata, bytes, pts, el_pts, geometry, NULL, false, NULL, NULL, NULL,false,NULL,false,NULL,false,NULL);
}

bool dvbridge_render_hdr10_rgb(struct dvbridge_renderer *r,
                              const struct dvbridge_hdr10_session *session,
                              const struct pl_frame *source,
                              const void *metadata, size_t bytes, double pts, double el_pts,
                              struct dvbridge_geometry geometry)
{
    if (!session) {
        dvbridge_renderer_reset(r);
        return false;
    }
    return render(r, source, metadata, bytes, pts, el_pts, geometry, NULL, false, session, NULL, NULL,false,NULL,false,NULL,false,NULL);
}

bool dvbridge_render_packed(struct dvbridge_renderer *r, const struct pl_frame *source,
                           const void *metadata, size_t bytes, double pts, double el_pts,
                           struct dvbridge_geometry geometry, pl_tex target, bool flip)
{
    return dvbridge_render_packed_overlay(r,source,metadata,bytes,pts,el_pts,geometry,target,flip,NULL);
}

static bool packed_transport_supported(const struct dvbridge_renderer *r,pl_tex target,bool reference)
{
    if(!r || !target || (!reference && !r->fragment_quad) || target->params.w!=3840 || target->params.h!=2160 ||
       !target->params.renderable || target->params.format->type!=PL_FMT_UNORM ||
       target->params.format->num_components!=4)return false;
    for(int c=0;c<4;c++)if(target->params.format->component_depth[c]!=8)return false;
    return true;
}

static bool overlay_valid(const struct dvbridge_native_overlay *overlay)
{
    if(!overlay)return true;
    if(!overlay->texture || !overlay->texture->params.sampleable || !overlay->degamma ||
       !overlay->pq || !overlay->degamma->params.sampleable || !overlay->pq->params.sampleable ||
       overlay->texture->params.w!=3840 || overlay->texture->params.h!=2160)return false;
    /* libplacebo requires distinct sampled objects in one dispatch. */
    if(overlay->texture==overlay->degamma || overlay->texture==overlay->pq ||
       overlay->degamma==overlay->pq)return false;
    for(int i=0;i<4;i++)if(!isfinite(overlay->rect[i]))return false;
    return overlay->rect[0]>=0 && overlay->rect[1]>=0 && overlay->rect[2]<=3840 &&
        overlay->rect[3]<=2160 && overlay->rect[0]<=overlay->rect[2] &&
        overlay->rect[1]<=overlay->rect[3] && !fmodf(overlay->rect[0],2) && !fmodf(overlay->rect[2],2);
}

static bool render_packed_overlay(struct dvbridge_renderer *r,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry,
    pl_tex target,bool flip,const struct dvbridge_native_overlay *overlay,bool force_refresh,
    const struct pl_cb1_dovi_reference *master,bool p5_fast,const struct cb1_master_ipt *ipt)
{
    if (r && r->dv.active)
        dvbridge_render_dv_policy_cancel(r);
    if (r)
        r->ready = false;
    if (!r || !source || !packed_transport_supported(r,target,master!=NULL) ||
        source->num_overlays || (source->enhancement_layer && source->enhancement_layer->num_overlays))
        return false;
    if(!overlay_valid(overlay))return false;
    // Transport bytes must not inherit GUI blending, dithering or write masks.
    // libplacebo owns viewport/scissor while rendering; preserve the caller's
    // enable state, just as the separate transport packer does.
    if (glGetError() != GL_NO_ERROR)
        return false;
    const GLenum caps[] = {GL_BLEND, GL_DEPTH_TEST, GL_STENCIL_TEST, GL_SCISSOR_TEST,
        GL_DITHER, GL_CULL_FACE, GL_RASTERIZER_DISCARD, GL_SAMPLE_ALPHA_TO_COVERAGE,
        GL_SAMPLE_COVERAGE};
    GLboolean enabled[sizeof(caps)/sizeof(*caps)], mask[4];
    glGetBooleanv(GL_COLOR_WRITEMASK, mask);
    for (unsigned i=0; i<sizeof(caps)/sizeof(*caps); ++i) {
        enabled[i] = glIsEnabled(caps[i]);
        glDisable(caps[i]);
    }
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    bool ok = render(r, source, metadata, bytes, pts, el_pts, geometry, target, flip, NULL, NULL, overlay,force_refresh,NULL,false,master,p5_fast,ipt);
    ok = glGetError() == GL_NO_ERROR && ok;
    glColorMask(mask[0], mask[1], mask[2], mask[3]);
    for (unsigned i=0; i<sizeof(caps)/sizeof(*caps); ++i) {
        if (enabled[i]) glEnable(caps[i]);
        else glDisable(caps[i]);
    }
    r->ready = ok && glGetError() == GL_NO_ERROR;
    return r->ready;
}

static int master_chroma_phase(const struct pl_frame *source);

bool dvbridge_render_packed_overlay(struct dvbridge_renderer *r,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry,
    pl_tex target,bool flip,const struct dvbridge_native_overlay *overlay)
{
    struct pl_cb1_dovi_reference raw;
    unsigned margins[4];
    /* Only Standard P5 admits the approximate IPT recipe. Master never inherits Fast. */
    if(r && source && r->optimized_dv && master_chroma_phase(source)==0 &&
       pl_cb1_dovi_reference_frame_supported(source,10) &&
       cb1_master_reference_transport(metadata,bytes) && dvbridge_dv_profile5_transport(metadata) &&
       cb1_master_reference_map(&raw,metadata,bytes,false)==CB1_MASTER_READY &&
       raw.bl_depth==10 && raw.output_depth==12 && !raw.residual &&
       dvbridge_frame_area(margins,metadata,bytes,geometry) && !(margins[0]&1) && !(margins[1]&1) &&
       pl_find_fmt(r->gpu,PL_FMT_UNORM,2,16,16,
                   PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR) &&
       dvbridge_renderer_supports_mode(r,DVBRIDGE_MODE_MASTER_REFERENCE))
        return render_packed_overlay(r,source,metadata,bytes,pts,el_pts,geometry,target,flip,overlay,false,&raw,true,NULL);
    return render_packed_overlay(r,source,metadata,bytes,pts,el_pts,geometry,target,flip,overlay,false,NULL,false,NULL);
}

static int master_chroma_phase(const struct pl_frame *source)
{
    if(!source || source->num_planes<2 || source->num_planes>3)return -1;
    int phase=-1;
    for(int p=0;p<source->num_planes;p++){
        const struct pl_plane *plane=&source->planes[p];
        if(plane->components<1 || plane->components>4)return -1;
        for(int c=0;c<plane->components;c++)if(plane->component_mapping[c]>0){
            if(plane->shift_x!=-.5f || (plane->shift_y!=0 && plane->shift_y!=-.5f))return -1;
            int current=plane->shift_y==-.5f;
            if(phase>=0 && phase!=current)return -1;
            phase=current;
        }
    }
    return phase;
}

static enum cb1_master_status render_master_reference(struct dvbridge_renderer *r,
    const struct pl_frame *source,const void *metadata,size_t bytes,double pts,double el_pts,
    struct dvbridge_geometry geometry,pl_tex target,bool flip,
    const struct dvbridge_native_overlay *overlay,bool ipt_output)
{
    if(r)r->ready=false;
    if(!r || !source)return CB1_MASTER_INVALID;
    struct pl_cb1_dovi_reference raw;
    enum cb1_master_status status=cb1_master_reference_map(&raw,metadata,bytes,
        source->enhancement_layer && isfinite(pts) && pts==el_pts);
    if(status!=CB1_MASTER_READY)return status;
    const int phase=master_chroma_phase(source);
    if(raw.residual){
        const struct pl_frame *el=source->enhancement_layer;
        const int scale=av_dovi_get_header((const AVDOVIMetadata*)metadata)->el_spatial_resampling_filter_flag?2:1;
        if(el->crop.x1*scale!=source->crop.x1 || el->crop.y1*scale!=source->crop.y1)return CB1_MASTER_UNSUPPORTED;
    }
    /* A colour-converted intermediate is not an exact source-domain carrier. */
    if(!target || !cb1_master_reference_transport(metadata,bytes) || phase<0 ||
       (raw.residual && phase!=master_chroma_phase(source->enhancement_layer)))return CB1_MASTER_UNSUPPORTED;
    if(!dvbridge_renderer_supports_mode(r,DVBRIDGE_MODE_MASTER_REFERENCE))return CB1_MASTER_GPU_UNAVAILABLE;
    /* Paired rows preserve the integer result and avoid duplicate reconstruction. */
    raw.contract=2;
    /* Profile5 is already IPT: both Master preferences retain its direct path. */
    ipt_output=ipt_output && !dvbridge_dv_profile5_transport(metadata);
    struct cb1_master_ipt ipt;
    if(ipt_output && !cb1_master_ipt_prepare(&ipt,metadata,bytes))return CB1_MASTER_UNSUPPORTED;
    if(ipt_output && !cb1_master_ipt_tables(r->gpu,r->ipt_pq,r->master_ipt_compact))return CB1_MASTER_GPU_UNAVAILABLE;
    return render_packed_overlay(r,source,metadata,bytes,pts,el_pts,geometry,target,flip,overlay,false,&raw,false,ipt_output?&ipt:NULL)?
        CB1_MASTER_READY:CB1_MASTER_FAILED;
}

enum cb1_master_status dvbridge_render_master_reference(struct dvbridge_renderer *r,
    const struct pl_frame *source,const void *metadata,size_t bytes,double pts,double el_pts,
    struct dvbridge_geometry geometry,pl_tex target,bool flip,
    const struct dvbridge_native_overlay *overlay)
{
    return render_master_reference(r,source,metadata,bytes,pts,el_pts,geometry,target,flip,overlay,false);
}

enum cb1_master_status dvbridge_render_master_reference_ipt(struct dvbridge_renderer *r,
    const struct pl_frame *source,const void *metadata,size_t bytes,double pts,double el_pts,
    struct dvbridge_geometry geometry,pl_tex target,bool flip,
    const struct dvbridge_native_overlay *overlay)
{
    return render_master_reference(r,source,metadata,bytes,pts,el_pts,geometry,target,flip,overlay,true);
}

pl_tex dvbridge_render_texture(const struct dvbridge_renderer *r)
{
    if(r && r->dv.active && (r->dv.ai_direct_lean || r->enhanced_skip_aux) && !r->dv.output.intermediate)return NULL;
    return r && r->ready && !r->packed && !r->direct_output ?
        (r->dv.active && r->dv.output.intermediate ? r->dv.output.intermediate : r->rgb) : NULL;
}

bool dvbridge_render_hdr10(struct dvbridge_renderer *r, pl_tex output,
                          bool flip, bool limited, unsigned bits)
{
    if (r && (r->policy_ready || r->dv.active || r->direct_output)) return false;
    if (!r || !r->ready || r->packed || !output || bits < 10 || bits > 16 ||
        output->params.w != 3840 || output->params.h != 2160) {
        if (r) r->ready = false;
        return false;
    }
    struct pl_frame source = {
        .num_planes = 1,
        .planes = {{.texture = r->rgb, .components = 4, .component_mapping = {0, 1, 2, 3}}},
        .repr = pl_color_repr_rgb,
        .color = r->reconstructed_color,
    };
    struct pl_frame target = source;
    target.planes[0].texture = output;
    target.planes[0].flipped = flip;
    target.repr.levels = limited ? PL_COLOR_LEVELS_LIMITED : PL_COLOR_LEVELS_FULL;
    target.repr.bits.sample_depth = bits;
    target.repr.bits.color_depth = bits;
    struct pl_render_params params = pl_render_default_params;
    params.min_fbo_precision = 32;
    params.peak_detect_params = NULL;
    params.frame_mixer = NULL;
    params.skip_caching_single_frame = true;
    params.dither_params = &pl_dither_default_params;
    // Identical source/target color spaces preserve absolute PQ luminance.
    // Only output quantization and the selected signal range change here.
    bool ok = pl_render_image(r->renderer, &source, &target, &params);
    struct pl_render_errors errors = pl_renderer_get_errors(r->renderer);
    r->ready = ok && !errors.errors && !errors.num_disabled_hooks;
    return r->ready;
}

const struct dvbridge_candidate *dvbridge_render_candidate(const struct dvbridge_renderer *r)
{
    return r && r->ready ? r->pending : NULL;
}

bool dvbridge_render_commit(struct dvbridge_renderer *r)
{
    if (!r || !r->ready || r->policy_ready || r->dv.active)
        return false;
    bool ok = !r->pending || dvbridge_commit(r->context, r->pending);
    if (ok) r->ready = r->direct_output = false;
    return ok;
}

void dvbridge_render_policy_cancel(struct dvbridge_renderer *r)
{
    if (!r) return;
    if (r->dv.active) dvbridge_render_dv_policy_cancel(r);
    r->policy_ready = r->ready = r->direct_output = false;
    memset(&r->policy_pending, 0, sizeof(r->policy_pending));
}

bool dvbridge_render_hdr10_policy_rgb(struct dvbridge_renderer *r,
    const struct dvbridge_policy *policy, const struct dvbridge_identity *identity,
    const struct pl_frame *source, const void *metadata, size_t bytes,
    double pts, double el_pts, struct dvbridge_geometry geometry)
{
    dvbridge_render_policy_cancel(r);
    if (!r || !identity || !policy || policy->mode==DVBRIDGE_MODE_ENHANCED_DV || identity->revision != policy->revision ||
        !isfinite(pts) || !isfinite(el_pts) || !source || source->num_overlays ||
        (source->enhancement_layer && source->enhancement_layer->num_overlays) ||
        !pl_find_fmt(r->gpu, PL_FMT_UNORM, 4, 16, 16, PL_FMT_CAP_LINEAR) ||
        !pl_find_fmt(r->gpu, PL_FMT_FLOAT, 1, 32, 32, PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR))
        return false;
    if (!render(r, source, metadata, bytes, pts, el_pts, geometry, NULL, false, NULL, policy, NULL,false,NULL,false,NULL,false,NULL))
        return false;
    r->policy_pending.identity = *identity;
    return true;
}

static bool direct_target_valid(struct dvbridge_renderer *r,pl_tex target,unsigned bits)
{
    if(!r || !target || bits<10 || bits>16 || target==r->rgb ||
       target->params.w!=3840 || target->params.h!=2160 || !target->params.renderable ||
       !target->params.format || target->params.format->num_components<3)return false;
    pl_fmt fmt=target->params.format;
    for(int c=0;c<3;c++)
        if(!((fmt->type==PL_FMT_UNORM && fmt->component_depth[c]>=(int)bits) ||
             (fmt->type==PL_FMT_FLOAT && fmt->component_depth[c]>=32)))return false;
    return true;
}

static bool direct_geometry_valid(struct dvbridge_geometry geometry)
{
    return geometry.x==0 && geometry.y==0 &&
        geometry.width==3840 && geometry.height==2160;
}

static void direct_target_init(struct direct_output *direct,pl_tex target,bool flip,
                               bool limited,unsigned bits,bool custom_quantize)
{
    *direct=(struct direct_output){.texture=target,.flip=flip,.custom_quantize=custom_quantize,
        .limited=limited,.bits=bits,
        .quantize={.span=limited?219u*(1u<<(bits-8)):(1u<<bits)-1,
            .offset=limited?16u*(1u<<(bits-8)):0,.maximum=(1u<<bits)-1}};
    direct->hook=(struct pl_hook){.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&direct->quantize,.hook=reference_quantize,.signature=0x4342315245530001ULL};
}

bool dvbridge_render_hdr10_direct(struct dvbridge_renderer *r,
    const struct dvbridge_hdr10_session *session,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,
    struct dvbridge_geometry geometry,pl_tex target,bool flip,bool limited,unsigned bits)
{
    dvbridge_render_policy_cancel(r);
    if(!r || !session || !isfinite(pts) || !source ||
       (source->enhancement_layer && !isfinite(el_pts)) ||
       source->num_overlays || (source->enhancement_layer && source->enhancement_layer->num_overlays) ||
       !direct_geometry_valid(geometry) || !direct_target_valid(r,target,bits))return false;
    struct direct_output direct;
    direct_target_init(&direct,target,flip,limited,bits,false);
    return render(r,source,metadata,bytes,pts,el_pts,geometry,NULL,false,session,NULL,NULL,false,&direct,false,NULL,false,NULL);
}

bool dvbridge_render_hdr10_policy_direct(struct dvbridge_renderer *r,
    const struct dvbridge_policy *policy,const struct dvbridge_identity *identity,
    const struct pl_frame *source,const void *metadata,size_t bytes,double pts,double el_pts,
    struct dvbridge_geometry geometry,pl_tex target,bool flip,bool limited,unsigned bits)
{
    dvbridge_render_policy_cancel(r);
    if(!r || !identity || !policy ||
       policy->mode!=DVBRIDGE_MODE_HDR10_EXPERT ||
       identity->revision!=policy->revision || !isfinite(pts) || !source ||
       (source->enhancement_layer && !isfinite(el_pts)) ||
       source->num_overlays || (source->enhancement_layer && source->enhancement_layer->num_overlays) ||
       !pl_find_fmt(r->gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_LINEAR) ||
       !pl_find_fmt(r->gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR) ||
       !direct_geometry_valid(geometry) || !direct_target_valid(r,target,bits))return false;
    struct direct_output direct;
    direct_target_init(&direct,target,flip,limited,bits,true);
    if(!render(r,source,metadata,bytes,pts,el_pts,geometry,NULL,false,NULL,policy,NULL,false,&direct,false,NULL,false,NULL))return false;
    r->policy_pending.identity=*identity;
    r->policy_pending.resolved=true;
    r->policy_pending.final_target=target;
    return true;
}

const struct dvbridge_hdr10_policy_output *dvbridge_render_policy_output(const struct dvbridge_renderer *r)
{
    return r && r->policy_ready && r->ready ? &r->policy_pending : NULL;
}

static struct pl_hook_res reference_quantize(void *priv, const struct pl_hook_params *p)
{
    struct reference_resolve *q = priv;
    q->called = true;
    q->output_shader = p->sh;
    struct pl_shader_var vars[] = {
        {.var=pl_var_float("reference_span"),.data=&q->span,.dynamic=true},
        {.var=pl_var_float("reference_offset"),.data=&q->offset,.dynamic=true},
        {.var=pl_var_float("reference_maximum"),.data=&q->maximum,.dynamic=true}};
    struct pl_custom_shader shader = {.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .variables=vars,.num_variables=3,.description="Expert range and integer quantization only",
        .body="color.rgb=floor(reference_offset+reference_span*clamp(color.rgb,0.0,1.0)+0.5)/reference_maximum;\n"};
    q->failed = p->stage != PL_HOOK_OUTPUT || !pl_shader_custom(p->sh,&shader);
    return (struct pl_hook_res){.failed=q->failed,.output=PL_HOOK_SIG_NONE};
}

bool dvbridge_render_hdr10_policy_resolve(struct dvbridge_renderer *r, pl_tex output,
                                         bool flip, bool limited, unsigned bits)
{
    if (!r || !r->policy_ready || !r->ready || !direct_target_valid(r,output,bits)) {
        dvbridge_render_policy_cancel(r); return false;
    }
    struct pl_frame source = {.num_planes=1,
        .planes={{.texture=r->rgb,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color=r->reconstructed_color};
    struct pl_frame target = source; target.planes[0].texture=output; target.planes[0].flipped=flip;
    struct pl_render_params params = pl_render_default_params;
    params.min_fbo_precision=32; params.peak_detect_params=NULL; params.frame_mixer=NULL;
    params.dither_params=NULL; params.skip_caching_single_frame=true;
    params.cb1_nearest_identity=true;
    struct reference_resolve q = {.span=limited?219u*(1u<<(bits-8)):(1u<<bits)-1,
        .offset=limited?16u*(1u<<(bits-8)):0,.maximum=(1u<<bits)-1};
    const struct pl_hook hook={.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&q,.hook=reference_quantize,.signature=0x4342315245530001ULL};
    const struct pl_hook *hooks[]={&hook}; params.hooks=hooks; params.num_hooks=1;
    bool ok=pl_render_image(r->renderer,&source,&target,&params);
    struct pl_render_errors errors=pl_renderer_get_errors(r->renderer);
    if (!ok || !q.called || q.failed || errors.errors || errors.num_disabled_hooks) {
        dvbridge_render_policy_cancel(r); return false;
    }
    r->policy_pending.resolved=true; r->policy_pending.final_target=output;
    return true;
}

bool dvbridge_render_policy_commit(struct dvbridge_renderer *r,
    const struct dvbridge_identity *identity, pl_tex target)
{
    if (!r || !r->policy_ready || !r->ready || !r->policy_pending.resolved ||
        !target || target != r->policy_pending.final_target ||
        !dvbridge_identity_equal(identity,&r->policy_pending.identity)) return false;
    r->policy_committed=r->policy_pending; r->policy_has_committed=true;
    dvbridge_render_policy_cancel(r);
    return true;
}

bool dvbridge_render_policy_committed(const struct dvbridge_renderer *r,
                                      struct dvbridge_hdr10_policy_output *snapshot)
{
    if (!r || !snapshot || !r->policy_has_committed) return false;
    *snapshot=r->policy_committed; return true;
}


#ifdef CB1_TEST_LEGACY_ANALYSIS
/* Historical test oracle. 128-lane reduction; counts carry an invalid-input
 * bit, while the fixed48-byte record has a separate flag. */
static const char dv_analysis_shader[] =
    "#version 310 es\nprecision highp float;precision highp int;\n"
    "layout(local_size_x=128)in;\n"
    "layout(binding=0)uniform highp sampler2D video;\n"
    "layout(std430,binding=0)readonly buffer Input{uvec4 input_part[];};\n"
    "layout(std430,binding=1)writeonly buffer Output{uvec4 output_part[];};\n"
    "layout(std430,binding=2)coherent buffer Scalar{uint scalar[12];};\n"
    "uniform uvec4 area;uniform uint count;uniform uint pass;uniform uint final_pass;\n"
    "uniform uvec2 stream_id,picture_id,revision_id;\n"
    "shared vec3 values[128];shared uint counts[128];\n"
    "float decode_pq(float q){if(q<=0.0)return 0.0;float z=log(q)/78.84375,y=z/16.0;"
    "float d=-y*(1.0+y*(0.5+y*(1.0/6.0+y*(1.0/24.0+y/120.0))));"
    "for(int i=0;i<4;i++)d=d*(2.0-d);"
    "return pow(max(0.1640625-d,0.0)/(0.1640625+18.6875*d),1.0/0.1593017578125);}\n"
    "float encode_pq(float n){if(n<=0.0)return 0.0;float v=pow(n,0.1593017578125);"
    "float d=0.1640625*(1.0-v)/(1.0+18.6875*v),t=d/(2.0-d),t2=t*t;"
    "float logarithm=-2.0*t*(1.0+t2*(1.0/3.0+t2*(1.0/5.0+t2*(1.0/7.0+t2/9.0))));"
    "return exp(78.84375*logarithm);}\n"
    "void main(){uint lane=gl_LocalInvocationID.x,index=gl_GlobalInvocationID.x;"
    "vec3 value=vec3(uintBitsToFloat(0x7f800000u),0.0,uintBitsToFloat(0xff800000u));uint n=0u;"
    "if(index<count){if(pass==0u){uint width=(area.z-area.x+1u)/2u;"
    "uvec2 origin=area.xy+2u*uvec2(index%width,index/width);vec3 sum=vec3(0.0);uint pixels=0u,bad=0u;"
    "for(uint y=0u;y<2u;y++)for(uint x=0u;x<2u;x++){uvec2 p=origin+uvec2(x,y);"
    "if(p.x>=area.z||p.y>=area.w)continue;vec3 q=texelFetch(video,ivec2(p),0).rgb;"
    "if(any(isnan(q))||any(isinf(q))||any(lessThan(q,vec3(0.0)))||any(greaterThan(q,vec3(1.0))))bad=0x80000000u;"
    "else sum+=vec3(decode_pq(q.r),decode_pq(q.g),decode_pq(q.b));pixels++;}"
    "float sample_pq=encode_pq(max(sum.r,max(sum.g,sum.b))/float(pixels));"
    "if(isnan(sample_pq)||isinf(sample_pq)||sample_pq<0.0||sample_pq>1.0)bad=0x80000000u;"
    "value=vec3(sample_pq);n=1u|bad;"
    "}else{uvec4 partial=input_part[index];value=uintBitsToFloat(partial.xyz);n=partial.w;}}"
    "values[lane]=value;counts[lane]=n;barrier();"
    "for(uint stride=1u;stride<128u;stride*=2u){uint left=lane*stride*2u;"
    "if(left<128u){vec3 a=values[left],b=values[left+stride];values[left]=vec3(min(a.x,b.x),a.y+b.y,max(a.z,b.z));"
    "uint na=counts[left],nb=counts[left+stride];counts[left]=((na&0x7fffffffu)+(nb&0x7fffffffu))|((na|nb)&0x80000000u);}barrier();}"
    "if(lane==0u){uvec3 bits=floatBitsToUint(values[0]);uint groups=counts[0]&0x7fffffffu;"
    "if(final_pass==0u)output_part[gl_WorkGroupID.x]=uvec4(bits,counts[0]);"
    "else{scalar[0]=bits.x;scalar[1]=bits.y;scalar[2]=bits.z;scalar[3]=groups;"
    "scalar[4]=stream_id.x;scalar[5]=stream_id.y;scalar[6]=picture_id.x;scalar[7]=picture_id.y;"
    "scalar[8]=revision_id.x;scalar[9]=revision_id.y;scalar[10]=(counts[0]&0x80000000u)==0u?1u:0u;scalar[11]=0u;}}}\n";

static GLuint dv_compute_program(void)
{
    GLuint shader=glCreateShader(GL_COMPUTE_SHADER);if(!shader)return 0;
    const char *text=dv_analysis_shader;glShaderSource(shader,1,&text,NULL);glCompileShader(shader);
    GLint ok;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
    if(!ok){char log[4096];glGetShaderInfoLog(shader,sizeof(log),NULL,log);
        fprintf(stderr,"DV analysis shader: %s\n",log);glDeleteShader(shader);return 0;}
    GLuint program=glCreateProgram();glAttachShader(program,shader);glLinkProgram(program);glDeleteShader(shader);
    glGetProgramiv(program,GL_LINK_STATUS,&ok);
    if(!ok){glDeleteProgram(program);return 0;}return program;
}

#endif

static void dv_delete_storage(GLuint buffers[3],GLuint sampler,const void *mapped)
{
    if(mapped){GLint previous;glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&previous);
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,buffers[2]);glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,previous);}
    glDeleteBuffers(3,buffers);
    glDeleteSamplers(1,&sampler);
}
static void dv_release_slot(struct dvbridge_dv_slot *s)
{
    if(s->fence)s->delete_sync(s->fence);
    if(!s->borrowed_storage)dv_delete_storage(s->buffers,s->sampler,s->mapped);
    av_free(s->source_metadata);
    /* Borrowed analysis storage survives; transaction metadata never does. */
    av_free(s->output_metadata);
    memset(s,0,sizeof(*s));
}
static void dv_release(struct dvbridge_renderer *r) { dv_release_slot(&r->dv); }

static enum dvbridge_dv_policy_status dv_retire_slot(struct dvbridge_dv_slot *s)
{
    if(s->quarantined)return DVBRIDGE_DV_FAILED;
    if(!s->active)return DVBRIDGE_DV_IDLE;
    if(s->fence){GLenum result=s->wait_sync(s->fence,0,0);
        if(result==GL_TIMEOUT_EXPIRED)return DVBRIDGE_DV_BUSY;
        if(result!=GL_ALREADY_SIGNALED && result!=GL_CONDITION_SATISFIED){s->quarantined=true;return DVBRIDGE_DV_FAILED;}}
    dv_release_slot(s);return DVBRIDGE_DV_IDLE;
}
static enum dvbridge_dv_policy_status dv_retire(struct dvbridge_renderer *r)
{
    enum dvbridge_dv_policy_status status=dv_retire_slot(&r->retired_packed);
    return status==DVBRIDGE_DV_IDLE?dv_retire_slot(&r->dv):status;
}

enum dvbridge_dv_policy_status dvbridge_render_dv_policy_advance(struct dvbridge_renderer *r)
{
    if(!r)return DVBRIDGE_DV_FAILED;
    enum dvbridge_dv_policy_status status=dv_retire_slot(&r->retired_packed);
    if(status!=DVBRIDGE_DV_IDLE)return status;
    struct dvbridge_dv_slot *s=&r->dv;
    bool authored=s->ordered_handoff && s->borrowed_storage && !s->ai_source && !s->source_metadata;
    if(!s->retiring || (!s->packed_target && !authored) ||
       (!authored && (s->mapped || s->source_metadata ||
        s->buffers[0] || s->buffers[1] || s->buffers[2] || s->sampler)))
        return dvbridge_render_dv_policy_poll(r);
    status=dv_retire_slot(s);
    if(status!=DVBRIDGE_DV_BUSY)return status;
    if(authored){
        /* The committed resolve no longer reads analysis storage. Order its
         * remaining image reads before the next reconstruction/compute write. */
        glMemoryBarrier(GL_SHADER_IMAGE_ACCESS_BARRIER_BIT|GL_FRAMEBUFFER_BARRIER_BIT|GL_TEXTURE_FETCH_BARRIER_BIT);
        if(glGetError()!=GL_NO_ERROR){s->quarantined=true;return DVBRIDGE_DV_FAILED;}
        memset(s->buffers,0,sizeof(s->buffers));s->mapped=NULL;s->sampler=0;s->borrowed_storage=false;
    }
    r->retired_packed=*s;
    memset(s,0,sizeof(*s));
    return DVBRIDGE_DV_IDLE;
}

struct dvbridge_retirement_owner *dvbridge_retirement_owner_create(pl_gpu gpu)
{
    if(!gpu || !pl_opengl_get(gpu))return NULL;
    struct dvbridge_retirement_owner *owner=calloc(1,sizeof(*owner));if(owner)owner->gpu=gpu;return owner;
}
struct dvbridge_renderer *dvbridge_renderer_create_with_owner(struct dvbridge_retirement_owner *owner)
{
    if(!owner || owner->attached || owner->lease)return NULL;
    struct dvbridge_renderer *r=dvbridge_renderer_create(owner->gpu);
    if(r){r->owner=owner;owner->attached=r;}return r;
}
enum dvbridge_dv_policy_status dvbridge_retirement_owner_poll(struct dvbridge_retirement_owner *owner)
{
    if(!owner)return DVBRIDGE_DV_FAILED;
    if(!owner->lease)return DVBRIDGE_DV_IDLE;
    enum dvbridge_dv_policy_status status=dv_retire(owner->lease);
    if(status==DVBRIDGE_DV_IDLE){renderer_free(owner->lease);owner->lease=NULL;}
    return status;
}
bool dvbridge_retirement_owner_destroy(struct dvbridge_retirement_owner **owner)
{
    if(!owner || !*owner)return true;
    if((*owner)->attached || (*owner)->lease)return false;
    free(*owner);*owner=NULL;return true;
}

static bool dv_gpu_requirements(pl_gpu gpu)
{
    pl_opengl gl=pl_opengl_get(gpu);
    const char *version=(const char *)glGetString(GL_VERSION);
    if(!gl || !version || strncmp(version,"OpenGL ES ",10) ||
       gl->major<3 || (gl->major==3 && gl->minor<1) ||
       !pl_opengl_has_ext(gl,"GL_EXT_buffer_storage"))return false;
    GLint precision,range[2],size,groups,invocations,bindings;GLint64 storage;
    for(unsigned i=0;i<2;i++){
        glGetShaderPrecisionFormat(i?GL_FRAGMENT_SHADER:GL_VERTEX_SHADER,GL_HIGH_FLOAT,range,&precision);
        if(precision<23 || range[0]<127 || range[1]<127)return false;}
    glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,&invocations);
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_SIZE,0,&size);
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT,0,&groups);
    glGetIntegerv(GL_MAX_SHADER_STORAGE_BUFFER_BINDINGS,&bindings);
    glGetInteger64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE,&storage);
    if(invocations<128 || size<128 || groups<16200 || bindings<3 || storage<259200 || glGetError()!=GL_NO_ERROR)return false;
    return eglGetProcAddress("glBufferStorageEXT") && eglGetProcAddress("glClientWaitSync") &&
           eglGetProcAddress("glDeleteSync") && eglGetProcAddress("glFenceSync") &&
           eglGetProcAddress("glMapBufferRange") && eglGetProcAddress("glDispatchCompute") &&
           eglGetProcAddress("glMemoryBarrier");
}

static bool dv_transport_requirements(pl_gpu gpu)
{
    pl_opengl gl=pl_opengl_get(gpu);
    const char *version=(const char *)glGetString(GL_VERSION);
    if(!gl || !version || strncmp(version,"OpenGL ES ",10) || gl->major<3)return false;
    GLint precision,range[2];
    glGetShaderPrecisionFormat(GL_FRAGMENT_SHADER,GL_HIGH_FLOAT,range,&precision);
    return precision>=23 && range[0]>=127 && range[1]>=127 && glGetError()==GL_NO_ERROR &&
        eglGetProcAddress("glClientWaitSync") && eglGetProcAddress("glDeleteSync") &&
        eglGetProcAddress("glFenceSync");
}

bool dvbridge_renderer_supports_mode(struct dvbridge_renderer *r,enum dvbridge_mode mode)
{
    if(!r || mode<=DVBRIDGE_MODE_DISABLED || mode>=DVBRIDGE_MODE_COUNT ||
       !r->gpu || !r->renderer ||
       !pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE))return false;
    if(mode==DVBRIDGE_MODE_MASTER_REFERENCE)
        return r->gpu->glsl.version >= (r->gpu->glsl.gles?310:400) &&
            pl_find_fmt(r->gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE) &&
            pl_find_fmt(r->gpu,PL_FMT_FLOAT,2,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);
    if(mode==DVBRIDGE_MODE_STANDARD || mode==DVBRIDGE_MODE_HDR10_BASIC)return true;
    if(mode==DVBRIDGE_MODE_HDR10PLUS)return cb1_hdr10plus_analysis_supported(r->gpu);
    if(!pl_find_fmt(r->gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_LINEAR) ||
       !pl_find_fmt(r->gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR))return false;
    return mode!=DVBRIDGE_MODE_ENHANCED_DV || dve_requirements(r->gpu);
}

#ifdef CB1_HAS_HDR10_AI
static bool hdr10_ai_gpu_requirements(pl_gpu gpu)
{
    pl_opengl gl=pl_opengl_get(gpu);
    if(!gl || !gpu->glsl.gles || gl->major<3 || (gl->major==3 && gl->minor<1))return false;
    if(!pl_find_fmt(gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE) ||
       !pl_find_fmt(gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_HOST_READABLE) ||
       !pl_find_fmt(gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE))return false;
    GLint invocations,size,groups,bindings,shared;GLint64 storage;
    glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,&invocations);
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_SIZE,0,&size);
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT,0,&groups);
    glGetIntegerv(GL_MAX_SHADER_STORAGE_BUFFER_BINDINGS,&bindings);
    glGetIntegerv(GL_MAX_COMPUTE_SHARED_MEMORY_SIZE,&shared);
    glGetInteger64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE,&storage);
    return invocations>=128 && size>=128 && groups>=2048 && bindings>=2 &&
        shared>=16384 && storage>=(65537+512)*4 && glGetError()==GL_NO_ERROR &&
        eglGetProcAddress("glMapBufferRange") && eglGetProcAddress("glDispatchCompute") &&
        eglGetProcAddress("glMemoryBarrier");
}
#endif

bool dvbridge_renderer_supports_hdr10_ai(struct dvbridge_renderer *r,enum dvbridge_mode mode)
{
#ifdef CB1_HAS_HDR10_AI
    return (mode==DVBRIDGE_MODE_STANDARD || mode==DVBRIDGE_MODE_ENHANCED_DV) &&
        dvbridge_renderer_supports_mode(r,mode==DVBRIDGE_MODE_ENHANCED_DV?DVBRIDGE_MODE_HDR10_EXPERT:mode) && dv_transport_requirements(r->gpu) &&
        hdr10_ai_gpu_requirements(r->gpu) &&
        (mode!=DVBRIDGE_MODE_ENHANCED_DV || dve_requirements(r->gpu));
#else
    (void)r;(void)mode;return false;
#endif
}

static bool dv_last_use(struct dvbridge_renderer *r)
{
    struct dvbridge_dv_slot *s=&r->dv;
    GLsync fence=s->fence_sync(GL_SYNC_GPU_COMMANDS_COMPLETE,0);glFlush();
    if(!fence || glGetError()!=GL_NO_ERROR){s->quarantined=true;s->active=true;return false;}
    if(s->fence)s->delete_sync(s->fence);
    s->fence=fence;
    return true;
}

static bool dv_allocate(struct dvbridge_renderer *r,size_t scratch_bytes)
{
    if(!dv_gpu_requirements(r->gpu))return false;
    struct dvbridge_dv_slot *s=&r->dv;
    bool reuse=r->enhanced_authored && r->reuse_authored_storage;
    if(reuse && (s->active || s->fence || s->mapped || s->buffers[0] || s->sampler))return false;
    s->buffer_storage=(PFNGLBUFFERSTORAGEEXTPROC)eglGetProcAddress("glBufferStorageEXT");
    s->wait_sync=(PFNGLCLIENTWAITSYNCPROC)eglGetProcAddress("glClientWaitSync");
    s->delete_sync=(PFNGLDELETESYNCPROC)eglGetProcAddress("glDeleteSync");
    s->fence_sync=(PFNGLFENCESYNCPROC)eglGetProcAddress("glFenceSync");
    size_t result_size=r->enhanced_authored?64:48;
    struct dvbridge_analysis_storage *storage=&r->analysis_storage;
    /* Authored DV alone borrows storage; AI keeps its existing frame ownership.
     * Admission still waits the transaction's final fence, including late GUI. */
    if(reuse && storage->mapped &&
       (storage->scratch_bytes<scratch_bytes || storage->result_bytes<result_size)){
        dv_delete_storage(storage->buffers,storage->sampler,storage->mapped);
        memset(storage,0,sizeof(*storage));
    }
    if(reuse && storage->mapped){
        memcpy(s->buffers,storage->buffers,sizeof(s->buffers));
        s->mapped=storage->mapped;s->sampler=storage->sampler;s->borrowed_storage=true;
    }else{
        GLint previous;glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&previous);
        glGenBuffers(3,s->buffers);
        for(unsigned i=0;i<2;i++){glBindBuffer(GL_SHADER_STORAGE_BUFFER,s->buffers[i]);glBufferData(GL_SHADER_STORAGE_BUFFER,scratch_bytes,NULL,GL_STREAM_DRAW);}
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,s->buffers[2]);
        GLbitfield flags=GL_MAP_READ_BIT|GL_MAP_PERSISTENT_BIT_EXT|GL_MAP_COHERENT_BIT_EXT;
        const uint32_t empty[16]={0};
        s->buffer_storage(GL_SHADER_STORAGE_BUFFER,result_size,empty,flags);
        if(glGetError()==GL_NO_ERROR)s->mapped=glMapBufferRange(GL_SHADER_STORAGE_BUFFER,0,result_size,flags);
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,previous);
        glGenSamplers(1,&s->sampler);
    }
#ifdef CB1_TEST_LEGACY_ANALYSIS
    if(!r->dv_analysis_program)r->dv_analysis_program=dv_compute_program();
    s->program=r->dv_analysis_program;
#endif
    /* Borrowed libplacebo textures need an explicit non-mipmapped sampler. */
    glSamplerParameteri(s->sampler,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glSamplerParameteri(s->sampler,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glSamplerParameteri(s->sampler,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glSamplerParameteri(s->sampler,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    if(!r->dv_transport_packer)
        r->dv_transport_packer=dvbridge_gl_packer_create(cb1_pack_vertex,cb1_pack_fragment);
    s->packer=r->dv_transport_packer;
    bool ok=s->mapped && s->packer && glGetError()==GL_NO_ERROR;
#ifdef CB1_TEST_LEGACY_ANALYSIS
    ok=ok && s->program;
#endif
    if(ok && reuse && !s->borrowed_storage){
        memcpy(storage->buffers,s->buffers,sizeof(s->buffers));storage->mapped=s->mapped;
        storage->sampler=s->sampler;storage->scratch_bytes=scratch_bytes;storage->result_bytes=result_size;
        s->borrowed_storage=true;
    }
    if(!ok)dv_release(r);
    return ok;
}

static bool dv_allocate_transport(struct dvbridge_renderer *r)
{
    struct dvbridge_dv_slot *s=&r->dv;
    if(!pl_opengl_get(r->gpu))return false;
    GLint precision,range[2];
    glGetShaderPrecisionFormat(GL_FRAGMENT_SHADER,GL_HIGH_FLOAT,range,&precision);
    if(precision<23 || range[0]<127 || range[1]<127)return false;
    s->wait_sync=(PFNGLCLIENTWAITSYNCPROC)eglGetProcAddress("glClientWaitSync");
    s->delete_sync=(PFNGLDELETESYNCPROC)eglGetProcAddress("glDeleteSync");
    s->fence_sync=(PFNGLFENCESYNCPROC)eglGetProcAddress("glFenceSync");
    if(!r->dv_transport_packer)
        r->dv_transport_packer=dvbridge_gl_packer_create(cb1_pack_vertex,cb1_pack_fragment);
    s->packer=r->dv_transport_packer;
    bool ok=s->wait_sync && s->delete_sync && s->fence_sync && s->packer && glGetError()==GL_NO_ERROR;
    if(!ok)dv_release(r);
    return ok;
}


#ifdef CB1_TEST_LEGACY_ANALYSIS
static bool dv_analyze(struct dvbridge_renderer *r,pl_tex texture)
{
    if(!texture)return false;
    struct dvbridge_dv_slot *s=&r->dv;const unsigned *m=s->output.value.margins;
    s->output.intermediate=texture;
    unsigned width=(3840-m[0]-m[1]+1)/2,height=(2160-m[2]-m[3]+1)/2;
    s->groups=width*height;
    GLint program,active,binding,sampler,generic,indexed[3];GLint64 offsets[3],sizes[3];
    glGetIntegerv(GL_CURRENT_PROGRAM,&program);glGetIntegerv(GL_ACTIVE_TEXTURE,&active);
    glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
    glGetIntegerv(GL_SAMPLER_BINDING,&sampler);
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&generic);
    for(unsigned i=0;i<3;i++){
        glGetIntegeri_v(GL_SHADER_STORAGE_BUFFER_BINDING,i,&indexed[i]);
        glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_START,i,&offsets[i]);
        glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_SIZE,i,&sizes[i]);
    }
    glUseProgram(s->program);
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(r->gpu,texture,NULL,NULL,NULL));
    glBindSampler(0,s->sampler);
    glUniform4ui(glGetUniformLocation(s->program,"area"),m[0],m[2],3840-m[1],2160-m[3]);
    const struct dvbridge_identity *id=&s->output.value.identity;
    glUniform2ui(glGetUniformLocation(s->program,"stream_id"),id->stream,id->stream>>32);
    glUniform2ui(glGetUniformLocation(s->program,"picture_id"),id->picture,id->picture>>32);
    glUniform2ui(glGetUniformLocation(s->program,"revision_id"),id->revision,id->revision>>32);
    unsigned count=s->groups,pass=0,input=1,output=0;
    while(count){unsigned dispatch=(count+127)/128;
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER,0,s->buffers[input]);
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER,1,s->buffers[output]);
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER,2,s->buffers[2]);
        glUniform1ui(glGetUniformLocation(s->program,"count"),count);
        glUniform1ui(glGetUniformLocation(s->program,"pass"),pass);
        glUniform1ui(glGetUniformLocation(s->program,"final_pass"),dispatch==1);
        glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT);glDispatchCompute(dispatch,1,1);
        if(dispatch==1)break;
        count=dispatch;
        pass=1;
        unsigned swap=input;input=output;output=swap;
    }
    bool ok=glGetError()==GL_NO_ERROR;
    for(unsigned i=0;i<3;i++){
        if(indexed[i] && sizes[i])glBindBufferRange(GL_SHADER_STORAGE_BUFFER,i,indexed[i],offsets[i],sizes[i]);
        else glBindBufferBase(GL_SHADER_STORAGE_BUFFER,i,indexed[i]);
    }
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,generic);glUseProgram(program);
    glBindSampler(0,sampler);glBindTexture(GL_TEXTURE_2D,binding);glActiveTexture(active);
    return dv_last_use(r) && ok && glGetError()==GL_NO_ERROR;
}

#endif

static uint16_t dv_wire_code(double pq)
{ return (uint16_t)fmin(4095,floor(4096*pq+.5)); }
static double dv_ideal_pq(double nits)
{
    if(!nits)return 0;
    double v=pow(nits/10000,2610.0/16384.0);
    return pow((3424.0/4096.0+2413.0/128.0*v)/(1+2392.0/128.0*v),2523.0/32.0);
}

static bool dve_requirements(pl_gpu gpu)
{
    if(!dv_gpu_requirements(gpu))return false;
    GLint groups,images,uniforms,shared;GLint64 storage;
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT,0,&groups);
    glGetIntegerv(GL_MAX_COMPUTE_IMAGE_UNIFORMS,&images);
    glGetIntegerv(GL_MAX_COMPUTE_UNIFORM_COMPONENTS,&uniforms);
    glGetIntegerv(GL_MAX_COMPUTE_SHARED_MEMORY_SIZE,&shared);
    glGetInteger64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE,&storage);
    return groups>=64800 && storage>=1036800 && images>=1 && uniforms>=384 && shared>=2048 &&
        pl_find_fmt(gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE) &&
        glGetError()==GL_NO_ERROR;
}
static bool dve_program(struct dvbridge_renderer *r,bool pq_lookup)
{
    bool quad=r->ai_enhanced_prepack;
    /* One cache identity for the exact preprocessor configuration below. */
    unsigned key=(unsigned)pq_lookup | (unsigned)r->enhanced_fast_pq<<1 |
        (unsigned)r->enhanced_linear<<2 | (unsigned)r->enhanced_prepack<<3 |
        (unsigned)r->ai_enhanced_fused<<4 | (unsigned)quad<<5 |
        (unsigned)r->enhanced_authored<<6 | (unsigned)r->enhanced_skip_aux<<7 |
        (unsigned)r->enhanced_authored_curve<<8;
    if(r->enhanced_program && r->enhanced_program_key!=key){
        glDeleteProgram(r->enhanced_program);r->enhanced_program=0;
    }
    if(!r->enhanced_program){
        GLuint shader=glCreateShader(GL_COMPUTE_SHADER);
        const char *text[]={"#version 310 es\n",pq_lookup?"#define CB1_DVE_PQ_LOOKUP 1\n":"",
            r->enhanced_fast_pq?"#define CB1_DVE_FAST_PQ 1\n":"",
            r->enhanced_linear?"#define CB1_DVE_LINEAR_INPUT 1\n":"",
            r->enhanced_prepack?"#define CB1_DVE_PREPACK 1\n":"",
            r->ai_enhanced_fused?"#define CB1_DVE_STATS_ONLY 1\n":"",
            quad?"#define CB1_DVE_QUAD_STATS 1\n":"",
            r->enhanced_authored?"#define CB1_DVE_AUTHORED 1\n":"",
            r->enhanced_skip_aux?"#define CB1_DVE_SKIP_AUX 1\n":"",
            r->enhanced_authored_curve?"#define CB1_DVE_AUTHORED_CURVE 1\n":"",
            dve_shader_uniforms,dve_math,dve_shader};
        glShaderSource(shader,sizeof(text)/sizeof(*text),text,NULL);glCompileShader(shader);GLint ok;
        glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);
        if(!ok){char log[4096];glGetShaderInfoLog(shader,sizeof(log),NULL,log);fprintf(stderr,"CB1 Enhanced: %s\n",log);glDeleteShader(shader);return false;}
        r->enhanced_program=glCreateProgram();glAttachShader(r->enhanced_program,shader);
        glLinkProgram(r->enhanced_program);glDeleteShader(shader);
        glGetProgramiv(r->enhanced_program,GL_LINK_STATUS,&ok);
        if(!ok){glDeleteProgram(r->enhanced_program);r->enhanced_program=0;return false;}
        r->enhanced_pq_lookup=pq_lookup;
        r->enhanced_program_key=key;
    }
    r->dv.program=r->enhanced_program;
    return true;
}
static bool dve_immutable(struct dvbridge_renderer *r,pl_tex *texture,GLuint *name,
    unsigned width,unsigned height,GLenum format)
{
    if(*texture && ((*texture)->params.w!=width || (*texture)->params.h!=height ||
        (*texture)->params.format->component_depth[0]!=((format==GL_RGBA16F || format==GL_RGBA16UI)?16:32))){
        pl_tex_destroy(r->gpu,texture);glDeleteTextures(1,name);*name=0;
    }
    if(!*texture){
        GLint previous;glGetIntegerv(GL_TEXTURE_BINDING_2D,&previous);
        glGenTextures(1,name);glBindTexture(GL_TEXTURE_2D,*name);
        glTexStorage2D(GL_TEXTURE_2D,1,format,width,height);glBindTexture(GL_TEXTURE_2D,previous);
        *texture=pl_opengl_wrap(r->gpu,pl_opengl_wrap_params(
            .texture=*name,.width=width,.height=height,.iformat=format));
        if(!*texture){glDeleteTextures(1,name);*name=0;}
    }
    return *texture!=NULL;
}
static bool dve_allocate(struct dvbridge_renderer *r,unsigned width,unsigned height,bool ai_fused,bool fast_pq)
{
    if(r->enhanced_authored){GLint shared;glGetIntegerv(GL_MAX_COMPUTE_SHARED_MEMORY_SIZE,&shared);if(shared<3584)return false;}
    if(!width || !height || width>3840 || height>2160 || !dve_requirements(r->gpu))return false;
    r->enhanced_fast_pq=fast_pq;
    size_t scratch_bytes=fast_pq?1036800:((width*height+127)/128)*16;
    if(!dv_allocate(r,scratch_bytes))return false;
    bool pq_lookup=!fast_pq && cb1_processing_pq_encoder(&r->processing,r->gpu)!=NULL;
    GLint images;glGetIntegerv(GL_MAX_COMPUTE_IMAGE_UNIFORMS,&images);
    GLint fragment_images;glGetIntegerv(GL_MAX_FRAGMENT_IMAGE_UNIFORMS,&fragment_images);
    r->ai_enhanced_fused=ai_fused && !r->ai_fusion_failed && fragment_images>=2;
    r->ai_enhanced_prepack=r->ai_enhanced_fused && r->fragment_quad && fragment_images>=3 && width==3840 && height==2160;
    /* Packing uses output geometry; the reconstruction/scaler keep their domain. */
    r->enhanced_prepack=(r->enhanced_linear || r->enhanced_skip_aux) && width==3840 && height==2160 && images>=2;
    r->enhanced_skip_aux=r->enhanced_skip_aux && r->enhanced_prepack;
    if(!dve_program(r,pq_lookup)){dv_release(r);return false;}
    /* ES image access requires immutable storage; pinned LP GLES uses mutable
     * textures. Wrap one native immutable texture, retaining explicit ownership. */
    /* Direct packing keeps full precision. Half-float PQ is retained only for
     * later GUI composition and guarded native recovery in this AI route. */
    bool ok=(r->reuse_authored_storage && r->enhanced_authored && r->enhanced_skip_aux) ||
        dve_immutable(r,&r->enhanced_rgb,&r->enhanced_texture,width,height,r->ai_enhanced_prepack?GL_RGBA16F:GL_RGBA32F);
    if(ok && r->ai_enhanced_fused){
        bool quad=r->ai_enhanced_prepack;
        ok=dve_immutable(r,&r->ai_enhanced_stats,&r->ai_enhanced_stats_texture,
            quad?width/2:width,quad?height/2:height,quad?GL_RGBA16UI:GL_R32F);
    }
    if(ok && r->ai_enhanced_prepack)
        ok=dve_immutable(r,&r->ai_enhanced_native,&r->ai_enhanced_native_texture,width,height,GL_RGBA16F);
    if(ok && (r->enhanced_prepack || r->ai_enhanced_prepack) && !r->enhanced_packed_texture){
        GLint texture,draw,read;glGetIntegerv(GL_TEXTURE_BINDING_2D,&texture);
        glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);
        glGenTextures(1,&r->enhanced_packed_texture);glBindTexture(GL_TEXTURE_2D,r->enhanced_packed_texture);
        glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA8,3840,2160);
        glGenFramebuffers(1,&r->enhanced_packed_fbo);glBindFramebuffer(GL_FRAMEBUFFER,r->enhanced_packed_fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,r->enhanced_packed_texture,0);
        ok=glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE;
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);glBindFramebuffer(GL_READ_FRAMEBUFFER,read);
        glBindTexture(GL_TEXTURE_2D,texture);
    }
    if(ok && r->ai_enhanced_prepack && !r->ai_enhanced_packed){
        r->ai_enhanced_packed=pl_opengl_wrap(r->gpu,pl_opengl_wrap_params(
            .texture=r->enhanced_packed_texture,.width=width,.height=height,.iformat=GL_RGBA8));
        ok=r->ai_enhanced_packed!=NULL;
    }
    r->dv.program=r->enhanced_program;
    if(!ok || glGetError()!=GL_NO_ERROR){
        dve_release_images(r);dv_release(r);return false;
    }
    return true;
}
static bool dve_clear_rows(unsigned framebuffer,unsigned first,unsigned end)
{
    if(!first && end==2160)return true;
    GLint read,draw,box[4];GLboolean mask[4],scissor=glIsEnabled(GL_SCISSOR_TEST);
    GLboolean discard=glIsEnabled(GL_RASTERIZER_DISCARD),dither=glIsEnabled(GL_DITHER);
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);
    glGetIntegerv(GL_SCISSOR_BOX,box);glGetBooleanv(GL_COLOR_WRITEMASK,mask);
    glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
    glDisable(GL_RASTERIZER_DISCARD);glDisable(GL_DITHER);
    glEnable(GL_SCISSOR_TEST);glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    const float black[4]={128.0f/255,16.0f/255,0,1};
    if(first){glScissor(0,0,3840,first);glClearBufferfv(GL_COLOR,0,black);}
    if(end<2160){glScissor(0,end,3840,2160-end);glClearBufferfv(GL_COLOR,0,black);}
    glColorMask(mask[0],mask[1],mask[2],mask[3]);glScissor(box[0],box[1],box[2],box[3]);
    if(!scissor)glDisable(GL_SCISSOR_TEST);
    if(discard)glEnable(GL_RASTERIZER_DISCARD);
    if(dither)glEnable(GL_DITHER);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,read);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);
    return glGetError()==GL_NO_ERROR;
}
static bool dve_run(struct dvbridge_renderer *r,const struct cb1_dv_enhanced_plan *p,
    pl_tex texture,const unsigned margins[4])
{
    bool skip_image=r->reuse_authored_storage && r->enhanced_authored && r->enhanced_skip_aux;
    if(!texture || (!r->enhanced_rgb && !skip_image) || p->status!=CB1_DVE_READY)return false;
    /* Reuse the calibrated transfer tables; unsupported GPUs keep analytic PQ. */
    bool pq_lookup=r->enhanced_pq_lookup;
    struct dvbridge_dv_slot *s=&r->dv;
    unsigned w=texture->params.w,h=texture->params.h;
    bool quad=s->ai_source && r->ai_enhanced_prepack;
    unsigned content_width=quad?3840:w,content_height=quad?2160:h;
    if(margins[0]+margins[1]>=content_width || margins[2]+margins[3]>=content_height)return false;
    unsigned first=0,end=h;
    if(r->enhanced_authored_curve && r->enhanced_skip_aux){
        first=margins[2];end=h-margins[3];
        if(s->enhanced_overlay){
            first=fmin(first,fmax(0,floor(s->overlay.rect[1])));
            end=fmax(end,fmin(h,ceil(s->overlay.rect[3])));
        }
        if(!dve_clear_rows(r->enhanced_packed_fbo,first,end))return false;
    }
    s->groups=(content_width-margins[0]-margins[1])*(content_height-margins[2]-margins[3]);
    GLint program,active,binding,sampler,generic,indexed[3],image[2][6];GLint64 offsets[3],sizes[3];
    glGetIntegerv(GL_CURRENT_PROGRAM,&program);glGetIntegerv(GL_ACTIVE_TEXTURE,&active);
    GLint lut_bindings[2],lut_samplers[2];
    if(pq_lookup)for(unsigned i=0;i<2;i++){
        glActiveTexture(GL_TEXTURE1+i);glGetIntegerv(GL_TEXTURE_BINDING_2D,&lut_bindings[i]);
        glGetIntegerv(GL_SAMPLER_BINDING,&lut_samplers[i]);
        glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(r->gpu,r->processing.pq_texture[i],NULL,NULL,NULL));
        glBindSampler(1+i,s->sampler);
    }
    if(pq_lookup){
        glSamplerParameteri(s->sampler,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glSamplerParameteri(s->sampler,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    }
    GLint gui_bindings[3],gui_samplers[3];
    bool prepack=r->enhanced_prepack;
    if(prepack){
        const struct dvbridge_native_overlay *o=&s->overlay;
        pl_tex textures[]={o->texture,o->degamma,o->pq};
        for(unsigned i=0;i<3;i++){
            glActiveTexture(GL_TEXTURE3+i);glGetIntegerv(GL_TEXTURE_BINDING_2D,&gui_bindings[i]);
            glGetIntegerv(GL_SAMPLER_BINDING,&gui_samplers[i]);
            glBindTexture(GL_TEXTURE_2D,s->enhanced_overlay?pl_opengl_unwrap(r->gpu,textures[i],NULL,NULL,NULL):0);
            glBindSampler(3+i,s->sampler);
        }
        glSamplerParameteri(s->sampler,GL_TEXTURE_MIN_FILTER,GL_LINEAR);
        glSamplerParameteri(s->sampler,GL_TEXTURE_MAG_FILTER,GL_LINEAR);
    }
    glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);glGetIntegerv(GL_SAMPLER_BINDING,&sampler);
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&generic);
    const GLenum queries[]={GL_IMAGE_BINDING_NAME,GL_IMAGE_BINDING_LEVEL,GL_IMAGE_BINDING_LAYERED,
        GL_IMAGE_BINDING_LAYER,GL_IMAGE_BINDING_ACCESS,GL_IMAGE_BINDING_FORMAT};
    for(unsigned unit=0;unit<(prepack?2:1);unit++)
        for(unsigned i=0;i<6;i++)glGetIntegeri_v(queries[i],unit,&image[unit][i]);
    for(unsigned i=0;i<3;i++){
        glGetIntegeri_v(GL_SHADER_STORAGE_BUFFER_BINDING,i,&indexed[i]);
        glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_START,i,&offsets[i]);
        glGetInteger64i_v(GL_SHADER_STORAGE_BUFFER_SIZE,i,&sizes[i]);
    }
    GLuint shader=r->enhanced_program;glUseProgram(shader);
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(r->gpu,texture,NULL,NULL,NULL));glBindSampler(0,s->sampler);
    if(s->ai_source && r->ai_enhanced_prepack){
        glSamplerParameteri(s->sampler,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
        glSamplerParameteri(s->sampler,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    }
    if(!r->ai_enhanced_fused && !skip_image)
        glBindImageTexture(0,pl_opengl_unwrap(r->gpu,r->enhanced_rgb,NULL,NULL,NULL),0,GL_FALSE,0,GL_WRITE_ONLY,GL_RGBA32F);
    if(prepack){
        glBindImageTexture(1,r->enhanced_packed_texture,0,GL_FALSE,0,GL_WRITE_ONLY,GL_RGBA8);
        glUniform1i(glGetUniformLocation(shader,"gui_visible"),s->enhanced_overlay);
        glUniform1i(glGetUniformLocation(shader,"gui_is_pq"),s->overlay.input_pq);
        glUniform4fv(glGetUniformLocation(shader,"gui_rect"),1,s->overlay.rect);
    }
    glUniform4ui(glGetUniformLocation(shader,"area"),margins[0],margins[2],w-margins[1],h-margins[3]);
    glUniform1ui(glGetUniformLocation(shader,"width"),w);
    glUniform1ui(glGetUniformLocation(shader,"origin_y"),first);
    glUniform1f(glGetUniformLocation(shader,"display_peak"),p->target);
    glUniform2f(glGetUniformLocation(shader,"bounds"),p->master,p->envelope);
    float curve[257],color[67],matrix[9];
    for(unsigned i=0;i<257;i++)curve[i]=p->extra[i];
    bool color_guidance=false,hue_guidance=false;
    for(unsigned i=0;i<67;i++){color[i]=p->color[i];color_guidance|=color[i]!=0;hue_guidance|=i>=2 && color[i]!=0;}
    pl_matrix3x3 lms=pl_ipt_rgb2lms(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++)matrix[j*3+i]=lms.m[i][j];
    glUniform1fv(glGetUniformLocation(shader,"extra"),257,curve);
    glUniform1fv(glGetUniformLocation(shader,"colors"),67,color);
    glUniform1i(glGetUniformLocation(shader,"color_guidance"),color_guidance);
    glUniform1i(glGetUniformLocation(shader,"hue_guidance"),hue_guidance);
    glUniform1f(glGetUniformLocation(shader,"master_pq"),dv_ideal_pq(p->master));
    glUniformMatrix3fv(glGetUniformLocation(shader,"lms"),1,GL_FALSE,matrix);
    const struct dvbridge_identity *id=&s->output.value.identity;
    glUniform2ui(glGetUniformLocation(shader,"stream_id"),id->stream,id->stream>>32);
    glUniform2ui(glGetUniformLocation(shader,"picture_id"),id->picture,id->picture>>32);
    glUniform2ui(glGetUniformLocation(shader,"revision_id"),id->revision,id->revision>>32);
    GLenum setup_error=glGetError();
    {
        unsigned count=w*(end-first),pass=0,input=1,output=0;
        while(count){
            unsigned tile=pass?(r->enhanced_fast_pq?64:128):(r->enhanced_fast_pq?512:1024),dispatch=(count+tile-1)/tile;
            glBindBufferBase(GL_SHADER_STORAGE_BUFFER,0,s->buffers[input]);
            glBindBufferBase(GL_SHADER_STORAGE_BUFFER,1,s->buffers[output]);
            glBindBufferBase(GL_SHADER_STORAGE_BUFFER,2,s->buffers[2]);
            glUniform1ui(glGetUniformLocation(shader,"count"),count);
            glUniform1ui(glGetUniformLocation(shader,"pass"),pass);
            glUniform1ui(glGetUniformLocation(shader,"final_pass"),dispatch==1);
            glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT|GL_TEXTURE_FETCH_BARRIER_BIT);
            glDispatchCompute(dispatch,1,1);
            if(dispatch==1)break;
            count=dispatch;pass=1;unsigned swap=input;input=output;output=swap;
        }
    }
    glMemoryBarrier(GL_SHADER_STORAGE_BARRIER_BIT|GL_CLIENT_MAPPED_BUFFER_BARRIER_BIT_EXT|
        GL_TEXTURE_FETCH_BARRIER_BIT|GL_SHADER_IMAGE_ACCESS_BARRIER_BIT|GL_FRAMEBUFFER_BARRIER_BIT);
    GLenum dispatch_error=glGetError();
    bool ok=setup_error==GL_NO_ERROR && dispatch_error==GL_NO_ERROR;
    for(unsigned i=0;i<3;i++){
        if(indexed[i] && sizes[i])glBindBufferRange(GL_SHADER_STORAGE_BUFFER,i,indexed[i],offsets[i],sizes[i]);
        else glBindBufferBase(GL_SHADER_STORAGE_BUFFER,i,indexed[i]);
    }
    for(unsigned unit=0;unit<(prepack?2:1);unit++)
        glBindImageTexture(unit,image[unit][0],image[unit][1],image[unit][2],image[unit][3],image[unit][4],image[unit][5]);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,generic);glUseProgram(program);
    if(pq_lookup)for(unsigned i=0;i<2;i++){
        glActiveTexture(GL_TEXTURE1+i);glBindTexture(GL_TEXTURE_2D,lut_bindings[i]);glBindSampler(1+i,lut_samplers[i]);
    }
    if(prepack)for(unsigned i=0;i<3;i++){
        glActiveTexture(GL_TEXTURE3+i);glBindTexture(GL_TEXTURE_2D,gui_bindings[i]);glBindSampler(3+i,gui_samplers[i]);
    }
    glActiveTexture(GL_TEXTURE0);
    glBindSampler(0,sampler);glBindTexture(GL_TEXTURE_2D,binding);glActiveTexture(active);
    s->prepacked=prepack || (s->ai_source && r->ai_enhanced_fused && r->ai_enhanced_prepack);
    return dv_last_use(r) && ok && glGetError()==GL_NO_ERROR;
}

/* Scalar-only replay of a constant endpoint's prescribed FP32 tree.
 * At most three levels, two 128-lane tiles per level. No image/pixel input. */
static float dv_constant_tile(float common,float tail,unsigned count)
{
    float values[128]={0};
    for(unsigned i=0;i<count;i++)values[i]=common;
    values[count-1]=tail;
    for(unsigned stride=1;stride<128;stride*=2)
        for(unsigned i=0;i<128;i+=2*stride)values[i]=(float)(values[i]+values[i+stride]);
    return values[0];
}
static float dv_constant_sum(float common,unsigned count)
{
    float tail=common;
    for(;;){
        tail=dv_constant_tile(common,tail,count%128?count%128:128);
        common=dv_constant_tile(common,common,128);
        count=(count+127)/128;
        if(count==1)return tail;
    }
}
static bool dv_derive(struct dvbridge_renderer *r,const uint32_t record[12])
{
    struct dvbridge_dv_slot *s=&r->dv;struct dvbridge_dv_policy_snapshot *v=&s->output.value;
    if(record[3]!=s->groups || !record[3] || record[3]>2073600 || record[10]!=1 || record[11] ||
       ((uint64_t)record[4]|(uint64_t)record[5]<<32)!=v->identity.stream ||
       ((uint64_t)record[6]|(uint64_t)record[7]<<32)!=v->identity.picture ||
       ((uint64_t)record[8]|(uint64_t)record[9]<<32)!=v->identity.revision)return false;
    float raw[3];memcpy(raw,record,sizeof(raw));
    double stats[3]={raw[0],(double)raw[1]/record[3],raw[2]};
    if(!isfinite(stats[0]) || !isfinite(stats[1]) || !isfinite(stats[2]) ||
       stats[0]<0 || stats[2]>1 || stats[0]>stats[2])return false;
    if(raw[0]==raw[2]){
        if(raw[1]!=dv_constant_sum(raw[0],record[3]) || fabs(stats[1]-stats[0])>1e-6)return false;
        stats[1]=stats[0];
    }else{
        if(raw[1]<dv_constant_sum(raw[0],record[3]) ||
           raw[1]>dv_constant_sum(raw[2],record[3]))return false;
        stats[1]=fmin(stats[2],fmax(stats[0],stats[1]));
    }
    v->raw_statistics[0]=raw[0];v->raw_statistics[1]=(double)raw[1]/record[3];v->raw_statistics[2]=raw[2];
    v->raw_sum=raw[1];v->sample_count=record[3];
    for(unsigned i=0;i<3;i++)v->statistics[i]=floor(stats[i]*100000+.5)/100000;
    if(v->statistics[0]>v->statistics[1] || v->statistics[1]>v->statistics[2])return false;
    v->l1[0]=dv_wire_code(v->statistics[0]);v->l1[1]=dv_wire_code(v->statistics[2]);v->l1[2]=dv_wire_code(v->statistics[1]);
    v->source_pq[1]=dv_wire_code(dv_ideal_pq(v->nominal_max_nits));
    s->output_metadata=av_dovi_metadata_alloc(&s->output_bytes);if(!s->output_metadata)return false;
    AVDOVIMetadata *m=s->output_metadata;m->num_ext_blocks=2;
    av_dovi_get_header(m)->disable_residual_flag=1;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);c->signal_eotf=65535;c->source_max_pq=v->source_pq[1];
    c->scene_refresh_flag=av_dovi_get_color((const AVDOVIMetadata *)s->source_metadata)->scene_refresh_flag;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0),*l5=av_dovi_get_ext(m,1);l1->level=1;l5->level=5;
    l1->l1.min_pq=v->l1[0];l1->l1.max_pq=v->l1[1];l1->l1.avg_pq=v->l1[2];
    l5->l5.left_offset=v->margins[0];l5->l5.right_offset=v->margins[1];
    l5->l5.top_offset=v->margins[2];l5->l5.bottom_offset=v->margins[3];
    bool force=!r->dv_has_committed || r->dv_committed.identity.stream!=v->identity.stream ||
        r->dv_committed.identity.revision!=v->identity.revision || r->dv_committed.output_generation!=v->output_generation;
    r->pending=dvbridge_prepare_output(r->context,m,s->output_bytes,s->pts,
        (struct dvbridge_geometry){3840,2160,0,0,3840,2160},v->fel_reconstructed,force);
    if(!r->pending)return false;
    s->output.output_metadata=m;s->output.bytes=s->output_bytes;s->output.candidate=r->pending;
    return true;
}

void dvbridge_render_dv_policy_cancel(struct dvbridge_renderer *r)
{
    if(!r)return;
    r->dv.ordered_handoff=false;
    if(r->dv.active){r->dv.retiring=true;r->dv.ready=false;}
    r->ready=false;
    memset(&r->dv.output,0,sizeof(r->dv.output));
    dvbridge_candidate_destroy(r->pending);r->pending=NULL;
}

static enum dvbridge_dv_policy_status dv_policy_prepare(struct dvbridge_renderer *r,
    const struct dvbridge_policy *policy,const struct dvbridge_identity *id,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry,
    pl_tex packed,bool flip,const struct dvbridge_native_overlay *overlay)
{
    if(!r)return DVBRIDGE_DV_FAILED;
    if(r->dv.active){dvbridge_render_dv_policy_cancel(r);return r->dv.quarantined?DVBRIDGE_DV_FAILED:DVBRIDGE_DV_BUSY;}
    dvbridge_render_policy_cancel(r);
    if(!r->owner)return DVBRIDGE_DV_UNSUPPORTED;
    if(!policy || !id || policy->mode!=DVBRIDGE_MODE_ENHANCED_DV || id->revision!=policy->revision ||
       !isfinite(pts) || !isfinite(el_pts) || !source || source->num_overlays ||
       (source->enhancement_layer && source->enhancement_layer->num_overlays))return DVBRIDGE_DV_FAILED;
    unsigned margins[4];struct dvbridge_color color;struct pl_color_space nominal;
    struct dvbridge_creative_plan creative;
    if(!dvbridge_frame_area(margins,metadata,bytes,geometry) ||
       !dvbridge_map_color(&color,metadata,bytes,source->enhancement_layer && pts==el_pts) ||
       dvbridge_creative_resolve(&creative,metadata,bytes,policy)==DVBRIDGE_CREATIVE_INVALID)return DVBRIDGE_DV_FAILED;
    struct cb1_dv_enhanced_source guidance;struct cb1_dv_enhanced_plan plan;
    bool guided=policy->adaptive!=DVBRIDGE_ADAPTIVE_A;
    if(!(guided?dvbridge_creative_enhanced_source_b(&guidance,metadata,bytes,policy):
         dvbridge_creative_enhanced_source(&guidance,metadata,bytes,policy)))return DVBRIDGE_DV_FAILED;
    enum cb1_dv_enhanced_status status=cb1_dv_enhanced_build(&plan,&guidance,policy);
    if(status==CB1_DVE_INVALID)return DVBRIDGE_DV_FAILED;
    bool reset=!r->enhanced_has_committed || r->enhanced_stream!=id->stream ||
        pts<r->enhanced_pts || pts-r->enhanced_pts>1;
    cb1_dv_enhanced_transition(&plan,&r->enhanced_committed,pts-r->enhanced_pts,reset);
    bool pixels=plan.status==CB1_DVE_READY;
    r->enhanced_linear=pixels && (guided ||
        (geometry.source_width==3840 && geometry.source_height==2160 &&
         !geometry.x && !geometry.y && geometry.width==3840 && geometry.height==2160));
    r->enhanced_authored=pixels;
    r->enhanced_authored_curve=pixels;
    r->enhanced_skip_aux=r->enhanced_authored_curve && packed && !overlay && !r->overlay_visible &&
        (r->enhanced_linear || guided);
    struct dvbridge_geometry reconstruction=geometry;
    memcpy(r->enhanced_margins,margins,sizeof(margins));
    bool native_grid=pixels && guided &&
        geometry.source_width<=3840 && geometry.source_height<=2160 &&
        (geometry.source_width<3840 || geometry.source_height<2160);
    if(native_grid){
        reconstruction.x=reconstruction.y=0;
        reconstruction.width=geometry.source_width;reconstruction.height=geometry.source_height;
        if(!dvbridge_frame_area(r->enhanced_margins,metadata,bytes,reconstruction))return DVBRIDGE_DV_FAILED;
        r->enhanced_margins[1]-=3840-reconstruction.width;
        r->enhanced_margins[3]-=2160-reconstruction.height;
    }
    unsigned reconstruction_width=native_grid?geometry.source_width:3840;
    unsigned reconstruction_height=native_grid?geometry.source_height:2160;
    if(r->enhanced_linear && (policy->adaptive==DVBRIDGE_ADAPTIVE_B_FP16 || native_grid)){
        int depth=policy->adaptive==DVBRIDGE_ADAPTIVE_B_FP16?16:32;
        pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,depth,32,
            PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_BLITTABLE);
        if(!fmt || fmt->component_depth[0]!=depth || !pl_tex_recreate(r->gpu,&r->enhanced_input,
            pl_tex_params(.w=reconstruction_width,.h=reconstruction_height,.format=fmt,
                .renderable=true,.sampleable=true,.blit_dst=true)))
            return DVBRIDGE_DV_UNSUPPORTED;
    }else pl_tex_destroy(r->gpu,&r->enhanced_input);
    if(packed && !pixels && !r->fragment_quad)return DVBRIDGE_DV_UNSUPPORTED;
    bool fel=color.dovi.nlq_active && source->enhancement_layer && pts==el_pts;
    bool fast_pq=pixels && r->enhanced_linear && r->fast_chroma &&
        (fel || (r->authored_p5_analytic && policy->adaptive==DVBRIDGE_ADAPTIVE_B_FP16 &&
                 geometry.source_width==3840 && geometry.source_height==2160 &&
                 dvbridge_dv_profile5_transport(metadata)));
    if(!(pixels?dve_allocate(r,reconstruction_width,reconstruction_height,false,fast_pq):dv_allocate_transport(r)))return DVBRIDGE_DV_UNSUPPORTED;
    struct dvbridge_dv_slot *s=&r->dv;
    s->output_metadata=av_memdup(metadata,bytes);s->output_bytes=bytes;
    if(!s->output_metadata){dv_release(r);return DVBRIDGE_DV_FAILED;}
    bool force=!r->dv_has_committed || r->dv_committed.identity.stream!=id->stream ||
        r->dv_committed.identity.revision!=id->revision;
    bool ok=packed && !pixels ? render_packed_overlay(r,source,metadata,bytes,pts,el_pts,geometry,packed,flip,overlay,force,NULL,false,NULL) :
        render(r,source,metadata,bytes,pts,el_pts,reconstruction,NULL,false,NULL,NULL,NULL,force,NULL,pixels,NULL,false,NULL);
    s->active=true;s->pts=pts;
    if(!ok){dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;}
    if(!r->pending){dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;}
    if(native_grid){
        /* Native-size reconstruction never changes the final transport area. */
        struct dvbridge_candidate *output=dvbridge_prepare_output(r->context,metadata,bytes,pts,geometry,fel,force);
        if(!output){dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;}
        dvbridge_candidate_destroy(r->pending);r->pending=output;
    }
    const AVDOVIColorMetadata *c=av_dovi_get_color(metadata);
    const AVDOVIDmData *l1=av_dovi_find_level(metadata,1);
    enum pl_color_primaries prim=policy->tv.gamut==DVBRIDGE_GAMUT_BT709?PL_COLOR_PRIM_BT_709:
        policy->tv.gamut==DVBRIDGE_GAMUT_P3_D65?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020;
    nominal=(struct pl_color_space){.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=policy->tv.peak_nits,.prim=*pl_raw_primaries_get(prim)}};
    s->output.value=(struct dvbridge_dv_policy_snapshot){.identity=*id,.policy=*policy,.source_cm_version=creative.cm4?40:29,
        .output_generation=DVBRIDGE_SOURCE_METADATA,.nominal_target=nominal,.container=r->reconstructed_color,
        .geometry=geometry,.nominal_max_nits=pixels?plan.envelope:policy->tv.peak_nits,.fel_reconstructed=fel,.creative=creative,
        .creative_edit={.status=DVBRIDGE_CREATIVE_NEUTRAL,.reason=DVBRIDGE_CREATIVE_NO_ANCHOR},
        .pixel_algorithm=guided?(policy->adaptive==DVBRIDGE_ADAPTIVE_B_FP16?
            "cb1-dve-guided-fp16-v1":"cb1-dve-guided-v1"):CB1_DVE_ALGORITHM,
        .expansion_reason=plan.reason,.guidance_family=guidance.family,
        .source_reference_nits=plan.master,.display_reference_nits=plan.target,
        .l1={l1?l1->l1.min_pq:0,l1?l1->l1.max_pq:0,l1?l1->l1.avg_pq:0},.source_pq={c->source_min_pq,c->source_max_pq}};
    memcpy(s->output.value.margins,margins,sizeof(margins));
    if(r->enhanced_linear)s->output.value.container=color.color;
    s->output.output_metadata=s->output_metadata;s->output.bytes=bytes;
    s->output.candidate=r->pending;s->output.intermediate=packed && !pixels?NULL:r->rgb;
    s->packed_target=pixels?NULL:packed;s->packed_flip=flip;
    s->enhanced_plan=plan;s->enhanced_pixels=pixels;
    s->enhanced_overlay=overlay!=NULL;if(overlay)s->overlay=*overlay;
    r->policy_ready=false;
    if(pixels){
        if(!dve_run(r,&plan,r->enhanced_input?r->enhanced_input:r->rgb,r->enhanced_margins)){
            dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;
        }
        s->ready=r->ready=false;
        return DVBRIDGE_DV_PENDING;
    }
    if(!dv_last_use(r)){dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;}
    s->ready=r->ready=true;
    return DVBRIDGE_DV_READY;
}

enum dvbridge_dv_policy_status dvbridge_render_dv_policy_prepare(struct dvbridge_renderer *r,
    const struct dvbridge_policy *policy,const struct dvbridge_identity *id,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry)
{
    return dv_policy_prepare(r,policy,id,source,metadata,bytes,pts,el_pts,geometry,NULL,false,NULL);
}

enum dvbridge_dv_policy_status dvbridge_render_dv_policy_prepare_packed(struct dvbridge_renderer *r,
    const struct dvbridge_policy *policy,const struct dvbridge_identity *id,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry,
    pl_tex target,bool flip,const struct dvbridge_native_overlay *overlay)
{
    if(!target)return DVBRIDGE_DV_FAILED;
    return dv_policy_prepare(r,policy,id,source,metadata,bytes,pts,el_pts,geometry,target,flip,overlay);
}

static bool dve_refresh_candidate(struct dvbridge_renderer *r)
{
    struct dvbridge_dv_slot *s=&r->dv;const struct dvbridge_dv_policy_snapshot *v=&s->output.value;
    struct dvbridge_geometry geometry=s->ai_source || v->output_generation==DVBRIDGE_RECONSTRUCTED_ENHANCED?
        (struct dvbridge_geometry){3840,2160,0,0,3840,2160}:v->geometry;
    bool force=!r->dv_has_committed || r->dv_committed.identity.stream!=v->identity.stream ||
        r->dv_committed.identity.revision!=v->identity.revision ||
        r->dv_committed.output_generation!=v->output_generation;
    struct dvbridge_candidate *candidate=dvbridge_prepare_output(r->context,s->output_metadata,
        s->output_bytes,s->pts,geometry,v->fel_reconstructed,force);
    if(!candidate)return false;
    dvbridge_candidate_destroy(r->pending);r->pending=candidate;s->output.candidate=candidate;
    s->overlay_dirty=false;return true;
}
bool dvbridge_render_dv_policy_update_overlay(struct dvbridge_renderer *r,
    const struct dvbridge_native_overlay *overlay,bool visible)
{
    if(!r)return false;
    struct dvbridge_dv_slot *s=&r->dv;
    if(!s->active || !s->enhanced_pixels || s->retiring || s->quarantined || s->packed_target || s->ai_direct_lean ||
       s->output.value.resolved || (overlay && (!overlay->texture || !overlay->degamma || !overlay->pq)))return false;
    /* Late GUI needs an uncomposed image, not a new source reconstruction.
     * Materialize it once; later redraws only replace the final overlay. */
    if(!s->ai_source && r->enhanced_skip_aux && s->enhanced_plan.status==CB1_DVE_READY){
        r->enhanced_skip_aux=r->enhanced_prepack=false;
        pl_tex input=r->enhanced_input?r->enhanced_input:r->rgb;
        if(!input || !dve_immutable(r,&r->enhanced_rgb,&r->enhanced_texture,input->params.w,input->params.h,GL_RGBA32F) ||
           !dve_program(r,r->enhanced_pq_lookup) ||
           !dve_run(r,&s->enhanced_plan,input,r->enhanced_margins))
            return false;
        s->output.intermediate=r->enhanced_rgb;
    }
    bool changed=visible!=r->overlay_visible;
    dvbridge_set_overlay_visible(r->context,visible);
    if(changed && s->ready && !dve_refresh_candidate(r)){
        dvbridge_set_overlay_visible(r->context,r->overlay_visible);return false;
    }
    r->overlay_visible=visible;s->overlay_dirty|=changed && !s->ready;
    s->prepacked=false;
    s->enhanced_overlay=overlay!=NULL;if(overlay)s->overlay=*overlay;
    return true;
}
/* Recover the canonical PQ image only when the source-bound guard rejects expansion. */
static struct pl_hook_res dve_linear_decode(void *priv,const struct pl_hook_params *p)
{
    (void)priv;
    struct pl_custom_shader shader={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .body="color.rgb *= 10000.0/203.0;",.description="Decode normalized linear Enhanced storage"};
    return (struct pl_hook_res){.failed=!pl_shader_custom(p->sh,&shader),.output=PL_HOOK_SIG_NONE};
}
static bool dve_native_pq(struct dvbridge_renderer *r)
{
    pl_tex input=r->enhanced_input?r->enhanced_input:r->rgb;
    if(!input || !dve_immutable(r,&r->enhanced_rgb,&r->enhanced_texture,input->params.w,input->params.h,GL_RGBA32F))return false;
    struct pl_frame image={.num_planes=1,
        .planes={{.texture=input,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color=r->reconstructed_color,.crop={0,0,input->params.w,input->params.h}};
    struct pl_frame target=image;target.planes[0].texture=r->enhanced_rgb;
    target.color.transfer=PL_COLOR_TRC_PQ;
    struct pl_render_params params=pl_render_default_params;
    const struct pl_hook hook={.stages=PL_HOOK_RGB,.input=PL_HOOK_SIG_COLOR,
        .hook=dve_linear_decode,.signature=0x4342314456450003ULL};
    const struct pl_hook *hooks[]={&hook};params.hooks=hooks;params.num_hooks=1;
    params.min_fbo_precision=32;params.peak_detect_params=NULL;params.dither_params=NULL;
    params.frame_mixer=NULL;params.skip_caching_single_frame=true;params.sigmoid_params=NULL;
    params.cb1_nearest_identity=true;params.border=PL_CLEAR_SKIP;
    bool ok=pl_render_image(r->renderer,&image,&target,&params);
    struct pl_render_errors errors=pl_renderer_get_errors(r->renderer);
    bool fenced=dv_last_use(r);
    return fenced && ok && !errors.errors && !errors.num_disabled_hooks;
}
static bool dve_derive(struct dvbridge_renderer *r,const uint32_t *record)
{
    struct dvbridge_dv_slot *s=&r->dv;struct dvbridge_dv_policy_snapshot *v=&s->output.value;
    if(!s->enhanced_pixels || record[3]!=s->groups || !record[3] || record[3]>8294400 ||
       record[10]!=1 || record[11]>1 ||
       ((uint64_t)record[4]|(uint64_t)record[5]<<32)!=v->identity.stream ||
       ((uint64_t)record[6]|(uint64_t)record[7]<<32)!=v->identity.picture ||
       ((uint64_t)record[8]|(uint64_t)record[9]<<32)!=v->identity.revision)return false;
    float raw[3];memcpy(raw,record,sizeof(raw));
    double mean=(double)raw[1]/record[3];
    if(!isfinite(raw[0]) || !isfinite(mean) || !isfinite(raw[2]) ||
       raw[0]<0 || raw[2]>1 || raw[0]>raw[2] || mean<raw[0]-1e-6 || mean>raw[2]+1e-6)return false;
    if(record[11]){
        bool direct=!s->ai_source && r->enhanced_skip_aux && r->fragment_quad &&
            v->policy.adaptive!=DVBRIDGE_ADAPTIVE_A;
        if(!direct && !s->ai_source && r->enhanced_linear && !dve_native_pq(r))return false;
        /* Keep the original metadata when expansion cannot be applied. */
        s->enhanced_plan.status=CB1_DVE_IDENTITY;s->enhanced_plan.reason=CB1_DVE_SOURCE_BOUND;
        v->expansion_reason=CB1_DVE_SOURCE_BOUND;
        if(s->ai_source)v->nominal_max_nits=v->source_reference_nits;
        s->output.intermediate=direct?NULL:s->ai_source && r->ai_enhanced_fused && r->ai_enhanced_prepack?r->ai_enhanced_native:
            !s->ai_source && r->enhanced_linear?r->enhanced_rgb:
            s->ai_source && (r->enhanced_rgb->params.w!=3840 || r->enhanced_rgb->params.h!=2160)?r->native_picture:r->rgb;
        return !s->overlay_dirty || dve_refresh_candidate(r);
    }
    size_t output_bytes=s->output_bytes;
    AVDOVIMetadata *m;
    if(!s->ai_source){
        /* Fast checks finite, non-darkening expansion for every source pixel. */
        if(!r->enhanced_fast_pq){
            float before[3];memcpy(before,record+12,sizeof(before));
            double input[3]={before[0],(double)before[1]/record[3],before[2]};
            double output[3]={raw[0],mean,raw[2]};
            if(record[15]!=record[3] || !isfinite(input[0]) || !isfinite(input[1]) || !isfinite(input[2]) ||
               input[0]<0 || input[2]>1 || input[0]>input[1]+1e-6 || input[1]>input[2]+1e-6)return false;
            for(unsigned i=0;i<3;i++)if(output[i]<input[i]-1e-5)return false;
        }
        m=av_dovi_metadata_alloc(&output_bytes);if(!m)return false;
        *av_dovi_get_header(m)=*av_dovi_get_header(s->output_metadata);
        *av_dovi_get_mapping(m)=*av_dovi_get_mapping(s->output_metadata);
        *av_dovi_get_color(m)=*av_dovi_get_color(s->output_metadata);
        m->num_ext_blocks=s->output_metadata->num_ext_blocks;
        for(int i=0;i<m->num_ext_blocks;i++)*av_dovi_get_ext(m,i)=*av_dovi_get_ext(s->output_metadata,i);
        AVDOVIDmData *l1=(AVDOVIDmData *)av_dovi_find_level(m,1);
        if(!l1){av_free(m);return false;}
        /* Transform authored scene statistics, not each frame's extrema. */
        AVDOVIDmData *l3=(AVDOVIDmData *)av_dovi_find_level(m,3);
        if(l3){
            l3->l3.min_pq_offset=l3->l3.max_pq_offset=l3->l3.avg_pq_offset=2048;
            memcpy(l3->dvbridge_original_bytes,(uint8_t[5]){0x80,0x08,0,0x80,0},5);
        }
        uint16_t analysis[3];
        if(!cb1_dv_enhanced_analysis(&s->enhanced_plan,analysis)){av_free(m);return false;}
        l1->l1.min_pq=analysis[0];l1->l1.max_pq=analysis[1];l1->l1.avg_pq=analysis[2];
        AVDOVIColorMetadata *c=av_dovi_get_color(m);
        /* Declare the applied transform's fixed envelope, not a per-frame master. */
        c->source_max_pq=fmax(c->source_max_pq,dv_wire_code(dv_ideal_pq(s->enhanced_plan.envelope)));
        /* Guard statistics remain linear; only the wire maximum needs PQ. */
        float measured_max_pq=r->enhanced_fast_pq?dv_ideal_pq(raw[2]*10000.0):raw[2];
        c->source_max_pq=fmax(c->source_max_pq,dv_wire_code(measured_max_pq));
        c->source_max_pq=fmax(c->source_max_pq,l1->l1.max_pq);
        AVDOVIDmData *l5=(AVDOVIDmData *)av_dovi_find_level(m,5);
        if(!l5){
            if(m->num_ext_blocks>=AV_DOVI_MAX_EXT_BLOCKS){av_free(m);return false;}
            l5=av_dovi_get_ext(m,m->num_ext_blocks++);*l5=(AVDOVIDmData){.level=5};
        }
        l5->l5.left_offset=v->margins[0];l5->l5.right_offset=v->margins[1];
        l5->l5.top_offset=v->margins[2];l5->l5.bottom_offset=v->margins[3];
    }else{
    m=av_dovi_metadata_alloc(&output_bytes);if(!m)return false;
    m->num_ext_blocks=2;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);c->signal_eotf=65535;
    c->source_max_pq=(uint16_t)floor(4095*dv_ideal_pq(s->enhanced_plan.envelope)+.5);
    c->scene_refresh_flag=av_dovi_get_color(s->output_metadata)->scene_refresh_flag;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0),*l5=av_dovi_get_ext(m,1);l1->level=1;l5->level=5;
    if(s->enhanced_plan.policy.adaptive!=DVBRIDGE_ADAPTIVE_A){
        uint16_t analysis[3];
        if(!cb1_dv_enhanced_analysis(&s->enhanced_plan,analysis)){av_free(m);return false;}
        l1->l1.min_pq=analysis[0];l1->l1.max_pq=analysis[1];l1->l1.avg_pq=analysis[2];
        c->source_max_pq=fmax(dv_wire_code(dv_ideal_pq(s->enhanced_plan.envelope)),
            fmax(l1->l1.max_pq,dv_wire_code(raw[2])));
    }else{
    l1->l1.min_pq=dv_wire_code(raw[0]);l1->l1.max_pq=dv_wire_code(raw[2]);
    l1->l1.avg_pq=dv_wire_code(fmin(raw[2],fmax(raw[0],mean)));
    }
    l5->l5.left_offset=v->margins[0];l5->l5.right_offset=v->margins[1];
    l5->l5.top_offset=v->margins[2];l5->l5.bottom_offset=v->margins[3];
    }
    av_dovi_get_header(m)->disable_residual_flag=1;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    const AVDOVIDmData *l1=av_dovi_find_level(m,1);
    bool force=!r->dv_has_committed || r->dv_committed.identity.stream!=v->identity.stream ||
        r->dv_committed.identity.revision!=v->identity.revision ||
        r->dv_committed.output_generation!=DVBRIDGE_RECONSTRUCTED_ENHANCED;
    struct dvbridge_candidate *candidate=dvbridge_prepare_output(r->context,m,output_bytes,s->pts,
        (struct dvbridge_geometry){3840,2160,0,0,3840,2160},v->fel_reconstructed,force);
    if(!candidate){av_free(m);return false;}
    dvbridge_candidate_destroy(r->pending);r->pending=candidate;
    av_free(s->output_metadata);s->output_metadata=m;
    s->output_bytes=output_bytes;
    s->output.output_metadata=m;s->output.bytes=s->output_bytes;
    s->output.candidate=candidate;s->output.intermediate=s->ai_direct_lean || r->enhanced_skip_aux?NULL:r->enhanced_rgb;
    v->output_generation=DVBRIDGE_RECONSTRUCTED_ENHANCED;
    v->analysis_model=s->ai_source?(s->enhanced_plan.policy.adaptive!=DVBRIDGE_ADAPTIVE_A?
        "cb1-ai-scene-curve-v1":CB1_DVE_ANALYSIS):r->enhanced_fast_pq?
        "cb1-authored-scene-curve-linear-guard-v1":"cb1-authored-scene-curve-v1";v->measured=true;
    v->raw_statistics[0]=v->statistics[0]=raw[0];v->raw_statistics[1]=v->statistics[1]=mean;
    v->raw_statistics[2]=v->statistics[2]=raw[2];v->raw_sum=raw[1];v->sample_count=record[3];
    v->l1[0]=l1->l1.min_pq;v->l1[1]=l1->l1.max_pq;v->l1[2]=l1->l1.avg_pq;
    v->source_pq[0]=c->source_min_pq;v->source_pq[1]=c->source_max_pq;
    if(!s->ai_source)v->nominal_max_nits=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,c->source_max_pq/4095.0);
    v->container=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=s->ai_source?s->enhanced_plan.envelope:v->nominal_max_nits,
            .prim=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020)}};
    return true;
}

enum dvbridge_dv_policy_status dvbridge_render_dv_policy_wait(struct dvbridge_renderer *r,uint64_t timeout_ns)
{
    if(!r)return DVBRIDGE_DV_FAILED;
    struct dvbridge_dv_slot *s=&r->dv;
    if(s->quarantined || r->retired_packed.quarantined)return DVBRIDGE_DV_FAILED;
    if(!s->active)return dv_retire(r);
    if(s->retiring)return dv_retire(r);
    if(s->ready)return DVBRIDGE_DV_READY;
    GLenum status=s->wait_sync(s->fence,0,r->enhanced_authored && s->enhanced_pixels?timeout_ns:0);
    if(status==GL_TIMEOUT_EXPIRED)return DVBRIDGE_DV_PENDING;
    if(status!=GL_ALREADY_SIGNALED && status!=GL_CONDITION_SATISFIED){s->quarantined=true;dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;}
    s->delete_sync(s->fence);s->fence=NULL;
    if(s->mapped){
        uint32_t record[16]={0};memcpy(record,s->mapped,r->enhanced_authored?64:48);
        if(s->enhanced_pixels?dve_derive(r,record):dv_derive(r,record)){
            s->ready=r->ready=true;return DVBRIDGE_DV_READY;
        }
    }
    dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;
}

enum dvbridge_dv_policy_status dvbridge_render_dv_policy_poll(struct dvbridge_renderer *r)
{
    return dvbridge_render_dv_policy_wait(r,0);
}

const struct dvbridge_dv_policy_output *dvbridge_render_dv_policy_output(const struct dvbridge_renderer *r)
{ return r && r->dv.active && r->dv.ready && !r->dv.retiring && !r->dv.quarantined ? &r->dv.output : NULL; }

static bool dv_final_framebuffer(unsigned framebuffer,unsigned alpha_bits)
{
    if(framebuffer && !glIsFramebuffer(framebuffer))return false;
    GLint draw,read,bits[4],encoding=0;
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);
    glBindFramebuffer(GL_FRAMEBUFFER,framebuffer);
    const GLenum channels[4]={GL_RED_BITS,GL_GREEN_BITS,GL_BLUE_BITS,GL_ALPHA_BITS};
    bool valid=glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE;
    if(valid){
        for(unsigned i=0;i<4;i++){glGetIntegerv(channels[i],&bits[i]);valid=valid && bits[i]==(i==3?alpha_bits:8);}
        glGetFramebufferAttachmentParameteriv(GL_FRAMEBUFFER,framebuffer?GL_COLOR_ATTACHMENT0:GL_BACK,
            GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING,&encoding);
        valid=valid && encoding==GL_LINEAR;
    }
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);glBindFramebuffer(GL_READ_FRAMEBUFFER,read);
    return glGetError()==GL_NO_ERROR && valid;
}

static struct pl_hook_res dve_overlay_output(void *priv,const struct pl_hook_params *p)
{
    struct active_mask *mask=priv;const struct dvbridge_native_overlay *o=mask->overlay;
    struct pl_shader_desc desc[3]={0};
    const char *names[]={"dve_gui","dve_degamma","dve_pq"};
    pl_tex textures[]={o->texture,o->degamma,o->pq};
    for(unsigned i=0;i<3;i++){
        desc[i].desc.name=names[i];desc[i].desc.type=PL_DESC_SAMPLED_TEX;
        desc[i].binding.object=textures[i];desc[i].binding.sample_mode=PL_TEX_SAMPLE_LINEAR;
        desc[i].binding.address_mode=PL_TEX_ADDRESS_CLAMP;
    }
    struct pl_shader_var rect={.var=pl_var_vec4("dve_rect"),.data=o->rect,.dynamic=true};
    struct pl_custom_shader shader={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .description="Compose GUI after Enhanced content analysis",.descriptors=desc,.num_descriptors=3,
        .variables=&rect,.num_variables=1,.header=o->input_pq?"#define DVE_GUI_PQ 1\n":"",
        .body="vec2 p=gl_FragCoord.xy;if(p.x>=dve_rect.x&&p.x<dve_rect.z&&p.y>=dve_rect.y&&p.y<dve_rect.w){"
        "vec4 gui=texture(dve_gui,vec2(p.x/3840.0,1.0-p.y/2160.0));\n"
        "#ifdef DVE_GUI_PQ\n"
        "color.rgb=clamp(gui.rgb+color.rgb*(1.0-gui.a),0.0,1.0);\n"
        "#else\n"
        "vec3 straight=gui.a>0.0?clamp(gui.rgb/gui.a,0.0,1.0):vec3(0);"
        "vec3 lin=vec3(texture(dve_degamma,vec2(straight.r,.5)).r,texture(dve_degamma,vec2(straight.g,.5)).r,texture(dve_degamma,vec2(straight.b,.5)).r);"
        "lin=mat3(.6274,.0691,.0164,.3293,.9195,.0880,.0433,.0114,.8956)*lin;"
        "vec3 q=vec3(texture(dve_pq,vec2(lin.r,.5)).r,texture(dve_pq,vec2(lin.g,.5)).r,texture(dve_pq,vec2(lin.b,.5)).r);"
        "color.rgb=clamp(q*gui.a+color.rgb*(1.0-gui.a),0.0,1.0);\n"
        "#endif\n}"
    };
    mask->called=true;mask->failed=!pl_shader_custom(p->sh,&shader);
    return (struct pl_hook_res){.failed=mask->failed,.output=PL_HOOK_SIG_NONE};
}
static pl_tex dve_compose(struct dvbridge_renderer *r,pl_tex input,bool compose)
{
    const struct dvbridge_native_overlay *o=&r->dv.overlay;
    if(!input || (compose && (!o->texture || !o->degamma || !o->pq)))return NULL;
    if(!compose && !ensure_rgb(r))return NULL;
    pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
    if(!fmt || (compose && !pl_tex_recreate(r->gpu,&r->ai_rgb,pl_tex_params(.w=3840,.h=2160,
        .format=fmt,.sampleable=true,.renderable=true))))return NULL;
    if(!compose && !p5_preserve_backing(r))return NULL;
    pl_tex output=compose?r->ai_rgb:r->rgb;
    if(output==input)return NULL;
    struct pl_frame image={.num_planes=1,.planes={{.texture=input,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color=r->dv.output.value.container,
        .crop={0,0,input->params.w,input->params.h}};
    struct pl_frame target=image;target.planes[0].texture=output;
    struct dvbridge_geometry geometry=r->dv.output.value.geometry;
    target.crop=(pl_rect2df){0,0,3840,2160};
    if(input->params.w!=3840 || input->params.h!=2160){
        double sx=(double)input->params.w/geometry.width,sy=(double)input->params.h/geometry.height;
        image.crop=(pl_rect2df){-geometry.x*sx,-geometry.y*sy,
            (3840-geometry.x)*sx,(2160-geometry.y)*sy};
    }
    const unsigned *m=r->dv.output.value.margins;
    struct active_mask mask={.overlay=o,.rect={m[0],m[2],3840-m[1],2160-m[3]}};
    if((input->params.w!=3840 || input->params.h!=2160) && r->dv.enhanced_plan.status==CB1_DVE_READY)
        mask.maximum_pq=dv_ideal_pq(r->dv.enhanced_plan.envelope);
    const struct pl_hook blank={.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&mask,.hook=mask_active_area,.signature=0x4342314456450004ULL};
    const struct pl_hook overlay={.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&mask,.hook=dve_overlay_output,.signature=0x4342314456450001ULL};
    const struct pl_hook *hooks[]={&blank,&overlay};struct pl_render_params params=pl_render_default_params;
    params.min_fbo_precision=32;params.peak_detect_params=NULL;params.dither_params=NULL;
    params.frame_mixer=NULL;params.skip_caching_single_frame=true;params.sigmoid_params=NULL;
    params.cb1_nearest_identity=true;params.cb1_stable_pq=true;params.border=PL_CLEAR_SKIP;
    params.hooks=hooks;params.num_hooks=compose?2:1;
    bool rendered=render_image(r,&image,&target,&params,&mask,NULL,false);
    /* Analysis has retired; final composition owns a new outstanding use. */
    return dv_last_use(r) && rendered?output:NULL;
}

pl_tex dvbridge_render_dv_policy_rgb(struct dvbridge_renderer *r)
{
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);
    if(!out || !out->intermediate)return NULL;
    pl_tex image=out->intermediate;
    if(image->params.w==3840 && image->params.h==2160)return image;
    image=dve_compose(r,image,false);
    if(image)r->dv.output.intermediate=image;
    return image;
}

/* Compose after content analysis, directly into the existing packed transport. */
static bool dve_pack_overlay(struct dvbridge_renderer *r,pl_tex input,pl_tex output,
    bool flip,const uint32_t *packets,unsigned count,bool linear)
{
    struct pl_frame image={.num_planes=1,.planes={{.texture=input,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color=linear?r->reconstructed_color:r->dv.output.value.container,
        .crop={0,0,input->params.w,input->params.h}};
    struct pl_frame target=image;target.planes[0].texture=output;target.planes[0].flipped=flip;
    struct dvbridge_geometry geometry=r->dv.output.value.geometry;
    target.crop=(pl_rect2df){0,0,3840,2160};
    if(input->params.w!=3840 || input->params.h!=2160){
        double sx=(double)input->params.w/geometry.width,sy=(double)input->params.h/geometry.height;
        image.crop=(pl_rect2df){-geometry.x*sx,-geometry.y*sy,
            (3840-geometry.x)*sx,(2160-geometry.y)*sy};
    }
    target.color.transfer=PL_COLOR_TRC_PQ;
    const unsigned *m=r->dv.output.value.margins;
    struct active_mask mask={.rect={m[0],m[2],3840-m[1],2160-m[3]},.packets=packets,.count=count,
        .flip=flip,.overlay=r->dv.enhanced_overlay?&r->dv.overlay:NULL,.straight_overlay=true};
    if(!linear && (input->params.w!=3840 || input->params.h!=2160) &&
       r->dv.enhanced_plan.status==CB1_DVE_READY)
        mask.maximum_pq=dv_ideal_pq(r->dv.enhanced_plan.envelope);
    /* Reuse only an identical source rectangle, without border realignment. */
    if(!linear && !image.crop.x0 && !image.crop.y0 &&
       image.crop.x1==input->params.w && image.crop.y1==input->params.h &&
       (input->params.w!=3840 || input->params.h!=2160))
        mask.reference_source=input;
    const struct pl_hook decode={.stages=PL_HOOK_RGB,.input=PL_HOOK_SIG_COLOR,
        .hook=dve_linear_decode,.signature=0x4342314456450003ULL};
    const struct pl_hook hook={.stages=PL_HOOK_OUTPUT|(mask.reference_source?PL_HOOK_RGB:0),.input=PL_HOOK_SIG_COLOR,
        .priv=&mask,.hook=pack_active_area,.signature=0x4342314456450002ULL};
    const struct pl_hook *hooks[]={&decode,&hook};struct pl_render_params params=pl_render_default_params;
    params.min_fbo_precision=32;params.peak_detect_params=NULL;params.dither_params=NULL;
    params.frame_mixer=NULL;params.skip_caching_single_frame=true;params.sigmoid_params=NULL;
    params.cb1_nearest_identity=true;params.cb1_stable_pq=!linear;params.border=PL_CLEAR_SKIP;
    params.hooks=linear?hooks:hooks+1;params.num_hooks=linear?2:1;
    params.cb1_quad_scaler=!linear && !r->dv.ai_source && r->fragment_quad && r->gpu->glsl.subgroup_size &&
        r->dv.enhanced_plan.status==CB1_DVE_READY && mask.reference_source &&
        input->params.w==1920 && input->params.h==1080;
    if(glGetError()!=GL_NO_ERROR)return false;
    const GLenum caps[]={GL_BLEND,GL_DEPTH_TEST,GL_STENCIL_TEST,GL_SCISSOR_TEST,
        GL_DITHER,GL_CULL_FACE,GL_RASTERIZER_DISCARD,GL_SAMPLE_ALPHA_TO_COVERAGE,GL_SAMPLE_COVERAGE};
    GLboolean enabled[sizeof(caps)/sizeof(*caps)],write_mask[4];glGetBooleanv(GL_COLOR_WRITEMASK,write_mask);
    for(unsigned i=0;i<sizeof(caps)/sizeof(*caps);i++){enabled[i]=glIsEnabled(caps[i]);glDisable(caps[i]);}
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    bool ok=render_image(r,&image,&target,&params,&mask,NULL,false);
    ok=glGetError()==GL_NO_ERROR && ok;
    glColorMask(write_mask[0],write_mask[1],write_mask[2],write_mask[3]);
    for(unsigned i=0;i<sizeof(caps)/sizeof(*caps);i++){
        if(enabled[i])glEnable(caps[i]);else glDisable(caps[i]);
    }
    return glGetError()==GL_NO_ERROR && ok;
}
static bool dve_copy_packed(struct dvbridge_renderer *r,unsigned framebuffer,bool flip,
    const uint32_t *packets,unsigned count)
{
    unsigned first=0,end=2160;
    const unsigned *margins=r->dv.output.value.margins;
    if(r->enhanced_authored && r->fast_chroma && r->dv.output.value.fel_reconstructed &&
       !r->dv.enhanced_overlay && margins[2]<2160 && margins[3]<2160-margins[2]){
        first=margins[2];end=2160-margins[3];
        if(!dve_clear_rows(framebuffer,flip?2160-end:first,flip?2160-first:end))return false;
    }
    GLint read,draw;glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);
    GLboolean scissor=glIsEnabled(GL_SCISSOR_TEST);glDisable(GL_SCISSOR_TEST);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,r->enhanced_packed_fbo);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,framebuffer);
    glBlitFramebuffer(0,first,3840,end,0,flip?2160-first:first,3840,flip?2160-end:end,GL_COLOR_BUFFER_BIT,GL_NEAREST);
    bool ok=glGetError()==GL_NO_ERROR;
    glBindFramebuffer(GL_READ_FRAMEBUFFER,read);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);
    if(scissor)glEnable(GL_SCISSOR_TEST);
    return ok && dvbridge_gl_patch(r->dv.packer,r->enhanced_packed_texture,framebuffer,3840,2160,packets,count,flip);
}
/* Reuse the prepack scratch for only the metadata rows when framebuffer fetch
 * is unavailable. The remaining movie pixels never leave the final target. */
static bool ai_patch_direct(struct dvbridge_renderer *r,unsigned framebuffer,
    const uint32_t *packets,unsigned count,bool flip)
{
    if(pl_opengl_has_ext(pl_opengl_get(r->gpu),"GL_EXT_shader_framebuffer_fetch_non_coherent"))
        return dvbridge_gl_patch_inplace(r->dv.packer,framebuffer,packets,count,flip);
    if(!count || count>5 || !r->enhanced_packed_fbo)return false;
    unsigned rows=(count*3072+3839)/3840;
    GLint read,draw;glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&read);glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);
    GLboolean scissor=glIsEnabled(GL_SCISSOR_TEST);glDisable(GL_SCISSOR_TEST);
    glBindFramebuffer(GL_READ_FRAMEBUFFER,framebuffer);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,r->enhanced_packed_fbo);
    glBlitFramebuffer(0,flip?2160:0,3840,flip?2160-rows:rows,0,0,3840,rows,GL_COLOR_BUFFER_BIT,GL_NEAREST);
    bool ok=glGetError()==GL_NO_ERROR;
    glBindFramebuffer(GL_READ_FRAMEBUFFER,read);glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);
    if(scissor)glEnable(GL_SCISSOR_TEST);
    return ok && dvbridge_gl_patch(r->dv.packer,r->enhanced_packed_texture,framebuffer,3840,2160,packets,count,flip);
}
bool dvbridge_render_dv_policy_resolve(struct dvbridge_renderer *r,pl_tex target,unsigned framebuffer,bool flip)
{
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);
    if(!out || !target || target==out->intermediate || r->resolve_serial==UINT64_MAX ||
       target->params.w!=3840 || target->params.h!=2160 || !target->params.renderable ||
       target->params.format->type!=PL_FMT_UNORM ||
       (target->params.format->num_components!=3 && target->params.format->num_components!=4)){dvbridge_render_dv_policy_cancel(r);return false;}
    /* Transport uses RGB only. Match absent alpha to the real RGB8 framebuffer. */
    unsigned alpha_bits=target->params.format->num_components==3?0:8;
    for(unsigned i=0;i<4;i++)if(target->params.format->component_depth[i]!=(i==3?alpha_bits:8)){dvbridge_render_dv_policy_cancel(r);return false;}
    /* Pinned LP texture formats belong to the public GPU registry. An opaque
     * framebuffer wrap owns a distinct queried format, and cannot be unwrapped
     * as a texture. Its explicit pair remains the native owner's assertion. */
    for(int i=0;i<r->gpu->num_formats;i++)if(target->params.format==r->gpu->formats[i]){
        unsigned attachment;
        if(!pl_opengl_unwrap(r->gpu,target,NULL,NULL,&attachment) || attachment!=framebuffer){
            dvbridge_render_dv_policy_cancel(r);return false;
        }
        break;
    }
    if(!dv_final_framebuffer(framebuffer,alpha_bits)){dvbridge_render_dv_policy_cancel(r);return false;}
    if(r->dv.packed_target){
        if(r->dv.packed_target!=target || r->dv.packed_flip!=flip){dvbridge_render_dv_policy_cancel(r);return false;}
        r->dv.output.value.resolved=true;r->dv.output.value.final_target=target;
        r->dv.output.value.final_framebuffer=framebuffer;
        r->dv.output.resolve_serial=++r->resolve_serial;return true;
    }
    unsigned texture_target,count;
    pl_tex intermediate=out->intermediate;
    const uint32_t *packets=dvbridge_packets(r->pending,&count);
    bool composed=r->dv.enhanced_pixels && r->dv.enhanced_overlay;
    bool ok;
    if(r->dv.ai_direct_target && r->dv.prepacked && r->dv.enhanced_plan.status==CB1_DVE_READY){
        ok=target==r->dv.ai_direct_target && framebuffer==r->dv.ai_direct_framebuffer && flip==r->dv.ai_direct_flip &&
            ai_patch_direct(r,framebuffer,packets,count,flip);
    }else if(r->dv.prepacked && r->dv.enhanced_plan.status==CB1_DVE_READY){
        ok=dve_copy_packed(r,framebuffer,flip,packets,count);
    }else if(!intermediate && r->dv.enhanced_pixels && r->enhanced_skip_aux &&
        r->dv.output.value.policy.adaptive!=DVBRIDGE_ADAPTIVE_A &&
        r->dv.output.value.expansion_reason==CB1_DVE_SOURCE_BOUND && !r->dv.ai_source && r->fragment_quad){
        /* Keep the guard, fusing native PQ recovery and transport in one draw. */
        ok=dve_pack_overlay(r,r->enhanced_input?r->enhanced_input:r->rgb,target,flip,packets,count,r->enhanced_linear);
    }else if(r->fragment_quad && (composed || (intermediate &&
        (intermediate->params.w!=3840 || intermediate->params.h!=2160)))){
        ok=dve_pack_overlay(r,intermediate,target,flip,packets,count,false);
    }else{
        if(composed || (intermediate &&
            (intermediate->params.w!=3840 || intermediate->params.h!=2160))){
            intermediate=dve_compose(r,intermediate,composed);
            if(!intermediate){dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return false;}
        }
        unsigned texture=pl_opengl_unwrap(r->gpu,intermediate,&texture_target,NULL,NULL);
        ok=texture_target==GL_TEXTURE_2D && dvbridge_gl_pack(r->dv.packer,texture,framebuffer,3840,2160,packets,count,flip);
    }
    bool fenced=dv_last_use(r);
    if(!ok || !fenced){dvbridge_render_dv_policy_cancel(r);return false;}
    r->dv.output.value.resolved=true;r->dv.output.value.final_target=target;
    r->dv.output.value.final_framebuffer=framebuffer;
    r->dv.output.resolve_serial=++r->resolve_serial;return true;
}
bool dvbridge_render_dv_policy_commit(struct dvbridge_renderer *r,
    const struct dvbridge_identity *id,pl_tex target,uint64_t serial)
{
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);
    if(!out || !out->value.resolved || !serial || serial!=out->resolve_serial || !target ||
       target!=out->value.final_target || !dvbridge_identity_equal(id,&out->value.identity) || !dvbridge_commit(r->context,r->pending))return false;
    if(r->dv.enhanced_pixels && r->dv.enhanced_plan.status==CB1_DVE_READY){
        r->enhanced_committed=r->dv.enhanced_plan;r->enhanced_pts=r->dv.pts;
        r->enhanced_stream=id->stream;r->enhanced_has_committed=true;
    }else r->enhanced_has_committed=false;
    bool handoff=r->dv.borrowed_storage && r->dv.enhanced_pixels && !r->dv.ai_source &&
        r->dv.enhanced_plan.status==CB1_DVE_READY && r->dv.prepacked && r->enhanced_skip_aux &&
        r->fast_chroma && !r->overlay_visible && !r->dv.enhanced_overlay &&
        out->value.policy.adaptive!=DVBRIDGE_ADAPTIVE_A &&
        out->value.geometry.source_width==3840 && out->value.geometry.source_height==2160 &&
        !out->value.geometry.x && !out->value.geometry.y &&
        out->value.geometry.width==3840 && out->value.geometry.height==2160;
    r->dv_committed=out->value;r->dv_has_committed=true;dvbridge_render_dv_policy_cancel(r);
    r->dv.ordered_handoff=handoff;return true;
}
bool dvbridge_render_dv_policy_committed(const struct dvbridge_renderer *r,struct dvbridge_dv_policy_snapshot *out)
{ if(!r || !out || !r->dv_has_committed)return false;*out=r->dv_committed;return true; }

static AVDOVIMetadata *ai_output_metadata(const struct cb1_ai_result *prediction,
    const struct pl_color_space *color,const unsigned margins[4],size_t *bytes)
{
    const struct cb1_l1l3 *raw=&prediction->raw;
    if(raw->l1_min>raw->l1_avg || raw->l1_avg>raw->l1_max || !raw->l1_max ||
       raw->l1_max>4095 || raw->l3_min>4095 || raw->l3_max>4095 || raw->l3_avg>4095)return NULL;
    AVDOVIMetadata *m=av_dovi_metadata_alloc(bytes);if(!m)return NULL;
    av_dovi_get_header(m)->disable_residual_flag=1;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);c->signal_eotf=65535;
    /* Missing mastering data stays unknown. PQ capacity is a transport envelope. */
    double peak=color->hdr.max_luma;
    c->source_max_pq=isfinite(peak) && peak>0 && peak<=10000?dv_wire_code(dv_ideal_pq(peak)):4095;
    c->source_min_pq=0;c->scene_refresh_flag=0;m->num_ext_blocks=3;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0),*l5=av_dovi_get_ext(m,1),*l3=av_dovi_get_ext(m,2);
    l1->level=1;l1->l1.min_pq=raw->l1_min;l1->l1.max_pq=raw->l1_max;l1->l1.avg_pq=raw->l1_avg;
    l5->level=5;l5->l5.left_offset=margins[0];l5->l5.right_offset=margins[1];
    l5->l5.top_offset=margins[2];l5->l5.bottom_offset=margins[3];
    l3->level=3;l3->dvbridge_raw_magic=0x41424456;l3->dvbridge_original_length=5;
    l3->l3.min_pq_offset=raw->l3_min;l3->l3.max_pq_offset=raw->l3_max;l3->l3.avg_pq_offset=raw->l3_avg;
    uint64_t bits=(uint64_t)raw->l3_min<<28|(uint64_t)raw->l3_max<<16|(uint64_t)raw->l3_avg<<4;
    for(unsigned i=0;i<5;++i)l3->dvbridge_original_bytes[i]=bits>>(32-8*i);
    return m;
}

/* Preserve native PQ for whole-frame rejection; publish expansion and its
 * content-only statistic alongside the native conversion. */
static struct pl_hook_res ai_enhanced_output(void *priv,const struct pl_hook_params *p)
{
    struct active_mask *mask=priv;struct dvbridge_renderer *r=mask->ai_renderer;
    const struct cb1_dv_enhanced_plan *plan=&r->dv.enhanced_plan;
    float curve[257],colors[67],bounds[2]={plan->master,plan->envelope},matrix[9];
    float master=dv_ideal_pq(plan->master);
    float display_peak=plan->target;
    uint32_t ai_flip=r->dv.ai_direct_flip;
    int guidance[2]={0};
    for(unsigned i=0;i<257;i++)curve[i]=plan->extra[i];
    for(unsigned i=0;i<67;i++){
        colors[i]=plan->color[i];guidance[0]|=colors[i]!=0;guidance[1]|=i>=2 && colors[i]!=0;
    }
    pl_matrix3x3 lms=pl_ipt_rgb2lms(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++)matrix[j*3+i]=lms.m[i][j];
    struct pl_shader_var vars[]={
        {.var={.name="extra",.type=PL_VAR_FLOAT,.dim_v=1,.dim_m=1,.dim_a=257},.data=curve,.dynamic=true},
        {.var={.name="colors",.type=PL_VAR_FLOAT,.dim_v=1,.dim_m=1,.dim_a=67},.data=colors,.dynamic=true},
        {.var=pl_var_vec2("bounds"),.data=bounds,.dynamic=true},
        {.var=pl_var_float("master_pq"),.data=&master,.dynamic=true},
        {.var=pl_var_mat3("lms"),.data=matrix,.dynamic=true},
        {.var={.name="guidance",.type=PL_VAR_SINT,.dim_v=2,.dim_m=1,.dim_a=1},.data=guidance,.dynamic=true},
        {.var=pl_var_vec4("ai_area"),.data=mask->rect,.dynamic=true},
        {.var=pl_var_uint("ai_flip"),.data=&ai_flip,.dynamic=true},
        {.var=pl_var_float("display_peak"),.data=&display_peak,.dynamic=true},
    };
    struct pl_shader_desc desc[2];unsigned descriptors=0;
    const char *names[]={"pq_decode","pq_encode"};
    if(r->enhanced_pq_lookup)for(unsigned i=0;i<2;i++)desc[descriptors++]=(struct pl_shader_desc){
        .desc={.name=names[i],.type=PL_DESC_SAMPLED_TEX},
        .binding={.object=r->processing.pq_texture[i],.sample_mode=PL_TEX_SAMPLE_LINEAR}};
    char header[sizeof(dve_math)+512];
    /* Clipped RGB, positive LMS coefficients and expansion keep LUT inputs nonnegative. */
    snprintf(header,sizeof(header),"%s%s%s%s#define CB1_AI_NONNEGATIVE_PQ 1\n#define color_guidance (guidance.x!=0)\n#define hue_guidance (guidance.y!=0)\n%s",
        r->ai_enhanced_prepack?"#define CB1_AI_PREPACK 1\n":"",
        r->enhanced_pq_lookup?"#define CB1_DVE_PQ_LOOKUP 1\n":"",
        r->ai_enhanced_prepack && r->dv.ai_direct_lean?"#define CB1_AI_SKIP_AUX 1\n":"",
        r->ai_enhanced_prepack?"#define CB1_AI_QUAD_STATS 1\n":"",dve_math);
    struct pl_custom_shader shader={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .prelude=r->ai_enhanced_prepack?
            "#extension GL_KHR_shader_subgroup_basic:require\n#extension GL_KHR_shader_subgroup_quad:require\n"
            "layout(rgba16f,binding=0)writeonly uniform highp image2D cb1_ai_expanded;\n"
            "layout(rgba16ui,binding=1)writeonly uniform highp uimage2D cb1_ai_statistics;\n"
            "layout(rgba16f,binding=2)writeonly uniform highp image2D cb1_ai_native;\n":
            "layout(rgba32f,binding=0)writeonly uniform highp image2D cb1_ai_expanded;\n"
            "layout(r32f,binding=1)writeonly uniform highp image2D cb1_ai_statistics;\n",
        .header=header,.variables=vars,.num_variables=9,
        .descriptors=desc,.num_descriptors=descriptors,
        .body="{ivec2 pos=ivec2(gl_FragCoord.xy);if(ai_flip!=0u)pos.y=2159-pos.y;vec3 q=clamp(color.rgb,0.0,1.0);float s=-1.0;"
            "\n#ifdef CB1_AI_PREPACK\nimageStore(cb1_ai_native,pos,vec4(q,color.a));\n#endif\n"
            "bool bad=any(isnan(color.rgb))||any(isinf(color.rgb));"
            "if(!bad){vec3 rgb=vec3(decode_pq(q.r),decode_pq(q.g),decode_pq(q.b));"
            "float y=dot(rgb,vec3(.262700212,.677998072,.059301716));"
            "bool bound=y>bounds.x*1.0001+.001||max(rgb.r,max(rgb.g,rgb.b))>bounds.y*1.0001+.001;"
            "vec3 expanded=expansion(rgb);if(any(notEqual(expanded,rgb)))"
            "q=vec3(encode_pq(expanded.r),encode_pq(expanded.g),encode_pq(expanded.b));"
            "vec3 cone=lms*expanded;s=encode_pq(max(cone.r,max(cone.g,cone.b)));if(bound)s+=2.0;}"
            "\n#ifndef CB1_AI_SKIP_AUX\nimageStore(cb1_ai_expanded,pos,vec4(q,color.a));\n#endif\n"
            "\n#ifdef CB1_AI_QUAD_STATS\n"
            "bool inside=float(pos.x)>=ai_area.x&&float(pos.y)>=ai_area.y&&float(pos.x)<ai_area.z&&float(pos.y)<ai_area.w;"
            "float actual=s>=2.0?s-2.0:s;"
            "vec4 a=inside?vec4(bad?-2.0:s>=2.0?-1.0:actual,bad?0.0:actual,bad?0.0:actual,1.0):"
            "vec4(uintBitsToFloat(0x7f800000u),0.0,uintBitsToFloat(0xff800000u),0.0);"
            "vec4 b=subgroupQuadSwapHorizontal(a);"
            "a=vec4(min(a.x,b.x),a.y+b.y,max(a.z,b.z),a.w+b.w);b=subgroupQuadSwapVertical(a);"
            "a=vec4(min(a.x,b.x),a.y+b.y,max(a.z,b.z),a.w+b.w);"
            "if((pos.x&1)==0&&(pos.y&1)==0){uint flags=uint(a.w)|(a.x<-.5?8u:0u)|(a.x<-1.5?16u:0u);"
            "imageStore(cb1_ai_statistics,pos/2,uvec4(floor(clamp(vec3(a.x,a.y*.25,a.z),0.0,1.0)*65535.0+.5),flags));}\n"
            "#else\nimageStore(cb1_ai_statistics,pos,vec4(s));\n#endif\n"
            "\n#ifdef CB1_AI_PREPACK\ncolor.rgb=q;\n#endif\n}",
        .description="HDR10 Enhanced conversion and expansion"};
    bool ok=p->stage==PL_HOOK_OUTPUT && !pl_shader_is_compute(p->sh) && pl_shader_custom(p->sh,&shader);
    if(ok && r->ai_enhanced_prepack)return pack_active_area(mask,p);
    return (struct pl_hook_res){.failed=!ok,.output=PL_HOOK_SIG_NONE};
}

static struct pl_hook_res ai_native_transport(void *priv,const struct pl_hook_params *p)
{
    (void)priv;
    /* Native UNORM16 sampling to the carrier's 12-bit code normalization. */
    float scale=65535.f/65520.f;
    struct pl_shader_var v={.var=pl_var_float("ai_source_scale"),.data=&scale,.dynamic=true};
    bool ok=pl_shader_custom(p->sh,&(struct pl_custom_shader){
        .input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,.output_w=3840,.output_h=2160,
        .variables=&v,.num_variables=1,.body="color.rgb*=ai_source_scale;"});
    return (struct pl_hook_res){.failed=!ok,.output=PL_HOOK_SIG_COLOR,.sh=p->sh,
        .repr=pl_color_repr_rgb,.color=p->color,.components=3,.rect=p->rect};
}

static bool ai_render_pixels(struct dvbridge_renderer *r,
    const struct pl_frame *source,struct dvbridge_geometry g,
    pl_tex packed,bool flip,const struct dvbridge_native_overlay *overlay)
{
    bool native=r->dv.active && r->dv.ai_source && r->dv.enhanced_plan.status==CB1_DVE_READY &&
        r->enhanced_rgb && (r->enhanced_rgb->params.w!=3840 || r->enhanced_rgb->params.h!=2160);
    if(native){
        pl_fmt fmt=pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        if(!fmt || !pl_tex_recreate(r->gpu,&r->native_picture,pl_tex_params(
            .w=g.source_width,.h=g.source_height,.format=fmt,.sampleable=true,.renderable=true)))return false;
        g.x=g.y=0;g.width=g.source_width;g.height=g.source_height;
    }
    bool fused=r->dv.active && r->dv.ai_source &&
        r->dv.enhanced_plan.status==CB1_DVE_READY && r->ai_enhanced_fused;
    bool prepack=fused && r->ai_enhanced_prepack;
    bool direct=prepack && r->dv.ai_direct_target;
    if(direct)flip=r->dv.ai_direct_flip;
    pl_tex rgb=native?r->native_picture:prepack?r->ai_enhanced_native:r->rgb;
    if(!packed && !prepack && !p5_preserve_backing(r))return false;
    /* Keep the native PQ result at FP32 precision for shared validation. */
    struct pl_frame image=*source,target={.num_planes=1,
        .planes={{.texture=packed?packed:direct?r->dv.ai_direct_target:prepack?r->ai_enhanced_packed:rgb,
            .flipped=(packed || direct) && flip,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color=source->color,.crop={g.x,g.y,g.x+g.width,g.y+g.height}};
    if(packed || prepack){
        /* Cover transport borders without materializing a padded RGB image. */
        float sx=(image.crop.x1-image.crop.x0)/g.width,sy=(image.crop.y1-image.crop.y0)/g.height;
        image.crop.x0-=g.x*sx;image.crop.y0-=g.y*sy;
        image.crop.x1+=(3840-g.x-g.width)*sx;image.crop.y1+=(2160-g.y-g.height)*sy;
        target.crop=(pl_rect2df){0,0,3840,2160};
    }
    bool raw=false;
#ifdef CB1_HAS_HDR10_AI
    raw=packed && !r->dv.active && !overlay && r->fast_chroma &&
        g.source_width==3840 && g.source_height==2160 && !g.x && !g.y && g.width==3840 && g.height==2160 &&
        source->crop.x0==0 && source->crop.y0==0 &&
        cb1_hdr10_ingress_validate(source)==CB1_AI_READY &&
        source->planes[1].texture->params.w==1920 && source->planes[1].texture->params.h==1080;
#endif
    struct pl_render_params params=pl_render_default_params;
    params.cb1_fast_chroma=r->fast_chroma;
    if (r->processing_optimizations && cb1_processing_prepare(&r->processing,r->gpu,
            source,NULL,0,false,CB1_PROCESSING_ALL&~r->processing_failed_groups))
        params.cb1_processing=&r->processing.view;
    params.min_fbo_precision=32;params.peak_detect_params=NULL;params.dither_params=NULL;
    params.frame_mixer=NULL;params.skip_caching_single_frame=true;params.border=PL_CLEAR_SKIP;
    params.cb1_nearest_identity=true;params.cb1_stable_pq=true;params.cb1_fp32_scaler_lut=true;
    params.sigmoid_params=NULL;params.disable_linear_scaling=raw;
    struct active_mask mask={.rect={g.x,g.y,g.x+g.width,g.y+g.height},.flip=flip,.source_domain=raw};
    mask.ai_renderer=fused?r:NULL;
    mask.overlay=overlay;
    mask.straight_overlay=r->optimized_dv && overlay && !overlay->input_pq;
    if(packed)mask.packets=dvbridge_packets(r->pending,&mask.count);
    const uint32_t empty_packets[640]={0};
    if(prepack)mask.packets=empty_packets;
    const struct pl_hook reference={.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&mask,.hook=packed?pack_active_area:mask_active_area,
        .signature=packed?0x4342314149500001ULL:0x4342314149520001ULL};
    const struct pl_hook expansion={.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&mask,.hook=ai_enhanced_output,.signature=prepack?0x4342314149450002ULL:0x4342314149450001ULL};
    const struct pl_hook native_transport={.stages=PL_HOOK_NATIVE,.input=PL_HOOK_SIG_COLOR,
        .hook=ai_native_transport,.signature=0x43423141494e0001ULL};
    const struct pl_hook *hooks[]={&native_transport,&reference,&expansion};
    params.hooks=raw?hooks:hooks+1;params.num_hooks=raw || fused?2:1;
    if(!packed && (g.x || g.y || g.width!=(unsigned)rgb->params.w || g.height!=(unsigned)rgb->params.h)){
        pl_tex_clear(r->gpu,rgb,(float[4]){0,0,0,1});
        if(fused){
            pl_tex_clear(r->gpu,r->enhanced_rgb,(float[4]){0,0,0,1});
            pl_tex_clear_ex(r->gpu,r->ai_enhanced_stats,(union pl_clear_color){0});
        }
    }
    GLint bindings[3][6];
    const GLenum queries[]={GL_IMAGE_BINDING_NAME,GL_IMAGE_BINDING_LEVEL,GL_IMAGE_BINDING_LAYERED,
        GL_IMAGE_BINDING_LAYER,GL_IMAGE_BINDING_ACCESS,GL_IMAGE_BINDING_FORMAT};
    if(fused){
        for(unsigned unit=0;unit<(prepack?3:2);unit++)for(unsigned i=0;i<6;i++)glGetIntegeri_v(queries[i],unit,&bindings[unit][i]);
        glBindImageTexture(0,r->enhanced_texture,0,GL_FALSE,0,GL_WRITE_ONLY,prepack?GL_RGBA16F:GL_RGBA32F);
        glBindImageTexture(1,r->ai_enhanced_stats_texture,0,GL_FALSE,0,GL_WRITE_ONLY,
            prepack?GL_RGBA16UI:GL_R32F);
        if(prepack)glBindImageTexture(2,r->ai_enhanced_native_texture,0,GL_FALSE,0,GL_WRITE_ONLY,GL_RGBA16F);
    }
    bool ok=render_image(r,&image,&target,&params,&mask,NULL,false);
    if(fused){
        glMemoryBarrier(GL_SHADER_IMAGE_ACCESS_BARRIER_BIT|GL_TEXTURE_FETCH_BARRIER_BIT|GL_FRAMEBUFFER_BARRIER_BIT);
        for(unsigned unit=0;unit<(prepack?3:2);unit++)glBindImageTexture(unit,bindings[unit][0],bindings[unit][1],
            bindings[unit][2],bindings[unit][3],bindings[unit][4],bindings[unit][5]);
        ok=ok && glGetError()==GL_NO_ERROR;
    }
    if(!ok)return false;
    r->reconstructed_color=source->color;
    r->dv.output.intermediate=packed?NULL:rgb;
    r->ready=true;return true;
}

static struct dvbridge_candidate *ai_prepare_candidate(struct dvbridge_renderer *r,
    const AVDOVIMetadata *metadata,size_t bytes,const struct cb1_ai_result *prediction)
{
    return dvbridge_prepare_output(r->context,metadata,bytes,prediction->pts,
        (struct dvbridge_geometry){3840,2160,0,0,3840,2160},false,
        !r->dv_has_committed || r->dv_committed.identity.stream!=prediction->id.stream ||
        r->dv_committed.identity.revision!=prediction->id.revision);
}

static bool ai_enhanced_plan(struct cb1_dv_enhanced_plan *plan,
    AVDOVIMetadata *metadata,size_t bytes,const struct cb1_ai_result *prediction,
    const struct pl_color_space *color,const struct dvbridge_policy *policy)
{
    struct dvbridge_creative_plan creative;
    if(dvbridge_creative_resolve(&creative,metadata,bytes,policy)==DVBRIDGE_CREATIVE_INVALID)return false;
    struct cb1_dv_enhanced_source guidance={.master=color->hdr.max_luma>0?color->hdr.max_luma:10000,
        .l1_present=creative.l1_present};
    memcpy(guidance.analysis,creative.analysis,sizeof(guidance.analysis));
    return cb1_dv_enhanced_build_ai(plan,&guidance,policy)!=CB1_DVE_INVALID;
}

/* HDR10 enters the shared executor as PQ pixels, never synthetic DV reshaping. */
static pl_tex ai_enhanced(struct dvbridge_renderer *r,const struct dvbridge_policy *policy,
    const struct cb1_ai_result *prediction,const struct pl_frame *source,struct dvbridge_geometry g,
    AVDOVIMetadata *metadata,size_t bytes,const unsigned margins[4],pl_tex direct,bool flip,
    const struct dvbridge_native_overlay *overlay)
{
    struct cb1_dv_enhanced_plan plan;
    if(!ai_enhanced_plan(&plan,metadata,bytes,prediction,&source->color,policy)){
        av_free(metadata);return NULL;
    }
    bool reset=!r->enhanced_has_committed || r->enhanced_stream!=prediction->id.stream ||
        prediction->pts<r->enhanced_pts || prediction->pts-r->enhanced_pts>1;
    cb1_dv_enhanced_transition(&plan,&r->enhanced_committed,prediction->pts-r->enhanced_pts,reset);
    bool pixels=plan.status==CB1_DVE_READY;
    r->enhanced_linear=false;
    r->enhanced_authored=false;
    r->enhanced_skip_aux=false;
    r->enhanced_authored_curve=false;
    if(!r->owner){av_free(metadata);return NULL;}
    bool native=pixels && (g.source_width!=3840 || g.source_height!=2160);
    bool allocated=pixels?dve_allocate(r,native?g.source_width:3840,native?g.source_height:2160,!native,false):dv_allocate_transport(r);
    if(!allocated && pixels && r->ai_enhanced_fused && !pl_gpu_is_failed(r->gpu)){
        r->ai_fusion_failed=true;
        allocated=dve_allocate(r,3840,2160,false,false);
    }
    if(!allocated){av_free(metadata);return NULL;}
    if(direct && pixels && !native && !r->ai_enhanced_prepack){av_free(metadata);return NULL;}
    struct dvbridge_dv_slot *s=&r->dv;
    s->active=true;s->ai_source=true;s->pts=prediction->pts;
    s->output_metadata=metadata;s->output_bytes=bytes;
    s->enhanced_pixels=true;s->enhanced_plan=plan;
    s->ai_direct_target=direct;s->ai_direct_flip=direct && flip;
    s->ai_direct_lean=direct && pixels && !overlay && !native;
    s->enhanced_overlay=overlay!=NULL;if(overlay)s->overlay=*overlay;
    bool rendered=ai_render_pixels(r,source,g,NULL,false,overlay);
    if(!rendered && !direct && pixels && r->ai_enhanced_fused && !pl_gpu_is_failed(r->gpu)){
        /* Same-context retry keeps all submitted resources leased until the
         * final fence. Only the optional fusion is disabled. */
        r->ai_fusion_failed=true;r->ai_enhanced_fused=r->ai_enhanced_prepack=false;
        pl_renderer_reset_errors(r->renderer,NULL);
        rendered=dve_program(r,r->enhanced_pq_lookup) && ai_render_pixels(r,source,g,NULL,false,NULL);
    }
    if(!rendered){
        dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return NULL;
    }
    s->output.value=(struct dvbridge_dv_policy_snapshot){
        .identity={prediction->id.stream,prediction->id.picture,prediction->id.revision},.policy=*policy,
        .output_generation=DVBRIDGE_ETSI_LEGACY_LITERAL,.geometry=g,.container=source->color,
        .nominal_max_nits=source->color.hdr.max_luma,.pixel_algorithm=CB1_DVE_ALGORITHM,
        .expansion_reason=plan.reason,.source_reference_nits=source->color.hdr.max_luma,
        .display_reference_nits=plan.target,
        .l1={prediction->raw.l1_min,prediction->raw.l1_max,prediction->raw.l1_avg},
        .source_pq={0,av_dovi_get_color(metadata)->source_max_pq}};
    memcpy(s->output.value.margins,margins,sizeof(s->output.value.margins));
    r->pending=ai_prepare_candidate(r,metadata,bytes,prediction);
    s->output.output_metadata=metadata;s->output.bytes=bytes;s->output.candidate=r->pending;
    r->policy_ready=false;r->packed=false;
    if(!r->pending){dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return NULL;}
    if(pixels){
        s->output.value.nominal_max_nits=plan.envelope;
        const unsigned native_margins[4]={0};
        if(!dve_run(r,&plan,r->ai_enhanced_fused?r->ai_enhanced_stats:native?r->native_picture:r->rgb,
            native?native_margins:margins)){
            dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return NULL;
        }
        s->output.intermediate=r->enhanced_rgb;s->ready=r->ready=false;
    }else{
        if(!dv_last_use(r)){dvbridge_render_dv_policy_cancel(r);return NULL;}
        s->ready=r->ready=true;
    }
    return s->output.intermediate;
}

/* A full-raster no-headroom plan changes metadata only, not HDR10 pixels. */
static bool ai_identity_transport(const struct dvbridge_policy *policy,const struct pl_frame *source,
    const struct dvbridge_geometry *g,const struct dvbridge_native_overlay *overlay)
{
#ifdef CB1_HAS_HDR10_AI
    if(!policy || policy->mode!=DVBRIDGE_MODE_ENHANCED_DV || policy->adaptive!=DVBRIDGE_ADAPTIVE_A ||
       dvbridge_policy_validate(policy)!=DVBRIDGE_POLICY_VALID || !source || !g || overlay ||
       g->source_width!=3840 || g->source_height!=2160 || g->x || g->y || g->width!=3840 || g->height!=2160 ||
       source->crop.x0 || source->crop.y0 || cb1_hdr10_ingress_validate(source)!=CB1_AI_READY ||
       source->planes[1].texture->params.w!=1920 || source->planes[1].texture->params.h!=1080)return false;
    double master=source->color.hdr.max_luma;
    if(!isfinite(master) || master<0 || master>10000)return false;
    if(!master)master=10000;
    return master>10 && policy->tv.peak_nits<=master;
#else
    (void)policy;(void)source;(void)g;(void)overlay;return false;
#endif
}

static pl_tex render_hdr10_ai(struct dvbridge_renderer *r,const struct dvbridge_policy *policy,
    const struct cb1_ai_result *prediction,const struct pl_frame *source,const struct dvbridge_geometry *geometry,
    pl_tex packed,bool flip,const struct dvbridge_native_overlay *overlay)
{
    if(!r)return NULL;
    bool identity=packed && ai_identity_transport(policy,source,geometry,overlay);
    if((!packed || !policy || (policy->mode!=DVBRIDGE_MODE_STANDARD && !identity)) && !ensure_rgb(r))return NULL;
    if(r->dv.active){dvbridge_render_dv_policy_cancel(r);return NULL;}
    dvbridge_render_policy_cancel(r);dvbridge_candidate_destroy(r->pending);r->pending=NULL;r->packed=false;
    if(!policy || !prediction || !source || !geometry || prediction->id.revision!=policy->revision ||
       !isfinite(prediction->pts) || prediction->pts<0 || dvbridge_policy_validate(policy)!=DVBRIDGE_POLICY_VALID ||
       (policy->mode!=DVBRIDGE_MODE_STANDARD && policy->mode!=DVBRIDGE_MODE_ENHANCED_DV) ||
       source->rotation || source->num_overlays ||
       source->profile.len || source->icc || source->lut || source->enhancement_layer || source->repr.dovi ||
       (source->repr.sys!=PL_COLOR_SYSTEM_RGB && source->repr.sys!=PL_COLOR_SYSTEM_BT_2020_NC) ||
       source->color.transfer!=PL_COLOR_TRC_PQ ||
       source->color.primaries!=PL_COLOR_PRIM_BT_2020 || source->num_planes<1 || source->num_planes>4 ||
       !isfinite(source->color.hdr.max_luma) || !isfinite(source->color.hdr.min_luma) ||
       !isfinite(source->color.hdr.max_cll) || !isfinite(source->color.hdr.max_fall) ||
       source->color.hdr.min_luma<0 || source->color.hdr.max_luma<0 || source->color.hdr.max_luma>10000 ||
       (source->color.hdr.max_luma>0 && source->color.hdr.min_luma>source->color.hdr.max_luma) ||
       source->crop.x1-source->crop.x0!=geometry->source_width ||
       source->crop.y1-source->crop.y0!=geometry->source_height)return NULL;
    for(int i=0;i<source->num_planes;++i)if(!source->planes[i].texture)return NULL;
    const struct dvbridge_geometry g=*geometry;
    if(g.source_width<=0 || g.source_width>3840 || g.source_height<=0 || g.source_height>2160 ||
       g.x<0 || g.y<0 || g.width<=0 || g.width>3840-g.x || g.height<=0 || g.height>2160-g.y ||
       (g.x&1) || (g.width&1) || fabs((double)g.width*g.source_height/g.source_width-g.height)>1.01)return NULL;
    unsigned margins[4]={g.x,3840-g.x-g.width,g.y,2160-g.y-g.height};size_t bytes;
    AVDOVIMetadata *metadata=ai_output_metadata(prediction,&source->color,margins,&bytes);if(!metadata)return NULL;
    struct cb1_dv_enhanced_plan identity_plan;
    if(identity && (!ai_enhanced_plan(&identity_plan,metadata,bytes,prediction,&source->color,policy) ||
        identity_plan.status!=CB1_DVE_IDENTITY || identity_plan.reason!=CB1_DVE_NO_HEADROOM)){
        av_free(metadata);return NULL;
    }
    if(policy->mode==DVBRIDGE_MODE_ENHANCED_DV && !identity)
        return ai_enhanced(r,policy,prediction,source,g,metadata,bytes,margins,packed,flip,overlay);
    if(!r->owner || !dv_allocate_transport(r)){av_free(metadata);return NULL;}
    /* Standard metadata is already complete; the output hook needs its exact packets. */
    if(packed && !(r->pending=ai_prepare_candidate(r,metadata,bytes,prediction))){
        r->dv.active=true;dvbridge_render_dv_policy_cancel(r);av_free(metadata);return NULL;
    }
    if(!ai_render_pixels(r,source,g,packed,flip,overlay)){
        r->dv.active=true;dv_last_use(r);dvbridge_render_dv_policy_cancel(r);
        av_free(metadata);return NULL;
    }
    struct dvbridge_dv_slot *s=&r->dv;s->active=true;s->pts=prediction->pts;
    s->output.value=(struct dvbridge_dv_policy_snapshot){
        .identity={prediction->id.stream,prediction->id.picture,prediction->id.revision},.policy=*policy,
        .source_cm_version=0,.output_generation=DVBRIDGE_ETSI_LEGACY_LITERAL,.geometry=g,
        .container=r->reconstructed_color,.nominal_target=source->color,
        .nominal_max_nits=source->color.hdr.max_luma};
    s->output.value.source_pq[0]=av_dovi_get_color(metadata)->source_min_pq;
    s->output.value.source_pq[1]=av_dovi_get_color(metadata)->source_max_pq;
    if(identity){
        s->ai_source=s->enhanced_pixels=true;s->enhanced_plan=identity_plan;
        s->output.value.pixel_algorithm=CB1_DVE_ALGORITHM;
        s->output.value.expansion_reason=identity_plan.reason;
        s->output.value.source_reference_nits=source->color.hdr.max_luma;
        s->output.value.display_reference_nits=identity_plan.target;
    }
    memcpy(s->output.value.margins,margins,sizeof(margins));r->policy_ready=false;
    s->output_metadata=metadata;s->output_bytes=bytes;
    if(!packed)r->pending=ai_prepare_candidate(r,metadata,bytes,prediction);
    if(!r->pending || !dv_last_use(r)){dvbridge_render_dv_policy_cancel(r);return NULL;}
    s->output.output_metadata=metadata;s->output.bytes=bytes;s->output.candidate=r->pending;
    s->packed_target=packed;s->packed_flip=flip;
    s->output.value.l1[0]=prediction->raw.l1_min;s->output.value.l1[1]=prediction->raw.l1_max;
    s->output.value.l1[2]=prediction->raw.l1_avg;s->ready=true;
    r->packed=packed!=NULL;return packed?packed:s->output.intermediate;
}

pl_tex dvbridge_render_hdr10_ai_rgb(struct dvbridge_renderer *r,const struct dvbridge_policy *policy,
    const struct cb1_ai_result *prediction,const struct pl_frame *source,const struct dvbridge_geometry *geometry)
{
    return render_hdr10_ai(r,policy,prediction,source,geometry,NULL,false,NULL);
}

/* Private optional API: full-raster Standard AI only; caller retains output/imports. */
bool dvbridge_render_hdr10_ai_packed(struct dvbridge_renderer *r,const struct dvbridge_policy *policy,
    const struct cb1_ai_result *prediction,const struct pl_frame *source,const struct dvbridge_geometry *geometry,
    pl_tex target,unsigned framebuffer,bool flip)
{
    return dvbridge_render_hdr10_ai_packed_overlay(r,policy,prediction,source,geometry,target,framebuffer,flip,NULL);
}

bool dvbridge_render_hdr10_ai_packed_overlay(struct dvbridge_renderer *r,const struct dvbridge_policy *policy,
    const struct cb1_ai_result *prediction,const struct pl_frame *source,const struct dvbridge_geometry *geometry,
    pl_tex target,unsigned framebuffer,bool flip,const struct dvbridge_native_overlay *overlay)
{
    /* Capability/admission rejection does not touch GL or an existing prepared output. */
    bool rgb_scanout=policy && (policy->mode==DVBRIDGE_MODE_STANDARD || policy->mode==DVBRIDGE_MODE_ENHANCED_DV) && r && r->fragment_quad &&
        target && target->params.w==3840 && target->params.h==2160 && target->params.renderable &&
        target->params.format->type==PL_FMT_UNORM && target->params.format->num_components==3 &&
        target->params.format->component_depth[0]==8 && target->params.format->component_depth[1]==8 &&
        target->params.format->component_depth[2]==8;
    if(!policy || (policy->mode!=DVBRIDGE_MODE_STANDARD && policy->mode!=DVBRIDGE_MODE_ENHANCED_DV) || !geometry ||
       (policy->mode==DVBRIDGE_MODE_STANDARD && (geometry->x || geometry->y || geometry->width!=3840 || geometry->height!=2160) &&
        (!r || !r->optimized_dv || geometry->width!=geometry->source_width || geometry->height!=geometry->source_height)) ||
       (!packed_transport_supported(r,target,false) && !rgb_scanout) || !overlay_valid(overlay))return false;
    if(policy->mode==DVBRIDGE_MODE_ENHANCED_DV && !r->fragment_quad)return false;
    if(!source || source->num_planes<1 || source->num_planes>4)return false;
    for(int p=0;p<source->num_planes;p++)
        if(!source->planes[p].texture || source->planes[p].texture==target)return false;
    if(glGetError()!=GL_NO_ERROR)return false;
    /* Match the existing resolve contract: registered texture/FBO pairs are
     * checked; an opaque framebuffer wrap carries the owner's explicit FBO. */
    GLuint output_texture=0;
    for(int i=0;i<r->gpu->num_formats;i++)if(target->params.format==r->gpu->formats[i]){
        unsigned actual_framebuffer=0;
        output_texture=pl_opengl_unwrap(r->gpu,target,NULL,NULL,&actual_framebuffer);
        if(!output_texture || actual_framebuffer!=framebuffer)return false;
        break;
    }
    if(!dv_final_framebuffer(framebuffer,rgb_scanout?0:8))return false;
    /* Separate wrappers can still alias. The pinned public unwrap API cannot
     * unwrap pseudo-textures, so inspect the explicitly owned FBO attachment. */
    if(!output_texture && framebuffer){
        GLint draw,type=0,name=0;glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&draw);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,framebuffer);
        glGetFramebufferAttachmentParameteriv(GL_DRAW_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,
            GL_FRAMEBUFFER_ATTACHMENT_OBJECT_TYPE,&type);
        if(type==GL_TEXTURE)glGetFramebufferAttachmentParameteriv(GL_DRAW_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,
            GL_FRAMEBUFFER_ATTACHMENT_OBJECT_NAME,&name);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);
        if(type==GL_TEXTURE)output_texture=(GLuint)name;
        else if(type!=GL_RENDERBUFFER)return false;
    }
    bool alias=false;
    for(int p=0;p<source->num_planes;p++){
        GLuint input_texture=pl_opengl_unwrap(r->gpu,source->planes[p].texture,NULL,NULL,NULL);
        alias=alias || !input_texture || (output_texture && input_texture==output_texture);
    }
    if(glGetError()!=GL_NO_ERROR || alias)return false;
    const GLenum caps[]={GL_BLEND,GL_DEPTH_TEST,GL_STENCIL_TEST,GL_SCISSOR_TEST,
        GL_DITHER,GL_CULL_FACE,GL_RASTERIZER_DISCARD,GL_SAMPLE_ALPHA_TO_COVERAGE,GL_SAMPLE_COVERAGE};
    GLboolean enabled[sizeof(caps)/sizeof(*caps)],mask[4];glGetBooleanv(GL_COLOR_WRITEMASK,mask);
    for(unsigned i=0;i<sizeof(caps)/sizeof(*caps);i++){enabled[i]=glIsEnabled(caps[i]);glDisable(caps[i]);}
    glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
    bool ok=render_hdr10_ai(r,policy,prediction,source,geometry,target,flip,overlay)!=NULL;
    if(ok && policy->mode==DVBRIDGE_MODE_ENHANCED_DV)r->dv.ai_direct_framebuffer=framebuffer;
    ok=glGetError()==GL_NO_ERROR && ok;
    glColorMask(mask[0],mask[1],mask[2],mask[3]);
    for(unsigned i=0;i<sizeof(caps)/sizeof(*caps);i++){
        if(enabled[i])glEnable(caps[i]);else glDisable(caps[i]);
    }
    ok=glGetError()==GL_NO_ERROR && ok;
    if(!ok)dvbridge_render_dv_policy_cancel(r);
    return ok;
}
