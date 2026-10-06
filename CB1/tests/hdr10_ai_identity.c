/* SPDX-License-Identifier: MIT */
#include "reference_test.h"
#include "cb1_hdr10_extrema.h"
#include <GLES3/gl3.h>
#include <time.h>

static enum cb1_ai_status wait_result(struct cb1_hdr10_extrema *ctx,
    struct cb1_ai_identity id, struct cb1_hdr10_bounds *out)
{
    for (unsigned i=0; i<10000; ++i) {
        enum cb1_ai_status result=cb1_hdr10_extrema_poll(ctx,id,out);
        if (result!=CB1_AI_PENDING) return result;
        nanosleep(&(struct timespec){.tv_nsec=1000000},NULL);
    }
    assert(!"GPU result timeout");
    return CB1_AI_INVALID;
}

int main(void)
{
    struct reference_gpu gpu=reference_gpu_create();
    struct cb1_hdr10_extrema *ctx=cb1_hdr10_extrema_create(gpu.gl->gpu);
    assert(ctx);
    float pixel[]={.1f,.2f,.3f,1.f};
    pl_tex texture=reference_texture(gpu.gl->gpu,1,1,pixel);
    const struct cb1_ai_identity first={3,17,5}, next={3,18,5};
    struct cb1_hdr10_bounds out={11,13,17,19,23,29}, saved=out;
    cb1_hdr10_extrema_reset(ctx,3,5);
    GLuint external_buffer;
    glGenBuffers(1,&external_buffer);
    glBindBuffer(GL_PIXEL_PACK_BUFFER,external_buffer);
    glBufferData(GL_PIXEL_PACK_BUFFER,128,NULL,GL_STREAM_READ);
    glPixelStorei(GL_PACK_ALIGNMENT,8);
    glPixelStorei(GL_PACK_ROW_LENGTH,11);
    glPixelStorei(GL_PACK_SKIP_ROWS,2);
    glPixelStorei(GL_PACK_SKIP_PIXELS,3);
    assert(cb1_hdr10_extrema_submit(ctx,texture,first)==CB1_AI_PENDING);
    GLint value;
    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&value); assert((GLuint)value==external_buffer);
    glGetIntegerv(GL_PACK_ALIGNMENT,&value); assert(value==8);
    glGetIntegerv(GL_PACK_ROW_LENGTH,&value); assert(value==11);
    glGetIntegerv(GL_PACK_SKIP_ROWS,&value); assert(value==2);
    glGetIntegerv(GL_PACK_SKIP_PIXELS,&value); assert(value==3);
    assert(cb1_hdr10_extrema_poll(ctx,next,&out)==CB1_AI_INVALID);
    assert(!memcmp(&out,&saved,sizeof(out)));
    assert(wait_result(ctx,first,&out)==CB1_AI_READY);
    glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&value); assert((GLuint)value==external_buffer);
    glBindBuffer(GL_PIXEL_PACK_BUFFER,0);
    glPixelStorei(GL_PACK_ALIGNMENT,4);
    glPixelStorei(GL_PACK_ROW_LENGTH,0);
    glPixelStorei(GL_PACK_SKIP_ROWS,0);
    glPixelStorei(GL_PACK_SKIP_PIXELS,0);
    glDeleteBuffers(1,&external_buffer);
    out=saved;
    assert(cb1_hdr10_extrema_submit(ctx,texture,next)==CB1_AI_PENDING);
    cb1_hdr10_extrema_reset(ctx,4,5); /* Seek/new stream retires pending metadata. */
    assert(cb1_hdr10_extrema_poll(ctx,next,&out)==CB1_AI_INVALID);
    assert(cb1_hdr10_extrema_submit(ctx,texture,next)==CB1_AI_INVALID);
    assert(!memcmp(&out,&saved,sizeof(out)));
    const struct cb1_ai_identity sought={4,1,5}, revised={4,1,6};
    assert(cb1_hdr10_extrema_submit(ctx,texture,sought)==CB1_AI_PENDING);
    cb1_hdr10_extrema_reset(ctx,4,6); /* Live mode change keeps picture, changes revision. */
    assert(cb1_hdr10_extrema_poll(ctx,sought,&out)==CB1_AI_INVALID);
    assert(cb1_hdr10_extrema_submit(ctx,texture,sought)==CB1_AI_INVALID);
    assert(!memcmp(&out,&saved,sizeof(out)));
    assert(cb1_hdr10_extrema_submit(ctx,texture,revised)==CB1_AI_PENDING);
    pl_tex_destroy(gpu.gl->gpu,&texture);
    assert(wait_result(ctx,revised,&out)==CB1_AI_READY);
    assert(out.minimum==6554 && out.maximum==19660);
    cb1_hdr10_extrema_destroy(&ctx);
    reference_gpu_destroy(&gpu);
    puts("Pending image, stream and revision identity checks passed");
}
