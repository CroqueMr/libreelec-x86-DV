/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Native reference graphs and separately selected candidate comparisons. */
#include "reference_test.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/filters.h>
#include <libplacebo/shaders/colorspace.h>
#include <libplacebo/shaders/sampling.h>
#include <libplacebo/utils/libav.h>

enum { W=8, H=8, FW=3, FH=3 };
static pl_log renderer_log;
static bool require_effective_domain;
static unsigned carrier_roundtrips;
static bool track_detail, fail_detail_alloc, fail_detail_dispatch;
static unsigned detail_extracts, detail_passes;
static unsigned detail_textures;
static int detail_active_w,detail_active_h;
static struct dvbridge_geometry spatial_geometry={W,H,0,0,W,H};
extern void __real_pl_shader_extract_features(pl_shader,struct pl_color_space);
void __wrap_pl_shader_extract_features(pl_shader sh,struct pl_color_space color)
{
    if(track_detail)detail_extracts++;
    __real_pl_shader_extract_features(sh,color);
}
static float detail_input[W*H*4];
struct detail_proxy { const struct pl_hook *hook;const struct pl_hook_params *params; };
static pl_tex detail_get_tex(void *priv,int w,int h)
{
    struct detail_proxy *proxy=priv;
    if(track_detail && !detail_textures++){detail_active_w=w;detail_active_h=h;}
    if(fail_detail_alloc && w==FW && h==FH){fail_detail_alloc=false;return NULL;}
    return proxy->params->get_tex(proxy->params->priv,w,h);
}
static struct pl_hook_res detail_hook(void *priv,const struct pl_hook_params *p)
{
    struct detail_proxy *proxy=priv;struct detail_proxy allocation={.params=p};
    struct pl_hook_params changed=*p;changed.get_tex=detail_get_tex;changed.priv=&allocation;
    if(track_detail && p->tex->params.w==W && p->tex->params.h==H)
        reference_read(p->gpu,p->tex,0,0,W,H,detail_input);
    return proxy->hook->hook(proxy->hook->priv,&changed);
}
extern bool __real_pl_render_image(pl_renderer,const struct pl_frame *,const struct pl_frame *,const struct pl_render_params *);
bool __wrap_pl_render_image(pl_renderer rr,const struct pl_frame *src,const struct pl_frame *dst,const struct pl_render_params *p)
{
    struct pl_hook hooks[2];const struct pl_hook *list[2];struct detail_proxy proxies[2];
    struct pl_render_params copy=*p;assert(p->num_hooks<=2);
    for(int i=0;i<p->num_hooks;i++){
        hooks[i]=*p->hooks[i];proxies[i].hook=p->hooks[i];
        if(hooks[i].input==PL_HOOK_SIG_TEX && hooks[i].stages==PL_HOOK_SCALED){
            hooks[i].hook=detail_hook;hooks[i].priv=&proxies[i];
        }
        list[i]=&hooks[i];
    }
    copy.hooks=list;return __real_pl_render_image(rr,src,dst,&copy);
}
extern bool __real_pl_dispatch_finish(pl_dispatch,const struct pl_dispatch_params *);
bool __wrap_pl_dispatch_finish(pl_dispatch dp,const struct pl_dispatch_params *p)
{
    if(track_detail && p->target && p->target->params.w<=W && p->target->params.h<=H){
        pl_fmt fmt=p->target->params.format;
        assert(fmt->type==PL_FMT_FLOAT && fmt->component_depth[0]==32);
        detail_passes++;
        if(fail_detail_dispatch && p->target->params.w==FW && p->target->params.h==FH){
            fail_detail_dispatch=false;pl_dispatch_abort(dp,p->shader);return false;
        }
    }
    return __real_pl_dispatch_finish(dp,p);
}
extern void __real_pl_shader_color_map(pl_shader,const struct pl_color_map_params *,
    struct pl_color_space,struct pl_color_space,pl_shader_obj *,bool);
void __wrap_pl_shader_color_map(pl_shader sh,const struct pl_color_map_params *params,
    struct pl_color_space src,struct pl_color_space dst,pl_shader_obj *state,bool linear)
{
    if(require_effective_domain && src.transfer==PL_COLOR_TRC_LINEAR && dst.transfer==PL_COLOR_TRC_LINEAR &&
       src.primaries==PL_COLOR_PRIM_DISPLAY_P3 && dst.primaries==PL_COLOR_PRIM_BT_2020)
        carrier_roundtrips++;
    __real_pl_shader_color_map(sh,params,src,dst,state,linear);
}
extern pl_renderer __real_pl_renderer_create(pl_log,pl_gpu);
pl_renderer __wrap_pl_renderer_create(pl_log log,pl_gpu gpu)
{
    return __real_pl_renderer_create(renderer_log?renderer_log:log,gpu);
}

static void finish(pl_dispatch dp,pl_shader *sh,pl_tex target)
{
    assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=sh,.target=target)));
}

