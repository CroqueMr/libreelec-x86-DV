/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DVBRIDGE_FEL_H
#define DVBRIDGE_FEL_H
#include <libavcodec/avcodec.h>
#include <stdbool.h>

struct dvbridge_fel;
/* Single decoder-thread owner. Returned frames retain their hardware surface. */
struct dvbridge_fel *dvbridge_fel_create(const AVCodecParameters *parameters, AVRational time_base);
void dvbridge_fel_destroy(struct dvbridge_fel *fel);
void dvbridge_fel_reset(struct dvbridge_fel *fel);
bool dvbridge_fel_device(struct dvbridge_fel *fel, AVBufferRef *device);
bool dvbridge_fel_submit(struct dvbridge_fel *fel, const AVPacket *packet);
/* Declared dual-track timing before conversion to Kodi's clock. AV_NOPTS_VALUE
 * marks an absent layer in a terminal unit; an EL-only unit never decodes BL.
 * A non-presentable BL remains a required compressed decoder reference. */
struct dvbridge_fel_source {
    int64_t base_pts, enhancement_pts;
    AVRational time_base;
    uint64_t epoch;
    bool presentable;
};
bool dvbridge_fel_submit_source(struct dvbridge_fel *fel, const AVPacket *packet,
                               const struct dvbridge_fel_source *source);
/* Optional reason is set only when the final drain identifies a specific fault. */
bool dvbridge_fel_drain(struct dvbridge_fel *fel, const char **reason);
/* 1: exact pair, 0: need input, 2: discard preroll, -1: missing pair / failure. */
int dvbridge_fel_take(struct dvbridge_fel *fel, int64_t pts, AVFrame **frame);
/* Disc playback may return 3 for a matched, validated RPU that needs no residual.
 * Compressed reference pictures remain available until a self-contained IDR. */
int dvbridge_fel_take_mel(struct dvbridge_fel *fel, int64_t pts, AVFrame **frame,
                         const void *metadata, size_t metadata_size);
bool dvbridge_fel_failed(const struct dvbridge_fel *fel);
/* Decoder reached EOF and no enhancement surface remains to pair. */
bool dvbridge_fel_exhausted(const struct dvbridge_fel *fel);
#endif
