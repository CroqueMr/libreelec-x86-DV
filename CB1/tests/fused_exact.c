/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Compare every transported byte, including metadata rows and L5 masks. */
#include <EGL/egl.h>
#include <GLES3/gl31.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include <libplacebo/opengl.h>
#include "dvbridge_render.h"
#include "dvbridge_gl_pack.h"

static char *read_file(const char *name)
{
    FILE *f=fopen(name,"rb"); assert(f);
    assert(!fseek(f,0,SEEK_END)); long n=ftell(f); rewind(f);
    char *s=calloc(n+1,1); assert(s && fread(s,1,n,f)==(size_t)n); fclose(f); return s;
}

int main(int argc,char **argv)
{
    assert(argc==3); setvbuf(stdout,NULL,_IONBF,0);
    EGLDisplay d=eglGetDisplay(EGL_DEFAULT_DISPLAY); assert(eglInitialize(d,NULL,NULL));
    assert(eglBindAPI(EGL_OPENGL_ES_API));
    EGLint attrs[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,0x40,
        EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};
    EGLConfig cfg; EGLint n; assert(eglChooseConfig(d,attrs,&cfg,1,&n)&&n);
    EGLint sa[]={EGL_WIDTH,3840,EGL_HEIGHT,2160,EGL_NONE},ca[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLSurface surface=eglCreatePbufferSurface(d,cfg,sa);
    EGLContext context=eglCreateContext(d,cfg,EGL_NO_CONTEXT,ca);
    assert(eglMakeCurrent(d,surface,surface,context));
    pl_log log=pl_log_create(PL_API_VER,pl_log_params(.log_cb=pl_log_simple,.log_level=PL_LOG_WARN));
    pl_opengl gl=pl_opengl_create(log,pl_opengl_params(
        .get_proc_addr=(pl_voidfunc_t(*)(const char*))eglGetProcAddress,
        .egl_display=d,.egl_context=context)); assert(gl);
    printf("GPU %s; subgroup size %d\n",glGetString(GL_RENDERER),gl->gpu->glsl.subgroup_size);
    printf("GL version: %s; subgroup extension: %d\n",glGetString(GL_VERSION),
           strstr((const char*)glGetString(GL_EXTENSIONS),"GL_KHR_shader_subgroup")!=NULL);
    GLint sgsize=0,sgstages=0,sgfeatures=0;
    glGetIntegerv(0x9532,&sgsize); glGetIntegerv(0x9533,&sgstages); glGetIntegerv(0x9534,&sgfeatures);
    printf("Subgroup raw: size=%d stages=%x features=%x error=%x\n",sgsize,sgstages,sgfeatures,glGetError());
    assert(sgsize>=4 && (sgfeatures&0x81)==0x81 && (sgstages&GL_FRAGMENT_SHADER_BIT));
    struct dvbridge_renderer *regular=dvbridge_renderer_create(gl->gpu);
    struct dvbridge_renderer *fused=dvbridge_renderer_create(gl->gpu); assert(regular&&fused);
    pl_tex output=pl_opengl_wrap(gl->gpu,pl_opengl_wrap_params(.width=3840,.height=2160)); assert(output);
    char *vs=read_file(argv[1]), *fs=read_file(argv[2]);
    struct dvbridge_gl_packer *packer=dvbridge_gl_packer_create(vs,fs); assert(packer); free(vs); free(fs);
    const size_t size=3840*2160*4;
    float *pixels=malloc(size*sizeof(float)); unsigned char *a=malloc(size),*b=malloc(size); assert(pixels&&a&&b);
    uint32_t seed=98137;
    for (size_t i=0;i<size;i++) { seed=1664525u*seed+1013904223u; pixels[i]=i%4==3?1.f:(seed>>8)/(float)0xffffff; }
    pl_fmt fmt=pl_find_fmt(gl->gpu,PL_FMT_FLOAT,4,32,32,PL_FMT_CAP_SAMPLEABLE); assert(fmt);
    pl_tex input=pl_tex_create(gl->gpu,pl_tex_params(.w=3840,.h=2160,.format=fmt,.sampleable=true,.initial_data=pixels)); assert(input);
    struct pl_frame frame={.num_planes=1,.planes={{.texture=input,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,3840,2160}};
    size_t bytes; AVDOVIMetadata *m=av_dovi_metadata_alloc(&bytes); assert(m);
    m->num_ext_blocks=2; av_dovi_get_ext(m,0)->level=1;
    AVDOVIDmData *l5=av_dovi_get_ext(m,1); l5->level=5;
    AVDOVIRpuDataHeader *h=av_dovi_get_header(m); h->disable_residual_flag=1;
    h->bl_bit_depth=h->el_bit_depth=10; h->coef_log2_denom=12;
    AVDOVIColorMetadata *color=av_dovi_get_color(m); color->signal_eotf=65535; color->source_max_pq=3079;
    for(int i=0;i<9;i++) { color->ycc_to_rgb_matrix[i]=(AVRational){i%4==0,1}; color->rgb_to_lms_matrix[i]=(AVRational){i%4==0,1}; }
    for(int c=0;c<3;c++) {
        color->ycc_to_rgb_offset[c]=(AVRational){0,1};
        AVDOVIReshapingCurve *curve=&av_dovi_get_mapping(m)->curves[c];
        curve->num_pivots=2; curve->pivots[1]=1023; curve->mapping_idc[0]=AV_DOVI_MAPPING_POLYNOMIAL;
        curve->poly_order[0]=1; curve->poly_coef[0][1]=4096;
    }
    struct dvbridge_geometry geometry={3840,2160,0,0,3840,2160};
    pl_fmt efmt=pl_find_fmt(gl->gpu,PL_FMT_UNORM,4,16,16,PL_FMT_CAP_SAMPLEABLE|PL_FMT_CAP_LINEAR); assert(efmt);
    const size_t esize=1920*1080*4; uint16_t *epixels=malloc(esize*sizeof(uint16_t)); assert(epixels);
    for(size_t i=0;i<esize;i++) { seed=1664525u*seed+1013904223u; epixels[i]=i%4==3?65535:(480+(seed%65))<<6; }
    pl_tex etex=pl_tex_create(gl->gpu,pl_tex_params(.w=1920,.h=1080,.format=efmt,.sampleable=true,.initial_data=epixels)); assert(etex);
    struct pl_frame el={.num_planes=1,.repr.bits={.sample_depth=16,.color_depth=10,.bit_shift=6},
        .planes={{.texture=etex,.components=4,.component_mapping={0,1,2,3}}},.crop={0,0,1920,1080}};
    AVDOVIDataMapping *mapping=av_dovi_get_mapping(m); mapping->nlq_method_idc=AV_DOVI_NLQ_LINEAR_DZ;
    for(int c=0;c<3;c++) { mapping->nlq[c].nlq_offset=512; mapping->nlq[c].linear_deadzone_slope=1; }
    unsigned failures=0;
    for(int fel=0;fel<2;fel++) for(int mask=0;mask<3;mask++) for(int flip=0;flip<2;flip++) {
        h->disable_residual_flag=!fel; frame.enhancement_layer=fel?&el:NULL;
        l5->l5.top_offset=mask==2?320:mask?37:0;
        l5->l5.bottom_offset=mask==2?320:mask?93:0;
        l5->l5.left_offset=mask==1?19:0;
        l5->l5.right_offset=mask==1?41:0;
        dvbridge_renderer_reset(regular); dvbridge_renderer_reset(fused);
        assert(dvbridge_render_rgb(regular,&frame,m,bytes,0,fel?0:NAN,geometry));
        unsigned count; const uint32_t *packets=dvbridge_packets(dvbridge_render_candidate(regular),&count);
        GLuint texture=pl_opengl_unwrap(gl->gpu,dvbridge_render_texture(regular),NULL,NULL,NULL);
        assert(dvbridge_gl_pack(packer,texture,0,3840,2160,packets,count,flip));
        glBindFramebuffer(GL_FRAMEBUFFER,0); glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,a);
        assert(glGetError()==GL_NO_ERROR);
        glEnable(GL_BLEND); glEnable(GL_DITHER); glEnable(GL_STENCIL_TEST);
        glColorMask(GL_FALSE,GL_TRUE,GL_FALSE,GL_FALSE);
        assert(dvbridge_render_packed(fused,&frame,m,bytes,0,fel?0:NAN,geometry,output,flip));
        assert(glIsEnabled(GL_BLEND) && glIsEnabled(GL_DITHER) && glIsEnabled(GL_STENCIL_TEST));
        GLboolean write_mask[4]; glGetBooleanv(GL_COLOR_WRITEMASK,write_mask);
        assert(!write_mask[0] && write_mask[1] && !write_mask[2] && !write_mask[3]);
        glDisable(GL_BLEND); glDisable(GL_STENCIL_TEST); glDisable(GL_DITHER);
        glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE);
        glBindFramebuffer(GL_FRAMEBUFFER,0); glReadPixels(0,0,3840,2160,GL_RGBA,GL_UNSIGNED_BYTE,b);
        assert(glGetError()==GL_NO_ERROR);
        unsigned mismatch=0; for(size_t i=0;i<size;i++) if(a[i]!=b[i]) { if(mismatch<3)printf("byte %zu: %u != %u\n",i,a[i],b[i]); mismatch++; }
        printf("fel=%d mask=%d flip=%d compared=%zu mismatched_bytes=%u\n",fel,mask,flip,size,mismatch);
        failures+=mismatch;
    }
    printf("TOTAL mismatched bytes: %u\n",failures);
    dvbridge_gl_packer_destroy(packer);
    dvbridge_renderer_destroy(regular); dvbridge_renderer_destroy(fused);
    pl_tex_destroy(gl->gpu,&input); pl_tex_destroy(gl->gpu,&etex); pl_tex_destroy(gl->gpu,&output);
    av_free(m); free(a); free(b); free(pixels); free(epixels);
    pl_opengl_destroy(&gl); pl_log_destroy(&log);
    eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(d,context); eglDestroySurface(d,surface); eglTerminate(d);
    return failures?1:0;
}
