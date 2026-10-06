/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include <libplacebo/shaders/custom.h>
#include <time.h>

#if defined(CB1_DV_TEST) && defined(DVBRIDGE_DV_POLICY_API)
static enum dvbridge_dv_policy_status dv_complete(struct dvbridge_renderer *r)
{
    enum dvbridge_dv_policy_status s=DVBRIDGE_DV_PENDING;
    for(unsigned i=0;i<10000 && (s==DVBRIDGE_DV_PENDING || s==DVBRIDGE_DV_BUSY);i++) {
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
        s=dvbridge_render_dv_policy_poll(r);
    }
    return s;
}
static void packed_read(pl_gpu gpu,pl_tex tex,int y,int w,int h,unsigned char *data)
{
    GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(gpu,tex,NULL,NULL,NULL),0);
    glReadPixels(0,y,w,h,GL_RGBA,GL_UNSIGNED_BYTE,data);assert(glGetError()==GL_NO_ERROR);
    glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
}
#endif

/* Standalone pinned-library sampling control, not the engine policy hook. */
static struct pl_hook_res capture_source(void *priv,const struct pl_hook_params *p)
{
    (void)priv;
    struct pl_custom_shader shader={.input=PL_SHADER_SIG_COLOR,.output=PL_SHADER_SIG_COLOR,
        .header=p->stage==PL_HOOK_NATIVE?"vec3 cb1_source_sample;\n":NULL,
        .body=p->stage==PL_HOOK_NATIVE?"cb1_source_sample=color.rgb;\n":"color.rgb=cb1_source_sample;\n"};
    return (struct pl_hook_res){.failed=!pl_shader_custom(p->sh,&shader),.output=PL_HOOK_SIG_NONE};
}

