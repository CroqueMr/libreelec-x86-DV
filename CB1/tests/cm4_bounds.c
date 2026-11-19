/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Encoding/bounds checks, not Dolby conformance or HDMI interoperability. */
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include "mpv_dvbridge_cm4.h"

static unsigned seed = 20260920;
static unsigned next_u32(void)
{
    seed ^= seed << 13;
    seed ^= seed >> 17;
    seed ^= seed << 5;
    return seed;
}

int main(void)
{
    uint8_t raw[32] = {0}, out[32] = {0};
    const uint8_t packed[] = {0x12, 0x34, 0x56, 0x78, 0x90};
    const uint8_t expected[] = {0x01, 0x23, 0x04, 0x56, 0x07, 0x89};
    assert(dvbridge_cm4_wire(3, packed, sizeof(packed), out) == 6);
    assert(!memcmp(out, expected, sizeof(expected)));
    /* Optional fields present with value zero must not be dropped. */
    assert(dvbridge_cm4_wire(8, raw, 10, out) == 13);
    assert(dvbridge_cm4_wire(8, raw, 12, out) == 15);
    assert(dvbridge_cm4_wire(8, raw, 13, out) == 17);
    assert(dvbridge_cm4_wire(8, raw, 19, out) == 23);
    assert(dvbridge_cm4_wire(8, raw, 25, out) == 29);
    assert(dvbridge_cm4_wire(3, NULL, 5, out) == -1);
    assert(dvbridge_cm4_wire(3, raw, 5, NULL) == -1);
    assert(dvbridge_cm4_wire(3, raw, SIZE_MAX, out) == -1);
    const unsigned levels[] = {3, 4, 8, 9, 10, 11, 254, 255};
    unsigned valid = 0, rejected = 0;
    for (unsigned k = 0; k < 1000000; k++) {
        size_t n = next_u32() % 65;
        uint8_t *input = malloc(n ? n : 1), *output = malloc(32);
        assert(input && output);
        for (size_t j = 0; j < n; j++) input[j] = next_u32() & 255;
        unsigned level = k % 2 ? levels[next_u32() % 8] : next_u32() % 256;
        int size = dvbridge_cm4_wire(level, input, n, output);
        assert(size >= -1 && size <= 32);
        valid += size >= 0; rejected += size < 0;
        free(input); free(output);
    }
    printf("{\"passed\":true,\"iterations\":1000000,\"accepted\":%u,\"rejected\":%u}\n", valid, rejected);
    return 0;
}
