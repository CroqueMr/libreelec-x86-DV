/* SPDX-License-Identifier: MIT */
#include "dvbridge_gl_pack.h"
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct dvbridge_gl_packer *beta5_create(const char *,const char *);
void beta5_destroy(struct dvbridge_gl_packer *);
bool beta5_pack(struct dvbridge_gl_packer *,unsigned,unsigned,int,int,const uint32_t *,unsigned,bool);
bool beta5_patch(struct dvbridge_gl_packer *,unsigned,unsigned,int,int,const uint32_t *,unsigned,bool);
bool beta5_inplace(struct dvbridge_gl_packer *,unsigned,const uint32_t *,unsigned,bool);

enum { W=3840,H=2160 };
static uint32_t seed=0x68a542f1;
static uint32_t next(void){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;return seed;}
static uint64_t compared;
static uint64_t digest=UINT64_C(14695981039346656037);
static char *read_text(const char *path)
{
    FILE *file=fopen(path,"rb");assert(file);assert(!fseek(file,0,SEEK_END));
    long size=ftell(file);assert(size>0 && size<65536);rewind(file);
    char *text=calloc(size+1,1);assert(text && fread(text,1,size,file)==(size_t)size);
    assert(!fclose(file));return text;
}
static void compare(GLuint fbo[2],uint8_t *bytes[2])
{
    size_t size=(size_t)W*H*4;
    for(int i=0;i<2;i++){
        glBindFramebuffer(GL_FRAMEBUFFER,fbo[i]);glReadPixels(0,0,W,H,GL_RGBA,GL_UNSIGNED_BYTE,bytes[i]);
        assert(glGetError()==GL_NO_ERROR);
    }
    if(memcmp(bytes[0],bytes[1],size)){
        for(size_t i=0;i<size;i++)if(bytes[0][i]!=bytes[1][i]){
            fprintf(stderr,"Different transport byte %zu: %u != %u\n",i,bytes[0][i],bytes[1][i]);break;
        }
        abort();
    }
    for(size_t i=0;i<size;i++)digest=(digest^bytes[0][i])*UINT64_C(1099511628211);
    compared+=size;
}
int main(int argc,char **argv)
{
    assert(argc==5);
    EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);assert(eglInitialize(display,NULL,NULL));
    assert(eglBindAPI(EGL_OPENGL_ES_API));
    EGLint attrs[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,0x40,EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_NONE};
    EGLConfig config;EGLint count;assert(eglChooseConfig(display,attrs,&config,1,&count) && count);
    EGLint surface_attrs[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE},context_attrs[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    EGLSurface surface=eglCreatePbufferSurface(display,config,surface_attrs);
    EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,context_attrs);
    assert(surface!=EGL_NO_SURFACE && context!=EGL_NO_CONTEXT && eglMakeCurrent(display,surface,surface,context));
    const char *renderer=(const char *)glGetString(GL_RENDERER);assert(strstr(renderer,"llvmpipe"));
    char *old_vertex=read_text(argv[1]),*old_fragment=read_text(argv[2]);
    char *vertex=read_text(argv[3]),*fragment=read_text(argv[4]);
    struct dvbridge_gl_packer *old=beta5_create(old_vertex,old_fragment);
    struct dvbridge_gl_packer *candidate=dvbridge_gl_packer_create(vertex,fragment);assert(old && candidate);
    free(old_vertex);free(old_fragment);free(vertex);free(fragment);
    GLuint input,packed,targets[2],fbo[2];glGenTextures(1,&input);glGenTextures(1,&packed);
    glGenTextures(2,targets);glGenFramebuffers(2,fbo);
    glBindTexture(GL_TEXTURE_2D,input);glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA32F,W,H);
    glBindTexture(GL_TEXTURE_2D,packed);glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA8,W,H);
    for(int i=0;i<2;i++){
        glBindTexture(GL_TEXTURE_2D,targets[i]);glTexStorage2D(GL_TEXTURE_2D,1,GL_RGBA8,W,H);
        glBindFramebuffer(GL_FRAMEBUFFER,fbo[i]);
        glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,targets[i],0);
        assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
    }
    float *pixels=malloc((size_t)W*H*4*sizeof(float));
    uint8_t *bytes[2]={malloc((size_t)W*H*4),malloc((size_t)W*H*4)};assert(pixels && bytes[0] && bytes[1]);
    bool inplace=strstr((const char *)glGetString(GL_EXTENSIONS),"GL_EXT_shader_framebuffer_fetch_non_coherent")!=NULL;
    for(unsigned test=0;test<12;test++){
        unsigned pattern=test/2;
        for(size_t i=0;i<(size_t)W*H;i++){
            for(unsigned channel=0;channel<3;channel++){
                float value;
                switch(pattern){
                case 0:value=(i>>channel)&1;break;
                case 1:value=((i+channel*131)%4096)/4095.0f;break;
                case 2:value=(next()&0xffffff)/16777215.0f;break;
                case 3:value=(next()&0xffffff)/13421772.0f-.125f;break;
                case 4:value=(((i*31+channel*17)%4096)+.5f)/4096;break;
                default:value=(next()&0xffff)/65535000.0f;break;
                }
                pixels[i*4+channel]=value;
            }
            pixels[i*4+3]=1;
        }
        glBindTexture(GL_TEXTURE_2D,input);glTexSubImage2D(GL_TEXTURE_2D,0,0,0,W,H,GL_RGBA,GL_FLOAT,pixels);
        uint32_t metadata[640];for(unsigned i=0;i<640;i++)metadata[i]=next()&255;
        unsigned packets=1+test%5;bool flip=test&1;
        assert(beta5_pack(old,input,fbo[0],W,H,metadata,packets,flip));
        assert(dvbridge_gl_pack(candidate,input,fbo[1],W,H,metadata,packets,flip));
        compare(fbo,bytes);
        glBindFramebuffer(GL_FRAMEBUFFER,fbo[0]);glBindTexture(GL_TEXTURE_2D,packed);
        glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,W,H);
        for(unsigned i=0;i<640;i++)metadata[i]=next()&255;
        assert(beta5_patch(old,packed,fbo[0],W,H,metadata,packets,flip));
        assert(dvbridge_gl_patch(candidate,packed,fbo[1],W,H,metadata,packets,flip));
        compare(fbo,bytes);
        if(inplace){
            for(unsigned i=0;i<640;i++)metadata[i]=next()&255;
            assert(beta5_inplace(old,fbo[0],metadata,packets,flip));
            assert(dvbridge_gl_patch_inplace(candidate,fbo[1],metadata,packets,flip));
            compare(fbo,bytes);
        }
    }
    printf("{\"renderer\":\"%s\",\"cases\":12,\"inplace\":%s,\"bytes_compared\":%llu,\"digest\":\"%016llx\",\"exact\":true}\n",
        renderer,inplace?"true":"false",(unsigned long long)compared,(unsigned long long)digest);
    beta5_destroy(old);dvbridge_gl_packer_destroy(candidate);
    glDeleteTextures(1,&input);glDeleteTextures(1,&packed);glDeleteTextures(2,targets);glDeleteFramebuffers(2,fbo);
    free(pixels);free(bytes[0]);free(bytes[1]);
    eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);return 0;
}
