"""Execute the matched native HDMI static-HDR emitters and live-depth query."""
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_hdr10_transport import function


class NvidiaNativeHdr(unittest.TestCase):
    def test_native_hdr_capability_includes_hlg_only_and_3d_capable_receivers(self):
        root=self.sources()[0]
        native=function((root/'src/nvidia-modeset/src/nvkms-dpy.c').read_text(),'nvDpyIsHDRCapable')
        self.compile_run(r'''
#include <assert.h>
typedef int NvBool;
#define TRUE 1
#define FALSE 0
#define nvEvoLogDisp(...) ((void)0)
typedef struct {struct {int smpte_st_2084_eotf,future_eotf;}supported_eotf;int static_metadata_type;} NVT_HDR_STATIC_METADATA;
typedef struct {int HDMI3DSupported;NVT_HDR_STATIC_METADATA hdr_static_metadata_info;} NVT_EDID_INFO;
typedef struct {struct {int valid;NVT_EDID_INFO info;}parsedEdid;int dp,hdmi;void*pDispEvo;char*name;} NVDpyEvoRec;
static int major=1,minor=3,query=1;
static int nvDpyUsesDPLib(const NVDpyEvoRec*d){return d->dp;}
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
static int nvDPDpyGetDpcdRevision(const NVDpyEvoRec*d,unsigned*a,unsigned*b){(void)d;*a=major;*b=minor;return query;}
@@NATIVE@@
int main(void){
 NVDpyEvoRec d={.hdmi=1};d.parsedEdid.valid=1;
 NVT_HDR_STATIC_METADATA*h=&d.parsedEdid.info.hdr_static_metadata_info;
 h->static_metadata_type=1;h->supported_eotf.future_eotf=1;
 assert(nvDpyIsHDRCapable(&d));d.parsedEdid.info.HDMI3DSupported=1;assert(nvDpyIsHDRCapable(&d));
 h->supported_eotf.future_eotf=0;assert(!nvDpyIsHDRCapable(&d));h->supported_eotf.smpte_st_2084_eotf=1;
 assert(nvDpyIsHDRCapable(&d));h->static_metadata_type=0;assert(!nvDpyIsHDRCapable(&d));h->static_metadata_type=1;
 d.parsedEdid.valid=0;assert(!nvDpyIsHDRCapable(&d));d.parsedEdid.valid=1;
 d.hdmi=0;assert(!nvDpyIsHDRCapable(&d));d.dp=1;
 minor=2;assert(!nvDpyIsHDRCapable(&d));minor=3;assert(nvDpyIsHDRCapable(&d));
 major=2;minor=0;assert(nvDpyIsHDRCapable(&d));query=0;assert(!nvDpyIsHDRCapable(&d));
}
'''.replace('@@NATIVE@@',native))

    def test_matched_r615_native_ceiling_still_requires_edid_and_deepcolor(self):
        root = self.sources()[0]
        config = Path(__file__).resolve().parents[2]/'packages/graphics/nvidia/files/hdr-depth.conf'
        self.assertTrue(config.is_file(), 'matched R615 native ceiling configuration is absent')
        ceiling = int(re.search(r'max_output_color_depth=(\d+)', config.read_text()).group(1))
        hdmi = (root/'src/nvidia-modeset/src/nvkms-hdmi.c').read_text()
        native = function((root/'kernel-open/nvidia-modeset/nvidia-modeset-linux.c').read_text(),
                          'nvkms_max_output_color_bpc')
        native += '\n'+function(hdmi, 'nvDpyIsHdmiDepth30Evo')
        native += '\n'+function(hdmi, 'nvDpyIsHdmiDepth36Evo')
        self.compile_run(r'''
#include <assert.h>
typedef unsigned NvU32;typedef int NvBool;
typedef struct {struct {int supportsHDMI10BPC;}caps;} Hal;
typedef struct {Hal*hal;} NVDevEvoRec;
typedef struct {struct {NVDevEvoRec*pDevEvo;}*pDispEvo;int hdmi;unsigned edid;} NVDpyEvoRec;
#define CAP_HDMI_SUPPORT_MONITOR_30_BPP 1
#define CAP_HDMI_SUPPORT_MONITOR_36_BPP 2
static unsigned max_output_color_depth=@@CEILING@@;static int deep=1;
static unsigned GetHDMISupportCap(const NVDpyEvoRec*d){return d->edid;}
static int nvkms_hdmi_deepcolor(void){return deep;}
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
@@NATIVE@@
int main(void){
 Hal hal={0};NVDevEvoRec dev={&hal};typeof(*((NVDpyEvoRec*)0)->pDispEvo) disp={&dev};
 NVDpyEvoRec d={&disp,1,3};
 assert(nvkms_max_output_color_bpc()==12 && nvDpyIsHdmiDepth36Evo(&d));
 assert(!nvDpyIsHdmiDepth30Evo(&d)); /* Turing native HDMI lacks RGB10. */
 d.edid=1;assert(!nvDpyIsHdmiDepth36Evo(&d));d.edid=3;
 deep=0;assert(!nvDpyIsHdmiDepth36Evo(&d));deep=1;
 d.hdmi=0;assert(!nvDpyIsHdmiDepth36Evo(&d));d.hdmi=1;
 max_output_color_depth=10;assert(!nvDpyIsHdmiDepth36Evo(&d));
 hal.caps.supportsHDMI10BPC=1;assert(nvDpyIsHdmiDepth30Evo(&d));
 max_output_color_depth=8;assert(!nvDpyIsHdmiDepth30Evo(&d));
}
'''.replace('@@NATIVE@@', native).replace('@@CEILING@@', str(ceiling)))

    def compile_run(self, program):
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp)/'check.c', Path(tmp)/'check'
            source.write_text(program)
            built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-function', '-Wno-unused-variable', str(source), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def sources(self):
        roots = [os.environ.get('CB1_NVIDIA_SOURCE'), os.environ.get('CB1_PASCAL_SOURCE')]
        if not all(roots):
            self.skipTest('requires privately replayed matched R615 and R580 source')
        return [Path(root) for root in roots]

    def test_requested_eotf_and_actual_vsif_owner(self):
        # Removing the requested-EOTF guard or retaining the sink-wide 3D skip
        # must fail these actual emitter observations (not a parallel policy).
        for root in self.sources():
            native = function((root/'src/nvidia-modeset/src/nvkms-hdmi.c').read_text(),
                              'SendHDRInfoFrame')
            modern = 'currentTransmitCtrl' in native
            lldv = 'nvDoviLowLatency' in native
            vsif = (root/'src/common/inc/nvkms-dv-vsif.h').read_text().replace('#include "nvtypes.h"', '') if lldv else ''
            program = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