int main(int argc,char **argv)
{
#if defined(CB1_DV_TEST) && !defined(DVBRIDGE_DV_POLICY_API)
    assert(!"Enhanced DV frame analysis and paired output entry is missing");
#endif
    bool reconstruction=argc==2 && !strcmp(argv[1],"library-reconstruction-black");
    bool native_image=argc==2 && !strcmp(argv[1],"library-reconstruction-image");
    bool sample_image=argc==2 && !strncmp(argv[1],"library-source-image",20);
    bool baseline=reconstruction || (argc==2 && !strcmp(argv[1],"library-black"));
    if(!baseline) assert(dvbridge_render_hdr10_policy_rgb && dvbridge_render_hdr10_policy_resolve);
    struct reference_gpu g=reference_gpu_create(); pl_gpu gpu=g.gl->gpu;
#if defined(CB1_DV_TEST) && defined(DVBRIDGE_DV_POLICY_API)
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(gpu);assert(owner);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
#else
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu); assert(r);
#endif
    size_t bytes; AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=2;
    av_dovi_get_ext(m,0)->level=1;
    av_dovi_get_ext(m,0)->l1.max_pq=3079; av_dovi_get_ext(m,0)->l1.avg_pq=1667;
    av_dovi_get_ext(m,1)->level=6; av_dovi_get_ext(m,1)->l6.max_luminance=1000;
    if(baseline) {
        pl_tex input=reference_texture(gpu,2,2,(float[16]){0,0,0,1,0,0,0,1,0,0,0,1,0,0,0,1});
        struct pl_frame f=reference_frame(input,2,2);
        if(reconstruction) {
            av_dovi_get_header(m)->disable_residual_flag=0;
            AVDOVIDataMapping *map=av_dovi_get_mapping(m);map->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
            for(int c=0;c<3;c++){map->nlq[c].nlq_offset=512;map->nlq[c].linear_deadzone_slope=1;}
            float neutral[16];for(int i=0;i<16;i++)neutral[i]=i%4==3?1:512.0f/1023;
            pl_tex et=reference_texture(gpu,2,2,neutral);struct pl_frame ef=reference_frame(et,2,2);f.enhancement_layer=&ef;
            assert(dvbridge_render_rgb(r,&f,m,bytes,0,0,(struct dvbridge_geometry){2,2,0,0,2,2}));
            float pixel[4];reference_read(gpu,dvbridge_render_texture(r),0,0,1,1,pixel);
            double endpoint=pow(3424.0/4096.0,2523.0/32.0);
            fprintf(stderr,"legacy reconstruction black PQ: %.17g %.17g %.17g; physical zero %.17g\n",pixel[0],pixel[1],pixel[2],endpoint);
            assert(pixel[0]<=endpoint && pixel[1]<=endpoint && pixel[2]<=endpoint);
            dvbridge_renderer_destroy(r);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&et);av_free(m);reference_gpu_destroy(&g);
            return 0;
        }
        struct dvbridge_hdr10_session session={.target={.primaries=PL_COLOR_PRIM_BT_709,
            .transfer=PL_COLOR_TRC_LINEAR,.hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1500}}};
        assert(dvbridge_render_hdr10_rgb(r,&session,&f,m,bytes,0,0,(struct dvbridge_geometry){2,2,0,0,2,2}));
        float pixel[4]; reference_read(gpu,dvbridge_render_texture(r),0,0,1,1,pixel);
        fprintf(stderr,"unprotected library black LINEAR nits/203: %.17g %.17g %.17g\n",pixel[0],pixel[1],pixel[2]);
        assert(pixel[0]==0 && pixel[1]==0 && pixel[2]==0);
        return 0;
    }
    int sw,sh,dw,dh,gamut,bits,limited,flip,fel,generation,has_l6;
    double peak,l6min,l6max;
    unsigned srcmin,srcmax,lmin,lavg,lmax,offsets[4];
    assert(scanf("%d%d%d%d%lf%d%d%d%d%d%d%d%lf%lf%u%u%u%u%u",
        &sw,&sh,&dw,&dh,&peak,&gamut,&bits,&limited,&flip,&fel,&generation,&has_l6,&l6min,&l6max,&srcmin,&srcmax,&lmin,&lavg,&lmax)==19);
    assert(sw>0 && sh>0 && sw*sh<=4096 && dw>0 && dh>0 && dw*dh<=4096);
    assert(scanf("%u%u%u%u",&offsets[0],&offsets[1],&offsets[2],&offsets[3])==4);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m); h->disable_residual_flag=!fel;
    AVDOVIColorMetadata *color=av_dovi_get_color(m); color->source_min_pq=srcmin; color->source_max_pq=srcmax;
    AVDOVIDmData *l1=av_dovi_get_ext(m,0); l1->l1.min_pq=lmin; l1->l1.avg_pq=lavg; l1->l1.max_pq=lmax;
    m->num_ext_blocks=1;
    if(has_l6) { AVDOVIDmData *l6=av_dovi_get_ext(m,m->num_ext_blocks++); l6->level=6;
        l6->l6.min_luminance=(unsigned)llround(l6min*10000); l6->l6.max_luminance=(unsigned)llround(l6max); }
    if(offsets[0]||offsets[1]||offsets[2]||offsets[3]) {
        AVDOVIDmData *l5=av_dovi_get_ext(m,m->num_ext_blocks++); l5->level=5;
        l5->l5.left_offset=offsets[0];l5->l5.right_offset=offsets[1];l5->l5.top_offset=offsets[2];l5->l5.bottom_offset=offsets[3];
    }
    if(generation==40) { AVDOVIDmData *cm=av_dovi_get_ext(m,m->num_ext_blocks++);
        *cm=(AVDOVIDmData){.level=254,.dvbridge_raw_magic=0x41424456,.dvbridge_original_length=2}; }
    AVDOVIDataMapping *map=av_dovi_get_mapping(m); map->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++) {
        unsigned o,s,t; assert(scanf("%u%u%u",&o,&s,&t)==3);
        map->nlq[c].nlq_offset=o;map->nlq[c].linear_deadzone_slope=s;map->nlq[c].linear_deadzone_threshold=t;
    }
    float *pixels=calloc(sw*sh*4,sizeof(float)),*el_pixels=calloc(sw*sh*4,sizeof(float)); assert(pixels&&el_pixels);
    for(int i=0;i<sw*sh;i++) {
        assert(scanf("%f%f%f%f%f%f",&pixels[4*i],&pixels[4*i+1],&pixels[4*i+2],&el_pixels[4*i],&el_pixels[4*i+1],&el_pixels[4*i+2])==6);
        pixels[4*i+3]=el_pixels[4*i+3]=1;
        for(int c=0;c<3;c++) el_pixels[4*i+c]/=1023;
    }
    pl_tex input=reference_texture(gpu,sw,sh,pixels),el=reference_texture(gpu,sw,sh,el_pixels);
    free(pixels);free(el_pixels);
    struct pl_frame f=reference_frame(input,sw,sh),ef=reference_frame(el,sw,sh);if(fel)f.enhancement_layer=&ef;
    struct dvbridge_policy policy=reference_policy();policy.tv.peak_nits=peak;policy.tv.gamut=gamut;
