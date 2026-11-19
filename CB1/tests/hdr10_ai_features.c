/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "cb1_hdr10_features.h"
#include "cb1_native_prefix_fixtures.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

static void invalid(const struct cb1_hdr10_descriptor *samples, size_t count,
                    const uint16_t base[3])
{
    float output[222];
    memset(output, 0x5a, sizeof(output));
    float before[222];
    memcpy(before, output, sizeof(output));
    assert(!cb1_hdr10_prefix(samples, count, base, true, true, output));
    assert(memcmp(output, before, sizeof(output)) == 0);
}

int main(void)
{
    for (size_t i = 0; i < sizeof(cb1_prefix_fixtures)/sizeof(cb1_prefix_fixtures[0]); ++i) {
        const struct cb1_prefix_fixture *f = &cb1_prefix_fixtures[i];
        float output[222];
        assert(cb1_hdr10_prefix(f->samples, f->count, f->base, f->left, f->right, output));
        for (unsigned field = 0; field < 222; ++field) {
            if (output[field] != f->expected[field])
                fprintf(stderr, "prefix %zu field %u: %.9g != %.9g\n",
                        i, field, output[field], f->expected[field]);
            assert(output[field] == f->expected[field]);
        }
    }
    uint16_t base[] = {0, 819, 2081};
    struct cb1_hdr10_descriptor samples[2] = {{.pts=0}, {.pts=.5}};
    invalid(NULL, 2, base);
    invalid(samples, 0, base);
    invalid(samples, 2, NULL);
    samples[1].pts = 1.01;
    invalid(samples, 2, base);
    samples[1].pts = samples[0].pts;
    invalid(samples, 2, base);
    samples[1].pts = .5;
    samples[1].global[12] = NAN;
    invalid(samples, 2, base);
    samples[1].global[12] = 0;
    samples[1].spatial[37] = INFINITY;
    invalid(samples, 2, base);
    printf("Exact native compact-prefix parity: %zu independent prefixes\n",
           sizeof(cb1_prefix_fixtures)/sizeof(cb1_prefix_fixtures[0]));
    return 0;
}
