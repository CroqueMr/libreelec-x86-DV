/* SPDX-License-Identifier: GPL-3.0-only */
#include "reference_test.h"
static bool reject_statistics;
static unsigned render_errors;
static void enhanced_log(void *priv,enum pl_log_level level,const char *message)
{
    reference_log(priv,level,message);
    if(level<=PL_LOG_ERR)render_errors++;
}
static bool withhold_fetch;
static bool ai_test_has_ext(pl_opengl gl,const char *name)
{return !(withhold_fetch && !strcmp(name,"GL_EXT_shader_framebuffer_fetch_non_coherent")) && pl_opengl_has_ext(gl,name);}
static GLuint rejected_texture;
static bool rejected_deleted;
static void ai_test_delete(GLsizei n,const GLuint *textures)
{
    for(GLsizei i=0;i<n;i++)if(rejected_texture && textures[i]==rejected_texture)rejected_deleted=true;
    glDeleteTextures(n,textures);
}
static pl_tex ai_test_wrap(pl_gpu gpu,const struct pl_opengl_wrap_params *params)
{
    if(reject_statistics && (params->iformat==GL_R32F || params->iformat==GL_RGBA16UI)){rejected_texture=params->texture;return NULL;}
    return pl_opengl_wrap(gpu,params);
}
#define pl_opengl_wrap ai_test_wrap
#define glDeleteTextures ai_test_delete
#define pl_opengl_has_ext ai_test_has_ext
#include "dvbridge_render.c"
#undef pl_opengl_wrap
#undef glDeleteTextures
#undef pl_opengl_has_ext
#include <time.h>

static enum dvbridge_dv_policy_status finish(struct dvbridge_renderer *r)
{
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status s=dvbridge_render_dv_policy_poll(r);
        if(s!=DVBRIDGE_DV_PENDING && s!=DVBRIDGE_DV_BUSY)return s;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"GPU completion timeout");return DVBRIDGE_DV_FAILED;
}
static void retire(struct dvbridge_renderer *r)
{dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);}

static uint64_t now_ns(void)
{struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
/* Half-float auxiliary PQ may truncate by less than two 12-bit codes.
 * The directly packed movie and measured metadata do not use this cache. */
static double auxiliary_codes(const struct dvbridge_renderer *r)
{return r->ai_enhanced_fused && r->ai_enhanced_prepack?2:1;}

static void live(pl_gpu gpu,struct dvbridge_renderer *r,const char *bundle)
{
    struct pl_frame source={.num_planes=2,.crop={0,0,3840,2160},
        .repr={.sys=PL_COLOR_SYSTEM_BT_2020_NC,.levels=PL_COLOR_LEVELS_LIMITED,
            .bits={.sample_depth=16,.color_depth=10,.bit_shift=6}},
        .color={.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,.hdr={.max_luma=1000}}};
    for(unsigned p=0;p<2;p++){
        unsigned w=p?1920:3840,h=p?1080:2160,c=p?2:1;
        uint16_t *data=malloc(w*h*c*sizeof(*data));assert(data);
        for(unsigned i=0;i<w*h*c;i++)data[i]=(p?512:700)<<6;
        source.planes[p]=(struct pl_plane){.components=c,.component_mapping={p,p+1},
            .texture=pl_tex_create(gpu,pl_tex_params(.w=w,.h=h,.initial_data=data,.sampleable=true,
                .format=pl_find_fmt(gpu,PL_FMT_UNORM,c,16,16,PL_FMT_CAP_SAMPLEABLE)))};
        free(data);assert(source.planes[p].texture);
    }
    struct cb1_hdr10_ai *ai=NULL;assert(cb1_hdr10_ai_create(gpu,bundle,&ai)==CB1_AI_READY);
    cb1_hdr10_ai_reset(ai,9,7);uint64_t start=now_ns();
    for(unsigned i=0;i<29;i++){
        struct cb1_ai_identity id={9,i+1,7};
        enum cb1_ai_status status=cb1_hdr10_ai_submit(ai,&source,id,i*.04);
        for(unsigned k=0;status==CB1_AI_PENDING && k<10000;k++){
            nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
            status=cb1_hdr10_ai_submit(ai,NULL,id,i*.04);
        }
        assert(status==CB1_AI_READY);
    }
    assert(cb1_hdr10_ai_advance(ai,1.16)==CB1_AI_READY);
    struct cb1_ai_result predictions[4];
    for(unsigned i=0;i<4;i++)assert(cb1_hdr10_ai_poll(ai,(struct cb1_ai_identity){9,i+1,7},&predictions[i])==CB1_AI_READY);
    pl_gpu_finish(gpu);uint64_t analysis=now_ns()-start;
    struct cb1_hdr10_ai_metrics metrics;cb1_hdr10_ai_metrics(ai,&metrics);
    struct dvbridge_policy policy={.revision=7,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    const struct dvbridge_geometry geometry={3840,2160,0,0,3840,2160};
    for(unsigned preset=1;preset<2;preset++){
        uint64_t total=0;
        for(unsigned i=0;i<4;i++){
            uint64_t begin=now_ns();
            assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&predictions[i],&source,&geometry));
            assert(finish(r)==DVBRIDGE_DV_READY);
            const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
            assert(out->value.identity.picture==i+1 && out->value.measured);
            assert(!av_dovi_find_level(out->output_metadata,3));pl_gpu_finish(gpu);
            uint64_t elapsed=now_ns()-begin;if(i)total+=elapsed;
            retire(r);
        }
        printf("LIVE preset=%u source=3840x2160-P010 frames=29 analysis_wall_ms=%.3f render_ready_mean_ms=%.3f inferences=%llu readback_bytes=%llu gpu_submissions=%llu inference_ms=%.3f\n",
            preset,analysis/1e6,total/3e6,(unsigned long long)metrics.inferences,
            (unsigned long long)metrics.readback_bytes,(unsigned long long)metrics.gpu_submissions,metrics.inference_ns/1e6);
    }
    cb1_hdr10_ai_destroy(&ai);for(unsigned p=0;p<2;p++)pl_tex_destroy(gpu,&source.planes[p].texture);
}

