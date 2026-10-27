/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "dvbridge_render.h"
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <libplacebo/opengl.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

struct fitting {pl_gpu gpu;pl_tex texture;unsigned bits,calls;};
static bool fit(void *priv,const struct pl_frame *image,const struct pl_frame *target,struct pl_frame *out)
{
    struct fitting *f=priv;f->calls++;
    pl_fmt format=pl_find_fmt(f->gpu,PL_FMT_FLOAT,4,f->bits,f->bits,
        PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);assert(format && format->component_depth[0]==f->bits);
    assert(pl_tex_recreate(f->gpu,&f->texture,pl_tex_params(
        .w=target->planes[0].texture->params.w,.h=target->planes[0].texture->params.h,
        .format=format,.renderable=true,.sampleable=true,.blit_dst=true)));
    pl_tex_clear(f->gpu,f->texture,(float[4]){.5,0,0,1});
    *out=*image;out->planes[0].texture=f->texture;out->crop=target->crop;return true;
}

int main(void)
{
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    EGLConfig config;EGLint count;
    const EGLint a[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
    const EGLint size[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE},version[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    assert(eglChooseConfig(display,a,&config,1,&count) && count);
    EGLSurface surface=eglCreatePbufferSurface(display,config,size);
    EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,version);
    assert(eglMakeCurrent(display,surface,surface,context));
    pl_opengl gl=pl_opengl_create(NULL,pl_opengl_params(.egl_display=display,.egl_context=context,
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,.allow_software=true));assert(gl);
    struct dvbridge_renderer *r=dvbridge_renderer_create(gl->gpu);assert(r);
    if(!dvbridge_renderer_supports_mode(r,DVBRIDGE_MODE_MASTER_REFERENCE)){
        puts("SKIP Master storage witness: exact GPU arithmetic unavailable");return 77;
    }
    size_t bytes;AVDOVIMetadata *m=av_dovi_metadata_alloc(&bytes);assert(m);
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m);
    h->disable_residual_flag=1;h->bl_bit_depth=h->el_bit_depth=10;h->vdr_bit_depth=12;h->coef_log2_denom=12;
    AVDOVIColorMetadata *c=av_dovi_get_color(m);
    c->signal_eotf=65535;c->signal_bit_depth=12;c->signal_full_range_flag=1;c->source_max_pq=3079;
    for(unsigned channel=0;channel<3;channel++){
        c->ycc_to_rgb_offset[channel]=(AVRational){1,channel?2:16};
        for(unsigned column=0;column<3;column++)c->ycc_to_rgb_matrix[3*channel+column]=
            c->rgb_to_lms_matrix[3*channel+column]=(AVRational){channel==column,1};
        AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(m)->curves[channel];
        curve->num_pivots=2;curve->pivots[1]=1023;curve->poly_order[0]=1;
        curve->mapping_idc[0]=AV_DOVI_MAPPING_POLYNOMIAL;curve->poly_coef[0][1]=4096;
    }
    m->num_ext_blocks=1;*av_dovi_get_ext(m,0)=(AVDOVIDmData){.level=1,.l1={.max_pq=3079,.avg_pq=1000}};
    void *saved=av_memdup(m,bytes);assert(saved);
    struct pl_frame source={.num_planes=2,.crop={0,0,64,36},
        .repr={.bits={.sample_depth=16,.color_depth=10,.bit_shift=6}}};
    for(unsigned p=0;p<2;p++){
        pl_fmt format=pl_find_fmt(gl->gpu,PL_FMT_UNORM,p?2:1,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_RENDERABLE);assert(format);
        source.planes[p]=(struct pl_plane){.components=p?2:1,.component_mapping={p,2},.shift_x=p?-.5f:0,
            .texture=pl_tex_create(gl->gpu,pl_tex_params(.w=p?32:64,.h=p?18:36,
                .format=format,.sampleable=true,.renderable=true,.blit_dst=true))};
        assert(source.planes[p].texture);pl_tex_clear(gl->gpu,source.planes[p].texture,(float[4]){.5,.5,0,1});
    }
    pl_tex target=pl_tex_create(gl->gpu,pl_tex_params(.w=1280,.h=720,
        .format=pl_find_named_fmt(gl->gpu,"rgba8"),.renderable=true));assert(target);
    struct fitting f={.gpu=gl->gpu,.bits=16};dvbridge_renderer_set_spatial_fit(r,fit,&f);
    struct dvbridge_geometry geometry={64,36,0,0,1280,720,1280,720};
    for(unsigned ipt=0;ipt<2;ipt++){
        f.bits=32;
        enum cb1_master_status (*render)(struct dvbridge_renderer*,const struct pl_frame*,const void*,size_t,double,double,
            struct dvbridge_geometry,pl_tex,bool,const struct dvbridge_native_overlay*)=
            ipt?dvbridge_render_master_reference_ipt:dvbridge_render_master_reference;
        assert(render(r,&source,m,bytes,1,NAN,geometry,target,false,NULL)==CB1_MASTER_READY);
        unsigned before=f.calls;f.bits=16;
        assert(render(r,&source,m,bytes,2,NAN,geometry,target,false,NULL)!=CB1_MASTER_READY);
        assert(f.calls>before && !memcmp(saved,m,bytes));
    }
    h->bl_video_full_range_flag=1;c->signal_color_space=2;c->ycc_to_rgb_offset[0]=(AVRational){0,1};
    dvbridge_renderer_set_optimized_dv(r,true);f.bits=16;
    assert(dvbridge_render_packed(r,&source,m,bytes,3,NAN,geometry,target,false));
    av_free(saved);av_free(m);dvbridge_renderer_destroy(r);pl_tex_destroy(gl->gpu,&f.texture);
    pl_tex_destroy(gl->gpu,&target);for(unsigned p=0;p<2;p++)pl_tex_destroy(gl->gpu,&source.planes[p].texture);
    pl_opengl_destroy(&gl);eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);
    puts("PASS real resized Masters reject16F; P5 Standard accepts16F");
}
