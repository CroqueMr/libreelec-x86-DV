/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <stddef.h>
#include "cb1_circuit.h"

const char *cb1_engine_version(void)
{
    return "CB1 1.0";
}

const char *cb1_circuit_version(enum cb1_circuit circuit)
{
    static const char *const versions[CB1_CIRCUIT_COUNT] = {
        [CB1_DV_DV_REFERENCE] = "CB1-DVDVR.1.0",
        [CB1_DV_HDR10_BASIC] = "CB1-DVHDR10B.1.0",
        [CB1_DV_HDR10_EXPERT] = "CB1-DVHDR10X.1.0",
        [CB1_DV_DV_ADAPTIVE] = "CB1-DVDVA.1.0",
        [CB1_HDR10_DV_REFERENCE] = "CB1-HDR10DVR.1.0",
        [CB1_HDR10_DV_ADAPTIVE] = "CB1-HDR10DVA.1.0",
        [CB1_DV_DV_MASTER_REFERENCE] = "CB1-DVDVMR.1.0",
        [CB1_DV_DV_ADAPTIVE_B] = "CB1-DVDVAB.1.0",
        [CB1_DV_DV_MASTER_IPT] = "CB1-DVDVMRI.1.0",
        [CB1_DV_HDR10PLUS] = "CB1-DVHDR10P.1.0",
        [CB1_HDR10PLUS_DV_REFERENCE] = "CB1-HDR10PDVR.1.0",
        [CB1_DV_SDR] = "CB1-DVSDR.1.0",
        [CB1_HDR10_SDR] = "CB1-HDR10SDR.1.0",
        [CB1_HLG_SDR] = "CB1-HLGSDR.1.0",
        [CB1_HLG_DV_REFERENCE] = "CB1-HLGDVR.1.0",
        [CB1_DV_DV_LLDV] = "CB1-DVLLDV.1.0",
    };
    return (unsigned)circuit < CB1_CIRCUIT_COUNT ? versions[circuit] : NULL;
}
