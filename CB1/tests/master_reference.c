/* SPDX-License-Identifier: GPL-3.0-or-later */
#define main preview7_native_control_main
#include "native_fidelity.c"
#undef main
#if __has_include("cb1_master_reference.h")
#include "cb1_master_reference.h"
#include "cb1_circuit.h"
#include <libplacebo/shaders/custom.h>
static unsigned reference_intermediates;
static bool track_reference_render(pl_renderer,const struct pl_frame *,const struct pl_frame *,const struct pl_render_params *);
#define pl_render_image track_reference_render
#include "../src/dvbridge_render.c"
#undef pl_render_image
#include "reference/master_vectors.h"
extern bool pl_shader_dovi_reference_component(pl_shader,const struct pl_cb1_dovi_reference *,
    int,pl_shader,pl_shader) __attribute__((weak));
#endif

static bool track_reference_render(pl_renderer renderer,const struct pl_frame *source,
    const struct pl_frame *target,const struct pl_render_params *params)
{
    if(params->cb1_dovi_reference && target->planes[0].texture->params.format->type==PL_FMT_FLOAT)
        reference_intermediates++;
    return pl_render_image(renderer,source,target,params);
}

static bool full_reference_rows;
bool __real_pl_render_image_cb1_active_rows(pl_renderer,const struct pl_frame *,
    const struct pl_frame *,const struct pl_render_params *,int,int);
bool __wrap_pl_render_image_cb1_active_rows(pl_renderer r,const struct pl_frame *source,
    const struct pl_frame *target,const struct pl_render_params *params,int y0,int y1)
{
    return full_reference_rows?pl_render_image(r,source,target,params):
        __real_pl_render_image_cb1_active_rows(r,source,target,params,y0,y1);
}

static void current_stages(void)
{
    struct reference_gpu g=reference_gpu_create();
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->vdr_bit_depth=12;h->coef_log2_denom=23;
    AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);
    for(int c=0;c<3;c++){
        mapping->curves[c].pivots[0]=256;mapping->curves[c].pivots[1]=768;
        mapping->curves[c].poly_order[0]=2;
        mapping->curves[c].poly_coef[0][1]=0;
        mapping->curves[c].poly_coef[0][2]=1<<23;
    }
    float value=sample(&g,m,900.f/1024,0,true);
    printf("{\"stage\":\"polynomial\",\"reference_code\":2304,\"current_code\":%u,\"current_value\":%.9g}\n",
        (unsigned)floorf(value*4096+.5f),value);
    av_free(m);reference_gpu_destroy(&g);
}

static void raw_contract(void)
{
#ifdef CB1_MASTER_REFERENCE_API
    assert(CB1_DV_DV_MASTER_REFERENCE==9 && DVBRIDGE_MODE_MASTER_REFERENCE==5);
    assert(!strcmp(cb1_circuit_version(CB1_DV_DV_REFERENCE),"CB1-DVDVR.0.5"));
    assert(!strcmp(cb1_circuit_version(CB1_DV_DV_MASTER_REFERENCE),"CB1-DVDVMR.0.5"));
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_MASTER_REFERENCE};
    assert(dvbridge_policy_validate(&policy)==DVBRIDGE_POLICY_VALID);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    AVDOVIColorMetadata *color=av_dovi_get_color(m);
    h->vdr_bit_depth=12;h->coef_log2_denom=23;
    color->signal_bit_depth=12;
    struct pl_cb1_dovi_reference result={0};
    int64_t exact=(INT64_C(1)<<24)+1;
    av_dovi_get_mapping(m)->curves[0].poly_coef[0][1]=exact;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_READY);
    assert(result.comp[0].poly[0][1]==exact);
    assert(result.contract==1 && result.bl_depth==10 && result.output_depth==12);
    h->bl_bit_depth=16;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_UNSUPPORTED);
    struct pl_cb1_dovi_reference zero={0};assert(!memcmp(&result,&zero,sizeof(result)));
    h->bl_bit_depth=10;h->disable_residual_flag=0;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_READY);
    av_dovi_get_mapping(m)->nlq[0].vdr_in_max=131072;
    av_dovi_get_mapping(m)->nlq[0].linear_deadzone_slope=8192;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_INVALID);
    assert(cb1_master_reference_map(&result,m,bytes,true)==CB1_MASTER_READY);
    av_dovi_get_mapping(m)->nlq[0].linear_deadzone_slope=UINT64_MAX;
    assert(cb1_master_reference_map(&result,m,bytes,true)==CB1_MASTER_UNSUPPORTED);
    assert(!memcmp(&result,&zero,sizeof(result)));
    h->disable_residual_flag=1;
    color->signal_eotf=18;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_UNSUPPORTED);
    assert(!memcmp(&result,&zero,sizeof(result)));
    color->signal_eotf=65535;
    h->spatial_resampling_filter_flag=1;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_UNSUPPORTED);
    h->spatial_resampling_filter_flag=0;
    /* MEL's unused EL filter and canonical zero NLQ require no EL image. */
    for(int c=0;c<3;c++)av_dovi_get_mapping(m)->nlq[c]=(AVDOVINLQParams){.vdr_in_max=1u<<23};
    av_dovi_get_mapping(m)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    h->disable_residual_flag=0;h->el_spatial_resampling_filter_flag=1;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_READY);
    assert(!result.residual);
    for(int c=0;c<3;c++)av_dovi_get_mapping(m)->nlq[c]=(AVDOVINLQParams){.nlq_offset=512,
        .vdr_in_max=1048576,.linear_deadzone_slope=2048};
    assert(cb1_master_reference_map(&result,m,bytes,true)==CB1_MASTER_READY && result.residual);
    h->el_spatial_resampling_filter_flag=2;
    assert(cb1_master_reference_map(&result,m,bytes,true)==CB1_MASTER_UNSUPPORTED);
    h->el_spatial_resampling_filter_flag=0;h->disable_residual_flag=1;
    av_dovi_get_mapping(m)->num_x_partitions=2;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_UNSUPPORTED);
    av_dovi_get_mapping(m)->num_x_partitions=0;
    av_dovi_get_mapping(m)->curves[0].poly_coef[0][1]=INT64_MAX;
    assert(cb1_master_reference_map(&result,m,bytes,false)==CB1_MASTER_UNSUPPORTED);
    av_free(m);