#ifdef CB1_DV_TEST
    policy.mode=DVBRIDGE_MODE_ENHANCED_DV;
    if(argc>=2 && (!strcmp(argv[1],"Natural") || !strcmp(argv[1],"Intense"))) {
        policy.enhancement=!strcmp(argv[1],"Intense") ? DVBRIDGE_ENHANCEMENT_INTENSE : DVBRIDGE_ENHANCEMENT_NATURAL;
    }
#endif
    struct dvbridge_identity id={1,7,1};struct dvbridge_geometry geometry={sw,sh,0,0,dw,dh};
    void *copy=av_memdup(m,bytes);assert(copy);
    if(sample_image) {
        struct dvbridge_color mapped;assert(dvbridge_map_color(&mapped,m,bytes,fel));
        struct pl_frame image=f;image.repr=mapped.repr;image.color=mapped.color;
        pl_tex target=reference_texture(gpu,3840,2160,NULL);
        struct pl_frame output=reference_frame(target,dw,dh);output.repr=pl_color_repr_rgb;output.color=mapped.color;
        const struct pl_hook hook={.stages=PL_HOOK_NATIVE|PL_HOOK_PRE_OUTPUT,.input=PL_HOOK_SIG_COLOR,
            .hook=capture_source,.signature=0x43423153414d504cULL};
        const struct pl_hook *hooks[]={&hook};struct pl_render_params params=pl_render_default_params;
        params.hooks=hooks;params.num_hooks=1;params.peak_detect_params=NULL;params.min_fbo_precision=32;
        if(!strcmp(argv[1],"library-source-image-nearest")) {
            params.upscaler=params.downscaler=params.plane_upscaler=params.plane_downscaler=&pl_filter_nearest;
            params.correct_subpixel_offsets=true;
        }
        if(!strcmp(argv[1],"library-source-image-no-builtins")) params.disable_builtin_scalers=true;
        if(!strcmp(argv[1],"library-source-image-policy-optin")) params.cb1_nearest_identity=true;
        pl_renderer renderer=pl_renderer_create(g.log,gpu);assert(renderer);
        assert(pl_render_image(renderer,&image,&output,&params));
        float sample[4];reference_read(gpu,target,0,0,1,1,sample);
        fprintf(stderr,"NATIVE sampled black before reshaping/EL/YCC/EOTF: %.17g %.17g %.17g\n",sample[0],sample[1],sample[2]);
        bool exact=sample[0]==0&&sample[1]==0&&sample[2]==0;
        pl_renderer_destroy(&renderer);dvbridge_renderer_destroy(r);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&el);
        pl_tex_destroy(gpu,&target);av_free(copy);av_free(m);reference_gpu_destroy(&g);
        return exact?0:1;
    }