static pl_tex features(pl_gpu gpu,pl_dispatch dp,pl_tex source,struct pl_color_space csp)
{
    pl_tex full=reference_texture(gpu,W,H,NULL),vertical=reference_texture(gpu,W,FH,NULL);
    pl_tex low=reference_texture(gpu,FW,FH,NULL);
    pl_shader sh=pl_dispatch_begin(dp);
    assert(pl_shader_sample_direct(sh,pl_sample_src(.tex=source)));
    pl_shader_extract_features(sh,csp);finish(dp,&sh,full);
    pl_shader_obj lut[2]={0};
    for(int axis=0;axis<2;axis++){
        sh=pl_dispatch_begin(dp);
        pl_tex input=axis?vertical:full,output=axis?low:vertical;
        struct pl_sample_src src={.tex=input,.rect={0,0,W,axis?FH:H},
            .components=1,.address_mode=PL_TEX_ADDRESS_MIRROR,
            .new_w=output->params.w,.new_h=output->params.h};
        struct pl_sample_filter_params filter={.filter=pl_filter_bicubic,
            .lut=&lut[axis],.no_compute=true,.cb1_fp32_lut=true};
        assert(pl_shader_sample_ortho2(sh,&src,&filter));finish(dp,&sh,output);
    }
    pl_tex_destroy(gpu,&full);pl_tex_destroy(gpu,&vertical);
    for(int i=0;i<2;i++)pl_shader_obj_destroy(&lut[i]);
    return low;
}

static void map(pl_gpu gpu,pl_dispatch dp,pl_tex source,pl_tex feature,float detail,
                enum pl_color_primaries prim,float pixels[W*H*4])
{
    struct pl_color_space from={.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
        .hdr={.min_luma=0,.max_luma=4000}};
    struct pl_color_space to=from;to.hdr.max_luma=1000;
    struct pl_color_map_params params={
        .gamut_mapping=&pl_gamut_map_perceptual,.tone_mapping_function=&pl_tone_map_spline,
        .gamut_constants={.colorimetric_gamma=1.8f,.softclip_knee=.7f,.softclip_desat=.35f,
            .perceptual_deadzone=.3f,.perceptual_strength=.8f},
        .tone_constants={.knee_adaptation=.4f,.knee_minimum=.1f,.knee_maximum=.8f,.knee_default=.4f,
            .knee_offset=1,.slope_tuning=1.5f,.slope_offset=.2f,.spline_contrast=.5f,
            .reinhard_contrast=.5f,.linear_knee=.3f,.exposure=1},
        .lut3d_size={48,32,256},.lut_size=256,.contrast_smoothness=3.5f,
        .contrast_recovery=detail,.metadata=PL_HDR_METADATA_CIE_Y,.cb1_fp32_tone_lut=true};
    pl_shader_obj state=NULL;
    pl_shader sh=pl_dispatch_begin(dp);
    assert(pl_shader_sample_direct(sh,pl_sample_src(.tex=source)));
    pl_shader_color_map_ex(sh,&params,pl_color_map_args(
        .src=from,.dst=to,.state=&state,.prelinearized=true,.feature_map=feature));
    pl_tex target=reference_texture(gpu,W,H,NULL);finish(dp,&sh,target);
    reference_read(gpu,target,0,0,W,H,pixels);
    for(int i=0;i<W*H*4;i++)assert(isfinite(pixels[i]));
    pl_shader_obj_destroy(&state);pl_tex_destroy(gpu,&target);
}

/* Independent native adaptation with an explicit HDR signal-black target. */
static void input_pixels(float pixels[W*H*4],bool colour)
{
    const double rgb[8][3]={{0,0,0},{1000,0,0},{1000,1000,0},{0,1000,0},
        {0,1000,1000},{0,0,1000},{1000,0,1000},{4000,4000,4000}};
    for(int y=0;y<H;y++)for(int x=0;x<W;x++){
        for(int c=0;c<3;c++){
            double nits=colour?rgb[x][c]:4000.0*x/(W-1);if(y%2)nits*=.1;
            pixels[(y*W+x)*4+c]=pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,nits);
        }
        pixels[(y*W+x)*4+3]=1;
    }
}