#else
    assert(!"Master Reference raw API missing");
#endif
}

static void arithmetic(void)
{
#ifdef CB1_MASTER_REFERENCE_API
    assert(pl_shader_dovi_reference_component && "exact GPU component primitive missing");
    struct reference_gpu g=reference_gpu_create();
    pl_dispatch dispatch=pl_dispatch_create(NULL,g.gl->gpu);
    int vector_count=sizeof(master_vectors)/sizeof(*master_vectors);
    for(int witness=0;witness<39+vector_count;witness++){
        size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
        AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
        h->vdr_bit_depth=12;h->coef_log2_denom=23;
        AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);
        int component=0,bl[3]={900,0,0},el=512;
        unsigned expected=2304;
        if(witness>=31+vector_count){
            int edge=witness-31-vector_count;
            bl[0]=512;mapping->curves[0].poly_coef[0][1]=1<<23;
            if(edge<5){
                h->disable_residual_flag=0;
                mapping->nlq[0]=(AVDOVINLQParams){.nlq_offset=512,.vdr_in_max=1048576,
                    .linear_deadzone_slope=edge==2?UINT64_C(1)<<33:16384+(edge==1),
                    .linear_deadzone_threshold=edge==4?UINT64_C(1)<<35:0};
                el=edge==3?0:65535;expected=edge==3?1536:2560;
            }else{
                mapping->curves[0].poly_coef[0][0]=edge==6?-INT64_C(2147483649):INT64_C(2147483647)+(edge==5);
                mapping->curves[0].poly_coef[0][1]=0;expected=edge==6?0:4095;
            }
        }else if(witness>=29+vector_count){
            h->coef_log2_denom=6;h->disable_residual_flag=0;
            mapping->curves[0].poly_coef[0][0]=32;mapping->curves[0].poly_coef[0][1]=0;
            mapping->nlq[0]=(AVDOVINLQParams){.nlq_offset=512,.vdr_in_max=1,.linear_deadzone_slope=1};
            el=witness==29+vector_count?513:511;expected=el==513?2080:2016;
        }else if(witness>=22+vector_count){
            static const int samples[]={63,64,511,512,513,940,941};
            int value=samples[witness-22-vector_count];bl[0]=value;
            AVDOVIReshapingCurve *curve=&mapping->curves[0];
            curve->num_pivots=3;curve->pivots[0]=64;curve->pivots[1]=512;curve->pivots[2]=940;
            curve->poly_coef[0][1]=1<<23;
            curve->mapping_idc[1]=AV_DOVI_MAPPING_POLYNOMIAL;curve->poly_order[1]=2;curve->poly_coef[1][2]=1<<23;
            expected=value<512?4*(value<64?64:value):(((value>940?940:value)*(value>940?940:value)+128)>>8);
        }else if(witness>=22){
            const struct master_vector *v=&master_vectors[witness-22];
            h->vdr_bit_depth=v->depth;h->disable_residual_flag=0;
            memcpy(bl,v->bl,sizeof(bl));el=v->el;expected=v->expected;
            component=v->method?1:0;
            AVDOVIReshapingCurve *curve=&mapping->curves[component];
            curve->mapping_idc[0]=v->method;
            if(v->method){
                curve->mmr_order[0]=v->order;curve->mmr_constant[0]=v->coeff[0];
                memcpy(curve->mmr_coef[0],v->coeff+1,sizeof(curve->mmr_coef[0]));
            }else{
                curve->poly_order[0]=v->order;
                memcpy(curve->poly_coef[0],v->coeff,sizeof(curve->poly_coef[0]));
            }
            mapping->nlq[component]=(AVDOVINLQParams){.nlq_offset=512,.vdr_in_max=131072,
                .linear_deadzone_slope=8192,.linear_deadzone_threshold=4096};
        }else if(witness==0){
            mapping->curves[0].pivots[0]=256;mapping->curves[0].pivots[1]=768;
            mapping->curves[0].poly_order[0]=2;
            mapping->curves[0].poly_coef[0][1]=0;mapping->curves[0].poly_coef[0][2]=1<<23;
        }else if(witness<=3){
            h->disable_residual_flag=0;
            mapping->curves[0].poly_coef[0][0]=1<<21;mapping->curves[0].poly_coef[0][1]=0;
            mapping->nlq[0]=(AVDOVINLQParams){.nlq_offset=512,.vdr_in_max=131072,
                .linear_deadzone_slope=8192,.linear_deadzone_threshold=4096};
            el=witness==1?768:witness==2?256:512;
            expected=witness==1?1088:witness==2?960:1024;
        }else{
            component=1;bl[0]=513;bl[1]=511;bl[2]=979;
            AVDOVIReshapingCurve *curve=&mapping->curves[1];
            curve->mapping_idc[0]=AV_DOVI_MAPPING_MMR;
            bool nonlinear=witness!=5;
            unsigned bias=witness>=6?witness-6:0;
            curve->mmr_order[0]=nonlinear?3:1;
            curve->mmr_coef[0][nonlinear?2:0][nonlinear?6:0]=1<<23;
            curve->mmr_constant[0]=128*bias;
            /* Literal mapped V=894. Sweep all low bits through final rounding. */
            expected=nonlinear?((894+bias+8)>>4):2052;
        }
        struct pl_cb1_dovi_reference raw;
        assert(cb1_master_reference_map(&raw,m,bytes,true)==CB1_MASTER_READY);
        pl_shader shader=pl_dispatch_begin(dispatch);
        pl_shader base=pl_shader_alloc(NULL,pl_shader_params(.gpu=g.gl->gpu,.id=1));
        pl_shader enhancement=pl_shader_alloc(NULL,pl_shader_params(.gpu=g.gl->gpu,.id=2));
        char body[160];snprintf(body,sizeof(body),"color=vec4(%d.0,%d.0,%d.0,1.0);",bl[0],bl[1],bl[2]);
        assert(pl_shader_custom(base,&(struct pl_custom_shader){.input=PL_SHADER_SIG_NONE,
            .output=PL_SHADER_SIG_COLOR,.body=body}));
        snprintf(body,sizeof(body),"color=vec4(%d.0);",el);
        assert(pl_shader_custom(enhancement,&(struct pl_custom_shader){.input=PL_SHADER_SIG_NONE,
            .output=PL_SHADER_SIG_COLOR,.body=body}));
        assert(pl_shader_dovi_reference_component(shader,&raw,component,base,enhancement));
        pl_shader_free(&base);pl_shader_free(&enhancement);
        pl_tex target=reference_texture(g.gl->gpu,1,1,NULL);
        assert(pl_dispatch_finish(dispatch,pl_dispatch_params(.shader=&shader,.target=target)));
        float value[4];reference_read(g.gl->gpu,target,0,0,1,1,value);
        fprintf(stderr,"Master witness %d: %.9g, expected %u\n",witness,value[0],expected);
        assert(value[0]==expected);
        pl_tex_destroy(g.gl->gpu,&target);av_free(m);
    }
    pl_dispatch_destroy(&dispatch);reference_gpu_destroy(&g);
