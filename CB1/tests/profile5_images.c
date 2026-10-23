/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
#include "cb1_master_reference.h"
static unsigned scaled_materializations;
static bool track_p5_scaling(pl_renderer,const struct pl_frame *,const struct pl_frame *,const struct pl_render_params *);
#define pl_render_image track_p5_scaling
#include "../src/dvbridge_render.c"
#undef pl_render_image
#include <time.h>

static void count_scaler_pass(void *priv,const struct pl_render_info *info)
{ (void)info;(*(unsigned*)priv)++; }

static bool track_p5_scaling(pl_renderer renderer,const struct pl_frame *source,
    const struct pl_frame *target,const struct pl_render_params *params)
{
    for(int i=0;i<params->num_hooks;i++)
        if(params->hooks[i]->input==PL_HOOK_SIG_TEX)scaled_materializations++;
    if(params->cb1_dovi_transport && !params->cb1_dovi_reference && source->num_planes==1){
        assert(source->repr.alpha==PL_ALPHA_NONE);
        assert(params->cb1_nearest_identity);
    }
    struct pl_render_params p=*params;
    unsigned passes=0;
    bool reused=params->cb1_dovi_transport && !params->cb1_dovi_reference &&
        source->num_planes==1 && params->num_hooks==1 &&
        params->hooks[0]->input==PL_HOOK_SIG_COLOR && !source->crop.x0 && !source->crop.y0 &&
        source->crop.x1<3840 && source->crop.x1*9==source->crop.y1*16;
    if(reused){p.info_callback=count_scaler_pass;p.info_priv=&passes;}
    bool ok=pl_render_image(renderer,source,target,&p);
    if(reused)assert(passes==2);
    return ok;
}

/* An AI write must supersede a deferred P5 backing before letterboxing. */
static void test_p5_ai_transition(struct reference_gpu *g,struct dvbridge_renderer *r,
    const struct pl_frame *source,const AVDOVIMetadata *m,size_t bytes,pl_tex output,
    unsigned char *a,unsigned char *b,size_t n)
{
    int w=source->crop.x1,h=source->crop.y1;
    AVDOVIMetadata *unmasked=av_memdup(m,bytes);assert(unmasked);
    for(int i=0;i<unmasked->num_ext_blocks;i++)if(av_dovi_get_ext(unmasked,i)->level==5)
        av_dovi_get_ext(unmasked,i)->l5=(typeof(av_dovi_get_ext(unmasked,i)->l5)){0};
    m=unmasked;
    struct dvbridge_geometry full={w,h,0,0,3840,2160},placed={w,804,0,276,3840,1608};
    struct pl_frame cropped=*source;cropped.crop.y1=804;
    dvbridge_renderer_reset(r);dvbridge_renderer_set_overlay_visible(r,false);
    assert(dvbridge_render_master_reference(r,source,m,bytes,0,NAN,full,output,false,NULL)==CB1_MASTER_READY);
    assert(dvbridge_render_commit(r));
    struct dvbridge_renderer *control=dvbridge_renderer_create(g->gl->gpu);assert(control);
    pl_tex black=reference_texture(g->gl->gpu,1,1,(float[4]){0,0,0,1});
    struct pl_frame ai=reference_frame(black,1,1);
    ai.repr=pl_color_repr_rgb;ai.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ};
    struct dvbridge_geometry screen={3840,2160,0,0,3840,2160};
    for(int path=0;path<2;path++){
        struct dvbridge_renderer *current=path?control:r;
        assert(ensure_rgb(current));
        dvbridge_renderer_reset(current);
        dvbridge_destroy(current->context);current->context=dvbridge_create();assert(current->context);
        assert(ai_render_pixels(current,&ai,screen,NULL,false,NULL));
        dvbridge_renderer_reset(current);
        assert(dvbridge_render_master_reference(current,&cropped,m,bytes,0,NAN,placed,output,false,NULL)==CB1_MASTER_READY);
        GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g->gl->gpu,output,NULL,NULL,NULL),0);
        glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,path?b:a);assert(glGetError()==GL_NO_ERROR);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);assert(dvbridge_render_commit(current));
    }
    assert(!memcmp(a,b,n));
    pl_tex_destroy(g->gl->gpu,&black);dvbridge_renderer_destroy(control);av_free(unmasked);
}

static double now(void)
{
    struct timespec t;timespec_get(&t,TIME_UTC);
    return t.tv_sec+t.tv_nsec*1e-9;
}

