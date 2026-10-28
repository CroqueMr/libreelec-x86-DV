/* SPDX-License-Identifier: MIT */
/* Exercise the R580 VSIF builder and Pascal EVO1 HDMI packer. */
#include <stdlib.h>
#include <string.h>
#include "nvkms-hdmi.c"
#include "nvkms-evo1.h"
#undef NDEBUG
#include <assert.h>

static unsigned writes, disables;
static NvU8 wire[36];

void *nvkms_memset(void *p, NvU8 c, size_t n) { return memset(p, c, n); }
void *nvkms_memcpy(void *p, const void *s, size_t n) { return memcpy(p, s, n); }
void *nvkms_alloc(size_t n, NvBool zero) { return zero ? calloc(1, n) : malloc(n); }
void nvkms_free(void *p, size_t n) { (void)n; free(p); }
void *nvInternalAlloc(size_t n, NvBool zero) { return nvkms_alloc(n, zero); }
void nvInternalFree(void *p) { free(p); }

NVT_STATUS NvTiming_ConstructVendorSpecificInfoframe(NVT_EDID_INFO *e,
    NVT_VENDOR_SPECIFIC_INFOFRAME_CTRL *c, NVT_VENDOR_SPECIFIC_INFOFRAME *p)
{
    (void)e; (void)c; (void)p;
    abort(); /* The private VSIF path must not enter HDMI 1.4/3D construction. */
}

NVHDMIPKT_RESULT NvHdmiPkt_PacketWrite(NvHdmiPkt_Handle h, NvU32 sd, NvU32 display,
    NvU32 head, NVHDMIPKT_TYPE type, NVHDMIPKT_TC tc, NvU32 size, const NvU8 *const data)
{
    (void)h; (void)tc;
    assert(sd == 0 && display == 7 && head == 0);
    assert(type == NVHDMIPKT_TYPE_VENDOR_SPECIFIC_INFOFRAME);
    assert(size == 30);
    memcpy(wire, data, 31);
    writes++;
    return NVHDMIPKT_SUCCESS;
}

static void disable(const NVDispEvoRec *d, NvU32 head, NvU8 type)
{
    (void)d;
    assert(head == 0 && type == NVT_INFOFRAME_TYPE_VENDOR_SPECIFIC);
    disables++;
}

int main(void)
{
    NVDevEvoRec *dev = calloc(1, sizeof(*dev));
    NVDispEvoRec *disp = calloc(1, sizeof(*disp));
    NVEvoHAL hal = {.SendHdmiInfoFrame = nvEvo1SendHdmiInfoFrame,
                    .DisableHdmiInfoFrame = disable};
    NVDispHeadInfoFrameStateEvoRec info = {0};
    NVT_EDID_INFO edid = {0};
    assert(dev && disp);
    dev->hal = &hal;
    disp->pDevEvo = dev;
    disp->headState[0].activeRmId = 7;
    struct NvKmsCb1Vsif *vsif = &disp->headState[0].hdmiVsifMetadata;
    vsif->payloadSize = 27;
    vsif->payload[0] = 0x46;
    vsif->payload[1] = 0xd0;
    vsif->payload[3] = 2;
    SendVendorSpecificInfoFrame(disp, 0, &info, &edid);
    const NvU8 expected[31] = {0x81, 0x01, 0x1b, 0x4b, 0x46, 0xd0, 0, 2};
    assert(writes == 1 && disables == 0);
    assert(memcmp(wire, expected, sizeof(expected)) == 0);
    vsif->payloadSize = 28;
    SendVendorSpecificInfoFrame(disp, 0, &info, &edid);
    assert(writes == 1 && disables == 0);
    vsif->payloadSize = 0;
    SendVendorSpecificInfoFrame(disp, 0, &info, &edid);
    assert(writes == 1 && disables == 1);
    free(disp); free(dev);
    return 0;
}
