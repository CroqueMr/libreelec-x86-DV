/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
#include <libplacebo/dispatch.h>

static bool tracing, reconstructed_source_domain;
static bool quad_disabled;
static unsigned reconstruction_width, reconstruction_height;
static unsigned final_draws;
static unsigned rgb_materializations;
static unsigned scratch_allocations, native_clears;
static unsigned native_width, native_height;
static unsigned scaler_passes;
static void count_scaler_pass(void *priv,const struct pl_render_info *info)
{ (void)priv;(void)info;scaler_passes++; }
static int final_precision;
static float final_antiringing;

static bool trace_render(pl_renderer renderer, const struct pl_frame *image,
    const struct pl_frame *target, const struct pl_render_params *params)
{
    assert((!quad_disabled || !params->cb1_quad_scaler) && "Other circuits must not enable Adaptive tap reuse");
    if(tracing){
        if(image->repr.dovi){
            reconstruction_width=lroundf(target->crop.x1-target->crop.x0);
            reconstruction_height=lroundf(target->crop.y1-target->crop.y0);
            reconstructed_source_domain=params->cb1_dovi_transport;
        }
        if(target->planes[0].texture->params.w==3840 &&
           (image->crop.x1-image->crop.x0)!=3840){
            final_draws++;
            rgb_materializations+=target->planes[0].texture->params.format->type==PL_FMT_FLOAT;
            final_precision=params->min_fbo_precision;
            final_antiringing=params->antiringing_strength;
        }
    }
    struct pl_render_params measured=*params;
    if(tracing && target->planes[0].texture->params.w==3840 &&
       target->planes[0].texture->params.format->type==PL_FMT_UNORM &&
       image->planes[0].texture->params.w!=3840){
        measured.info_callback=count_scaler_pass;scaler_passes=0;
    }
    bool ok=pl_render_image(renderer,image,target,&measured);
    if(tracing && !ok){
        struct pl_render_errors errors=pl_renderer_get_errors(renderer);
        fprintf(stderr,"Render failed: dst %.0fx%.0f linear=%u errors=%u disabled=%d\n",
            target->crop.x1-target->crop.x0,target->crop.y1-target->crop.y0,
            params->cb1_dovi_linear,errors.errors,errors.num_disabled_hooks);
    }
    return ok;
}
static void GL_APIENTRY trace_buffer_data(GLenum target,GLsizeiptr size,const void *data,GLenum usage)
{
    if(tracing && target==GL_SHADER_STORAGE_BUFFER)scratch_allocations++;
    glBufferData(target,size,data,usage);
}
static void trace_clear(pl_gpu gpu,pl_tex texture,const float color[4])
{
    if(tracing && texture->params.w==(int)native_width && texture->params.h==(int)native_height)
        native_clears++;
    pl_tex_clear(gpu,texture,color);
}
#define glBufferData trace_buffer_data
#define pl_tex_clear trace_clear
#define pl_render_image trace_render
#include "../src/dvbridge_render.c"
#undef pl_render_image
#undef pl_tex_clear
#undef glBufferData
#include <time.h>

static void finish(struct dvbridge_renderer *r)
{
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_poll(r);
        if(status==DVBRIDGE_DV_READY)return;
        assert(status==DVBRIDGE_DV_PENDING || status==DVBRIDGE_DV_BUSY);
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"Completion timed out");
}

static GLenum GL_APIENTRY withheld_fence(GLsync fence,GLbitfield flags,GLuint64 timeout)
{ (void)fence;(void)flags;(void)timeout;return GL_TIMEOUT_EXPIRED; }

static void cancel_composition(struct dvbridge_renderer *r)
{
    assert(r->dv.fence && "Final source-size composition must retain a retirement fence");
    PFNGLCLIENTWAITSYNCPROC wait=r->dv.wait_sync;
    r->dv.wait_sync=withheld_fence;
    dvbridge_render_dv_policy_cancel(r);
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_BUSY);
    r->dv.wait_sync=wait;
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_poll(r);
        if(status==DVBRIDGE_DV_IDLE)return;
        assert(status==DVBRIDGE_DV_BUSY);
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"Composition retirement timed out");
}