static void envelope_oracle(pl_gpu gpu,pl_dispatch dp,bool colour)
{
    float pixels[W*H*4],output[W*H*4];
    input_pixels(pixels,colour);
    pl_tex input=reference_texture(gpu,W,H,pixels),target=reference_texture(gpu,W,H,NULL);
    float maximum=lround(pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,4000)*4095)/4095.0f;
    struct pl_color_space from={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
        .hdr={.max_luma=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,maximum),.max_pq_y=maximum,
            .prim=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020)}};
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    av_dovi_get_color(m)->source_max_pq=lround(maximum*4095);
    struct pl_color_repr repr;struct pl_dovi_metadata dovi;
    struct pl_color_space decoded;
    pl_map_avdovi_metadata(&decoded,&repr,&dovi,m);
    struct pl_color_map_params params={.gamut_mapping=&pl_gamut_map_clip,
        .tone_mapping_function=&pl_tone_map_spline,
        .tone_constants={.knee_adaptation=.4f,.knee_minimum=.1f,.knee_maximum=.8f,.knee_default=.4f,
            .knee_offset=1,.slope_tuning=1.5f,.slope_offset=.2f,.spline_contrast=.5f,
            .reinhard_contrast=.5f,.linear_knee=.3f,.exposure=1},
        .lut_size=256,.metadata=PL_HDR_METADATA_CIE_Y,.cb1_fp32_tone_lut=true};
    pl_shader_obj state=NULL;
    puts("{\"algorithm\":\"native-explicit-black-v1\",\"native\":[");
    for(int gamut=0;gamut<2;gamut++){
        enum pl_color_primaries prim=gamut?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020;
        struct pl_color_space to={.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
            .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1000,.prim=*pl_raw_primaries_get(prim)}};
        pl_shader sh=pl_dispatch_begin(dp);
        assert(pl_shader_sample_nearest(sh,pl_sample_src(.tex=input)));
        if(colour){
            struct pl_color_repr copy=repr;
            pl_shader_decode_color_ex(sh,pl_color_decode_args(.repr=&copy));
        }
        pl_shader_color_map(sh,&params,from,to,&state,false);finish(dp,&sh,target);
        reference_read(gpu,target,0,0,W,H,output);
        printf("%s{\"gamut\":%d,\"linear\":[",gamut?",":"",gamut);
        for(int i=0;i<W*H;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",output[i*4],output[i*4+1],output[i*4+2]);
        puts("]}");
    }
    puts("]}");pl_shader_obj_destroy(&state);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&target);av_free(m);
}

/* Test-only native final-gamut/encoding oracle. Input is independent linear RGB. */
static void gamut_oracle(pl_gpu gpu,pl_dispatch dp)
{
    /* Match the renderer's transfer arithmetic, not its creative operator. */
    pl_dispatch_mark_cb1_stable_pq(dp,true);
    unsigned gamut;assert(scanf("%u",&gamut)==1 && gamut<2);
    float input[W*H*4],output[W*H*4];
    for(int i=0;i<W*H;i++){
        double rgb[3];assert(scanf("%lf %lf %lf",rgb,rgb+1,rgb+2)==3);
        for(int c=0;c<3;c++)input[4*i+c]=rgb[c]/203;
        input[4*i+3]=1;
    }
    pl_tex source=reference_texture(gpu,W,H,input),target=reference_texture(gpu,W,H,NULL);
    enum pl_color_primaries prim=gamut?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020;
    struct pl_color_space from={.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1000,
            .prim=*pl_raw_primaries_get(PL_COLOR_PRIM_ACES_AP0)}};
    struct pl_color_space to=from;to.hdr.prim=*pl_raw_primaries_get(prim);
    to.primaries=PL_COLOR_PRIM_BT_2020;to.transfer=PL_COLOR_TRC_PQ;
    struct pl_color_map_params params={.gamut_mapping=&pl_gamut_map_perceptual,
        .tone_mapping_function=&pl_tone_map_clip,.metadata=PL_HDR_METADATA_HDR10,
        .gamut_constants={.colorimetric_gamma=1.8f,.softclip_knee=.7f,.softclip_desat=.35f,
            .perceptual_deadzone=.3f,.perceptual_strength=.8f},.lut3d_size={48,32,256},.lut_size=256};
    pl_shader_obj state=NULL;pl_shader sh=pl_dispatch_begin(dp);
    assert(pl_shader_sample_nearest(sh,pl_sample_src(.tex=source)));
    pl_shader_color_map(sh,&params,from,to,&state,true);finish(dp,&sh,target);
    reference_read(gpu,target,0,0,W,H,output);puts("{\"pq\":[");
    for(int i=0;i<W*H;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",output[4*i],output[4*i+1],output[4*i+2]);
    puts("]}");pl_shader_obj_destroy(&state);pl_tex_destroy(gpu,&source);pl_tex_destroy(gpu,&target);
}

#ifndef DVBRIDGE_CM4_GPU_API
extern bool dvbridge_creative_cm4_shader(pl_shader,const struct dvbridge_cm4_coefficients *) __attribute__((weak));
#endif

