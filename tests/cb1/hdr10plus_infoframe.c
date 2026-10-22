/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <errno.h>
#include <linux/types.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
struct device;
#include "hdmi-test.h"
#include "drm_hdr10plus.h"
#include "hdmi-functions.inc"

int main(void)
{
    const u8 packet[31] = {0x81,1,27,0,0x8b,0x84,0x90,0x7e,
        10,1,0,255,4,8,16,32,64,128,0,0,0,0,0,0,0,0,0,0,0,0,0x40};
    union hdmi_vendor_any_infoframe frame;
    memset(&frame, 0xa5, sizeof(frame));
    assert(hdmi_vendor_any_infoframe_unpack(&frame, packet, sizeof(packet)) == 0);
    u8 output[31];
    memset(output, 0xa5, sizeof(output));
    assert(hdmi_vendor_any_infoframe_pack_only(&frame, output, sizeof(output)) == 31);
    assert(!memcmp(packet, output, sizeof(packet)));
    assert(hdmi_vendor_any_infoframe_pack_only(&frame, output, 30) == -ENOSPC);
    assert(!memcmp(packet, output, sizeof(packet)));
    union hdmi_vendor_any_infoframe saved = frame;
    for (unsigned size = 0; size < 31; size++) {
        assert(hdmi_vendor_any_infoframe_unpack(&frame, packet, size) < 0);
        assert(!memcmp(&frame, &saved, sizeof(frame)));
    }
    u8 bad[31];
    memcpy(bad, packet, sizeof(bad));
    bad[15] ^= 1;
    assert(hdmi_vendor_any_infoframe_unpack(&frame, bad, sizeof(bad)) < 0);
    assert(!memcmp(&frame, &saved, sizeof(frame)));
    puts("hdr10plus HDMI vendor round trip: pass");
}
