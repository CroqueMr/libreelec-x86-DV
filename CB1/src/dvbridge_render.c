/* SPDX-License-Identifier: GPL-3.0-only
 * Original engine contributions: GPL-3.0-or-later.
 * Creative numerical adaptations: see docs/CREATIVE-MAPPING.md, 2026-10-04.
 */
/* Reconstruct video at full precision, then pack the HDMI transport with frame-matched metadata. */
#include "dvbridge_render.h"
#include "dvbridge_placebo.h"
#include "dvbridge_gl_pack.h"
#include "dvbridge_pack_sources.h"
#include "cb1_hdr10_ai.h"
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
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

struct dvbridge_dv_slot {
    bool active, retiring, ready, quarantined, allocated;
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
    GLuint buffers[3], programs[2], sampler;
    const uint32_t *mapped;
    void *source_metadata;
    unsigned groups;
};
struct dvbridge_retirement_owner {
    pl_gpu gpu;
    struct dvbridge_renderer *attached, *lease;
};
struct fit_byte { size_t offset; uint8_t value; };
struct creative_fit_cache {
    void *source;
    size_t bytes, count;
    struct fit_byte *edits; /* Encoded changed words, not picture or GPU state. */
    struct dvbridge_policy policy;
    struct dvbridge_creative_edit_report report;
};

struct dvbridge_renderer {
    pl_gpu gpu;
    pl_renderer renderer;
    pl_tex rgb;
    struct dvbridge_context *context;
    struct dvbridge_candidate *pending;
    bool ready;
    bool packed, fragment_quad;
    struct pl_color_space reconstructed_color;
    struct dvbridge_hdr10_policy_output policy_pending, policy_committed;
    bool policy_ready, policy_has_committed;
    struct dvbridge_retirement_owner *owner;
    struct dvbridge_dv_slot dv;
    GLuint dv_analysis_program;
    struct dvbridge_gl_packer *dv_transport_packer;
    struct dvbridge_dv_policy_snapshot dv_committed;
    bool dv_has_committed;
    uint64_t resolve_serial;
    pl_shader_obj creative_state, creative_gamut_state;
    pl_shader_obj creative_detail_lut[2];
    struct creative_fit_cache fit_cache;
};

static void renderer_free(struct dvbridge_renderer *r);
static enum dvbridge_dv_policy_status dv_retire(struct dvbridge_renderer *r);
static void fit_cache_clear(struct creative_fit_cache *c)
{
    av_free(c->source);av_free(c->edits);memset(c,0,sizeof(*c));
}

struct reference_hook {
    float rect[4];
    float enhancement[4]; /* peak/203, brightness, chroma, scene mask */
    bool enhanced, intense;
    pl_matrix3x3 to_xyz, to_bt2020;
    pl_shader scaled_shader;
    bool called, failed;
    bool creative;
    struct dvbridge_creative_plan creative_plan;
    struct pl_color_space creative_source, creative_target;
    struct pl_color_map_params creative_mapper;
    pl_shader_obj *creative_state;
    pl_shader_obj *creative_gamut_state;
    bool cm4;
    struct dvbridge_cm4_coefficients cm4_coefficients;
    pl_shader_obj *detail_lut;
    pl_tex feature_map;
};