static void check_ceiling(struct dvbridge_renderer *r)
{
    if(!getenv("CB1_TEST_CEILING"))return;
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(r->dv.enhanced_plan.status==CB1_DVE_READY);
    size_t count=3840u*2160u;
    float *picture=malloc(count*4*sizeof(*picture));assert(picture);
    pl_tex rgb=dvbridge_render_dv_policy_rgb(r);assert(rgb);
    reference_read(r->gpu,rgb,0,0,3840,2160,picture);
    float maximum=0,minimum=1,ceiling=dv_ideal_pq(r->dv.enhanced_plan.envelope);
    for(size_t p=0;p<count;p++)for(unsigned c=0;c<3;c++){
        float value=picture[4*p+c];assert(isfinite(value));
        maximum=fmaxf(maximum,value);minimum=fminf(minimum,value);
    }
    fprintf(stderr,"Final PQ bounds %.9g..%.9g, ceiling %.9g\n",minimum,maximum,ceiling);
    assert(minimum>=0 && maximum<=ceiling+2e-6);
    free(picture);
}

static pl_tex request_rgb(struct dvbridge_renderer *r)
{
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
    void *metadata=av_memdup(out->output_metadata,out->bytes);assert(metadata);
    unsigned before=final_draws;
    bool native=out->intermediate->params.w!=3840 || out->intermediate->params.h!=2160;
    pl_tex rgb=dvbridge_render_dv_policy_rgb(r);assert(rgb);
    assert(rgb->params.w==3840 && rgb->params.h==2160);
    assert(final_draws==before+native);
    assert(dvbridge_render_dv_policy_rgb(r)==rgb && final_draws==before+native);
    assert(!memcmp(metadata,out->output_metadata,out->bytes));
    av_free(metadata);return rgb;
}

static void compare_lazy_transport(struct dvbridge_renderer *r,pl_tex target,unsigned fbo,bool flip)
{
    const size_t bytes=3840u*2160u*4;
    unsigned char *direct=malloc(bytes),*compat=malloc(bytes);assert(direct && compat);
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,direct);
    request_rgb(r);
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,compat);
    size_t differences=0;unsigned maximum=0;
    for(size_t i=0;i<bytes;i++){
        unsigned delta=abs((int)direct[i]-(int)compat[i]);
        differences+=delta!=0;maximum=maximum>delta?maximum:delta;
    }
    fprintf(stderr,"Lazy RGB transport: %zu differing bytes, max %u\n",differences,maximum);
    assert(!differences);
    pl_tex rgb=dvbridge_render_dv_policy_rgb(r);
    pl_tex_clear(r->gpu,rgb,(float[4]){.125,.25,.5,1});
    assert(dvbridge_render_dv_policy_rgb(r)==rgb);
    float pixel[4];reference_read(r->gpu,rgb,17,19,1,1,pixel);
    assert(pixel[0]==.125f && pixel[1]==.25f && pixel[2]==.5f);
    free(direct);free(compat);
}