#if defined(CB1_DV_TEST) && defined(DVBRIDGE_DV_POLICY_API)
    enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_prepare(r,&policy,&id,&f,m,bytes,0,0,geometry);
    if(argc==3 && !strcmp(argv[2],"negative-geometry")){
        assert(status==DVBRIDGE_DV_FAILED && !dvbridge_render_dv_policy_output(r) && !dvbridge_render_candidate(r));
        assert(!memcmp(copy,m,bytes) && dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
        struct dvbridge_dv_policy_snapshot previous;assert(!dvbridge_render_dv_policy_committed(r,&previous));
        dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
        pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&el);av_free(copy);av_free(m);reference_gpu_destroy(&g);
        puts("{\"negative_geometry\":true}");return 0;
    }
    if(status==DVBRIDGE_DV_UNSUPPORTED) {
        dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
        pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&el);av_free(copy);av_free(m);reference_gpu_destroy(&g);
        fprintf(stderr,"UNSUPPORTED required real GPU DV capability; paired image/packet not executed\n");return 77;
    }
    assert(status==DVBRIDGE_DV_READY);
    struct dvbridge_renderer *native=dvbridge_renderer_create(gpu);assert(native);
    assert(dvbridge_render_rgb(native,&f,m,bytes,0,0,geometry));
    float *native_rgb=calloc(dw*dh*4,sizeof(float));assert(native_rgb);
    reference_read(gpu,dvbridge_render_texture(native),0,0,dw,dh,native_rgb);
    /* Caller metadata storage may go away after prepare; imports have a
     * separate GPU last-use lifetime. Poll must use the engine-owned copy. */
    assert(r->dv.output_metadata!=m && !memcmp(r->dv.output_metadata,copy,bytes));
    av_free(m);m=av_memdup(copy,bytes);assert(m);
    assert(dv_complete(r)==DVBRIDGE_DV_READY);
    const struct dvbridge_dv_policy_output *dv=dvbridge_render_dv_policy_output(r);assert(dv);
    struct dvbridge_dv_policy_snapshot value=dv->value;
    unsigned packet_count;const uint32_t *packet=dvbridge_packets(dv->candidate,&packet_count);
    uint32_t packet_copy[128];assert(packet_count==1);memcpy(packet_copy,packet,sizeof(packet_copy));
    assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_READY);
    assert(dvbridge_render_dv_policy_output(r)->candidate==dv->candidate);
    assert(!memcmp(r->dv.output_metadata,copy,bytes));
    assert(!value.measured && !value.sample_count);
#else
    assert(native_image ? dvbridge_render_rgb(r,&f,m,bytes,0,0,geometry) :
        dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&f,m,bytes,0,0,geometry));
#endif
    assert(!memcmp(copy,m,bytes));av_free(copy);
    pl_tex intermediate=dvbridge_render_texture(r);assert(intermediate);
    unsigned overlays;assert(scanf("%u",&overlays)==1);
    for(unsigned i=0;i<overlays;i++) {
        unsigned index;float alpha,pixel[4],osd[3];assert(scanf("%u%f%f%f%f",&index,&alpha,&osd[0],&osd[1],&osd[2])==5);
        assert(index<(unsigned)(dw*dh));reference_read(gpu,intermediate,index%dw,index/dw,1,1,pixel);
        for(int c=0;c<3;c++)pixel[c]=(1-alpha)*pixel[c]+alpha*osd[c];pixel[3]=1;
        glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(gpu,intermediate,NULL,NULL,NULL));
        glTexSubImage2D(GL_TEXTURE_2D,0,index%dw,index/dw,1,1,GL_RGBA,GL_FLOAT,pixel);assert(glGetError()==GL_NO_ERROR);glBindTexture(GL_TEXTURE_2D,0);
    }
    float *rgb=calloc(dw*dh*4,sizeof(float)),*encoded=calloc(dw*dh*4,sizeof(float));assert(rgb&&encoded);
    reference_read(gpu,intermediate,0,0,dw,dh,rgb);
#if defined(CB1_DV_TEST) && defined(DVBRIDGE_DV_POLICY_API)
    assert(!memcmp(rgb,native_rgb,dw*dh*4*sizeof(float)));free(native_rgb);
    dvbridge_renderer_destroy(native);
#endif
    /* Every pixel outside the synthetic complete image must be exact signal black. */
    float *raster=malloc(3840*2160*4*sizeof(float));assert(raster);
    reference_read(gpu,intermediate,0,0,3840,2160,raster);
    for(int y=0;y<2160;y++)for(int x=0;x<3840;x++)if(
#if defined(CB1_DV_TEST) && defined(DVBRIDGE_DV_POLICY_API)
        x<(int)value.margins[0] || x>=3840-(int)value.margins[1] ||
        y<(int)value.margins[2] || y>=2160-(int)value.margins[3]
#else
        x>=dw||y>=dh
#endif
    )
        for(int c=0;c<3;c++)assert(raster[4*(y*3840+x)+c]==0);
    free(raster);
