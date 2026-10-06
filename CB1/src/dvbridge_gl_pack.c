/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Pack transport bytes with isolated GL state; never apply ordinary RGB color processing. */
#include "dvbridge_gl_pack.h"
#include <GLES3/gl3.h>
#include <stdio.h>
#include <stdlib.h>

struct dvbridge_gl_packer {
    GLuint program, vao, sampler;
    GLint input, words, count, flip;
};

static GLuint compile(GLenum type, const char *source)
{
    if (!source)
        return 0;
    GLuint shader = glCreateShader(type);
    glShaderSource(shader, 1, &source, NULL);
    glCompileShader(shader);
    GLint ok;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetShaderInfoLog(shader, sizeof(log), NULL, log);
        fprintf(stderr, "DV transport shader: %s\n", log);
        glDeleteShader(shader);
        return 0;
    }
    return shader;
}

struct dvbridge_gl_packer *dvbridge_gl_packer_create(const char *vertex, const char *fragment)
{
    GLuint vs = compile(GL_VERTEX_SHADER, vertex), fs = compile(GL_FRAGMENT_SHADER, fragment);
    if (!vs || !fs) {
        glDeleteShader(vs);
        glDeleteShader(fs);
        return NULL;
    }
    struct dvbridge_gl_packer *p = calloc(1, sizeof(*p));
    if (!p) {
        glDeleteShader(vs);
        glDeleteShader(fs);
        return NULL;
    }
    p->program = glCreateProgram();
    glAttachShader(p->program, vs);
    glAttachShader(p->program, fs);
    glLinkProgram(p->program);
    glDeleteShader(vs);
    glDeleteShader(fs);
    GLint linked;
    glGetProgramiv(p->program, GL_LINK_STATUS, &linked);
    p->input = glGetUniformLocation(p->program, "pq_input");
    p->words = glGetUniformLocation(p->program, "metadata_words");
    p->count = glGetUniformLocation(p->program, "packet_count");
    p->flip = glGetUniformLocation(p->program, "flip_y");
    if (!linked || p->input < 0 || p->words < 0 || p->count < 0 || p->flip < 0) {
        dvbridge_gl_packer_destroy(p);
        return NULL;
    }
    glGenVertexArrays(1, &p->vao);
    glGenSamplers(1, &p->sampler);
    glSamplerParameteri(p->sampler, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glSamplerParameteri(p->sampler, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glSamplerParameteri(p->sampler, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glSamplerParameteri(p->sampler, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    if (!p->vao || !p->sampler || glGetError() != GL_NO_ERROR) {
        dvbridge_gl_packer_destroy(p);
        return NULL;
    }
    return p;
}

void dvbridge_gl_packer_destroy(struct dvbridge_gl_packer *p)
{
    if (!p)
        return;
    glDeleteVertexArrays(1, &p->vao);
    glDeleteSamplers(1, &p->sampler);
    glDeleteProgram(p->program);
    free(p);
}

bool dvbridge_gl_pack(struct dvbridge_gl_packer *p, unsigned texture, unsigned framebuffer,
                     int width, int height, const uint32_t packets[512], unsigned count, bool flip)
{
    if (!p || !texture || !packets || !count || count > 4 || width != 3840 || height != 2160)
        return false;
    for (unsigned i = 0; i < count * 128; ++i)
        if (packets[i] > 255)
            return false;
    if (glGetError() != GL_NO_ERROR)
        return false;
    GLint program, vao, draw, read, viewport[4], active, binding, sampler;
    GLboolean mask[4];
    glGetIntegerv(GL_CURRENT_PROGRAM, &program);
    glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &vao);
    glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &draw);
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &read);
    glGetIntegerv(GL_VIEWPORT, viewport);
    glGetIntegerv(GL_ACTIVE_TEXTURE, &active);
    glGetBooleanv(GL_COLOR_WRITEMASK, mask);
    glActiveTexture(GL_TEXTURE0);
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &binding);
    glGetIntegerv(GL_SAMPLER_BINDING, &sampler);
    const GLenum caps[] = {GL_BLEND, GL_DEPTH_TEST, GL_STENCIL_TEST, GL_SCISSOR_TEST,
        GL_DITHER, GL_CULL_FACE, GL_RASTERIZER_DISCARD, GL_SAMPLE_ALPHA_TO_COVERAGE,
        GL_SAMPLE_COVERAGE};
    GLboolean enabled[sizeof(caps) / sizeof(*caps)];
    for (unsigned i = 0; i < sizeof(caps) / sizeof(*caps); ++i) {
        enabled[i] = glIsEnabled(caps[i]);
        glDisable(caps[i]);
    }
    bool ok = false;
    glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
    GLint red, green, blue, samples, encoding;
    glGetIntegerv(GL_RED_BITS, &red);
    glGetIntegerv(GL_GREEN_BITS, &green);
    glGetIntegerv(GL_BLUE_BITS, &blue);
    glGetIntegerv(GL_SAMPLES, &samples);
    glGetFramebufferAttachmentParameteriv(GL_FRAMEBUFFER,
        framebuffer ? GL_COLOR_ATTACHMENT0 : GL_BACK,
        GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING, &encoding);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE ||
        red != 8 || green != 8 || blue != 8 || samples > 1 || encoding != GL_LINEAR)
        goto restore;
    glViewport(0, 0, width, height);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glUseProgram(p->program);
    glBindVertexArray(p->vao);
    // libplacebo-owned textures use sampler objects and need not have usable
    // default texture filtering (e.g. mipmaps may be absent). Own our exact
    // non-mipmapped sampler without mutating the borrowed texture's state.
    glBindSampler(0, p->sampler);
    glBindTexture(GL_TEXTURE_2D, texture);
    glUniform1i(p->input, 0);
    glUniform4uiv(p->words, 128, packets);
    glUniform1ui(p->count, count);
    glUniform1ui(p->flip, flip);
    glDrawArrays(GL_TRIANGLES, 0, 3);
    ok = glGetError() == GL_NO_ERROR;
restore:
    glBindTexture(GL_TEXTURE_2D, binding);
    glBindSampler(0, sampler);
    glActiveTexture(active);
    glBindVertexArray(vao);
    glUseProgram(program);
    glBindFramebuffer(GL_DRAW_FRAMEBUFFER, draw);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, read);
    glViewport(viewport[0], viewport[1], viewport[2], viewport[3]);
    glColorMask(mask[0], mask[1], mask[2], mask[3]);
    for (unsigned i = 0; i < sizeof(caps) / sizeof(*caps); ++i)
        if (enabled[i]) glEnable(caps[i]);
    return ok && glGetError() == GL_NO_ERROR;
}
