/* SPDX-License-Identifier: MIT */
/* Standalone oracle probe. No capture or test hook is linked into CB1. */
#include "reference_test.h"
#include CB1_RENDER_IMPLEMENTATION

static unsigned records;
static void emit(const void *bytes,size_t count)
{
#ifdef CB1_MUTATE_CAPTURE
    if(!records && count){
        unsigned char first=*(const unsigned char *)bytes^1;
        assert(fwrite(&first,1,1,stdout)==1);
        bytes=(const unsigned char *)bytes+1;count--;
    }
#endif
    assert(fwrite(bytes,1,count,stdout)==count);records++;
}
static void carrier(pl_gpu gpu,pl_tex texture)
{
    size_t count=(size_t)texture->params.w*texture->params.h*4;
    unsigned char *bytes=malloc(count);assert(bytes);
    unsigned fbo;pl_opengl_unwrap(gpu,texture,NULL,NULL,&fbo);assert(fbo);
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glReadPixels(0,0,texture->params.w,texture->params.h,GL_RGBA,GL_UNSIGNED_BYTE,bytes);
    assert(glGetError()==GL_NO_ERROR);glBindFramebuffer(GL_FRAMEBUFFER,0);
    emit(bytes,count);free(bytes);
}
static void trim_probe(pl_gpu gpu,pl_dispatch dp)
{
    enum{W=128,H=32};float pixels[W*H*4],output[W*H*4];
    for(unsigned i=0;i<W*H;i++)for(unsigned c=0;c<4;c++)
        pixels[4*i+c]=c==3?1:(float)((i*(17+c*13))%8191)/4096;
    pl_tex input=reference_texture(gpu,W,H,pixels),target=reference_texture(gpu,W,H,NULL);
    const double controls[][5]={{2048,2048,2048,2048,2048},{1200,1980,2400,2300,2700},
        {2048.25,1900.5,2200.125,1800.25,2600.5},{4095,4095,0,4095,4095}};
    for(unsigned c=0;c<4;c++){
        struct reference_hook hook={.creative_plan.policy.tv.peak_nits=1500};
        memcpy(hook.creative_plan.codes,controls[c],sizeof(controls[c]));
        pl_shader sh=pl_dispatch_begin(dp);
        assert(pl_shader_sample_direct(sh,pl_sample_src(.tex=input)));
        assert(cm29_add_sop(sh,&hook) && cm29_add_chroma(sh,&hook));
        assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));
        reference_read(gpu,target,0,0,W,H,output);emit(output,sizeof(output));
    }
    pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&target);
}
static void transport_probe(pl_gpu gpu,pl_dispatch dp,bool quad)
{
    enum{W=3840,H=2160};size_t count=(size_t)W*H;
    float *pixels=malloc(count*4*sizeof(float));assert(pixels);
    for(size_t i=0;i<count;i++)for(unsigned c=0;c<4;c++)
        pixels[4*i+c]=c==3?1:(float)((i*(17+c*13)+c*971)%65536)/65535;
    pl_tex input=reference_texture(gpu,W,H,pixels);free(pixels);
    pl_tex target=pl_tex_create(gpu,pl_tex_params(.w=W,.h=H,.format=pl_find_named_fmt(gpu,"rgba8"),.renderable=true));assert(target);
    pl_tex gui=reference_texture(gpu,W,H,NULL),lut=reference_texture(gpu,1,1,(float[4]){.1,.2,.3,1});
    pl_tex_clear(gpu,gui,(float[4]){.08,.12,.04,.5});
    struct dvbridge_native_overlay overlay={.texture=gui,.degamma=lut,.pq=lut,.rect={0,0,3840,2160}};
    uint32_t words[640];for(unsigned i=0;i<640;i++)words[i]=(i*173+71)&255;
    for(unsigned reference=0;reference<2;reference++){
        if(!reference && !quad)continue;
        for(unsigned scaled=0;scaled<=reference;scaled++)
        for(unsigned flip=0;flip<2;flip++)for(unsigned gui_state=0;gui_state<3;gui_state++){
            struct active_mask mask={.source_domain=true,.reference_transport=reference,
                .rect={2,111,3838,2037},.packets=words,.count=5,.flip=flip,
                .overlay=gui_state?&overlay:NULL,.source_overlay=gui_state!=0,
                .scaled_reference=scaled?input:NULL,.scaled_rect={0,0,1,1}};
            for(unsigned i=0;i<3;i++){mask.nonlinear[4*i]=1;mask.linear[4*i]=1;}
            overlay.input_pq=gui_state==2;
            pl_shader sh=pl_dispatch_begin(dp);
            if(!scaled)assert(pl_shader_sample_direct(sh,pl_sample_src(.tex=input)));
            struct pl_hook_params p={.stage=PL_HOOK_OUTPUT,.sh=sh};
            assert(!pack_active_area(&mask,&p).failed && mask.called);
            assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));
            carrier(gpu,target);
        }
    }
    if(quad)for(unsigned flip=0;flip<2;flip++){
        struct active_mask mask={.rect={0,0,3840,2160},.packets=words,.count=5,.flip=flip};
        pl_shader sh=pl_dispatch_begin(dp);assert(pl_shader_sample_direct(sh,pl_sample_src(.tex=input)));
        struct pl_hook_params p={.stage=PL_HOOK_OUTPUT,.sh=sh};
        assert(!pack_active_area(&mask,&p).failed && mask.called);
        assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));carrier(gpu,target);
    }
    pl_tex_destroy(gpu,&gui);pl_tex_destroy(gpu,&lut);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&target);
}
static void adaptive_probe(pl_gpu gpu)
{
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    struct cb1_dv_enhanced_source source={.master=1000,.l1_present=true,.analysis={0,3079,1463}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,.tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct cb1_dv_enhanced_plan plan;assert(cb1_dv_enhanced_build(&plan,&source,&policy)==CB1_DVE_READY);
    enum{W=3840,H=2160};size_t count=(size_t)W*H;
    float *pixels=malloc(count*4*sizeof(float));assert(pixels);
    for(unsigned linear=0;linear<2;linear++){
        for(size_t i=0;i<count;i++)for(unsigned c=0;c<4;c++){
            double nits=.01+(i*(13+c*19)%997);
            pixels[4*i+c]=c==3?1:linear?nits/10000:dv_ideal_pq(nits);
        }
        pl_tex input=reference_texture(gpu,W,H,pixels);
        r->enhanced_linear=linear;r->enhanced_skip_aux=!linear;r->enhanced_authored_curve=true;
        assert(dve_allocate(r,W,H,false,false) && r->enhanced_prepack);
        r->dv.output.value.identity=(struct dvbridge_identity){1,1,1};
        assert(dve_run(r,&plan,input,(unsigned[4]){0,0,111,123}));glFinish();
        assert(r->dv.prepacked && r->dv.mapped[10] && !r->dv.mapped[11]);
        /* Non-authored mode publishes 12 words; the following four are unused. */
        emit(r->dv.mapped,12*sizeof(uint32_t));
        pl_tex wrapped=pl_opengl_wrap(gpu,pl_opengl_wrap_params(.texture=r->enhanced_packed_texture,
            .width=W,.height=H,.iformat=GL_RGBA8));assert(wrapped);carrier(gpu,wrapped);
        pl_tex_destroy(gpu,&wrapped);pl_tex_destroy(gpu,&input);dv_release(r);
    }
    free(pixels);dvbridge_renderer_destroy(r);
}
int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    bool quad=pl_opengl_has_ext(g.gl,"GL_KHR_shader_subgroup");
    fprintf(stderr,"Quad exchange: %s\n",quad?"available":"unqualified (extension unavailable)");
    pl_dispatch dp=pl_dispatch_create(g.log,g.gl->gpu);assert(dp);
    trim_probe(g.gl->gpu,dp);transport_probe(g.gl->gpu,dp,quad);adaptive_probe(g.gl->gpu);
    fprintf(stderr,"Complete captured records: %u\n",records);
    pl_dispatch_destroy(&dp);reference_gpu_destroy(&g);return 0;
}
