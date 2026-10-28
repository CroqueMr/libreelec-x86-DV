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
typedef struct {struct {unsigned payloadSize;}hdmiVsifMetadata;
 struct {int state,eotf;struct NvKmsHDRStaticMetadata staticMetadata;}hdrInfoFrame;
} NVDispHeadStateEvoRec;
typedef struct {struct {void (*SendHdmiInfoFrame)();}*hal;
 struct {int supportsGenericSharedInfoFrames;}caps;} NVDevEvoRec;
typedef struct {NVDevEvoRec *pDevEvo;NVDispHeadStateEvoRec headState[1];} NVDispEvoRec;
static unsigned writes;static NvU8 eotf;
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
 typeof(*((NVDevEvoRec*)0)->hal) hal={send};NVDevEvoRec dev={.hal=&hal};
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
}
'''
            call = 'SendHDRInfoFrame(&disp,0,'
            if 'pInfoFrameState' in native:
                call += '&info,'
            if modern:
                call += '&a,&b,'
            call += '&edid);'
            program = program.replace('@@NATIVE@@', native).replace('@@CALL@@', call)
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