static struct dvbridge_creative_plan test_plan(unsigned control,unsigned gamut)
{
    struct dvbridge_creative_plan p={.status=DVBRIDGE_CREATIVE_READY,.cm4=true,
        .cm4_targets=DVBRIDGE_CM4_TARGETS_RESOLVED,.policy={.tv={1000,DVBRIDGE_PANEL_OLED,
        gamut?DVBRIDGE_GAMUT_P3_D65:DVBRIDGE_GAMUT_BT2020}}};
    p.cm4_output.primaries=*pl_raw_primaries_get(gamut?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020);
    p.cm4_output.transfer=PL_COLOR_TRC_PQ;
    p.cm4_lower.present=true;p.cm4_lower.target=p.cm4_output;
    struct dvbridge_cm4_controls *c=&p.cm4_lower.controls;
    c->present_fields=31;c->mid_contrast=c->clip_trim=2048;
    for(unsigned i=0;i<6;i++){c->primary[i]=2048;c->saturation[i]=c->hue[i]=128;}
    if(control<6 && control)c->primary[control-1]=3072;
    if(control==6)c->primary[5]=4095;
    if(control==7)c->mid_contrast=3072;
    if(control==8)c->clip_trim=0;
    if(control==9){c->saturation[0]=255;c->saturation[2]=0;}
    if(control==10){c->hue[0]=0;c->hue[2]=255;}
    if(control==11){c->primary[0]=2304;c->primary[1]=2200;c->primary[2]=1900;
        c->primary[3]=3000;c->primary[4]=2700;c->mid_contrast=2400;c->clip_trim=1800;
        c->saturation[1]=180;c->hue[4]=200;}
    return p;
}
static void scalar_gpu(pl_gpu gpu,pl_dispatch dp)
{
    assert(dvbridge_creative_cm4_shader && "CM4 GPU scalar stage is not implemented");
    struct dvbridge_creative_plan check=test_plan(0,0);struct dvbridge_cm4_coefficients coeff;
    assert(dvbridge_creative_cm4_coefficients(&coeff,&check));
    pl_shader invalid=pl_dispatch_begin(dp);coeff.sop[2]=NAN;
    assert(!dvbridge_creative_cm4_shader(invalid,&coeff));pl_dispatch_abort(dp,&invalid);
    const double rgb[][3]={{0,0,0},{1e-9,1e-9,1e-9},{125,125,125},
        {250,250,250},{500,500,500},{750,750,750},{1000,1000,1000},
        {500,80,40},{40,500,80},{80,40,500},{500,500,40},{40,500,500},{500,40,500},
        {19.13059191405773,757.886997461319,3.43754905462265},
        {61.45135140419006,6.217452883720398,600.7314229011536},
        {10,900,1},{1000,1,1000}};
    enum { N=sizeof(rgb)/sizeof(*rgb) };
    float input[N*4],output[N*4];
    for(int i=0;i<N;i++){for(int j=0;j<3;j++)input[4*i+j]=rgb[i][j]/203;input[4*i+3]=1;}
    pl_tex source=reference_texture(gpu,N,1,input),target=reference_texture(gpu,N,1,NULL);
    puts("{\"cases\":[");bool comma=false;
    for(unsigned gamut=0;gamut<2;gamut++)for(unsigned control=0;control<12;control++){
        struct dvbridge_creative_plan p=test_plan(control,gamut);struct dvbridge_cm4_coefficients c;
        assert(dvbridge_creative_cm4_coefficients(&c,&p));
        pl_shader sh=pl_dispatch_begin(dp);assert(pl_shader_sample_nearest(sh,pl_sample_src(.tex=source)));
        assert(dvbridge_creative_cm4_shader(sh,&c));finish(dp,&sh,target);
        reference_read(gpu,target,0,0,N,1,output);
        for(int i=0;i<N;i++){
            for(int j=0;j<3;j++)assert(isfinite(output[4*i+j]));
            printf("%s{\"gamut\":%u,\"control\":%u,\"rgb\":[%.17g,%.17g,%.17g],\"out\":[%.17g,%.17g,%.17g]}",
                comma?",":"",gamut,control,rgb[i][0],rgb[i][1],rgb[i][2],
                output[4*i]*203.0,output[4*i+1]*203.0,output[4*i+2]*203.0);comma=true;
        }
    }
    puts("]}");pl_tex_destroy(gpu,&source);pl_tex_destroy(gpu,&target);
}

