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
