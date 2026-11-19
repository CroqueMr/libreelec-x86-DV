/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cb1_hdr10_expert.h"
#include "dvbridge_render.h"
#include "hdr10_expert_fixture.h"
#include <libplacebo/opengl.h>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void read_pixels(pl_gpu gpu,pl_tex texture,float pixels[8])
{
    GLuint fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,
        pl_opengl_unwrap(gpu,texture,NULL,NULL,NULL),0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    glReadPixels(0,0,2,1,GL_RGBA,GL_FLOAT,pixels);assert(glGetError()==GL_NO_ERROR);
    glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);
}
static double pq(double nits)
{
    double x=pow(nits/10000,2610.0/16384);
    return pow((3424.0/4096+(2413.0/128)*x)/(1+(2392.0/128)*x),2523.0/32);
}
int main(void)
{
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    const EGLint attributes[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
    const EGLint size[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE},version[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLConfig config;EGLint count;assert(eglChooseConfig(display,attributes,&config,1,&count) && count);
    EGLSurface surface=eglCreatePbufferSurface(display,config,size);
    EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,version);
    assert(eglMakeCurrent(display,surface,surface,context));
    pl_opengl gl=pl_opengl_create(NULL,pl_opengl_params(.egl_display=display,.egl_context=context,
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,.allow_software=true));assert(gl);
    struct dvbridge_renderer *r=dvbridge_renderer_create(gl->gpu);assert(r);
    pl_fmt fmt=pl_find_fmt(gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_RENDERABLE|PL_FMT_CAP_SAMPLEABLE);assert(fmt);
    const float pixels[]={.9,.9,.9,1,.9,.9,.9,1,.9,.9,.9,1,.9,.9,.9,1};
    pl_tex input=pl_tex_create(gl->gpu,pl_tex_params(.w=2,.h=2,.format=fmt,.sampleable=true,.initial_data=pixels));
    pl_tex output=pl_tex_create(gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.renderable=true));assert(input && output);
    struct pl_frame frame={.num_planes=1,.planes={{.texture=input,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,2,2}};
    size_t bytes;AVDOVIMetadata *m=expert_fixture(&bytes,false);
    void *original=av_memdup(m,bytes);assert(original);
    struct dvbridge_policy policy={.revision=1,.mode=DVBRIDGE_MODE_HDR10_EXPERT,
        .tv={50,DVBRIDGE_PANEL_OLED,DVBRIDGE_GAMUT_BT2020}};
    struct dvbridge_identity id={1,1,1};
    const double peaks[]={50,600.1,1000,2000,10000};
    for(unsigned p=0;p<5;p++)for(unsigned bits=10;bits<=12;bits+=2)for(unsigned limited=0;limited<2;limited++){
        policy.tv.peak_nits=peaks[p];
        assert(dvbridge_render_hdr10_policy_direct(r,&policy,&id,&frame,m,bytes,0,0,
            (struct dvbridge_geometry){2,2,0,0,3840,2160},output,false,limited,bits));
        float actual[8];read_pixels(gl->gpu,output,actual);
        unsigned span=limited?219u<<(bits-8):(1u<<bits)-1,offset=limited?16u<<(bits-8):0;
        unsigned cap=floor(offset+span*pq(peaks[p]));
        for(unsigned c=0;c<8;c++)if(c%4!=3){
            unsigned code=lround(actual[c]*((1u<<bits)-1));
            assert(code>=offset && code<=cap);
        }
        id.picture++;
    }
    /* Same real RGB composition surface used by Kodi: film first, GUI later. */
    policy.tv.peak_nits=50;policy.expert_output_bits=10;
    assert(dvbridge_render_hdr10_policy_rgb(r,&policy,&id,&frame,m,bytes,0,0,
        (struct dvbridge_geometry){2,2,0,0,2,2}));
    const float gui[]={.8,.8,.8,1};
    glBindTexture(GL_TEXTURE_2D,pl_opengl_unwrap(gl->gpu,dvbridge_render_texture(r),NULL,NULL,NULL));
    glTexSubImage2D(GL_TEXTURE_2D,0,0,0,1,1,GL_RGBA,GL_FLOAT,gui);assert(glGetError()==GL_NO_ERROR);
    glBindTexture(GL_TEXTURE_2D,0);
    assert(dvbridge_render_hdr10_policy_resolve(r,output,false,false,10));
    float actual[8];read_pixels(gl->gpu,output,actual);
    for(unsigned c=0;c<3;c++){
        assert(lround(actual[c]*1023)==lround(.8*1023));
        assert(lround(actual[4+c]*1023)<=(long)floor(pq(50)*1023));
    }
    /* Render HDR10, both LLDV depths, then HDR10 again on an offscreen surface. */
    /* The packed test uses a known linear picture on the same renderer. */
    pl_tex linear=pl_tex_create(gl->gpu,pl_tex_params(.w=2,.h=2,.format=fmt,.sampleable=true,.initial_data=pixels));
    pl_fmt rgba8=pl_find_fmt(gl->gpu,PL_FMT_UNORM,4,8,8,PL_FMT_CAP_RENDERABLE);assert(rgba8);
    pl_tex carrier=pl_tex_create(gl->gpu,pl_tex_params(.w=2,.h=2,.format=rgba8,.renderable=true));
    assert(linear && carrier);
    pl_tex sdr_target=pl_tex_create(gl->gpu,pl_tex_params(.w=2,.h=2,.format=fmt,.renderable=true));
    assert(sdr_target);
    const struct dvbridge_policy sdr={.revision=policy.revision,.mode=DVBRIDGE_MODE_SDR};
    struct pl_frame sdr_frame=frame;sdr_frame.repr.alpha=PL_ALPHA_NONE;
    const struct dvbridge_geometry native={2,2,0,0,2,2,2,2};
    float sdr_before[8], sdr_after[8];
    id.picture++;
    assert(dvbridge_render_hdr10_policy_direct(r,&sdr,&id,&sdr_frame,m,bytes,0,0,native,sdr_target,false,true,10));
    read_pixels(gl->gpu,sdr_target,sdr_before);
    assert(dvbridge_render_policy_commit(r,&id,sdr_target));

    policy.tv.peak_nits=1000;policy.expert_output_limited=true;
    const struct dvbridge_geometry raster={2,2,0,0,3840,2160};
    float before[8], after[8];
    id.picture++;
    assert(dvbridge_render_hdr10_policy_direct(r,&policy,&id,&frame,m,bytes,0,0,raster,output,false,true,10));
    read_pixels(gl->gpu,output,before);
    assert(dvbridge_render_policy_commit(r,&id,output));

    assert(dvbridge_pack_player_led_422(r,&policy,linear,carrier,10,false));
    assert(dvbridge_pack_player_led_422(r,&policy,linear,carrier,12,false));
    assert(!dvbridge_render_candidate(r));

    id.picture++;
    assert(dvbridge_render_hdr10_policy_direct(r,&policy,&id,&frame,m,bytes,0,0,raster,output,false,true,10));
    read_pixels(gl->gpu,output,after);
    assert(!memcmp(before,after,sizeof(before)));
    assert(dvbridge_render_policy_commit(r,&id,output));
    id.picture++;
    assert(dvbridge_render_hdr10_policy_direct(r,&sdr,&id,&sdr_frame,m,bytes,0,0,native,sdr_target,false,true,10));
    read_pixels(gl->gpu,sdr_target,sdr_after);
    assert(!memcmp(sdr_before,sdr_after,sizeof(sdr_before)));
    assert(dvbridge_render_policy_commit(r,&id,sdr_target));
    pl_tex_destroy(gl->gpu,&sdr_target);
    pl_tex_destroy(gl->gpu,&carrier);pl_tex_destroy(gl->gpu,&linear);

    assert(!memcmp(m,original,bytes));
    av_free(original);av_free(m);dvbridge_renderer_destroy(r);
    pl_tex_destroy(gl->gpu,&input);pl_tex_destroy(gl->gpu,&output);pl_opengl_destroy(&gl);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);
    puts("PASS scaled 10/12-bit strict film ceilings and bright GUI preservation");
}
