/* SPDX-License-Identifier: GPL-3.0-only */
#include "reference_test.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/sampling.h>
#include <time.h>
static bool stage_trace,stage_describe;
static unsigned compute_count;
static unsigned quad_scaler_calls;
static uint64_t stage_ns[4],stage_start;
static uint64_t stage_clock(void)
{
    struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));
    return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;
}
/* Serialized completion costs, not overlapping playback/headroom measurements. */
static void stage_begin(void)
{ if(stage_trace){glFinish();stage_start=stage_clock();} }
static void stage_end(unsigned kind)
{ if(stage_trace){glFinish();stage_ns[kind]+=stage_clock()-stage_start;} }
static void stage_info(void *priv,const struct pl_render_info *info)
{
    (void)priv;
    if(stage_describe)printf("LPPASS,%d,%d,%.6f,%s\n",info->index,
        info->pass->num_samples,info->pass->average/1e6,info->pass->shader->description);
}
static bool stage_render(pl_renderer renderer,const struct pl_frame *image,
    const struct pl_frame *target,const struct pl_render_params *params)
{
    struct pl_render_params measured=*params;
    bool reuse=false;
#if PL_HAVE_CB1_PROCESSING >= 10
    reuse=params->cb1_quad_scaler;
#endif
    bool eligible=image->planes[0].texture->params.w==1920 &&
        image->planes[0].texture->params.h==1080 &&
        image->crop.x0==0 && image->crop.y0==0 &&
        image->crop.x1==1920 && image->crop.y1==1080 &&
        target->planes[0].texture->params.w==3840 &&
        target->planes[0].texture->params.h==2160 &&
        target->planes[0].texture->params.format->type==PL_FMT_UNORM &&
        !params->cb1_dovi_linear;
    assert((!reuse || eligible) && "Quad scaler must be isolated to the full 1080p Adaptive transport");
    quad_scaler_calls+=reuse;
#if PL_HAVE_CB1_PROCESSING >= 10
    if(getenv("CB1_TEST_QUAD_CONTROL"))measured.cb1_quad_scaler=false;
#endif
    if(stage_trace)measured.info_callback=stage_info;
    stage_begin();bool ok=pl_render_image(renderer,image,target,&measured);
    stage_end(image->repr.dovi?0:3);return ok;
}
static void GL_APIENTRY stage_compute(GLuint x,GLuint y,GLuint z)
{
    stage_begin();glDispatchCompute(x,y,z);stage_end(compute_count++?2:1);
}
#define pl_render_image stage_render
#define glDispatchCompute stage_compute
#include "../src/dvbridge_render.c"
#undef glDispatchCompute
#undef pl_render_image

static void finish(struct dvbridge_renderer *r)
{
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status s=dvbridge_render_dv_policy_poll(r);
        if(s==DVBRIDGE_DV_READY)return;
        assert(s==DVBRIDGE_DV_PENDING || s==DVBRIDGE_DV_BUSY);
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"Adaptive completion timed out");
}

static void retire(struct dvbridge_renderer *r)
{
    dvbridge_render_dv_policy_cancel(r);glFinish();
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
}

static void read_carrier(unsigned fbo,unsigned char *out)
{
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,out);
    assert(glGetError()==GL_NO_ERROR);glBindFramebuffer(GL_FRAMEBUFFER,0);
}

static void reject_expansion(struct dvbridge_renderer *r)
{
    glFinish();uint32_t record[16];memcpy(record,r->dv.mapped,sizeof(record));
    record[11]=1;assert(dve_derive(r,record));r->dv.ready=r->ready=true;
    assert(r->dv.output.value.expansion_reason==CB1_DVE_SOURCE_BOUND);
}