typedef unsigned NvU32; typedef unsigned char NvU8; typedef uint16_t NvU16;
typedef int NvBool; typedef int NvEvoInfoFrameTransmitControl;
typedef int NvEvoInfoFrameTransmitFrequency;
#define TRUE 1
#define FALSE 0
#define NV_TRUE 1
#define NV_FALSE 0
#define ct_assert(x) _Static_assert(x, #x)
#define nvAssert(x) assert(x)
#define nvkms_memcpy memcpy
enum {NVKMS_HDR_INFOFRAME_STATE_ENABLED=1,NVKMS_HDR_INFOFRAME_STATE_TRANSITIONING,
 NVKMS_HDR_INFOFRAME_STATE_DISABLED};
enum {NVKMS_INFOFRAME_EOTF_SDR_GAMMA=0,NVKMS_INFOFRAME_EOTF_HDR_GAMMA=1,
 NVKMS_INFOFRAME_EOTF_ST2084=2,NVKMS_INFOFRAME_EOTF_HLG=3};
enum {NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_INIT,
 NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_EVERY_FRAME,
 NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_SINGLE_FRAME,
 NV_EVO_INFOFRAME_TRANSMIT_CONTROL_INIT,
 NV_EVO_INFOFRAME_TRANSMIT_CONTROL_EVERY_FRAME,
 NV_EVO_INFOFRAME_TRANSMIT_CONTROL_SINGLE_FRAME,
 NVT_INFOFRAME_TYPE_DYNAMIC_RANGE_MASTERING=0x87,
 NVT_VIDEO_INFOFRAME_VERSION_1=1,NVT_CEA861_STATIC_METADATA_SM0=0};
typedef struct {NvU8 type,version,length;} NVT_INFOFRAME_HEADER;
struct NvKmsHDRStaticMetadata {NvU16 data[12];};
typedef struct NvKmsHDRStaticMetadata NVT_HDR_INFOFRAME_MASTERING_DATA;
typedef struct {NvU8 eotf,static_metadata_desc_id;
 NVT_HDR_INFOFRAME_MASTERING_DATA type1;} Payload;