bool dvbridge_creative_cm4_shader(pl_shader sh,const struct dvbridge_cm4_coefficients *c)
{
    if(!sh || !c || !isfinite(c->peak_nits) || c->peak_nits<=0 || c->peak_nits>10000 ||
       !(c->chroma_base>0) || !(c->saturation_gain>0) || !(c->mid_exponent>0))return false;
    float sop[4]={c->sop[0],c->sop[1],c->sop[2],c->peak_nits};
    float shape[4]={c->mid_exponent,c->clip_strength,log2(c->chroma_base),log2(c->saturation_gain)};
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
        flags[3]=flags[3] || c->secondary_gain[i]!=1 || turns[i]!=0;
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
        {.var=pl_var_vec3("cm4_turns_b"),.data=turns+3,.dynamic=true}};
    const struct pl_custom_shader trim={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .variables=vars,.num_variables=13,.description="Independent CB1 CM4 linear-nits controls",
        /* Relative ST.2084 evaluation retains small chromatic differences. */
        .header="#if __VERSION__ >= 400 || (defined(GL_ES) && __VERSION__ >= 320)\n#define CB1_CM4_FMA fma\n#else\n#define CB1_CM4_FMA(a,b,c) ((a)*(b)+(c))\n#endif\n"
            "vec3 cb1_cm4_log1p(vec3 x){vec3 v=x*(vec3(1.0)-x*(vec3(0.5)-x*(vec3(1.0/3.0)-x*(vec3(0.25)-x*(vec3(0.2)-x*(vec3(1.0/6.0)-x*(vec3(1.0/7.0)-x/8.0)))))));"
            "return mix(v,log(max(vec3(1.0)+x,vec3(1e-30))),greaterThan(abs(x),vec3(0.125)));}\n"
            "vec3 cb1_cm4_expm1(vec3 x){vec3 v=x*(vec3(1.0)+x*(vec3(0.5)+x*(vec3(1.0/6.0)+x*(vec3(1.0/24.0)+x*(vec3(1.0/120.0)+x*(vec3(1.0/720.0)+x*(vec3(1.0/5040.0)+x/40320.0)))))));"
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
            "float primary_log=log(2.0)*(cm4_shape.w+cm4_shape.z*(2.0*z-1.0));float h=atan(ipt.z,ipt.y);\n"
            "float centres[6]=float[6](cm4_centres_a.x,cm4_centres_a.y,cm4_centres_a.z,cm4_centres_b.x,cm4_centres_b.y,cm4_centres_b.z);\n"
            "float gains[6]=float[6](cm4_gains_a.x,cm4_gains_a.y,cm4_gains_a.z,cm4_gains_b.x,cm4_gains_b.y,cm4_gains_b.z);\n"
            "float turns[6]=float[6](cm4_turns_a.x,cm4_turns_a.y,cm4_turns_a.z,cm4_turns_b.x,cm4_turns_b.y,cm4_turns_b.z);\n"
            "float sum=0.0,g=0.0,turn=0.0;for(int i=0;i<6;i++){float w=exp(4.0*(cos(h-centres[i])-1.0));sum+=w;g+=w*gains[i];turn+=w*turns[i];}\n"
            /* Evaluate the adjustment directly; subtracting rotated IPT loses dark-channel precision. */
            "turn/=sum;float gm=cb1_cm4_expm1(vec3(primary_log+g/sum)).x,scale=gm+1.0;"
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
        const float zero=0;
        struct pl_shader_var black_zero={.var=pl_var_float("reference_black_zero"),.data=&zero,.dynamic=true};
        struct pl_custom_shader capture = {.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
            .header="bool dvbridge_signal_black;\n"
                "vec3 dvbridge_reference_m2(vec3 v){vec3 v2=v*v,v4=v2*v2,v8=v4*v4,v16=v8*v8,v32=v16*v16,v64=v32*v32;"
                "return ((v64*v8)*v4)*v2*pow(v,vec3(0.84375));}\n",
            .variables=&black_zero,.num_variables=1,
            .body=p->color.transfer==PL_COLOR_TRC_PQ ?
                "vec3 z=pow(vec3(reference_black_zero),vec3(0.1593017578125));\n"
                "z=vec3(1.0)-0.1640625*(vec3(1.0)-z)/(vec3(1.0)+18.6875*z);\n"
                "dvbridge_signal_black=all(lessThanEqual(color.rgb,dvbridge_reference_m2(z)));\n" :
                "dvbridge_signal_black=all(lessThanEqual(color.rgb,vec3(0.0)));\n",
            .description="Retain exact signal black before Expert mapping"};
        h->failed = !pl_shader_custom(p->sh, &capture);
        if(h->creative){
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
            pl_shader_color_map(p->sh,&h->creative_mapper,h->creative_source,
                h->creative_target,h->creative_state,p->color.transfer==PL_COLOR_TRC_LINEAR);
            const double *c=h->creative_plan.codes;
            float sop[4]={c[0]/4096+.5,c[1]/4096-.5,c[2]/4096+.5,h->creative_plan.policy.tv.peak_nits/203};
            float cg[2]={c[3]/4096-.5,c[4]/4096-.5};
            struct pl_shader_var vars[]={
                {.var=pl_var_vec4("creative_sop"),.data=sop,.dynamic=true},
                {.var=pl_var_vec2("creative_color"),.data=cg,.dynamic=true}};
            struct pl_custom_shader trim={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
                .variables=vars,.num_variables=2,.description="CM2.9 linear-nits creative controls",
                .body="vec3 t=clamp(color.rgb/creative_sop.w*creative_sop.x+creative_sop.y,0.0,1.0);\n"
                    "t=creative_sop.w*pow(t,vec3(creative_sop.z));\n"
                    "float Y=dot(t,vec3(0.22897,0.69174,0.07929));\n"
                    "if(Y>0.0 && creative_color.y!=0.0){\n"
                    "for(int i=0;i<3;i++)if(t[i]>0.0)t[i]*=pow((1.0+creative_color.x)*t[i]/Y,creative_color.y);}\n"
                    "color.rgb=t;\n"};
            h->failed=h->failed || !pl_shader_custom(p->sh,&trim);
            pl_shader_delinearize(p->sh,&h->creative_source);
            }
        }
        return (struct pl_hook_res){.failed=h->failed,.output=PL_HOOK_SIG_NONE};
    }
    h->called = true;
    if (p->stage != PL_HOOK_PRE_OUTPUT || (!h->cm4 && p->sh != h->scaled_shader) ||
        p->color.transfer != PL_COLOR_TRC_LINEAR) {
        h->failed = true;
        return (struct pl_hook_res){.failed=true};
    }
    if (h->enhanced) {
        struct pl_shader_var params={.var=pl_var_vec4("enhanced_policy"),.data=h->enhancement,.dynamic=true};
        struct pl_custom_shader enhance={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
            .variables=&params,.num_variables=1,.description="Shared selective Natural/Intense nominal LINEAR policy",
            .header=h->intense ? "#define CB1_ONSET vec2(0.02,0.25)\n" : "#define CB1_ONSET vec2(0.25,0.75)\n",
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
        {.var=pl_var_mat3("reference_xyz"),.data=&h->to_xyz,.dynamic=true},
        {.var=pl_var_mat3("reference_bt2020"),.data=&h->to_bt2020,.dynamic=true},
        {.var=pl_var_vec4("reference_area"),.data=h->rect,.dynamic=true},
        {.var=pl_var_int("reference_keep_black"),.data=&keep_black,.dynamic=true},
    };
    struct pl_custom_shader conversion = {.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .variables=vars,.num_variables=4,.description="Expert nominal LINEAR to BT2020 PQ before caller overlays",
        .body="color.rgb=reference_bt2020*(reference_xyz*color.rgb);\n"
              "bvec3 zero=lessThanEqual(color.rgb,vec3(0.0));\n"
              "vec3 v=pow(clamp(color.rgb*(203.0/10000.0),0.0,1.0),vec3(2610.0/16384.0));\n"
              "v=vec3(1.0)-(21.0/128.0)*(vec3(1.0)-v)/(vec3(1.0)+(2392.0/128.0)*v);\n"
              "color.rgb=mix(dvbridge_reference_m2(v),vec3(0.0),zero);\n"
              "if((dvbridge_signal_black && reference_keep_black!=0) || gl_FragCoord.x<reference_area.x || gl_FragCoord.x>=reference_area.z || "
              "gl_FragCoord.y<reference_area.y || gl_FragCoord.y>=reference_area.w)color=vec4(0,0,0,1);\n"};
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

struct active_mask {
    float rect[4];
    bool called, failed;
    const uint32_t *packets;
    uint32_t count, flip;
    pl_shader native_shader;
    bool early_mask;
};

static struct pl_hook_res skip_inactive_area(struct active_mask *mask,
                                             const struct pl_hook_params *p)
{
    mask->native_shader = p->sh;
    struct pl_shader_var vars[] = {
        {.var=pl_var_vec4("early_area"), .data=mask->rect, .dynamic=true},
        {.var={.name="early_words", .type=PL_VAR_UINT, .dim_v=4, .dim_m=1, .dim_a=128},
         .data=mask->packets, .dynamic=true},
        {.var=pl_var_uint("early_count"), .data=&mask->count, .dynamic=true},
        {.var=pl_var_uint("early_flip"), .data=&mask->flip, .dynamic=true}};
    struct pl_custom_shader shader = {
        .input=PL_SHADER_SIG_COLOR, .output=PL_SHADER_SIG_COLOR,
        .description="Skip reconstruction outside the DV active picture",
        .variables=vars, .num_variables=4,
        .body=
        "ivec2 ep=ivec2(gl_FragCoord.xy); if(early_flip!=0u) ep.y=2159-ep.y;\n"
        // Keep boundary pairs together: their chroma also uses the active neighbor.
        "int ex=ep.x&~1;\n"
        "if(float(ex+1)<early_area.x || float(ex)>=early_area.z || float(ep.y)<early_area.y || float(ep.y)>=early_area.w){\n"
        "uint ei=uint(ep.y*3840+ep.x), ek=ei/3072u, ev=0u;\n"
        "if(ek<early_count){uint eb=ei%1024u, ew=ek*128u+eb/8u;\n"
        "ev=(early_words[ew/4u][int(ew%4u)]>>(7u-eb%8u))&1u;}\n"
        "return vec4(128.0,16.0,float(ev*16u),255.0)/255.0;}\n"};
    mask->failed = pl_shader_is_compute(p->sh) || !pl_shader_custom(p->sh, &shader);
    return (struct pl_hook_res){.failed=mask->failed, .output=PL_HOOK_SIG_NONE};
}

/* Same arithmetic/packing as pack_gles300.frag. Subgroup exchange replaces
 * only the full-precision intermediate texture fetch of the adjacent pixel.
 * Adapted from the existing mpv_dvbridge_fused1.h implementation. */
static struct pl_hook_res pack_active_area(void *priv, const struct pl_hook_params *p)
{
    struct active_mask *mask = priv;
    if (p->stage == PL_HOOK_NATIVE)
        return skip_inactive_area(mask, p);
    mask->called = true;
    struct pl_shader_var vars[] = {
        {.var = pl_var_vec4("active_area"), .data = mask->rect, .dynamic = true},
        {.var = {.name="metadata_words", .type=PL_VAR_UINT, .dim_v=4, .dim_m=1, .dim_a=128},
         .data=mask->packets, .dynamic=true},
        {.var=pl_var_uint("packet_count"), .data=&mask->count, .dynamic=true},
        {.var=pl_var_uint("flip_y"), .data=&mask->flip, .dynamic=true}};
    struct pl_custom_shader shader = {
        .prelude="#extension GL_KHR_shader_subgroup_basic : require\n"
                 "#extension GL_KHR_shader_subgroup_quad : require\n",
        .input=PL_SHADER_SIG_COLOR, .output=PL_SHADER_SIG_COLOR,
        .description="Exact full-raster DV transport without intermediate image",
        .variables=vars, .num_variables=4,
        .body=
        "ivec2 p=ivec2(gl_FragCoord.xy); if(flip_y!=0u) p.y=2159-p.y;\n"
        "if(float(p.x)<active_area.x || float(p.x)>=active_area.z || float(p.y)<active_area.y || float(p.y)>=active_area.w) color=vec4(0,0,0,1);\n"
        "vec3 self_rgb=clamp(color.rgb,0.0,1.0);\n"
        "vec3 peer_rgb=subgroupQuadSwapHorizontal(self_rgb);\n"
        "vec3 a=(p.x&1)==0?self_rgb:peer_rgb, b=(p.x&1)==0?peer_rgb:self_rgb;\n"
        "float ya=dot(a,vec3(.2627,.6780,.0593)), yb=dot(b,vec3(.2627,.6780,.0593));\n"
        "uint y=uint(floor(256.0+3504.0*((p.x&1)==0?ya:yb)+.5));\n"
        "float cb=2048.0+3584.0*((a.b-ya)+(b.b-yb))/(2.0*1.8814);\n"
        "float cr=2048.0+3584.0*((a.r-ya)+(b.r-yb))/(2.0*1.4746);\n"
        "uint c=uint(floor(((p.x&1)==0?cb:cr)+.5));\n"
        "uint index=uint(p.y*3840+p.x), packet=index/3072u;\n"
        "if(packet<packet_count){ uint bit=index%1024u, byte_index=packet*128u+bit/8u;\n"
        "uint value=(metadata_words[byte_index/4u][int(byte_index%4u)]>>(7u-bit%8u))&1u;\n"
        "uint parity=uint(bitCount(c>>1u)+bitCount(y))&1u; c=(c&4094u)|(value^parity); }\n"
        "color=vec4(float(c>>4u),float(y>>4u),float((y&15u)|((c&15u)<<4u)),255.0)/255.0;\n"};
    // An early return must reach the transport target, never an intermediate image.
    mask->failed = mask->failed || p->stage != PL_HOOK_OUTPUT ||
                   (mask->early_mask && mask->native_shader != p->sh) || pl_shader_is_compute(p->sh) ||
                   !pl_shader_custom(p->sh, &shader);
    return (struct pl_hook_res){.failed=mask->failed, .output=PL_HOOK_SIG_NONE};
}

static struct pl_hook_res mask_active_area(void *priv, const struct pl_hook_params *p)
{
    struct active_mask *mask = priv;
    mask->called = true;
    struct pl_shader_var variable = {
        .var = pl_var_vec4("dvbridge_active"), .data = mask->rect, .dynamic = true};
    struct pl_custom_shader shader = {
        .input = PL_SHADER_SIG_COLOR, .output = PL_SHADER_SIG_COLOR,
        .body = "if(gl_FragCoord.x < dvbridge_active.x || gl_FragCoord.x >= dvbridge_active.z || "
                "gl_FragCoord.y < dvbridge_active.y || gl_FragCoord.y >= dvbridge_active.w) "
                "color = vec4(0.0, 0.0, 0.0, 1.0);",
        .variables = &variable, .num_variables = 1,
        .description = "DV active picture blanking before target overlays"};
    mask->failed = p->stage != PL_HOOK_OUTPUT || !pl_shader_custom(p->sh, &shader);
    return (struct pl_hook_res){.failed = mask->failed, .output = PL_HOOK_SIG_NONE};
}

struct dvbridge_renderer *dvbridge_renderer_create(pl_gpu gpu)
{
    if (!gpu)
        return NULL;
    struct dvbridge_renderer *r = calloc(1, sizeof(*r));
    if (!r)
        return NULL;
    r->gpu = gpu;
    // Query just the operation used here. libplacebo's global subgroup flag
    // requires arithmetic/clustered features that this fragment hook never uses.
    pl_opengl gl = pl_opengl_get(gpu);
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
    if (fmt)
        r->rgb = pl_tex_create(gpu, pl_tex_params(.w = 3840, .h = 2160, .format = fmt,
            .sampleable = true, .renderable = true, .blit_dst = true));
    if (!r->renderer || !r->context || !r->rgb) {
        dvbridge_renderer_destroy(r);
        return NULL;
    }
    return r;
}

void dvbridge_renderer_reset(struct dvbridge_renderer *r)
{
    if (!r)
        return;
    dvbridge_render_dv_policy_cancel(r);
    r->dv_has_committed=false;
    fit_cache_clear(&r->fit_cache);
    dvbridge_candidate_destroy(r->pending);
    r->pending = NULL;
    r->ready = false;
    r->packed = false;
    r->policy_ready = r->policy_has_committed = false;
    dvbridge_reset(r->context);
    if (r->renderer && !r->dv.active) {
        pl_renderer_flush_cache(r->renderer);
        pl_renderer_reset_errors(r->renderer, NULL);
    }
}

void dvbridge_renderer_destroy(struct dvbridge_renderer *r)
{
    if (!r)
        return;
    dvbridge_render_dv_policy_cancel(r);
    if (r->owner) {
        struct dvbridge_retirement_owner *owner=r->owner;
        owner->attached=NULL;
        if (r->dv.active) { owner->lease=r;return; }
    }
    renderer_free(r);
}

static void renderer_free(struct dvbridge_renderer *r)
{
    glDeleteProgram(r->dv_analysis_program);
    dvbridge_gl_packer_destroy(r->dv_transport_packer);
    dvbridge_candidate_destroy(r->pending);
    dvbridge_destroy(r->context);
    pl_tex_destroy(r->gpu, &r->rgb);
    pl_renderer_destroy(&r->renderer);
    pl_shader_obj_destroy(&r->creative_state);
    pl_shader_obj_destroy(&r->creative_gamut_state);
    for(int i=0;i<2;i++)pl_shader_obj_destroy(&r->creative_detail_lut[i]);
    fit_cache_clear(&r->fit_cache);
    free(r);
}

static bool render(struct dvbridge_renderer *r, const struct pl_frame *source,
                        const void *metadata, size_t bytes, double pts, double el_pts,
                        struct dvbridge_geometry geometry, pl_tex packed, bool flip,
                        const struct dvbridge_hdr10_session *session,
                        const struct dvbridge_policy *policy)
{
    if (!r)
        return false;
    if (r->dv.active) {
        dvbridge_render_dv_policy_cancel(r);
        return false;
    }
    r->ready = false;
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
        r->pending = dvbridge_prepare(r->context, metadata, bytes, pts, geometry,
                                     paired && mapped.dovi.nlq_active);
        if (!dvbridge_active_area(r->pending, margins))
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
        .planes = {{.texture = packed ? packed : r->rgb, .flipped = packed && flip,
                    .components = 4, .component_mapping = {0, 1, 2, 3}}},
        .repr = pl_color_repr_rgb,
        .color = mapped.color,
        .crop = {geometry.x, geometry.y, geometry.x + geometry.width, geometry.y + geometry.height},
    };
    struct pl_render_params params = pl_render_default_params;
    struct pl_color_map_params color_map = pl_color_map_default_params;
    if (session) {
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
        params.cb1_stable_pq = true;
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
    r->reconstructed_color = target.color;
    params.min_fbo_precision = 32;
    params.peak_detect_params = NULL;
    params.dither_params = NULL;
    params.frame_mixer = NULL;
    params.skip_caching_single_frame = true;
    // Own exact PQ-zero borders below. Do not translate an sRGB clear color
    // through the output transfer function or clear a full-raster frame twice.
    params.border = PL_CLEAR_SKIP;
    struct active_mask mask = {.rect = {margins[0], margins[2],
                                       3840 - margins[1], 2160 - margins[3]}};
    mask.flip = flip;
    mask.packets = dvbridge_packets(r->pending, &mask.count);
    mask.early_mask = packed && geometry.source_width == 3840 && geometry.source_height == 2160 &&
                      (margins[0] || margins[1] || margins[2] || margins[3]);
    const struct pl_hook hook = {
        .stages = PL_HOOK_OUTPUT | (mask.early_mask ? PL_HOOK_NATIVE : 0),
        .input = PL_HOOK_SIG_COLOR,
        .priv = &mask, .hook = packed ? pack_active_area : mask_active_area,
        .signature = packed ? 0x4456425246555302ULL : 0x445642524c350001ULL};
    const struct pl_hook *hooks[] = {&hook};
    params.hooks = hooks;
    params.num_hooks = 1;
    struct reference_hook reference = {
        .to_xyz=pl_get_rgb2xyz_matrix(pl_raw_primaries_get(target.color.primaries)),
        .to_bt2020=pl_get_xyz2rgb_matrix(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020)),
    };
    struct dvbridge_cm4_coefficients cm4;
    bool use_cm4=policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT &&
        dvbridge_creative_cm4_coefficients(&cm4,&creative);
    bool spatial=false;
    params.cb1_hook_color_space=use_cm4;
    if(policy && policy->mode==DVBRIDGE_MODE_HDR10_EXPERT && (creative.anchor_present || use_cm4)){
        reference.creative=true;reference.creative_plan=creative;
        reference.cm4=use_cm4;
        if(use_cm4){
            reference.cm4_coefficients=cm4;
            reference.detail_lut=r->creative_detail_lut;
            creative.backend=DVBRIDGE_CREATIVE_CM4;creative.status=DVBRIDGE_CREATIVE_READY;
            creative.reason=DVBRIDGE_CREATIVE_OK;creative.applied_levels&=~(1u<<2);creative.applied_levels|=1u<<8;
            creative.l2_coverage.applied=0;creative.l2_coverage.preserved=creative.l2_coverage.present;
            creative.l8_coverage.applied=cm4.present&~(1u<<5);creative.l8_coverage.preserved=cm4.present&~creative.l8_coverage.applied;
        }
        reference.creative_state=&r->creative_state;reference.creative_gamut_state=&r->creative_gamut_state;
        reference.creative_mapper=color_map;
        reference.creative_mapper.gamut_expansion=false;
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
            else creative.reason=DVBRIDGE_CREATIVE_DETAIL_NO_COMPRESSION;
        }
        // The SCALED hook owns tone mapping. The remaining map only changes gamut.
        image.color.hdr=reference.creative_target.hdr;
        color_map.tone_mapping_function=&pl_tone_map_clip;color_map.metadata=PL_HDR_METADATA_HDR10;
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
        reference.enhanced=policy->mode==DVBRIDGE_MODE_ENHANCED_DV;
        reference.intense=policy->enhancement==DVBRIDGE_ENHANCEMENT_INTENSE;
        if (reference.enhanced) {
            /* Decode immutable source hints with the pinned public API, divide
             * in binary64. This is a scene proxy, not measured luminance/FALL. */
            double maximum=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,mapped.color.hdr.max_pq_y);
            double average=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,mapped.color.hdr.avg_pq_y);
            if (!isfinite(maximum) || maximum<=0 || !isfinite(average)) return false;
            double x=fmax(0,fmin(1,(average/maximum-.1)/.4));
            reference.enhancement[0]=policy->tv.peak_nits/203.0;
            reference.enhancement[1]=reference.intense?.35f:.20f;
            reference.enhancement[2]=reference.intense?.08f:.04f;
            reference.enhancement[3]=1-.5*x*x*(3-2*x);
        }
        params.hooks=ref_hooks;
        params.num_hooks=spatial?2:1;
    }
    if (!packed && (geometry.x || geometry.y || geometry.width != 3840 || geometry.height != 2160))
        pl_tex_clear(r->gpu, r->rgb, (float[4]){0, 0, 0, 1});
    bool rendered = pl_render_image(r->renderer, &image, &target, &params);
    r->ready = rendered && (policy ? reference.called && !reference.failed : mask.called && !mask.failed);
    /* An EL sampling failure can otherwise return a successfully rendered BL-only frame. */
    struct pl_render_errors errors = pl_renderer_get_errors(r->renderer);
    r->ready = r->ready && !errors.errors && !errors.num_disabled_hooks;
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
    return r->ready;
}

