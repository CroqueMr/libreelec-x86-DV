/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "reference_test.h"
#include "cb1_master_reference.h"
#include "cb1_hdr10_ai.h"

static const char *mode="master";
static bool crop_half;

static void render_target(struct reference_gpu *g,struct dvbridge_renderer *r,
    const struct pl_frame *source,AVDOVIMetadata *metadata,size_t bytes,
    int width,int height,bool inset,unsigned char sample[4])
{
    bool hdr10=!strncmp(mode,"basic",5) || !strncmp(mode,"expert",6);
    bool rgb=strstr(mode,"_rgb")!=NULL;
    bool ai=!strcmp(mode,"ai") || !strcmp(mode,"ai_adaptive");
    bool adaptive=!strcmp(mode,"adaptive") || !strcmp(mode,"ai_adaptive");
    pl_fmt format=hdr10?pl_find_fmt(g->gl->gpu,PL_FMT_FLOAT,4,32,32,
        PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE):pl_find_named_fmt(g->gl->gpu,"rgba8");
    pl_tex target=pl_tex_create(g->gl->gpu,pl_tex_params(.w=width,.h=height,
        .format=format,.renderable=true,.sampleable=hdr10));
    assert(target);
    int sw=source->crop.x1,sh=source->crop.y1;
    struct dvbridge_geometry geometry={sw,sh,0,0,width,height,width,height};
    if(crop_half){
        geometry.width=sw;geometry.height=sh;
        memcpy(geometry.crop,(float[4]){0,0,sw/2,sh},sizeof(geometry.crop));
    }
    if(inset){
        geometry.x=1;geometry.width=width-2;
        memcpy(geometry.crop,(float[4]){0,0,sw,sh},sizeof(geometry.crop));
    }
    /* Native Kodi supplies an explicit destination, even when it fills the screen. */
    memcpy(geometry.placement,(float[4]){geometry.x,geometry.y,
        geometry.x+geometry.width,geometry.y+geometry.height},sizeof(geometry.placement));
    unsigned fbo;
    assert(pl_opengl_unwrap(g->gl->gpu,target,NULL,NULL,&fbo));
    struct dvbridge_policy policy=reference_policy();
    policy.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    struct dvbridge_identity id={1,1,1};
    bool rendered=false;
    if(hdr10){
        if(!strncmp(mode,"expert",6))
            rendered=rgb?
                dvbridge_render_hdr10_policy_rgb(r,&policy,&id,source,metadata,bytes,0,0,geometry) &&
                dvbridge_render_hdr10_policy_resolve(r,target,false,false,10):
                dvbridge_render_hdr10_policy_direct(r,&policy,&id,source,metadata,bytes,
                    0,0,geometry,target,false,false,10);
        else{
            struct dvbridge_hdr10_session session;
            assert(dvbridge_hdr10_session_init(&session,metadata,bytes));
            rendered=rgb?
                dvbridge_render_hdr10_rgb(r,&session,source,metadata,bytes,0,0,geometry) &&
                dvbridge_render_hdr10(r,target,false,false,10):
                dvbridge_render_hdr10_direct(r,&session,source,metadata,bytes,
                    0,0,geometry,target,false,false,10);
        }
    }else if(ai || adaptive){
        policy.mode=adaptive?DVBRIDGE_MODE_ENHANCED_DV:DVBRIDGE_MODE_STANDARD;
        policy.adaptive=adaptive?DVBRIDGE_ADAPTIVE_B_FP16:DVBRIDGE_ADAPTIVE_A;
        policy.tv.peak_nits=2300;
        if(ai){
            struct pl_frame hdr=*source;
            hdr.repr.sys=PL_COLOR_SYSTEM_BT_2020_NC;hdr.repr.levels=PL_COLOR_LEVELS_LIMITED;
            hdr.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,
                .transfer=PL_COLOR_TRC_PQ,.hdr={.min_luma=0,.max_luma=1000}};
            struct cb1_ai_result prediction={.id={1,1,1},.pts=0,
                .raw={.l1_min=0,.l1_max=3079,.l1_avg=1463,
                    .l3_min=2048,.l3_max=2048,.l3_avg=2048}};
            rendered=dvbridge_render_hdr10_ai_packed(r,&policy,&prediction,&hdr,&geometry,target,fbo,false);
        }else{
            enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_prepare_packed(r,
                &policy,&id,source,metadata,bytes,0,0,geometry,target,false,NULL);
            fprintf(stderr,"Adaptive prepare status=%u\n",status);
            rendered=status==DVBRIDGE_DV_PENDING || status==DVBRIDGE_DV_READY;
        }
        if(rendered){
            glFinish();
            assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_READY);
            assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
            const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);
            assert(out && out->value.policy.mode==policy.mode);
        }
    }else if(!strcmp(mode,"standard"))
        rendered=dvbridge_render_packed(r,source,metadata,bytes,0,NAN,geometry,target,false);
    else
        rendered=dvbridge_render_master_reference(r,source,metadata,bytes,
            0,NAN,geometry,target,false,NULL)==CB1_MASTER_READY;
    fprintf(stderr,"%s target %dx%d ready=%u\n",mode,width,height,rendered);
    assert(rendered);
    unsigned margins[4];
    if(!hdr10 && !ai && !adaptive){
        assert(dvbridge_active_area(dvbridge_render_candidate(r),margins));
        assert(margins[0]==inset && margins[1]==inset && !margins[2] && !margins[3]);
    }
    glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    if(hdr10){
        float pixel[4];glReadPixels(crop_half?sw*3/4:width/2,crop_half?sh/2:height/2,1,1,GL_RGBA,GL_FLOAT,pixel);
        for(unsigned i=0;i<4;i++){assert(isfinite(pixel[i]));sample[i]=lroundf(255*fmaxf(0,fminf(1,pixel[i])));}
    }else glReadPixels(width/2,height/2,1,1,GL_RGBA,GL_UNSIGNED_BYTE,sample);
    assert(glGetError()==GL_NO_ERROR && sample[3]==255);
    if(crop_half)assert(hdr10 && !sample[0] && !sample[1] && !sample[2] && "Source crop must precede the final fit");
    if(inset){
        unsigned char edge[8];
        glReadPixels(0,height/2,2,1,GL_RGBA,GL_UNSIGNED_BYTE,edge);
        unsigned y0=(edge[1]<<4)|(edge[2]&15),y1=(edge[5]<<4)|(edge[6]&15);
        unsigned cb=(edge[0]<<4)|(edge[2]>>4),cr=(edge[4]<<4)|(edge[6]>>4);
        fprintf(stderr,"Inset pair Y=%u,%u C=%u,%u\n",y0,y1,cb,cr);
        assert(y0==256 && y1==2048 && cb==1536 && cr==2560);
    }
    glBindFramebuffer(GL_FRAMEBUFFER,0);
    if(ai || adaptive){
        dvbridge_render_dv_policy_cancel(r);glFinish();
        assert(dvbridge_render_dv_policy_poll(r)==DVBRIDGE_DV_IDLE);
    }else if(!strncmp(mode,"expert",6))dvbridge_render_policy_cancel(r);
    else assert(dvbridge_render_commit(r));
    pl_tex_destroy(g->gl->gpu,&target);
}

