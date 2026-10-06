/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef DVBRIDGE_POLICY_H
#define DVBRIDGE_POLICY_H
#include <stdbool.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

enum dvbridge_mode {
    DVBRIDGE_MODE_DISABLED, DVBRIDGE_MODE_STANDARD, DVBRIDGE_MODE_HDR10_BASIC,
    DVBRIDGE_MODE_HDR10_EXPERT, DVBRIDGE_MODE_ENHANCED_DV
};
enum dvbridge_enhancement {
    DVBRIDGE_ENHANCEMENT_NATURAL=0, DVBRIDGE_ENHANCEMENT_SIGNATURE=1,
    DVBRIDGE_ENHANCEMENT_INTENSE=DVBRIDGE_ENHANCEMENT_SIGNATURE /* Deprecated source alias. */
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
/* Plain value snapshots. Validation neither mutates them nor enables rendering. */
struct dvbridge_policy {
    uint64_t revision;
    enum dvbridge_mode mode;
    enum dvbridge_enhancement enhancement;
    struct dvbridge_tv_profile tv;
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
