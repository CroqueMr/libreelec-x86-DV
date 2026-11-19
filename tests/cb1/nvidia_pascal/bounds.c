/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <string.h>
#include "nvkms-cb1-vsif.h"

int main(void)
{
    struct NvKmsCb1Vsif packet = {0};
    assert(nvCb1VsifValid(&packet));
    packet.payloadSize = 27;
    packet.payload[0] = 0x46;
    packet.payload[1] = 0xd0;
    packet.payload[3] = 2;
    assert(nvCb1VsifValid(&packet));
    packet.payloadSize = 28;
    assert(!nvCb1VsifValid(&packet));
    packet.payloadSize = 1;
    assert(!nvCb1VsifValid(&packet));
    packet.payloadSize = 2;
    assert(!nvCb1VsifValid(&packet));
    packet.payloadSize = 3;
    assert(nvCb1VsifValid(&packet));
    packet.payloadSize = ~0U;
    assert(!nvCb1VsifValid(&packet));
    assert(!nvCb1VsifValid(NULL));
    return 0;
}