#else
    assert(!"Master Reference GPU component API missing");
#endif
}

static int chroma_code(int c,int x,int y)
{ x=x<0?0:x>15?15:x;y=y<0?0:y>15?15:y;return ((c==1?43:19)*x+(c==1?107:87)*y)%1024; }

static void spatial_case(int storage,int shift,bool top,bool interleaved,int mmr)
{
#ifdef CB1_MASTER_REFERENCE_API
    struct reference_gpu g=reference_gpu_create();
    pl_renderer renderer=pl_renderer_create(g.log,g.gl->gpu);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->vdr_bit_depth=12;h->coef_log2_denom=23;
    for(int c=0;c<3;c++)av_dovi_get_mapping(m)->curves[c].poly_coef[0][1]=1<<23;
    struct dvbridge_color mapped;assert(dvbridge_map_color(&mapped,m,bytes,false));
    struct pl_cb1_dovi_reference raw;
    assert(cb1_master_reference_map(&raw,m,bytes,false)==CB1_MASTER_READY);
    if(storage==8){
        raw.bl_depth=8;
        for(int c=0;c<3;c++)raw.comp[c].pivots[1]=255;
    }
    if(mmr==1){
        raw.comp[0].order[0]=2;raw.comp[0].poly[0][1]=0;raw.comp[0].poly[0][2]=1<<23;
        raw.comp[1].method[0]=1;raw.comp[1].order[0]=1;raw.comp[1].mmr[0][0][0]=1<<23;
    }
    if(mmr==2)for(int c=1;c<3;c++){
        raw.comp[c].num_pivots=9;
        for(int p=0;p<9;p++)raw.comp[c].pivots[p]=p==8?1023:p*128;
        for(int p=0;p<8;p++){
            raw.comp[c].method[p]=1;raw.comp[c].order[p]=3;
            raw.comp[c].mmr[p][0][c]=1<<23;
        }
    }
    struct pl_frame source={.num_planes=interleaved?2:3,.repr=mapped.repr,.color=mapped.color,.crop={0,0,32,32}};
    source.repr.bits=(struct pl_bit_encoding){.sample_depth=storage,.color_depth=raw.bl_depth,.bit_shift=shift};
    for(int c=0;c<source.num_planes;c++){
        int size=c?16:32,lanes=c && interleaved?2:1;
        uint16_t values[1024];uint8_t bytes8[1024];
        for(int y=0;y<size;y++)for(int x=0;x<size;x++)for(int lane=0;lane<lanes;lane++){
            int value=c?chroma_code(c+lane,x,y):32*y+x;
            if(storage==8)value>>=2;
            values[(y*size+x)*lanes+lane]=value<<shift;
            bytes8[(y*size+x)*lanes+lane]=value;
        }
        pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,lanes,storage,storage,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
        source.planes[c]=(struct pl_plane){.components=lanes,.component_mapping={c,2},
            .shift_x=c?-.5f:0,.shift_y=c && top?-.5f:0};
        source.planes[c].texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=size,.h=size,
            .format=fmt,.sampleable=true,.initial_data=storage==8?(void*)bytes8:(void*)values));
        assert(source.planes[c].texture);
    }
    pl_tex output=reference_texture(g.gl->gpu,32,32,NULL);
    struct pl_frame target=reference_frame(output,32,32);target.color=mapped.color;target.repr=pl_color_repr_rgb;
    struct pl_render_params params=pl_render_default_params;
    params.cb1_dovi_reference=&raw;params.cb1_dovi_transport=true;
    params.peak_detect_params=NULL;params.dither_params=NULL;params.frame_mixer=NULL;
    params.sigmoid_params=NULL;params.disable_linear_scaling=true;params.min_fbo_precision=32;
    assert(pl_render_image(renderer,&source,&target,&params));
    float values[32*32*4];reference_read(g.gl->gpu,output,0,0,32,32,values);
    const int weights[2][6]={{2,-12,65,222,-25,4},{4,-25,222,65,-12,2}};
    const int half[8]={22,94,-524,2456,2456,-524,94,22};
    for(int y=0;y<32;y++)for(int x=0;x<32;x++)for(int c=0;c<3;c++){
        unsigned got=(unsigned)floorf(values[(y*32+x)*4+c]*4095+.5f);
        int expected=storage==8?((32*y+x)>>2)*16:4*(32*y+x);
        if(mmr==1 && !c)expected=((32*y+x)*(32*y+x)+128)>>8;
        if(c){
            expected=0;
            int count=top?(y%2?8:1):6,bits=top?(y%2?12:0):8;
            for(int i=0;i<count;i++){
                int row=y/2+(top?(count==1?0:i-3):i-3+y%2);
                int raw=chroma_code(c,x/2,row),code=storage==8?(raw>>2)*16:raw*4;
                if(mmr==1 && c==1){
                    int clipped=row<0?0:row>15?15:row;
                    code=4*(64*clipped+2*(x/2)+16);
                }
                expected+=(top?(count==1?1:half[i]):weights[y%2][i])*code;
            }
            expected=(expected+(bits?1<<(bits-1):0))>>bits;
            expected=expected<0?0:expected>4095?4095:expected;
        }
        if(got!=expected)fprintf(stderr,"spatial (%d,%d,%d): %u expected %u\n",x,y,c,got,expected);
        assert(got==expected);
    }
    target.planes[0].flipped=true;
    assert(pl_render_image(renderer,&source,&target,&params));
    float flipped[32*32*4];reference_read(g.gl->gpu,output,0,0,32,32,flipped);
    for(int y=0;y<32;y++)for(int x=0;x<32;x++)for(int c=0;c<3;c++)
        assert(roundf(flipped[(y*32+x)*4+c]*4095)==roundf(values[((31-y)*32+x)*4+c]*4095));
    target.planes[0].flipped=false;
    if(!interleaved){
        source.planes[2].shift_y=-.5f;
        assert(!pl_render_image(renderer,&source,&target,&params));
    }
    for(int c=0;c<source.num_planes;c++)pl_tex_destroy(g.gl->gpu,&source.planes[c].texture);
    pl_tex_destroy(g.gl->gpu,&output);pl_renderer_destroy(&renderer);
    av_free(m);reference_gpu_destroy(&g);
