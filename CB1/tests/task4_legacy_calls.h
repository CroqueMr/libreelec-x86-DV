/* Historical per-call tests initialize independently; session tests use the new API directly. */
#ifndef TASK4_LEGACY_CALLS_H
#define TASK4_LEGACY_CALLS_H
#include "dvbridge_render.h"
static bool legacy_hdr10(struct dvbridge_renderer *r,const struct pl_frame *frame,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry)
{
    struct dvbridge_hdr10_session session;
    if (!dvbridge_hdr10_session_init(&session,metadata,bytes)) {
        dvbridge_renderer_reset(r);
        return false;
    }
    return dvbridge_render_hdr10_rgb(r,&session,frame,metadata,bytes,pts,el_pts,geometry);
}
#endif
