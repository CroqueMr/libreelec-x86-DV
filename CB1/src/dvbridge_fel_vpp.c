/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_fel_vpp.h"
#include <limits.h>
#include <stdlib.h>
#include <unistd.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <GLES2/gl2ext.h>
#include <drm_fourcc.h>
#include <libavutil/hwcontext.h>
#include <libavutil/hwcontext_vaapi.h>
#include <libavutil/log.h>
#include <va/va_drmcommon.h>
#include <va/va_vpp.h>

struct vpp_slot {
    struct dvbridge_fel_vpp_image image;
    VASurfaceID surface;
    EGLImageKHR egl_image;
    bool leased;
};
struct dvbridge_fel_vpp {
    AVBufferRef *device;
    VADisplay va;
    VAConfigID config;
    VAContextID context;
    EGLDisplay egl;
    EGLContext gl_context;
    int width, height;
    bool failed;
    struct vpp_slot slots[2];
};

static bool import_surface(struct dvbridge_fel_vpp *vpp, struct vpp_slot *slot)
{
    VADRMPRIMESurfaceDescriptor d = {0};
    if (vaExportSurfaceHandle(vpp->va, slot->surface, VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2,
        VA_EXPORT_SURFACE_READ_ONLY | VA_EXPORT_SURFACE_COMPOSED_LAYERS, &d) != VA_STATUS_SUCCESS)
        return false;
    bool ok = false;
    av_log(NULL, AV_LOG_DEBUG, "CB1 FEL VPP export: fourcc=%u layers=%u objects=%u size=%ux%u pitch=%u bytes=%u\n",
        d.fourcc, d.num_layers, d.num_objects, d.width, d.height, d.layers[0].pitch[0], d.objects[0].size);
    if (d.fourcc != VA_FOURCC_Y416 || d.num_layers != 1 || d.layers[0].num_planes != 1 ||
        !d.num_objects || d.num_objects > 4 || d.width != (unsigned)vpp->width ||
        d.height != (unsigned)vpp->height)
        goto done;
    unsigned object = d.layers[0].object_index[0];
    if (object >= d.num_objects || d.objects[object].fd < 0 ||
        d.layers[0].pitch[0] < (unsigned)vpp->width * 8 ||
        d.layers[0].pitch[0] > INT_MAX || d.layers[0].offset[0] > INT_MAX ||
        (uint64_t)d.layers[0].offset[0] + (uint64_t)d.layers[0].pitch[0] * vpp->height > d.objects[object].size)
        goto done;
    const uint64_t modifier = d.objects[object].drm_format_modifier;
    /* Y416 stores U,Y,V,A words. Import the same bytes as RGBA16 UNORM. */
    EGLint attrs[] = {EGL_WIDTH, vpp->width, EGL_HEIGHT, vpp->height,
        EGL_LINUX_DRM_FOURCC_EXT, DRM_FORMAT_ABGR16161616,
        EGL_DMA_BUF_PLANE0_FD_EXT, d.objects[object].fd,
        EGL_DMA_BUF_PLANE0_OFFSET_EXT, (EGLint)d.layers[0].offset[0],
        EGL_DMA_BUF_PLANE0_PITCH_EXT, (EGLint)d.layers[0].pitch[0],
        EGL_DMA_BUF_PLANE0_MODIFIER_LO_EXT, (EGLint)(uint32_t)modifier,
        EGL_DMA_BUF_PLANE0_MODIFIER_HI_EXT, (EGLint)(uint32_t)(modifier >> 32), EGL_NONE};
    PFNEGLCREATEIMAGEKHRPROC create = (void *)eglGetProcAddress("eglCreateImageKHR");
    PFNGLEGLIMAGETARGETTEXTURE2DOESPROC bind = (void *)eglGetProcAddress("glEGLImageTargetTexture2DOES");
    if (!create || !bind)
        goto done;
    slot->egl_image = create(vpp->egl, EGL_NO_CONTEXT, EGL_LINUX_DMA_BUF_EXT, NULL, attrs);
    if (!slot->egl_image)
        goto done;
    GLint previous;
    glGetIntegerv(GL_TEXTURE_BINDING_2D, &previous);
    glGenTextures(1, &slot->image.plane.texture);
    glBindTexture(GL_TEXTURE_2D, slot->image.plane.texture);
    bind(GL_TEXTURE_2D, slot->egl_image);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    ok = glGetError() == GL_NO_ERROR;
    glBindTexture(GL_TEXTURE_2D, previous);
    slot->image.width = slot->image.plane.width = vpp->width;
    slot->image.height = slot->image.plane.height = vpp->height;
done:
    for (unsigned i = 0; i < d.num_objects && i < 4; ++i)
        if (d.objects[i].fd >= 0) close(d.objects[i].fd);
    return ok;
}

