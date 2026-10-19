/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "reference_test.h"
#include "dvbridge_gl_frame.h"

#ifndef CB1_FEL_FILTER_API
extern void dvbridge_renderer_set_fel_nearest(struct dvbridge_renderer *,bool) __attribute__((weak));
#endif

static pl_tex residual(pl_gpu gpu,int w,int h,int out_w,int out_h,int enlarged,bool flip)
{
    uint16_t *data=malloc((size_t)out_w*out_h*8);assert(data);
    for(int y=0;y<out_h;y++)for(int x=0;x<out_w;x++){
        /* Independent left-sited horizontal, centered vertical nearest oracle. */
        int sx=enlarged?(x+(enlarged==1))/2:x,sy=enlarged?y/2:y;
        if(sx>=w)sx=w-1;if(sy>=h)sy=h-1;
        if(flip)sy=h-1-sy;
        unsigned at=4u*(y*out_w+x);
        for(int c=0;c<3;c++)data[at+c]=(384+((sx*3+sy*5+c)%5)*64)<<6;
        data[at+3]=65535;
    }
    pl_fmt fmt=pl_find_fmt(gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_SAMPLEABLE);
    assert(fmt);
    pl_tex tex=pl_tex_create(gpu,pl_tex_params(.w=out_w,.h=out_h,.format=fmt,
        .sampleable=true,.initial_data=data));free(data);assert(tex);return tex;
}