static void check_rejected_target(struct dvbridge_renderer *r,const struct dvbridge_policy *policy,
    const struct dvbridge_identity *id,const struct pl_frame *source,const void *metadata,size_t bytes,
    struct dvbridge_geometry geometry)
{
    dvbridge_render_dv_policy_cancel(r);glFinish();
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    pl_tex small=pl_tex_create(r->gpu,pl_tex_params(.w=128,.h=72,
        .format=pl_find_named_fmt(r->gpu,"rgba8"),.renderable=true));assert(small);
    unsigned fbo;assert(pl_opengl_unwrap(r->gpu,small,NULL,NULL,&fbo));
    unsigned char before[128*72*4],after[sizeof(before)];
    pl_tex_clear(r->gpu,small,(float[4]){.25,.5,.75,1});
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,128,72,GL_RGBA,GL_UNSIGNED_BYTE,before);
    assert(dvbridge_render_dv_policy_prepare_packed(r,policy,id,source,metadata,bytes,
        0,0,geometry,small,false,NULL)==DVBRIDGE_DV_PENDING);
    finish(r);
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,128,72,GL_RGBA,GL_UNSIGNED_BYTE,after);
    assert(!memcmp(before,after,sizeof(before)) && "Preparation must not write an unvalidated output target");
    assert(!dvbridge_render_dv_policy_resolve(r,small,fbo,false));
    glFinish();assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    pl_tex_destroy(r->gpu,&small);
}

static void check_final_scale(struct dvbridge_renderer *r,bool expert)
{
    pl_renderer oracle=pl_renderer_create(NULL,r->gpu);assert(oracle);
    pl_tex expected=reference_texture(r->gpu,3840,2160,NULL);
    struct pl_frame image={.num_planes=1,
        .planes={{.texture=r->native_picture,.components=4,.component_mapping={0,1,2,3}}},
        .repr=pl_color_repr_rgb,.color=r->reconstructed_color,
        .crop={0,0,r->native_picture->params.w,r->native_picture->params.h}};
    struct pl_frame output=image;output.planes[0].texture=expected;output.crop=(pl_rect2df){0,0,3840,2160};
    struct pl_render_params params=pl_render_default_params;
    params.min_fbo_precision=32;params.peak_detect_params=NULL;params.dither_params=NULL;
    params.frame_mixer=NULL;params.sigmoid_params=NULL;params.cb1_nearest_identity=true;
    params.cb1_fp32_scaler_lut=expert;
    params.cb1_stable_pq=true;
    assert(pl_render_image(oracle,&image,&output,&params));
    for(unsigned i=0;i<24;i++){
        unsigned x=17+(i*157)%3800,y=13+(i*193)%2100;
        float actual[4],wanted[4];reference_read(r->gpu,r->rgb,x,y,1,1,actual);
        reference_read(r->gpu,expected,x,y,1,1,wanted);
        float maximum=dv_ideal_pq(r->reconstructed_color.hdr.max_luma);
        for(unsigned c=0;c<3;c++){
            wanted[c]=fminf(maximum,fmaxf(0,wanted[c]));
            if(wanted[c]<=7.30956e-7f)wanted[c]=0;
            assert(fabs(actual[c]-wanted[c])<=2e-6);
        }
    }
    pl_tex_destroy(r->gpu,&expected);pl_renderer_destroy(&oracle);
}