static void write_bits(uint8_t *data,unsigned bit,unsigned count,unsigned value)
{
    for(unsigned i=0;i<count;i++){
        unsigned at=bit+i,mask=1u<<(7-at%8);
        data[at/8]=(data[at/8]&~mask)|(((value>>(count-1-i))&1)?mask:0);
    }
}
static AVDOVIDmData wire_controls(const struct dvbridge_cm4_controls *c,unsigned target)
{
    AVDOVIDmData e={.level=8,.l8={.target_display_index=target,
        .trim_slope=c->primary[0],.trim_offset=c->primary[1],.trim_power=c->primary[2],
        .trim_chroma_weight=c->primary[3],.trim_saturation_gain=c->primary[4],.ms_weight=c->primary[5],
        .target_mid_contrast=c->mid_contrast,.clip_trim=c->clip_trim},
        .dvbridge_raw_magic=0x41424456,.dvbridge_original_length=25};
    e.dvbridge_original_bytes[0]=target;
    for(int i=0;i<6;i++)write_bits(e.dvbridge_original_bytes,8+12*i,12,c->primary[i]);
    write_bits(e.dvbridge_original_bytes,80,12,c->mid_contrast);
    write_bits(e.dvbridge_original_bytes,92,12,c->clip_trim);
    memcpy(e.dvbridge_original_bytes+13,c->saturation,6);memcpy(e.l8.saturation_vector_field,c->saturation,6);
    memcpy(e.dvbridge_original_bytes+19,c->hue,6);memcpy(e.l8.hue_vector_field,c->hue,6);
    return e;
}
static void full_gpu(pl_gpu gpu,bool colour)
{
    float source[W*H*4],output[W*H*4];
    input_pixels(source,colour);
    pl_tex input=reference_texture(gpu,W,H,source);struct pl_frame frame=reference_frame(input,W,H);
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    av_dovi_get_color(m)->source_max_pq=lround(pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,4000)*4095);
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=av_dovi_get_color(m)->source_max_pq}};
    puts("{\"full\":[");bool comma=false;
    for(unsigned gamut=0;gamut<2;gamut++)for(unsigned control=0;control<12;control++){
        if(control==6)continue;
        struct dvbridge_creative_plan p=test_plan(control,gamut);
        p.policy.revision=1;p.policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;
        *av_dovi_get_ext(m,1)=wire_controls(&p.cm4_lower.controls,gamut?48:49);
        const struct dvbridge_identity id={1,control+1,1};
        assert(dvbridge_render_hdr10_policy_rgb(r,&p.policy,&id,&frame,m,bytes,0,0,
            (struct dvbridge_geometry){W,H,0,0,W,H}));
        const struct dvbridge_hdr10_policy_output *pending=dvbridge_render_policy_output(r);
        assert(pending && pending->creative.backend==DVBRIDGE_CREATIVE_CM4);
        assert(pending->creative.l8_coverage.applied==(1023u&~(1u<<5)));
        assert(!(pending->creative.applied_levels&(1u<<2)));
        reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,output);
        printf("%s{\"gamut\":%u,\"control\":%u,\"pq\":[",comma?",":"",gamut,control);comma=true;
        for(int i=0;i<W*H;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",output[i*4],output[i*4+1],output[i*4+2]);
        puts("]}");
    }
    puts("]}");
    if(require_effective_domain)assert(!carrier_roundtrips && "CM4 must retain its declared working colour domain");
    dvbridge_renderer_destroy(r);av_free(m);pl_tex_destroy(gpu,&input);
}

