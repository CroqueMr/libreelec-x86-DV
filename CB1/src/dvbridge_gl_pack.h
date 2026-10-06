/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_GL_PACK_H
#define DVBRIDGE_GL_PACK_H
#include <stdbool.h>
#include <stdint.h>
struct dvbridge_gl_packer;
struct dvbridge_gl_packer *dvbridge_gl_packer_create(const char *vertex, const char *fragment);
void dvbridge_gl_packer_destroy(struct dvbridge_gl_packer *packer);
/* Current GLES3 context; PQ texture and destination must both be 3840x2160.
 * Destination must be linear RGB8/RGBA8, without multisampling. */
bool dvbridge_gl_pack(struct dvbridge_gl_packer *packer, unsigned pq_texture,
                     unsigned framebuffer, int width, int height,
                     const uint32_t packets[512], unsigned count, bool flip_y);
#endif
