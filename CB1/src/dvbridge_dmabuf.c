/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Import validated VAAPI DMA-BUF planes without copying decoded video to the CPU. */
#include "dvbridge_dmabuf.h"
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <GLES2/gl2ext.h>
#include <libavutil/hwcontext.h>
#include <libavutil/hwcontext_drm.h>
#include <libdrm/drm_fourcc.h>
#include <limits.h>
#include <string.h>

bool dvbridge_dmabuf_validate_p010(const AVDRMFrameDescriptor *desc, int width, int height)
{
    if (!desc || width < 1 || width > 4096 || height < 1 || height > 2304 ||
        desc->nb_layers != 2 || desc->nb_objects < 1 || desc->nb_objects > AV_DRM_MAX_PLANES)
        return false;
    for (int i = 0; i < 2; ++i) {
        const AVDRMLayerDescriptor *layer = &desc->layers[i];
        const AVDRMPlaneDescriptor *plane = &layer->planes[0];
        if (layer->nb_planes != 1 || layer->format != (i ? DRM_FORMAT_GR1616 : DRM_FORMAT_R16) ||
            plane->object_index < 0 || plane->object_index >= desc->nb_objects)
            return false;
        const AVDRMObjectDescriptor *object = &desc->objects[plane->object_index];
        uint64_t row_bytes = i ? ((width + 1) / 2) * 4 : width * 2;
        uint64_t rows = i ? (height + 1) / 2 : height;
        if (object->fd < 0 || plane->offset < 0 || plane->offset > INT_MAX ||
            plane->pitch <= 0 || plane->pitch > INT_MAX || (uint64_t)plane->pitch < row_bytes ||
            (uint64_t)plane->offset >= object->size)
            return false;
        if (object->format_modifier == DRM_FORMAT_MOD_LINEAR &&
            (uint64_t)plane->offset + (rows - 1) * plane->pitch + row_bytes > object->size)
            return false;
    }
    return true;
}

void dvbridge_dmabuf_release(struct dvbridge_dmabuf *frame)
{
    if (!frame)
        return;
    PFNEGLDESTROYIMAGEKHRPROC destroy = (void *)eglGetProcAddress("eglDestroyImageKHR");
    for (int i = 0; i < 2; ++i) {
        if (frame->planes[i].texture)
            glDeleteTextures(1, &frame->planes[i].texture);
        if (frame->images[i] && destroy)
            destroy(frame->display, frame->images[i]);
    }
    av_frame_free(&frame->mapping);
    memset(frame, 0, sizeof(*frame));
}

bool dvbridge_dmabuf_import(struct dvbridge_dmabuf *out, const AVFrame *source)
{
    if (!out || out->mapping || !source || source->format != AV_PIX_FMT_VAAPI ||
        !source->hw_frames_ctx || source->width < 1 || source->height < 1 ||
        source->width > 3840 || source->height > 2160)
        return false;
    PFNEGLCREATEIMAGEKHRPROC create = (void *)eglGetProcAddress("eglCreateImageKHR");
    PFNGLEGLIMAGETARGETTEXTURE2DOESPROC bind = (void *)eglGetProcAddress("glEGLImageTargetTexture2DOES");
    EGLDisplay display = eglGetCurrentDisplay();
    if (!create || !bind || display == EGL_NO_DISPLAY)
        return false;
    AVHWFramesContext *hw = (void *)source->hw_frames_ctx->data;
    if (hw->sw_format != AV_PIX_FMT_P010 || hw->width < source->width || hw->height < source->height)
        return false;
    struct dvbridge_dmabuf candidate = {.display = display, .layout = DVBRIDGE_P010};
    candidate.mapping = av_frame_alloc();
    if (!candidate.mapping)
        return false;
    candidate.mapping->format = AV_PIX_FMT_DRM_PRIME;
    if (av_hwframe_map(candidate.mapping, source, AV_HWFRAME_MAP_READ | AV_HWFRAME_MAP_DIRECT) < 0)
        goto fail;
    const AVDRMFrameDescriptor *desc = (void *)candidate.mapping->data[0];
    if (!dvbridge_dmabuf_validate_p010(desc, hw->width, hw->height))
        goto fail;
    const char *extensions = eglQueryString(display, EGL_EXTENSIONS);
    bool modifiers = extensions && strstr(extensions, "EGL_EXT_image_dma_buf_import_modifiers");
    for (int i = 0; i < 2; ++i) {
        const AVDRMLayerDescriptor *layer = &desc->layers[i];
        const AVDRMPlaneDescriptor *plane = &layer->planes[0];
        const AVDRMObjectDescriptor *object = &desc->objects[plane->object_index];
        int width = i ? (hw->width + 1) / 2 : hw->width;
        int height = i ? (hw->height + 1) / 2 : hw->height;
        if (object->format_modifier != DRM_FORMAT_MOD_INVALID &&
            object->format_modifier != DRM_FORMAT_MOD_LINEAR && !modifiers)
            goto fail;
        EGLint attrs[24] = {
            EGL_WIDTH, width, EGL_HEIGHT, height, EGL_LINUX_DRM_FOURCC_EXT, (EGLint)layer->format,
            EGL_DMA_BUF_PLANE0_FD_EXT, object->fd, EGL_DMA_BUF_PLANE0_OFFSET_EXT, (EGLint)plane->offset,
            EGL_DMA_BUF_PLANE0_PITCH_EXT, (EGLint)plane->pitch, EGL_NONE};
        if (modifiers && object->format_modifier != DRM_FORMAT_MOD_INVALID) {
            attrs[12] = EGL_DMA_BUF_PLANE0_MODIFIER_LO_EXT;
            attrs[13] = (EGLint)(object->format_modifier & UINT32_MAX);
            attrs[14] = EGL_DMA_BUF_PLANE0_MODIFIER_HI_EXT;
            attrs[15] = (EGLint)(object->format_modifier >> 32);
            attrs[16] = EGL_NONE;
        }
        candidate.images[i] = create(display, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, attrs);
        if (!candidate.images[i])
            goto fail;
        GLint previous;
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &previous);
        glGenTextures(1, &candidate.planes[i].texture);
        glBindTexture(GL_TEXTURE_2D, candidate.planes[i].texture);
        bind(GL_TEXTURE_2D, candidate.images[i]);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glBindTexture(GL_TEXTURE_2D, previous);
        if (glGetError() != GL_NO_ERROR)
            goto fail;
        candidate.planes[i].width = width;
        candidate.planes[i].height = height;
    }
    *out = candidate;
    return true;
fail:
    dvbridge_dmabuf_release(&candidate);
    return false;
}