bool dvbridge_render_rgb(struct dvbridge_renderer *r, const struct pl_frame *source,
                        const void *metadata, size_t bytes, double pts, double el_pts,
                        struct dvbridge_geometry geometry)
{
    return render(r, source, metadata, bytes, pts, el_pts, geometry, NULL, false, NULL, NULL);
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
    return render(r, source, metadata, bytes, pts, el_pts, geometry, NULL, false, session, NULL);
}

bool dvbridge_render_packed(struct dvbridge_renderer *r, const struct pl_frame *source,
                           const void *metadata, size_t bytes, double pts, double el_pts,
                           struct dvbridge_geometry geometry, pl_tex target, bool flip)
{
    if (r && r->dv.active)
        dvbridge_render_dv_policy_cancel(r);
    if (r)
        r->ready = false;
    if (!r || !source || !target || !r->fragment_quad ||
        target->params.w != 3840 || target->params.h != 2160 ||
        !target->params.renderable || target->params.format->type != PL_FMT_UNORM ||
        target->params.format->num_components != 4 ||
        geometry.x || geometry.y || geometry.width != 3840 || geometry.height != 2160 ||
        source->num_overlays || (source->enhancement_layer && source->enhancement_layer->num_overlays))
        return false;
    for (int c = 0; c < 4; ++c)
        if (target->params.format->component_depth[c] != 8)
            return false;
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
    bool ok = render(r, source, metadata, bytes, pts, el_pts, geometry, target, flip, NULL, NULL);
    ok = glGetError() == GL_NO_ERROR && ok;
    glColorMask(mask[0], mask[1], mask[2], mask[3]);
    for (unsigned i=0; i<sizeof(caps)/sizeof(*caps); ++i) {
        if (enabled[i]) glEnable(caps[i]);
        else glDisable(caps[i]);
    }
    r->ready = ok && glGetError() == GL_NO_ERROR;
    return r->ready;
}