typedef struct {NVT_INFOFRAME_HEADER header; Payload payload;} NVT_HDR_INFOFRAME;
typedef struct {struct {unsigned trad_gamma_sdr_eotf:1,trad_gamma_hdr_eotf:1,
 smpte_st_2084_eotf:1,future_eotf:1;} supported_eotf;
 unsigned static_metadata_type;} NVT_HDR_STATIC_METADATA;
typedef struct {NVT_HDR_STATIC_METADATA hdr_static_metadata_info;
 int HDMI3DSupported;} NVT_EDID_INFO;
typedef struct {struct {int Enable;}vendorSpecificCtrl;} NVDispHeadInfoFrameStateEvoRec;
typedef struct {struct {unsigned payloadSize;NvU8 payload[27];}hdmiVsifMetadata;
 int bypassComposition;
 struct {int state,eotf;struct NvKmsHDRStaticMetadata staticMetadata;}hdrInfoFrame;
} NVDispHeadStateEvoRec;
typedef struct {struct {void (*SendHdmiInfoFrame)(); void (*DisableHdmiInfoFrame)();}*hal;
 struct {int supportsGenericSharedInfoFrames;}caps;} NVDevEvoRec;
typedef struct {NVDevEvoRec *pDevEvo;NVDispHeadStateEvoRec headState[1];} NVDispEvoRec;
static unsigned writes,clears;static NvU8 eotf;
static void disable(const NVDispEvoRec*d,NvU32 h,void*c,int type){
 (void)d;(void)c;assert(h==0 && type==NVT_INFOFRAME_TYPE_DYNAMIC_RANGE_MASTERING);clears++;
}
static void send(const NVDispEvoRec*d,NvU32 h,@@CTRLTYPE@@ c,
 const NVT_INFOFRAME_HEADER*p,NvU32 size,NvBool checksum){
 (void)d;(void)c;assert(h==0 && size==sizeof(NVT_HDR_INFOFRAME) && checksum);
 const NVT_HDR_INFOFRAME *hdr=(const void*)p;writes++;eotf=hdr->payload.eotf;
}
static void nvDpyAssignSDRInfoFramePayload(Payload*p){p->eotf=0;}
static void UpdateInfoFrameFlipStatePre(NvEvoInfoFrameTransmitControl*a,
 NvEvoInfoFrameTransmitControl*b,int c,NvBool d){(void)a;(void)b;(void)c;(void)d;}
static void UpdateInfoFrameFlipStatePost(NvEvoInfoFrameTransmitControl*a){(void)a;}
@@NATIVE@@
int main(void){
 typeof(*((NVDevEvoRec*)0)->hal) hal={send,disable};NVDevEvoRec dev={.hal=&hal};
 NVDispEvoRec disp={.pDevEvo=&dev};NVT_EDID_INFO edid={0};
 NVDispHeadInfoFrameStateEvoRec info={0};NvEvoInfoFrameTransmitControl a=0,b=0;(void)info;
 disp.headState[0].hdrInfoFrame.state=NVKMS_HDR_INFOFRAME_STATE_ENABLED;
 for(unsigned mask=0;mask<16;mask++){
  edid.hdr_static_metadata_info.supported_eotf.trad_gamma_sdr_eotf=mask&1;
  edid.hdr_static_metadata_info.supported_eotf.trad_gamma_hdr_eotf=(mask>>1)&1;
  edid.hdr_static_metadata_info.supported_eotf.smpte_st_2084_eotf=(mask>>2)&1;
  edid.hdr_static_metadata_info.supported_eotf.future_eotf=(mask>>3)&1;
  for(int requested=0;requested<=4;requested++){
   disp.headState[0].hdrInfoFrame.eotf=requested;
   for(unsigned type=0;type<=2;type++){
    edid.hdr_static_metadata_info.static_metadata_type=type;writes=0;
    @@CALL@@
    assert(writes==(type==1 && requested<4 && (mask&(1u<<requested))?1u:0u));
    if(writes)assert(eotf==requested);
   }
  }
 }
 edid.hdr_static_metadata_info.static_metadata_type=1;
 edid.hdr_static_metadata_info.supported_eotf.future_eotf=1;
 disp.headState[0].hdrInfoFrame.eotf=3;
 edid.HDMI3DSupported=1;writes=0;@@CALL@@ assert(writes==1);
 info.vendorSpecificCtrl.Enable=1;writes=0;@@CALL@@ assert(writes==0);
 info.vendorSpecificCtrl.Enable=0;disp.headState[0].hdmiVsifMetadata.payloadSize=27;
 writes=0;@@CALL@@ assert(writes==0);
 disp.headState[0].hdmiVsifMetadata.payloadSize=0;
 for(int state=NVKMS_HDR_INFOFRAME_STATE_TRANSITIONING;state<=NVKMS_HDR_INFOFRAME_STATE_DISABLED;state++){
  disp.headState[0].hdrInfoFrame.state=state;writes=0;@@CALL@@
  assert(writes==1 && eotf==0);
 }
 @@LLDV_TEST@@
}
'''
            call = 'SendHDRInfoFrame(&disp,0,'
            if 'pInfoFrameState' in native:
                call += '&info,'
            if modern:
                call += '&a,&b,'
            call += '&edid);'
            program = program.replace('@@LLDV_TEST@@', r'''
 disp.headState[0].bypassComposition=1;
 disp.headState[0].hdmiVsifMetadata.payloadSize=27;
 memcpy(disp.headState[0].hdmiVsifMetadata.payload,nvDoviLowLatencyPayload,27);
 for(int separate=0;separate<2;separate++){
  dev.caps.supportsGenericSharedInfoFrames=separate;writes=clears=0;
  @@CALL@@
  assert(writes==0 && clears==(unsigned)separate);
 }
