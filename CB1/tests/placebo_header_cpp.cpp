/* SPDX-License-Identifier: MIT */
#include <cassert>
#include <initializer_list>
extern "C" {
#include "dvbridge_placebo.h"
}
int main()
{
    for (const auto transfer : {PL_COLOR_TRC_HLG, PL_COLOR_TRC_PQ}) {
        const auto color = cb1_hlg_reference_color(transfer);
        auto expected = pl_hdr_metadata_empty;
        expected.prim = *pl_raw_primaries_get(PL_COLOR_PRIM_BT_2020);
        expected.max_luma = 1000;
        assert(color.primaries == PL_COLOR_PRIM_BT_2020 && color.transfer == transfer);
        assert(pl_hdr_metadata_equal(&color.hdr, &expected));
    }
}