int main(int argc,char **argv)
{
    withhold_fetch=getenv("CB1_TEST_NO_FETCH")!=NULL;
    struct reference_gpu gpu=reference_gpu_create();
    pl_log_update(gpu.log,pl_log_params(.log_cb=enhanced_log,.log_level=PL_LOG_ERR));
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu.gl->gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    GLint fragment_images;glGetIntegerv(GL_MAX_FRAGMENT_IMAGE_UNIFORMS,&fragment_images);
    const bool can_direct=r->fragment_quad && fragment_images>=3;
    if(argc==2 && !strcmp(argv[1],"--metadata-shape")){
        for(unsigned count=0;count<=5;count++){
            uint32_t words[640]={0};
            struct active_mask mask={.packets=words,.count=count};
            pl_shader sh=pl_shader_alloc(NULL,pl_shader_params(.gpu=gpu.gl->gpu));
            assert(pl_shader_custom(sh,&(struct pl_custom_shader){.input=PL_SHADER_SIG_NONE,
                .output=PL_SHADER_SIG_COLOR,.body="color=vec4(0.0);"}));
            assert(!pack_active_area(&mask,&(struct pl_hook_params){.sh=sh,.stage=PL_HOOK_OUTPUT}).failed);
            const struct pl_shader_res *result=pl_shader_finalize(sh);assert(result);
            bool found=false;
            for(int i=0;i<result->num_variables;i++){
                const struct pl_var *v=&result->variables[i].var;
                if(v->type==PL_VAR_UINT && v->dim_v==4){
                    assert(v->dim_a==(count?count*32:32));found=true;
                }
            }
            assert(found);pl_shader_free(&sh);
        }
        dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
        reference_gpu_destroy(&gpu);puts("PASS metadata array shape for empty and five-packet transport");return 0;
    }
    if(argc==2){
        live(gpu.gl->gpu,r,argv[1]);dvbridge_renderer_destroy(r);
        assert(dvbridge_retirement_owner_destroy(&owner));reference_gpu_destroy(&gpu);return 0;
    }
    float pixel[32];for(unsigned i=0;i<32;i++)pixel[i]=i%4==3?1:dv_ideal_pq(500);
    pl_tex tex=reference_texture(gpu.gl->gpu,4,2,pixel);
    struct pl_frame source=reference_frame(tex,4,2);source.repr=pl_color_repr_rgb;
    source.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,
        .transfer=PL_COLOR_TRC_PQ,.hdr={.max_luma=1000}};
    struct dvbridge_geometry geometry={4,2,0,120,3840,1920};
    struct cb1_ai_result prediction={.id={3,4,7},.pts=0,
        .raw={.l1_min=0,.l1_max=3080,.l1_avg=1463,.l3_min=2048,.l3_max=2048,.l3_avg=2048}};
    struct dvbridge_policy policy={.revision=7,.mode=DVBRIDGE_MODE_ENHANCED_DV,
        .tv={2300,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_BT2020}};
    float native[4];
    for(unsigned preset=1;preset<2;preset++){
        assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
        assert(finish(r)==DVBRIDGE_DV_READY);
        assert(!render_errors && "Letterboxed Enhanced must not issue invalid texture operations");
        printf("Enhanced statistics: %s; prepack=%d\n",
            r->ai_enhanced_stats?r->ai_enhanced_stats->params.format->name:"none",r->ai_enhanced_prepack);
        const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
        assert(out->value.pixel_algorithm && !strcmp(out->value.pixel_algorithm,CB1_DVE_ALGORITHM));
        assert(out->value.measured && out->value.sample_count==4u*2u);
        assert(out->value.output_generation==DVBRIDGE_RECONSTRUCTED_ENHANCED);
        assert(out->value.source_reference_nits==1000 && out->value.nominal_max_nits==2300);
        assert(!av_dovi_find_level(out->output_metadata,2) && !av_dovi_find_level(out->output_metadata,3));
        assert(!out->value.guidance_family && !out->value.fel_reconstructed);
        struct cb1_dv_enhanced_source guidance={.master=1000,.l1_present=true,.analysis={0,3080,1463}};
        struct cb1_dv_enhanced_plan plan;assert(cb1_dv_enhanced_build_ai(&plan,&guidance,&policy)==CB1_DVE_READY);
        double want[3];assert(cb1_dv_enhanced_pixel(&plan,(double[3]){500,500,500},want));
        float sample[4];reference_read(gpu.gl->gpu,dvbridge_render_dv_policy_rgb(r),1200,900,1,1,sample);
        for(unsigned c=0;c<3;c++)assert(fabs(sample[c]-dv_ideal_pq(want[c]))*4095<=auxiliary_codes(r));
        /* On capable GPUs, conversion publishes expanded pixels without a
         * second full-image expansion dispatch. Reduction only measures them. */
        GLint fragment_images;glGetIntegerv(GL_MAX_FRAGMENT_IMAGE_UNIFORMS,&fragment_images);
        if(r->ai_enhanced_prepack)assert(r->dv.prepacked);
        if(r->ai_enhanced_fused){
            pl_tex_clear(gpu.gl->gpu,r->enhanced_rgb,(float[4]){0,0,0,1});
            assert(ai_render_pixels(r,&source,geometry,NULL,false,NULL));
            reference_read(gpu.gl->gpu,r->enhanced_rgb,1200,900,1,1,sample);
            for(unsigned c=0;c<3;c++)assert(fabs(sample[c]-dv_ideal_pq(want[c]))*4095<=auxiliary_codes(r));
            assert(sample[3]==1);
        }
        reference_read(gpu.gl->gpu,dvbridge_render_dv_policy_rgb(r),1000,10,1,1,sample);
        for(unsigned c=0;c<3;c++)assert(sample[c]==0);
        retire(r);
    }
    /* Direct transport agrees with the retained intermediate route, including
     * a late overlay and both scanout orientations. */
    pl_tex direct_target=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(gpu.gl->gpu,"rgba8"),.renderable=true));assert(direct_target);
    unsigned direct_fbo;pl_opengl_unwrap(gpu.gl->gpu,direct_target,NULL,NULL,&direct_fbo);
    size_t packed_bytes=(size_t)3840*2160*4;
    unsigned char *control_bytes=malloc(packed_bytes),*direct_bytes=malloc(packed_bytes);assert(control_bytes && direct_bytes);
    pl_tex overlay_planes[3];
    overlay_planes[0]=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(gpu.gl->gpu,"rgba16f"),.renderable=true,.sampleable=true));assert(overlay_planes[0]);
    pl_tex_clear(gpu.gl->gpu,overlay_planes[0],(float[4]){.1,.1,.1,.5});
    for(unsigned i=1;i<3;i++)overlay_planes[i]=reference_texture(gpu.gl->gpu,1,1,(float[4]){.1,.1,.1,.5});
    struct dvbridge_native_overlay late={.texture=overlay_planes[0],.degamma=overlay_planes[1],.pq=overlay_planes[2],
        .rect={0,0,100,100},.input_pq=true};
    for(unsigned i=0;i<32;i++)pixel[i]=i%4==3?1:dv_ideal_pq(100+(i*103)%750);
    pl_tex_destroy(gpu.gl->gpu,&tex);tex=reference_texture(gpu.gl->gpu,4,2,pixel);
    source.planes[0].texture=tex;
    pl_tex full_source=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(gpu.gl->gpu,"rgba32f"),.sampleable=true,.renderable=true));assert(full_source);
    pl_tex_clear(gpu.gl->gpu,full_source,(float[4]){pixel[0],pixel[1],pixel[2],1});
    for(unsigned preset=0;can_direct && preset<2;preset++)for(unsigned flip=0;flip<2;flip++)for(unsigned gui=0;gui<3;gui++){
        source.planes[0].texture=preset?full_source:tex;
        source.crop=preset?(pl_rect2df){0,0,3840,2160}:(pl_rect2df){0,0,4,2};
        geometry=preset?(struct dvbridge_geometry){3840,2160,0,0,3840,2160}:
            (struct dvbridge_geometry){4,2,0,120,3840,1920};
        dvbridge_renderer_set_overlay_visible(r,gui==2);
        assert(render_hdr10_ai(r,&policy,&prediction,&source,&geometry,NULL,false,gui==2?&late:NULL));
        assert(finish(r)==DVBRIDGE_DV_READY);
        if(gui==1)assert(dvbridge_render_dv_policy_update_overlay(r,&late,true));
        assert(dvbridge_render_dv_policy_resolve(r,direct_target,direct_fbo,flip));
        glBindFramebuffer(GL_FRAMEBUFFER,direct_fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,control_bytes);
        glBindFramebuffer(GL_FRAMEBUFFER,0);assert(glGetError()==GL_NO_ERROR);retire(r);
        dvbridge_renderer_set_overlay_visible(r,gui==2);
        assert(dvbridge_render_hdr10_ai_packed_overlay(r,&policy,&prediction,&source,&geometry,direct_target,direct_fbo,flip,gui==2?&late:NULL));
        assert(finish(r)==DVBRIDGE_DV_READY);
        if(gui==1){
            if(r->dv.ai_direct_lean){
                assert(!dvbridge_render_dv_policy_update_overlay(r,&late,true));
                retire(r);
                assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
                assert(finish(r)==DVBRIDGE_DV_READY);
            }
            assert(dvbridge_render_dv_policy_update_overlay(r,&late,true));
        }
        assert(dvbridge_render_dv_policy_resolve(r,direct_target,direct_fbo,flip));
        glBindFramebuffer(GL_FRAMEBUFFER,direct_fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,direct_bytes);
        glBindFramebuffer(GL_FRAMEBUFFER,0);assert(glGetError()==GL_NO_ERROR);
        if(memcmp(control_bytes,direct_bytes,packed_bytes)){
            size_t first=0;while(first<packed_bytes && control_bytes[first]==direct_bytes[first])first++;
            fprintf(stderr,"direct mismatch preset=%u flip=%u gui=%u offset=%zu values=%u/%u\n",preset,flip,gui,first,control_bytes[first],direct_bytes[first]);
            abort();
        }
        retire(r);
    }
    pl_tex_destroy(gpu.gl->gpu,&full_source);source.planes[0].texture=tex;
    source.crop=(pl_rect2df){0,0,4,2};geometry=(struct dvbridge_geometry){4,2,0,120,3840,1920};
    for(unsigned i=0;i<3;i++)pl_tex_destroy(gpu.gl->gpu,&overlay_planes[i]);
    free(control_bytes);free(direct_bytes);pl_tex_destroy(gpu.gl->gpu,&direct_target);
    for(unsigned i=0;i<32;i++)pixel[i]=i%4==3?1:dv_ideal_pq(500);
    pl_tex_destroy(gpu.gl->gpu,&tex);tex=reference_texture(gpu.gl->gpu,4,2,pixel);
    source.planes[0].texture=tex;
    /* Full-resolution margins remain valid for a half-resolution record grid. */
    const struct dvbridge_geometry centered={4,2,960,601,1920,960};
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&centered));
    assert(finish(r)==DVBRIDGE_DV_READY);
    assert(dvbridge_render_dv_policy_output(r)->value.sample_count==4u*2u);
    retire(r);
    /* Identity retains original AI L1/L3 and ungraded pixels. */
    policy.tv.peak_nits=600;
    direct_target=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(gpu.gl->gpu,"rgba8"),.renderable=true));assert(direct_target);
    pl_opengl_unwrap(gpu.gl->gpu,direct_target,NULL,NULL,&direct_fbo);
    if(can_direct){
        assert(dvbridge_render_hdr10_ai_packed_overlay(r,&policy,&prediction,&source,&geometry,direct_target,direct_fbo,false,NULL));
        assert(finish(r)==DVBRIDGE_DV_READY);
        assert(dvbridge_render_dv_policy_output(r)->value.expansion_reason==CB1_DVE_NO_HEADROOM);
        assert(dvbridge_render_dv_policy_resolve(r,direct_target,direct_fbo,false));retire(r);
    }else assert(!dvbridge_render_hdr10_ai_packed_overlay(r,&policy,&prediction,&source,&geometry,direct_target,direct_fbo,false,NULL));
    pl_tex_destroy(gpu.gl->gpu,&direct_target);
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    assert(finish(r)==DVBRIDGE_DV_READY);
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.expansion_reason==CB1_DVE_NO_HEADROOM && !out->value.measured);
    assert(av_dovi_find_level(out->output_metadata,3));
    reference_read(gpu.gl->gpu,dvbridge_render_dv_policy_rgb(r),1200,900,1,1,native);
    assert(fabs(native[0]-pixel[0])<2e-6);retire(r);
    source.color.hdr.max_luma=0;policy.tv.peak_nits=2300;
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.source_reference_nits==0 && out->value.source_pq[1]==4095);
    assert(out->value.expansion_reason==CB1_DVE_NO_HEADROOM);retire(r);
    source.color.hdr.max_luma=1000;prediction.raw.l3_max=2080;
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    assert(r->dv.enhanced_plan.analysis[1]==3144); /* +32 normalized PQ rounds to +64 codes. */
    assert(finish(r)==DVBRIDGE_DV_READY);retire(r);prediction.raw.l3_max=2048;
    /* Whole-image source guard retains the original AI pair, without DV reshaping. */
    for(unsigned i=0;i<32;i++)pixel[i]=i%4==3?1:dv_ideal_pq(1200);
    pl_tex_destroy(gpu.gl->gpu,&tex);tex=reference_texture(gpu.gl->gpu,4,2,pixel);
    source.planes[0].texture=tex;
    prediction.id.picture++;
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.expansion_reason==CB1_DVE_SOURCE_BOUND && !out->value.measured);
    assert(av_dovi_find_level(out->output_metadata,3));
    reference_read(gpu.gl->gpu,dvbridge_render_dv_policy_rgb(r),1200,900,1,1,native);
    assert(fabs(native[0]-pixel[0])<(r->ai_enhanced_prepack?2.0/4095:2e-6));retire(r);
    direct_target=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(gpu.gl->gpu,"rgba8"),.renderable=true));assert(direct_target);
    pl_opengl_unwrap(gpu.gl->gpu,direct_target,NULL,NULL,&direct_fbo);
    control_bytes=malloc(packed_bytes);direct_bytes=malloc(packed_bytes);assert(control_bytes && direct_bytes);
    for(unsigned flip=0;can_direct && flip<2;flip++){
        assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
        assert(finish(r)==DVBRIDGE_DV_READY);
        assert(dvbridge_render_dv_policy_resolve(r,direct_target,direct_fbo,flip));
        glBindFramebuffer(GL_FRAMEBUFFER,direct_fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,control_bytes);
        glBindFramebuffer(GL_FRAMEBUFFER,0);retire(r);
        assert(dvbridge_render_hdr10_ai_packed_overlay(r,&policy,&prediction,&source,&geometry,direct_target,direct_fbo,flip,NULL));
        assert(finish(r)==DVBRIDGE_DV_READY);
        out=dvbridge_render_dv_policy_output(r);assert(out && out->value.expansion_reason==CB1_DVE_SOURCE_BOUND);
        assert(dvbridge_render_texture(r)==out->intermediate);
        assert(dvbridge_render_dv_policy_resolve(r,direct_target,direct_fbo,flip));
        glBindFramebuffer(GL_FRAMEBUFFER,direct_fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,direct_bytes);
        glBindFramebuffer(GL_FRAMEBUFFER,0);assert(glGetError()==GL_NO_ERROR);
        assert(!memcmp(control_bytes,direct_bytes,packed_bytes));retire(r);
    }
    free(control_bytes);free(direct_bytes);pl_tex_destroy(gpu.gl->gpu,&direct_target);
    /* Limited-range P010 and float PQ share the same color-domain contract. */
    uint16_t y[8],uv[4];for(unsigned i=0;i<8;i++)y[i]=512<<6;
    for(unsigned i=0;i<4;i++)uv[i]=512<<6;
    pl_fmt yf=pl_find_fmt(gpu.gl->gpu,PL_FMT_UNORM,1,16,16,PL_FMT_CAP_SAMPLEABLE);
    pl_fmt cf=pl_find_fmt(gpu.gl->gpu,PL_FMT_UNORM,2,16,16,PL_FMT_CAP_SAMPLEABLE);assert(yf && cf);
    struct pl_frame planar={.num_planes=2,.crop={0,0,4,2},.color=source.color,
        .repr={.sys=PL_COLOR_SYSTEM_BT_2020_NC,.levels=PL_COLOR_LEVELS_LIMITED,
            .bits={.sample_depth=16,.color_depth=10,.bit_shift=6}},
        .planes={{.components=1,.component_mapping={0},
            .texture=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=4,.h=2,.format=yf,.sampleable=true,.initial_data=y))},
            {.components=2,.component_mapping={1,2},
            .texture=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=2,.h=1,.format=cf,.sampleable=true,.initial_data=uv))}}};
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&planar,&geometry));
    assert(r->rgb->params.format->type==PL_FMT_FLOAT && r->rgb->params.format->texel_size==16);
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    struct cb1_dv_enhanced_source guidance={.master=1000,.l1_present=true,.analysis={0,3080,1463}};
    struct cb1_dv_enhanced_plan plan;assert(cb1_dv_enhanced_build_ai(&plan,&guidance,&policy)==CB1_DVE_READY);
    double level=(512.0-64)/876;
    double expected[3],nits=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,level);
    assert(cb1_dv_enhanced_pixel(&plan,(double[3]){nits,nits,nits},expected));
    reference_read(gpu.gl->gpu,dvbridge_render_dv_policy_rgb(r),1200,900,1,1,native);
    for(unsigned c=0;c<3;c++)assert(fabs(native[c]-dv_ideal_pq(expected[c]))*4095<=auxiliary_codes(r));
    retire(r);
    planar.color.hdr.max_luma=50;
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&planar,&geometry));
    assert(finish(r)==DVBRIDGE_DV_READY);out=dvbridge_render_dv_policy_output(r);assert(out);
    assert(out->value.expansion_reason==CB1_DVE_SOURCE_BOUND && out->value.nominal_max_nits==50);
    pl_tex original=dvbridge_render_dv_policy_rgb(r);
    unsigned original_name=pl_opengl_unwrap(gpu.gl->gpu,original,NULL,NULL,NULL);
    float gui[4]={.1f,.1f,.1f,1};pl_tex gui_tex=reference_texture(gpu.gl->gpu,1,1,gui);
    struct dvbridge_native_overlay overlay={.texture=gui_tex,.degamma=gui_tex,.pq=gui_tex,
        .rect={0,0,3840,2160},.input_pq=true};
    assert(dvbridge_render_dv_policy_update_overlay(r,&overlay,true));
    pl_tex target=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=3840,.h=2160,
        .format=pl_find_named_fmt(gpu.gl->gpu,"rgba8"),.renderable=true));assert(target);
    unsigned fbo;pl_opengl_unwrap(gpu.gl->gpu,target,NULL,NULL,&fbo);
    r->fragment_quad=false;
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    assert(out->intermediate==original &&
        original==(r->ai_enhanced_fused && r->ai_enhanced_prepack?r->ai_enhanced_native:r->rgb));
    assert(pl_opengl_unwrap(gpu.gl->gpu,original,NULL,NULL,NULL)==original_name);
    reference_read(gpu.gl->gpu,original,1200,900,1,1,native);
    assert(fabs(native[0]-level)*4095<=1);
    retire(r);
    /* Only actual presentation advances the shared temporal plan. */
    for(unsigned i=0;i<32;i++)pixel[i]=i%4==3?1:dv_ideal_pq(500);
    pl_tex_destroy(gpu.gl->gpu,&tex);tex=reference_texture(gpu.gl->gpu,4,2,pixel);
    source.planes[0].texture=tex;prediction.id.picture++;prediction.pts=0;
    dvbridge_renderer_set_overlay_visible(r,false);
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    GLsync pending=r->dv.fence;
    assert(dvbridge_render_dv_policy_update_overlay(r,&overlay,true));
    assert(dvbridge_render_dv_policy_update_overlay(r,NULL,false));
    assert(r->dv.fence==pending && !r->dv.ready);
    assert(finish(r)==DVBRIDGE_DV_READY);
    struct cb1_dv_enhanced_plan first=r->dv.enhanced_plan;
    out=dvbridge_render_dv_policy_output(r);assert(out);
    uint32_t bad[12];memcpy(bad,r->dv.mapped,sizeof(bad));bad[6]++;
    assert(!dve_derive(r,bad));
    assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
    struct dvbridge_identity id={prediction.id.stream,prediction.id.picture,prediction.id.revision};
    assert(dvbridge_render_dv_policy_commit(r,&id,target,out->resolve_serial));
    assert(finish(r)==DVBRIDGE_DV_IDLE && r->enhanced_has_committed);
    struct dvbridge_dv_policy_snapshot committed;assert(dvbridge_render_dv_policy_committed(r,&committed));
    prediction.id.picture++;prediction.pts=.04;prediction.raw.l1_max=2000;prediction.raw.l1_avg=1000;
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    retire(r);assert(!memcmp(&r->enhanced_committed,&first,sizeof(first)));
    struct dvbridge_dv_policy_snapshot after;assert(dvbridge_render_dv_policy_committed(r,&after));
    assert(!memcmp(&committed,&after,sizeof(after)));
    prediction.id.picture++;prediction.pts=.08;
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    guidance.analysis[1]=2000;guidance.analysis[2]=1000;
    assert(cb1_dv_enhanced_build_ai(&plan,&guidance,&policy)!=CB1_DVE_INVALID);
    cb1_dv_enhanced_transition(&plan,&first,.08,false);
    assert(!memcmp(plan.extra,r->dv.enhanced_plan.extra,sizeof(plan.extra)));
    retire(r);
    prediction.pts=0;prediction.id.picture++;
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    assert(!memcmp(r->dv.enhanced_plan.extra,first.extra,sizeof(first.extra)));
    retire(r);
    prediction.id.revision++; /* Mismatched policy cannot prepare or publish. */
    assert(!dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&source,&geometry));
    assert(!dvbridge_render_dv_policy_output(r));
    /* Saturated input uses the same native color normalization as Reference. */
    prediction.id.revision=policy.revision;prediction.id.picture++;prediction.pts=10;
    prediction.raw.l1_max=3080;prediction.raw.l1_avg=1463;planar.color.hdr.max_luma=1000;
    const uint16_t saturated[]={64<<6,512<<6,64<<6,512<<6};
    pl_tex_destroy(gpu.gl->gpu,&planar.planes[1].texture);
    planar.planes[1].texture=pl_tex_create(gpu.gl->gpu,pl_tex_params(.w=2,.h=1,.format=cf,
        .sampleable=true,.initial_data=saturated));assert(planar.planes[1].texture);
    for(unsigned i=0;i<8;i++){
        pixel[4*i]=.5114f;pixel[4*i+1]=.594f;pixel[4*i+2]=-.43f;pixel[4*i+3]=1;
    }
    pl_tex_destroy(gpu.gl->gpu,&tex);tex=reference_texture(gpu.gl->gpu,4,2,pixel);
    source.planes[0].texture=tex;
    const struct pl_frame *saturated_inputs[]={&planar,&source};
    for(unsigned i=0;i<2;i++){
        float reference[4],ingress[4];
        policy.mode=DVBRIDGE_MODE_STANDARD;
        pl_tex baseline=dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,saturated_inputs[i],&geometry);
        assert(baseline && finish(r)==DVBRIDGE_DV_READY);
        reference_read(gpu.gl->gpu,baseline,1200,900,1,1,reference);retire(r);
        policy.mode=DVBRIDGE_MODE_ENHANCED_DV;
        assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,saturated_inputs[i],&geometry));
        bool native_grid=r->native_picture && r->enhanced_rgb->params.w==geometry.source_width &&
            r->enhanced_rgb->params.h==geometry.source_height;
        reference_read(gpu.gl->gpu,native_grid?r->native_picture:
            r->ai_enhanced_fused && r->ai_enhanced_prepack?r->ai_enhanced_native:r->rgb,
            native_grid?1:1200,native_grid?1:900,1,1,ingress);
        for(unsigned c=0;c<3;c++)assert(fabs(ingress[c]-reference[c])<(r->ai_enhanced_prepack?2.0/4095:2e-6));
        assert(reference[2]==0); /* Native PQ conversion, not carrier clipping. */
        assert(finish(r)==DVBRIDGE_DV_READY);
        out=dvbridge_render_dv_policy_output(r);assert(out);
        double input[3],wanted[3];
        for(unsigned c=0;c<3;c++)input[c]=pl_hdr_rescale(PL_HDR_PQ,PL_HDR_NITS,reference[c]);
        assert(cb1_dv_enhanced_pixel(&r->dv.enhanced_plan,input,wanted));
        reference_read(gpu.gl->gpu,dvbridge_render_dv_policy_rgb(r),1200,900,1,1,native);
        for(unsigned c=0;c<3;c++)assert(fabs(native[c]-dv_ideal_pq(wanted[c]))*4095<=auxiliary_codes(r));
        memcpy(bad,r->dv.mapped,sizeof(bad));bad[10]=0;
        assert(!dve_derive(r,bad));retire(r);
    }
    /* Failure of optional statistics storage keeps the existing compute route. */
    dvbridge_renderer_destroy(r);r=dvbridge_renderer_create_with_owner(owner);assert(r);
    prediction.id.picture++;reject_statistics=true;
    assert(dvbridge_render_hdr10_ai_rgb(r,&policy,&prediction,&planar,&geometry));
    assert(finish(r)==DVBRIDGE_DV_READY);
    assert(!rejected_texture || rejected_deleted);
    out=dvbridge_render_dv_policy_output(r);assert(out && out->value.measured);
    retire(r);reject_statistics=false;
    pl_tex_destroy(gpu.gl->gpu,&target);pl_tex_destroy(gpu.gl->gpu,&gui_tex);
    for(unsigned p=0;p<2;p++)pl_tex_destroy(gpu.gl->gpu,&planar.planes[p].texture);
    pl_tex_destroy(gpu.gl->gpu,&tex);dvbridge_renderer_destroy(r);
    assert(dvbridge_retirement_owner_destroy(&owner));reference_gpu_destroy(&gpu);
    puts("PASS shared AI expansion, dense output metadata and source-specific identity");
}