static void check_quad_sampler(pl_gpu gpu)
{
#if PL_HAVE_CB1_PROCESSING >= 10
    if(!gpu->glsl.subgroup_size)return;
    pl_tex input=reference_texture(gpu,8,8,NULL);
    pl_shader_obj lut=NULL;
    for(unsigned axis=0;axis<2;axis++)for(unsigned on=0;on<2;on++){
        pl_shader sh=pl_shader_alloc(NULL,pl_shader_params(.gpu=gpu));assert(sh);
        struct pl_sample_filter_params params={.filter=pl_filter_lanczos,.lut=&lut,.cb1_quad_scaler=on};
        params.filter.radius=3;
        assert(pl_shader_sample_ortho2(sh,pl_sample_src(.tex=input,.rect={0,0,8,8},
            .new_w=axis?8:16,.new_h=axis?16:8,.components=4),&params));
        const struct pl_shader_res *res=pl_shader_finalize(sh);assert(res);
        bool reused=strstr(res->glsl,"bool odd = (int(gl_FragCoord.")!=NULL;
        if(reused!=on)fprintf(stderr,"quad sampler axis %u on %u: %s\n",axis,on,res->glsl);
        assert(reused==on);
        pl_shader_free(&sh);
    }
    pl_shader_obj_destroy(&lut);pl_tex_destroy(gpu,&input);
#endif
}

