"""Execute R580's native LLDV request and its final vendor-selected link gate."""
import os
from pathlib import Path
import unittest
import test_nvidia_pascal_hdr10plus as pascal_hdr


class PascalLldv(unittest.TestCase):
    native = pascal_hdr.PascalHdr10plus.native
    run_c = pascal_hdr.PascalHdr10plus.run_c
    def test_native_request_preserves_codes_and_the_existing_rgb8_carrier(self):
        native = self.native('src/nvidia-modeset/kapi/src/nvkms-kapi.c',
                             'ConfigureCb1VsifOutput')
        root = Path(os.environ['CB1_PASCAL_SOURCE'])
        vsif = (root/'src/common/inc/nvkms-dv-vsif.h').read_text().replace('#include "nvtypes.h"', '')
        self.run_c(r'''
#include <assert.h>
#include <string.h>
typedef unsigned NvU32;typedef unsigned char NvU8;typedef int NvBool;
#define NV_TRUE 1
#define NV_FALSE 0
#define TRUE 1
#define FALSE 0
enum NvKmsOutputTf {NVKMS_OUTPUT_TF_NONE,NVKMS_OUTPUT_TF_PQ};
enum {NVKMS_OUTPUT_COLORIMETRY_DEFAULT,NVKMS_OUTPUT_COLORIMETRY_BT2100};
enum {NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_SPACE_RGB,
 NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_SPACE_YCbCr422};
enum {NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_FULL,NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED};
struct NvKmsCb1Vsif {NvU32 payloadSize;NvU8 payload[27];NvBool disableDithering;};
static NvBool nvCb1VsifValid(const struct NvKmsCb1Vsif*p){return p->payloadSize>=3 && p->payloadSize<=27;}
struct NvKmsKapiHeadModeSetConfig {
 struct NvKmsCb1Vsif hdmiVsifMetadata;unsigned colorBpc,colorimetry,numDisplays;
 int strictDeepOutput;struct {int enabled;}hdrInfoFrame,hdr10plus;
};
struct NvKmsSetModeOneHeadRequest {int colorSpaceSpecified,colorSpace,
 colorRangeSpecified,colorRange;};
''' + vsif + '\n' + native + r'''
int main(void){
 struct NvKmsKapiHeadModeSetConfig c={.colorBpc=10,.numDisplays=1,.colorimetry=1};
 memcpy(c.hdmiVsifMetadata.payload,nvDoviLowLatencyPayload,27);
 c.hdmiVsifMetadata.payloadSize=27;c.hdmiVsifMetadata.disableDithering=1;
 struct NvKmsSetModeOneHeadRequest r={0};
 assert(ConfigureCb1VsifOutput(&c,NVKMS_OUTPUT_TF_NONE,&r));
 assert(r.colorSpaceSpecified && r.colorSpace==1 && r.colorRangeSpecified && r.colorRange==1);
 struct NvKmsKapiHeadModeSetConfig good=c;
 for(unsigned bpc=0;bpc<=16;bpc++){
  c=good;c.colorBpc=bpc;assert(ConfigureCb1VsifOutput(&c,NVKMS_OUTPUT_TF_NONE,&r)==(bpc==10));
 }
 #define REJECT(field,value) c=good;c.field=value;assert(!ConfigureCb1VsifOutput(&c,NVKMS_OUTPUT_TF_NONE,&r))
 REJECT(colorimetry,0);REJECT(numDisplays,0);REJECT(numDisplays,2);
 REJECT(hdrInfoFrame.enabled,1);REJECT(hdr10plus.enabled,1);REJECT(strictDeepOutput,1);
 REJECT(hdmiVsifMetadata.disableDithering,0);
 c=good;assert(!ConfigureCb1VsifOutput(&c,NVKMS_OUTPUT_TF_PQ,&r));
 c=good;c.colorBpc=8;c.colorimetry=0;
 assert(ConfigureCb1VsifOutput(&c,NVKMS_OUTPUT_TF_NONE,&r));assert(r.colorSpace==0 && r.colorRange==0);
 c.hdmiVsifMetadata.payloadSize=0;r=(struct NvKmsSetModeOneHeadRequest){0};
 assert(ConfigureCb1VsifOutput(&c,NVKMS_OUTPUT_TF_PQ,&r));assert(!r.colorSpaceSpecified);
}
''')

    def test_native_capability_excludes_maxwell_dp_and_edid_without_ten_bits(self):
        native = self.native('src/nvidia-modeset/src/nvkms.c', 'Cb1NativeLldv422')
        self.run_c(r'''
#include <assert.h>
typedef int NvBool;
#define FALSE 0
#define NVKMS_CONNECTOR_SIGNAL_FORMAT_TMDS 1
typedef struct {struct {int minBpc,maxBpc;}yuv422;}NvKmsDpyOutputColorFormatInfo;
typedef struct {struct {int supportsYUV2020,hdmiYCbCr422MaxBpc;}caps;}NVDevEvoRec;
typedef struct {NVDevEvoRec*pDevEvo;}NVDispEvoRec;
typedef struct {int signalFormat;}NVConnectorEvoRec;
typedef struct {NVDispEvoRec*pDispEvo;NVConnectorEvoRec*pConnectorEvo;int hdmi,dp;}NVDpyEvoRec;
static NvKmsDpyOutputColorFormatInfo caps={.yuv422={8,10}};
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
static int nvDpyUsesDPLib(const NVDpyEvoRec*d){return d->dp;}
static NvKmsDpyOutputColorFormatInfo nvDpyGetOutputColorFormatInfo(const NVDpyEvoRec*d){(void)d;return caps;}
''' + native + r'''
int main(void){
 NVDevEvoRec dev={.caps={1,12}};NVDispEvoRec disp={&dev};NVConnectorEvoRec conn={1};
 NVDpyEvoRec d={&disp,&conn,1,0};assert(Cb1NativeLldv422(&d));
 dev.caps.supportsYUV2020=0;assert(!Cb1NativeLldv422(&d));dev.caps.supportsYUV2020=1;
 dev.caps.hdmiYCbCr422MaxBpc=0;assert(!Cb1NativeLldv422(&d));dev.caps.hdmiYCbCr422MaxBpc=12;
 d.dp=1;assert(!Cb1NativeLldv422(&d));d.dp=0;
 d.hdmi=0;assert(!Cb1NativeLldv422(&d));d.hdmi=1;
 conn.signalFormat=2;assert(!Cb1NativeLldv422(&d));conn.signalFormat=1;
 caps.yuv422.maxBpc=8;assert(!Cb1NativeLldv422(&d));caps.yuv422.maxBpc=10;
 caps.yuv422.minBpc=12;assert(!Cb1NativeLldv422(&d));
}
''')

    def test_drm_native_surface_contract_and_forced_carrier_are_distinct(self):
        native = self.native('kernel-open/nvidia-drm/nvidia-drm-connector.c', 'nv_drm_lldv_supported')
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
typedef unsigned char u8;
enum {NVKMS_CONNECTOR_TYPE_HDMI=1,connector_status_connected=1,
 DRM_MODE_COLORIMETRY_DEFAULT=0,DRM_MODE_COLORIMETRY_BT2020_RGB=9,
 DRM_FORMAT_XRGB8888=1,DRM_FORMAT_ARGB8888=2,DRM_FORMAT_XBGR2101010=3,DRM_FORMAT_ABGR2101010=4,
 DRM_MODE_ROTATE_0=1,DRM_BLEND_ALPHA_OPAQUE=65535,NV_DRM_INPUT_COLOR_SPACE_NONE=0,
 NV_DRM_TRANSFER_FUNCTION_LINEAR=1};
