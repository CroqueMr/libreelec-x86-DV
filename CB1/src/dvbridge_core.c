/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Own frame metadata and commit serializer state only after a successful presentation. */
#include "dvbridge_core.h"
#include "dvbridge_metadata.h"

struct dvbridge_context {
    struct dvbridge_dv state;
    uint64_t revision;
    bool overlay_visible, overlay_presented;
};

struct dvbridge_candidate {
    struct dvbridge_dv state;
    unsigned margins[4];
    const struct dvbridge_context *owner;
    uint64_t revision;
    bool overlay_visible;
};

struct dvbridge_context *dvbridge_create(void)
{
    return calloc(1, sizeof(struct dvbridge_context));
}

void dvbridge_destroy(struct dvbridge_context *context)
{
    free(context);
}

void dvbridge_reset(struct dvbridge_context *context)
{
    if (!context) return;
    memset(&context->state, 0, sizeof(context->state));
    context->overlay_presented = false;
    ++context->revision;
}

void dvbridge_set_overlay_visible(struct dvbridge_context *context, bool visible)
{
    if (context) context->overlay_visible = visible;
}

bool dvbridge_frame_area(unsigned margins[4], const void *metadata, size_t bytes,
                         struct dvbridge_geometry geometry)
{
    if (!margins || !dvbridge_metadata_bounds(metadata, bytes)) return false;
    if (geometry.source_width <= 0 || geometry.source_width > 3840 ||
        geometry.source_height <= 0 || geometry.source_height > 2160 ||
        geometry.x < 0 || geometry.x > 3840 || geometry.y < 0 || geometry.y > 2160 ||
        geometry.width <= 0 || geometry.width > 3840 ||
        geometry.height <= 0 || geometry.height > 2160) return false;
    const AVDOVIMetadata *m = metadata;
    struct dvbridge_dv area = {0};
    if (!dvbridge_dv_geometry(&area, geometry.source_width, geometry.source_height,
            geometry.x, geometry.y, geometry.width, geometry.height)) return false;
    unsigned offsets[4] = {0};
    unsigned levels = 0;
    for (int i = 0; i < m->num_ext_blocks; ++i) {
        const AVDOVIDmData *e = av_dovi_get_ext(m, i);
        if (e->level != 5)
            continue;
        if (++levels > 1) return false;
        offsets[0] = e->l5.left_offset;
        offsets[1] = e->l5.right_offset;
        offsets[2] = e->l5.top_offset;
        offsets[3] = e->l5.bottom_offset;
    }
    unsigned computed[4];
    if (!dvbridge_dv_area(&area, offsets[0], offsets[1], offsets[2], offsets[3], computed))
        return false;
    memcpy(margins, computed, sizeof(computed));
    return true;
}

static struct dvbridge_candidate *prepare_output(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed, bool force_refresh,
    bool source_transport)
{
    if (!context || !dvbridge_dv_bounds(metadata, bytes)) return NULL;
    if (source_transport && (!dvbridge_dv_source_transport(metadata) ||
        geometry.source_width!=3840 || geometry.source_height!=2160 || geometry.x || geometry.y ||
        geometry.width!=3840 || geometry.height!=2160)) return NULL;
    unsigned margins[4];
    if (!dvbridge_frame_area(margins, metadata, bytes, geometry)) return NULL;
    struct dvbridge_candidate *candidate = calloc(1, sizeof(*candidate));
    if (!candidate) return NULL;
    candidate->state = context->state;
    candidate->owner = context;
    candidate->revision = context->revision;
    candidate->state.fel_verified = fel_reconstructed;
    candidate->state.source_transport = source_transport;
    /* Only the transmitted L5 changes; the caller masks with the source margins
     * before composing overlays. Both visibility edges refresh the display. */
    static const unsigned full_raster[4];
    const bool overlay = context->overlay_visible;
    const bool edge = context->state.frames && overlay != context->overlay_presented;
    if (!dvbridge_dv_geometry(&candidate->state, geometry.source_width, geometry.source_height,
            geometry.x, geometry.y, geometry.width, geometry.height) ||
        !dvbridge_dv_metadata_output(&candidate->state, metadata, pts,
            overlay ? full_raster : margins, force_refresh || edge)) {
        free(candidate);
        return NULL;
    }
    memcpy(candidate->margins, margins, sizeof(margins));
    candidate->overlay_visible = overlay;
    return candidate;
}

struct dvbridge_candidate *dvbridge_prepare_output(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed, bool force_refresh)
{
    return prepare_output(context,metadata,bytes,pts,geometry,fel_reconstructed,force_refresh,false);
}

struct dvbridge_candidate *dvbridge_prepare_source_output(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed, bool force_refresh)
{
    return prepare_output(context,metadata,bytes,pts,geometry,fel_reconstructed,force_refresh,true);
}

struct dvbridge_candidate *dvbridge_prepare(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed)
{
    return dvbridge_prepare_output(context,metadata,bytes,pts,geometry,fel_reconstructed,false);
}

void dvbridge_candidate_destroy(struct dvbridge_candidate *candidate)
{
    free(candidate);
}

bool dvbridge_commit(struct dvbridge_context *context, const struct dvbridge_candidate *candidate)
{
    if (!context || !candidate || candidate->owner != context ||
        candidate->revision != context->revision) return false;
    context->state = candidate->state;
    context->overlay_presented = candidate->overlay_visible;
    ++context->revision;
    return true;
}

const uint32_t *dvbridge_packets(const struct dvbridge_candidate *candidate, unsigned *count)
{
    if (count) *count = candidate ? candidate->state.count : 0;
    return candidate ? candidate->state.packets : NULL;
}

bool dvbridge_active_area(const struct dvbridge_candidate *candidate, unsigned margins[4])
{
    if (!candidate || !margins)
        return false;
    memcpy(margins, candidate->margins, sizeof(candidate->margins));
    return true;
}
