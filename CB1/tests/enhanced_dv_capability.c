/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include <GLES2/gl2ext.h>
#include <time.h>
int main(void)
{
    struct reference_gpu g=reference_gpu_create();
    GLint precision,range[2],ssbo,invocations;
    glGetShaderPrecisionFormat(GL_FRAGMENT_SHADER,GL_HIGH_FLOAT,range,&precision);
    glGetIntegerv(GL_MAX_SHADER_STORAGE_BUFFER_BINDINGS,&ssbo);
    glGetIntegerv(GL_MAX_COMPUTE_WORK_GROUP_INVOCATIONS,&invocations);
    fprintf(stderr,"actual legal fragment highp=%d range=%d/%d ssbo_bindings=%d invocations=%d EXT_buffer_storage=%d function=%d\n",
        precision,range[0],range[1],ssbo,invocations,
        pl_opengl_has_ext(g.gl,"GL_EXT_buffer_storage"),eglGetProcAddress("glBufferStorageEXT")!=NULL);
    GLint size,groups;GLint64 storage;
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_SIZE,0,&size);
    glGetIntegeri_v(GL_MAX_COMPUTE_WORK_GROUP_COUNT,0,&groups);
    glGetInteger64v(GL_MAX_SHADER_STORAGE_BLOCK_SIZE,&storage);
    fprintf(stderr,"actual libplacebo gl=%d.%d compute=%d max_ssbo_size=%zu native size=%d groups=%d storage=%lld query_error=%x\n",
        g.gl->major,g.gl->minor,g.gl->gpu->glsl.compute,(size_t)g.gl->gpu->limits.max_ssbo_size,size,groups,(long long)storage,glGetError());
    PFNGLBUFFERSTORAGEEXTPROC allocate=(PFNGLBUFFERSTORAGEEXTPROC)eglGetProcAddress("glBufferStorageEXT");
    if(allocate && pl_opengl_has_ext(g.gl,"GL_EXT_buffer_storage")){
        GLuint probe;glGenBuffers(1,&probe);glBindBuffer(GL_SHADER_STORAGE_BUFFER,probe);
        GLbitfield flags=GL_MAP_READ_BIT|GL_MAP_PERSISTENT_BIT_EXT|GL_MAP_COHERENT_BIT_EXT;
        const uint32_t zero[12]={0};GLenum before=glGetError();
        allocate(GL_SHADER_STORAGE_BUFFER,48,zero,flags);GLenum allocated=glGetError();
        void *map=allocated==GL_NO_ERROR?glMapBufferRange(GL_SHADER_STORAGE_BUFFER,0,48,flags):NULL;
        GLenum mapped=glGetError();
        fprintf(stderr,"actual native EXT scalar probe bytes=48 flags=%x before=%x allocation_error=%x map_nonnull=%d map_error=%x\n",flags,before,allocated,map!=NULL,mapped);
        if(map)assert(glUnmapBuffer(GL_SHADER_STORAGE_BUFFER));
        glBindBuffer(GL_SHADER_STORAGE_BUFFER,0);glDeleteBuffers(1,&probe);
        fprintf(stderr,"actual native EXT probe release_error=%x\n",glGetError());
    }
#ifndef DVBRIDGE_DV_POLICY_API
    assert(!"Enhanced DV asynchronous capability entry is missing");
#else
    struct dvbridge_retirement_owner *o=dvbridge_retirement_owner_create(g.gl->gpu);assert(o);
    struct dvbridge_renderer *r=dvbridge_renderer_create_with_owner(o);assert(r);
    size_t bytes;AVDOVIMetadata *m=task3_fixture(&bytes);
    m->num_ext_blocks=1;av_dovi_get_ext(m,0)->level=1;
    av_dovi_get_ext(m,0)->l1.max_pq=3079;av_dovi_get_ext(m,0)->l1.avg_pq=1667;
    pl_tex input=reference_texture(g.gl->gpu,2,2,(float[16]){.5,.5,.5,1,.5,.5,.5,1,.5,.5,.5,1,.5,.5,.5,1});
    struct pl_frame f=reference_frame(input,2,2);
    struct dvbridge_policy p=reference_policy();p.mode=DVBRIDGE_MODE_ENHANCED_DV;p.enhancement=DVBRIDGE_ENHANCEMENT_NATURAL;
    struct dvbridge_identity id={1,7,1};
    enum dvbridge_dv_policy_status s=dvbridge_render_dv_policy_prepare(r,&p,&id,&f,m,bytes,0,0,(struct dvbridge_geometry){2,2,0,0,2,2});
    fprintf(stderr,"actual engine capability outcome=%d\n",s);
    bool unavailable=s==DVBRIDGE_DV_UNSUPPORTED;
    assert(unavailable || s==DVBRIDGE_DV_READY);
    dvbridge_render_dv_policy_cancel(r);
    /* Test harness waits through callbacks only; runtime poll never blocks. */
    for(unsigned i=0;i<10000 && s!=DVBRIDGE_DV_IDLE && !unavailable;i++){
        s=dvbridge_render_dv_policy_poll(r);
        if(s==DVBRIDGE_DV_BUSY)nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(unavailable || s==DVBRIDGE_DV_IDLE);
    dvbridge_renderer_destroy(r);assert(dvbridge_retirement_owner_destroy(&o));
    pl_tex_destroy(g.gl->gpu,&input);av_free(m);reference_gpu_destroy(&g);
    if(unavailable){puts("UNSUPPORTED real required GPU capabilities; no GPU qualification");return 77;}
    puts("PASS actual required allocation/map/fence path, not physical GPU qualification");
#endif
}
