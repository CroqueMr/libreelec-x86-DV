/* SPDX-License-Identifier: GPL-2.0-or-later */
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

bool dvbridge_geometry_raster(struct dvbridge_geometry geometry, int *width, int *height)
{
    int w=geometry.target_width,h=geometry.target_height;
    if(!w && !h){w=3840;h=2160;}
    if(!width || !height || w<=0 || h<=0 || (uint64_t)w*h>INT_MAX)return false;
    *width=w;*height=h;
    return true;
}

bool dvbridge_geometry_source(struct dvbridge_geometry geometry,float crop[4])
{
    if(!crop || geometry.source_width<=0 || geometry.source_width>3840 ||
       geometry.source_height<=0 || geometry.source_height>2160)return false;
    float rect[4]={0,0,geometry.source_width,geometry.source_height};
    if(geometry.crop[0] || geometry.crop[1] || geometry.crop[2] || geometry.crop[3])
        memcpy(rect,geometry.crop,sizeof(rect));
    for(unsigned i=0;i<4;i++)if(!isfinite(rect[i]))return false;
    if(rect[0]<0 || rect[1]<0 || rect[2]>geometry.source_width || rect[3]>geometry.source_height ||
       rect[0]>=rect[2] || rect[1]>=rect[3])return false;
    memcpy(crop,rect,sizeof(rect));
    return true;
}

bool dvbridge_geometry_destination(struct dvbridge_geometry geometry,float rect[4])
{
    int width,height;
    if(!rect || !dvbridge_geometry_raster(geometry,&width,&height))return false;
    float value[4]={(float)geometry.x,(float)geometry.y,
        (float)geometry.x+geometry.width,(float)geometry.y+geometry.height};
    if(geometry.placement[2] || geometry.placement[3])
        memcpy(value,geometry.placement,sizeof(value));
    for(unsigned i=0;i<4;i++)if(!isfinite(value[i]))return false;
    if(value[0]<0 || value[1]<0 || value[2]>width || value[3]>height ||
       value[0]>=value[2] || value[1]>=value[3])return false;
    memcpy(rect,value,sizeof(value));
    return true;
}

bool dvbridge_frame_area(unsigned margins[4], const void *metadata, size_t bytes,
                         struct dvbridge_geometry geometry)
{
    if (!margins || !dvbridge_metadata_bounds(metadata, bytes)) return false;
    int target_width,target_height;
    if (!dvbridge_geometry_raster(geometry,&target_width,&target_height) || (target_width&1)) return false;
    if (geometry.source_width <= 0 || geometry.source_width > 3840 ||
        geometry.source_height <= 0 || geometry.source_height > 2160 ||
        geometry.x < 0 || geometry.x > target_width || geometry.y < 0 || geometry.y > target_height ||
        geometry.width <= 0 || geometry.width > target_width-geometry.x ||
        geometry.height <= 0 || geometry.height > target_height-geometry.y) return false;
    float crop[4],dest[4];
    if(!dvbridge_geometry_source(geometry,crop) ||
       !dvbridge_geometry_destination(geometry,dest))return false;
    const bool native_crop=geometry.crop[2]!=0 || geometry.crop[3]!=0 || geometry.placement[2]!=0;
    const AVDOVIMetadata *m = metadata;
    struct dvbridge_dv area = {.target_w=target_width,.target_h=target_height};
    if (!native_crop && !dvbridge_dv_geometry(&area, geometry.source_width, geometry.source_height,
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
    if(native_crop){
        if(offsets[0]>=(unsigned)geometry.source_width ||
           offsets[1]>=(unsigned)geometry.source_width-offsets[0] ||
           offsets[2]>=(unsigned)geometry.source_height ||
           offsets[3]>=(unsigned)geometry.source_height-offsets[2])return false;
        double left=fmax(crop[0],offsets[0]),right=fmin(crop[2],geometry.source_width-offsets[1]);
        double top=fmax(crop[1],offsets[2]),bottom=fmin(crop[3],geometry.source_height-offsets[3]);
        if(left>=right || top>=bottom)return false;
        double sx=(dest[2]-dest[0])/(double)(crop[2]-crop[0]);
        double sy=(dest[3]-dest[1])/(double)(crop[3]-crop[1]);
        computed[0]=lround(dest[0]+(left-crop[0])*sx);
        computed[1]=target_width-lround(dest[0]+(right-crop[0])*sx);
        computed[2]=lround(dest[1]+(top-crop[1])*sy);
        computed[3]=target_height-lround(dest[1]+(bottom-crop[1])*sy);
    }else if (!dvbridge_dv_area(&area, offsets[0], offsets[1], offsets[2], offsets[3], computed))
        return false;
    memcpy(margins, computed, sizeof(computed));
    return true;
}

static struct dvbridge_candidate *prepare_output(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed, bool force_refresh,
    bool source_transport, bool profile5_transport, bool ipt_transport)
{
    if (!context || !dvbridge_dv_bounds(metadata, bytes)) return NULL;
    if (source_transport && !(profile5_transport ? dvbridge_dv_profile5_transport(metadata) :
        dvbridge_dv_source_transport(metadata))) return NULL;
    if (ipt_transport && !dvbridge_dv_source_transport(metadata)) return NULL;
    unsigned margins[4];
    if (!dvbridge_frame_area(margins, metadata, bytes, geometry)) return NULL;
    struct dvbridge_candidate *candidate = calloc(1, sizeof(*candidate));
    if (!candidate) return NULL;
    candidate->state = context->state;
    if(!dvbridge_geometry_raster(geometry,&candidate->state.target_w,&candidate->state.target_h)){
        free(candidate);return NULL;
    }
    candidate->owner = context;
    candidate->revision = context->revision;
    candidate->state.fel_verified = fel_reconstructed;
    candidate->state.source_transport = source_transport;
    candidate->state.profile5_transport = profile5_transport;
    candidate->state.ipt_transport = ipt_transport;
    /* Only the transmitted L5 changes; the caller masks with the source margins
     * before composing overlays. Both visibility edges refresh the display. */
    static const unsigned full_raster[4];
    const bool overlay = context->overlay_visible;
    const bool edge = context->state.frames && overlay != context->overlay_presented;
    candidate->state.source_w=geometry.source_width;candidate->state.source_h=geometry.source_height;
    candidate->state.dest_x=geometry.x;candidate->state.dest_y=geometry.y;
    candidate->state.dest_w=geometry.width;candidate->state.dest_h=geometry.height;
    if (!dvbridge_dv_metadata_output(&candidate->state, metadata, pts,
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
    return prepare_output(context,metadata,bytes,pts,geometry,fel_reconstructed,force_refresh,false,false,false);
}

struct dvbridge_candidate *dvbridge_prepare_source_output(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed, bool force_refresh)
{
    return prepare_output(context,metadata,bytes,pts,geometry,fel_reconstructed,force_refresh,true,false,false);
}

struct dvbridge_candidate *dvbridge_prepare_master_source_output(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed, bool force_refresh)
{
    if(!dvbridge_dv_bounds(metadata,bytes))return NULL;
    return prepare_output(context,metadata,bytes,pts,geometry,fel_reconstructed,force_refresh,
        true,dvbridge_dv_profile5(metadata),false);
}

struct dvbridge_candidate *dvbridge_prepare_ipt_output(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed, bool force_refresh)
{
    return prepare_output(context,metadata,bytes,pts,geometry,fel_reconstructed,force_refresh,false,false,true);
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