pl_tex dvbridge_render_texture(const struct dvbridge_renderer *r)
{
    return r && r->ready && !r->packed ? r->rgb : NULL;
}

bool dvbridge_render_hdr10(struct dvbridge_renderer *r, pl_tex output,
                          bool flip, bool limited, unsigned bits)
{
    if (r && (r->policy_ready || r->dv.active)) return false;
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
    if (ok) r->ready = false;
    return ok;
}

void dvbridge_render_policy_cancel(struct dvbridge_renderer *r)
{
    if (!r) return;
    if (r->dv.active) dvbridge_render_dv_policy_cancel(r);
    r->policy_ready = r->ready = false;
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
    if (!render(r, source, metadata, bytes, pts, el_pts, geometry, NULL, false, NULL, policy))
        return false;
    r->policy_pending.identity = *identity;
    return true;
}

const struct dvbridge_hdr10_policy_output *dvbridge_render_policy_output(const struct dvbridge_renderer *r)
{
    return r && r->policy_ready && r->ready ? &r->policy_pending : NULL;
}

struct reference_resolve { float span, offset, maximum; bool called, failed; };
static struct pl_hook_res reference_quantize(void *priv, const struct pl_hook_params *p)
{
    struct reference_resolve *q = priv;
    q->called = true;
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
    if (!r || !r->policy_ready || !r->ready || !output || output == r->rgb ||
        bits < 10 || bits > 16 || output->params.w != 3840 || output->params.h != 2160 ||
        !output->params.renderable || output->params.format->num_components < 3) {
        dvbridge_render_policy_cancel(r); return false;
    }
    /* Validate stored RGB, not host transfer bits or intermediate precision.
     * Binary32 preserves all requested 10..16-bit codes; smaller floats are
     * not a proven final representation for this API. */
    pl_fmt fmt=output->params.format;
    for (int c=0;c<3;c++) {
        if ((fmt->type==PL_FMT_UNORM && fmt->component_depth[c]>=(int)bits) ||
            (fmt->type==PL_FMT_FLOAT && fmt->component_depth[c]>=32)) continue;
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


/* Each group has 128 lanes and a contiguous pairwise tree. Counts carry one
 * invalid-input bit internally; the fixed 48-byte record has a separate flag. */
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

static void dv_release(struct dvbridge_renderer *r)
{
    struct dvbridge_dv_slot *s=&r->dv;
    if(s->fence)s->delete_sync(s->fence);
    if(s->mapped){GLint previous;glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&previous);
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,s->buffers[2]);glUnmapBuffer(GL_SHADER_STORAGE_BUFFER);
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,previous);}
    glDeleteBuffers(3,s->buffers);glDeleteProgram(s->programs[1]);
    glDeleteSamplers(1,&s->sampler);
    av_free(s->source_metadata);
    /* Programs belong to the renderer; storage and metadata belong to the frame. */
    av_free(s->output_metadata);
    memset(s,0,sizeof(*s));
}

