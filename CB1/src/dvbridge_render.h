/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_RENDER_H
#define DVBRIDGE_RENDER_H
#include <libplacebo/renderer.h>
#include "dvbridge_core.h"
#include "dvbridge_placebo.h"
#include "dvbridge_creative.h"

struct dvbridge_renderer;
struct cb1_ai_result;
#define CB1_HDR10_AI_RENDER_API 1
/* Borrowed intermediate. DV preparation may still need its existing poll;
 * resolve and successful presentation remain separate from this call. */
pl_tex dvbridge_render_hdr10_ai_rgb(struct dvbridge_renderer *renderer,
    const struct dvbridge_policy *policy,const struct cb1_ai_result *prediction,
    const struct pl_frame *source,const struct dvbridge_geometry *geometry);
struct dvbridge_retirement_owner;
#define DVBRIDGE_CM4_GPU_API 1
/* Trim-only shader in linear 203-nit units. The caller retains the shader. */
bool dvbridge_creative_cm4_shader(pl_shader shader,const struct dvbridge_cm4_coefficients *coefficients);
#define DVBRIDGE_DV_POLICY_API 5
enum dvbridge_output_generation { DVBRIDGE_ETSI_LEGACY_LITERAL=1, DVBRIDGE_SOURCE_METADATA=2 };
struct dvbridge_dv_policy_snapshot {
    struct dvbridge_identity identity;
    struct dvbridge_policy policy;
    unsigned source_cm_version;
    enum dvbridge_output_generation output_generation;
    struct pl_color_space nominal_target, container;
    struct dvbridge_geometry geometry;
    double nominal_max_nits, statistics[3]; /* Legacy analysis fields; zero for source-metadata output. */
    double raw_statistics[3];
    float raw_sum;
    uint32_t sample_count;
    uint16_t l1[3], source_pq[2]; /* Source min,max,avg; original mastering envelope. */
    unsigned margins[4], max_cll, max_fall;
    bool measured, fel_reconstructed, resolved;
    pl_tex final_target; /* Non-owning historical identity token after commit. */
    unsigned final_framebuffer; /* Captured matching-context authority, not an owned GL object. */
    struct dvbridge_creative_plan creative;
    struct dvbridge_creative_edit_report creative_edit;
};
struct dvbridge_dv_policy_output {
    struct dvbridge_dv_policy_snapshot value;
    const void *output_metadata;
    size_t bytes;
    const struct dvbridge_candidate *candidate;
    pl_tex intermediate;
    uint64_t resolve_serial;
};
enum dvbridge_dv_policy_status {
    DVBRIDGE_DV_FAILED, DVBRIDGE_DV_UNSUPPORTED, DVBRIDGE_DV_BUSY,
    DVBRIDGE_DV_PENDING, DVBRIDGE_DV_READY, DVBRIDGE_DV_IDLE
};
/* Borrowed GPU/context must stay usable/current until owner destroy succeeds.
 * Exactly one attached renderer or detached retirement lease. No context refcount.
 * Caller independently retains decoder imports and display-in-flight targets. */
struct dvbridge_retirement_owner *dvbridge_retirement_owner_create(pl_gpu gpu);
struct dvbridge_renderer *dvbridge_renderer_create_with_owner(struct dvbridge_retirement_owner *owner);
enum dvbridge_dv_policy_status dvbridge_retirement_owner_poll(struct dvbridge_retirement_owner *owner);
bool dvbridge_retirement_owner_destroy(struct dvbridge_retirement_owner **owner);
#define DVBRIDGE_HDR10_POLICY_API 4
struct dvbridge_hdr10_policy_output {
    struct dvbridge_identity identity;
    struct dvbridge_policy policy;
    struct pl_color_space nominal_target;
    struct pl_color_space container;
    struct dvbridge_hdr10_metadata hdr10;
    struct dvbridge_geometry geometry;
    struct dvbridge_creative_plan creative;
    bool fel_reconstructed;
    bool resolved;
    pl_tex final_target; /* Borrowed caller-owned target; historical token after commit. */
};
struct dvbridge_renderer *dvbridge_renderer_create(pl_gpu gpu);
void dvbridge_renderer_destroy(struct dvbridge_renderer *renderer);
void dvbridge_renderer_reset(struct dvbridge_renderer *renderer);

/* Requires the renderer's current borrowed GL context. GPU requirements only;
 * source/TV policy, allocation success and HDMI admission are separate checks.
 * Disabled has no CB1 processing route and returns false, as do null/invalid inputs. */
bool dvbridge_renderer_supports_mode(struct dvbridge_renderer *renderer, enum dvbridge_mode mode);
/* HDR10 AI output retains its separate analysis requirements. */
bool dvbridge_renderer_supports_hdr10_ai(struct dvbridge_renderer *renderer, enum dvbridge_mode mode);

/* Produces an intermediate PQ RGB image, not a scanout-ready DV frame. */
bool dvbridge_render_rgb(struct dvbridge_renderer *renderer, const struct pl_frame *source,
                        const void *metadata, size_t bytes, double pts, double el_pts,
                        struct dvbridge_geometry geometry);
/* Apply per-picture L1 mapping to the fixed session target before overlays. */
bool dvbridge_render_hdr10_rgb(struct dvbridge_renderer *renderer,
                              const struct dvbridge_hdr10_session *session,
                              const struct pl_frame *source,
                              const void *metadata, size_t bytes, double pts, double el_pts,
                              struct dvbridge_geometry geometry);
/* Optional full-raster, overlay-free fast path. The caller owns an exact RGBA8
 * linear target; all other layouts keep the separate full-precision path. */
