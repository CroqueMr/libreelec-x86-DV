/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Exercise the real Expert-only tail, independently of its scalar P3 reference. */
#include <assert.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <libplacebo/opengl.h>
#include "cb1_hdr10_expert.h"
#include <libplacebo/dispatch.h>
#include <libplacebo/shaders/sampling.h>
#include <math.h>
#include <stdio.h>

int main(void)
{
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    const EGLint attrs[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
    const EGLint size[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE},version[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLConfig config;EGLint count;assert(eglChooseConfig(display,attrs,&config,1,&count) && count);
    EGLSurface surface=eglCreatePbufferSurface(display,config,size);
    EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,version);
    assert(eglMakeCurrent(display,surface,surface,context));
    pl_opengl gl=pl_opengl_create(NULL,pl_opengl_params(.egl_display=display,.egl_context=context,
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,.allow_software=true));assert(gl);
    pl_dispatch dispatch=pl_dispatch_create(NULL,gl->gpu);assert(dispatch);
    const float pixels[][4]={{0,0,0,1},{1,1,1,1},{.001,.001,.001,1},
        {4,1,.2,1},{.2,3,1,1},{.2,.4,4,1},{0,.2,1,1},{.001,.003,.008,1}};
    enum {N=sizeof(pixels)/sizeof(*pixels)};
    pl_fmt format=pl_find_fmt(gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);assert(format);
    pl_tex input=pl_tex_create(gl->gpu,pl_tex_params(.w=N,.h=1,.format=format,
        .sampleable=true,.renderable=true,.host_writable=true,.initial_data=pixels));assert(input);
    pl_tex output=pl_tex_create(gl->gpu,pl_tex_params(.w=N,.h=1,.format=format,
        .sampleable=true,.renderable=true));assert(output);
    /* Derived independently from BT.2020 primaries and D65, not from the shader. */
    const double weights[]={.2627002120112671,.6779980715188708,.0593017164698620};
    const unsigned words[][2]={{2048,2048},{2300,2800},{1800,1600}};
    double maximum=0;
    for(unsigned t=0;t<sizeof(words)/sizeof(*words);t++){
        struct dvbridge_creative_plan plan={.policy={.mode=DVBRIDGE_MODE_HDR10_EXPERT,
            .tv={10000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}},
            .codes={2048,2048,2048,words[t][0],words[t][1]}};
        pl_shader shader=pl_dispatch_begin(dispatch);
        assert(pl_shader_sample_direct(shader,pl_sample_src(.tex=input)) &&
            cb1_hdr10_expert_trim(shader,&plan,PL_COLOR_PRIM_BT_2020));
        assert(pl_dispatch_finish(dispatch,pl_dispatch_params(.shader=&shader,.target=output)));
        GLuint texture=pl_opengl_unwrap(gl->gpu,output,NULL,NULL,NULL),fbo;assert(texture);
        glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
        assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
        float actual[N][4];glReadPixels(0,0,N,1,GL_RGBA,GL_FLOAT,actual);assert(glGetError()==GL_NO_ERROR);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
        double chroma=words[t][0]/4096.0-.5,gain=words[t][1]/4096.0-.5;
        for(unsigned i=0;i<N;i++){
            double luma=0;for(unsigned c=0;c<3;c++)luma+=pixels[i][c]*weights[c];
            for(unsigned c=0;c<3;c++){
                double expected=pixels[i][c];
                if(expected>0 && gain!=0)expected*=pow((1+chroma)*expected/luma,gain);
                assert(isfinite(actual[i][c]));
                double error=fabs(actual[i][c]-expected);maximum=fmax(maximum,error);
                if(error>2e-6*fmax(1,expected))
                    fprintf(stderr,"Expert BT2020 luma: trim=%u pixel=%u channel=%u expected=%.9g actual=%.9g\n",t,i,c,expected,actual[i][c]);
                assert(error<=2e-6*fmax(1,expected));
            }
            assert(actual[i][3]==1);
        }
    }
    printf("PASS Expert BT2020 trim chroma: %u pixels, 3 controls, max linear error %.9g\n",N,maximum);
    /* The native mapper may leave components outside the target RGB volume.
     * Its pre-chroma domain is independent of slope. Luma trims already ran
     * in the native tone LUT and must not run a second time in this helper. */
    float boundary[N][4];
    for(unsigned i=0;i<N;i++){
        boundary[i][0]=1200.0/203;boundary[i][1]=200.0/203;
        boundary[i][2]=100.0/203;boundary[i][3]=1;
    }
    assert(pl_tex_upload(gl->gpu,pl_tex_transfer_params(.tex=input,.ptr=boundary)));
    double previous_green=0;
    for(unsigned slope=2048;slope<=2049;slope++){
        struct dvbridge_creative_plan plan={.policy={.mode=DVBRIDGE_MODE_HDR10_EXPERT,
            .tv={1000,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}},
            .codes={slope,2048,2048,2048,3072}};
        pl_shader shader=pl_dispatch_begin(dispatch);
        assert(pl_shader_sample_direct(shader,pl_sample_src(.tex=input)) &&
            cb1_hdr10_expert_trim(shader,&plan,PL_COLOR_PRIM_BT_2020));
        assert(pl_dispatch_finish(dispatch,pl_dispatch_params(.shader=&shader,.target=output)));
        GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,
            pl_opengl_unwrap(gl->gpu,output,NULL,NULL,NULL),0);
        float actual[N][4];glReadPixels(0,0,N,1,GL_RGBA,GL_FLOAT,actual);assert(glGetError()==GL_NO_ERROR);
        glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
        if(slope==2048){
            const double expected[]={1000,167.737575,70.524963};
            for(unsigned c=0;c<3;c++){
                double value=203.0*actual[0][c];
                if(fabs(value-expected[c])>=.001)
                    fprintf(stderr,"Expert neutral SOP domain channel=%u actual=%.9g expected=%.9g nits\n",c,value,expected[c]);
                assert(fabs(value-expected[c])<.001);
            }
            previous_green=203.0*actual[0][1];
        }else assert(203.0*actual[0][1]==previous_green);
    }
    puts("PASS chroma domain independent of slope; no duplicate luma trim");
    pl_tex_destroy(gl->gpu,&output);pl_tex_destroy(gl->gpu,&input);pl_dispatch_destroy(&dispatch);pl_opengl_destroy(&gl);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);
}