struct drm_edid {int v;};struct drm_display_mode {unsigned clock;};
struct drm_framebuffer {struct {unsigned format;}*format;unsigned width,height;};
struct drm_plane_state {struct drm_framebuffer*fb;struct drm_crtc*crtc;
 unsigned src_x,src_y,src_w,src_h,crtc_x,crtc_y,crtc_w,crtc_h,rotation,alpha;void*color_pipeline;};
struct drm_plane {struct drm_plane_state*state;};struct drm_crtc {struct drm_plane*primary;};
struct drm_crtc_state {struct drm_display_mode mode;int active,vrr_enabled,async_flip;
 unsigned connector_mask,plane_mask;void*ctm,*gamma_lut,*degamma_lut;};
struct nv_drm_crtc_state {struct drm_crtc_state base;void*regamma_lut;unsigned regamma_tf;};
struct nv_drm_plane_state {struct drm_plane_state base;unsigned input_colorspace,degamma_tf;
 void*hdr_output_metadata,*lms_ctm,*lms_to_itp_ctm,*itp_to_lms_ctm,*blend_ctm,*degamma_lut,*tmo_lut;};
struct drm_connector_state {void*hdr_output_metadata,*hdr10plus_metadata;unsigned max_requested_bpc,colorspace;};
struct nv_cb1_connector_state {struct drm_connector_state base;unsigned lldv_format;};
struct drm_connector {int status;struct {int is_hdmi,has_hdmi_infoframe;}display_info;};
struct nv_drm_connector {struct drm_connector base;const struct drm_edid*edid;unsigned type;};
typedef struct {int async_update;}nv_drm_atomic_state_base_t;
struct dvbridge_sink_caps {int legacy_vsif;};
static unsigned mode_vic=93;static int native_cap=1,edid_422=1;
#define to_nv_connector(c) ((const struct nv_drm_connector*)(c))
#define to_nv_drm_plane_state_const(p) ((const struct nv_drm_plane_state*)(p))
#define to_nv_crtc_state_const(p) ((const struct nv_drm_crtc_state*)(p))
#define nv_cb1_state(p) ((const struct nv_cb1_connector_state*)(p))
#define drm_match_cea_mode(m) ((void)(m),mode_vic)
#define drm_atomic_get_new_plane_state(a,p) ((void)(a),(p)->state)
#define drm_connector_mask(c) ((void)(c),1U)
#define drm_plane_mask(p) ((void)(p),1U)
#define drm_edid_raw(p) (p)
#define drm_edid_size(p) sizeof(*(p))
#define nv_drm_native_lldv_422(p) ((void)(p),native_cap)
static struct dvbridge_sink_caps dvbridge_parse_edid(const u8*p,unsigned n){(void)p;(void)n;return (struct dvbridge_sink_caps){0};}
static int dvbridge_lldv_422(struct dvbridge_sink_caps c){(void)c;return edid_422;}
''' + native + r'''
int main(void){
 struct drm_edid edid={0};struct nv_drm_connector c={.base={1,{1,1}},.edid=&edid,.type=1};
 struct nv_cb1_connector_state s={.base={.max_requested_bpc=10,.colorspace=0},.lldv_format=2};
 typeof(*((struct drm_framebuffer*)0)->format) fmt={3};struct drm_framebuffer fb={&fmt,3840,2160};
 struct nv_drm_plane_state p={0};struct drm_plane plane={&p.base};struct drm_crtc crtc={&plane};
 p.base=(struct drm_plane_state){.fb=&fb,.crtc=&crtc,.src_w=3840U<<16,.src_h=2160U<<16,
  .crtc_w=3840,.crtc_h=2160,.rotation=1,.alpha=65535};
 struct nv_drm_crtc_state cs={.base={.mode={297000},.active=1,.connector_mask=1,.plane_mask=1}};
 nv_drm_atomic_state_base_t a={0};
 #define CHECK() nv_drm_lldv_supported(&c.base,&s.base,&crtc,&cs.base,&a)
 assert(CHECK());fmt.format=4;assert(CHECK());fmt.format=1;assert(!CHECK());fmt.format=3;
 s.base.max_requested_bpc=12;assert(!CHECK());s.base.max_requested_bpc=10;
 s.base.colorspace=9;assert(!CHECK());s.base.colorspace=0;
 native_cap=0;assert(!CHECK());native_cap=1;edid_422=0;assert(!CHECK());edid_422=1;
 cs.base.mode.clock=594000;assert(!CHECK());cs.base.mode.clock=296703;assert(CHECK());
 cs.base.gamma_lut=&edid;assert(!CHECK());cs.base.gamma_lut=0;
 p.hdr_output_metadata=&edid;assert(!CHECK());p.hdr_output_metadata=0;
 p.input_colorspace=1;assert(!CHECK());p.input_colorspace=0;
 p.degamma_tf=2;assert(!CHECK());p.degamma_tf=0;
 cs.regamma_tf=2;assert(!CHECK());cs.regamma_tf=0;
 cs.base.plane_mask=3;assert(!CHECK());cs.base.plane_mask=1;
 s.lldv_format=1;s.base.max_requested_bpc=8;s.base.colorspace=0;fmt.format=1;native_cap=0;
 assert(CHECK());fmt.format=3;assert(!CHECK());
}
''')

    def test_default_property_enters_native_bt2020_and_restores_effective_color(self):
        native = self.native('kernel-open/nvidia-drm/nvidia-drm-connector.c',
                             '__nv_drm_connector_atomic_check')
        # Compile the production tail that derives the final KAPI colour and its
        # change flag. The preceding HDR/EDID validation is covered separately.
        start = min(native.index('// When adding a case here'),
                    native.index('req_config->flags.colorimetryChanged ='))
        tail = native[start:]
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
enum {DRM_MODE_COLORIMETRY_DEFAULT,DRM_MODE_COLORIMETRY_BT601_YCC,
 DRM_MODE_COLORIMETRY_BT709_YCC,DRM_MODE_COLORIMETRY_BT2020_RGB,DRM_MODE_COLORIMETRY_BT2020_YCC};
enum NvKmsOutputColorimetry {NVKMS_OUTPUT_COLORIMETRY_DEFAULT,NVKMS_OUTPUT_COLORIMETRY_BT601,
 NVKMS_OUTPUT_COLORIMETRY_BT709,NVKMS_OUTPUT_COLORIMETRY_BT2100};
struct drm_connector_state {unsigned colorspace;};
struct nv_cb1_connector_state {struct drm_connector_state base;unsigned lldv_format;};
struct NvKmsKapiHeadRequestedConfig {
 struct {enum NvKmsOutputColorimetry colorimetry;}modeSetConfig;
 struct {bool colorimetryChanged;}flags;
};
#define nv_cb1_state(s) ((struct nv_cb1_connector_state*)(s))
#define NV_DRM_DEV_LOG_ERR(dev,text) ((void)(dev),(void)(text))
static int update(struct NvKmsKapiHeadRequestedConfig *req_config,
 struct drm_connector_state *old_connector_state,struct drm_connector_state *new_connector_state){
 enum NvKmsOutputColorimetry colorimetry=NVKMS_OUTPUT_COLORIMETRY_DEFAULT;
 (void)colorimetry;(void)old_connector_state;void*nv_dev=0;
''' + tail + r'''
int main(void){
 struct NvKmsKapiHeadRequestedConfig req={0};
 struct nv_cb1_connector_state old={0},next={.lldv_format=2};
 assert(!update(&req,&old.base,&next.base));
 assert(req.modeSetConfig.colorimetry==NVKMS_OUTPUT_COLORIMETRY_BT2100 && req.flags.colorimetryChanged);
 old=next;assert(!update(&req,&old.base,&next.base));assert(!req.flags.colorimetryChanged);
 next.lldv_format=0;assert(!update(&req,&old.base,&next.base));
 assert(req.modeSetConfig.colorimetry==NVKMS_OUTPUT_COLORIMETRY_DEFAULT && req.flags.colorimetryChanged);
 old=next;assert(!update(&req,&old.base,&next.base));assert(!req.flags.colorimetryChanged);
 next.lldv_format=2;assert(!update(&req,&old.base,&next.base));
 old=next;next.lldv_format=1;assert(!update(&req,&old.base,&next.base));
 assert(req.modeSetConfig.colorimetry==NVKMS_OUTPUT_COLORIMETRY_DEFAULT && req.flags.colorimetryChanged);
 old=next;next.lldv_format=0;next.base.colorspace=DRM_MODE_COLORIMETRY_BT2020_YCC;
 assert(!update(&req,&old.base,&next.base));
 assert(req.modeSetConfig.colorimetry==NVKMS_OUTPUT_COLORIMETRY_BT2100 && req.flags.colorimetryChanged);
 old=next;next.base.colorspace=DRM_MODE_COLORIMETRY_BT709_YCC;
 assert(!update(&req,&old.base,&next.base));
 assert(req.modeSetConfig.colorimetry==NVKMS_OUTPUT_COLORIMETRY_BT709 && req.flags.colorimetryChanged);
}
''')

    def test_active_readback_rejects_old_hdr_state_and_wrong_head(self):
        native = self.native('src/nvidia-modeset/src/nvkms.c', 'Cb1NativeLldvActive')
        root = Path(os.environ['CB1_PASCAL_SOURCE'])
        vsif = (root/'src/common/inc/nvkms-dv-vsif.h').read_text().replace('#include "nvtypes.h"', '')
        self.run_c(r'''
#include <assert.h>
#include <string.h>
typedef unsigned NvU32;typedef unsigned char NvU8;typedef int NvBool;
#define NV_TRUE 1
#define NV_FALSE 0
#define TRUE 1
#define FALSE 0
#define NVKMS_OUTPUT_TF_NONE 0
#define NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_SPACE_YCbCr422 2
#define NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED 1
#define NVKMS_OUTPUT_COLORIMETRY_BT2100 3
#define NVKMS_PIXEL_DEPTH_20_422 20
struct Vsif {NvU8 payload[27];NvU32 payloadSize;};
typedef struct {unsigned hwHeadsMask,activeDpys;struct {struct {int format,bpc,range,colorimetry;}color;}attributes;
 struct Vsif hdmiVsifMetadata;int tf,hdrInfoFrameOverride,hdrStaticMetadataLayerMask;}NVDispApiHeadStateEvoRec;
typedef struct {void*pConnectorEvo;int pixelDepth,tf;struct Vsif hdmiVsifMetadata;
 struct {int enabled;}hdrInfoFrameOverride;}NVDispHeadStateEvoRec;
typedef struct {struct {unsigned numApiHeads;}*pDevEvo;NVDispApiHeadStateEvoRec apiHeadState[2];
 NVDispHeadStateEvoRec headState[2];}NVDispEvoRec;
typedef struct {NVDispEvoRec*pDispEvo;unsigned apiHead,id;void*pConnectorEvo;}NVDpyEvoRec;
static unsigned nvPopCount32(unsigned x){return __builtin_popcount(x);}
static int nvDpyIdIsInDpyIdList(unsigned id,unsigned ids){return ids&(1U<<id);}
static unsigned nvCountDpyIdsInDpyIdList(unsigned ids){return nvPopCount32(ids);}
static unsigned nvGetPrimaryHwHead(const NVDispEvoRec*d,unsigned head){(void)d;return head;}
''' + vsif + '\n' + native + r'''
int main(void){
 typeof(*((NVDispEvoRec*)0)->pDevEvo) dev={2};NVDispEvoRec disp={.pDevEvo=&dev};
 NVDpyEvoRec d={&disp,0,0,(void*)1};
 NVDispApiHeadStateEvoRec*a=&disp.apiHeadState[0];NVDispHeadStateEvoRec*h=&disp.headState[0];
 *a=(NVDispApiHeadStateEvoRec){.hwHeadsMask=1,.activeDpys=1,.attributes={{2,10,1,3}}};
 h->pConnectorEvo=(void*)1;h->pixelDepth=20;
 memcpy(a->hdmiVsifMetadata.payload,nvDoviLowLatencyPayload,27);a->hdmiVsifMetadata.payloadSize=27;
 h->hdmiVsifMetadata=a->hdmiVsifMetadata;
 assert(Cb1NativeLldvActive(&d,0));assert(!Cb1NativeLldvActive(&d,1));assert(!Cb1NativeLldvActive(&d,2));
 a->hdmiVsifMetadata.payloadSize=0;assert(!Cb1NativeLldvActive(&d,0));a->hdmiVsifMetadata=h->hdmiVsifMetadata;
 h->hdmiVsifMetadata.payloadSize=0;assert(!Cb1NativeLldvActive(&d,0));h->hdmiVsifMetadata=a->hdmiVsifMetadata;
 a->attributes.color.bpc=8;assert(!Cb1NativeLldvActive(&d,0));a->attributes.color.bpc=10;
 a->attributes.color.format=0;assert(!Cb1NativeLldvActive(&d,0));a->attributes.color.format=2;
 h->pixelDepth=24;assert(!Cb1NativeLldvActive(&d,0));h->pixelDepth=20;
 a->activeDpys=3;assert(!Cb1NativeLldvActive(&d,0));a->activeDpys=1;
 a->hwHeadsMask=3;assert(!Cb1NativeLldvActive(&d,0));a->hwHeadsMask=1;
 h->pConnectorEvo=(void*)2;assert(!Cb1NativeLldvActive(&d,0));
}
''')

    def test_final_link_rejects_bandwidth_and_depth_fallback_before_commit(self):
        native = self.native('src/nvidia-modeset/src/nvkms-modeset.c', 'Cb1NativeLldvModeValid')
        self.run_c(r'''
#include <assert.h>
typedef int NvBool;
#define NVKMS_OUTPUT_TF_NONE 0
#define NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_SPACE_YCbCr422 2
#define NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED 1
#define NVKMS_OUTPUT_COLORIMETRY_BT2100 3
#define NVKMS_PIXEL_DEPTH_20_422 20
typedef struct {int format,bpc,range,colorimetry;}Color;
typedef struct {unsigned hwHeadsMask;struct {Color color;}attributes;
 int tf,hdrInfoFrameOverride,hdrStaticMetadataLayerMask;}NVProposedModeSetStateOneApiHead;
static unsigned nvPopCount32(unsigned x){return __builtin_popcount(x);}
static int nvEvoDpyColorToPixelDepth(const Color*c){return c->bpc==10 && c->format==2?20:0;}
''' + native + r'''
int main(void){
 NVProposedModeSetStateOneApiHead good={.hwHeadsMask=1,.attributes={{2,10,1,3}}};
 assert(Cb1NativeLldvModeValid(&good));NVProposedModeSetStateOneApiHead p;
 #define REJECT(field,value) p=good;p.field=value;assert(!Cb1NativeLldvModeValid(&p))
 REJECT(attributes.color.format,0);REJECT(attributes.color.bpc,8);REJECT(attributes.color.bpc,12);
 REJECT(attributes.color.range,0);REJECT(attributes.color.colorimetry,0);
 REJECT(hwHeadsMask,0);REJECT(hwHeadsMask,3);REJECT(tf,1);
 REJECT(hdrInfoFrameOverride,1);REJECT(hdrStaticMetadataLayerMask,1);
}
''')


if __name__ == '__main__':
    unittest.main()