static enum dvbridge_dv_policy_status dv_retire(struct dvbridge_renderer *r)
{
    struct dvbridge_dv_slot *s=&r->dv;
    if(s->quarantined)return DVBRIDGE_DV_FAILED;
    if(!s->active)return DVBRIDGE_DV_IDLE;
    if(s->fence){GLenum result=s->wait_sync(s->fence,0,0);
        if(result==GL_TIMEOUT_EXPIRED)return DVBRIDGE_DV_BUSY;
        if(result!=GL_ALREADY_SIGNALED && result!=GL_CONDITION_SATISFIED){s->quarantined=true;return DVBRIDGE_DV_FAILED;}}
    dv_release(r);return DVBRIDGE_DV_IDLE;
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
    if(!r || mode<=DVBRIDGE_MODE_DISABLED || mode>DVBRIDGE_MODE_ENHANCED_DV ||
       !r->gpu || !r->renderer || !r->rgb ||
       !pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE))return false;
    if(mode==DVBRIDGE_MODE_STANDARD || mode==DVBRIDGE_MODE_HDR10_BASIC)return true;
    if(!pl_find_fmt(r->gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_LINEAR) ||
       !pl_find_fmt(r->gpu,PL_FMT_FLOAT,1,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR))return false;
    return mode!=DVBRIDGE_MODE_ENHANCED_DV || dv_transport_requirements(r->gpu);
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
        dvbridge_renderer_supports_mode(r,mode) && dv_transport_requirements(r->gpu) &&
        hdr10_ai_gpu_requirements(r->gpu) &&
        (mode!=DVBRIDGE_MODE_ENHANCED_DV || dv_gpu_requirements(r->gpu));
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