bool dvbridge_fel_vpp_destroy(struct dvbridge_fel_vpp **ptr)
{
    if (!ptr || !*ptr) return true;
    struct dvbridge_fel_vpp *vpp = *ptr;
    for (unsigned i = 0; i < 2; ++i)
        if (vpp->slots[i].leased) return false;
    PFNEGLDESTROYIMAGEKHRPROC destroy = (void *)eglGetProcAddress("eglDestroyImageKHR");
    for (unsigned i = 0; i < 2; ++i) {
        struct vpp_slot *slot = &vpp->slots[i];
        if (slot->image.plane.texture) glDeleteTextures(1, &slot->image.plane.texture);
        if (slot->egl_image && destroy) destroy(vpp->egl, slot->egl_image);
        if (slot->surface != VA_INVALID_SURFACE) vaDestroySurfaces(vpp->va, &slot->surface, 1);
    }
    if (vpp->context != VA_INVALID_ID) vaDestroyContext(vpp->va, vpp->context);
    if (vpp->config != VA_INVALID_ID) vaDestroyConfig(vpp->va, vpp->config);
    av_buffer_unref(&vpp->device);
    free(vpp); *ptr = NULL;
    return true;
}

struct dvbridge_fel_vpp *dvbridge_fel_vpp_create(AVBufferRef *device, int width, int height)
{
    if (!device || width <= 0 || height <= 0 || width > 3840 || height > 2160 ||
        (width & 1) || (height & 1) || eglGetCurrentContext() == EGL_NO_CONTEXT)
        return NULL;
    AVHWDeviceContext *hw = (void *)device->data;
    if (hw->type != AV_HWDEVICE_TYPE_VAAPI || !hw->hwctx) return NULL;
    struct dvbridge_fel_vpp *vpp = calloc(1, sizeof(*vpp));
    if (!vpp) return NULL;
    vpp->config = vpp->context = VA_INVALID_ID;
    for (unsigned i = 0; i < 2; ++i) vpp->slots[i].surface = VA_INVALID_SURFACE;
    vpp->device = av_buffer_ref(device);
    vpp->va = ((AVVAAPIDeviceContext *)hw->hwctx)->display;
    vpp->egl = eglGetCurrentDisplay(); vpp->gl_context = eglGetCurrentContext();
    vpp->width = width; vpp->height = height;
    /* VPP's general RT mask is not an exhaustive list of output formats. */
    if (!vpp->device || !vpp->va ||
        vaCreateConfig(vpp->va, VAProfileNone, VAEntrypointVideoProc, NULL, 0, &vpp->config) != VA_STATUS_SUCCESS ||
        vaCreateContext(vpp->va, vpp->config, width, height, VA_PROGRESSIVE, NULL, 0, &vpp->context) != VA_STATUS_SUCCESS)
        goto fail;
    VASurfaceAttrib format = {.type = VASurfaceAttribPixelFormat, .flags = VA_SURFACE_ATTRIB_SETTABLE,
        .value = {.type = VAGenericValueTypeInteger, .value.i = VA_FOURCC_Y416}};
    for (unsigned i = 0; i < 2; ++i) {
        if (vaCreateSurfaces(vpp->va, VA_RT_FORMAT_YUV444_12, width, height,
            &vpp->slots[i].surface, 1, &format, 1) != VA_STATUS_SUCCESS || !import_surface(vpp, &vpp->slots[i]))
            goto fail;
    }
    return vpp;
fail:
    dvbridge_fel_vpp_destroy(&vpp);
    return NULL;
}

