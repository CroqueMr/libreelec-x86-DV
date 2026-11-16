"""Execute R615's actual native LLDV format, bandwidth and Dolby EDID gates."""
import os
from pathlib import Path
import unittest

from test_hdr10_transport import function
import test_nvidia_native_hdr as native_hdr


@unittest.skipUnless(os.environ.get('CB1_NVIDIA_SOURCE'), 'matched R615 source required')
class NvidiaNativeLldvFormats(unittest.TestCase):
    compile_run = native_hdr.NvidiaNativeHdr.compile_run

    def native(self, path, *names):
        source = (Path(os.environ['CB1_NVIDIA_SOURCE']) / path).read_text()
        return '\n'.join(function(source, name) for name in names)

    def header(self):
        return (Path(os.environ['CB1_NVIDIA_SOURCE']) /
                'src/common/inc/nvkms-lldv-formats.h').read_text()

    def test_vendor_depth_selector_rejects_turing_ten_even_with_422_twelve_ceiling(self):
        native = self.native('src/nvidia-modeset/src/nvkms-evo.c', 'ChooseColorBpc')
        self.compile_run(r'''
#include <assert.h>
typedef int NvBool;
#define nvAssert assert
enum NvKmsDpyAttributeColorBpcValue {NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_UNKNOWN=0,
 NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_8=8,NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_10=10,
 NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_12=12};
typedef struct {int hdmi,depth30;}NVDpyEvoRec;
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
static int nvDpyIsHdmiDepth30Evo(const NVDpyEvoRec*d){return d->depth30;}
''' + native + r'''
int main(void){
 NVDpyEvoRec d={1,0};
 /* The vendor RGB, 422 and 444 selectors all call this same depth function.
    A 422 ceiling of 12 does not override its GPU/HDMI 10-bpc rejection. */
 assert(ChooseColorBpc(&d,10,12,8)==NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_UNKNOWN);
 assert(ChooseColorBpc(&d,12,12,8)==12);
 d.depth30=1;assert(ChooseColorBpc(&d,10,12,8)==10);
 d.hdmi=0;d.depth30=0;assert(ChooseColorBpc(&d,10,12,8)==10);
}
''')

    def test_all_six_native_formats_are_exact_requests(self):
        native = self.native('src/nvidia-modeset/kapi/src/nvkms-kapi.c', 'ConfigureLldvOutput')
        self.compile_run(r'''
#include <assert.h>
typedef unsigned NvU32;typedef int NvBool;
#define NV_TRUE 1
#define NV_FALSE 0
#define TRUE 1
enum NvKmsOutputTf {NVKMS_OUTPUT_TF_NONE,NVKMS_OUTPUT_TF_PQ};
enum {NVKMS_OUTPUT_COLORIMETRY_DEFAULT,NVKMS_OUTPUT_COLORIMETRY_BT2100};
enum {NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_FORMAT_RGB,
 NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_FORMAT_YCbCr422,
 NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_FORMAT_YCbCr444};
enum {NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_FULL,NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED};
#define NV_KMS_DPY_ATTRIBUTE_REQUESTED_DITHERING_DISABLED 0
struct NvKmsKapiHeadModeSetConfig {
 struct {unsigned char payload[1];unsigned payloadSize;}hdmiVsifMetadata;
 unsigned colorBpc,colorimetry,numDisplays,lldvFormat;
 struct {int enabled;}hdrInfoFrame;struct {int enabled,deepColor;}cb1Hdr;
 struct {int state;}dithering;int postcompColorPassthrough;
};
struct NvKmsSetModeOneHeadRequest {int colorFormatSpecified,colorFormat,
 colorRangeSpecified,colorRange;struct {struct {int specified;}dithering;}flip;};
static int nvDoviLowLatency(const unsigned char*p,unsigned n){return n && p[0];}
''' + self.header() + native + r'''
int main(void){
 /* DRM enums 3..8: 42212, RGB12, 44410, 44412, 42210, RGB10. */
 const unsigned depth[]={12,12,10,12,10,10};
 const unsigned encoding[]={1,0,2,2,1,0};
 const unsigned range[]={1,0,1,1,1,0};
 for(unsigned i=0;i<6;i++){
  struct NvKmsKapiHeadModeSetConfig c={.hdmiVsifMetadata={{1},1},
   .colorBpc=depth[i],.colorimetry=1,.numDisplays=1,.lldvFormat=3+i};
  struct NvKmsSetModeOneHeadRequest r={0};
  assert(ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&r));
  assert(r.colorFormatSpecified && r.colorRangeSpecified && r.flip.dithering.specified);
  assert((unsigned)r.colorFormat==encoding[i] && (unsigned)r.colorRange==range[i]);
  c.colorBpc=depth[i]==12?10:12;assert(!ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&r));
  c.colorBpc=depth[i];c.colorimetry=0;assert(!ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&r));
  c.colorimetry=1;c.postcompColorPassthrough=1;assert(!ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&r));
 }
 for(unsigned format=1;format<=2;format++){
  struct NvKmsKapiHeadModeSetConfig c={.hdmiVsifMetadata={{1},1},
   .colorBpc=8,.colorimetry=0,.numDisplays=1,.lldvFormat=format,.postcompColorPassthrough=1};
  struct NvKmsSetModeOneHeadRequest r={0};
  assert(ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&r));
  assert(r.colorFormat==0 && r.colorRange==0); /* Old packed paths remain byte-preserving. */
 }
}
''')

    def test_capabilities_respect_tmds_depth_scdc_and_port(self):
        native = self.native('src/nvidia-modeset/src/nvkms-hdmi.c',
                             'GetMaxPossibleTmdsPixelClockKHz', 'nvNativeLldvFormats')
        self.compile_run(r'''
#include <assert.h>
#include <stddef.h>
typedef unsigned NvU32;typedef int NvBool;
#define nvAssert assert
#define ct_assert(c) _Static_assert(c,#c)
#define NV_MIN(a,b) ((a)<(b)?(a):(b))
enum NvKmsDpyAttributeColorBpcValue {NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_UNKNOWN=0,
 NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_8=8,NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_10=10,
 NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_12=12,NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_MAX=12};
enum {NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_FORMAT_RGB,
 NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_FORMAT_YCbCr422,NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_FORMAT_YCbCr444};
enum {NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_FULL,NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED};
#define NVKMS_OUTPUT_COLORIMETRY_BT2100 1
#define NVKMS_CONNECTOR_SIGNAL_FORMAT_TMDS 1
#define NVT_CEA861_CAP_YCbCr_444 4
typedef struct {unsigned format,range,bpc,colorimetry;}NVDpyAttributeColor;
typedef struct {struct {enum NvKmsDpyAttributeColorBpcValue maxBpc;}rgb444,yuv444,yuv422;}NvKmsDpyOutputColorFormatInfo;
typedef struct {struct {int dc_y444;}hdmiLlcInfo;struct {unsigned basic_caps;}ext861;
 struct {int scdc_present;}hdmiForumInfo;}NVT_EDID_INFO;
typedef struct {unsigned numSubDevices;struct {unsigned hdmiTmds10BpcMaxPClkMHz;}caps;}NVDevEvoRec;
typedef struct {NVDevEvoRec*pDevEvo;}NVDispEvoRec;
typedef struct {unsigned signalFormat;}NVConnectorEvoRec;
typedef struct {struct {int valid;NVT_EDID_INFO info;}parsedEdid;NVDispEvoRec*pDispEvo;
 NVConnectorEvoRec*pConnectorEvo;unsigned maxSingleLinkPixelClockKHz;int hdmi,dp;}NVDpyEvoRec;
static int ten=1;
static NvKmsDpyOutputColorFormatInfo caps={{12},{12},{12}};
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
static int nvDpyUsesDPLib(const NVDpyEvoRec*d){return d->dp;}
static int nvDpyIsHdmiDepth30Evo(const NVDpyEvoRec*d){return ten && d->hdmi;}
static int nvDpyIsHdmiDepth36Evo(const NVDpyEvoRec*d){return d->hdmi && caps.rgb444.maxBpc==12;}
static NvKmsDpyOutputColorFormatInfo nvDpyGetOutputColorFormatInfo(const NVDpyEvoRec*d){(void)d;return caps;}
''' + self.header() + native + r'''
int main(void){
 NVDevEvoRec dev={.numSubDevices=1};NVDispEvoRec disp={&dev};NVConnectorEvoRec conn={1};
 NVDpyEvoRec d={.parsedEdid={1,{{1},{4},{1}}},.pDispEvo=&disp,.pConnectorEvo=&conn,
  .maxSingleLinkPixelClockKHz=600000,.hdmi=1};
 const unsigned all=0x1f8,only422=(1u<<3)|(1u<<7),only12=(1u<<3)|(1u<<4)|(1u<<6);
 assert(nvNativeLldvFormats(&d)==all);assert(!nvNativeLldvFormats(NULL));
 ten=0;assert(nvNativeLldvFormats(&d)==only12);ten=1; /* Turing: 12 is not proof of 10. */
 d.maxSingleLinkPixelClockKHz=340000;assert(nvNativeLldvFormats(&d)==only422);
 d.maxSingleLinkPixelClockKHz=371249;assert(nvNativeLldvFormats(&d)==only422);
 d.maxSingleLinkPixelClockKHz=371250;assert(nvNativeLldvFormats(&d)==(only422|(1u<<5)|(1u<<8)));
 d.maxSingleLinkPixelClockKHz=445499;assert(nvNativeLldvFormats(&d)==(only422|(1u<<5)|(1u<<8)));
 d.maxSingleLinkPixelClockKHz=445500;assert(nvNativeLldvFormats(&d)==all);
 d.maxSingleLinkPixelClockKHz=296999;assert(!nvNativeLldvFormats(&d));d.maxSingleLinkPixelClockKHz=600000;
 dev.caps.hdmiTmds10BpcMaxPClkMHz=296;assert(nvNativeLldvFormats(&d)==(only12|(1u<<7)));
 dev.caps.hdmiTmds10BpcMaxPClkMHz=0;
 d.parsedEdid.info.hdmiForumInfo.scdc_present=0;assert(nvNativeLldvFormats(&d)==only422);
 d.parsedEdid.info.hdmiForumInfo.scdc_present=1;
 d.parsedEdid.info.hdmiLlcInfo.dc_y444=0;assert(nvNativeLldvFormats(&d)==(all&~((1u<<5)|(1u<<6))));
 d.parsedEdid.info.hdmiLlcInfo.dc_y444=1;d.parsedEdid.info.ext861.basic_caps=0;
 assert(nvNativeLldvFormats(&d)==(all&~((1u<<5)|(1u<<6))));d.parsedEdid.info.ext861.basic_caps=4;
 caps.rgb444.maxBpc=8;caps.yuv444.maxBpc=8;assert(nvNativeLldvFormats(&d)==only422);
 caps.yuv422.maxBpc=8;assert(!nvNativeLldvFormats(&d));caps=(NvKmsDpyOutputColorFormatInfo){{12},{12},{12}};
 d.dp=1;assert(!nvNativeLldvFormats(&d));d.dp=0;
 d.hdmi=0;assert(!nvNativeLldvFormats(&d));d.hdmi=1;
 conn.signalFormat=2;assert(!nvNativeLldvFormats(&d));conn.signalFormat=1;
 dev.numSubDevices=2;assert(!nvNativeLldvFormats(&d));dev.numSubDevices=1;
 d.parsedEdid.valid=0;assert(!nvNativeLldvFormats(&d));
}
''')

    def test_dolby_gate_intersects_depth_and_never_invents_ten_from_twelve(self):
        native = self.native('kernel-open/nvidia-drm/nvidia-drm-connector.c',
                             'nv_drm_native_lldv_formats')
        self.compile_run(r'''
#include <assert.h>
#include <stddef.h>
typedef unsigned NvU32;typedef unsigned char u8;
#define connector_status_connected 1
#define NVKMS_CONNECTOR_TYPE_HDMI 1
struct dvbridge_sink_caps {unsigned lldv,legacy_vsif,depth,twelve;};
struct drm_edid {struct dvbridge_sink_caps caps;};
struct drm_connector {int status;void*dev;};
struct encoder {unsigned hDisplay;};
struct nv_drm_connector {struct drm_connector base;struct drm_edid*edid;struct encoder*nv_detected_encoder;unsigned type;};
struct nv_drm_device {void*pDevice;};
static const struct nv_drm_connector*to_nv_connector(const struct drm_connector*c){return (const void*)c;}
static struct nv_drm_device*to_nv_device(void*d){return d;}
static const void*drm_edid_raw(const struct drm_edid*e){return &e->caps;}
static size_t drm_edid_size(const struct drm_edid*e){return sizeof(*e);}
static struct dvbridge_sink_caps dvbridge_parse_edid(const u8*p,size_t n){(void)n;return *(const struct dvbridge_sink_caps*)p;}
static unsigned dvbridge_lldv_422(struct dvbridge_sink_caps c){return c.lldv;}
static unsigned dvbridge_lldv_422_12(struct dvbridge_sink_caps c){return c.twelve;}
static unsigned dvbridge_lldv_444_bits(struct dvbridge_sink_caps c){return c.depth;}
static unsigned physical=0x1f8;
static unsigned get_formats(void*d,unsigned h){(void)d;(void)h;return physical;}
static struct {unsigned(*getNativeLldvFormats)(void*,unsigned);}api={get_formats},*nvKms=&api;
''' + self.header() + native + r'''
int main(void){
 struct nv_drm_device dev={0};struct drm_edid e={{1,0,12,1}};struct encoder encoder={1};
 struct nv_drm_connector c={{1,&dev},&e,&encoder,1};
 const unsigned only422=(1u<<3)|(1u<<7);
 assert(nv_drm_native_lldv_formats(&c.base)==(only422|(1u<<4)|(1u<<6)));
 e.caps.depth=10;assert(nv_drm_native_lldv_formats(&c.base)==(only422|(1u<<5)|(1u<<8)));
 e.caps.depth=0;assert(nv_drm_native_lldv_formats(&c.base)==only422);
 e.caps.twelve=0;assert(nv_drm_native_lldv_formats(&c.base)==(1u<<7));
 e.caps.depth=12;physical=(1u<<3)|(1u<<7);assert(nv_drm_native_lldv_formats(&c.base)==(1u<<7));
 physical=0;assert(!nv_drm_native_lldv_formats(&c.base));physical=0x1f8;
 e.caps.lldv=0;assert(!nv_drm_native_lldv_formats(&c.base));e.caps.lldv=1;
 e.caps.legacy_vsif=1;assert(!nv_drm_native_lldv_formats(&c.base));e.caps.legacy_vsif=0;
 c.base.status=0;assert(!nv_drm_native_lldv_formats(&c.base));c.base.status=1;
 c.type=2;assert(!nv_drm_native_lldv_formats(&c.base));c.type=1;
 c.edid=NULL;assert(!nv_drm_native_lldv_formats(&c.base));c.edid=&e;
 c.nv_detected_encoder=NULL;assert(!nv_drm_native_lldv_formats(&c.base));
}
''')
