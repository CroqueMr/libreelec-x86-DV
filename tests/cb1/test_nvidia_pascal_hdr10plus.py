"""Execute the independent R580 deep-output and native packet owner."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


class PascalHdr10plus(unittest.TestCase):
    def native(self, path, name):
        root = os.environ.get('CB1_PASCAL_SOURCE')
        if not root:
            self.skipTest('requires privately applied R580 source')
        source = (Path(root) / path).read_text()
        self.assertTrue(name + '(' in source, 'missing native ' + name)
        return function(source, name)

    def run_c(self, code):
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp)/'check.c', Path(tmp)/'check'
            source.write_text(code)
            result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_strict_mode_requests_real_422_10_without_changing_ordinary_policy(self):
        # Removing the strict request's exact native colour/depth fields would
        # allow the original RGB8 preference to win on Pascal.
        native = self.native('src/nvidia-modeset/kapi/src/nvkms-kapi.c',
                             'ConfigureCb1DeepOutput')
        self.run_c(r'''
#include <assert.h>
typedef int NvBool;
#define NV_TRUE 1
#define NV_FALSE 0
#define NVKMS_INFOFRAME_EOTF_ST2084 2
#define NVKMS_OUTPUT_COLORIMETRY_BT2100 3
#define NV_KMS_DPY_ATTRIBUTE_REQUESTED_COLOR_SPACE_YCbCr422 4
struct NvKmsKapiHeadModeSetConfig {
 int strictDeepOutput,colorBpc,numDisplays,bActive,colorimetry;
 struct {int enabled;} hdr10plus;
 struct {int payloadSize;} hdmiVsifMetadata;
 struct {int enabled,eotf;}hdrInfoFrame;
};
struct NvKmsSetModeOneHeadRequest {
 int colorSpaceSpecified,colorSpace,colorBpcSpecified,colorBpc;
};
''' + native + r'''
int main(void){
 struct NvKmsKapiHeadModeSetConfig h={0};
 struct NvKmsSetModeOneHeadRequest r={0};
 assert(ConfigureCb1DeepOutput(&h,&r) && !r.colorSpaceSpecified);
 h.strictDeepOutput=1;assert(!ConfigureCb1DeepOutput(&h,&r));
 h.colorBpc=10;h.numDisplays=1;h.bActive=1;h.colorimetry=3;
 h.hdrInfoFrame.enabled=1;h.hdrInfoFrame.eotf=2;
 assert(ConfigureCb1DeepOutput(&h,&r));
 assert(r.colorSpaceSpecified && r.colorSpace==4 && r.colorBpcSpecified && r.colorBpc==10);
 h.hdmiVsifMetadata.payloadSize=27;assert(!ConfigureCb1DeepOutput(&h,&r));h.hdmiVsifMetadata.payloadSize=0;
 h.colorBpc=8;assert(!ConfigureCb1DeepOutput(&h,&r));h.colorBpc=10;
 h.hdrInfoFrame.eotf=3;assert(!ConfigureCb1DeepOutput(&h,&r));h.hdrInfoFrame.eotf=2;
 h.numDisplays=2;assert(!ConfigureCb1DeepOutput(&h,&r));h.numDisplays=1;
 h.strictDeepOutput=0;h.hdr10plus.enabled=1;r=(struct NvKmsSetModeOneHeadRequest){0};
 assert(ConfigureCb1DeepOutput(&h,&r) && r.colorBpc==10);
}
''')

    def test_native_hdr_capability_accepts_hlg_and_3d_capable_receiver(self):
        # A capable receiver is not an active 3D packet owner. The separate
        # packet route validates the selected mode and requested EOTF.
        native = self.native('src/nvidia-modeset/src/nvkms-dpy.c', 'nvDpyIsHDRCapable')
        self.run_c(r'''
#include <assert.h>
typedef int NvBool;
#define TRUE 1
#define FALSE 0
#define nvAssert assert
typedef struct {struct {int smpte_st_2084_eotf,future_eotf;}supported_eotf;
 int static_metadata_type;} NVT_HDR_STATIC_METADATA;
typedef struct {NVT_HDR_STATIC_METADATA hdr_static_metadata_info;int HDMI3DSupported;} NVT_EDID_INFO;
typedef struct {struct {int supportsDP13;}caps;} NVDevEvoRec;
typedef struct {NVDevEvoRec*pDevEvo;} NVDispEvoRec;
typedef struct {NVDispEvoRec*pDispEvo;struct {NVT_EDID_INFO info;int valid;}parsedEdid;
 int dp,hdmi;} NVDpyEvoRec;
static unsigned major=1,minor=3;static int revision_ok=1;
static int nvDpyUsesDPLib(const NVDpyEvoRec*d){return d->dp;}
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
static int nvDPDpyGetDpcdRevision(const NVDpyEvoRec*d,unsigned*a,unsigned*b){
 (void)d;*a=major;*b=minor;return revision_ok;
}
''' + native + r'''
int main(void){
 NVDevEvoRec dev={.caps={1}};NVDispEvoRec disp={&dev};
 NVDpyEvoRec d={.pDispEvo=&disp,.parsedEdid={.valid=1},.hdmi=1};
 NVT_HDR_STATIC_METADATA *hdr=&d.parsedEdid.info.hdr_static_metadata_info;
 for(unsigned eotfs=0;eotfs<4;eotfs++){
  hdr->supported_eotf.smpte_st_2084_eotf=eotfs&1;
  hdr->supported_eotf.future_eotf=(eotfs>>1)&1;
  for(unsigned stereo=0;stereo<2;stereo++){
   d.parsedEdid.info.HDMI3DSupported=stereo;
   for(unsigned type=0;type<3;type++){
    hdr->static_metadata_type=type;
    assert(nvDpyIsHDRCapable(&d)==(eotfs!=0 && type==1));
   }
  }
 }
 hdr->static_metadata_type=1;hdr->supported_eotf.future_eotf=1;
 d.parsedEdid.valid=0;assert(!nvDpyIsHDRCapable(&d));d.parsedEdid.valid=1;
 d.hdmi=0;assert(!nvDpyIsHDRCapable(&d));d.dp=1;
 assert(nvDpyIsHDRCapable(&d));minor=2;assert(!nvDpyIsHDRCapable(&d));minor=3;
 dev.caps.supportsDP13=0;assert(!nvDpyIsHDRCapable(&d));dev.caps.supportsDP13=1;
 revision_ok=0;assert(!nvDpyIsHDRCapable(&d));
}
''')

    def test_packet_write_disable_fault_and_test_only_keep_ownership_truthful(self):
        native = self.native('src/nvidia-modeset/src/nvkms-hdmi.c',
                             'nvCb1CommitHdr10plus')
        status = self.native('src/nvidia-modeset/src/nvkms-hdmi.c',
                             'nvCb1Hdr10plusStatus')
        reassigned = self.native('src/nvidia-modeset/src/nvkms-hdmi.c',
                                 'Cb1GenericSlotReassigned')
        self.run_c(r'''
#include <assert.h>
#include <string.h>
typedef unsigned NvU32;typedef unsigned char NvU8;typedef int NvBool;
typedef int NVHDMIPKT_RESULT;
#define TRUE 1
#define FALSE 0
#define NVHDMIPKT_SUCCESS 0
#define NVHDMIPKT_TYPE_GENERIC 3
#define NVHDMIPKT_TRANSMIT_CONTROL_ENABLE_EVERY_FRAME 7
#define NVHDMIPKT_TRANSMIT_CONTROL_DISABLE 0
#define NVHDMIPKT_TRANSMIT_CONTROL_ENABLE_EVERY_FRAME_SW_CHECKSUM 7
#define NVBIT(x) (1U << (x))
struct NvKmsCb1Hdr10plus {NvBool specified,enabled;NvU8 packet[31];};
struct NvKmsCb1Hdr10plusOwner {NvU32 rmId,status;NvBool occupied;};
typedef struct {struct {void*handle;}hdmiLib;NvU32 numApiHeads;}NVDevEvoRec;
typedef struct {NVDevEvoRec*pDevEvo;NvU32 displayOwner;
 struct {NvU32 activeRmId;struct NvKmsCb1Hdr10plusOwner hdr10plus;}headState[1];
 struct {NvU32 hwHeadsMask;struct {struct {NvBool EnableVRR;}empCtrl;}infoFrame;}apiHeadState[1];}NVDispEvoRec;
static int failure,writes,disables;static NvU8 observed[31];
static int NvHdmiPkt_PacketWrite(void*h,unsigned d,unsigned r,unsigned n,int t,int c,unsigned size,const NvU8*p){
 assert(h==(void*)1 && d==4 && r==9 && n==0 && t==3 && c==7 && size==31);
 writes++;memcpy(observed,p,31);return failure;
}
static int NvHdmiPkt_PacketCtrl(void*h,unsigned d,unsigned r,unsigned n,int t,int c){
 assert(h==(void*)1 && d==4 && r==9 && n==0 && t==3 && c==0);disables++;return failure;
}
''' + reassigned + '\n' + native + '\n' + status + r'''
int main(void){
 NVDevEvoRec dev={.hdmiLib={(void*)1},.numApiHeads=1};NVDispEvoRec disp={.pDevEvo=&dev,.displayOwner=4};
 struct NvKmsCb1Hdr10plus m={.specified=1,.enabled=1};
 struct NvKmsCb1Hdr10plusOwner *o=&disp.headState[0].hdr10plus;
 disp.headState[0].activeRmId=9;
 disp.apiHeadState[0].hwHeadsMask=1;
 for(unsigned i=0;i<31;i++)m.packet[i]=i;
 nvCb1CommitHdr10plus(&disp,0,&m,FALSE);assert(!writes && !o->status);
 nvCb1CommitHdr10plus(&disp,0,&m,TRUE);assert(writes==1 && o->occupied && o->status==1 && o->rmId==9);
 assert(!memcmp(observed,m.packet,31));
 assert(nvCb1Hdr10plusStatus(&disp,0,9,FALSE)==1);
 assert(nvCb1Hdr10plusStatus(&disp,0,10,FALSE)==2); /* another route cannot inherit active */
 assert(nvCb1Hdr10plusStatus(&disp,0,0,TRUE)==2); /* timed-out presentation latches fault */
 assert(o->occupied && o->status==2 && o->rmId==9);
 m.enabled=0;nvCb1CommitHdr10plus(&disp,0,&m,TRUE);m.enabled=1;
 nvCb1CommitHdr10plus(&disp,0,&m,TRUE);assert(o->status==1);
 failure=1;m.packet[8]=99;nvCb1CommitHdr10plus(&disp,0,&m,TRUE);
 assert(o->occupied && o->status==2 && o->rmId==9);
 failure=0;nvCb1CommitHdr10plus(&disp,0,&m,TRUE);assert(o->status==2); /* explicit clear required */
 m.enabled=0;failure=1;nvCb1CommitHdr10plus(&disp,0,&m,TRUE);assert(o->status==2 && o->occupied);
 /* A failed old clear cannot disable the native EMP owner of the new mode. */
 disp.apiHeadState[0].infoFrame.empCtrl.EnableVRR=1;failure=0;
 int before=disables;nvCb1CommitHdr10plus(&disp,0,&m,TRUE);
 assert(disables==before && o->status==2 && o->occupied && o->rmId==9);
 disp.apiHeadState[0].infoFrame.empCtrl.EnableVRR=0;
 disp.headState[0].activeRmId=10;nvCb1CommitHdr10plus(&disp,0,&m,TRUE);
 assert(disables==before && o->status==2 && o->rmId==9);
 disp.headState[0].activeRmId=9;
 failure=0;nvCb1CommitHdr10plus(&disp,0,&m,TRUE);assert(!o->status && !o->occupied && disables==3);
 nvCb1CommitHdr10plus(&disp,0,&m,TRUE);assert(disables==3);
}
''')

    def test_native_route_rejects_conflicting_owner_and_unqualified_topology(self):
        native = self.native('src/nvidia-modeset/src/nvkms-hdmi.c', 'nvCb1Hdr10plusRoute')
        self.run_c(r'''
#include <assert.h>
typedef int NvBool;typedef unsigned NvU32;typedef unsigned NVDpyIdList;
#define FALSE 0
#define TRUE 1
#define NV9770_DISPLAY 0x9770
#define NV9870_DISPLAY 0x9870
#define NVKMS_CONNECTOR_TYPE_HDMI 2
#define NVKMS_OUTPUT_COLORIMETRY_BT2100 3
#define NV_KMS_DPY_ATTRIBUTE_CURRENT_COLOR_SPACE_YCbCr422 4
#define NV_YUV420_MODE_NONE 0
typedef struct {int bpc,colorimetry,format;}NVDpyAttributeColor;
typedef struct {struct {int Enable;}vendorSpecificCtrl;struct {int EnableVRR;}empCtrl;}NVDispHeadInfoFrameStateEvoRec;
struct NvKmsCb1Vsif {int payloadSize;};
typedef struct {struct {unsigned type;}*pConnectorEvo;int hdmi;}NVDpyEvoRec;
typedef struct {struct {int dispClass;}*pDevEvo;struct {unsigned hwHeadsMask;}apiHeadState[1];}NVDispEvoRec;
static NVDpyEvoRec dpy;
static unsigned nvCountDpyIdsInDpyIdList(unsigned x){return __builtin_popcount(x);}
static NVDpyEvoRec*nvGetOneArbitraryDpyEvo(unsigned x,const NVDispEvoRec*d){(void)x;(void)d;return &dpy;}
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
''' + native + r'''
int main(void){
 typeof(*dpy.pConnectorEvo) connector={2};dpy.pConnectorEvo=&connector;dpy.hdmi=1;
 typeof(*((NVDispEvoRec*)0)->pDevEvo) dev={0x9870};NVDispEvoRec disp={.pDevEvo=&dev};
 NVDpyAttributeColor color={10,3,4};NVDispHeadInfoFrameStateEvoRec info={0};struct NvKmsCb1Vsif vsif={0};
 assert(nvCb1Hdr10plusRoute(&disp,0,1,&color,&info,&vsif,0));
 info.empCtrl.EnableVRR=1;assert(!nvCb1Hdr10plusRoute(&disp,0,1,&color,&info,&vsif,0));info.empCtrl.EnableVRR=0;
 info.vendorSpecificCtrl.Enable=1;assert(!nvCb1Hdr10plusRoute(&disp,0,1,&color,&info,&vsif,0));info.vendorSpecificCtrl.Enable=0;
 vsif.payloadSize=27;assert(!nvCb1Hdr10plusRoute(&disp,0,1,&color,&info,&vsif,0));vsif.payloadSize=0;
 color.bpc=8;assert(!nvCb1Hdr10plusRoute(&disp,0,1,&color,&info,&vsif,0));color.bpc=10;
 assert(!nvCb1Hdr10plusRoute(&disp,0,3,&color,&info,&vsif,0));
 assert(!nvCb1Hdr10plusRoute(&disp,0,1,&color,&info,&vsif,1));
 connector.type=1;assert(!nvCb1Hdr10plusRoute(&disp,0,1,&color,&info,&vsif,0));connector.type=2;
 dev.dispClass=0xc670;assert(!nvCb1Hdr10plusRoute(&disp,0,1,&color,&info,&vsif,0));
}
''')

    def test_static_strict_pq_intent_requires_the_same_native_slot_validation(self):
        gate = self.native('src/common/inc/nvkms-cb1-hdr10plus.h', 'nvCb1NeedsDeepRoute')
        self.run_c(r'''
#include <assert.h>
typedef int NvBool;
struct NvKmsCb1Hdr10plus {NvBool specified,enabled,strictDeepOutput;};
''' + gate + r'''
int main(void){
 for(unsigned flags=0;flags<8;flags++){
  struct NvKmsCb1Hdr10plus intent={flags&1,(flags>>1)&1,(flags>>2)&1};
  assert(nvCb1NeedsDeepRoute(&intent)==((flags&1) && (flags&6)));
 }
 /* Converted HDR10 with no dynamic blob must not skip slot admission. */
 struct NvKmsCb1Hdr10plus basic={1,0,1};assert(nvCb1NeedsDeepRoute(&basic));
}
''')

    def test_render_fence_preflight_is_bounded_before_acceptance(self):
        native = self.native('kernel-open/nvidia-drm/nvidia-drm-modeset.c',
                             'nv_drm_cb1_ready_fences')
        self.run_c(r'''
#include <assert.h>
#include <stddef.h>
typedef int bool;
#define false 0
#define EBUSY 16
#define ETIMEDOUT 110
#define HZ 100
struct dma_fence {int signaled,error,completion_error;};
struct drm_plane_state {struct dma_fence*fence;};
struct drm_plane {int unused;};
typedef struct {struct drm_plane pp;struct drm_plane_state ss;}nv_drm_atomic_state_base_t;
#define for_each_new_plane_in_state(a,p,s,i) for(i=0,p=&(a)->pp,s=&(a)->ss;(void)p,i<1;i++)
static int waits;
static __attribute__((unused)) int dma_fence_get_status(struct dma_fence*f){return f->completion_error?f->completion_error:1;}
static long dma_fence_wait_timeout(struct dma_fence*f,int intr,long timeout){
 assert(!intr && (timeout==0 || timeout==3*HZ));if(timeout)waits++;return f->error?f->error:f->signaled;
}
''' + native + r'''
int main(void){
 struct dma_fence f={0};nv_drm_atomic_state_base_t state={.ss={&f}};
 assert(nv_drm_cb1_ready_fences(&state,1)==-EBUSY && !waits);
 assert(nv_drm_cb1_ready_fences(&state,0)==-ETIMEDOUT && waits==1);
 f.error=-5;assert(nv_drm_cb1_ready_fences(&state,0)==-5);
 assert(nv_drm_cb1_ready_fences(&state,1)==-5);
 f.error=0;f.signaled=1;assert(!nv_drm_cb1_ready_fences(&state,1));
 f.completion_error=-5;assert(nv_drm_cb1_ready_fences(&state,1)==-5);f.completion_error=0;
 state.ss.fence=NULL;assert(!nv_drm_cb1_ready_fences(&state,0));
}
''')

    def test_blocking_commit_waits_before_swap_and_does_not_fake_completion(self):
        native = self.native('kernel-open/nvidia-drm/nvidia-drm-modeset.c', 'nv_drm_atomic_commit')
        fences = self.native('kernel-open/nvidia-drm/nvidia-drm-modeset.c', 'nv_drm_cb1_ready_fences')
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdlib.h>
#include <errno.h>
typedef int NvBool;
#define HZ 100
struct list_head {int empty;};
struct nv_drm_flip {void*event;struct list_head list_entry,deferred_flip_list;};
struct drm_crtc_state {int color_mgmt_changed;};
struct drm_crtc {struct drm_crtc_state*state;};
struct nv_drm_crtc {struct drm_crtc base;struct list_head flip_list;int flip_list_lock;unsigned head;};
struct nv_drm_device {void*pDevice;int flip_event_wq;};
struct drm_device {struct nv_drm_device n;int event_lock;};
struct nv_drm_crtc_state {struct {struct {struct {int enabled;}hdr10plus;}modeSetConfig;}req_config;
 struct nv_drm_flip*nv_flip;};
typedef struct {bool cb1_prepared;}nv_drm_atomic_state_base_t;
struct dma_fence {int ready;};
struct drm_plane {int unused;};
struct drm_plane_state {struct dma_fence*fence;};
static struct drm_plane primary;
static struct drm_plane_state ps;
static struct dma_fence implicit;
static struct drm_crtc_state cs,old_cs;
static struct nv_drm_crtc c={.base={&old_cs},.flip_list={1},.head=2};
static struct nv_drm_crtc_state ns,old_ns;
static struct nv_drm_flip last;
#define to_nv_device(d) (&(d)->n)
#define to_nv_crtc(x) ((struct nv_drm_crtc*)(x))
#define to_nv_crtc_state(x) ((x)==&old_cs?&old_ns:&ns)
#define to_nv_atomic_state(x) (x)
#define for_each_new_crtc_in_state(s,p,v,i) for(i=0,p=&c.base,v=&cs;(void)(s),i<1;i++)
#define for_each_old_crtc_in_state(s,p,v,i) for(i=0,p=&c.base,v=&old_cs;(void)(s),i<1;i++)
#define for_each_new_plane_in_state(s,p,v,i) for(i=0,p=&primary,v=&ps;(void)(s),(void)p,i<1;i++)
#define list_empty(x) ((x)->empty)
#define list_last_entry(a,t,m) ((void)(a),&last)
#define list_add(a,b) ((void)(a),(void)(b))
#define spin_lock(x) ((void)(x))
#define spin_unlock(x) ((void)(x))
#define WARN_ON(x) (x)
#define NV_DRM_DEV_LOG_ERR(...) ((void)0)
#define wait_event_timeout(q,condition,timeout) ((void)(q),assert((timeout)==3*HZ),(condition))
static int swaps,swap_failure,apply_failure,prepared,unprepared,ready_calls,lut_complete=1,post_pending,faults,drained;
static int lut(void*d,unsigned h,bool wait){(void)d;assert(h==2 && wait);return lut_complete;}
static void fault(void*d,unsigned h){(void)d;assert(h==2);faults++;}
static struct {int(*checkLutNotifier)(void*,unsigned,bool);void(*markHdr10plusFault)(void*,unsigned);}api={lut,fault},*nvKms=&api;
static int drm_atomic_helper_prepare_planes(struct drm_device*d,nv_drm_atomic_state_base_t*s){
 (void)d;assert(!s->cb1_prepared && !ps.fence);prepared++;ps.fence=&implicit;return 0;
}
static void drm_atomic_helper_unprepare_planes(struct drm_device*d,nv_drm_atomic_state_base_t*s){
 (void)d;(void)s;assert(ps.fence==&implicit);unprepared++;ps.fence=NULL;
}
static long dma_fence_wait_timeout(struct dma_fence*f,bool intr,long timeout){
 assert(f==&implicit && !intr && timeout==3*HZ);ready_calls++;return f->ready;
}
static int dma_fence_get_status(struct dma_fence*f){assert(f==&implicit);return 1;}
static int drm_atomic_helper_swap_state(nv_drm_atomic_state_base_t*s,bool stall){
 (void)s;assert(!stall);if(swap_failure)return swap_failure;c.base.state=&cs;swaps++;return 0;
}
static void drm_atomic_helper_update_legacy_modeset_state(struct drm_device*d,nv_drm_atomic_state_base_t*s){(void)d;(void)s;}
static int nv_drm_atomic_apply_modeset_config(struct drm_device*d,nv_drm_atomic_state_base_t*s,bool commit){
 (void)d;(void)s;assert(commit);if(apply_failure)return apply_failure;c.flip_list.empty=!post_pending;return 0;
}
static void drm_crtc_send_vblank_event(struct drm_crtc*c,void*e){(void)c;(void)e;}
static void nv_drm_free(void*p){free(p);}
static void __nv_drm_handle_flip_event(struct nv_drm_crtc*p){p->flip_list.empty=1;drained++;}
''' + fences + '\n' + native + r'''
int main(void){
 struct drm_device d={0};nv_drm_atomic_state_base_t state={0};
 ns.req_config.modeSetConfig.hdr10plus.enabled=1;old_ns.req_config.modeSetConfig.hdr10plus.enabled=1;
 c.flip_list.empty=0;assert(nv_drm_atomic_commit(&d,&state,false)==-EBUSY && !swaps);
 c.flip_list.empty=1;cs.color_mgmt_changed=1;lut_complete=0;
 assert(nv_drm_atomic_commit(&d,&state,false)==-EBUSY && !swaps);
 lut_complete=1;cs.color_mgmt_changed=0;assert(!ps.fence);
 assert(nv_drm_atomic_commit(&d,&state,false)==-ETIMEDOUT && !swaps && unprepared==1);
 assert(ready_calls==1 && !ps.fence && !state.cb1_prepared);
 implicit.ready=1;swap_failure=-ENOMEM;
 assert(nv_drm_atomic_commit(&d,&state,false)==-ENOMEM && !swaps && unprepared==2);
 assert(!ps.fence && !state.cb1_prepared);
 swap_failure=0;post_pending=1;
 assert(!nv_drm_atomic_commit(&d,&state,false) && swaps==1 && faults==1);
 assert(!state.cb1_prepared); /* proof is scoped to this accepted transaction */
 assert(!c.flip_list.empty && !drained); /* wait for the real native event */
 c.flip_list.empty=1;ps.fence=NULL;apply_failure=-EIO;
 assert(!nv_drm_atomic_commit(&d,&state,false) && swaps==2 && faults==2 && !drained);
 assert(!state.cb1_prepared); /* accepted state cannot report the old packet as active */
 c.base.state=&old_cs;ns.req_config.modeSetConfig.hdr10plus.enabled=0;ps.fence=NULL;
 assert(!nv_drm_atomic_commit(&d,&state,false) && swaps==3 && faults==3); /* failed explicit clear */
 c.base.state=&old_cs;old_ns.req_config.modeSetConfig.hdr10plus.enabled=0;
 ns.req_config.modeSetConfig.hdr10plus.enabled=1;ps.fence=NULL;
 assert(!nv_drm_atomic_commit(&d,&state,false) && swaps==4 && faults==4); /* failed initial enable */
 apply_failure=0;
 c.flip_list.empty=1;ns.req_config.modeSetConfig.hdr10plus.enabled=0;
 assert(!nv_drm_atomic_commit(&d,&state,false) && swaps==5 && drained==1 && faults==4);
 assert(prepared==6 && unprepared==2);
}
''')
