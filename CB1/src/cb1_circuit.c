/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <stddef.h>
#include "cb1_circuit.h"

const char *cb1_engine_version(void)
{
    return "CB1 0.1";
}

const char *cb1_circuit_version(enum cb1_circuit circuit)
{
    static const char *const versions[CB1_CIRCUIT_COUNT] = {
        [CB1_DV_DV_REFERENCE] = "CB1-DVDVR.0.1",
        [CB1_DV_HDR10_BASIC] = "CB1-DVHDR10B.0.1",
        [CB1_DV_HDR10_EXPERT] = "CB1-DVHDR10X.0.3",
        [CB1_DV_DV_NATURAL] = "CB1-DVDVEa.0.3",
        [CB1_DV_DV_INTENSE] = "CB1-DVDVEb.0.3",
        [CB1_HDR10_DV_REFERENCE] = "CB1-HDR10DVR.0.1.1",
        [CB1_HDR10_DV_NATURAL] = "CB1-HDR10DVEa.0.1.1",
        [CB1_HDR10_DV_INTENSE] = "CB1-HDR10DVEb.0.1.1"
    };
    return (unsigned)circuit < CB1_CIRCUIT_COUNT ? versions[circuit] : NULL;
}
