/* SPDX-License-Identifier: GPL-3.0-or-later */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "mpv_dvbridge_cm4.h"

int main(void)
{
    /* Public L3 bitstream order is minimum, maximum, average, then zero padding. */
    const uint16_t expected[3] = {37, 3128, 1412};
    uint64_t bits = ((uint64_t)expected[0] << 28) |
                    ((uint64_t)expected[1] << 16) | ((uint64_t)expected[2] << 4);
    uint8_t raw[5], wire[32] = {0};
    for (unsigned i = 0; i < 5; i++)
        raw[i] = bits >> (32 - 8*i);
    assert(dvbridge_cm4_wire(3, raw, sizeof(raw), wire) == 6);
    for (unsigned i = 0; i < 3; i++)
        assert(((unsigned)wire[2*i] << 8 | wire[2*i+1]) == expected[i]);
    uint64_t decoded = 0;
    for (unsigned i = 0; i < 5; i++)
        decoded = decoded << 8 | raw[i];
    assert((decoded >> 28 & 4095) == expected[0]);
    assert((decoded >> 16 & 4095) == expected[1]);
    assert((decoded >> 4 & 4095) == expected[2]);
    raw[4] |= 1;
    assert(dvbridge_cm4_wire(3, raw, sizeof(raw), wire) == -1);
    assert(dvbridge_cm4_wire(3, raw, sizeof(raw)-1, wire) == -1);
    return 0;
}
