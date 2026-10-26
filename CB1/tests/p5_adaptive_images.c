/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Paired Adaptive transfer: pixels, black and complete output metadata. */
#include "reference_test.h"
#include "../src/dvbridge_render.c"
#include <time.h>
static enum dvbridge_dv_policy_status finish(struct dvbridge_renderer*r)
{
    for(unsigned i=0;i<10000;i++){
        enum dvbridge_dv_policy_status s=dvbridge_render_dv_policy_poll(r);
        if(s!=DVBRIDGE_DV_PENDING&&s!=DVBRIDGE_DV_BUSY)return s;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"GPU timeout");return DVBRIDGE_DV_FAILED;
}
int main(int argc,char **argv)
{
    const bool fel=argc==2;
    assert(argc==1 || (argc==2 && !strcmp(argv[1],"--fel")));
    struct reference_gpu g=reference_gpu_create();size_t bytes;
    AVDOVIMetadata*m=task3_fixture(&bytes);
    AVDOVIRpuDataHeader*h=av_dovi_get_header(m);
    if(!fel){
        h->rpu_type=2;h->rpu_format=18;h->vdr_rpu_profile=0;h->bl_video_full_range_flag=1;
        h->vdr_bit_depth=12;h->coef_log2_denom=23;
        AVDOVIColorMetadata*c=av_dovi_get_color(m);c->signal_color_space=2;
        c->signal_bit_depth=12;c->signal_full_range_flag=1;c->source_max_pq=3079;
        const int ycc[9]={8192,799,1681,8192,-933,1091,8192,267,-5545};
        for(unsigned i=0;i<9;i++){
            c->ycc_to_rgb_matrix[i]=(AVRational){ycc[i],8192};
            c->rgb_to_lms_matrix[i]=(AVRational){i%4==0?17081:-349,16384};
        }
        for(unsigned i=0;i<3;i++){
            c->ycc_to_rgb_offset[i]=(AVRational){i?1:0,i?2:1};
            av_dovi_get_mapping(m)->curves[i].poly_coef[0][1]=1<<23;
        }
        assert(dvbridge_dv_profile5_transport(m));
    }else{
        h->disable_residual_flag=0;h->vdr_bit_depth=12;h->coef_log2_denom=23;
        AVDOVIDataMapping*mapping=av_dovi_get_mapping(m);
        mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
        for(unsigned j=0;j<3;j++){
            mapping->curves[j].poly_coef[0][1]=1<<23;
            mapping->nlq[j]=(AVDOVINLQParams){.nlq_offset=512,.vdr_in_max=131072,
                .linear_deadzone_slope=8192,.linear_deadzone_threshold=4096};
        }
        AVDOVIColorMetadata*c=av_dovi_get_color(m);c->source_max_pq=3079;c->signal_bit_depth=12;
        for(unsigned j=0;j<9;j++){
            c->ycc_to_rgb_matrix[j]=(AVRational){dvbridge_output_ycc[j],8192};
            c->rgb_to_lms_matrix[j]=(AVRational){dvbridge_output_lms[j],16384};
        }
        for(unsigned j=0;j<3;j++)c->ycc_to_rgb_offset[j]=(AVRational){1,j?2:16};
    }
    m->num_ext_blocks=3;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1200}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=2851,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    *av_dovi_get_ext(m,2)=(AVDOVIDmData){.level=5};
    struct pl_frame source={.num_planes=2,.crop={0,0,3840,2160},
        .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
    for(unsigned p=0;p<2;p++){
        unsigned w=p?1920:3840,hh=p?1080:2160,components=p?2:1;
        uint16_t*data=malloc((size_t)w*hh*components*2);assert(data);
        for(unsigned y=0;y<hh;y++)for(unsigned x=0;x<w;x++)for(unsigned k=0;k<components;k++){
            unsigned code=p?(x<32?512:502+(x*3+y*5+k*7)%21):(x<64?0:(x*17+y*29)%701);
            data[((size_t)y*w+x)*components+k]=code<<6;
        }
        pl_fmt f=pl_find_fmt(g.gl->gpu,PL_FMT_UNORM,components,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);
        source.planes[p]=(struct pl_plane){.components=components,.component_mapping={p,2},.shift_x=p?-.5f:0,
            .texture=pl_tex_create(g.gl->gpu,pl_tex_params(.w=w,.h=hh,.format=f,.sampleable=true,.renderable=true,
                .host_writable=true,.initial_data=data))};
        free(data);assert(source.planes[p].texture);
    }
    struct pl_frame enhancement=source;
    if(fel){
        source.enhancement_layer=&enhancement;
        for(unsigned p=0;p<2;p++){
            struct pl_tex_params params=source.planes[p].texture->params;
            params.initial_data=NULL;params.blit_dst=true;
            enhancement.planes[p].texture=pl_tex_create(g.gl->gpu,&params);assert(enhancement.planes[p].texture);
            pl_tex_clear(g.gl->gpu,enhancement.planes[p].texture,(float[4]){32768.f/65535,32768.f/65535,0,1});
        }
    }
    pl_fmt f=pl_find_named_fmt(g.gl->gpu,"rgba8");
    pl_tex target=pl_tex_create(g.gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=f,.renderable=true));assert(target);
    GLuint fbo;pl_opengl_unwrap(g.gl->gpu,target,NULL,NULL,&fbo);
    size_t n=3840u*2160u*4;uint8_t*a=malloc(n),*b=malloc(n);assert(a&&b);
    for(unsigned colour=0;colour<2;colour++){
        av_dovi_get_ext(m,1)->l2.trim_chroma_weight=colour?2300:2048;
        av_dovi_get_ext(m,1)->l2.trim_saturation_gain=colour?2200:2048;
        void*meta=NULL;size_t size=0;unsigned packet_reference=0;
        for(unsigned trial=0;trial<2;trial++){
            struct dvbridge_retirement_owner*owner=dvbridge_retirement_owner_create(g.gl->gpu);assert(owner);
            struct dvbridge_renderer*r=dvbridge_renderer_create_with_owner(owner);assert(r);
            r->authored_p5_analytic=trial;r->authored_fel_lookup=!trial;

            struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_ENHANCED_DV,
                .adaptive=DVBRIDGE_ADAPTIVE_B_FP16,.tv={2500,DVBRIDGE_PANEL_UNSET,DVBRIDGE_GAMUT_P3_D65}};
            if(fel)policy.tv.peak_nits=5000;
            struct dvbridge_identity id={77,1,1};
            assert(dvbridge_render_dv_policy_prepare_packed(r,&policy,&id,&source,m,bytes,0,0,
                (struct dvbridge_geometry){3840,2160,0,0,3840,2160},target,false,NULL)==DVBRIDGE_DV_PENDING);
            assert(finish(r)==DVBRIDGE_DV_READY);const struct dvbridge_dv_policy_output*out=dvbridge_render_dv_policy_output(r);
            assert(out&&out->value.expansion_reason==CB1_DVE_ACTIVE);
            assert(r->enhanced_analytic_pq==(bool)trial&&r->enhanced_pq_lookup==!trial);
            unsigned packets;assert(dvbridge_packets(out->candidate,&packets));
            if(!trial)packet_reference=packets;else assert(packets==packet_reference);
            if(!trial){size=out->bytes;meta=av_memdup(out->output_metadata,size);assert(meta);}
            else assert(size==out->bytes&&!memcmp(meta,out->output_metadata,size));
            assert(dvbridge_render_dv_policy_resolve(r,target,fbo,false));
            glBindFramebuffer(GL_FRAMEBUFFER,fbo);glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,trial?b:a);
            glBindFramebuffer(GL_FRAMEBUFFER,0);assert(glGetError()==GL_NO_ERROR);
            if(trial){
                unsigned my=0,mc=0,black=0;size_t changed=0,black_samples=0;
                double sy=0,sc=0;size_t first=(size_t)packet_reference*3072;
                assert(first<n/4);
                for(size_t i=first*4;i<n;i+=4){
                    unsigned ay=16*a[i+1]+(a[i+2]&15),by=16*b[i+1]+(b[i+2]&15);
                    unsigned ac=16*a[i]+(a[i+2]>>4),bc=16*b[i]+(b[i+2]>>4);
                    unsigned dy=abs((int)ay-(int)by),dc=abs((int)ac-(int)bc);
                    my=fmax(my,dy);mc=fmax(mc,dc);sy+=dy;sc+=dc;changed+=dy||dc;
                    if(ay==256){black=fmax(black,dy);black_samples++;}
                }
                printf("%s analytic colour%u maxY=%u maxC=%u meanY=%.9g meanC=%.9g black=%u black_samples=%zu changed=%zu packet_pixels_excluded=%zu metadata=exact\n",
                    fel?"FEL":"P5",colour,my,mc,sy/(n/4-first),sc/(n/4-first),black,black_samples,changed,first);
                assert(my<=1&&mc<=2&&!black&&black_samples&&black_samples<(n/4-first)/2);
            }
            dvbridge_render_dv_policy_cancel(r);assert(finish(r)==DVBRIDGE_DV_IDLE);
            dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&owner));
        }
        av_free(meta);
    }
    free(a);free(b);pl_tex_destroy(g.gl->gpu,&target);
    for(unsigned p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&source.planes[p].texture);
    if(fel)for(unsigned p=0;p<2;p++)pl_tex_destroy(g.gl->gpu,&enhancement.planes[p].texture);
    av_free(m);reference_gpu_destroy(&g);puts("PASS Adaptive paired transfer");
}
