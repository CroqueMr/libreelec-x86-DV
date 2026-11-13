/* SPDX-License-Identifier: GPL-2.0-or-later */
#pragma once

/* Desktop OpenGL builds: the core names of what the GLES code reaches through extensions. */
#ifndef GL_GLEXT_PROTOTYPES
#define GL_GLEXT_PROTOTYPES 1
#endif
#include <GL/gl.h>
#include <GL/glext.h>

#ifndef GL_MAP_PERSISTENT_BIT_EXT
#define GL_MAP_PERSISTENT_BIT_EXT GL_MAP_PERSISTENT_BIT
#endif
#ifndef GL_MAP_COHERENT_BIT_EXT
#define GL_MAP_COHERENT_BIT_EXT GL_MAP_COHERENT_BIT
#endif
#ifndef GL_CLIENT_MAPPED_BUFFER_BARRIER_BIT_EXT
#define GL_CLIENT_MAPPED_BUFFER_BARRIER_BIT_EXT GL_CLIENT_MAPPED_BUFFER_BARRIER_BIT
#endif
typedef PFNGLBUFFERSTORAGEPROC PFNGLBUFFERSTORAGEEXTPROC;

/* Core profiles dropped GL_RED_BITS and friends and call the default colour buffer
 * GL_BACK_LEFT, so read the sizes and the encoding from the bound colour attachment. */
static inline void dvbridge_gl_color_bits(GLuint framebuffer, GLint bits[4], GLint *encoding)
{
    static const GLenum sizes[4] = {GL_FRAMEBUFFER_ATTACHMENT_RED_SIZE,
        GL_FRAMEBUFFER_ATTACHMENT_GREEN_SIZE, GL_FRAMEBUFFER_ATTACHMENT_BLUE_SIZE,
        GL_FRAMEBUFFER_ATTACHMENT_ALPHA_SIZE};
    const GLenum attachment = framebuffer ? GL_COLOR_ATTACHMENT0 : GL_BACK_LEFT;
    for (int i = 0; i < 4; ++i)
        glGetFramebufferAttachmentParameteriv(GL_FRAMEBUFFER, attachment, sizes[i], &bits[i]);
    glGetFramebufferAttachmentParameteriv(GL_FRAMEBUFFER, attachment,
        GL_FRAMEBUFFER_ATTACHMENT_COLOR_ENCODING, encoding);
    /* Mesa gives desktop default framebuffers sRGB formats; writes stay linear until
     * GL_FRAMEBUFFER_SRGB is enabled. */
    if (*encoding == GL_SRGB && !glIsEnabled(GL_FRAMEBUFFER_SRGB))
        *encoding = GL_LINEAR;
}