static void qualify(struct reference_gpu *g,int ew,int eh,bool flip,bool fast)
{
    const int w=64,h=48;
    float *base=malloc((size_t)w*h*16),*actual=malloc((size_t)w*h*16);
    float *expected=malloc((size_t)w*h*16),*before=malloc((size_t)w*h*16);
    float *lower=malloc((size_t)w*h*16);assert(base && actual && expected && before && lower);
    for(int i=0;i<w*h;i++)for(int c=0;c<4;c++)base[4*i+c]=c==3?1.f:.2f+c*.01f;
    pl_tex bl=reference_texture(g->gl->gpu,w,h,base);
    pl_tex small=residual(g->gl->gpu,ew,eh,ew,eh,false,false);
    pl_tex full=residual(g->gl->gpu,ew,eh,w,h,1,flip);
    pl_tex full_lower=residual(g->gl->gpu,ew,eh,w,h,2,flip);
    struct pl_frame source=reference_frame(bl,w,h),el=reference_frame(small,ew,eh);
    el.repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
    el.planes[0].flipped=flip;
    source.enhancement_layer=&el;
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1500}};
    av_dovi_get_header(m)->disable_residual_flag=0;
    AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);
    mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++){
        mapping->nlq[c].nlq_offset=512;
        mapping->nlq[c].linear_deadzone_slope=4096;
        mapping->nlq[c].vdr_in_max=1023*4096;
    }
    struct dvbridge_renderer *r=dvbridge_renderer_create(g->gl->gpu);assert(r);
    dvbridge_renderer_set_fast_chroma(r,fast);
    struct dvbridge_geometry geometry={w,h,0,0,w & ~1,h};
    assert(dvbridge_render_rgb(r,&source,m,bytes,1,1,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,before);
    dvbridge_renderer_set_fel_nearest(r,true);
    assert(dvbridge_render_rgb(r,&source,m,bytes,2,2,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,actual);
    el=reference_frame(full,w,h);
    el.repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
    assert(dvbridge_render_rgb(r,&source,m,bytes,3,3,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,expected);
    el.planes[0].texture=full_lower;
    assert(dvbridge_render_rgb(r,&source,m,bytes,3.5,3.5,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,lower);
    bool differs=false;
    for(int p=0;p<w*h;p++){
        bool upper_match=true,lower_match=true;
        for(int c=0;c<4;c++){
            int i=p*4+c;
            assert(isfinite(actual[i]) && isfinite(expected[i]) && isfinite(lower[i]));
            upper_match &= fabsf(actual[i]-expected[i])<=2e-5f;
            lower_match &= fabsf(actual[i]-lower[i])<=2e-5f;
            differs|=fabsf(actual[i]-before[i])>1e-4f;
        }
        /* At an exact half-way coordinate either equidistant texel is nearest.
         * Both independent oracles coincide at every non-tied coordinate. */
        if(!upper_match && !lower_match){
            fprintf(stderr,"nearest mismatch EL=%dx%d flip=%d fast=%d at=%d actual=%.8g lower=%.8g upper=%.8g\n",
                ew,eh,flip,fast,p,actual[p*4],lower[p*4],expected[p*4]);
            assert(!"Nearest EL phase or residual changed");
        }
    }
    assert(differs && "Fixture must exercise an actual nonzero scaled FEL residual");
    el=reference_frame(small,ew,eh);el.planes[0].flipped=flip;
    el.repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
    dvbridge_renderer_set_fel_nearest(r,false);
    assert(dvbridge_render_rgb(r,&source,m,bytes,4,4,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,actual);
    assert(!memcmp(actual,before,(size_t)w*h*16) && "Default rendering changed after filter switch");
    source.enhancement_layer=NULL;av_dovi_get_header(m)->disable_residual_flag=1;
    assert(dvbridge_render_rgb(r,&source,m,bytes,5,NAN,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,before);
    dvbridge_renderer_set_fel_nearest(r,true);
    assert(dvbridge_render_rgb(r,&source,m,bytes,6,NAN,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,actual);
    assert(!memcmp(actual,before,(size_t)w*h*16) && "Nearest changed a source without FEL");
    dvbridge_renderer_destroy(r);av_free(m);
    pl_tex_destroy(g->gl->gpu,&bl);pl_tex_destroy(g->gl->gpu,&small);pl_tex_destroy(g->gl->gpu,&full);
    pl_tex_destroy(g->gl->gpu,&full_lower);
    free(base);free(actual);free(expected);free(before);free(lower);
}

static pl_tex render_mode(struct dvbridge_renderer *r,const struct pl_frame *source,
    AVDOVIMetadata *metadata,size_t bytes,struct dvbridge_geometry geometry,int mode)
{
    if(!mode){
        assert(dvbridge_render_rgb(r,source,metadata,bytes,1,1,geometry));
        return dvbridge_render_texture(r);
    }
    struct dvbridge_policy p=reference_policy();
    p.tv.gamut=DVBRIDGE_GAMUT_BT2020;
    struct dvbridge_identity id={1,1,1};
    p.mode=mode==1?DVBRIDGE_MODE_HDR10_BASIC:mode==2?DVBRIDGE_MODE_HDR10_EXPERT:DVBRIDGE_MODE_ENHANCED_DV;
    if(mode==1){
        struct dvbridge_hdr10_session session={.target={.primaries=PL_COLOR_PRIM_BT_2020,
            .transfer=PL_COLOR_TRC_LINEAR,.hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1000}}};
        assert(dvbridge_render_hdr10_rgb(r,&session,source,metadata,bytes,1,1,geometry));
        return dvbridge_render_texture(r);
    }
    if(mode==2){
        assert(dvbridge_render_hdr10_policy_rgb(r,&p,&id,source,metadata,bytes,1,1,geometry));
        return dvbridge_render_texture(r);
    }
    
    enum dvbridge_dv_policy_status status=dvbridge_render_dv_policy_prepare(r,&p,&id,
        source,metadata,bytes,1,1,geometry);
    for(int i=0;i<100 && status==DVBRIDGE_DV_PENDING;i++){
        glFinish();status=dvbridge_render_dv_policy_poll(r);
    }
    if(status!=DVBRIDGE_DV_READY)fprintf(stderr,"Adaptive fixture mode=%d status=%d\n",mode,status);
    assert(status==DVBRIDGE_DV_READY);
    const struct dvbridge_dv_policy_output *out=dvbridge_render_dv_policy_output(r);
    assert(out && out->value.fel_reconstructed);
    return out->intermediate;
}

static void qualify_modes(struct reference_gpu *g)
{
    const int w=64,h=48;
    float base[w*h*4],actual[w*h*4],expected[w*h*4];
    for(int i=0;i<w*h;i++)for(int c=0;c<4;c++)base[4*i+c]=c==3?1.f:.25f+c*.01f;
    pl_tex bl=reference_texture(g->gl->gpu,w,h,base);
    /* Vertical variation avoids half-texel tie ambiguity in this path comparison. */
    pl_tex small=residual(g->gl->gpu,w,h/2,w,h/2,0,false);
    uint16_t data[w*h*4];
    for(int y=0;y<h;y++)for(int x=0;x<w;x++)for(int c=0;c<4;c++)
        data[(y*w+x)*4+c]=c==3?65535:(384+((x*3+(y/2)*5+c)%5)*64)<<6;
    pl_fmt fmt=pl_find_fmt(g->gl->gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
    pl_tex full=pl_tex_create(g->gl->gpu,pl_tex_params(.w=w,.h=h,.format=fmt,
        .sampleable=true,.initial_data=data));assert(full);
    struct pl_frame source=reference_frame(bl,w,h),el=reference_frame(small,w,h/2);
    el.repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
    source.enhancement_layer=&el;
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=2;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1500}};
    *av_dovi_get_ext(m,1)=(AVDOVIDmData){.level=5,.l5={.top_offset=4,.bottom_offset=4}};
    av_dovi_get_header(m)->disable_residual_flag=0;
    AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++){
        mapping->nlq[c].nlq_offset=512;mapping->nlq[c].linear_deadzone_slope=4096;
        mapping->nlq[c].vdr_in_max=1023*4096;
    }
    struct dvbridge_geometry geometry={w,h,0,0,w,h};
    for(int fast=0;fast<2;fast++)for(int mode=0;mode<5;mode++){
        struct dvbridge_retirement_owner *a=dvbridge_retirement_owner_create(g->gl->gpu);
        struct dvbridge_retirement_owner *b=dvbridge_retirement_owner_create(g->gl->gpu);assert(a && b);
        struct dvbridge_renderer *nearest=dvbridge_renderer_create_with_owner(a);
        struct dvbridge_renderer *oracle=dvbridge_renderer_create_with_owner(b);assert(nearest && oracle);
        dvbridge_renderer_set_fast_chroma(nearest,fast);dvbridge_renderer_set_fast_chroma(oracle,fast);
        dvbridge_renderer_set_fel_nearest(nearest,true);
        dvbridge_renderer_set_fel_nearest(oracle,true);
        el.planes[0].texture=small;
        reference_read(g->gl->gpu,render_mode(nearest,&source,m,bytes,geometry,mode),0,0,w,h,actual);
        el=reference_frame(full,w,h);
        el.repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
        reference_read(g->gl->gpu,render_mode(oracle,&source,m,bytes,geometry,mode),0,0,w,h,expected);
        for(int i=0;i<w*h*4;i++)if(!isfinite(actual[i]) || fabsf(actual[i]-expected[i])>=3e-5f){
            fprintf(stderr,"mode=%d fast=%d at=%d actual=%.9g oracle=%.9g\n",mode,fast,i,actual[i],expected[i]);
            assert(!"FEL filter circuit comparison failed");
        }
        dvbridge_renderer_destroy(nearest);dvbridge_renderer_destroy(oracle);
        glFinish();dvbridge_retirement_owner_poll(a);dvbridge_retirement_owner_poll(b);
        assert(dvbridge_retirement_owner_destroy(&a) && dvbridge_retirement_owner_destroy(&b));
        el=reference_frame(small,w,h/2);
        el.repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
    }
    pl_tex_destroy(g->gl->gpu,&bl);pl_tex_destroy(g->gl->gpu,&small);pl_tex_destroy(g->gl->gpu,&full);av_free(m);
}

static unsigned residual_code(int x,int y,int c)
{
    return 384+((x*3+y*2+c)%5)*64;
}

static void qualify_planes(struct reference_gpu *g,bool planar,bool flip,bool fast)
{
    const int w=16,h=16,ew=8,eh=8;
    float base[w*h*4],actual[w*h*4],before[w*h*4],expected[8][w*h*4];
    for(int i=0;i<w*h;i++)for(int c=0;c<4;c++)base[i*4+c]=c==3?1:.2f+c*.01f;
    pl_tex bl=reference_texture(g->gl->gpu,w,h,base),planes[3]={0};
    struct dvbridge_gl_plane handles[3]={0};
    for(int p=0;p<(planar?3:2);p++){
        int pw=p?ew/2:ew,ph=p?eh/2:eh,components=(!planar && p)?2:1;
        uint16_t data[pw*ph*components];
        for(int y=0;y<ph;y++)for(int x=0;x<pw;x++)for(int c=0;c<components;c++)
            data[(y*pw+x)*components+c]=residual_code(x,y,p+c)<<(planar?0:6);
        pl_fmt fmt=pl_find_fmt(g->gl->gpu,PL_FMT_UNORM,components,16,16,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
        planes[p]=pl_tex_create(g->gl->gpu,pl_tex_params(.w=pw,.h=ph,.format=fmt,.sampleable=true,.initial_data=data));
        assert(planes[p]);
        handles[p]=(struct dvbridge_gl_plane){pl_opengl_unwrap(g->gl->gpu,planes[p],NULL,NULL,NULL),pw,ph};
    }
    struct dvbridge_gl_frame imported={0};
    assert(dvbridge_gl_frame_import(&imported,g->gl->gpu,planar?DVBRIDGE_YUV420P10:DVBRIDGE_P010,ew,eh,handles));
    for(int p=0;p<imported.frame.num_planes;p++)imported.frame.planes[p].flipped=flip;
    struct pl_frame source=reference_frame(bl,w,h);source.enhancement_layer=&imported.frame;
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);m->num_ext_blocks=1;
    *av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1500}};
    av_dovi_get_header(m)->disable_residual_flag=0;
    AVDOVIDataMapping *mapping=av_dovi_get_mapping(m);mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++){
        mapping->nlq[c].nlq_offset=512;mapping->nlq[c].linear_deadzone_slope=4096;
        mapping->nlq[c].vdr_in_max=1023*4096;
    }
    struct dvbridge_geometry geometry={w,h,0,0,w,h};
    struct dvbridge_renderer *r=dvbridge_renderer_create(g->gl->gpu);assert(r);
    dvbridge_renderer_set_fast_chroma(r,fast);
    assert(dvbridge_render_rgb(r,&source,m,bytes,0,0,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,before);
    dvbridge_renderer_set_fel_nearest(r,true);
    assert(dvbridge_render_rgb(r,&source,m,bytes,1,1,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,actual);
    /* Packed independent reconstructions enumerate only equidistant horizontal
     * ties, separately for luma and each chroma channel. Vertical siting is exact. */
    for(int tie=0;tie<8;tie++){
        uint16_t data[w*h*4];
        for(int y=0;y<h;y++)for(int x=0;x<w;x++)for(int c=0;c<4;c++){
            int scale=c?4:2;
            int sx=(x+1)/scale,sy=y/scale;
            if((x+1)%scale==0 && sx>0 && !(tie&(1<<c)))--sx;
            if(sx>=ew/(c?2:1))sx=ew/(c?2:1)-1;
            if(flip)sy=eh/(c?2:1)-1-sy;
            data[(y*w+x)*4+c]=c==3?65535:residual_code(sx,sy,c)<<6;
        }
        pl_fmt fmt=pl_find_fmt(g->gl->gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_SAMPLEABLE);assert(fmt);
        pl_tex full=pl_tex_create(g->gl->gpu,pl_tex_params(.w=w,.h=h,.format=fmt,
            .sampleable=true,.initial_data=data));assert(full);
        struct pl_frame oracle=reference_frame(full,w,h);
        oracle.repr.bits=(struct pl_bit_encoding){.sample_depth=16,.color_depth=10,.bit_shift=6};
        source.enhancement_layer=&oracle;
        assert(dvbridge_render_rgb(r,&source,m,bytes,2+tie,2+tie,geometry));
        reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,expected[tie]);
        pl_tex_destroy(g->gl->gpu,&full);
    }
    for(int p=0;p<w*h;p++){
        bool matches=false;
        for(int tie=0;tie<8;tie++){
            bool same=true;
            for(int c=0;c<4;c++)same &= isfinite(actual[p*4+c]) && fabsf(actual[p*4+c]-expected[tie][p*4+c])<2e-5f;
            matches |= same;
        }
        if(!matches){fprintf(stderr,"EL planes=%d flip=%d fast=%d pixel=%d\n",planar?3:2,flip,fast,p);assert(matches);}
    }
    source.enhancement_layer=&imported.frame;dvbridge_renderer_set_fel_nearest(r,false);
    assert(dvbridge_render_rgb(r,&source,m,bytes,10,10,geometry));
    reference_read(g->gl->gpu,dvbridge_render_texture(r),0,0,w,h,actual);
    assert(!memcmp(actual,before,sizeof(before)));
    dvbridge_renderer_destroy(r);dvbridge_gl_frame_release(&imported);
    for(int p=0;p<3;p++)pl_tex_destroy(g->gl->gpu,&planes[p]);
    pl_tex_destroy(g->gl->gpu,&bl);av_free(m);
}

int main(void)
{
    assert(dvbridge_renderer_set_fel_nearest && "Explicit FEL filter API missing");
    struct reference_gpu g=reference_gpu_create();
    for(int fast=0;fast<2;fast++)for(int flip=0;flip<2;flip++){
        qualify(&g,32,24,flip,fast);qualify(&g,33,25,flip,fast);
    }
    qualify_modes(&g);
    for(int planar=0;planar<2;planar++)for(int flip=0;flip<2;flip++)for(int fast=0;fast<2;fast++)
        qualify_planes(&g,planar,flip,fast);
    reference_gpu_destroy(&g);
    puts("PASS FEL nearest phase, borders, residual, Fast, policy reset and non-FEL identity");
}
