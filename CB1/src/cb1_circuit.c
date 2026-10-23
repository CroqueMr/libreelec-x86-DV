/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stddef.h>
#include "cb1_circuit.h"

const char *cb1_engine_version(void)
{
    return "CB1 0.3";
}

const char *cb1_circuit_version(enum cb1_circuit circuit)
{
    static const char *const versions[CB1_CIRCUIT_COUNT] = {
        [CB1_DV_DV_REFERENCE] = "CB1-DVDVR.0.5",
        [CB1_DV_HDR10_BASIC] = "CB1-DVHDR10B.0.4",
        [CB1_DV_HDR10_EXPERT] = "CB1-DVHDR10X.0.9",
        [CB1_DV_DV_ADAPTIVE] = "CB1-DVDVA.0.9",
        [CB1_HDR10_DV_REFERENCE] = "CB1-HDR10DVR.0.1.2",
        [CB1_HDR10_DV_ADAPTIVE] = "CB1-HDR10DVA.0.5",
        [CB1_DV_DV_MASTER_REFERENCE] = "CB1-DVDVMR.0.5",
        [CB1_DV_DV_ADAPTIVE_B] = "CB1-DVDVA.0.11",
    };
    return (unsigned)circuit < CB1_CIRCUIT_COUNT ? versions[circuit] : NULL;
}