static bool dv_allocate(struct dvbridge_renderer *r)
{
    if(!dv_gpu_requirements(r->gpu))return false;
    struct dvbridge_dv_slot *s=&r->dv;
    s->buffer_storage=(PFNGLBUFFERSTORAGEEXTPROC)eglGetProcAddress("glBufferStorageEXT");
    s->wait_sync=(PFNGLCLIENTWAITSYNCPROC)eglGetProcAddress("glClientWaitSync");
    s->delete_sync=(PFNGLDELETESYNCPROC)eglGetProcAddress("glDeleteSync");
    s->fence_sync=(PFNGLFENCESYNCPROC)eglGetProcAddress("glFenceSync");
    GLint previous;glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&previous);
    glGenBuffers(3,s->buffers);
    for(unsigned i=0;i<2;i++){glBindBuffer(GL_SHADER_STORAGE_BUFFER,s->buffers[i]);glBufferData(GL_SHADER_STORAGE_BUFFER,259200,NULL,GL_STREAM_DRAW);}
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,s->buffers[2]);
    GLbitfield flags=GL_MAP_READ_BIT|GL_MAP_PERSISTENT_BIT_EXT|GL_MAP_COHERENT_BIT_EXT;
    const uint32_t empty[12]={0};s->buffer_storage(GL_SHADER_STORAGE_BUFFER,48,empty,flags);
    if(glGetError()==GL_NO_ERROR)s->mapped=glMapBufferRange(GL_SHADER_STORAGE_BUFFER,0,48,flags);
    glBindBuffer(GL_SHADER_STORAGE_BUFFER,previous);
    if(!r->dv_analysis_program)r->dv_analysis_program=dv_compute_program();
    s->programs[0]=r->dv_analysis_program;
    /* Borrowed libplacebo textures need an explicit non-mipmapped sampler. */
    glGenSamplers(1,&s->sampler);
    glSamplerParameteri(s->sampler,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glSamplerParameteri(s->sampler,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glSamplerParameteri(s->sampler,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glSamplerParameteri(s->sampler,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    if(!r->dv_transport_packer)
        r->dv_transport_packer=dvbridge_gl_packer_create(cb1_pack_vertex,cb1_pack_fragment);
    s->packer=r->dv_transport_packer;
    s->allocated=s->mapped && s->programs[0] && s->packer && glGetError()==GL_NO_ERROR;
    if(!s->allocated)dv_release(r);
    return s->allocated;
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
    s->allocated=s->wait_sync && s->delete_sync && s->fence_sync && s->packer && glGetError()==GL_NO_ERROR;
    if(!s->allocated)dv_release(r);
    return s->allocated;
}


static bool dv_analyze(struct dvbridge_renderer *r)
{
    struct dvbridge_dv_slot *s=&r->dv;const unsigned *m=s->output.value.margins;
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
    glUseProgram(s->programs[0]);
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(r->gpu,r->rgb,NULL,NULL,NULL));
    glBindSampler(0,s->sampler);
    glUniform4ui(glGetUniformLocation(s->programs[0],"area"),m[0],m[2],3840-m[1],2160-m[3]);
    const struct dvbridge_identity *id=&s->output.value.identity;
    glUniform2ui(glGetUniformLocation(s->programs[0],"stream_id"),id->stream,id->stream>>32);
    glUniform2ui(glGetUniformLocation(s->programs[0],"picture_id"),id->picture,id->picture>>32);
    glUniform2ui(glGetUniformLocation(s->programs[0],"revision_id"),id->revision,id->revision>>32);
    unsigned count=s->groups,pass=0,input=1,output=0;
    while(count){unsigned dispatch=(count+127)/128;
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER,0,s->buffers[input]);
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER,1,s->buffers[output]);
        glBindBufferBase(GL_SHADER_STORAGE_BUFFER,2,s->buffers[2]);
        glUniform1ui(glGetUniformLocation(s->programs[0],"count"),count);
        glUniform1ui(glGetUniformLocation(s->programs[0],"pass"),pass);
        glUniform1ui(glGetUniformLocation(s->programs[0],"final_pass"),dispatch==1);
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

static uint16_t dv_wire_code(double pq)
{ return (uint16_t)fmin(4095,floor(4096*pq+.5)); }
static double dv_ideal_pq(double nits)
{
    if(!nits)return 0;
    double v=pow(nits/10000,2610.0/16384.0);
    return pow((3424.0/4096.0+2413.0/128.0*v)/(1+2392.0/128.0*v),2523.0/32.0);
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
    s->output.output_metadata=m;s->output.bytes=s->output_bytes;s->output.candidate=r->pending;s->output.intermediate=r->rgb;
    return true;
}

void dvbridge_render_dv_policy_cancel(struct dvbridge_renderer *r)
{
    if(!r)return;
    if(r->dv.active){r->dv.retiring=true;r->dv.ready=false;}
    r->ready=false;
    memset(&r->dv.output,0,sizeof(r->dv.output));
    dvbridge_candidate_destroy(r->pending);r->pending=NULL;
}

static bool fit_policy_equal(const struct dvbridge_policy *a,const struct dvbridge_policy *b)
{
    return a->revision==b->revision && a->mode==b->mode && a->enhancement==b->enhancement &&
        a->tv.peak_nits==b->tv.peak_nits && a->tv.panel==b->tv.panel && a->tv.gamut==b->tv.gamut;
}
/* Call only after original raw/parsed resolution succeeds for this picture. */
static enum dvbridge_creative_status fit_cached(struct dvbridge_renderer *r,void **output,
    size_t *output_bytes,const void *metadata,size_t bytes,const struct dvbridge_creative_plan *p,
    struct dvbridge_creative_edit_report *report)
{
    struct creative_fit_cache *c=&r->fit_cache;
    if(c->source && c->bytes==bytes && fit_policy_equal(&c->policy,&p->policy) &&
       !memcmp(c->source,metadata,bytes)){
        uint8_t *copy=av_memdup(metadata,bytes);
        if(!copy){*output=NULL;*output_bytes=0;return DVBRIDGE_CREATIVE_INVALID;}
        for(size_t i=0;i<c->count;i++)copy[c->edits[i].offset]=c->edits[i].value;
        *output=copy;*output_bytes=bytes;*report=c->report;
        report->cache_hit=true;report->candidate_evaluations=0;report->fit_ns=0;
        return report->status;
    }
    enum dvbridge_creative_status status=dvbridge_creative_edit(output,output_bytes,metadata,bytes,p,report);
    fit_cache_clear(c);
    if(status==DVBRIDGE_CREATIVE_INVALID)return status;
    const uint8_t *source=metadata,*edited=*output;size_t count=0;
    for(size_t i=0;i<bytes;i++)count+=source[i]!=edited[i];
    void *key=av_memdup(metadata,bytes);
    struct fit_byte *edits=count?av_malloc_array(count,sizeof(*edits)):NULL;
    if(!key || (count && !edits)){av_free(key);av_free(edits);return status;}
    size_t n=0;for(size_t i=0;i<bytes;i++)if(source[i]!=edited[i])
        edits[n++]=(struct fit_byte){.offset=i,.value=edited[i]};
    *c=(struct creative_fit_cache){.source=key,.bytes=bytes,.count=count,.edits=edits,.policy=p->policy,.report=*report};
    return status;
}

enum dvbridge_dv_policy_status dvbridge_render_dv_policy_prepare(struct dvbridge_renderer *r,
    const struct dvbridge_policy *policy,const struct dvbridge_identity *id,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry)
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
    if(!dv_allocate_transport(r))return DVBRIDGE_DV_UNSUPPORTED;
    struct dvbridge_dv_slot *s=&r->dv;
    void *output=NULL;size_t output_bytes=0;
    struct dvbridge_creative_edit_report edit_report;
    enum dvbridge_creative_status edit=fit_cached(r,&output,&output_bytes,metadata,bytes,&creative,&edit_report);
    if(edit==DVBRIDGE_CREATIVE_INVALID){dv_release(r);return DVBRIDGE_DV_FAILED;}
    s->output_metadata=output;s->output_bytes=output_bytes;
    bool ok=render(r,source,metadata,bytes,pts,el_pts,geometry,NULL,false,NULL,NULL);
    s->active=true;s->pts=pts;
    if(!ok){dv_last_use(r);dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;}
    bool fel=color.dovi.nlq_active && source->enhancement_layer && pts==el_pts;
    dvbridge_candidate_destroy(r->pending);
    bool force=!r->dv_has_committed || r->dv_committed.identity.stream!=id->stream ||
        r->dv_committed.identity.revision!=id->revision;
    r->pending=dvbridge_prepare_output(r->context,output,output_bytes,pts,geometry,fel,force);
    if(!r->pending || !dv_last_use(r)){dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;}
    const AVDOVIColorMetadata *c=av_dovi_get_color(output);
    const AVDOVIDmData *l1=av_dovi_find_level(output,1);
    enum pl_color_primaries prim=policy->tv.gamut==DVBRIDGE_GAMUT_BT709?PL_COLOR_PRIM_BT_709:
        policy->tv.gamut==DVBRIDGE_GAMUT_P3_D65?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020;
    nominal=(struct pl_color_space){.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=policy->tv.peak_nits,.prim=*pl_raw_primaries_get(prim)}};
    s->output.value=(struct dvbridge_dv_policy_snapshot){.identity=*id,.policy=*policy,.source_cm_version=creative.cm4?40:29,
        .output_generation=DVBRIDGE_SOURCE_METADATA,.nominal_target=nominal,.container=r->reconstructed_color,
        .geometry=geometry,.nominal_max_nits=policy->tv.peak_nits,.fel_reconstructed=fel,.creative=creative,.creative_edit=edit_report,
        .l1={l1?l1->l1.min_pq:0,l1?l1->l1.max_pq:0,l1?l1->l1.avg_pq:0},.source_pq={c->source_min_pq,c->source_max_pq}};
    memcpy(s->output.value.margins,margins,sizeof(margins));
    s->output.output_metadata=output;s->output.bytes=output_bytes;
    s->output.candidate=r->pending;s->output.intermediate=r->rgb;
    r->policy_ready=false;s->ready=r->ready=true;
    return DVBRIDGE_DV_READY;
}


