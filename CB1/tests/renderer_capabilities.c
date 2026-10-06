/* SPDX-License-Identifier: MIT */
#include "reference_test.h"

/* Require the public declaration even though the owning unit is included below. */
static bool (*const query)(struct dvbridge_renderer *, enum dvbridge_mode)=
    dvbridge_renderer_supports_mode;
extern bool dvbridge_renderer_supports_hdr10_ai(struct dvbridge_renderer *, enum dvbridge_mode);

/* Exercise the real renderer with only individual external capability facts
 * withheld. Including its unit follows the existing lifecycle test pattern. */
static bool no_storage;
static const char *missing_proc;
static enum pl_fmt_type missing_format;
static int missing_components;
static enum pl_fmt_caps missing_caps;
static GLenum low_limit;
static GLint64 storage_override;
static bool low_precision;
static bool low_range,old_gles,desktop_gl;
static pl_opengl capability_gl(pl_gpu gpu)
{
    pl_opengl gl=pl_opengl_get(gpu);
    if(!gl || !old_gles)return gl;
    static struct pl_opengl_t old;old=*gl;old.major=3;old.minor=0;return &old;
}
static const GLubyte *capability_string(GLenum name)
{ return desktop_gl && name==GL_VERSION?(const GLubyte *)"4.6":glGetString(name); }
static bool has_ext(pl_opengl gl,const char *name)
{ return !(no_storage && !strcmp(name,"GL_EXT_buffer_storage")) && pl_opengl_has_ext(gl,name); }
static __eglMustCastToProperFunctionPointerType proc(const char *name)
{ return missing_proc && !strcmp(name,missing_proc)?NULL:eglGetProcAddress(name); }
static pl_fmt format(pl_gpu gpu,enum pl_fmt_type type,int components,int depth,int host,enum pl_fmt_caps caps)
{ return (type==missing_format && components==missing_components) || (caps&missing_caps)?NULL:pl_find_fmt(gpu,type,components,depth,host,caps); }
static void integer(GLenum name,GLint *value)
{ glGetIntegerv(name,value);if(name==low_limit)*value=0; }
static void capability_indexed(GLenum name,GLuint index,GLint *value)
{ glGetIntegeri_v(name,index,value);if(name==low_limit)*value=0; }
static void integer64(GLenum name,GLint64 *value)
{ glGetInteger64v(name,value);if(name==low_limit)*value=0;if(name==GL_MAX_SHADER_STORAGE_BLOCK_SIZE && storage_override)*value=storage_override; }
static void capability_precision(GLenum shader,GLenum type,GLint *range,GLint *bits)
{ glGetShaderPrecisionFormat(shader,type,range,bits);if(low_precision)*bits=22;if(low_range)range[1]=126; }
static void no_buffers(GLsizei count,GLuint *buffers)
{ (void)count;(void)buffers;assert(!"capability query allocated analysis buffers"); }
static void no_readback(GLint x,GLint y,GLsizei w,GLsizei h,GLenum fmt,GLenum type,void *pixels)
{ (void)x;(void)y;(void)w;(void)h;(void)fmt;(void)type;(void)pixels;assert(!"capability query read pixels"); }
#define pl_opengl_has_ext has_ext
#define pl_opengl_get capability_gl
#define glGetString capability_string
#define eglGetProcAddress proc
#define pl_find_fmt format
#define glGetIntegerv integer
#define glGetIntegeri_v capability_indexed
#define glGetInteger64v integer64
#define glGetShaderPrecisionFormat capability_precision
#define glGenBuffers no_buffers
#define glReadPixels no_readback
#include "../src/dvbridge_render.c"
#undef glGetIntegerv
#undef glGenBuffers
#undef glReadPixels

static void unchanged(struct dvbridge_renderer *r,enum dvbridge_mode mode,bool expected)
{
    struct dvbridge_renderer before=*r;
    GLint buffer,program,texture;
    glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&buffer);
    glGetIntegerv(GL_CURRENT_PROGRAM,&program);
    glGetIntegerv(GL_ACTIVE_TEXTURE,&texture);
    assert(query(r,mode)==expected);
    assert(!memcmp(&before,r,sizeof(before)));
    GLint value;glGetIntegerv(GL_SHADER_STORAGE_BUFFER_BINDING,&value);assert(value==buffer);
    glGetIntegerv(GL_CURRENT_PROGRAM,&value);assert(value==program);
    glGetIntegerv(GL_ACTIVE_TEXTURE,&value);assert(value==texture);
    assert(glGetError()==GL_NO_ERROR);
}

