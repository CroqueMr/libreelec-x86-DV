/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "dvbridge_placebo.h"
#include "dvbridge_render.h"
#include <libplacebo/opengl.h>
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static double st2084(double luminance)
{
    double v=pow(luminance/10000,2610.0/16384);
    return pow((3424.0/4096+(2413.0/128)*v)/(1+(2392.0/128)*v),2523.0/32);
}

int main(void)
{
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    const EGLint attributes[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
    const EGLint size[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE},version[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLConfig config;EGLint count;
    assert(eglChooseConfig(display,attributes,&config,1,&count) && count);
    EGLSurface surface=eglCreatePbufferSurface(display,config,size);
    EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,version);
    assert(eglMakeCurrent(display,surface,surface,context));
    pl_opengl gl=pl_opengl_create(NULL,pl_opengl_params(.egl_display=display,.egl_context=context,
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,.allow_software=true));assert(gl);
    struct dvbridge_renderer *renderer=dvbridge_renderer_create(gl->gpu);assert(renderer);
    const double nits[]={0,.0001,.001,.005,.01,.025,.05,.1,.25,.5,1,2,5,10,100,1000};
    float pixels[64];
    for(unsigned i=0;i<16;i++)for(unsigned c=0;c<4;c++)pixels[4*i+c]=c==3?1:st2084(nits[i]);
    pl_fmt format=pl_find_fmt(gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);assert(format);
    pl_tex texture=pl_tex_create(gl->gpu,pl_tex_params(.w=16,.h=1,.format=format,
        .sampleable=true,.renderable=true,.initial_data=pixels));assert(texture);
    struct pl_frame frame={.num_planes=1,.planes={{.texture=texture,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,16,1}};
    size_t bytes;AVDOVIMetadata *metadata=av_dovi_metadata_alloc(&bytes);assert(metadata);
    AVDOVIRpuDataHeader *header=av_dovi_get_header(metadata);
    header->disable_residual_flag=1;header->bl_bit_depth=header->el_bit_depth=10;header->coef_log2_denom=12;
    AVDOVIColorMetadata *color=av_dovi_get_color(metadata);
    color->signal_eotf=65535;color->source_min_pq=7;color->source_max_pq=3079;
    for(unsigned row=0;row<3;row++){
        color->ycc_to_rgb_offset[row]=(AVRational){0,1};
        for(unsigned col=0;col<3;col++)color->ycc_to_rgb_matrix[3*row+col]=
            color->rgb_to_lms_matrix[3*row+col]=(AVRational){row==col,1};
        AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(metadata)->curves[row];
        curve->num_pivots=2;curve->pivots[1]=1023;curve->mapping_idc[0]=AV_DOVI_MAPPING_POLYNOMIAL;
        curve->poly_order[0]=1;curve->poly_coef[0][1]=4096;
    }
    *av_dovi_get_ext(metadata,0)=(AVDOVIDmData){.level=1,.l1={.min_pq=0,.max_pq=3079,.avg_pq=1500}};
    *av_dovi_get_ext(metadata,2)=(AVDOVIDmData){.level=2,.l2={.target_max_pq=3079,
        .trim_slope=2048,.trim_offset=2048,.trim_power=2048,.trim_chroma_weight=2048,
        .trim_saturation_gain=2048,.ms_weight=-1}};
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={2500,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    unsigned minima[]={0,1,100,1000};
    for(unsigned trims=0;trims<2;trims++)for(unsigned i=0;i<4;i++){
        metadata->num_ext_blocks=2+trims;
        *av_dovi_get_ext(metadata,1)=(AVDOVIDmData){.level=6,
            .l6={.max_luminance=1000,.min_luminance=minima[i]}};
        void *saved=av_memdup(metadata,bytes);assert(saved);
        struct dvbridge_identity identity={1,1+4*trims+i,1};
        assert(dvbridge_render_hdr10_policy_rgb(renderer,&policy,&identity,&frame,metadata,bytes,0,0,
            (struct dvbridge_geometry){16,1,0,0,16,1}));
        GLuint output=pl_opengl_unwrap(gl->gpu,dvbridge_render_texture(renderer),NULL,NULL,NULL),fbo;
        assert(output);glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,output,0);
        assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
        float actual[64];glReadPixels(0,0,16,1,GL_RGBA,GL_FLOAT,actual);assert(glGetError()==GL_NO_ERROR);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
        for(unsigned sample=0;sample<16;sample++)for(unsigned channel=0;channel<3;channel++){
            double expected=sample?st2084(nits[sample]):0;
            if(fabs(actual[4*sample+channel]-expected)>5e-5)
                fprintf(stderr,"Expert black floor: mastering_min=%u trims=%u input_nits=%g expectedPQ=%.9f got=%.9f\n",
                    minima[i],trims,nits[sample],expected,actual[4*sample+channel]);
            assert(fabs(actual[4*sample+channel]-expected)<=5e-5);
        }
        assert(!memcmp(saved,metadata,bytes));av_free(saved);
        struct dvbridge_policy other=policy;other.mode=DVBRIDGE_MODE_ENHANCED_DV;
        struct dvbridge_color mapped;struct pl_color_space target;struct dvbridge_hdr10_metadata signal;
        assert(dvbridge_reference_map(&mapped,&target,&signal,&other,metadata,bytes,false));
        assert(fabs(mapped.color.hdr.min_luma-minima[i]/10000.0)<1e-8);
    }
    av_free(metadata);pl_tex_destroy(gl->gpu,&texture);dvbridge_renderer_destroy(renderer);pl_opengl_destroy(&gl);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);
    puts("PASS Expert preserves absolute-PQ near-black independently of L6 mastering minimum");
}
