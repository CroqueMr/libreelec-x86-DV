/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "dvbridge_gl_pack.h"

static bool fail_sampler;
void tested_packer_destroy(struct dvbridge_gl_packer *p);
static void injected_samplers(GLsizei count, GLuint *samplers)
{
    if (fail_sampler) {
        assert(count == 1);
        samplers[0] = 0;
    } else {
        glGenSamplers(count, samplers);
    }
}
/* Compile the owning unit with a single external allocation failure. */
#define glGenSamplers injected_samplers
#define dvbridge_gl_packer_create tested_packer_create
#define dvbridge_gl_packer_destroy tested_packer_destroy
#define dvbridge_gl_pack tested_pack
#include "../src/dvbridge_gl_pack.c"
#undef glGenSamplers
#undef dvbridge_gl_packer_create
#undef dvbridge_gl_packer_destroy
#undef dvbridge_gl_pack

enum { WIDTH = 3840, HEIGHT = 2160, OUTPUT_HEIGHT = 8 };

static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    assert(f);
    assert(!fseek(f, 0, SEEK_END));
    long size = ftell(f);
    assert(size > 0 && size < 65536);
    rewind(f);
    char *text = calloc((size_t)size + 1, 1);
    assert(text && fread(text, 1, size, f) == (size_t)size);
    fclose(f);
    return text;
}

static GLuint shader(GLenum kind, const char *path)
{
    char *source = read_file(path);
    GLuint id = glCreateShader(kind);
    const char *p = source;
    glShaderSource(id, 1, &p, NULL);
    glCompileShader(id);
    GLint ok;
    glGetShaderiv(id, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[8192];
        glGetShaderInfoLog(id, sizeof(log), NULL, log);
        fprintf(stderr, "%s\n", log);
        exit(1);
    }
    free(source);
    return id;
}

static float luminance(const float *rgb)
{
    return rgb[0] * .2627f + rgb[1] * .6780f + rgb[2] * .0593f;
}