int main(void)
{
    assert(!query(NULL,DVBRIDGE_MODE_STANDARD));
    struct reference_gpu g=reference_gpu_create();
    struct dvbridge_renderer *r=dvbridge_renderer_create(g.gl->gpu);assert(r);
    unchanged(r,DVBRIDGE_MODE_DISABLED,false);
    unchanged(r,(enum dvbridge_mode)-1,false);
    unchanged(r,(enum dvbridge_mode)99,false);
    unchanged(r,(enum dvbridge_mode)5,false);
    for(int mode=DVBRIDGE_MODE_STANDARD;mode<=DVBRIDGE_MODE_ENHANCED_DV;mode++)
        unchanged(r,mode,true);
    /* Both committed identities and a prepared transaction survive queries. */
    r->dv_has_committed=true;r->dv_committed.identity=(struct dvbridge_identity){11,12,13};
    r->policy_has_committed=true;r->policy_committed.identity=(struct dvbridge_identity){21,22,23};
    r->ready=true;r->policy_ready=true;
    no_storage=true;
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
#ifdef CB1_HAS_HDR10_AI
    assert(dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_STANDARD));
#endif
    unchanged(r,DVBRIDGE_MODE_STANDARD,true);
    unchanged(r,DVBRIDGE_MODE_HDR10_BASIC,true);
    unchanged(r,DVBRIDGE_MODE_HDR10_EXPERT,true);
    unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,true);
    no_storage=false;
#ifdef CB1_HAS_HDR10_AI
    storage_override=65537*4;
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_STANDARD));
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
    storage_override=(65537+512)*4;
    assert(dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_STANDARD));
    assert(dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
    storage_override=0;
#endif
    const GLenum limits[]={GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,GL_MAX_COMPUTE_WORK_GROUP_SIZE,
        GL_MAX_COMPUTE_WORK_GROUP_COUNT,GL_MAX_SHADER_STORAGE_BUFFER_BINDINGS,GL_MAX_SHADER_STORAGE_BLOCK_SIZE,
        GL_MAX_COMPUTE_SHARED_MEMORY_SIZE};
    for(unsigned i=0;i<sizeof(limits)/sizeof(*limits);i++){
        low_limit=limits[i];
        assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
        assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_STANDARD));
        unchanged(r,DVBRIDGE_MODE_STANDARD,true);unchanged(r,DVBRIDGE_MODE_HDR10_BASIC,true);
        unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,true);
    }
    low_limit=0;low_precision=true;unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,false);low_precision=false;
    low_range=true;unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,false);low_range=false;
    old_gles=true;unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,true);
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_STANDARD));
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));old_gles=false;
    desktop_gl=true;unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,false);desktop_gl=false;
    const char *functions[]={"glBufferStorageEXT","glClientWaitSync","glDeleteSync","glFenceSync",
        "glMapBufferRange","glDispatchCompute","glMemoryBarrier"};
    for(unsigned i=0;i<sizeof(functions)/sizeof(*functions);i++){
        missing_proc=functions[i];
        assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
        unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,i==0 || i>=4);
    }
    missing_proc=NULL;
    for(unsigned i=0;i<2;i++){
        missing_format=i?PL_FMT_FLOAT:PL_FMT_UNORM;missing_components=i?1:4;
        unchanged(r,DVBRIDGE_MODE_STANDARD,true);unchanged(r,DVBRIDGE_MODE_HDR10_BASIC,true);
        unchanged(r,DVBRIDGE_MODE_HDR10_EXPERT,false);
        unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,false);
        assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_STANDARD));
        assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
    }
    missing_format=PL_FMT_FLOAT;missing_components=4;
    for(int mode=DVBRIDGE_MODE_STANDARD;mode<=DVBRIDGE_MODE_ENHANCED_DV;mode++)unchanged(r,mode,false);
    missing_components=0;unchanged(r,DVBRIDGE_MODE_ENHANCED_DV,true);
    missing_caps=PL_FMT_CAP_HOST_READABLE;
    unchanged(r,DVBRIDGE_MODE_STANDARD,true);
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_STANDARD));
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
    missing_caps=0;
#ifdef CB1_HAS_HDR10_AI
    assert(dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
    assert(dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_STANDARD));
#else
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_ENHANCED_DV));
#endif
    assert(!dvbridge_renderer_supports_hdr10_ai(r,DVBRIDGE_MODE_HDR10_BASIC));
    dvbridge_renderer_destroy(r);reference_gpu_destroy(&g);
    puts("PASS mode-specific GPU requirements without prepare, allocation, readback or identity/state changes");
}
