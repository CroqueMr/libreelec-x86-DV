/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_CORE_H
#define DVBRIDGE_CORE_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

struct dvbridge_context;
struct dvbridge_candidate;
/* Render-thread confined. Destroy all candidates before their owning context. */

struct dvbridge_geometry {
    int source_width, source_height;
    int x, y, width, height;
};

/* Common active-picture bounds. Failure leaves margins untouched. */
bool dvbridge_frame_area(unsigned margins[4], const void *metadata, size_t bytes,
                         struct dvbridge_geometry geometry);

struct dvbridge_context *dvbridge_create(void);
void dvbridge_destroy(struct dvbridge_context *context);
void dvbridge_reset(struct dvbridge_context *context);

/* No state advances until presentation succeeds and commit is called. */
struct dvbridge_candidate *dvbridge_prepare(
    const struct dvbridge_context *context, const void *metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed);
#define DVBRIDGE_OUTPUT_METADATA_API 1
struct dvbridge_candidate *dvbridge_prepare_output(
    const struct dvbridge_context *context, const void *output_metadata, size_t bytes,
    double pts, struct dvbridge_geometry geometry, bool fel_reconstructed, bool force_refresh);
void dvbridge_candidate_destroy(struct dvbridge_candidate *candidate);
bool dvbridge_commit(struct dvbridge_context *context, const struct dvbridge_candidate *candidate);
const uint32_t *dvbridge_packets(const struct dvbridge_candidate *candidate, unsigned *count);
/* Left, right, top, bottom blanking margins in the final 3840x2160 raster. */
bool dvbridge_active_area(const struct dvbridge_candidate *candidate, unsigned margins[4]);

#ifdef __cplusplus
}
#endif
#endif