#else
    assert(!"Master Reference source API missing");
#endif
}

static void fel_spatial(void)
{
    struct reference_gpu g=reference_gpu_create();pl_renderer renderer=pl_renderer_create(g.log,g.gl->gpu);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);h->vdr_bit_depth=12;h->coef_log2_denom=23;h->disable_residual_flag=0;
    for(int c=0;c<3;c++){
        av_dovi_get_mapping(m)->curves[c].poly_coef[0][1]=1<<23;
        av_dovi_get_mapping(m)->nlq[c]=(AVDOVINLQParams){.nlq_offset=512,.vdr_in_max=131072,
            .linear_deadzone_slope=8192,.linear_deadzone_threshold=4096};
    }
    struct dvbridge_color mapped;assert(dvbridge_map_color(&mapped,m,bytes,true));
    struct pl_cb1_dovi_reference raw;assert(cb1_master_reference_map(&raw,m,bytes,true)==CB1_MASTER_READY);
    struct pl_frame frames[2]={{.num_planes=2,.crop={0,0,8,8},.repr=mapped.repr,.color=mapped.color},
        {.num_planes=2,.crop={0,0,4,4}}};
    const int uv[2][2]={{480,520},{540,500}};
    for(int f=0;f<2;f++){
        frames[f].repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
        for(int p=0;p<2;p++){
            int size=(f?4:8)/(p?2:1),lanes=p?2:1;uint16_t codes[64];
            for(int y=0;y<size;y++)for(int x=0;x<size;x++)for(int lane=0;lane<lanes;lane++)
                codes[(y*size+x)*lanes+lane]=(f?(p?uv[y][x]:(x*113+y*97)%1024):512)<<6;
            pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,lanes,16,16,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
            frames[f].planes[p]=(struct pl_plane){.components=lanes,.component_mapping={p,2},.shift_x=p?-.5f:0,
                .texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=size,.h=size,.format=fmt,.sampleable=true,.initial_data=codes))};
            assert(frames[f].planes[p].texture);
        }
    }
    frames[0].enhancement_layer=&frames[1];
    pl_tex output=reference_texture(g.gl->gpu,8,8,NULL);struct pl_frame target=reference_frame(output,8,8);
    target.repr=pl_color_repr_rgb;target.color=mapped.color;
    struct pl_render_params params=pl_render_default_params;
    params.cb1_dovi_reference=&raw;params.cb1_dovi_transport=true;params.min_fbo_precision=32;
    params.disable_linear_scaling=true;params.peak_detect_params=NULL;params.dither_params=NULL;params.sigmoid_params=NULL;
    assert(pl_render_image(renderer,&frames[0],&target,&params));
    /* Literal arrays from the independent Python oracle, contract 1. */
    const int ycodes[8][8]={
        {1984,1984,1984,1984,1984,1984,1984,1984},
        {1984,1984,1984,1984,1984,1984,1984,1984},
        {1984,1984,1984,1984,1984,1984,1984,1984},
        {1984,1984,1984,1984,1984,1984,1984,1984},
        {1984,1984,1984,1984,1984,1984,2036,2064},
        {1984,1984,1984,1984,1984,2048,2112,2112},
        {1984,1984,1984,1984,2000,2112,2112,2112},
        {1984,1984,1984,1984,2096,2112,2112,2112}};
    const int ccodes[8][4]={{1986,1999,2081,2097},{1980,2003,2077,2092},
        {1975,2013,2067,2078},{2008,2029,2051,2055},{2074,2051,2029,2025},
        {2112,2067,2013,2002},{2114,2077,2003,1988},{2111,2081,1999,1983}};
    float values[8*8*4];reference_read(g.gl->gpu,output,0,0,8,8,values);
    for(int y=0;y<8;y++)for(int x=0;x<8;x++)for(int c=0;c<3;c++){
        int expected=c?ccodes[y][x/2]:ycodes[y][x];
        int got=roundf(values[(y*8+x)*4+c]*4095);
        if(got!=expected)fprintf(stderr,"FEL %d,%d,%d: %d expected %d\n",x,y,c,got,expected);
        assert(got==expected);
    }
    /* Matching top-left grids retain Annex B reconstruction and their output phase. */
    frames[0].planes[1].shift_y=frames[1].planes[1].shift_y=-.5f;
    assert(pl_render_image(renderer,&frames[0],&target,&params));
    const int topcodes[8][4]={{1984,2000,2080,2096},{1973,2007,2073,2087},
        {1984,2020,2060,2068},{2041,2040,2040,2040},{2100,2060,2020,2012},
        {2118,2073,2007,1993},{2112,2080,2000,1984},{2110,2081,1999,1983}};
    reference_read(g.gl->gpu,output,0,0,8,8,values);
    for(int y=0;y<8;y++)for(int x=0;x<8;x++)for(int c=0;c<3;c++)
        assert(roundf(values[(y*8+x)*4+c]*4095)==(c?topcodes[y][x/2]:ycodes[y][x]));
    for(int phases=1;phases<3;phases++){
        frames[0].planes[1].shift_y=(phases&1)?-.5f:0;
        frames[1].planes[1].shift_y=(phases&2)?-.5f:0;
        assert(!pl_render_image(renderer,&frames[0],&target,&params));
    }
    struct pl_frame same_size=frames[0];same_size.enhancement_layer=NULL;
    for(int p=0;p<2;p++){
        uint16_t neutral[64];for(int i=0;i<64;i++)neutral[i]=512<<6;
        struct pl_tex_params texture=frames[0].planes[p].texture->params;
        texture.initial_data=neutral;
        same_size.planes[p].texture=pl_tex_create(g.gl->gpu,&texture);assert(same_size.planes[p].texture);
    }
    frames[0].enhancement_layer=&same_size;
    frames[0].planes[1].shift_y=same_size.planes[1].shift_y=-.5f;
    assert(pl_render_image(renderer,&frames[0],&target,&params));
    reference_read(g.gl->gpu,output,0,0,8,8,values);
    for(int i=0;i<8*8;i++)for(int c=0;c<3;c++){
        if(roundf(values[i*4+c]*4095)!=2048)fprintf(stderr,"same size %d,%d: %g\n",i,c,values[i*4+c]*4095);
        assert(roundf(values[i*4+c]*4095)==2048);
    }
    for(int phases=1;phases<3;phases++){
        frames[0].planes[1].shift_y=(phases&1)?-.5f:0;
        same_size.planes[1].shift_y=(phases&2)?-.5f:0;
        assert(!pl_render_image(renderer,&frames[0],&target,&params));
    }
    for(int p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&same_size.planes[p].texture);
    for(int f=0;f<2;f++)for(int p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&frames[f].planes[p].texture);
    pl_tex_destroy(g.gl->gpu,&output);pl_renderer_destroy(&renderer);av_free(m);reference_gpu_destroy(&g);
}

