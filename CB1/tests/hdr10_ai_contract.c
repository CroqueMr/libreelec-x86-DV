/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include <string.h>
#include "cb1_circuit.h"
#if defined(CB1_EXPECT_HDR10_AI) && !defined(CB1_HAS_HDR10_AI)
#error "AI-enabled consumers require the matched native API"
#endif
#if !defined(CB1_EXPECT_HDR10_AI) && defined(CB1_HAS_HDR10_AI)
#error "Native consumers must not enable AI implicitly"
#endif

int main(void)
{
    const char *expected[] = {
        "CB1-DVDVR.0.1", "CB1-DVHDR10B.0.1", "CB1-DVHDR10X.0.3",
        "CB1-DVDVEa.0.3", "CB1-DVDVEb.0.3",
        NULL, NULL,
        "CB1-HDR10DVR.0.1.1", "CB1-HDR10DVEa.0.1.1", "CB1-HDR10DVEb.0.1.1"
    };
    assert(strcmp(cb1_engine_version(), "CB1 0.1") == 0);
    assert(CB1_CIRCUIT_COUNT == 10);
    for (int i = 0; i < CB1_CIRCUIT_COUNT; ++i)
        if (expected[i]) assert(strcmp(cb1_circuit_version((enum cb1_circuit)i), expected[i]) == 0);
        else assert(cb1_circuit_version((enum cb1_circuit)i) == NULL);
    assert(cb1_circuit_version((enum cb1_circuit)-1) == NULL);
    assert(cb1_circuit_version(CB1_CIRCUIT_COUNT) == NULL);
    return 0;
}