enum dvbridge_dv_policy_status dvbridge_render_dv_policy_poll(struct dvbridge_renderer *r)
{
    if(!r)return DVBRIDGE_DV_FAILED;
    struct dvbridge_dv_slot *s=&r->dv;
    if(s->quarantined)return DVBRIDGE_DV_FAILED;
    if(!s->active)return DVBRIDGE_DV_IDLE;
    if(s->retiring)return dv_retire(r);
    if(s->ready)return DVBRIDGE_DV_READY;
    GLenum status=s->wait_sync(s->fence,0,0);
    if(status==GL_TIMEOUT_EXPIRED)return DVBRIDGE_DV_PENDING;
    if(status!=GL_ALREADY_SIGNALED && status!=GL_CONDITION_SATISFIED){s->quarantined=true;dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;}
    s->delete_sync(s->fence);s->fence=NULL;
    if(s->mapped){
        uint32_t record[12];memcpy(record,s->mapped,sizeof(record));
        if(dv_derive(r,record)){s->ready=r->ready=true;return DVBRIDGE_DV_READY;}
    }
    dvbridge_render_dv_policy_cancel(r);return DVBRIDGE_DV_FAILED;
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
bool dvbridge_render_dv_policy_resolve(struct dvbridge_renderer *r,pl_tex target,unsigned framebuffer,bool flip)
{
    if(!dvbridge_render_dv_policy_output(r) || !target || target==r->rgb || r->resolve_serial==UINT64_MAX ||
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
    unsigned texture_target,count;
    unsigned texture=pl_opengl_unwrap(r->gpu,r->rgb,&texture_target,NULL,NULL);
    const uint32_t *packets=dvbridge_packets(r->pending,&count);
    bool ok=texture_target==GL_TEXTURE_2D && dvbridge_gl_pack(r->dv.packer,texture,framebuffer,3840,2160,packets,count,flip);
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
    r->dv_committed=out->value;r->dv_has_committed=true;dvbridge_render_dv_policy_cancel(r);return true;
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
    uint64_t bits=(uint64_t)raw->l3_min<<28|(uint64_t)raw->l3_max<<16|(uint64_t)raw->l3_avg<<4;
    for(unsigned i=0;i<5;++i)l3->dvbridge_original_bytes[i]=bits>>(32-8*i);
    return m;
}

static bool ai_render_pixels(struct dvbridge_renderer *r,const struct dvbridge_policy *policy,
    const struct cb1_ai_result *prediction,const struct pl_frame *source,struct dvbridge_geometry g)
{
    struct pl_frame image=*source,target={.num_planes=1,
        .planes={{.texture=r->rgb,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color=source->color,.crop={g.x,g.y,g.x+g.width,g.y+g.height}};
    struct pl_render_params params=pl_render_default_params;
    params.min_fbo_precision=32;params.peak_detect_params=NULL;params.dither_params=NULL;
    params.frame_mixer=NULL;params.skip_caching_single_frame=true;params.border=PL_CLEAR_SKIP;
    params.cb1_nearest_identity=true;params.cb1_stable_pq=true;params.cb1_fp32_scaler_lut=true;
    params.sigmoid_params=NULL;
    struct active_mask mask={.rect={g.x,g.y,g.x+g.width,g.y+g.height}};
    const struct pl_hook reference={.stages=PL_HOOK_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&mask,.hook=mask_active_area,.signature=0x4342314149520001ULL};
    const struct pl_hook *hooks[]={&reference};params.hooks=hooks;params.num_hooks=1;
    struct reference_hook enhanced={.enhanced=true,.intense=policy->enhancement==DVBRIDGE_ENHANCEMENT_INTENSE,
        .rect={g.x,g.y,g.x+g.width,g.y+g.height}};
    struct pl_color_map_params map={.gamut_mapping=&pl_gamut_map_perceptual,.tone_mapping_function=&pl_tone_map_spline,
        .gamut_constants={.colorimetric_gamma=1.8f,.softclip_knee=.7f,.softclip_desat=.35f,
            .perceptual_deadzone=.3f,.perceptual_strength=.8f},
        .tone_constants={.knee_adaptation=.4f,.knee_minimum=.1f,.knee_maximum=.8f,.knee_default=.4f,
            .knee_offset=1,.slope_tuning=1.5f,.slope_offset=.2f,.spline_contrast=.5f,
            .reinhard_contrast=.5f,.linear_knee=.3f,.exposure=1},
        .lut3d_size={48,32,256},.lut_size=256,.contrast_smoothness=3.5f,
        .metadata=PL_HDR_METADATA_CIE_Y,.inverse_tone_mapping=false,.gamut_expansion=true,.cb1_fp32_tone_lut=true};
    const struct pl_hook enhance_hook={.stages=PL_HOOK_SCALED|PL_HOOK_PRE_OUTPUT,.input=PL_HOOK_SIG_COLOR,
        .priv=&enhanced,.hook=reference_output,.signature=0x4342314149450001ULL};
    if(policy->mode!=DVBRIDGE_MODE_STANDARD){
        enum pl_color_primaries prim=policy->tv.gamut==DVBRIDGE_GAMUT_BT709?PL_COLOR_PRIM_BT_709:
            policy->tv.gamut==DVBRIDGE_GAMUT_P3_D65?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020;
        target.color=(struct pl_color_space){.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
            .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=policy->tv.peak_nits,.prim=*pl_raw_primaries_get(prim)}};
        image.color.hdr.max_pq_y=prediction->raw.l1_max/4095.f;
        image.color.hdr.avg_pq_y=prediction->raw.l1_avg/4095.f;
        image.color.hdr.prim=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020);
        image.color.hdr.max_cll=image.color.hdr.max_fall=0;
        enhanced.to_xyz=pl_get_rgb2xyz_matrix(pl_raw_primaries_get(prim));
        enhanced.to_bt2020=pl_get_xyz2rgb_matrix(pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020));
        for(int i=0;i<3;++i)for(int j=i+1;j<3;++j){
            float v=enhanced.to_xyz.m[i][j];enhanced.to_xyz.m[i][j]=enhanced.to_xyz.m[j][i];enhanced.to_xyz.m[j][i]=v;
            v=enhanced.to_bt2020.m[i][j];enhanced.to_bt2020.m[i][j]=enhanced.to_bt2020.m[j][i];enhanced.to_bt2020.m[j][i]=v;}
        double max=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,image.color.hdr.max_pq_y),
            avg=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,image.color.hdr.avg_pq_y);
        if(!isfinite(max) || max<=0 || !isfinite(avg))return false;
        double x=fmax(0,fmin(1,(avg/max-.1)/.4));
        enhanced.enhancement[0]=policy->tv.peak_nits/203;
        enhanced.enhancement[1]=enhanced.intense?.35f:.20f;
        enhanced.enhancement[2]=enhanced.intense?.08f:.04f;
        enhanced.enhancement[3]=1-.5*x*x*(3-2*x);
        params.color_map_params=&map;hooks[0]=&enhance_hook;
    }
    if(g.x || g.y || g.width!=3840 || g.height!=2160)pl_tex_clear(r->gpu,r->rgb,(float[4]){0,0,0,1});
    bool ok=pl_render_image(r->renderer,&image,&target,&params);
    struct pl_render_errors errors=pl_renderer_get_errors(r->renderer);
    if(!ok || errors.errors || errors.num_disabled_hooks ||
       (policy->mode==DVBRIDGE_MODE_STANDARD?(!mask.called || mask.failed):(!enhanced.called || enhanced.failed)))return false;
    r->reconstructed_color=source->color;
    if(policy->mode!=DVBRIDGE_MODE_STANDARD){
        r->reconstructed_color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
            .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=policy->tv.peak_nits,.prim=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020)}};
        r->policy_pending=(struct dvbridge_hdr10_policy_output){
            .identity={prediction->id.stream,prediction->id.picture,prediction->id.revision},.policy=*policy,
            .nominal_target=target.color,.container=r->reconstructed_color,.geometry=g,
            .hdr10={.max_luminance=(unsigned)ceil(policy->tv.peak_nits)}};
        r->policy_ready=true;
    }
    r->ready=true;return true;
}