static void spatial(void)
{
    spatial_case(16,6,false,false,false);
    spatial_case(16,0,false,true,false);
    spatial_case(8,0,false,true,false);
    spatial_case(16,6,true,true,false);
    spatial_case(16,6,false,true,true);
    spatial_case(16,6,false,true,2);
    fel_spatial();
}

static void transport(bool lifecycle,bool rows)
{
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *renderer=dvbridge_renderer_create(g.gl->gpu);assert(renderer);
    if(g.log){pl_renderer_destroy(&renderer->renderer);renderer->renderer=pl_renderer_create(g.log,g.gl->gpu);}
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    AVDOVIColorMetadata *color=av_dovi_get_color(m);
    h->vdr_bit_depth=color->signal_bit_depth=12;h->coef_log2_denom=23;
    color->signal_full_range_flag=1;
    for(int c=0;c<3;c++){
        av_dovi_get_mapping(m)->curves[c].poly_coef[0][1]=1<<23;
        color->ycc_to_rgb_offset[c]=(AVRational){1,c?2:16};
    }
    m->num_ext_blocks=1;av_dovi_get_ext(m,0)->level=1;
    av_dovi_get_ext(m,0)->l1.max_pq=3079;av_dovi_get_ext(m,0)->l1.avg_pq=1800;
    assert(cb1_master_reference_transport(m,bytes));
    struct pl_frame source={.num_planes=2,.crop={0,0,3840,2160},
        .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
    for(int p=0;p<2;p++){
        pl_fmt format=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,p?2:1,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        source.planes[p]=(struct pl_plane){.components=p?2:1,.component_mapping={p,2},.shift_x=p?-.5f:0};
        source.planes[p].texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=p?1920:3840,.h=p?1080:2160,
            .format=format,.sampleable=true,.renderable=true,.blit_dst=true));
        assert(source.planes[p].texture);
        pl_tex_clear(g.gl->gpu,source.planes[p].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
    }
    struct pl_frame enhancement={.num_planes=2,.crop={0,0,1920,1080},.repr=source.repr};
    if(!lifecycle){
        h->disable_residual_flag=0;
        h->el_spatial_resampling_filter_flag=1;
        for(int c=0;c<3;c++)av_dovi_get_mapping(m)->nlq[c]=(AVDOVINLQParams){.nlq_offset=512,
            .vdr_in_max=131072,.linear_deadzone_slope=8192,.linear_deadzone_threshold=4096};
        for(int p=0;p<2;p++){
            enhancement.planes[p]=source.planes[p];
            enhancement.planes[p].texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=p?960:1920,.h=p?540:1080,
                .format=source.planes[p].texture->params.format,.sampleable=true,.renderable=true,.blit_dst=true));
            assert(enhancement.planes[p].texture);
            pl_tex_clear(g.gl->gpu,enhancement.planes[p].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
        }
        source.enhancement_layer=&enhancement;
    }
    pl_fmt rgba=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);
    pl_tex output=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=rgba,.sampleable=true,.renderable=true));assert(output);
    struct dvbridge_geometry geometry={3840,2160,0,0,3840,2160};
    source.planes[1].shift_y=-.5f;
    if(!lifecycle)assert(dvbridge_render_master_reference(renderer,&source,m,bytes,1,1,geometry,output,false,NULL)==CB1_MASTER_UNSUPPORTED);
    source.planes[1].shift_y=0;
    if(!lifecycle){
        h->el_spatial_resampling_filter_flag=0;
        assert(dvbridge_render_master_reference(renderer,&source,m,bytes,1,1,geometry,output,false,NULL)==CB1_MASTER_UNSUPPORTED);
        h->el_spatial_resampling_filter_flag=1;
    }
    dvbridge_renderer_set_fast_chroma(renderer,true);
    dvbridge_renderer_set_fel_nearest(renderer,true);
    dvbridge_renderer_set_processing_optimizations(renderer,true);
    assert(dvbridge_render_master_reference(renderer,&source,m,bytes,1,lifecycle?NAN:1,geometry,output,false,NULL)==CB1_MASTER_READY);
    const struct dvbridge_candidate *candidate=dvbridge_render_candidate(renderer);assert(candidate);
    unsigned count;const uint32_t *packets=dvbridge_packets(candidate,&count);assert(packets && count);
    GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
    uint8_t *pixels=malloc((size_t)3840*2160*4);assert(pixels);
    glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,pixels);assert(glGetError()==GL_NO_ERROR);
    for(unsigned i=0;i<3840*2160;i++){
        unsigned c=2048,packet=i/3072;
        if(packet<count){unsigned bit=i%1024,word=packet*128+bit/8;c|=(packets[word]>>(7-bit%8))&1;}
        uint8_t expected[4]={c>>4,128,(c&15)<<4,255};
        if(memcmp(pixels+4*i,expected,4))fprintf(stderr,"carrier mismatch %u: %u %u %u\n",i,pixels[4*i],pixels[4*i+1],pixels[4*i+2]);
        assert(!memcmp(pixels+4*i,expected,4));
    }
    free(pixels);glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
    assert(dvbridge_render_commit(renderer));assert(!dvbridge_render_candidate(renderer));
    if(lifecycle){
        pl_fmt overlay_format=pl_find_fmt(g.gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        pl_tex gui=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=overlay_format,
            .sampleable=true,.renderable=true,.blit_dst=true));assert(gui);
        pl_tex_clear(g.gl->gpu,gui,(float[4]){0,0,0,0});
        float tile[4*2*4];for(int i=0;i<8;i++)memcpy(tile+i*4,(float[4]){0,0,0,.5},4*sizeof(float));
        glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,gui,NULL,NULL,NULL));
        glTexSubImage2D(GL_TEXTURE_2D,0,100,2058,4,2,GL_RGBA,GL_FLOAT,tile);assert(glGetError()==GL_NO_ERROR);
        pl_tex decode=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
        pl_tex encode=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
        struct dvbridge_native_overlay overlay={.texture=gui,.degamma=decode,.pq=encode,.rect={100,100,104,102}};
        dvbridge_renderer_set_overlay_visible(renderer,true);
        for(int pq=0;pq<2;pq++){
            overlay.input_pq=pq;
            assert(dvbridge_render_master_reference(renderer,&source,m,bytes,1,NAN,geometry,output,false,&overlay)==CB1_MASTER_READY);
            glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
            uint8_t *frame=malloc((size_t)3840*2160*4);assert(frame);
            glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,frame);assert(glGetError()==GL_NO_ERROR);
            for(unsigned i=3840*4;i<3840*2160;i++){
                unsigned x=i%3840,y=i/3840;
                if(x>=100 && x<104 && y>=100 && y<102){
                    /* Black GUI maps to source offsets (1/16,1/2,1/2).
                     * Half-alpha over code 2048 rounds to 1152/2048/2048. */
                    unsigned yy=1152,cc=2048;
                    assert(frame[i*4]==cc>>4 && frame[i*4+1]==yy>>4 &&
                           frame[i*4+2]==((yy&15)|((cc&15)<<4)) && frame[i*4+3]==255);
                    continue;
                }
                assert(frame[i*4]==128 && frame[i*4+1]==128 && frame[i*4+2]==0 && frame[i*4+3]==255);
            }
            free(frame);glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
            assert(dvbridge_render_commit(renderer));
        }
        pl_tex_destroy(g.gl->gpu,&gui);pl_tex_destroy(g.gl->gpu,&decode);pl_tex_destroy(g.gl->gpu,&encode);
        dvbridge_renderer_set_overlay_visible(renderer,false);
        m->num_ext_blocks=2;av_dovi_get_ext(m,1)->level=5;
        av_dovi_get_ext(m,1)->l5.top_offset=av_dovi_get_ext(m,1)->l5.bottom_offset=280;
        assert(dvbridge_render_master_reference(renderer,&source,m,bytes,1,NAN,geometry,output,false,NULL)==CB1_MASTER_READY);
        glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
        uint8_t border[4];glReadPixels(2000,10,1,1,GL_RGBA,GL_UNSIGNED_BYTE,border);
        assert(glGetError()==GL_NO_ERROR && border[0]==128 && border[1]==16 && border[2]==0);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
        assert(dvbridge_render_commit(renderer));
        m->num_ext_blocks=1;
        /* Equal PTS with changed coefficients is a new picture, not a cache hit. */
        av_dovi_get_mapping(m)->curves[0].poly_coef[0][0]=1<<20;
        assert(dvbridge_render_master_reference(renderer,&source,m,bytes,1,NAN,geometry,output,false,NULL)==CB1_MASTER_READY);
        uint8_t changed[4];glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
        glReadPixels(2000,1000,1,1,GL_RGBA,GL_UNSIGNED_BYTE,changed);
        assert(glGetError()==GL_NO_ERROR && changed[1]==160);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
        pl_tex_clear(g.gl->gpu,source.planes[0].texture,(float[4]){40960.f/65535,0,0,1});
        assert(dvbridge_render_master_reference(renderer,&source,m,bytes,1,NAN,geometry,output,false,NULL)==CB1_MASTER_READY);
        glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
        glReadPixels(2000,1000,1,1,GL_RGBA,GL_UNSIGNED_BYTE,changed);
        assert(glGetError()==GL_NO_ERROR && changed[1]==192);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
        dvbridge_renderer_reset(renderer);
        assert(!dvbridge_render_candidate(renderer) && !dvbridge_render_commit(renderer));
        h->bl_bit_depth=16;
        assert(dvbridge_render_master_reference(renderer,&source,m,bytes,2,NAN,geometry,output,false,NULL)==CB1_MASTER_UNSUPPORTED);
        assert(!dvbridge_render_candidate(renderer) && !dvbridge_render_commit(renderer));
    }
    if(rows){
        /* Compare row pruning against the same integer renderer without pruning. */
        assert(!lifecycle);
        struct dvbridge_renderer *control=dvbridge_renderer_create(g.gl->gpu);assert(control);
        struct pl_frame *frames[2]={&source,&enhancement};
        for(int f=0;f<2;f++)for(int p=0;p<2;p++){
            pl_tex texture=frames[f]->planes[p].texture;
            int w=texture->params.w,hh=texture->params.h,n=p?2:1;
            uint16_t *data=malloc((size_t)w*hh*n*sizeof(*data));assert(data);
            for(int y=0;y<hh;y++)for(int x=0;x<w;x++)for(int c=0;c<n;c++)
                data[((size_t)y*w+x)*n+c]=(f?(384+(x*17+y*43+c*67)%256):
                    (64+(x*29+y*31+c*157)%896))<<6;
            glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,texture,NULL,NULL,NULL));
            glTexSubImage2D(GL_TEXTURE_2D,0,0,0,w,hh,p?GL_RG:GL_RED,GL_UNSIGNED_SHORT,data);
            assert(glGetError()==GL_NO_ERROR);
            free(data);
            frames[f]->planes[p].shift_y=p?-.5f:0;
        }
        for(int c=1;c<3;c++){
            AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(m)->curves[c];
            curve->mapping_idc[0]=AV_DOVI_MAPPING_MMR;curve->mmr_order[0]=3;
            curve->mmr_constant[0]=952886;
            const int64_t coefs[3][7]={{-138065,8549620,-3540104,1186039,-1277267,434303,417667},
                {631068,434312,2092876,-2269805,725073,-938044,825071},
                {-311742,-1512718,1760842,-1341841,845025,1787171,1351114}};
            memcpy(curve->mmr_coef[0],coefs,sizeof(coefs));
        }
        m->num_ext_blocks=2;av_dovi_get_ext(m,1)->level=5;
        pl_fmt gui_format=pl_find_fmt(g.gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        pl_tex gui=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=gui_format,
            .sampleable=true,.renderable=true,.blit_dst=true));assert(gui);
        pl_tex_clear(g.gl->gpu,gui,(float[4]){0,0,0,0});
        float tile[4*16*4];for(int i=0;i<64;i++)memcpy(tile+4*i,(float[4]){0,0,0,.5},4*sizeof(float));
        glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,gui,NULL,NULL,NULL));
        glTexSubImage2D(GL_TEXTURE_2D,0,100,2160-285,4,16,GL_RGBA,GL_FLOAT,tile);
        assert(glGetError()==GL_NO_ERROR);
        pl_tex decode=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
        pl_tex encode=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
        struct dvbridge_native_overlay overlay={.texture=gui,.degamma=decode,.pq=encode,.rect={100,269,104,285}};
        size_t frame_bytes=(size_t)3840*2160*4;
        uint8_t *expected=malloc(frame_bytes),*actual=malloc(frame_bytes);assert(expected && actual);
        const int offsets[][2]={{277,281},{1,3},{279,276},{0,0},{275,279}};
        for(unsigned test=0;test<sizeof(offsets)/sizeof(offsets[0]);test++)for(int flip=0;flip<2;flip++){
            av_dovi_get_ext(m,1)->l5.top_offset=offsets[test][0];
            av_dovi_get_ext(m,1)->l5.bottom_offset=offsets[test][1];
            uint32_t expected_packets[1024];unsigned expected_count=0;
            for(int full=0;full<2;full++){
                full_reference_rows=full;
                struct dvbridge_renderer *current=full?control:renderer;
                dvbridge_renderer_set_overlay_visible(current,test==0);
                assert(dvbridge_render_master_reference(current,&source,m,bytes,2+test,2+test,
                    geometry,output,flip,test==0?&overlay:NULL)==CB1_MASTER_READY);
                const struct dvbridge_candidate *pending=dvbridge_render_candidate(current);assert(pending);
                unsigned n;const uint32_t *p=dvbridge_packets(pending,&n);assert(n<=1024);
                if(!full){expected_count=n;memcpy(expected_packets,p,n*sizeof(*p));}
                else assert(n==expected_count && !memcmp(expected_packets,p,n*sizeof(*p)));
                glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
                glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,
                    pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
                glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,full?actual:expected);
                assert(glGetError()==GL_NO_ERROR);
                glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
                assert(dvbridge_render_commit(current));
            }
            full_reference_rows=false;
            if(memcmp(expected,actual,frame_bytes))fprintf(stderr,"L5 rows mismatch case %u flip %d\n",test,flip);
            assert(!memcmp(expected,actual,frame_bytes));
        }
        free(expected);free(actual);dvbridge_renderer_destroy(control);
        pl_tex_destroy(g.gl->gpu,&gui);pl_tex_destroy(g.gl->gpu,&decode);pl_tex_destroy(g.gl->gpu,&encode);
        puts("PASS 10 complete FEL/MMR carriers: odd/asymmetric L5, flip, reused state, GUI across bars");
    }
    pl_gpu_finish(g.gl->gpu);
    assert(renderer->fast_chroma && renderer->fel_nearest && renderer->processing_optimizations);
    dvbridge_renderer_destroy(renderer);
    for(int p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&source.planes[p].texture);
    if(!lifecycle)for(int p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&enhancement.planes[p].texture);
    pl_tex_destroy(g.gl->gpu,&output);av_free(m);reference_gpu_destroy(&g);
}

