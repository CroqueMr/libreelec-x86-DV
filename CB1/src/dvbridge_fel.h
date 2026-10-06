/* SPDX-License-Identifier: GPL-3.0-or-later */
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
bool dvbridge_fel_drain(struct dvbridge_fel *fel);
/* 1: exact pair, 0: need input, 2: discard preroll, -1: missing pair / failure. */
int dvbridge_fel_take(struct dvbridge_fel *fel, int64_t pts, AVFrame **frame);
bool dvbridge_fel_failed(const struct dvbridge_fel *fel);
/* Decoder reached EOF and no enhancement surface remains to pair. */
bool dvbridge_fel_exhausted(const struct dvbridge_fel *fel);
#endif
