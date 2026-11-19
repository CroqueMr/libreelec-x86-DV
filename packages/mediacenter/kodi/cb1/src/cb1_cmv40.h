/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_CMV40_H
#define CB1_CMV40_H
#include <stdbool.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct AVDOVIMetadata AVDOVIMetadata;

enum cb1_cmv40_mode {
    CB1_CMV40_DISABLED, CB1_CMV40_NO_L2, CB1_CMV40_ALWAYS, CB1_CMV40_AUTO, CB1_CMV40_AUTO2
};
enum cb1_cmv40_status {
    CB1_CMV40_OFF, CB1_CMV40_EXISTING, CB1_CMV40_NOT_SELECTED,
    CB1_CMV40_NEEDS_TV, CB1_CMV40_APPEND, CB1_CMV40_INVALID, CB1_CMV40_REJECTED
};
struct cb1_cmv40_options {
    enum cb1_cmv40_mode mode;
    unsigned trigger; /* 0: TV >= mastering peak; otherwise 1000/2000/4000/10000. */
    unsigned headroom; /* Auto 2: 0..50 percent, Kodi default 20. */
    double tv_peak;
};

enum cb1_cmv40_status cb1_cmv40_decide(const struct cb1_cmv40_options *options,
    const AVDOVIMetadata *source,size_t bytes);
/* A successful no-op returns a NULL copy. Source is never modified. */
bool cb1_cmv40_output(const struct cb1_cmv40_options *options,
    const AVDOVIMetadata *source,size_t bytes,bool disable_l2,
    AVDOVIMetadata **copy,size_t *copy_bytes,enum cb1_cmv40_status *status);
#ifdef __cplusplus
}
#endif
#endif