''' if lldv else '')
            program = program.replace('@@NATIVE@@', vsif+'\n'+native).replace('@@CALL@@', call)
            program = program.replace('@@CTRLTYPE@@',
                'const NvEvoInfoFrameTransmitControl*' if modern else 'NvEvoInfoFrameTransmitControl')
            with self.subTest(stack=str(root)):
                self.compile_run(program)

    def test_live_depth_uses_native_attribute_and_selected_head(self):
        # A request/max-depth value is not the current link depth. Failed,
        # off-head and DPMS-off native queries must produce unknown, not 10.
        for root in self.sources():
            native = function((root/'src/nvidia-modeset/kapi/src/nvkms-kapi.c').read_text(),
                              'GetCurrentOutputBpc')
            program = r'''
#include <assert.h>
#include <stddef.h>
typedef unsigned NvU32;typedef int NvBool;typedef long long NvS64;
typedef unsigned NvKmsKapiDisplay;
struct NvKmsKapiDevice {unsigned hKmsDevice,hKmsDisp;void*pKmsOpen;};
struct NvKmsGetDpyAttributeParams {
 struct {unsigned deviceHandle,dispHandle,dpyId;int attribute;}request;
 struct {NvS64 value;}reply;
};
enum {NVKMS_IOCTL_GET_DPY_ATTRIBUTE=17,NV_KMS_DPY_ATTRIBUTE_HEAD=3,
 NV_KMS_DPY_ATTRIBUTE_DPMS=25,NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC=15,
 NV_KMS_DPY_ATTRIBUTE_DPMS_ON=0,NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_MAX=@@MAX@@};