int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    dvbridge_renderer_set_optimized_dv(r,true);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->rpu_type=2;h->rpu_format=18;h->vdr_rpu_profile=0;h->bl_video_full_range_flag=1;
    h->vdr_bit_depth=12;h->coef_log2_denom=23;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    c->signal_color_space=2;c->signal_bit_depth=12;c->signal_full_range_flag=1;
    const int ycc[9]={8192,799,1681,8192,-933,1091,8192,267,-5545};
    for(int i=0;i<9;i++){
        c->ycc_to_rgb_matrix[i]=(AVRational){ycc[i],8192};
        c->rgb_to_lms_matrix[i]=(AVRational){i%4==0?17081:-349,16384};
    }
    for(int i=0;i<3;i++){
        c->ycc_to_rgb_offset[i]=(AVRational){i?1:0,i?2:1};
        av_dovi_get_mapping(m)->curves[i].poly_coef[0][1]=1<<23;
    }
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1200}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=5,.l5={.top_offset=12,.bottom_offset=12}};
    pl_fmt rgba=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);
    pl_tex output=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=rgba,.sampleable=true,.renderable=true));assert(output);
    const size_t n=(size_t)3840*2160*4;
    uint8_t *a=malloc(n),*b=malloc(n);assert(a && b);
    const int sizes[][2]={{3840,2160},{1920,1080},{2560,1440},{1920,804},
        {1920,1080},{3840,2160},{3840,2160},{3840,2160},{3840,2160}};
    for(unsigned test=0;test<sizeof(sizes)/sizeof(*sizes);test++){
        int w=sizes[test][0],hh=sizes[test][1];
        for(int component=0;component<3;component++){
            AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(m)->curves[component];
            memset(curve,0,sizeof(*curve));curve->num_pivots=2;curve->pivots[1]=1023;
            curve->poly_order[0]=1;curve->poly_coef[0][1]=1<<23;
            if(test==5 && !component){curve->poly_order[0]=2;curve->poly_coef[0][1]=0;curve->poly_coef[0][2]=1<<23;}
            if(test==6 && component){curve->mapping_idc[0]=AV_DOVI_MAPPING_MMR;
                curve->mmr_order[0]=1;curve->mmr_constant[0]=(component==1?1:3)<<21;}
        }
        struct pl_frame source={.num_planes=2,.crop={0,0,w,hh},
            .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
        for(int p=0;p<2;p++){
            pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,p?2:1,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
            source.planes[p]=(struct pl_plane){.components=p?2:1,.component_mapping={p,2},.shift_x=p?-.5f:0,
                .texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=p?w/2:w,.h=p?hh/2:hh,.format=fmt,
                    .sampleable=true,.renderable=true,.blit_dst=true,.host_writable=true))};
            assert(source.planes[p].texture);
            pl_tex_clear(g.gl->gpu,source.planes[p].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
            if(test==7 && !p){
                uint16_t *pixels=malloc((size_t)w*hh*sizeof(*pixels));assert(pixels);
                for(int y=0;y<hh;y++)for(int x=0;x<w;x++)pixels[(size_t)y*w+x]=((x*17+y*29)%1024)<<6;
                assert(pl_tex_upload(g.gl->gpu,pl_tex_transfer_params(.tex=source.planes[p].texture,.ptr=pixels)));
                free(pixels);
            }
        }
        struct dvbridge_geometry geo={w,hh,0,(2160-(int)round(3840.0*hh/w))/2,3840,(int)round(3840.0*hh/w)};
        if(test==4)geo=(struct dvbridge_geometry){w,hh,960,540,w,hh};
        struct dvbridge_native_overlay overlay={0};
        if(test==8){
            pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
            overlay.texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.sampleable=true,.renderable=true,.blit_dst=true));assert(overlay.texture);
            pl_tex_clear(g.gl->gpu,overlay.texture,(float[4]){0,0,0,0});
            float tile[8*4];for(int i=0;i<8;i++)memcpy(tile+4*i,(float[4]){0,0,0,.5f},4*sizeof(float));
            glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,overlay.texture,NULL,NULL,NULL));
            glTexSubImage2D(GL_TEXTURE_2D,0,100,2058,4,2,GL_RGBA,GL_FLOAT,tile);assert(glGetError()==GL_NO_ERROR);
            overlay.degamma=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
            overlay.pq=reference_texture(g.gl->gpu,1,1,(float[4]){0,0,0,1});
            memcpy(overlay.rect,(float[4]){100,100,104,102},sizeof(overlay.rect));
        }
        const int modes=
#ifdef CB1_ENABLE_MASTER_IPT
            3;
#else
            2;