bool dvbridge_render_packed(struct dvbridge_renderer *renderer, const struct pl_frame *source,
                           const void *metadata, size_t bytes, double pts, double el_pts,
                           struct dvbridge_geometry geometry, pl_tex target, bool flip_y);
#define DVBRIDGE_NATIVE_OVERLAY_API 1
/* Borrowed Kodi subtitle texture and sRGB transfer LUTs. Row zero is the logical bottom;
 * rect is a clipped, even-x screen rectangle in top-down 3840x2160 coordinates.
 * An all-zero rectangle keeps the same shader ready without drawing a subtitle.
 * The caller retains textures until GPU completion. Video metadata is unchanged. */
struct dvbridge_native_overlay {
    pl_tex texture, degamma, pq;
    float rect[4];
    bool input_pq; /* Premultiplied BT.2020 PQ; LUTs remain bound but unused. */
};
bool dvbridge_render_packed_overlay(struct dvbridge_renderer *renderer,
    const struct pl_frame *source, const void *metadata, size_t bytes,
    double pts, double el_pts, struct dvbridge_geometry geometry,
    pl_tex target, bool flip_y, const struct dvbridge_native_overlay *overlay);
pl_tex dvbridge_render_texture(const struct dvbridge_renderer *renderer);
/* Quantize the composed PQ image without applying tone mapping again. */
bool dvbridge_render_hdr10(struct dvbridge_renderer *renderer, pl_tex target,
                          bool flip_y, bool limited, unsigned bits);
const struct dvbridge_candidate *dvbridge_render_candidate(const struct dvbridge_renderer *renderer);
/* Call only after successful presentation. Consumes one prepared frame. */
bool dvbridge_render_commit(struct dvbridge_renderer *renderer);

/* identity is the caller-verified BL/RPU/applicable EL tuple assertion, not an
 * independently inspectable source-origin tag. All times must be finite;
 * applicable EL must have exactly the same PTS. Explicit prepare always treats
 * original source because the exposed intermediate may have been composed.
 * Paused final-surface reuse is caller-owned, without another prepare. */
bool dvbridge_render_hdr10_policy_rgb(struct dvbridge_renderer *renderer,
    const struct dvbridge_policy *policy, const struct dvbridge_identity *identity,
    const struct pl_frame *source, const void *metadata, size_t bytes,
    double pts, double el_pts, struct dvbridge_geometry geometry);
const struct dvbridge_hdr10_policy_output *dvbridge_render_policy_output(const struct dvbridge_renderer *renderer);
bool dvbridge_render_hdr10_policy_resolve(struct dvbridge_renderer *renderer, pl_tex target,
    bool flip_y, bool limited, unsigned bits);
/* After actual successful presentation only. Caller retains final targets
 * through display completion. This function never owns or frees them. */
bool dvbridge_render_policy_commit(struct dvbridge_renderer *renderer,
    const struct dvbridge_identity *presented_identity, pl_tex presented_target);
void dvbridge_render_policy_cancel(struct dvbridge_renderer *renderer);
bool dvbridge_render_policy_committed(const struct dvbridge_renderer *renderer,
    struct dvbridge_hdr10_policy_output *snapshot);

enum dvbridge_dv_policy_status dvbridge_render_dv_policy_prepare(
    struct dvbridge_renderer *renderer,const struct dvbridge_policy *policy,
    const struct dvbridge_identity *identity,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry);
#define DVBRIDGE_ENHANCED_PACKED_API 1
/* Same metadata adjustment with native full-raster packing and optional subtitles.
 * Other GUI/capture composition retains the RGB intermediate prepare above. */
enum dvbridge_dv_policy_status dvbridge_render_dv_policy_prepare_packed(
    struct dvbridge_renderer *renderer,const struct dvbridge_policy *policy,
    const struct dvbridge_identity *identity,const struct pl_frame *source,
    const void *metadata,size_t bytes,double pts,double el_pts,struct dvbridge_geometry geometry,
    pl_tex target,bool flip_y,const struct dvbridge_native_overlay *overlay);
enum dvbridge_dv_policy_status dvbridge_render_dv_policy_poll(struct dvbridge_renderer *renderer);
#define CB1_PACKED_AHEAD_API 1
/* Retain one committed packed frame's GPU lease while preparing the next.
 * Other paths keep normal polling; a third outstanding frame returns Busy. */
enum dvbridge_dv_policy_status dvbridge_render_dv_policy_advance(struct dvbridge_renderer *renderer);
const struct dvbridge_dv_policy_output *dvbridge_render_dv_policy_output(const struct dvbridge_renderer *renderer);
/* target/FBO pair is the caller's matching-context assertion for opaque output.
 * Store the FBO when wrapping output; never guess zero from unwrap failure.
 * Retain both through actual GPU use and presentation. Texture attachments are
 * additionally checked against pinned LP ownership. Framebuffer 0 is valid. */
bool dvbridge_render_dv_policy_resolve(struct dvbridge_renderer *renderer,pl_tex target,
    unsigned final_framebuffer,bool flip_y);
/* Captured serial belongs to the exact resolve the caller successfully presented.
 * Never reread the latest serial from a delayed presentation callback. */
bool dvbridge_render_dv_policy_commit(struct dvbridge_renderer *renderer,
    const struct dvbridge_identity *presented_identity,pl_tex presented_target,uint64_t submitted_resolve_serial);
void dvbridge_render_dv_policy_cancel(struct dvbridge_renderer *renderer);
bool dvbridge_render_dv_policy_committed(const struct dvbridge_renderer *renderer,
    struct dvbridge_dv_policy_snapshot *snapshot);
#endif