#if defined(CB1_DV_TEST) && defined(DVBRIDGE_DV_POLICY_API)
    pl_fmt packed_fmt=pl_find_fmt(gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE);
    assert(packed_fmt);pl_tex target=pl_tex_create(gpu,pl_tex_params(.w=3840,.h=2160,.format=packed_fmt,.renderable=true));assert(target);
    unsigned target_framebuffer;assert(pl_opengl_unwrap(gpu,target,NULL,NULL,&target_framebuffer));
    assert(dvbridge_render_dv_policy_resolve(r,target,target_framebuffer,flip));
    uint64_t old_serial=dvbridge_render_dv_policy_output(r)->resolve_serial;
    assert(dvbridge_render_dv_policy_resolve(r,target,target_framebuffer,flip));
    uint64_t latest_serial=dvbridge_render_dv_policy_output(r)->resolve_serial;assert(latest_serial>old_serial);
    assert(!dvbridge_render_dv_policy_commit(r,&id,target,old_serial));
    unsigned char *packed=calloc(dw*dh,4);assert(packed);packed_read(gpu,target,flip?2160-dh:0,dw,dh,packed);
#else
    pl_tex target=reference_texture(gpu,3840,2160,NULL);
    assert(native_image ? dvbridge_render_hdr10(r,target,flip,limited,bits) :
        dvbridge_render_hdr10_policy_resolve(r,target,flip,limited,bits));
    reference_read(gpu,target,0,flip?2160-dh:0,dw,dh,encoded);
#endif
    printf("{\"rgb\":[");
    for(int y=0;y<dh;y++)for(int x=0;x<dw;x++) {
        int j=y*dw+x,k=((flip?dh-1-y:y)*dw+x)*4;
        printf("%s[%.17g,%.17g,%.17g]",j?",":"",rgb[k],rgb[k+1],rgb[k+2]);
    }
#if defined(CB1_DV_TEST) && defined(DVBRIDGE_DV_POLICY_API)
    printf("],\"packed\":[");
    for(int i=0;i<dw*dh;i++)printf("%s[%u,%u,%u,%u]",i?",":"",packed[4*i],packed[4*i+1],packed[4*i+2],packed[4*i+3]);
    printf("],\"raw_record\":[");for(unsigned i=0;i<12;i++)printf("%s%u",i?",":"",0u);
    printf("],\"statistics\":[%.17g,%.17g,%.17g],\"l1\":[%u,%u,%u],\"margins\":[%u,%u,%u,%u],\"source_pq\":[%u,%u],\"source_cm_version\":%u,\"packet_hex\":\"",
        value.statistics[0],value.statistics[1],value.statistics[2],value.l1[0],value.l1[1],value.l1[2],
        value.margins[0],value.margins[1],value.margins[2],value.margins[3],value.source_pq[0],value.source_pq[1],value.source_cm_version);
    for(int i=0;i<128;i++)printf("%02x",packet_copy[i]);printf("\"}\n");free(packed);
    assert(dvbridge_render_dv_policy_commit(r,&id,target,latest_serial));
    assert(!dvbridge_render_dv_policy_commit(r,&id,target,latest_serial));
    struct dvbridge_dv_policy_snapshot committed;assert(dvbridge_render_dv_policy_committed(r,&committed));
    assert(committed.final_target==target && dv_complete(r)==DVBRIDGE_DV_IDLE);
#else
    printf("],\"codes\":[");
    for(int i=0;i<dw*dh;i++)printf("%s[%u,%u,%u]",i?",":"",
        (unsigned)floor(encoded[4*i]*((1u<<bits)-1)+.5),(unsigned)floor(encoded[4*i+1]*((1u<<bits)-1)+.5),(unsigned)floor(encoded[4*i+2]*((1u<<bits)-1)+.5));
    puts("]}");
#endif
    free(rgb);free(encoded);
    dvbridge_renderer_destroy(r);
#if defined(CB1_DV_TEST) && defined(DVBRIDGE_DV_POLICY_API)
    assert(dvbridge_retirement_owner_destroy(&owner));
#endif
    pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&el);pl_tex_destroy(gpu,&target);av_free(m);reference_gpu_destroy(&g);
}