#define nvNvU32ToDpyId(x) (x)
static unsigned calls,fail,head,depth=8,off;
static NvBool nvkms_ioctl_from_kapi(void*open,unsigned cmd,
 struct NvKmsGetDpyAttributeParams*p,size_t size){
 assert(open==(void*)1 && cmd==17 && size==sizeof(*p));
 assert(p->request.deviceHandle==4 && p->request.dispHandle==7 && p->request.dpyId==9);
 calls++;if(calls==fail)return 0;
 switch(p->request.attribute){
 case NV_KMS_DPY_ATTRIBUTE_HEAD:p->reply.value=head;break;
 case NV_KMS_DPY_ATTRIBUTE_DPMS:p->reply.value=off;break;
 case NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC:p->reply.value=depth;break;
 default:assert(0);
 }return 1;
}
@@NATIVE@@
int main(void){
 struct NvKmsKapiDevice dev={4,7,(void*)1};
 assert(GetCurrentOutputBpc(NULL,9,0)==0 && calls==0);
 for(depth=0;depth<=16;depth++){
  calls=0;assert(GetCurrentOutputBpc(&dev,9,0)==
   (depth==6 || depth==8 || depth==10 || (depth==12 && @@MAX@@==12)?depth:0));
 }
 depth=10;head=1;calls=0;assert(GetCurrentOutputBpc(&dev,9,0)==0);
 head=0;off=1;calls=0;assert(GetCurrentOutputBpc(&dev,9,0)==0);
 off=0;
 for(fail=1;fail<=3;fail++){calls=0;assert(GetCurrentOutputBpc(&dev,9,0)==0);}
 fail=0;calls=0;depth=8;assert(GetCurrentOutputBpc(&dev,9,0)==8);
 depth=10;calls=0;assert(GetCurrentOutputBpc(&dev,9,0)==10);
}
'''
            maximum = '12' if root.name == 'nvidia615' else '10'
            self.compile_run(program.replace('@@NATIVE@@', native).replace('@@MAX@@', maximum))

    def test_depth_property_is_bound_to_current_connector_and_head(self):
        for root in self.sources():
            native = function((root/'kernel-open/nvidia-drm/nvidia-drm-connector.c').read_text(),
                              'nv_drm_connector_current_output_bpc')
            program = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
typedef unsigned NvU32;
struct drm_crtc_state {int active;};
struct drm_crtc {struct drm_crtc_state*state;unsigned head;};
struct drm_encoder {unsigned hDisplay;};
struct drm_connector_state {struct drm_crtc*crtc;struct drm_encoder*best_encoder;};
struct drm_connector {int status;void*dev;};
struct nv_drm_device {void*pDevice;};
#define connector_status_connected 1
#define to_nv_device(x) ((struct nv_drm_device*)(x))
#define to_nv_crtc(x) (x)
#define to_nv_encoder(x) (x)
static unsigned depth=8,calls;
static NvU32 query(void*dev,unsigned display,unsigned head){
 assert(dev==(void*)1 && display==9 && head==2);calls++;return depth;
}
static struct {NvU32(*getCurrentOutputBpc)(void*,unsigned,unsigned);}api={query},*nvKms=&api;
@@NATIVE@@
int main(void){
 struct nv_drm_device dev={(void*)1};struct drm_connector c={1,&dev};
 struct drm_crtc_state cs={1};struct drm_crtc crtc={&cs,2};struct drm_encoder enc={9};
 struct drm_connector_state s={&crtc,&enc};
 assert(nv_drm_connector_current_output_bpc(&c,&s)==8 && calls==1);
 depth=12;assert(nv_drm_connector_current_output_bpc(&c,&s)==12 && calls==2);
 s.crtc=NULL;assert(nv_drm_connector_current_output_bpc(&c,&s)==0 && calls==2);s.crtc=&crtc;
 s.best_encoder=NULL;assert(nv_drm_connector_current_output_bpc(&c,&s)==0 && calls==2);s.best_encoder=&enc;
 cs.active=0;assert(nv_drm_connector_current_output_bpc(&c,&s)==0 && calls==2);cs.active=1;
 c.status=0;assert(nv_drm_connector_current_output_bpc(&c,&s)==0 && calls==2);
}
'''
            self.compile_run(program.replace('@@NATIVE@@', native))

    def test_native_lldv_exact_link_and_no_downgrade(self):
        root = self.sources()[0]
        source = (root/'src/nvidia-modeset/kapi/src/nvkms-kapi.c').read_text()
        hw = (root/'src/nvidia-modeset/src/nvkms-hw-flip.c').read_text()
        native = function(source, 'ConfigureLldvOutput')+'\n'+function(hw, 'nvIsNativeLldvColor')
        vsif = (root/'src/common/inc/nvkms-dv-vsif.h').read_text().replace('#include "nvtypes.h"', '')
        self.compile_run(r"""
#include <assert.h>
#include <string.h>
typedef unsigned NvU32;typedef unsigned char NvU8;typedef int NvBool;
#define NV_TRUE 1
#define NV_FALSE 0
#define TRUE 1
#define FALSE 0
enum NvKmsOutputTf {NVKMS_OUTPUT_TF_NONE, NVKMS_OUTPUT_TF_PQ};
enum {NVKMS_OUTPUT_COLORIMETRY_DEFAULT,NVKMS_OUTPUT_COLORIMETRY_BT2100};
enum {NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_FORMAT_RGB,
 NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_FORMAT_YCbCr422,
 NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_FORMAT_YCbCr422};
enum {NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_FULL,NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED};
enum {NV_KMS_DPY_ATTRIBUTE_REQUESTED_DITHERING_DISABLED,
 NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_12=12};
struct NvKmsHdmiVsifMetadata {NvU8 payload[27];NvU32 payloadSize;};
struct NvKmsKapiHeadModeSetConfig {
 struct NvKmsHdmiVsifMetadata hdmiVsifMetadata;
 unsigned colorBpc,colorimetry,numDisplays;
 struct {int enabled;}hdrInfoFrame;
 struct {int enabled,deepColor;}cb1Hdr;
 struct {int state;}dithering;int postcompColorPassthrough;
};
struct NvKmsSetModeOneHeadRequest {int colorFormatSpecified,colorFormat,
 colorRangeSpecified,colorRange;struct {struct {int specified;}dithering;}flip;};
typedef struct {int format,bpc,range,colorimetry;} NVDpyAttributeColor;
@@VSIF@@
@@NATIVE@@
int main(void){
 struct NvKmsKapiHeadModeSetConfig c={.colorBpc=12,.numDisplays=1,
  .colorimetry=NVKMS_OUTPUT_COLORIMETRY_BT2100};
 memcpy(c.hdmiVsifMetadata.payload,nvDoviLowLatencyPayload,27);c.hdmiVsifMetadata.payloadSize=27;
 struct NvKmsSetModeOneHeadRequest h={0};
 assert(ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&h));
 assert(h.colorFormatSpecified && h.colorFormat==NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_FORMAT_YCbCr422);
 assert(h.colorRangeSpecified && h.colorRange==NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED);
 assert(h.flip.dithering.specified);
 struct NvKmsKapiHeadModeSetConfig good=c;
 for(unsigned bpc=0;bpc<=16;bpc++){
  c=good;c.colorBpc=bpc;assert(ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&h)==(bpc==12));
 }
 c=good;c.colorBpc=8;c.colorimetry=NVKMS_OUTPUT_COLORIMETRY_DEFAULT;
 assert(ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&h));
 assert(h.colorFormat==NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_FORMAT_RGB &&
        h.colorRange==NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_FULL);
 c.postcompColorPassthrough=1;
 assert(ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&h)); /* existing packed path */
 #define REJECT(field,value) c=good;c.field=value;assert(!ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_NONE,&h))
 REJECT(colorimetry,0);REJECT(numDisplays,0);REJECT(numDisplays,2);
 REJECT(hdrInfoFrame.enabled,1);REJECT(cb1Hdr.enabled,1);REJECT(cb1Hdr.deepColor,1);
 REJECT(dithering.state,1);REJECT(postcompColorPassthrough,1);
 c=good;assert(!ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_PQ,&h));
 c.hdmiVsifMetadata.payloadSize=0;memset(&h,0,sizeof(h));
 assert(ConfigureLldvOutput(&c,NVKMS_OUTPUT_TF_PQ,&h));assert(!h.colorFormatSpecified && !h.colorRangeSpecified);
 NVDpyAttributeColor color={NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_FORMAT_YCbCr422,12,
  NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED,NVKMS_OUTPUT_COLORIMETRY_BT2100};
 c=good;assert(nvIsNativeLldvColor(&c.hdmiVsifMetadata,&color));
 color.bpc=10;assert(!nvIsNativeLldvColor(&c.hdmiVsifMetadata,&color));color.bpc=12;
 color.range=NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_FULL;assert(!nvIsNativeLldvColor(&c.hdmiVsifMetadata,&color));
 color.range=NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED;color.format=0;
 assert(!nvIsNativeLldvColor(&c.hdmiVsifMetadata,&color));
}
""".replace('@@VSIF@@',vsif).replace('@@NATIVE@@',native))

    def test_native_lldv_preserves_integer_pipeline_and_rejects_processing(self):
        root = self.sources()[0]
        hw = (root/'src/nvidia-modeset/src/nvkms-hw-flip.c').read_text()
        native = function(hw,'nvIsNativeLldvSurface')+'\n'+function(hw,'ValidateColorPassthroughFlipState')
        vsif = (root/'src/common/inc/nvkms-dv-vsif.h').read_text().replace('#include "nvtypes.h"', '')
        self.compile_run(r"""
#include <assert.h>
#include <string.h>
typedef unsigned NvU32;typedef unsigned char NvU8;typedef int NvBool;
#define NV_TRUE 1
#define NV_FALSE 0
#define TRUE 1
#define FALSE 0
#define NVKMS_MAIN_LAYER 0
#define NVKMS_LEFT 0
#define NVKMS_RIGHT 1
#define NVKMS_INPUT_TF_LINEAR 0
#define NVKMS_OUTPUT_TF_NONE 0
enum {NvKmsSurfaceMemoryFormatR16G16B16A16=1,
 NvKmsSurfaceMemoryFormatRF16GF16BF16AF16,NvKmsSurfaceMemoryFormatRF16GF16BF16XF16};
typedef struct {int format;} NVSurfaceEvoRec;
typedef struct {int fromOverride;void*pLutSurfaceEvo;} Lut;
typedef struct {int enabled,matrix;} Override;
typedef struct {
 NVSurfaceEvoRec*pSurfaceEvo[2];int precompColorPassthrough,tf,cscMatrix;
 Lut inputLut,tmoLut;Override fmtOverride,csc00Override,csc01Override,csc10Override,csc11Override;
 struct {int width,height;}sizeIn,sizeOut;struct {int enabled;}hdrStaticMetadata;
} NVFlipChannelEvoHwState;
typedef struct {
 NVFlipChannelEvoHwState layer[2];int postcompColorPassthrough,tf;
 struct {NvU8 payload[27];NvU32 payloadSize;}hdmiVsifMetadata;
 struct {int enabled;}hdrInfoFrame;Lut outputLut;struct {void*pSurfaceEvo;}cursor;
} NVFlipEvoHwState;
typedef struct {struct {struct {int width,height;}in,out;}viewPort;} NVHwModeTimingsEvo;
typedef struct {struct {struct {int supportsColorPassthrough;}caps;}*hal;
 struct {NvU32 numLayers;}head[1];}NVDevEvoRec;
static int nvIsCscMatrixIdentity(const int*m){return *m==1;}
@@VSIF@@
@@NATIVE@@
int main(void){
 NVSurfaceEvoRec surface={NvKmsSurfaceMemoryFormatR16G16B16A16};
 typeof(*((NVDevEvoRec*)0)->hal) hal={.caps={1}};NVDevEvoRec dev={&hal,{{2}}};
 NVHwModeTimingsEvo timings={.viewPort={{3840,2160},{3840,2160}}};
 NVFlipEvoHwState f={0};f.layer[0].pSurfaceEvo[0]=&surface;f.layer[0].cscMatrix=1;
 f.layer[0].sizeIn.width=f.layer[0].sizeOut.width=3840;
 f.layer[0].sizeIn.height=f.layer[0].sizeOut.height=2160;
 memcpy(f.hdmiVsifMetadata.payload,nvDoviLowLatencyPayload,27);f.hdmiVsifMetadata.payloadSize=27;
 assert(nvIsNativeLldvSurface(&f));assert(ValidateColorPassthroughFlipState(&dev,0,&timings,&f));
 NVFlipEvoHwState good=f;
 #define REJECT(field,value) f=good;f.field=value;assert(!ValidateColorPassthroughFlipState(&dev,0,&timings,&f))
 REJECT(layer[0].precompColorPassthrough,1);REJECT(postcompColorPassthrough,1);
 REJECT(hdrInfoFrame.enabled,1);REJECT(layer[0].hdrStaticMetadata.enabled,1);
 REJECT(layer[1].hdrStaticMetadata.enabled,1);REJECT(layer[1].pSurfaceEvo[0],&surface);
 REJECT(layer[1].pSurfaceEvo[1],&surface);REJECT(layer[0].tf,1);REJECT(tf,1);
 REJECT(layer[0].cscMatrix,0);REJECT(layer[0].sizeOut.width,1920);REJECT(cursor.pSurfaceEvo,&surface);
 f=good;f.layer[0].inputLut=(Lut){1,&surface};assert(!ValidateColorPassthroughFlipState(&dev,0,&timings,&f));
 f=good;f.layer[0].tmoLut=(Lut){1,&surface};assert(!ValidateColorPassthroughFlipState(&dev,0,&timings,&f));
 f=good;f.outputLut=(Lut){1,&surface};assert(!ValidateColorPassthroughFlipState(&dev,0,&timings,&f));
 f=good;f.layer[0].csc11Override=(Override){1,0};assert(!ValidateColorPassthroughFlipState(&dev,0,&timings,&f));
 f=good;timings.viewPort.out.width=1920;assert(!ValidateColorPassthroughFlipState(&dev,0,&timings,&f));
 timings.viewPort.out.width=3840;f.hdmiVsifMetadata.payloadSize=0;
 assert(!nvIsNativeLldvSurface(&f));f.layer[0].tf=1;
 assert(ValidateColorPassthroughFlipState(&dev,0,&timings,&f)); /* ordinary path unchanged */
}
""".replace('@@VSIF@@',vsif).replace('@@NATIVE@@',native))

    def test_native_lldv_active_reads_current_head_not_requested_properties(self):
        root = self.sources()[0]
        current = function((root/'src/nvidia-modeset/src/nvkms.c').read_text(), 'CurrentNativeLldvActive')
        color = function((root/'src/nvidia-modeset/src/nvkms-hw-flip.c').read_text(), 'nvIsNativeLldvColor')
        vsif = (root/'src/common/inc/nvkms-dv-vsif.h').read_text().replace('#include "nvtypes.h"', '')
        self.compile_run(r"""
#include <assert.h>
#include <string.h>
typedef unsigned NvU32;typedef unsigned char NvU8;typedef int NvBool;
#define NV_TRUE 1
#define NV_FALSE 0
#define TRUE 1
#define FALSE 0
#define NVKMS_MAX_HEADS_PER_DISP 2
#define NV_INVALID_HEAD (~0u)
#define NVKMS_OUTPUT_TF_NONE 0
enum {NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_FORMAT_YCbCr422=1,
 NV_KMS_DPY_ATTRIBUTE_COLOR_RANGE_LIMITED=1,NVKMS_OUTPUT_COLORIMETRY_BT2100=1,
 NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_BPC_12=12};
struct NvKmsHdmiVsifMetadata {NvU8 payload[27];NvU32 payloadSize;};
typedef struct {int format,bpc,range,colorimetry;} NVDpyAttributeColor;
typedef struct {int bypassComposition,postcompColorPassthrough,tf;
 struct {int enabled;}hdrInfoFrameOverride;
 struct NvKmsHdmiVsifMetadata hdmiVsifMetadata;} NVDispHeadStateEvoRec;
typedef struct {NVDispHeadStateEvoRec headState[2];unsigned primary;int active;} NVDispEvoRec;
typedef struct {NVDispEvoRec*pDispEvo;unsigned apiHead;int hdmi;
 struct {NVDpyAttributeColor color;}currentAttributes;}NVDpyEvoRec;
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
static int nvApiHeadIsActive(const NVDispEvoRec*d,unsigned h){return h<2 && d->active;}
static unsigned nvGetPrimaryHwHead(const NVDispEvoRec*d,unsigned h){(void)h;return d->primary;}
@@VSIF@@
@@COLOR@@
@@CURRENT@@
int main(void){
 NVDispEvoRec disp={.primary=1,.active=1};NVDpyEvoRec d={&disp,0,1,{{1,12,1,1}}};
 NVDispHeadStateEvoRec*s=&disp.headState[1];s->bypassComposition=1;
 s->hdmiVsifMetadata.payloadSize=27;memcpy(s->hdmiVsifMetadata.payload,nvDoviLowLatencyPayload,27);
 assert(CurrentNativeLldvActive(&d,0));assert(!CurrentNativeLldvActive(NULL,0));
 assert(!CurrentNativeLldvActive(&d,1));assert(!CurrentNativeLldvActive(&d,2));
 disp.primary=NV_INVALID_HEAD;assert(!CurrentNativeLldvActive(&d,0));disp.primary=1;
 disp.active=0;assert(!CurrentNativeLldvActive(&d,0));disp.active=1;
 d.hdmi=0;assert(!CurrentNativeLldvActive(&d,0));d.hdmi=1;
 d.currentAttributes.color.format=0;assert(!CurrentNativeLldvActive(&d,0)); /* old RGB12, even if requested enum3 */
 d.currentAttributes.color.format=1;d.currentAttributes.color.bpc=10;assert(!CurrentNativeLldvActive(&d,0));
 d.currentAttributes.color.bpc=12;d.currentAttributes.color.range=0;assert(!CurrentNativeLldvActive(&d,0));
 d.currentAttributes.color.range=1;d.currentAttributes.color.colorimetry=0;assert(!CurrentNativeLldvActive(&d,0));
 d.currentAttributes.color.colorimetry=1;
 s->hdmiVsifMetadata.payloadSize=0;assert(!CurrentNativeLldvActive(&d,0));s->hdmiVsifMetadata.payloadSize=27;
 s->bypassComposition=0;assert(!CurrentNativeLldvActive(&d,0));s->bypassComposition=1;
 s->postcompColorPassthrough=1;assert(!CurrentNativeLldvActive(&d,0));s->postcompColorPassthrough=0;
 s->tf=1;assert(!CurrentNativeLldvActive(&d,0));s->tf=0;
 s->hdrInfoFrameOverride.enabled=1;assert(!CurrentNativeLldvActive(&d,0));s->hdrInfoFrameOverride.enabled=0;
 assert(CurrentNativeLldvActive(&d,0));
}
""".replace('@@VSIF@@',vsif).replace('@@COLOR@@',color).replace('@@CURRENT@@',current))
