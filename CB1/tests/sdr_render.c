/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_circuit.h"
#ifndef DVBRIDGE_SDR_POLICY_API
extern bool dvbridge_render_sdr_policy_rgb(struct dvbridge_renderer *,const struct dvbridge_policy *,
 const struct dvbridge_identity *,const struct pl_frame *,const void *,size_t,double,double,
 struct dvbridge_geometry) __attribute__((weak));
#endif
int main(void)
{
    /* Missing implementation must fail as behavior, not a compiler error. */
    assert(dvbridge_render_sdr_policy_rgb);
#ifdef DVBRIDGE_SDR_POLICY_API
    struct dvbridge_policy p={.revision=3,.mode=DVBRIDGE_MODE_SDR};
    double peak,gamma,black;
    assert(dvbridge_sdr_target(&p.sdr,&peak,&gamma,&black) && peak==100 && gamma==2.4 && black==0);
    p.sdr.preset=DVBRIDGE_SDR_BRIGHT;
    assert(dvbridge_sdr_target(&p.sdr,&peak,&gamma,&black) && peak==200 && gamma==2.2);
    p.sdr=(struct dvbridge_sdr_profile){DVBRIDGE_SDR_CUSTOM,80,2.6,.02};
    assert(dvbridge_policy_validate(&p)==DVBRIDGE_POLICY_VALID);
    p.sdr.gamma=NAN;assert(dvbridge_policy_validate(&p)==DVBRIDGE_POLICY_INVALID_VALUE);
    p.sdr.gamma=2.6;p.sdr.black_nits=INFINITY;
    assert(dvbridge_policy_validate(&p)==DVBRIDGE_POLICY_INVALID_VALUE);
    p.sdr=(struct dvbridge_sdr_profile){0};
    assert(CB1_DV_SDR==14 && CB1_HDR10_SDR==15 && CB1_HLG_DV_REFERENCE==16);
    assert(cb1_circuit_version(CB1_DV_SDR));
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu.gl->gpu);assert(r);
    const float pixels[]={.5,.5,.5,1, .75,.75,.75,1, .1,.1,.1,1, .9,.2,.1,1};
    pl_tex input=reference_texture(gpu.gl->gpu,2,2,pixels);
    pl_tex output=reference_texture(gpu.gl->gpu,2,2,NULL);
    struct pl_frame frame=reference_frame(input,2,2);
    frame.repr=pl_color_repr_rgb;
    frame.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
        .hdr={.max_luma=1000}};
    const struct dvbridge_identity id={1,1,3};
    const struct dvbridge_geometry g={2,2,0,0,2,2,2,2};
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,0,0,g));
    const struct dvbridge_hdr10_policy_output *o=dvbridge_render_policy_output(r);assert(o);
    assert(o->container.primaries==PL_COLOR_PRIM_BT_709 && o->container.transfer==PL_COLOR_TRC_GAMMA24);
    assert(o->container.hdr.min_luma==PL_COLOR_HDR_BLACK); /* Zero means unknown to libplacebo. */
    assert(!o->hdr10.max_luminance && !o->resolved);
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,8));
    struct dvbridge_identity wrong=id;wrong.picture++;
    assert(!dvbridge_render_policy_commit(r,&wrong,output));
    assert(dvbridge_render_policy_commit(r,&id,output));
    float actual[16];reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
    for(unsigned i=0;i<16;i++)assert(isfinite(actual[i]) && actual[i]>=0 && actual[i]<=1.001);
    assert(actual[0]>.1 && actual[0]<actual[4]);
    float static_hdr10[16];memcpy(static_hdr10,actual,sizeof(actual));
    frame.color.hdr.scene_max[0]=frame.color.hdr.scene_max[1]=frame.color.hdr.scene_max[2]=400;
    frame.color.hdr.scene_avg=100;
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,0,0,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,8));
    reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
    float dynamic_effect=0;
    for(unsigned i=0;i<16;i++)dynamic_effect=fmaxf(dynamic_effect,fabs(actual[i]-static_hdr10[i]));
    assert(dynamic_effect>.005); /* Accepted HDR10+ MaxSCL/average guide SDR. */
    memset(frame.color.hdr.scene_max,0,sizeof(frame.color.hdr.scene_max));frame.color.hdr.scene_avg=0;
    /* Custom gamma transforms the signal inside its legal video range. */
    p.sdr=(struct dvbridge_sdr_profile){DVBRIDGE_SDR_CUSTOM,100,2.4,0};
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,0,0,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,true,10));
    float gamma24[16];reference_read(gpu.gl->gpu,output,0,0,2,2,gamma24);
    p.sdr.gamma=2.3;
    assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,0,0,g));
    assert(dvbridge_render_sdr_policy_resolve(r,output,false,true,10));
    reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
    for(unsigned i=0;i<16;i++)if(i%4!=3){
        double offset=64./1023,span=876./1023;
        double want=offset+span*pow(fmax(0,(gamma24[i]-offset)/span),2.4/2.3);
        assert(fabs(actual[i]-want)<.002);
    }
    p.sdr=(struct dvbridge_sdr_profile){0};
    /* Independently reconstructed DV must map exactly like its complete RGB
     * image. Exercise a real non-neutral FEL and HLG-base DV source tags. */
    size_t dvbytes;AVDOVIMetadata *dv=task3_fixture(&dvbytes);
    pl_renderer oracle=pl_renderer_create(NULL,gpu.gl->gpu);assert(oracle);
    const float residual[]={.6,.6,.6,1,.7,.7,.7,1,.55,.55,.55,1,.6,.6,.6,1};
    pl_tex et=reference_texture(gpu.gl->gpu,2,2,residual);
    struct pl_frame enhancement=reference_frame(et,2,2),dvframe=frame;
    dvframe.repr=(struct pl_color_repr){0};dvframe.color.transfer=PL_COLOR_TRC_HLG;
    float without_fel[16];
    for(unsigned fel=0;fel<2;fel++){
        av_dovi_get_header(dv)->disable_residual_flag=!fel;
        dvframe.enhancement_layer=fel?&enhancement:NULL;
        AVDOVIDataMapping *mapping=av_dovi_get_mapping(dv);mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
        for(unsigned c=0;c<3;c++){
            mapping->nlq[c].nlq_offset=512;mapping->nlq[c].linear_deadzone_slope=4096;
            mapping->nlq[c].vdr_in_max=1023*4096;
        }
        struct dvbridge_color mapped;assert(dvbridge_map_color(&mapped,dv,dvbytes,fel));
        pl_tex reconstructed_tex=reference_texture(gpu.gl->gpu,2,2,NULL);
        struct pl_frame oracle_source=dvframe;oracle_source.repr=mapped.repr;oracle_source.color=mapped.color;
        struct pl_frame oracle_target=reference_frame(reconstructed_tex,2,2);
        oracle_target.repr=pl_color_repr_rgb;oracle_target.color=mapped.color;
        struct pl_render_params params=pl_render_default_params;params.min_fbo_precision=32;
        params.peak_detect_params=NULL;params.dither_params=NULL;
        assert(pl_render_image(oracle,&oracle_source,&oracle_target,&params));
        struct pl_frame plain=reference_frame(reconstructed_tex,2,2);plain.repr=pl_color_repr_rgb;plain.color=mapped.color;
        assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&plain,NULL,0,1,1,g));
        assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,10));
        float expected[16];reference_read(gpu.gl->gpu,output,0,0,2,2,expected);
        assert(dvbridge_render_sdr_policy_rgb(r,&p,&id,&dvframe,dv,dvbytes,1,1,g));
        assert(dvbridge_render_policy_output(r)->fel_reconstructed==!!fel);
        assert(dvbridge_render_sdr_policy_resolve(r,output,false,false,10));
        reference_read(gpu.gl->gpu,output,0,0,2,2,actual);
        float fel_effect=0;
        for(unsigned i=0;i<16;i++){
            assert(fabs(actual[i]-expected[i])<.002);
            if(fel)fel_effect=fmaxf(fel_effect,fabs(actual[i]-without_fel[i]));
        }
        if(fel)assert(fel_effect>.002);else memcpy(without_fel,actual,sizeof(actual));
        pl_tex_destroy(gpu.gl->gpu,&reconstructed_tex);
    }
    pl_renderer_destroy(&oracle);pl_tex_destroy(gpu.gl->gpu,&et);av_free(dv);
    /* A mismatched FEL must reject the whole picture and clear pending output. */
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    struct pl_frame el=frame;frame.enhancement_layer=&el;
    av_dovi_get_header(m)->disable_residual_flag=0;
    assert(!dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,m,bytes,1,2,g));
    assert(!dvbridge_render_policy_output(r));av_free(m);
    frame.enhancement_layer=NULL;frame.color.hdr.max_luma=NAN;
    assert(!dvbridge_render_sdr_policy_rgb(r,&p,&id,&frame,NULL,0,1,1,g));
    assert(!dvbridge_render_policy_output(r));
    dvbridge_renderer_destroy(r);
    pl_tex_destroy(gpu.gl->gpu,&input);pl_tex_destroy(gpu.gl->gpu,&output);reference_gpu_destroy(&gpu);
#endif
    return 0;
}
