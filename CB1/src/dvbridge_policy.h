/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DVBRIDGE_POLICY_H
#define DVBRIDGE_POLICY_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum dvbridge_mode {
    DVBRIDGE_MODE_DISABLED, DVBRIDGE_MODE_STANDARD, DVBRIDGE_MODE_HDR10_BASIC,
    DVBRIDGE_MODE_HDR10_EXPERT, DVBRIDGE_MODE_ENHANCED_DV,
    DVBRIDGE_MODE_MASTER_REFERENCE = 5, DVBRIDGE_MODE_HDR10PLUS = 6,
    DVBRIDGE_MODE_SDR = 7, DVBRIDGE_MODE_COUNT = 8
};
enum dvbridge_panel { DVBRIDGE_PANEL_UNSET, DVBRIDGE_PANEL_OLED, DVBRIDGE_PANEL_LCD };
enum dvbridge_gamut {
    DVBRIDGE_GAMUT_UNSET, DVBRIDGE_GAMUT_BT709, DVBRIDGE_GAMUT_P3_D65, DVBRIDGE_GAMUT_BT2020
};
struct dvbridge_tv_profile {
    double peak_nits;
    enum dvbridge_panel panel;
    enum dvbridge_gamut gamut;
};
#define DVBRIDGE_SDR_POLICY_API 1
enum dvbridge_sdr_preset { DVBRIDGE_SDR_REFERENCE, DVBRIDGE_SDR_BRIGHT, DVBRIDGE_SDR_CUSTOM };
struct dvbridge_sdr_profile {
    enum dvbridge_sdr_preset preset;
    double peak_nits, gamma, black_nits; /* Custom only; presets have fixed values. */
};
bool dvbridge_sdr_target(const struct dvbridge_sdr_profile *profile,
    double *peak_nits, double *gamma, double *black_nits);
enum dvbridge_adaptive_variant {
    DVBRIDGE_ADAPTIVE_A, DVBRIDGE_ADAPTIVE_B_FP32, DVBRIDGE_ADAPTIVE_B_FP16
};
/* Plain value snapshots. Validation neither mutates them nor enables rendering. */
struct dvbridge_policy {
    uint64_t revision;
    enum dvbridge_mode mode;
    struct dvbridge_tv_profile tv;
    enum dvbridge_adaptive_variant adaptive;
    bool master_ipt;
    /* Expert only; other modes do not consume display-black calibration. */
    double expert_black_nits;
    /* Known scanout grid reserves the film ceiling before GUI composition.
     * Zero requests a floating PQ intermediate, with no transport-grid claim. */
    unsigned expert_output_bits;
    bool expert_output_limited;
    struct dvbridge_sdr_profile sdr;
};
struct dvbridge_identity { uint64_t stream, picture, revision; };
enum dvbridge_policy_status {
    DVBRIDGE_POLICY_VALID, DVBRIDGE_POLICY_INVALID_VALUE, DVBRIDGE_POLICY_TV_PROFILE_REQUIRED
};
/* All-zero TV fields mean unset; a partial profile is never valid.
 * Zero peak with explicit panel and gamut is invalid, not a complete profile. */
enum dvbridge_policy_status dvbridge_policy_validate(const struct dvbridge_policy *policy);
bool dvbridge_identity_equal(const struct dvbridge_identity *a, const struct dvbridge_identity *b);

#ifdef __cplusplus
}
#endif
#endif
