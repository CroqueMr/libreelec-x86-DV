/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DVBRIDGE_GL_PACK_H
#define DVBRIDGE_GL_PACK_H
#include <stdbool.h>
#include <stdint.h>
struct dvbridge_gl_packer;
struct dvbridge_gl_packer *dvbridge_gl_packer_create(const char *vertex, const char *fragment);
void dvbridge_gl_packer_destroy(struct dvbridge_gl_packer *packer);
/* Current GLES3 context; PQ texture and destination match the validated raster.
 * Even width, packet capacity and viewport limits are required. Destination
 * must be linear RGB8/RGBA8 without multisampling; HDMI admission is separate. */
bool dvbridge_gl_pack(struct dvbridge_gl_packer *packer, unsigned pq_texture,
                     unsigned framebuffer, int width, int height,
                     const uint32_t packets[640], unsigned count, bool flip_y);
/* Patch only metadata-covered pixels from an already packed RGB8 texture.
 * The destination must already contain its full-raster copy, with matching flip. */
bool dvbridge_gl_patch(struct dvbridge_gl_packer *packer, unsigned packed_texture,
                      unsigned framebuffer, int width, int height,
                      const uint32_t packets[640], unsigned count, bool flip_y);
/* Requires EXT_shader_framebuffer_fetch_non_coherent. Exact RGB8 metadata only. */
bool dvbridge_gl_patch_inplace(struct dvbridge_gl_packer *packer,unsigned framebuffer,int width,int height,
    const uint32_t packets[640],unsigned count,bool flip_y);
#endif
