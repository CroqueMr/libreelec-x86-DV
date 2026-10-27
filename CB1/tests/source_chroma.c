/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "dvbridge_gl_frame.h"
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <assert.h>
#include <stdio.h>

int main(void)
{
    EGLDisplay d=eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(d,NULL,NULL) && eglBindAPI(EGL_OPENGL_ES_API));
    EGLConfig config;EGLint count;
    const EGLint attributes[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
    const EGLint dimensions[]={EGL_WIDTH,1,EGL_HEIGHT,1,EGL_NONE};
    const EGLint version[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
    assert(eglChooseConfig(d,attributes,&config,1,&count) && count);
    EGLSurface surface=eglCreatePbufferSurface(d,config,dimensions);
    EGLContext context=eglCreateContext(d,config,EGL_NO_CONTEXT,version);
    assert(eglMakeCurrent(d,surface,surface,context));
    pl_opengl gl=pl_opengl_create(NULL,pl_opengl_params(.egl_display=d,.egl_context=context,
        .get_proc_addr=(pl_voidfunc_t (*)(const char *))eglGetProcAddress,.allow_software=true));assert(gl);
    const enum dvbridge_gl_layout layouts[]={DVBRIDGE_NV12,DVBRIDGE_YUV420P10,DVBRIDGE_YUV444P10,DVBRIDGE_Y416};
    const enum pl_chroma_location locations[]={PL_CHROMA_LEFT,PL_CHROMA_CENTER,PL_CHROMA_TOP_LEFT};
    for(unsigned layout=0;layout<4;layout++){
        GLuint textures[3];glGenTextures(3,textures);
        bool packed=layout==3,subsampled=layout<2;
        unsigned planes=packed?1:layout?3:2;
        struct dvbridge_gl_plane input[3]={0};
        for(unsigned p=0;p<planes;p++){
            int size=p && subsampled?4:8;
            GLenum format=packed?0x805B:layout?0x822A:p?GL_RG8:GL_R8;
            glBindTexture(GL_TEXTURE_2D,textures[p]);glTexStorage2D(GL_TEXTURE_2D,1,format,size,size);
            assert(glGetError()==GL_NO_ERROR);
            input[p]=(struct dvbridge_gl_plane){textures[p],size,size};
        }
        /* Both BL and EL use this import, each retaining its own siting. */
        struct dvbridge_gl_frame bl={0},el={0};
        assert(dvbridge_gl_frame_import(&bl,gl->gpu,layouts[layout],8,8,input));
        assert(dvbridge_gl_frame_import(&el,gl->gpu,layouts[layout],8,8,input));
        for(unsigned position=0;position<3;position++){
            dvbridge_gl_frame_set_chroma(&bl,locations[position]);
            dvbridge_gl_frame_set_chroma(&el,PL_CHROMA_TOP_LEFT);
            assert(bl.frame.repr.sys==PL_COLOR_SYSTEM_UNKNOWN);
            for(unsigned p=0;p<planes;p++){
                float x=packed?-.5f:p && subsampled && position!=1?-.5f:0;
                float y=p && subsampled && position==2?-.5f:0;
                assert(bl.frame.planes[p].shift_x==x && bl.frame.planes[p].shift_y==y);
                assert(el.frame.planes[p].shift_x==(packed || (p && subsampled)?-.5f:0));
                assert(el.frame.planes[p].shift_y==(p && subsampled?-.5f:0));
            }
        }
        dvbridge_gl_frame_release(&el);dvbridge_gl_frame_release(&bl);glDeleteTextures(3,textures);
    }
    pl_opengl_destroy(&gl);eglMakeCurrent(d,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT);
    eglDestroyContext(d,context);eglDestroySurface(d,surface);eglTerminate(d);
    puts("PASS actual BL/EL imports: LEFT/CENTER/TOPLEFT; Y416 and 4:4:4 preserved");
}
