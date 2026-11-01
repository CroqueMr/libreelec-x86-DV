/* SPDX-License-Identifier: GPL-2.0-or-later
 * CM block field widths: dovi_tool d4ad4ba7, MIT.
 * See LICENSES/MIT-dovi-tool.txt. The wire contract is recorded in
 * docs/GPL2-MIGRATION.md; no display-mapping algorithm is implemented here.
 */
#ifndef MPV_DVBRIDGE_CM4_H
#define MPV_DVBRIDGE_CM4_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>

/* Expand packed fields to byte/word transport fields. The destination holds
 * 32 bytes. Failure returns -1; no destination content is valid after failure. */
static int dvbridge_cm4_wire(unsigned level, const uint8_t *raw, size_t length, uint8_t out[32])
{
    static const uint8_t l3[] = {12,12,12};
    static const uint8_t l4[] = {12,12};
    static const uint8_t l8[] = {8,12,12,12,12,12,12,12,12,8,8,8,8,8,8,8,8,8,8,8,8};
    static const uint8_t l9[] = {8,16,16,16,16,16,16,16,16};
    static const uint8_t l10[] = {8,12,12,8,16,16,16,16,16,16,16,16};
    static const uint8_t bytes[] = {8,8,8,8};
    const uint8_t *widths;
    unsigned fields;
    if (!raw || !out || length > 32)
        return -1;
    switch (level) {
    case 3:
        if (length != 5) return -1;
        widths = l3; fields = 3; break;
    case 4:
        if (length != 3) return -1;
        widths = l4; fields = 2; break;
    case 8:
        switch (length) {
        case 10: fields = 7; break;
        case 12: fields = 8; break;
        case 13: fields = 9; break;
        case 19: fields = 15; break;
        case 25: fields = 21; break;
        default: return -1;
        }
        widths = l8; break;
    case 9:
        if ((length != 1 && length != 17) || ((raw[0] == 255) != (length == 17)))
            return -1;
        widths = l9; fields = length == 17 ? 9 : 1; break;
    case 10:
        if ((length != 5 && length != 21) || ((raw[4] == 255) != (length == 21)))
            return -1;
        widths = l10; fields = length == 21 ? 12 : 4; break;
    case 11:
        if (length != 4 || raw[0] > 15 || (raw[1] & 7) || raw[2] || raw[3])
            return -1;
        widths = bytes; fields = 4; break;
    case 254:
        if (length != 2) return -1;
        widths = bytes; fields = 2; break;
    default:
        return -1;
    }
    unsigned position = 0, written = 0;
    for (unsigned field = 0; field < fields; ++field) {
        unsigned left = widths[field], value = 0;
        while (left) {
            unsigned available = 8 - position % 8;
            unsigned take = left < available ? left : available;
            value = (value << take) |
                ((raw[position / 8] >> (available - take)) & ((1U << take) - 1));
            position += take;
            left -= take;
        }
        if (widths[field] > 8)
            out[written++] = value >> 8;
        out[written++] = value;
    }
    if (position % 8 && (raw[position / 8] & ((1U << (8 - position % 8)) - 1)))
        return -1;
    return (int)written;
}
#endif