enum dvbridge_fel_vpp_result dvbridge_fel_vpp_acquire(struct dvbridge_fel_vpp *vpp,
    const AVFrame *source, const struct dvbridge_fel_vpp_image **image)
{
    if (image) *image = NULL;
    if (!vpp || !image || !source || vpp->failed || source->format != AV_PIX_FMT_VAAPI ||
        !source->hw_frames_ctx || source->color_range == AVCOL_RANGE_JPEG ||
        source->width != vpp->width / 2 || source->height != vpp->height / 2 ||
        eglGetCurrentDisplay() != vpp->egl || eglGetCurrentContext() != vpp->gl_context)
        return DVBRIDGE_VPP_FAILED;
    const AVHWFramesContext *frames = (void *)source->hw_frames_ctx->data;
    if (frames->sw_format != AV_PIX_FMT_P010LE || !frames->device_ref ||
        frames->device_ref->data != vpp->device->data)
        return DVBRIDGE_VPP_FAILED;
    struct vpp_slot *slot = NULL;
    for (unsigned i = 0; i < 2; ++i)
        if (!vpp->slots[i].leased) { slot = &vpp->slots[i]; break; }
    if (!slot) return DVBRIDGE_VPP_BUSY;
    VARectangle src = {0, 0, source->width, source->height}, dst = {0, 0, vpp->width, vpp->height};
    VAProcPipelineParameterBuffer params = {.surface = (VASurfaceID)(uintptr_t)source->data[3],
        .surface_region = &src, .output_region = &dst,
        .surface_color_standard = VAProcColorStandardBT2020,
        .output_color_standard = VAProcColorStandardBT2020, .filter_flags = VA_FILTER_SCALING_DEFAULT};
    params.input_color_properties.color_range = params.output_color_properties.color_range = VA_SOURCE_RANGE_REDUCED;
    params.input_color_properties.chroma_sample_location = VA_CHROMA_SITING_VERTICAL_CENTER | VA_CHROMA_SITING_HORIZONTAL_LEFT;
    VABufferID buffer = VA_INVALID_ID;
    VAStatus status = vaCreateBuffer(vpp->va, vpp->context, VAProcPipelineParameterBufferType,
        sizeof(params), 1, &params, &buffer);
    if (status == VA_STATUS_SUCCESS) status = vaBeginPicture(vpp->va, vpp->context, slot->surface);
    if (status == VA_STATUS_SUCCESS) {
        status = vaRenderPicture(vpp->va, vpp->context, &buffer, 1);
        const VAStatus ended = vaEndPicture(vpp->va, vpp->context);
        if (status == VA_STATUS_SUCCESS) status = ended;
    }
    if (buffer != VA_INVALID_ID) vaDestroyBuffer(vpp->va, buffer);
    if (status == VA_STATUS_SUCCESS) status = vaSyncSurface(vpp->va, slot->surface);
    if (status != VA_STATUS_SUCCESS) { vpp->failed = true; return DVBRIDGE_VPP_FAILED; }
    slot->leased = true; *image = &slot->image;
    return DVBRIDGE_VPP_OK;
}

void dvbridge_fel_vpp_release(struct dvbridge_fel_vpp *vpp, const struct dvbridge_fel_vpp_image *image)
{
    if (!vpp || !image) return;
    for (unsigned i = 0; i < 2; ++i)
        if (image == &vpp->slots[i].image) { vpp->slots[i].leased = false; return; }
}