static void resolutions(bool placement)
{
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    if(g.log){pl_renderer_destroy(&r->renderer);r->renderer=pl_renderer_create(g.log,g.gl->gpu);}
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    av_dovi_get_header(m)->vdr_bit_depth=12;av_dovi_get_header(m)->coef_log2_denom=23;
    av_dovi_get_color(m)->signal_bit_depth=12;
    av_dovi_get_color(m)->signal_full_range_flag=1;
    for(unsigned c=0;c<3;c++)av_dovi_get_color(m)->ycc_to_rgb_offset[c]=(AVRational){1,c?2:16};
    assert(cb1_master_reference_transport(m,bytes));
    for(unsigned c=0;c<3;c++)av_dovi_get_mapping(m)->curves[c].poly_coef[0][1]=1<<23;
    m->num_ext_blocks=1;*av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1800}};
    const int sizes[][2]={{1920,1080},{3840,2020},{1920,800},{1280,720},{3840,2160},
        {1920,1080},{3840,2020}};
    pl_tex output=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(g.gl->gpu,"rgba8"),.renderable=true));assert(output);
    size_t frame_bytes=(size_t)3840*2160*4;
    uint8_t *upright=malloc(frame_bytes),*flipped=malloc(frame_bytes);assert(upright && flipped);
    for(unsigned test=0;test<sizeof(sizes)/sizeof(sizes[0]);test++){
        int w=sizes[test][0],h=sizes[test][1],height=(int)((int64_t)h*3840/w);
        struct pl_frame source={.num_planes=2,.crop={0,0,w,h},
            .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
        for(unsigned p=0;p<2;p++){
            source.planes[p]=(struct pl_plane){.components=p?2:1,.component_mapping={p,2},.shift_x=p?-.5f:0,
                .texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=p?w/2:w,.h=p?h/2:h,
                    .format=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,p?2:1,16,16,PL_FMT_CAP_SAMPLEABLE),.sampleable=true,.blit_dst=true,.host_writable=true))};
            assert(source.planes[p].texture);pl_tex_clear(g.gl->gpu,source.planes[p].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
            if(!p){
                uint16_t *luma=malloc((size_t)w*h*sizeof(*luma));assert(luma);
                for(int y=0;y<h;y++)for(int x=0;x<w;x++)
                    luma[y*w+x]=(y<h/4?256:y>3*h/4?768:512)<<6;
                assert(pl_tex_upload(g.gl->gpu,pl_tex_transfer_params(.tex=source.planes[p].texture,.ptr=luma)));
                free(luma);
            }
            if(p){
                uint16_t *chroma=malloc((size_t)w*h);assert(chroma);
                for(int y=0;y<h/2;y++)for(int x=0;x<w/2;x++){
                    unsigned i=(y*(w/2)+x)*2;
                    chroma[i]=chroma[i+1]=(x%17<8?384:640)<<6;
                }
                assert(pl_tex_upload(g.gl->gpu,pl_tex_transfer_params(.tex=source.planes[p].texture,.ptr=chroma)));
                free(chroma);
            }
        }
        struct dvbridge_geometry geometry={w,h,0,(2160-height)/2,3840,height};
        if(test==4 || test==5)geometry=(struct dvbridge_geometry){w,h,960,540,1920,1080};
        struct dvbridge_native_overlay overlay={0};
        if(test==6){
            m->num_ext_blocks=2;*av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=5,
                .l5={.top_offset=7,.bottom_offset=11}};
            pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
            overlay.texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,
                .sampleable=true,.renderable=true,.blit_dst=true));assert(overlay.texture);
            pl_tex_clear(g.gl->gpu,overlay.texture,(float[4]){0,0,0,0});
            float tile[4*40*4];for(unsigned i=0;i<4*40;i++)memcpy(tile+i*4,(float[4]){.1,.1,.1,.5},4*sizeof(float));
            glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,overlay.texture,NULL,NULL,NULL));
            glTexSubImage2D(GL_TEXTURE_2D,0,100,2060,4,40,GL_RGBA,GL_FLOAT,tile);assert(glGetError()==GL_NO_ERROR);
            overlay.degamma=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
            overlay.pq=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
            memcpy(overlay.rect,(float[4]){100,60,104,100},sizeof(overlay.rect));overlay.input_pq=true;
        }
        for(unsigned flip=0;flip<2;flip++){
        reference_intermediates=0;
        enum cb1_master_status status=dvbridge_render_master_reference(r,&source,m,bytes,test*2,NAN,geometry,output,flip,test==6?&overlay:NULL);
        if(status!=CB1_MASTER_READY)fprintf(stderr,"source %dx%d status %d\n",w,h,status);
        assert(status==CB1_MASTER_READY);
        if(placement && w==geometry.width && h==geometry.height)assert(!reference_intermediates);
        unsigned margins[4];assert(dvbridge_active_area(dvbridge_render_candidate(r),margins));
        assert(margins[0]==geometry.x && margins[1]==3840-geometry.x-geometry.width &&
            margins[2]==geometry.y+(test==6?7:0) && margins[3]==2160-geometry.y-geometry.height+(test==6?11:0));
        unsigned fbo;pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        uint8_t center[4];glReadPixels(2000,1080,1,1,GL_RGBA,GL_UNSIGNED_BYTE,center);
        if(center[1]!=128 || (center[2]&15))fprintf(stderr,"center %dx%d RGBA %u %u %u %u\n",w,h,center[0],center[1],center[2],center[3]);
        assert(glGetError()==GL_NO_ERROR && center[1]==128 && (center[2]&15)==0);
        uint8_t row[3840*4];glReadPixels(0,1080,3840,1,GL_RGBA,GL_UNSIGNED_BYTE,row);
        for(unsigned x=0;x<3840;x+=2){
            unsigned cb=(row[x*4]<<4)|(row[x*4+2]>>4);
            unsigned cr=(row[(x+1)*4]<<4)|(row[(x+1)*4+2]>>4);
            if(cb!=cr)fprintf(stderr,"scaled pair %dx%d x=%u Cb=%u Cr=%u\n",w,h,x,cb,cr);
            assert(cb==cr);
        }
        if(geometry.y){
            glReadPixels(2000,10,1,1,GL_RGBA,GL_UNSIGNED_BYTE,center);
            assert(glGetError()==GL_NO_ERROR && center[0]==128 && center[1]==16 && center[2]==0);
        }
        glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,flip?flipped:upright);
        assert(glGetError()==GL_NO_ERROR);
        if(test==6){
            uint8_t *pixels=flip?flipped:upright;
            assert(pixels[((size_t)(flip?2159-65:65)*3840+100)*4+1]!=16);
        }
        if(getenv("CB1_TEST_CARRIERS")){
            char path[4096];snprintf(path,sizeof(path),"%s/%u-%u.rgba",getenv("CB1_TEST_CARRIERS"),test,flip);
            FILE *out=fopen(path,"wb");assert(out);
            assert(fwrite(flip?flipped:upright,1,frame_bytes,out)==frame_bytes && !fclose(out));
        }
        if(flip)for(int y=0;y<2160;y++){
            if(memcmp(upright+(size_t)y*3840*4,flipped+(size_t)(2159-y)*3840*4,3840*4))
                fprintf(stderr,"Master orientation %dx%d row %d\n",w,h,y);
            assert(!memcmp(upright+(size_t)y*3840*4,flipped+(size_t)(2159-y)*3840*4,3840*4));
        }
        assert(dvbridge_render_commit(r));
        }
        for(unsigned p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&source.planes[p].texture);
        if(test==6){pl_tex_destroy(g.gl->gpu,&overlay.texture);pl_tex_destroy(g.gl->gpu,&overlay.degamma);pl_tex_destroy(g.gl->gpu,&overlay.pq);}
    }
    free(upright);free(flipped);
    dvbridge_renderer_destroy(r);pl_tex_destroy(g.gl->gpu,&output);av_free(m);reference_gpu_destroy(&g);
    puts("PASS Master 1080p, 720p and cropped sources");
}

int main(int argc,char **argv)
{
    assert(argc>=3 && !strcmp(argv[1],"--case"));
    if(!strcmp(argv[2],"current")){current_stages();return 0;}
    if(!strcmp(argv[2],"capabilities")){raw_contract();return 0;}
    if(!strcmp(argv[2],"reconstruction")){arithmetic();return 0;}
    if(!strcmp(argv[2],"spatial")){spatial();return 0;}
    if(!strcmp(argv[2],"transport")){transport(false,false);return 0;}
    if(!strcmp(argv[2],"lifecycle")){transport(true,false);return 0;}
    if(!strcmp(argv[2],"rows")){transport(false,true);return 0;}
    if(!strcmp(argv[2],"resolutions")){resolutions(false);return 0;}
    if(!strcmp(argv[2],"placement")){resolutions(true);return 0;}
    assert(!"Master Reference GPU route missing");
    return 1;
}
