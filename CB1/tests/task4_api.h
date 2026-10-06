/* Test-only baseline bridge: execute old APIs without adding latch behavior. */
#include "dvbridge_placebo.h"
#ifdef TASK4_BASELINE
struct dvbridge_hdr10_session {
    struct pl_color_space target;
    struct dvbridge_hdr10_metadata output;
};
static bool dvbridge_hdr10_session_init(struct dvbridge_hdr10_session *out,
                                        const void *metadata, size_t bytes)
{
    return out && dvbridge_hdr10_target(&out->target, metadata, bytes) &&
        dvbridge_get_hdr10_metadata(&out->output, metadata, bytes);
}
#define HDR10(r,s,...) dvbridge_render_hdr10_rgb(r,__VA_ARGS__)
#else
#define HDR10(r,s,...) dvbridge_render_hdr10_rgb(r,s,__VA_ARGS__)
#endif