int main(int argc, char **argv)
{
    assert(argc == 3);
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    assert(eglInitialize(display, NULL, NULL));
    assert(eglBindAPI(EGL_OPENGL_ES_API));
    EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, 0x40,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
    EGLConfig config;
    EGLint count;
    assert(eglChooseConfig(display, attributes, &config, 1, &count) && count);
    EGLint surface_attributes[] = {EGL_WIDTH, WIDTH, EGL_HEIGHT, HEIGHT, EGL_NONE};
    EGLSurface surface = eglCreatePbufferSurface(display, config, surface_attributes);
    EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    assert(context != EGL_NO_CONTEXT && surface != EGL_NO_SURFACE);
    assert(eglMakeCurrent(display, surface, surface, context));
    printf("Renderer: %s; %s\n", glGetString(GL_RENDERER), glGetString(GL_VERSION));

    GLuint program = glCreateProgram();
    GLuint vertex = shader(GL_VERTEX_SHADER, argv[1]), fragment = shader(GL_FRAGMENT_SHADER, argv[2]);
    glAttachShader(program, vertex);
    glAttachShader(program, fragment);
    glLinkProgram(program);
    GLint linked;
    glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (!linked) {
        char log[8192];
        glGetProgramInfoLog(program, sizeof(log), NULL, log);
        fprintf(stderr, "%s\n", log);
        return 1;
    }
    glUseProgram(program);
    char *vs = read_file(argv[1]), *fs = read_file(argv[2]);
    fail_sampler = true;
    assert(!tested_packer_create(vs, fs));
    while (glGetError() != GL_NO_ERROR) {}
    fail_sampler = false;
    struct dvbridge_gl_packer *retry = tested_packer_create(vs, fs);
    assert(retry && retry->vao && glIsSampler(retry->sampler));
    glBindVertexArray(retry->vao);
    assert(glIsVertexArray(retry->vao));
    glBindVertexArray(0);
    tested_packer_destroy(retry);
    struct dvbridge_gl_packer *packer = dvbridge_gl_packer_create(vs, fs);
    free(vs);
    free(fs);
    assert(packer);
    float *pixels = calloc((size_t)WIDTH * HEIGHT * 4, sizeof(float));
    uint8_t *result = malloc(WIDTH * OUTPUT_HEIGHT * 4);
    assert(pixels && result);
    for (unsigned y = 0; y < HEIGHT; ++y)
        for (unsigned x = 0; x < WIDTH; ++x) {
            float *p = pixels + ((size_t)y * WIDTH + x) * 4;
            p[0] = ((x + y) % 5) * .25f;
            p[1] = ((x / 10 + y) % 5) * .25f;
            p[2] = ((x / 50 + y) % 5) * .25f;
            p[3] = 1;
        }
    GLuint texture;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, WIDTH, HEIGHT, 0, GL_RGBA, GL_FLOAT, pixels);
    glUniform1i(glGetUniformLocation(program, "pq_input"), 0);
    GLuint metadata[512];
    for (unsigned i = 0; i < 512; ++i) metadata[i] = (i * 37 + 19) & 255;
    glUniform4uiv(glGetUniformLocation(program, "metadata_words"), 128, metadata);
    glUniform1ui(glGetUniformLocation(program, "packet_count"), 4);
    glDisable(GL_DITHER);
    glDisable(GL_BLEND);
    glViewport(0, 0, WIDTH, OUTPUT_HEIGHT);
    unsigned mismatches = 0;
    for (unsigned flip = 0; flip < 2; ++flip) {
        // Real libplacebo interop can leave the texture's default sampler
        // mipmapped/incomplete. The packer must supply its own sampler.
        glBindTexture(GL_TEXTURE_2D, texture);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST_MIPMAP_LINEAR);
        glEnable(GL_BLEND);
        glEnable(GL_DITHER);
        glEnable(GL_SCISSOR_TEST);
        glScissor(0, 0, 1, 1);
        glColorMask(GL_FALSE, GL_TRUE, GL_FALSE, GL_TRUE);
        glViewport(3, 5, 13, 17);
        assert(!dvbridge_gl_pack(packer, texture, 0, WIDTH, HEIGHT, metadata, 5, flip));
        assert(dvbridge_gl_pack(packer, texture, 0, WIDTH, HEIGHT, metadata, 4, flip));
        GLint originalFilter;
        glGetTexParameteriv(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, &originalFilter);
        assert(originalFilter == GL_NEAREST_MIPMAP_LINEAR);
        assert(glIsEnabled(GL_BLEND) && glIsEnabled(GL_DITHER) && glIsEnabled(GL_SCISSOR_TEST));
        GLint restored[4];
        glGetIntegerv(GL_VIEWPORT, restored);
        assert(restored[0] == 3 && restored[1] == 5 && restored[2] == 13 && restored[3] == 17);
        GLboolean mask[4];
        glGetBooleanv(GL_COLOR_WRITEMASK, mask);
        assert(!mask[0] && mask[1] && !mask[2] && mask[3]);
        glReadPixels(0, 0, WIDTH, OUTPUT_HEIGHT, GL_RGBA, GL_UNSIGNED_BYTE, result);
        assert(glGetError() == GL_NO_ERROR);
        for (unsigned row = 0; row < OUTPUT_HEIGHT; ++row)
            for (unsigned x = 0; x < WIDTH; ++x) {
                unsigned y = flip ? HEIGHT - 1 - row : row;
                const float *a = pixels + ((size_t)y * WIDTH + (x & ~1u)) * 4;
                const float *b = a + 4;
                float ya = luminance(a), yb = luminance(b);
                unsigned luma = (unsigned)floorf(256.f + 3504.f * ((x & 1) ? yb : ya) + .5f);
                float cb = 2048.f + 3584.f * ((a[2] - ya) + (b[2] - yb)) / (2.f * 1.8814f);
                float cr = 2048.f + 3584.f * ((a[0] - ya) + (b[0] - yb)) / (2.f * 1.4746f);
                unsigned c = (unsigned)floorf(((x & 1) ? cr : cb) + .5f);
                unsigned index = y * WIDTH + x, packet = index / 3072;
                if (packet < 4) {
                    unsigned bit = index % 1024;
                    unsigned v = (metadata[packet * 128 + bit / 8] >> (7 - bit % 8)) & 1;
                    c = (c & 4094) | (v ^ (__builtin_parity(c >> 1) ^ __builtin_parity(luma)));
                }
                uint8_t expected[4] = {c >> 4, luma >> 4, (luma & 15) | ((c & 15) << 4), 255};
                for (unsigned k = 0; k < 4; ++k)
                    if (result[(row * WIDTH + x) * 4 + k] != expected[k]) {
                        if (mismatches < 8)
                            fprintf(stderr, "Mismatch flip=%u x=%u y=%u component=%u actual=%u expected=%u\n",
                                flip, x, y, k, result[(row * WIDTH + x) * 4 + k], expected[k]);
                        ++mismatches;
                    }
            }
    }
    printf("Compared %u pixels; mismatched bytes=%u\n", WIDTH * OUTPUT_HEIGHT * 2, mismatches);
    free(pixels);
    free(result);
    glDeleteTextures(1, &texture);
    dvbridge_gl_packer_destroy(packer);
    glDeleteProgram(program);
    glDeleteShader(vertex);
    glDeleteShader(fragment);
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context);
    eglDestroySurface(display, surface);
    eglTerminate(display);
    return mismatches ? 1 : 0;
}