int main(int argc,char **argv)
{
    bool gui_only=argc>1 && !strcmp(argv[1],"gui");
    bool domain_only=argc>1 && !strcmp(argv[1],"domain");
    bool area_only=argc>1 && !strcmp(argv[1],"area");
    bool placed_only=argc>1 && !strcmp(argv[1],"placed");
    bool warm_placed=argc>1 && !strcmp(argv[1],"warmplaced");
    bool stages=argc>1 && !strcmp(argv[1],"stages");
    bool benchmark=stages || (argc>1 && !strcmp(argv[1],"bench"));
    struct reference_gpu g=reference_gpu_create();
    check_quad_sampler(g.gl->gpu);
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(g.gl->gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    if(getenv("CB1_TEST_FAST"))dvbridge_renderer_set_fast_chroma(r,true);
    /* This witness checks admission/metadata only, never executes a quad pack. */
    if(area_only)r->fragment_quad=true;
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=2;
    av_dovi_get_color(m)->source_max_pq=3079;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1463}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2851,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,.tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_identity id={1,1,1};
    pl_tex target=pl_tex_create(r->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(r->gpu,"rgba8"),.renderable=true));assert(target);
    unsigned fbo=0;pl_opengl_unwrap(r->gpu,target,NULL,NULL,&fbo);assert(fbo);
    pl_tex gui=reference_texture(r->gpu,3840,2160,NULL);
    pl_tex lut=reference_texture(r->gpu,1,1,(float[4]){.1,.1,.1,1});
    pl_tex pq=reference_texture(r->gpu,1,1,(float[4]){.2,.2,.2,1});
    struct dvbridge_native_overlay overlay={.texture=gui,.degamma=lut,.pq=pq,
        .rect={0,0,3840,2160},.input_pq=true};
    pl_tex_clear(r->gpu,gui,(float[4]){.1,.05,.025,.5});
    const size_t packed_bytes=3840u*2160u*4;
    unsigned char *control=malloc(packed_bytes),*actual=malloc(packed_bytes);assert(control && actual);
    const struct dvbridge_geometry cases[]={
        {1920,1080,0,0,3840,2160},{2560,1440,0,0,3840,2160},
        {1280,720,0,0,3840,2160},{2048,1152,0,0,3840,2160},
        {1920,800,0,280,3840,1600},{3840,2160,0,0,3840,2160}};
    for(unsigned preset=DVBRIDGE_ADAPTIVE_B_FP32;preset<=DVBRIDGE_ADAPTIVE_B_FP16;preset++)
    for(unsigned c=0;c<sizeof(cases)/sizeof(*cases);c++){
        policy.adaptive=preset;
        if(benchmark && preset!=DVBRIDGE_ADAPTIVE_B_FP16)continue;
        if(stages && c!=0 && c!=5)continue;
        if(gui_only && c!=5)continue;
        if(placed_only && c!=4)continue;
        if(warm_placed && c!=3 && c!=4)continue;
        struct dvbridge_geometry geometry=cases[c];
        size_t count=(size_t)geometry.source_width*geometry.source_height;
        float *pixels=malloc(count*4*sizeof(float));assert(pixels);
        for(size_t i=0;i<count;i++)for(unsigned j=0;j<4;j++)
            pixels[i*4+j]=j==3?1:dv_ideal_pq(60+(i%251)*(j+1)*.25);
        pl_tex input=reference_texture(r->gpu,geometry.source_width,geometry.source_height,pixels);free(pixels);
        struct pl_frame frame=reference_frame(input,geometry.source_width,geometry.source_height);
        if(c==4 && preset==DVBRIDGE_ADAPTIVE_B_FP16){
            pl_fmt fp16=pl_find_fmt(r->gpu,PL_FMT_FLOAT,4,16,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);assert(fp16);
            assert(pl_tex_recreate(r->gpu,&r->enhanced_input,pl_tex_params(.w=3840,.h=2160,
                .format=fp16,.renderable=true,.sampleable=true,.blit_dst=true)));
            pl_tex_clear(r->gpu,r->enhanced_input,(float[4]){.006,.005,.004,1});
        }
        if(benchmark){
            for(unsigned visible=0;visible<(stages?1:2);visible++)for(unsigned i=0;i<24;i++){
                struct timespec a,b,submitted,ready;glFinish();clock_gettime(CLOCK_MONOTONIC,&a);
                compute_count=0;memset(stage_ns,0,sizeof(stage_ns));stage_trace=stages;
                stage_describe=stages && i==23;
                dvbridge_renderer_set_overlay_visible(r,visible);
                assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&frame,m,bytes,
                    1,1,geometry,target,false,visible?&overlay:NULL)==DVBRIDGE_DV_PENDING);
                clock_gettime(CLOCK_MONOTONIC,&submitted);finish(r);
                clock_gettime(CLOCK_MONOTONIC,&ready);
                assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));glFinish();stage_trace=false;
                clock_gettime(CLOCK_MONOTONIC,&b);
                if(i>=8)printf("BENCH,%u,%u,%u,%u,%.6f\n",geometry.source_width,
                    geometry.source_height,visible,i-8,(b.tv_sec-a.tv_sec)*1000.+(b.tv_nsec-a.tv_nsec)/1e6);
                if(stages && i>=8){
                    printf("SERIALSTAGES,%u,%u,%u,%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n",
                        geometry.source_width,geometry.source_height,i-8,
                        stage_ns[0]/1e6,stage_ns[1]/1e6,stage_ns[2]/1e6,stage_ns[3]/1e6,
                        (submitted.tv_sec-a.tv_sec)*1000.+(submitted.tv_nsec-a.tv_nsec)/1e6,
                        (ready.tv_sec-submitted.tv_sec)*1000.+(ready.tv_nsec-submitted.tv_nsec)/1e6);
                }
                retire(r);id.picture++;
            }
            goto next_geometry;
        }
        for(unsigned flip=0;flip<2;flip++)for(unsigned gui_state=0;gui_state<6;gui_state++){
            void *expected_metadata=NULL;size_t expected_bytes=0;
            for(unsigned optimized=0;optimized<2;optimized++){
                dvbridge_renderer_set_overlay_visible(r,gui_state==3);
                enum dvbridge_dv_policy_status status=optimized?
                    dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&frame,m,bytes,
                        1,1,geometry,target,flip,gui_state==3?&overlay:NULL):
                    dvbridge_render_dv_policy_prepare(r,&policy,&id,&frame,m,bytes,1,1,geometry);
                assert(status==DVBRIDGE_DV_PENDING);
                if(domain_only){
                    assert(r->enhanced_linear && "Scaled Adaptive must not add a PQ round trip");
                    assert((preset!=DVBRIDGE_ADAPTIVE_B_FP16 ||
                        (r->enhanced_input && r->enhanced_input->params.format->component_depth[0]==16)) &&
                        "Scaled Adaptive must retain the FP16 reconstruction path");
                    assert((preset!=DVBRIDGE_ADAPTIVE_B_FP16 || r->enhanced_input->params.blit_dst) &&
                        "Adaptive storage must support clearing reused letterbox borders");
                    if(preset==DVBRIDGE_ADAPTIVE_B_FP16 && !geometry.x && !geometry.y &&
                       geometry.width==3840 && geometry.height==2160)
                        assert(r->enhanced_input->params.w==(int)geometry.source_width &&
                            r->enhanced_input->params.h==(int)geometry.source_height &&
                            "Native expansion is independent of the final packer's quad support");
                    finish(r);retire(r);goto next_geometry;
                }
                if(area_only){
                    reject_expansion(r);finish(r);
                    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
                    unsigned active[4];assert(dvbridge_active_area(out->candidate,active));
                    assert(!memcmp(active,out->value.margins,sizeof(active)) &&
                        "Native-grid rejection must retain output-raster L5 geometry");
                    retire(r);goto next_geometry;
                }
                if(optimized && !gui_state){
                    bool native=r->enhanced_input && (r->enhanced_input->params.w!=3840 ||
                        r->enhanced_input->params.h!=2160);
                    assert((native || (r->enhanced_prepack && r->enhanced_skip_aux)) &&
                        "Use native-grid expansion or fused output, not the old scaled PQ path");
                }
                if(gui_state==2)finish(r);
                if(gui_state==4)reject_expansion(r);
                if(gui_state){
                    assert(dvbridge_render_dv_policy_update_overlay(r,&overlay,true) &&
                        "A late GUI redraw must preserve the pending picture");
                    GLsync fence=r->dv.fence;
                    for(unsigned redraw=0;redraw<5;redraw++){
                        overlay.rect[1]=redraw*7;overlay.input_pq=redraw&1;
                        assert(dvbridge_render_dv_policy_update_overlay(r,redraw==2?NULL:&overlay,redraw!=2));
                        assert(r->dv.fence==fence && "GUI redraw must not resubmit video analysis");
                    }
                }
                if(gui_state==5)reject_expansion(r);
                finish(r);
                const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
                assert(out->value.identity.picture==id.picture && out->value.measured==(gui_state<4));
                if(!optimized){expected_bytes=out->bytes;expected_metadata=av_memdup(out->output_metadata,out->bytes);assert(expected_metadata);}
                else assert(out->bytes==expected_bytes && !memcmp(out->output_metadata,expected_metadata,expected_bytes));
                if(!optimized && (geometry.source_width!=3840 || geometry.source_height!=2160))
                    assert(dvbridge_render_dv_policy_rgb(r));
                assert(dvbridge_render_dv_policy_resolve(r,target,fbo,flip));
                read_carrier(fbo,optimized?actual:control);
                if(c==4 && !gui_state && !flip){
                    unsigned char *image=optimized?actual:control;
                    assert(image[0]==128 && image[1]==16 && "Placed Adaptive must clear reused borders to transport black");
                }
                retire(r);
            }
            if(memcmp(actual,control,packed_bytes)){
                size_t first=0,changed=0;while(first<packed_bytes && actual[first]==control[first])first++;
                for(size_t i=first;i<packed_bytes;i++)changed+=actual[i]!=control[i];
                fprintf(stderr,"carrier mismatch preset=%u geometry=%u flip=%u gui=%u first=%zu (%u vs %u) bytes=%zu\n",
                    preset,c,flip,gui_state,first,actual[first],control[first],changed);
                assert(!"Fusion/late overlays changed carrier bytes");
            }
            av_free(expected_metadata);id.picture++;
        }
next_geometry:
        if(c==0 && !domain_only && !area_only && r->fragment_quad && r->gpu->glsl.subgroup_size){
            assert(quad_scaler_calls && "Full 1080p Adaptive transport must select exact tap reuse");
        }
        fprintf(stderr,"PASS geometry %ux%u placement %u,%u %ux%u\n",geometry.source_width,
            geometry.source_height,geometry.x,geometry.y,geometry.width,geometry.height);
        pl_tex_destroy(r->gpu,&input);
    }
    free(control);free(actual);pl_tex_destroy(r->gpu,&gui);pl_tex_destroy(r->gpu,&lut);
    pl_tex_destroy(r->gpu,&pq);pl_tex_destroy(r->gpu,&target);av_free(m);
    dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
    reference_gpu_destroy(&g);
    puts("PASS scaled Adaptive: exact carrier/metadata and pending/ready GUI updates");
}