static bool spatial_render(struct dvbridge_renderer *r,const struct pl_frame *frame,
    AVDOVIMetadata *m,size_t bytes,unsigned ms,uint64_t picture)
{
    struct dvbridge_creative_plan p=test_plan(0,0);p.cm4_lower.controls.primary[5]=ms;
    *av_dovi_get_ext(m,1)=wire_controls(&p.cm4_lower.controls,49);
    p.policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;p.policy.revision=1;
    struct dvbridge_identity id={1,picture,1};
    detail_extracts=detail_passes=detail_textures=0;track_detail=true;
    bool ok=dvbridge_render_hdr10_policy_rgb(r,&p.policy,&id,frame,m,bytes,0,0,
        spatial_geometry);
    track_detail=false;return ok;
}
static void spatial_failure(pl_gpu gpu,const struct pl_frame *frame,AVDOVIMetadata *m,size_t bytes,bool dispatch)
{
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    assert(spatial_render(r,frame,m,bytes,2048,1));
    pl_tex target=reference_texture(gpu,3840,2160,NULL);
    assert(dvbridge_render_hdr10_policy_resolve(r,target,false,false,12));
    const struct dvbridge_identity id={1,1,1};assert(dvbridge_render_policy_commit(r,&id,target));
    struct dvbridge_hdr10_policy_output before,after;
    assert(dvbridge_render_policy_committed(r,&before));
    float original[W*H*4],preserved[W*H*4];reference_read(gpu,target,0,0,W,H,original);
    fail_detail_alloc=!dispatch;fail_detail_dispatch=dispatch;
    assert(!spatial_render(r,frame,m,bytes,4095,2));
    assert(!fail_detail_alloc && !fail_detail_dispatch);
    assert(!dvbridge_render_policy_output(r) && dvbridge_render_policy_committed(r,&after));
    assert(!memcmp(&before,&after,sizeof(before)));
    reference_read(gpu,target,0,0,W,H,preserved);assert(!memcmp(original,preserved,sizeof(original)));
    dvbridge_renderer_destroy(r);pl_tex_destroy(gpu,&target);
}
static void spatial_gpu(pl_gpu gpu)
{
    float input[W*H*4],neutral[W*H*4],positive[W*H*4],negative[W*H*4];
    input_pixels(input,false);
    pl_tex tex=reference_texture(gpu,W,H,input);struct pl_frame frame=reference_frame(tex,W,H);
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    unsigned maximum=lround(pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,4000)*4095);
    av_dovi_get_color(m)->source_max_pq=maximum;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=maximum}};
    assert(spatial_render(r,&frame,m,bytes,2048,1));
    assert(!detail_extracts && !detail_passes);reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,neutral);
    assert(spatial_render(r,&frame,m,bytes,4095,2) && "CM4 spatial detail is not implemented");
    assert(detail_extracts==1 && detail_passes==3);
    const struct dvbridge_hdr10_policy_output *out=dvbridge_render_policy_output(r);
    assert(out && (out->creative.l8_coverage.applied&(1u<<5)));
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,positive);
    assert(spatial_render(r,&frame,m,bytes,0,3));
    assert(detail_extracts==1 && detail_passes==3);
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,negative);
    assert(memcmp(positive,neutral,sizeof(neutral)) && memcmp(negative,neutral,sizeof(neutral)));
    for(unsigned i=0;i<W*H*4;i++)assert(isfinite(positive[i]) && isfinite(negative[i]));
    /* Exact active-edge mirror: changing only L5 pixels must not change content. */
    m->num_ext_blocks=3;*av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=5,.l5={1,1,1,1}};
    assert(spatial_render(r,&frame,m,bytes,4095,4));
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,positive);
    float scaled[W*H*4];memcpy(scaled,detail_input,sizeof(scaled));
    float changed[W*H*4];memcpy(changed,input,sizeof(changed));
    for(int y=0;y<H;y++)for(int x=0;x<W;x++)if(!x || !y || x==W-1 || y==H-1)
        for(int c=0;c<3;c++)changed[(y*W+x)*4+c]=c==1?1:0;
    pl_tex border=reference_texture(gpu,W,H,changed);frame=reference_frame(border,W,H);
    assert(spatial_render(r,&frame,m,bytes,4095,5));
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,negative);
    for(unsigned i=0;i<W*H*4;i++)if(i/4%W && i/4%W<W-1 && i/4/W && i/4/W<H-1 && scaled[i]!=detail_input[i])
        fprintf(stderr,"Scaled difference %u: %.9g -> %.9g\n",i,scaled[i],detail_input[i]);
    for(unsigned i=0;i<W*H*4;i++)if(positive[i]!=negative[i])
        fprintf(stderr,"L5 difference %u: %.9g -> %.9g\n",i,positive[i],negative[i]);
    assert(!memcmp(positive,negative,sizeof(positive)));
    spatial_geometry=(struct dvbridge_geometry){W,H,0,0,W-1,H-1};
    assert(spatial_render(r,&frame,m,bytes,4095,11));
    assert(detail_active_w==5 && detail_active_h==5 && "L5 filtering must use only visible pixel centres");
    spatial_geometry=(struct dvbridge_geometry){W,H,0,0,W,H};
    for(int y=0;y<H;y++)for(int x=0;x<W;x++)if(!x || !y || x==W-1 || y==H-1)
        for(int c=0;c<3;c++)assert(negative[(y*W+x)*4+c]==0);
    frame=reference_frame(tex,W,H);m->num_ext_blocks=2;
    assert(spatial_render(r,&frame,m,bytes,4095,6));
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,positive);
    memset(changed,0,sizeof(changed));for(unsigned i=3;i<W*H*4;i+=4)changed[i]=1;
    pl_tex black=reference_texture(gpu,W,H,changed);frame=reference_frame(black,W,H);
    assert(spatial_render(r,&frame,m,bytes,4095,7));
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,negative);
    for(unsigned i=0;i<W*H*4;i++)if(i%4!=3)assert(negative[i]==0);
    frame=reference_frame(tex,W,H);assert(spatial_render(r,&frame,m,bytes,4095,8));
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,negative);
    assert(!memcmp(positive,negative,sizeof(positive)));
    spatial_failure(gpu,&frame,m,bytes,false);spatial_failure(gpu,&frame,m,bytes,true);
    for(unsigned i=0;i<W*H*4;i++)changed[i]=i%4==3?1:pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,300);
    pl_tex flat=reference_texture(gpu,W,H,changed);frame=reference_frame(flat,W,H);
    assert(spatial_render(r,&frame,m,bytes,4095,9));
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,positive);
    assert(spatial_render(r,&frame,m,bytes,0,10));
    reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,negative);
    for(unsigned i=0;i<W*H*4;i++)assert(fabs(positive[i]-negative[i])<=2e-5);
    maximum=lround(pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,500)*4095);
    av_dovi_get_color(m)->source_max_pq=maximum;av_dovi_get_ext(m,0)->l1.max_pq=maximum;
    assert(spatial_render(r,&frame,m,bytes,4095,4));assert(!detail_extracts && !detail_passes);
    out=dvbridge_render_policy_output(r);assert(out && !(out->creative.l8_coverage.applied&(1u<<5)) &&
        out->creative.reason==DVBRIDGE_CREATIVE_DETAIL_NO_COMPRESSION);
    dvbridge_render_policy_cancel(r);assert(!dvbridge_render_policy_output(r));
    assert(!dvbridge_render_policy_commit(r,&(struct dvbridge_identity){1,4,1},NULL));
    dvbridge_renderer_destroy(r);pl_tex_destroy(gpu,&tex);pl_tex_destroy(gpu,&border);pl_tex_destroy(gpu,&black);
    pl_tex_destroy(gpu,&flat);av_free(m);
    puts("PASS neutral/no-compression bypass, signed detail, active-edge mirror, FP32, current picture, failure preservation and cancellation");
}

