/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_CIRCUIT_H
#define CB1_CIRCUIT_H
#ifdef __cplusplus
extern "C" {
#endif

enum cb1_circuit {
    CB1_DV_DV_REFERENCE,
    CB1_DV_HDR10_BASIC,
    CB1_DV_HDR10_EXPERT,
    CB1_DV_DV_NATURAL,
    CB1_DV_DV_INTENSE,
    /* Retain existing IDs; retired entries are not reassigned. */
    CB1_HDR10_DV_REFERENCE = 7,
    CB1_HDR10_DV_NATURAL,
    CB1_HDR10_DV_INTENSE,
    CB1_CIRCUIT_COUNT
};

const char *cb1_engine_version(void);
/* An identity does not imply that its circuit is available on this output. */
const char *cb1_circuit_version(enum cb1_circuit circuit);

#ifdef __cplusplus
}
#endif
#endif
