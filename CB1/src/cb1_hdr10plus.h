/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_HDR10PLUS_H
#define CB1_HDR10PLUS_H
#include <stdbool.h>
#include <stdint.h>
#include <libavutil/hdr_dynamic_metadata.h>
#ifdef __cplusplus
extern "C" {
#endif

enum cb1_hdr10plus_status {
    CB1_HDR10PLUS_OK, CB1_HDR10PLUS_INVALID, CB1_HDR10PLUS_UNREPRESENTABLE
};
#define CB1_HDR10PLUS_VSIF_BYTES 31
/* Complete HDMI infoframe: type, version, length, checksum, 27 payload bytes.
 * Failure preserves out. Input metadata is never changed. no_delay is true
 * only when the presentation backend latches the packet with its image. */
enum cb1_hdr10plus_status cb1_hdr10plus_vsif(uint8_t out[CB1_HDR10PLUS_VSIF_BYTES],
    const AVDynamicHDRPlus *metadata, bool overlay, bool no_delay);

#ifdef __cplusplus
}
#endif
#endif
