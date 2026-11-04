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
static void compatibility_gpu(pl_gpu gpu,bool colour)
{
    float source[W*H*4],output[W*H*4],baseline[W*H*4];
    input_pixels(source,colour);
    pl_tex input=reference_texture(gpu,W,H,source);struct pl_frame frame=reference_frame(input,W,H);
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    av_dovi_get_color(m)->source_max_pq=lround(pl_hdr_rescale(PL_HDR_NITS,PL_HDR_PQ,4000)*4095);
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=av_dovi_get_color(m)->source_max_pq}};
    puts("{\"full\":[");bool comma=false;
    for(unsigned gamut=0;gamut<2;gamut++)for(unsigned control=0;control<12;control++){
        struct dvbridge_creative_plan p=test_plan(control,gamut);
        p.policy.revision=1;p.policy.mode=DVBRIDGE_MODE_HDR10_EXPERT;
        *av_dovi_get_ext(m,1)=wire_controls(&p.cm4_lower.controls,gamut?48:49);
        const struct dvbridge_identity id={1,control+1,1};
        assert(dvbridge_render_hdr10_policy_rgb(r,&p.policy,&id,&frame,m,bytes,0,0,
            (struct dvbridge_geometry){W,H,0,0,W,H}));
        const struct dvbridge_hdr10_policy_output *pending=dvbridge_render_policy_output(r);
        assert(pending && pending->creative.backend==DVBRIDGE_CREATIVE_NONE);
        assert(!pending->creative.l8_coverage.applied && !(pending->creative.applied_levels&(1u<<8)));
        assert(pending->creative.l8_coverage.preserved==pending->creative.l8_coverage.present);
        assert(!(pending->creative.applied_levels&(1u<<2)));
        reference_read(gpu,dvbridge_render_texture(r),0,0,W,H,output);
        if(!control)memcpy(baseline,output,sizeof(baseline));
        else assert(!memcmp(baseline,output,sizeof(baseline)) &&
            "Public Expert without L2 must not claim or apply local CM4 controls");
        printf("%s{\"gamut\":%u,\"control\":%u,\"pq\":[",comma?",":"",gamut,control);comma=true;
        for(int i=0;i<W*H;i++)printf("%s[%.17g,%.17g,%.17g]",i?",":"",output[i*4],output[i*4+1],output[i*4+2]);
        puts("]}");
    }
    puts("]}");
    if(require_effective_domain)assert(!carrier_roundtrips && "CM4 must retain its declared working colour domain");
    dvbridge_renderer_destroy(r);av_free(m);pl_tex_destroy(gpu,&input);
}

int main(int argc,char **argv)
{
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    renderer_log=g.log;
    pl_dispatch dp=pl_dispatch_create(NULL,gpu);assert(dp);
    if(argc==2 && !strcmp(argv[1],"--domain")){
        require_effective_domain=true;compatibility_gpu(gpu,true);pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
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
    if(argc==2 && (!strcmp(argv[1],"--compat") || !strcmp(argv[1],"--compat-colour"))){
        compatibility_gpu(gpu,!strcmp(argv[1],"--compat-colour"));pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
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
