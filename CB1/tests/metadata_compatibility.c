/* SPDX-License-Identifier: MIT */
#include "dvbridge_metadata_bounds.h"
#include "mpv_dvbridge_cm4.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int beta5_wire(unsigned, const uint8_t *, size_t, uint8_t *);
bool beta5_bounds(const void *, size_t);
static uint32_t random_state = 0x56ac7139;
static uint32_t next_value(void)
{
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
}

static unsigned accepted, rejected;
static void compare(unsigned level, const uint8_t *raw, size_t size)
{
    unsigned char expected[32] = {0}, actual[32] = {0};
    int a = beta5_wire(level, raw, size, expected);
    int b = dvbridge_cm4_wire(level, raw, size, actual);
    assert(a == b);
    if (a >= 0) {
        assert(a <= 32 && memcmp(expected, actual, (size_t)a) == 0);
        ++accepted;
    } else {
        ++rejected;
    }
}

int main(void)
{
    uint8_t raw[33];
    for (unsigned level = 0; level <= 255; ++level) {
        compare(level, NULL, 0);
        for (size_t n = 0; n <= sizeof(raw); ++n) {
            memset(raw, 0, sizeof(raw));
            compare(level, raw, n);
            for (size_t bit = 0; bit < n * 8; ++bit) {
                raw[bit / 8] = 1U << (bit % 8);
                compare(level, raw, n);
                raw[bit / 8] = 0;
            }
        }
    }
    const unsigned levels[] = {3,4,8,9,10,11,254};
    const size_t lengths[] = {1,2,3,4,5,10,12,13,17,19,21,25,32};
    for (unsigned i = 0; i < 1000000; ++i) {
        for (size_t n = 0; n < sizeof(raw); ++n)
            raw[n] = next_value();
        compare(levels[i % 7], raw, lengths[(i / 7) % 13]);
    }
    AVDOVIMetadata metadata = {0};
    size_t bounds_cases = 0;
    for (unsigned i = 0; i < 250000; ++i) {
        metadata.header_offset = 64;
        metadata.mapping_offset = 4096;
        metadata.color_offset = 16384;
        metadata.ext_block_offset = 32768;
        metadata.ext_block_size = sizeof(AVDOVIDmData);
        metadata.num_ext_blocks = i % 33;
        size_t size = 131072;
        size_t value = i % 2 ? next_value() % 131073 : SIZE_MAX - i % 128;
        switch (i % 9) {
        case 0: metadata.header_offset = value; break;
        case 1: metadata.mapping_offset = value; break;
        case 2: metadata.color_offset = value; break;
        case 3: metadata.ext_block_offset = value; break;
        case 4: metadata.ext_block_size = value; break;
        case 5: metadata.num_ext_blocks = (int)(value % 520) - 20; break;
        case 6: size = value; break;
        case 7: metadata.num_ext_blocks = 0; break;
        default: break;
        }
        assert(beta5_bounds(&metadata, size) == dvbridge_metadata_bounds(&metadata, size));
        ++bounds_cases;
    }
    assert(!dvbridge_metadata_bounds(NULL, SIZE_MAX));
    assert(dvbridge_cm4_wire(3, raw, SIZE_MAX, raw) == -1);
    assert(dvbridge_cm4_wire(3, raw, 5, NULL) == -1);
    printf("{\"wire_accepted\":%u,\"wire_rejected\":%u,\"bounds_cases\":%zu,\"exact\":true}\n",
           accepted, rejected, bounds_cases);
    return 0;
}