/* Independent graph: CPU crop is test-only and cannot sample L5 pixels. */
static void spatial_oracle(pl_gpu gpu,pl_dispatch dp,const AVDOVIMetadata *m,unsigned gamut,
    unsigned ms,unsigned border,float output[W*H*4])
{
    struct pl_color_space from;struct pl_color_repr repr;struct pl_dovi_metadata dovi;
    pl_map_avdovi_metadata(&from,&repr,&dovi,m);
    from.hdr.prim=*pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020);
    from.hdr.max_pq_y=av_dovi_get_ext(m,0)->l1.max_pq/4095.0f;
    from.hdr.avg_pq_y=0;from.hdr.max_cll=from.hdr.max_fall=0;
    enum pl_color_primaries prim=gamut?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020;
    struct pl_color_space to={.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
        .hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1000,.prim=*pl_raw_primaries_get(prim)}};
    float cropped[W*H*4];int aw=W-2*border,ah=H-2*border;
    for(int y=0;y<ah;y++)for(int x=0;x<aw;x++)
        memcpy(cropped+(y*aw+x)*4,detail_input+((y+border)*W+x+border)*4,4*sizeof(float));
    pl_tex source=reference_texture(gpu,W,H,detail_input),active=reference_texture(gpu,aw,ah,cropped);
    pl_tex full=reference_texture(gpu,aw,ah,NULL),vertical=reference_texture(gpu,W,FH,NULL);
    pl_tex feature=reference_texture(gpu,FW,FH,NULL),target=reference_texture(gpu,W,H,NULL);
    pl_shader sh=pl_dispatch_begin(dp);assert(pl_shader_sample_nearest(sh,pl_sample_src(.tex=active)));
    pl_shader_extract_features(sh,from);finish(dp,&sh,full);
    pl_shader_obj lut[2]={0},state=NULL;
    for(int axis=0;axis<2;axis++){
        sh=pl_dispatch_begin(dp);pl_tex input=axis?vertical:full,output=axis?feature:vertical;
        struct pl_sample_src sample={.tex=input,.components=1,.address_mode=PL_TEX_ADDRESS_MIRROR,
            .rect=axis?(pl_rect2df){0,0,W,FH}:(pl_rect2df){-(int)border,-(int)border,W-border,H-border},
            .new_w=output->params.w,.new_h=output->params.h};
        struct pl_sample_filter_params filter={.filter=pl_filter_bicubic,
            .lut=&lut[axis],.no_compute=true,.cb1_fp32_lut=true};
        assert(pl_shader_sample_ortho2(sh,&sample,&filter));finish(dp,&sh,output);
    }
    struct pl_color_map_params params={.gamut_mapping=&pl_gamut_map_clip,
        .tone_mapping_function=&pl_tone_map_spline,
        .tone_constants={.knee_adaptation=.4f,.knee_minimum=.1f,.knee_maximum=.8f,.knee_default=.4f,
            .knee_offset=1,.slope_tuning=1.5f,.slope_offset=.2f,.spline_contrast=.5f,
            .reinhard_contrast=.5f,.linear_knee=.3f,.exposure=1},
        .lut_size=256,.metadata=PL_HDR_METADATA_CIE_Y,.cb1_fp32_tone_lut=true,
        .contrast_recovery=.30*((int)ms-2048)/2048,.contrast_smoothness=3.5f};
    sh=pl_dispatch_begin(dp);assert(pl_shader_sample_nearest(sh,pl_sample_src(.tex=source)));
    pl_shader_color_map_ex(sh,&params,pl_color_map_args(.src=from,.dst=to,.state=&state,.feature_map=feature));
    finish(dp,&sh,target);reference_read(gpu,target,0,0,W,H,output);
    for(int i=0;i<2;i++)pl_shader_obj_destroy(&lut[i]);pl_shader_obj_destroy(&state);
    pl_tex textures[]={source,active,full,vertical,feature,target};
    for(unsigned i=0;i<sizeof(textures)/sizeof(*textures);i++)pl_tex_destroy(gpu,&textures[i]);
}

