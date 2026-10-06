/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_policy.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    assert(dvbridge_policy_validate(NULL) == DVBRIDGE_POLICY_INVALID_VALUE);
    for (int mode = DVBRIDGE_MODE_DISABLED; mode <= DVBRIDGE_MODE_ENHANCED_DV; ++mode) {
        for (int enhancement = DVBRIDGE_ENHANCEMENT_NATURAL;
             enhancement <= DVBRIDGE_ENHANCEMENT_INTENSE; ++enhancement) {
            struct dvbridge_policy p = {.revision = UINT64_MAX, .mode = mode,
                                       .enhancement = enhancement};
            const bool required = mode >= DVBRIDGE_MODE_HDR10_EXPERT;
            assert(dvbridge_policy_validate(&p) == (required ?
                   DVBRIDGE_POLICY_TV_PROFILE_REQUIRED : DVBRIDGE_POLICY_VALID));
            p.tv.panel = DVBRIDGE_PANEL_OLED;
            assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_TV_PROFILE_REQUIRED);
            p.tv.peak_nits = 1000;
            assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_TV_PROFILE_REQUIRED);
            p.tv.gamut = DVBRIDGE_GAMUT_BT2020;
            struct dvbridge_policy before = p;
            assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_VALID);
            assert(!memcmp(&before, &p, sizeof(p)));
            const double invalid[] = {NAN, INFINITY, -INFINITY, -1, 0, 10000.01};
            for (unsigned i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i) {
                p.tv.peak_nits = invalid[i];
                assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_INVALID_VALUE);
            }
            for (int panel = DVBRIDGE_PANEL_UNSET; panel <= DVBRIDGE_PANEL_LCD; ++panel)
                for (int gamut = DVBRIDGE_GAMUT_BT709; gamut <= DVBRIDGE_GAMUT_BT2020; ++gamut) {
                    p.tv = (struct dvbridge_tv_profile){10000, panel, gamut};
                    assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_VALID);
                    p.tv.peak_nits = 0.001;
                    assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_VALID);
                }
            p.tv = (struct dvbridge_tv_profile){NAN, 0, 0};
            assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_INVALID_VALUE);
            p.tv = (struct dvbridge_tv_profile){0, -1, 0};
            assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_INVALID_VALUE);
            p.tv = (struct dvbridge_tv_profile){0, 0, 99};
            assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_INVALID_VALUE);
            p.tv = (struct dvbridge_tv_profile){1000, 99, DVBRIDGE_GAMUT_BT709};
            assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_INVALID_VALUE);
        }
    }
    struct dvbridge_policy p = {0};
    const int unknown[] = {-1, 5, 99};
    for (unsigned i = 0; i < sizeof(unknown)/sizeof(unknown[0]); ++i) {
        p.mode = unknown[i];
        assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_INVALID_VALUE);
        p.mode = DVBRIDGE_MODE_DISABLED; p.enhancement = unknown[i];
        assert(dvbridge_policy_validate(&p) == DVBRIDGE_POLICY_INVALID_VALUE);
        p.enhancement = DVBRIDGE_ENHANCEMENT_NATURAL;
    }
    puts("PASS: preference bounds, complete profile and immutable validation");
}