int main(int argc,char **argv)
{
    bool full=argc==4 && !strcmp(argv[3],"--source4k");
    bool p5=argc==4 && !strcmp(argv[3],"--p5");
    crop_half=argc==4 && !strcmp(argv[3],"--crop");
    if((argc==3 || full || p5 || crop_half) && !strcmp(argv[1],"--case"))mode=argv[2];
    else assert(argc==1);
    struct reference_gpu g=reference_gpu_create();
    if(strcmp(mode,"master") && strncmp(mode,"basic",5) && strncmp(mode,"expert",6)){
        GLint size=0,stages=0,features=0;
        if(pl_opengl_has_ext(g.gl,"GL_KHR_shader_subgroup")){
            glGetIntegerv(0x9532,&size);glGetIntegerv(0x9533,&stages);glGetIntegerv(0x9534,&features);
        }
        if(size<4 || !(stages&GL_FRAGMENT_SHADER_BIT) || (features&0x81)!=0x81){
            fputs("SKIP packed transport needs fragment subgroup quad support\n",stderr);
            reference_gpu_destroy(&g);return 77;
        }
    }
    struct dvbridge_retirement_owner *owner=dvbridge_retirement_owner_create(g.gl->gpu);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(owner);assert(r);
    dvbridge_renderer_set_optimized_dv(r,true);
    if(strcmp(mode,"master") && strncmp(mode,"basic",5) && strncmp(mode,"expert",6) &&
       !dvbridge_renderer_supports_mode(r,DVBRIDGE_MODE_STANDARD)){
        dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
        reference_gpu_destroy(&g);return 77;
    }
    int sw=full?3840:64,sh=full?2160:36;
    struct pl_frame source={.num_planes=2,.crop={0,0,sw,sh},
        .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
    for(int p=0;p<2;p++){
        pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,p?2:1,16,16,
            PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        source.planes[p]=(struct pl_plane){.components=p?2:1,.component_mapping={p,2},
            .shift_x=p?-.5f:0,.texture=pl_tex_create(g.gl->gpu,pl_tex_params(
                .w=p?sw/2:sw,.h=p?sh/2:sh,.format=fmt,.sampleable=true,.renderable=true,.blit_dst=true,.host_writable=crop_half))};
        assert(source.planes[p].texture);
        pl_tex_clear(g.gl->gpu,source.planes[p].texture,
            p?(float[4]){16384.f/65535,49152.f/65535,0,1}:(float[4]){32768.f/65535,0,0,1});
    }
    if(crop_half){
        uint16_t *luma=malloc((size_t)sw*sh*sizeof(*luma));assert(luma);
        for(int y=0;y<sh;y++)for(int x=0;x<sw;x++)luma[y*sw+x]=x<sw/2?4096:32768;
        assert(pl_tex_upload(g.gl->gpu,pl_tex_transfer_params(.tex=source.planes[0].texture,.ptr=luma)));
        free(luma);
        pl_tex_clear(g.gl->gpu,source.planes[1].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
    }
    size_t bytes;
    AVDOVIMetadata *metadata=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *header=av_dovi_get_header(metadata);
    header->vdr_bit_depth=12;
    AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    color->signal_bit_depth=12;color->signal_full_range_flag=1;
    color->source_max_pq=3079;
    for(unsigned i=0;i<3;i++)color->ycc_to_rgb_offset[i]=(AVRational){1,i?2:16};
    if(p5){
        header->rpu_type=2;header->rpu_format=18;header->vdr_rpu_profile=0;
        header->bl_video_full_range_flag=1;header->coef_log2_denom=23;
        color->signal_color_space=2;
        const int matrix[9]={8192,799,1681,8192,-933,1091,8192,267,-5545};
        for(unsigned i=0;i<9;i++){
            color->ycc_to_rgb_matrix[i]=(AVRational){matrix[i],8192};
            color->rgb_to_lms_matrix[i]=(AVRational){i%4?-349:17081,16384};
        }
        for(unsigned i=0;i<3;i++){
            color->ycc_to_rgb_offset[i]=(AVRational){i?1:0,i?2:1};
            av_dovi_get_mapping(metadata)->curves[i].poly_coef[0][1]=1<<23;
        }
    }
    metadata->num_ext_blocks=1;
    *av_dovi_get_ext(metadata,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1800}};
    unsigned char expected[4],actual[4];
    render_target(&g,r,&source,metadata,bytes,3840,2160,false,expected);
    const int sizes[][2]={{1280,720},{1920,1080},{2560,1440}};
    for(unsigned i=0;i<sizeof(sizes)/sizeof(*sizes);i++){
        render_target(&g,r,&source,metadata,bytes,sizes[i][0],sizes[i][1],false,actual);
        if(memcmp(expected,actual,4))fprintf(stderr,"constant target=%ux%u bytes expected=%u,%u,%u,%u actual=%u,%u,%u,%u\n",
            sizes[i][0],sizes[i][1],expected[0],expected[1],expected[2],expected[3],actual[0],actual[1],actual[2],actual[3]);
        assert(!memcmp(expected,actual,4) && "Constant reference codes must not depend on carrier size");
    }
    if(!strcmp(mode,"master") && !p5)
        render_target(&g,r,&source,metadata,bytes,1280,720,true,actual);
    for(int p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&source.planes[p].texture);
    av_free(metadata);
    dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
    reference_gpu_destroy(&g);
    puts("PASS Master packing and active area use the actual output target");
}