#endif
        for(int mode=0;mode<modes;mode++){
            dvbridge_renderer_reset(r);
            dvbridge_renderer_set_overlay_visible(r,test==8);
            for(int flip=0;flip<2;flip++){
                scaled_materializations=0;
                enum cb1_master_status status;
                if(mode==modes-1)
                    status=dvbridge_render_packed_overlay(r,&source,m,bytes,0,NAN,geo,output,flip,test==8?&overlay:NULL)?CB1_MASTER_READY:CB1_MASTER_FAILED;
                else
#ifdef CB1_ENABLE_MASTER_IPT
                if(mode)status=dvbridge_render_master_reference_ipt(r,&source,m,bytes,0,NAN,geo,output,flip,test==8?&overlay:NULL);
                else
#endif
                status=dvbridge_render_master_reference(r,&source,m,bytes,0,NAN,geo,output,flip,test==8?&overlay:NULL);
                assert(status==CB1_MASTER_READY);
                if(r->fragment_quad && test>=1 && test<=3)assert(!scaled_materializations);
                unsigned count;const uint32_t *packets=dvbridge_packets(dvbridge_render_candidate(r),&count);assert(count);
                unsigned margins[4];assert(dvbridge_active_area(dvbridge_render_candidate(r),margins));
                GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
                glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
                glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,b);assert(glGetError()==GL_NO_ERROR);
                for(unsigned yy=0;yy<2160;yy++)for(unsigned x=0;x<3840;x++){
                    unsigned y=flip?2159-yy:yy,index=y*3840+x;
                    bool border=x<margins[0] || x>=3840-margins[1] || y<margins[2] || y>=2160-margins[3];
                    unsigned ii=border?0:test==5?1024:test==7?4*((x*17+y*29)%1024):2048;
                    unsigned cc=border?2048:test==6?((x&1)?3072:1024):2048;
                    if(test==8 && x>=100 && x<104 && y>=100 && y<102)ii=1024;
                    unsigned packet=index/3072;
                    if(packet<count){unsigned bit=index%1024,word=packet*128+bit/8;
                        unsigned value=(packets[word]>>(7-bit%8))&1;
                        unsigned parity=(__builtin_popcount(cc>>1)+__builtin_popcount(ii))&1;
                        cc=(cc&4094)|(value^parity);}
                    uint8_t expected[4]={cc>>4,ii>>4,(ii&15)|((cc&15)<<4),255};
                    if(memcmp(b+((size_t)yy*3840+x)*4,expected,4)){
                        fprintf(stderr,"P5 %dx%d mode%d flip%d @%u,%u unexpected carrier\n",w,hh,mode,flip,x,y);abort();}
                }
                if(!mode && !flip)memcpy(a,b,n);
                if(mode && !flip)assert(!memcmp(a,b,n));
                glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
                assert(dvbridge_render_commit(r));
            }
            glFinish();double start=now();
            for(int i=0;i<12;i++){
                if(mode==modes-1)
                    assert(dvbridge_render_packed(r,&source,m,bytes,i/25.0,NAN,geo,output,false));
                else
#ifdef CB1_ENABLE_MASTER_IPT
                if(mode)assert(dvbridge_render_master_reference_ipt(r,&source,m,bytes,i/25.0,NAN,geo,output,false,NULL)==CB1_MASTER_READY);
                else
#endif
                assert(dvbridge_render_master_reference(r,&source,m,bytes,i/25.0,NAN,geo,output,false,NULL)==CB1_MASTER_READY);
                glFinish();assert(dvbridge_render_commit(r));
            }
            printf("P5 case%u %dx%d %s mean render %.3f ms\n",test,w,hh,
                mode==modes-1?"Standard IPT Fast":mode?"Master IPT":"Master",(now()-start)*1000/12);fflush(stdout);
        }
        if(r->fragment_quad && test>=1 && test<=3){
            dvbridge_renderer_reset(r);r->fragment_quad=false;scaled_materializations=0;
            assert(dvbridge_render_master_reference(r,&source,m,bytes,0,NAN,geo,output,false,NULL)==CB1_MASTER_READY);
            assert(scaled_materializations);
            GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
            glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
            glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,b);assert(glGetError()==GL_NO_ERROR && !memcmp(a,b,n));
            glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);assert(dvbridge_render_commit(r));
            r->fragment_quad=true;
            /* Varied chroma catches an incorrect neighbouring quad lane. */
            for(int p=0;p<2;p++){
                pl_tex tex=source.planes[p].texture;int lanes=p?2:1;
                uint16_t *data=malloc((size_t)tex->params.w*tex->params.h*lanes*sizeof(*data));assert(data);
                for(int y=0;y<tex->params.h;y++)for(int x=0;x<tex->params.w;x++)for(int l=0;l<lanes;l++)
                    data[((size_t)y*tex->params.w+x)*lanes+l]=((x*17+y*29+l*211+(x^y)*7)%1024)<<6;
                assert(pl_tex_upload(g.gl->gpu,pl_tex_transfer_params(.tex=tex,.ptr=data)));free(data);
            }
            for(int path=0;path<2;path++){
                dvbridge_renderer_reset(r);r->fragment_quad=!path;
                assert(dvbridge_render_master_reference(r,&source,m,bytes,0,NAN,geo,output,false,NULL)==CB1_MASTER_READY);
                glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
                glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,output,NULL,NULL,NULL),0);
                glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,path?b:a);assert(glGetError()==GL_NO_ERROR);
                glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);assert(dvbridge_render_commit(r));
            }
            assert(!memcmp(a,b,n));r->fragment_quad=true;
        }
        if(test==1 && r->fragment_quad)test_p5_ai_transition(&g,r,&source,m,bytes,output,a,b,n);
        if(test==8){pl_tex_destroy(g.gl->gpu,&overlay.texture);pl_tex_destroy(g.gl->gpu,&overlay.degamma);pl_tex_destroy(g.gl->gpu,&overlay.pq);}
        for(int p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&source.planes[p].texture);
    }
    free(a);free(b);pl_tex_destroy(g.gl->gpu,&output);dvbridge_renderer_destroy(r);av_free(m);reference_gpu_destroy(&g);
    puts("PASS P5 complete carrier, metadata parity, geometry and Standard/Master routes");
}