pl_tex dvbridge_render_hdr10_ai_rgb(struct dvbridge_renderer *r,const struct dvbridge_policy *policy,
    const struct cb1_ai_result *prediction,const struct pl_frame *source,const struct dvbridge_geometry *geometry)
{
    if(!r)return NULL;
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
    if(!r->owner || !(policy->mode==DVBRIDGE_MODE_ENHANCED_DV?dv_allocate(r):dv_allocate_transport(r))){av_free(metadata);return NULL;}
    if(!ai_render_pixels(r,policy,prediction,source,g)){
        r->dv.active=true;dv_last_use(r);dvbridge_render_dv_policy_cancel(r);
        av_free(metadata);return NULL;
    }
    struct dvbridge_dv_slot *s=&r->dv;s->active=true;s->pts=prediction->pts;
    s->output.value=(struct dvbridge_dv_policy_snapshot){
        .identity={prediction->id.stream,prediction->id.picture,prediction->id.revision},.policy=*policy,
        .source_cm_version=0,.output_generation=DVBRIDGE_ETSI_LEGACY_LITERAL,.geometry=g,
        .container=r->reconstructed_color,.nominal_target=r->policy_pending.nominal_target,
        .nominal_max_nits=policy->mode==DVBRIDGE_MODE_STANDARD?source->color.hdr.max_luma:ceil(policy->tv.peak_nits)};
    memcpy(s->output.value.margins,margins,sizeof(margins));r->policy_ready=false;
    if(policy->mode==DVBRIDGE_MODE_ENHANCED_DV){
        /* Source estimates guide enhancement. Output L1 is measured afterwards;
         * source L3 is not reused on deliberately changed pixels. */
        s->source_metadata=metadata;r->ready=false;
        if(!dv_analyze(r)){dvbridge_render_dv_policy_cancel(r);return NULL;}
    }else{
        s->output_metadata=metadata;s->output_bytes=bytes;
        r->pending=dvbridge_prepare_output(r->context,metadata,bytes,prediction->pts,
            (struct dvbridge_geometry){3840,2160,0,0,3840,2160},false,
            !r->dv_has_committed || r->dv_committed.identity.stream!=prediction->id.stream ||
            r->dv_committed.identity.revision!=prediction->id.revision);
        if(!r->pending || !dv_last_use(r)){dvbridge_render_dv_policy_cancel(r);return NULL;}
        s->output.output_metadata=metadata;s->output.bytes=bytes;s->output.candidate=r->pending;s->output.intermediate=r->rgb;
        s->output.value.l1[0]=prediction->raw.l1_min;s->output.value.l1[1]=prediction->raw.l1_max;
        s->output.value.l1[2]=prediction->raw.l1_avg;s->ready=true;
    }
    return r->rgb;
}
