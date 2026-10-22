/* SPDX-License-Identifier: GPL-3.0-only */
#include "reference_test.h"
static pl_tex reconstructed_texture;
static bool trace_render(pl_renderer renderer,const struct pl_frame *image,
    const struct pl_frame *target,const struct pl_render_params *params)
{
    if(image->repr.dovi)reconstructed_texture=target->planes[0].texture;
    return pl_render_image(renderer,image,target,params);
}
#define DVBRIDGE_PQ_ENCODER_TEST 1
#define pl_render_image trace_render
#include "../src/dvbridge_render.c"
#undef pl_render_image

static pl_tex stripes(pl_gpu gpu,unsigned w,unsigned h)
{
    const double levels[]={0,.001,.01,.1,1,10,100,600};
    float *data=malloc((size_t)w*h*4*sizeof(float));assert(data);
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){
        for(unsigned c=0;c<3;c++)data[4*((size_t)y*w+x)+c]=dv_ideal_pq(levels[x*8/w]*(1+.04*c));
        data[4*((size_t)y*w+x)+3]=1;
    }
    pl_tex result=reference_texture(gpu,w,h,data);free(data);return result;
}

int main(void)
{
    const unsigned native_width=getenv("CB1_TEST_NATIVE_1080")?1920:64,native_height=native_width*9/16;
    struct reference_gpu g=reference_gpu_create();pl_gpu gpu=g.gl->gpu;
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    struct dvbridge_renderer *dense=dvbridge_renderer_create(gpu);assert(dense);
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);
    av_dovi_get_color(metadata)->source_max_pq=3696;
    metadata->num_ext_blocks=3;
    *av_dovi_get_ext(metadata,0)=(AVDOVIDmData){.level=1,.l1={0,3696,1500}};
    *av_dovi_get_ext(metadata,1)=(AVDOVIDmData){.level=6,.l6={.max_luminance=4000,.min_luminance=1}};
    *av_dovi_get_ext(metadata,2)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    av_dovi_get_header(metadata)->disable_residual_flag=0;
    av_dovi_get_mapping(metadata)->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++)av_dovi_get_mapping(metadata)->nlq[c]=(AVDOVINLQParams){.nlq_offset=512,.linear_deadzone_slope=1};
    void *single=av_memdup(metadata,bytes);assert(single);av_dovi_get_header(single)->disable_residual_flag=1;
    float ep[16];for(unsigned i=0;i<16;i++)ep[i]=i%4==3?1:512.0f/1023;
    pl_tex el=reference_texture(gpu,2,2,ep);struct pl_frame enhancement=reference_frame(el,2,2);
    pl_tex output=reference_texture(gpu,3840,2160,NULL);
    struct dvbridge_policy policy=reference_policy();policy.tv.peak_nits=1000;policy.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    struct dvbridge_identity identity={1,1,1};
    pl_tex full=stripes(gpu,3840,2160),native=stripes(gpu,native_width,native_height);
    struct pl_frame source=reference_frame(full,3840,2160);source.enhancement_layer=&enhancement;
    assert(dvbridge_render_hdr10_policy_direct(r,&policy,&identity,&source,metadata,bytes,0,0,
        (struct dvbridge_geometry){3840,2160,0,0,3840,2160},output,false,false,10));
    assert(!r->cm29_tail_atlas && cm29_gpu_map_build_count==0 &&
        "Neutral Expert must not allocate or build a 160-cubed tail cache on its first frame");
    av_dovi_get_ext(metadata,2)->l2.trim_slope=2020;
    av_dovi_get_ext(metadata,2)->l2.trim_saturation_gain=2150;
    memcpy(single,metadata,bytes);av_dovi_get_header(single)->disable_residual_flag=1;
    float baseline[8][4];
    for(unsigned pass=0;pass<3;pass++){
        unsigned w=pass==1?3840:native_width,h=pass==1?2160:native_height;
        source=reference_frame(pass==1?full:native,w,h);source.enhancement_layer=&enhancement;
        struct dvbridge_geometry geometry={w,h,0,0,3840,2160};++identity.picture;
        assert(dvbridge_render_hdr10_policy_direct(r,&policy,&identity,&source,metadata,bytes,0,0,
            geometry,output,false,false,10));
        pl_tex native_texture=reconstructed_texture;
        assert(r->cm29_tail_key_valid && cm29_gpu_map_build_count==1 &&
            "Non-neutral native and 4K Expert must reuse the same qualified tail cache");
        float samples[8][4];
        for(unsigned i=0;i<8;i++)reference_read(gpu,output,i*480+240,1080,1,1,samples[i]);
        if(!pass)memcpy(baseline,samples,sizeof(baseline));
        else for(unsigned i=0;i<8;i++)for(unsigned c=0;c<3;c++)
            assert(fabs(samples[i][c]-baseline[i][c])<=1.01/1023 && "Native/4K final quantized code parity");
        source.enhancement_layer=NULL;
        assert(dvbridge_render_hdr10_policy_rgb(dense,&policy,&identity,&source,single,bytes,0,0,geometry));
        assert(dvbridge_render_hdr10_policy_resolve(dense,output,false,false,10));
        for(unsigned i=0;i<8;i++){
            float sample[4];reference_read(gpu,output,i*480+240,1080,1,1,sample);
            for(unsigned c=0;c<3;c++)assert(fabs(sample[c]-samples[i][c])<=1.01/1023 &&
                "Cached Expert must match uncached zero-residual reference within one final code");
        }
        if(pass!=1){
            assert(native_texture && native_texture->params.w==(int)w &&
                native_texture->params.h==(int)h && "Reconstruction must use the source grid");
            bool fractional=false;
            for(unsigned i=1;i<8;i++){
                float sample[4];reference_read(gpu,native_texture,i*w/8+w/16,h/2,1,1,sample);
                fractional|=fabs(sample[0]*1023-round(sample[0]*1023))>.1;
            }
            assert(fractional && "Native FP32 intermediate must not be quantized before final scaling");
        }
    }
    /* Hard transitions exercise final-scale ringing, L5, flip and range. */
    float bright[64*36*4];
    for(unsigned y=0;y<36;y++)for(unsigned x=0;x<64;x++){
        for(unsigned c=0;c<3;c++)bright[4*(y*64+x)+c]=dv_ideal_pq(x<32?0:10000);
        bright[4*(y*64+x)+3]=1;
    }
    pl_tex edge=reference_texture(gpu,64,36,bright);
    source=reference_frame(edge,64,36);policy.tv.peak_nits=600;
    av_dovi_get_header(metadata)->disable_residual_flag=1;
    av_dovi_get_ext(metadata,2)->l2.trim_slope=2048;
    av_dovi_get_ext(metadata,2)->l2.trim_saturation_gain=2048;
    metadata->num_ext_blocks=4;
    *av_dovi_get_ext(metadata,3)=(AVDOVIDmData){.level=5,.l5={3,5,2,4}};
    for(unsigned flipped=0;flipped<2;flipped++){
        ++identity.picture;
        assert(dvbridge_render_hdr10_policy_direct(r,&policy,&identity,&source,metadata,bytes,0,0,
            (struct dvbridge_geometry){64,36,0,0,3840,2160},output,flipped,true,10));
        float row[3840*4];reference_read(gpu,output,0,1080,3840,1,row);
        double cap=round(64+876*dv_ideal_pq(600)),maximum=0;
        for(unsigned x=0;x<3840;x++)for(unsigned c=0;c<3;c++){
            double code=round(row[4*x+c]*1023);
            assert(code>=64 && code<=cap && "Final scaling must not overshoot the target peak");
            if(code>maximum)maximum=code;
        }
        assert(maximum>cap-4 && "Peak test must reach the target, not test only black");
        float black[4];
        reference_read(gpu,output,3000,flipped?60:2100,1,1,black);
        for(unsigned c=0;c<3;c++)assert(round(black[c]*1023)==64 && "L5 survives scale, flip and limited range");
    }
    struct dvbridge_geometry placed={64,36,480,270,2880,1620};++identity.picture;
    assert(dvbridge_render_hdr10_policy_rgb(r,&policy,&identity,&source,metadata,bytes,0,0,placed));
    assert(!memcmp(&dvbridge_render_policy_output(r)->geometry,&placed,sizeof(placed)));
    float zero[4];reference_read(gpu,dvbridge_render_texture(r),1000,1080,1,1,zero);
    for(unsigned c=0;c<3;c++)assert(zero[c]==0 && "Unquantized scaled signal black must remain exact zero");
    assert(dvbridge_render_hdr10_policy_resolve(r,output,false,false,10));
    float black[4],white[4];reference_read(gpu,output,3000,300,1,1,black);
    reference_read(gpu,output,2800,1080,1,1,white);
    for(unsigned c=0;c<3;c++)assert(black[c]==0 && white[c]>.5 && "Placed source and L5 active area are preserved");
    pl_tex_destroy(gpu,&edge);
    pl_tex_destroy(gpu,&full);pl_tex_destroy(gpu,&native);pl_tex_destroy(gpu,&output);pl_tex_destroy(gpu,&el);
    av_free(single);av_free(metadata);dvbridge_renderer_destroy(dense);dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
    puts("PASS Expert native/4K cache, dense parity, FP32 stage, peak, L5, flip, range and placement");
}