static void spatial_numeric(pl_gpu gpu,pl_dispatch dp)
{
    float input[W*H*4],output[W*H*4],base[W*H*4];input_pixels(input,true);
    pl_tex tex=reference_texture(gpu,W,H,input);struct pl_frame frame=reference_frame(tex,W,H);
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    unsigned maximum=lround(pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,4000)*4095);
    av_dovi_get_color(m)->source_max_pq=maximum;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=maximum}};
    puts("{\"spatial\":[");bool comma=false;unsigned picture=1;
    for(unsigned gamut=0;gamut<2;gamut++)for(unsigned combination=0;combination<2;combination++)
    for(unsigned sign=0;sign<2;sign++)for(unsigned border=0;border<2;border++){
        unsigned control=combination?11:0,ms=sign?4095:0;
        struct dvbridge_creative_plan p=test_plan(control,gamut);p.cm4_lower.controls.primary[5]=ms;
        p.policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;p.policy.revision=1;
        m->num_ext_blocks=border?3:2;*av_dovi_get_ext(m,1)=wire_controls(&p.cm4_lower.controls,gamut?48:49);
        if(border)*av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=5,.l5={1,1,1,1}};
        struct dvbridge_identity id={1,picture++,1};track_detail=true;
        assert(dvbridge_render_hdr10_policy_rgb(r,&p.policy,&id,&frame,m,bytes,0,0,
            (struct dvbridge_geometry){W,H,0,0,W,H}));track_detail=false;
        reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,output);
        pl_dispatch_mark_cb1_stable_pq(dp,true);spatial_oracle(gpu,dp,m,gamut,ms,border,base);
        printf("%s{\"gamut\":%u,\"control\":%u,\"ms\":%u,\"border\":%u,\"native\":[",comma?",":"",gamut,control,ms,border);comma=true;
        for(int i=0;i<W*H;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",base[i*4],base[i*4+1],base[i*4+2]);
        printf("],\"pq\":[");
        for(int i=0;i<W*H;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",output[i*4],output[i*4+1],output[i*4+2]);
        puts("]}");
    }
    puts("]}");dvbridge_renderer_destroy(r);pl_tex_destroy(gpu,&tex);av_free(m);
}

int main(int argc,char **argv)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    renderer_log=g.log;
    pl_dispatch dp=pl_dispatch_create(NULL,gpu);assert(dp);
    if(argc==2 && !strcmp(argv[1],"--spatial")){
        spatial_gpu(gpu);pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
    }
    if(argc==2 && !strcmp(argv[1],"--spatial-numeric")){
        spatial_numeric(gpu,dp);pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
    }
    if(argc==2 && !strcmp(argv[1],"--domain")){
        require_effective_domain=true;full_gpu(gpu,true);pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
    }
    if(argc==2 && (!strcmp(argv[1],"--envelope-oracle") || !strcmp(argv[1],"--colour-oracle"))){
        envelope_oracle(gpu,dp,!strcmp(argv[1],"--colour-oracle"));pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
    }
    if(argc==2 && !strcmp(argv[1],"--gamut-oracle")){
        gamut_oracle(gpu,dp);pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
    }
    if(argc==2 && !strcmp(argv[1],"--gpu")){
        scalar_gpu(gpu,dp);pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
    }
    if(argc==2 && (!strcmp(argv[1],"--full") || !strcmp(argv[1],"--full-colour"))){
        full_gpu(gpu,!strcmp(argv[1],"--full-colour"));pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
    }
    float source[W*H*4],output[W*H*4],base[W*H*4];
    for(int y=0;y<H;y++)for(int x=0;x<W;x++){
        int i=(y*W+x)*4;
        double nits=x==0?0:4000.0*x/(W-1);
        if(y%2)nits*=.10;
        for(int c=0;c<3;c++)source[i+c]=nits/203;
        source[i+3]=1;
    }
    pl_tex input=reference_texture(gpu,W,H,source);
    puts("{\"algorithm\":\"cb1-cm4-v1\",\"size\":[8,8],\"unit_nits\":203,\"native\":[");
    for(int gamut=0;gamut<2;gamut++){
        enum pl_color_primaries prim=gamut?PL_COLOR_PRIM_DISPLAY_P3:PL_COLOR_PRIM_BT_2020;
        struct pl_color_space csp={.primaries=prim,.transfer=PL_COLOR_TRC_LINEAR,
            .hdr={.min_luma=0,.max_luma=4000}};
        pl_tex feature=features(gpu,dp,input,csp);
        for(int variation=0;variation<3;variation++){
            float detail=variation==0?0:variation==1?.30f:-.30f;
            map(gpu,dp,input,variation?feature:NULL,detail,prim,output);
            if(!variation)memcpy(base,output,sizeof(base));
            else assert(memcmp(base,output,sizeof(base)));
            printf("%s{\"gamut\":\"%s\",\"detail\":%.9g,\"linear\":[",
                gamut||variation?",":"",gamut?"P3-D65":"BT2020",detail);
            for(int i=0;i<W*H;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",
                output[i*4],output[i*4+1],output[i*4+2]);
            puts("]}");
        }
        pl_tex_destroy(gpu,&feature);
    }
    puts("]}");
    pl_tex_destroy(gpu,&input);pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);
}
