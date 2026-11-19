/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
#include <string.h>

int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    GLint subgroup=0,stages=0,features=0;
    if(pl_opengl_has_ext(g.gl,"GL_KHR_shader_subgroup")){
        glGetIntegerv(0x9532,&subgroup);glGetIntegerv(0x9533,&stages);glGetIntegerv(0x9534,&features);
    }
    bool legacy=subgroup>=4 && subgroup<=128 && !(subgroup&(subgroup-1)) &&
        (stages&GL_FRAGMENT_SHADER_BIT) && (features&0x81)==0x81;
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->rpu_type=2;h->rpu_format=18;h->vdr_rpu_profile=0;
    h->bl_video_full_range_flag=1;h->vdr_bit_depth=12;h->coef_log2_denom=23;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    c->signal_color_space=2;c->signal_bit_depth=12;c->signal_full_range_flag=1;
    const int matrix[9]={8192,799,1681,8192,-933,1091,8192,267,-5545};
    for(int i=0;i<9;i++){
        c->ycc_to_rgb_matrix[i]=(AVRational){matrix[i],8192};
        c->rgb_to_lms_matrix[i]=(AVRational){i%4?-349:17081,16384};
    }
    for(int i=0;i<3;i++){
        c->ycc_to_rgb_offset[i]=(AVRational){i?1:0,i?2:1};
        av_dovi_get_mapping(m)->curves[i].poly_coef[0][1]=1<<23;
    }
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.min_pq=12,.max_pq=3079,.avg_pq=1200}};
    void *saved=av_memdup(m,bytes);assert(saved);
    struct pl_frame source={.num_planes=2,.crop={0,0,3840,2160},
        .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
    for(int p=0;p<2;p++){
        pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,p?2:1,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        source.planes[p]=(struct pl_plane){.components=p?2:1,.component_mapping={p,2},.shift_x=p?-.5f:0,
            .texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=p?1920:3840,.h=p?1080:2160,
                .format=fmt,.sampleable=true,.renderable=true,.blit_dst=true,.host_writable=true))};
        assert(source.planes[p].texture);
        pl_tex_clear(g.gl->gpu,source.planes[p].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
    }
    pl_fmt fmt=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);
    pl_tex out=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true,.sampleable=true));assert(out);
    struct dvbridge_geometry geo={3840,2160,0,0,3840,2160};
    dvbridge_renderer_set_optimized_dv(r,true);
    assert(pl_cb1_dovi_reference_frame_supported(&source,10));
    struct pl_frame unsupported=source;
    unsupported.repr.bits.sample_depth=10;
    assert(!pl_cb1_dovi_reference_frame_supported(&unsupported,10));
    unsupported=source;unsupported.field=PL_FIELD_TOP;
    assert(!pl_cb1_dovi_reference_frame_supported(&unsupported,10));
    /* Repeated Standard pictures keep their fixed IPT recipe and source metadata. */
    for(int picture=0;picture<2;picture++){

        assert(dvbridge_render_packed(r,&source,m,bytes,picture,NAN,geo,out,false));
        const struct dvbridge_candidate *candidate=dvbridge_render_candidate(r);assert(candidate);
        unsigned count;const uint32_t *packets=dvbridge_packets(candidate,&count);
        assert(count && packets[5+61]==2);
        assert(!memcmp(saved,m,bytes));
        assert(dvbridge_render_commit(r));
    }
    /* A sharp chroma step distinguishes the five-tap Standard from exact Master. */
    uint16_t *uv=malloc((size_t)1920*1080*2*sizeof(*uv));assert(uv);
    for(int y=0;y<1080;y++)for(int x=0;x<1920;x++){
        uv[((size_t)y*1920+x)*2]=(y>=4?1023:0)<<6;
        uv[((size_t)y*1920+x)*2+1]=512<<6;
    }
    assert(pl_tex_upload(g.gl->gpu,pl_tex_transfer_params(.tex=source.planes[1].texture,.ptr=uv)));free(uv);
    GLuint fbo;glGenFramebuffers(1,&fbo);
    for(int master=0;master<2;master++){
        if(master)assert(dvbridge_render_master_reference(r,&source,m,bytes,2,NAN,geo,out,false,NULL)==CB1_MASTER_READY);
        else assert(dvbridge_render_packed(r,&source,m,bytes,2,NAN,geo,out,false));
        glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,out,NULL,NULL,NULL),0);
        uint8_t pixel[4];glReadPixels(200,7,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);assert(glGetError()==GL_NO_ERROR);
        unsigned ipt_p=(pixel[0]<<4)|(pixel[2]>>4);
        /* Hardware interpolation permits two codes around the analytical five-tap value. */
        if(master)assert(ipt_p==879);
        else assert(abs((int)ipt_p-783)<=2);
        assert(((pixel[1]<<4)|(pixel[2]&15))==2048);
        glBindFramebuffer(GL_FRAMEBUFFER,0);assert(dvbridge_render_commit(r));
    }
    glDeleteFramebuffers(1,&fbo);
    AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(m)->curves[0];
    curve->num_pivots=3;curve->pivots[2]=1023;
    curve->poly_order[1]=1;curve->poly_coef[1][0]=1<<21;
    glGenFramebuffers(1,&fbo);
    for(int turn=0;turn<2;turn++){
        curve->pivots[1]=turn?768:256;
        memcpy(saved,m,bytes);
        assert(dvbridge_render_packed(r,&source,m,bytes,3+turn,NAN,geo,out,false));
        glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,pl_opengl_unwrap(g.gl->gpu,out,NULL,NULL,NULL),0);
        uint8_t pixel[4];glReadPixels(200,1000,1,1,GL_RGBA,GL_UNSIGNED_BYTE,pixel);assert(glGetError()==GL_NO_ERROR);
        assert(((pixel[1]<<4)|(pixel[2]&15))==(turn?2048:1024));
        glBindFramebuffer(GL_FRAMEBUFFER,0);assert(!memcmp(saved,m,bytes));assert(dvbridge_render_commit(r));
    }
    glDeleteFramebuffers(1,&fbo);
    source.planes[1].shift_y=-.5f;
    bool ok=dvbridge_render_packed(r,&source,m,bytes,5,NAN,geo,out,false);assert(ok==legacy);
    unsigned count;const uint32_t *packets;
    if(ok){packets=dvbridge_packets(dvbridge_render_candidate(r),&count);
        assert(count && packets[5+61]==0);assert(dvbridge_render_commit(r));}
    source.planes[1].shift_y=0;
    h->vdr_rpu_profile=1;h->bl_video_full_range_flag=0;c->signal_color_space=0;
    c->ycc_to_rgb_offset[0]=(AVRational){1,16};
    ok=dvbridge_render_packed(r,&source,m,bytes,6,NAN,geo,out,false);assert(ok==legacy);
    if(ok){packets=dvbridge_packets(dvbridge_render_candidate(r),&count);
        assert(count && packets[5+61]==0);assert(dvbridge_render_commit(r));}
    h->vdr_rpu_profile=0;h->bl_video_full_range_flag=1;c->signal_color_space=2;
    c->ycc_to_rgb_offset[0]=(AVRational){0,1};m->num_ext_blocks=2;
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=5,.l5={.left_offset=1,.right_offset=1}};
    ok=dvbridge_render_packed(r,&source,m,bytes,7,NAN,geo,out,false);assert(ok==legacy);
    if(ok){packets=dvbridge_packets(dvbridge_render_candidate(r),&count);
        assert(count && packets[5+61]==0);assert(dvbridge_render_commit(r));}
    for(int p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&source.planes[p].texture);
    pl_tex_destroy(g.gl->gpu,&out);dvbridge_renderer_destroy(r);av_free(saved);av_free(m);
    reference_gpu_destroy(&g);puts("PASS P5 Standard IPT admission and immutable metadata");
    return 0;
}
