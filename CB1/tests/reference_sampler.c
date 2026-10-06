/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include <libplacebo/shaders/sampling.h>
#include <libplacebo/dispatch.h>
#include <dlfcn.h>
static bool missing_format;
pl_fmt pl_find_fmt(pl_gpu gpu,enum pl_fmt_type type,int comps,int depth,int host,enum pl_fmt_caps caps)
{
    static pl_fmt (*real)(pl_gpu,enum pl_fmt_type,int,int,int,enum pl_fmt_caps);
    if(!real)real=dlsym(RTLD_NEXT,"pl_find_fmt");assert(real);
    if(missing_format && type==PL_FMT_FLOAT && comps==4 && depth==32 && host==32 &&
       caps==(PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR))return NULL;
    return real(gpu,type,comps,depth,host,caps);
}
static void sampler_toggle(struct reference_gpu *g,const struct pl_filter_config *original,int axis,bool down)
{
    pl_gpu gpu=g->gl->gpu;float input[4*4*4];for(int i=0;i<64;i++)input[i]=i%4==3?1:(float)(i%11)/11;
    pl_tex src=reference_texture(gpu,4,4,input),target=reference_texture(gpu,axis==0?(down?2:8):4,axis==1?(down?2:8):4,NULL);
    pl_dispatch dp=pl_dispatch_create(g->log,gpu);assert(dp);pl_shader_obj lut=NULL;
    struct pl_sample_src source={.tex=src,.rect={0,0,4,4},.new_w=target->params.w,.new_h=target->params.h,.components=4};
    struct pl_filter_config cfg=*original;cfg.blur=down?2:1;
    pl_filter filter=pl_filter_generate(g->log,pl_filter_params(.config=cfg,.lut_entries=256,.row_stride_align=4));assert(filter);
    size_t count=(size_t)filter->row_stride*256;float *weights=calloc(count,sizeof(float));assert(weights);
    memcpy(weights,filter->weights,count*sizeof(float));
    if(filter->radius==filter->radius_zero)for(int row=0;row<256;row++){
        float *p=weights+row*filter->row_stride;const float *w=filter->weights+row*filter->row_stride;
        int i=0;for(;i<filter->row_size;i+=2){p[i]=w[i]+w[i+1];p[i+1]=w[i+1]/p[i];}
        for(;i<filter->row_stride;i++)p[i]=i>=4?p[i-4]:0;
    }
    float baseline[8*4*4],pixels[8*4*4];size_t bytes=(size_t)target->params.w*target->params.h*4*sizeof(float);
    for(int step=0;step<4;step++){
        bool fp32=step%2!=0;pl_shader sh=pl_dispatch_begin(dp);
        struct pl_sample_filter_params params={.filter=*original,.lut=&lut,.cb1_fp32_lut=fp32};
        assert(pl_shader_sample_ortho2(sh,&source,&params));
        const struct pl_shader_res *res=pl_shader_finalize(sh);assert(res);pl_tex texture=NULL;
        for(int i=0;i<res->num_descriptors;i++)if(res->descriptors[i].desc.type==PL_DESC_SAMPLED_TEX){
            pl_tex tex=res->descriptors[i].binding.object;if(tex->params.h==256)texture=tex;
        }
        assert(texture && texture->params.format->component_depth[0]==(fp32?32:16));
        float *actual=calloc(count,sizeof(float));assert(actual);reference_read(gpu,texture,0,0,filter->row_stride/4,256,actual);
        int unequal=0;for(size_t i=0;i<count;i++)unequal+=memcmp(&actual[i],&weights[i],sizeof(float))!=0;
        assert(fp32?unequal==0:unequal>0);free(actual);
        fprintf(stderr,"SCALER_CACHE axis=%d down=%d step=%d actual=%s unequal=%d/%zu\n",axis,down,step,texture->params.format->name,unequal,count);
        /* Finalization exposes descriptors but freezes that shader. Execute
         * another shader using the exact same retained LUT object. */
        pl_dispatch_abort(dp,&sh);sh=pl_dispatch_begin(dp);
        assert(pl_shader_sample_ortho2(sh,&source,&params));
        assert(pl_dispatch_finish(dp,pl_dispatch_params(.shader=&sh,.target=target)));
        reference_read(gpu,target,0,0,target->params.w,target->params.h,pixels);
        if(!step)memcpy(baseline,pixels,bytes);if(step==2)assert(!memcmp(baseline,pixels,bytes));
    }
    missing_format=true;pl_shader sh=pl_dispatch_begin(dp);
    struct pl_sample_filter_params params={.filter=*original,.lut=&lut,.cb1_fp32_lut=true};
    assert(!pl_shader_sample_ortho2(sh,&source,&params));pl_dispatch_abort(dp,&sh);missing_format=false;
    free(weights);pl_filter_free(&filter);pl_shader_obj_destroy(&lut);pl_dispatch_destroy(&dp);
    pl_tex_destroy(gpu,&src);pl_tex_destroy(gpu,&target);
}
static void transaction_capability(struct reference_gpu *g)
{
    pl_gpu gpu=g->gl->gpu;float pixels[64];for(int i=0;i<64;i++)pixels[i]=i%4==3?1:.4f;
    pl_tex input=reference_texture(gpu,4,4,pixels),final=reference_texture(gpu,3840,2160,NULL);
    struct pl_frame source=reference_frame(input,4,4);size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=1;AVDOVIDmData *l1=av_dovi_get_ext(m,0);l1->level=1;l1->l1.max_pq=3079;l1->l1.avg_pq=1667;
    struct dvbridge_policy policy=reference_policy();struct dvbridge_identity id={1,7,1};
    struct dvbridge_geometry geometry={4,4,0,0,2,8};
    struct dvbridge_renderer *r=dvbridge_renderer_create(gpu);assert(r);
    assert(dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&source,m,bytes,1,1,geometry));
    assert(dvbridge_render_hdr10_policy_resolve(r,final,false,true,12));
    assert(dvbridge_render_policy_commit(r,&id,final));
    struct dvbridge_hdr10_policy_output saved;assert(dvbridge_render_policy_committed(r,&saved));
    missing_format=true;assert(!pl_sample_filter_cb1_fp32_lut_format(gpu));id.picture++;
    assert(!dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&source,m,bytes,2,2,geometry));
    assert(!dvbridge_render_policy_output(r));struct dvbridge_hdr10_policy_output after;
    assert(dvbridge_render_policy_committed(r,&after));assert(after.identity.picture==saved.identity.picture && after.final_target==final);
    assert(glIsTexture(pl_opengl_unwrap(gpu,input,NULL,NULL,NULL)) && glIsTexture(pl_opengl_unwrap(gpu,final,NULL,NULL,NULL)));
    missing_format=false;
    /* Pinned renderer errors are sticky until the existing public reset;
     * reset intentionally invalidates committed engine availability. */
    dvbridge_renderer_reset(r);assert(!dvbridge_render_policy_committed(r,&after));
    assert(dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&source,m,bytes,2,2,geometry));
    dvbridge_renderer_destroy(r);assert(glIsTexture(pl_opengl_unwrap(gpu,final,NULL,NULL,NULL)));
    av_free(m);pl_tex_destroy(gpu,&input);pl_tex_destroy(gpu,&final);
    puts("PASS unavailable FP32 LINEAR LUT rejects Expert transaction, preserves commit/borrowed textures and recovers");
}
static void renderer_toggle(struct reference_gpu *g)
{
    pl_gpu gpu=g->gl->gpu;float input[64];for(int i=0;i<64;i++)input[i]=i%4==3?1:(float)(i%11)/11;
    pl_tex src=reference_texture(gpu,4,4,input),target=reference_texture(gpu,2,8,NULL);
    struct pl_frame source=reference_frame(src,4,4),out=reference_frame(target,2,8);
    source.repr=out.repr=pl_color_repr_rgb;source.color=out.color=(struct pl_color_space){.primaries=PL_COLOR_PRIM_BT_2020,.transfer=PL_COLOR_TRC_PQ,.hdr={.min_luma=PL_COLOR_HDR_BLACK,.max_luma=1000}};
    pl_renderer rr=pl_renderer_create(g->log,gpu);assert(rr);float baseline[64],actual[64];
    struct pl_render_params params=pl_render_default_params;params.min_fbo_precision=32;params.peak_detect_params=NULL;params.dither_params=NULL;params.sigmoid_params=NULL;
    for(int step=0;step<4;step++){
        params.cb1_fp32_scaler_lut=step%2!=0;assert(pl_render_image(rr,&source,&out,&params));
        int count=0;GLint saved;glGetIntegerv(GL_TEXTURE_BINDING_2D,&saved);
        for(GLuint id=1;id<1024;id++){
            if(!glIsTexture(id))continue;glBindTexture(GL_TEXTURE_2D,id);if(glGetError()!=GL_NO_ERROR)continue;
            GLint h,fmt;glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_HEIGHT,&h);glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_INTERNAL_FORMAT,&fmt);
            if(h!=256||(fmt!=GL_RGBA16F&&fmt!=GL_RGBA32F))continue;
            assert(fmt==(params.cb1_fp32_scaler_lut?GL_RGBA32F:GL_RGBA16F));count++;
        }
        glBindTexture(GL_TEXTURE_2D,saved);assert(count==2);
        reference_read(gpu,target,0,0,2,8,actual);if(!step)memcpy(baseline,actual,sizeof(actual));
        if(step==2)assert(!memcmp(baseline,actual,sizeof(actual)));
        fprintf(stderr,"RENDERER_SCALER_CACHE step=%d fp32=%d actual_textures=%d\n",step,params.cb1_fp32_scaler_lut,count);
    }
    pl_renderer_destroy(&rr);pl_tex_destroy(gpu,&src);pl_tex_destroy(gpu,&target);
}
int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    pl_fmt fmt=pl_sample_filter_cb1_fp32_lut_format(g.gl->gpu);
    assert(fmt && fmt->type==PL_FMT_FLOAT && fmt->num_components==4 && fmt->component_depth[0]==32);
    assert((fmt->caps&(PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR))==(PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR));
    assert(!pl_render_default_params.cb1_fp32_scaler_lut);
    for(int axis=0;axis<2;axis++){
        sampler_toggle(&g,&pl_filter_lanczos,axis,false);
        sampler_toggle(&g,&pl_filter_hermite,axis,false);
        sampler_toggle(&g,&pl_filter_hermite,axis,true);
    }
    renderer_toggle(&g);transaction_capability(&g);
    reference_gpu_destroy(&g);
    puts("PASS exact FP32 linear scaler-LUT capability");
}