int main(int argc,char **argv)
{
    assert(argc==3 && !strcmp(argv[1],"--case"));
    const char *name=argv[2];
    const bool flip=getenv("CB1_TEST_FLIP")!=NULL;
    const bool full1080=getenv("CB1_TEST_FULL1080")!=NULL;
    const unsigned w=full1080?1920:64,h=full1080?1080:getenv("CB1_TEST_CROPPED")?26:36;
    quad_disabled=strcmp(name,"adaptive")!=0;
    struct reference_gpu gpu=reference_gpu_create();
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu.gl->gpu);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    assert(!dvbridge_render_dv_policy_rgb(r));
    if(getenv("CB1_TEST_NO_QUAD"))r->fragment_quad=false;
    if((!strcmp(name,"standard") || getenv("CB1_TEST_CLONE")) && !r->fragment_quad){
        fputs("SKIP Standard fused transport requires fragment subgroup quad support\n",stderr);
        dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));reference_gpu_destroy(&gpu);
        return 77;
    }
    if(gpu.log){pl_renderer_destroy(&r->renderer);r->renderer=pl_renderer_create(gpu.log,r->gpu);assert(r->renderer);}
    float *pixels=malloc((size_t)w*h*4*sizeof(*pixels));assert(pixels);
    for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)for(unsigned c=0;c<4;c++)
        pixels[4*(y*w+x)+c]=c==3?1:dv_ideal_pq((x<4?0.01:20+(x*11+y*7)%400)*(1+.12*c));
    if(getenv("CB1_TEST_CEILING"))
        for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++)for(unsigned c=0;c<4;c++)
            pixels[4*(y*w+x)+c]=c==3?1:x<w/2?dv_ideal_pq(1000):0;
    pl_tex input=reference_texture(r->gpu,w,h,pixels);free(pixels);
    struct pl_frame source=reference_frame(input,w,h);
    size_t bytes;AVDOVIMetadata *metadata=task3_fixture(&bytes);
    metadata->num_ext_blocks=2;
    av_dovi_get_color(metadata)->source_max_pq=3079;
    *av_dovi_get_ext(metadata,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1463}};
    *av_dovi_get_ext(metadata,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2851,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    const struct dvbridge_geometry geometry={w,h,0,h==26?300:0,3840,h==26?1560:2160};
    struct dvbridge_identity id={1,1,1};
    struct dvbridge_policy policy=reference_policy();
    policy.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    pl_tex target=pl_tex_create(r->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(r->gpu,"rgba8"),.renderable=true));assert(target);
    unsigned fbo;pl_opengl_unwrap(r->gpu,target,NULL,NULL,&fbo);
    native_width=w;native_height=h;
    tracing=true;
    if(!strcmp(name,"hdr10")){
        struct dvbridge_hdr10_session session;
        assert(dvbridge_hdr10_session_init(&session,metadata,bytes));
        assert(dvbridge_render_hdr10_rgb(r,&session,&source,metadata,bytes,0,NAN,geometry));
        fprintf(stderr,"Basic processing target %ux%u, expected %ux%u\n",
            reconstruction_width,reconstruction_height,w,h);
        assert(reconstruction_width==w && reconstruction_height==h);
        if(h==36)check_final_scale(r,false);
        reconstruction_width=reconstruction_height=0;
        assert(dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&source,metadata,bytes,0,0,geometry));
        assert(reconstruction_width==w && reconstruction_height==h);
        if(h==36)check_final_scale(r,true);
        struct dvbridge_geometry invalid=geometry;invalid.width=0;
        assert(!dvbridge_render_hdr10_rgb(r,&session,&source,metadata,bytes,1,NAN,invalid));
        assert(!dvbridge_render_texture(r) && "Rejected geometry must not expose a native intermediate");
    }else if(!strcmp(name,"adaptive")){
        policy.mode=DVBRIDGE_MODE_ENHANCED_DV;policy.adaptive=DVBRIDGE_ADAPTIVE_B_FP16;
        policy.tv.peak_nits=2300;
        assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&source,metadata,bytes,
            0,0,geometry,target,flip,NULL)==DVBRIDGE_DV_PENDING);
        fprintf(stderr,"Adaptive scratch allocations: %u\n",scratch_allocations);
        assert(scratch_allocations==2 && "Allocate each scratch buffer once at its required size");
        assert(!dvbridge_render_dv_policy_rgb(r));
        assert(r->enhanced_rgb->params.w==(int)w && r->enhanced_rgb->params.h==(int)h);
        if(getenv("CB1_TEST_RECOVERY")){
            assert(r->enhanced_linear && r->dv.fence);
            /* Retire completed analysis before deriving a source-bound record. */
            glFinish();r->dv.delete_sync(r->dv.fence);r->dv.fence=NULL;
            uint32_t record[16];memcpy(record,r->dv.mapped,sizeof(record));record[11]=1;
            r->enhanced_skip_aux=false;
            assert(dve_derive(r,record));
            r->dv.ready=r->ready=true;
            assert(r->dv.output.value.expansion_reason==CB1_DVE_SOURCE_BOUND);
            cancel_composition(r);
            goto cleanup;
        }
        finish(r);
        assert(dvbridge_render_dv_policy_output(r)->intermediate->params.w==(int)w &&
            "Packed preparation must defer final enlargement until resolve");
        assert(!rgb_materializations);
        assert(!r->dv.packed_target && "Final transport is validated before writing");
        request_rgb(r);
        check_ceiling(r);
        cancel_composition(r);
        assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&source,metadata,bytes,
            0,0,geometry,target,flip,NULL)==DVBRIDGE_DV_PENDING);
        finish(r);assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));
        if(getenv("CB1_TEST_CLONE") && r->fragment_quad && !geometry.x && !geometry.y){
            fprintf(stderr,"Final scaler GPU passes: %u\n",scaler_passes);
            assert(scaler_passes==2 && "Authored RGB needs only the two Lanczos passes, not a native copy");
        }
        compare_lazy_transport(r,target,fbo,flip);
        fprintf(stderr,"Adaptive final precision %d, anti-ringing %g\n",final_precision,final_antiringing);
        assert(final_precision==32 && final_antiringing==0);
        check_rejected_target(r,&policy,&id,&source,metadata,bytes,geometry);
    }else if(!strcmp(name,"ai")){
        policy.mode=DVBRIDGE_MODE_ENHANCED_DV;policy.tv.peak_nits=2300;
        source.repr=pl_color_repr_rgb;
        source.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,
            .hdr={.min_luma=0,.max_luma=1000}};
        struct cb1_ai_result prediction={.id={1,1,1},.pts=0,
            .raw={.l1_min=0,.l1_max=3079,.l1_avg=1463,.l3_min=2048,.l3_max=2048,.l3_avg=2048}};
        assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
        fprintf(stderr,"AI native clears: %u\n",native_clears);
        assert(!native_clears && "A fully overwritten native picture needs no clear");
        fprintf(stderr,"AI expansion target %dx%d, expected %ux%u\n",
            r->enhanced_rgb->params.w,r->enhanced_rgb->params.h,w,h);
        assert(r->enhanced_rgb->params.w==(int)w && r->enhanced_rgb->params.h==(int)h);
        finish(r);
        assert(dvbridge_render_dv_policy_output(r)->intermediate->params.w==(int)w && !final_draws);
        if(r->fragment_quad && !getenv("CB1_TEST_CEILING")){
            assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));
            compare_lazy_transport(r,target,fbo,flip);
        }else request_rgb(r);
        check_ceiling(r);cancel_composition(r);
    }else if(!strcmp(name,"standard")){
        AVDOVIColorMetadata *c=av_dovi_get_color(metadata);
        av_dovi_get_header(metadata)->vdr_bit_depth=12;c->signal_bit_depth=12;c->signal_full_range_flag=1;
        for(unsigned i=0;i<3;i++)c->ycc_to_rgb_offset[i]=(AVRational){1,i?2:16};
        assert(dvbridge_dv_source_transport(metadata));
        dvbridge_renderer_set_optimized_dv(r,true);
        dvbridge_renderer_set_processing_optimizations(r,true);
        assert(dvbridge_render_packed(r,&source,metadata,bytes,0,NAN,geometry,target,false));
        assert(reconstructed_source_domain && "Scaling must not add a movie colour conversion");
        assert(!r->processing.pq_texture[0] && !r->processing.pq_texture[1] &&
            "Source-domain transport must not allocate unused PQ conversions");
    }else assert(!"Unknown resolution-contract case");
cleanup:
    tracing=false;dvbridge_render_dv_policy_cancel(r);glFinish();
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    pl_tex_destroy(r->gpu,&target);pl_tex_destroy(r->gpu,&input);av_free(metadata);
    dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));reference_gpu_destroy(&gpu);
    puts("PASS source-resolution processing contract");
}
