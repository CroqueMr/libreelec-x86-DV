"""Run the independent R615 typed packet/slot admission and accepted ledger."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_NVIDIA_SOURCE'), 'requires replayed native R615')
class NvidiaHdr10PlusTransport(unittest.TestCase):
    def test_failed_generic_disable_blocks_vrr_handoff_on_same_reassigned_head(self):
        root=Path(os.environ['CB1_NVIDIA_SOURCE'])
        hdmi=(root/'src/nvidia-modeset/src/nvkms-hdmi.c').read_text()
        apply=function(hdmi,'nvCb1HdrApply')
        transition=function(hdmi,'nvCb1HdrVrrTransitionValid') if 'nvCb1HdrVrrTransitionValid(' in hdmi else ''
        validate=function((root/'src/nvidia-modeset/src/nvkms-modeset.c').read_text(),'ValidateProposedFlipHwStateOneSubDev')
        program=r'''
#include <assert.h>
#include <stddef.h>
#include "nvkms-cb1-hdr.h"
#define NVKMS_DPY_VRR_TYPE_NONE 0
#define NVKMS_SET_MODE_ONE_HEAD_STATUS_INVALID_FLIP 6
#define TRUE NV_TRUE
#define FALSE NV_FALSE
typedef struct {struct {int type;}vrr;struct {int possibleUsage;}viewPort;} NVHwModeTimingsEvo;
typedef struct {int unused;} NVDispHeadInfoFrameStateEvoRec;
typedef struct {unsigned bpc;} NVDpyAttributeColor;
typedef struct {int unused;} NVFlipEvoHwState;
struct Dev;
typedef struct {struct Dev*pDevEvo;struct {unsigned activeRmId;struct NvKmsCb1HdrLedger cb1HdrLedger;}headState[1];} NVDispEvoRec;
typedef struct Dev {unsigned numApiHeads;NVDispEvoRec*pDispEvo[1];struct {int supportsGenericSharedInfoFrames;}caps;} NVDevEvoRec;
typedef struct {int hdmi;} NVDpyEvoRec;
typedef struct {int changed,dpyIdList;unsigned hwHeadsMask;struct {NVDpyAttributeColor color;}attributes;
 NVDispHeadInfoFrameStateEvoRec infoFrame;struct NvKmsCb1Hdr cb1Hdr;int cb1Primary;unsigned cb1Slot;} NVProposedModeSetStateOneApiHead;
typedef struct {NVProposedModeSetStateOneApiHead apiHead[1];struct {NVHwModeTimingsEvo timings;void*pConnectorEvo;}head[1];} NVProposedModeSetHwStateOneDisp;
typedef struct {struct {NVFlipEvoHwState flip;}head[1];} NVProposedModeSetHwStateOneSubDev;
struct NvKmsSetModeOneDispReply {struct {int status;}head[1];};
#define FOR_EACH_EVO_HW_HEAD_IN_MASK(mask,h) for(h=0;h<1 && ((mask)&1);h++)
#define nvDpyIdListIsEmpty(x) (!(x))
#define nvOverrideScalingUsageBounds(...) ((void)0)
#define nvValidateFlipEvoHwState(...) NV_TRUE
/* The packet/depth contract is tested separately; isolate native slot handoff. */
#define nvCb1HdrValidate(d,c,t,i,f,h,p,s) (*(s)=0,NV_TRUE)
static NVDpyEvoRec testDpy={1};
#define nvGetOneArbitraryDpyEvo(list,disp) ((void)(list),(void)(disp),&testDpy)
#define nvPopCount32(x) ((x)&1)
#define nvCountDpyIdsInDpyIdList(x) ((x)?1:0)
static NvBool nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
static unsigned hwOwner,writes,disables;static int failClear;
static NvBool nvCb1HdrWrite(const NVDispEvoRec*d,unsigned head,unsigned slot,unsigned owner,const NvU8*packet){
 (void)d;assert(!head&&slot==1);
 if(packet){hwOwner=owner;writes++;return NV_TRUE;}
 disables++;assert(owner==7);if(failClear)return NV_FALSE;hwOwner=0;return NV_TRUE;
}
@@APPLY@@
@@TRANSITION@@
@@VALIDATE@@
int main(void){
 NVDevEvoRec dev={.numApiHeads=1};NVDispEvoRec disp={.pDevEvo=&dev};dev.pDispEvo[0]=&disp;disp.headState[0].activeRmId=7;
 struct NvKmsCb1Hdr hdr={.specified=1,.enabled=1},clear={.specified=1};
 nvCb1HdrApply(&disp,0,&hdr,1);assert(hwOwner==7&&writes==1);
 failClear=1;nvCb1HdrApply(&disp,0,&clear,0);
 assert(hwOwner==7&&disp.headState[0].cb1HdrLedger.status==2&&disp.headState[0].cb1HdrLedger.slot==1);
 NVProposedModeSetHwStateOneDisp p={0};NVProposedModeSetHwStateOneSubDev sd={0};struct NvKmsSetModeOneDispReply reply={0};
 p.apiHead[0].changed=1;p.apiHead[0].dpyIdList=1;p.apiHead[0].hwHeadsMask=1;p.head[0].timings.vrr.type=1;
 disp.headState[0].activeRmId=8; /* New connector/mode wants this same physical packet register. */
 assert(!ValidateProposedFlipHwStateOneSubDev(&dev,&p,&sd,&reply));
 assert(hwOwner==7&&writes==1&&disables==1);
 failClear=0;nvCb1HdrApply(&disp,0,&clear,0);assert(hwOwner==0&&!disp.headState[0].cb1HdrLedger.slot);
 assert(ValidateProposedFlipHwStateOneSubDev(&dev,&p,&sd,&reply));
 hwOwner=8;unsigned before=disables; /* Native EMP can own GENERIC only after successful clear. */
 nvCb1HdrApply(&disp,0,&clear,0);assert(hwOwner==8&&disables==before);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src,binary=Path(tmp)/'check.c',Path(tmp)/'check'
            src.write_text(program.replace('@@APPLY@@',apply).replace('@@TRANSITION@@',transition).replace('@@VALIDATE@@',validate))
            build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter',
                '-I'+str(root/'src/common/inc'),'-I'+str(root/'src/common/sdk/nvidia/inc'),str(src),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_blackwell_real_c8_avi_pairs_do_not_share_hdr10plus_slot(self):
        root=Path(os.environ['CB1_NVIDIA_SOURCE'])
        modes=root/'src/nvidia-modeset/src'
        lib=root/'src/common/modeset/hdmipacket'
        blocks=[]
        for path,names in [(lib/'nvhdmipkt_C871.c',[
                'isInfoframeOffsetAvailable','disableInfoframeC871','updateAdvancedInfoframeCtrlC871',
                'hdmiAdvancedPacketCtrlC871','programAdvancedInfoframeC871']),
                (lib/'nvhdmipkt.c',['NvHdmiPkt_SetupAdvancedInfoframe','NvHdmiPkt_AdvancedPacketCtrl']),
                (modes/'nvkms-evo1.c',['nvEvo1NvtToHdmiInfoFramePacketType']),
                (modes/'nvkms-evo3.c',['NvtToHdmiLibGenericInfoFramePktType',
                    'ConstructAdvancedInfoFramePacket','nvEvoSendHdmiInfoFrameC8']),
                (modes/'nvkms-hdmi.c',['UpdateInfoFrameFlipStatePost','nvCb1HdrWrite'])]:
            source=path.read_text()
            blocks.extend(function(source,n) for n in names)
        program=r'''
#include <stdlib.h>
#include <string.h>
#include "nvkms-types.h"
#include "nvkms-utils.h"
#include "nvkms-evo1.h"
#include "nvkms-evo3.h"
#include "hdmi_spec.h"
#include "hdmipacket/nvhdmipkt_common.h"
#include "hdmipacket/nvhdmipkt_class.h"
#include "hdmipacket/nvhdmipkt_internal.h"
#include "class/clc871.h"
#undef NDEBUG
#include <assert.h>
#undef nvAssert
#define nvAssert(x) assert(x)
#define nvEvoLogDev(...) abort()
static NvU32 payload[10][9],selected,word;
static void mmio_write(NvU32*b,NvU32 offset,NvU32 value){
 b[offset/4]=value;
 if(offset==NVC871_SF_GENERIC_INFOFRAME_DATA_CTRL(0)){
  selected=DRF_VAL(C871,_SF_GENERIC_INFOFRAME_DATA_CTRL,_OFFSET,value);word=0;assert(selected<10);
 }else if(offset==NVC871_SF_GENERIC_INFOFRAME_DATA(0)){
  assert(word<9);payload[selected][word++]=value;
 }
}
#undef REG_WR32
#define REG_WR32(b,o,v) mmio_write(b,o,v)
void *nvkms_memcpy(void*d,const void*s,size_t n){return memcpy(d,s,n);}
static void lock(NvHdmiPkt_CBHandle h){(void)h;}
static NvBool setTimer(NvHdmiPkt_CBHandle h,NvU32 us){(void)h;(void)us;return NV_TRUE;}
static NvBool expired(NvHdmiPkt_CBHandle h){(void)h;return NV_FALSE;}
static void print(NvHdmiPkt_CBHandle h,const char*f,...){(void)h;(void)f;}
void nvEvo1SendHdmiInfoFrame(const NVDispEvoRec*d,NvU32 h,const NvEvoInfoFrameTransmitControl*c,
 const NVT_INFOFRAME_HEADER*p,NvU32 size,NvBool sum){(void)d;(void)h;(void)c;(void)p;(void)size;(void)sum;abort();}
NVHDMIPKT_RESULT NvHdmiPkt_PacketWrite(NvHdmiPkt_Handle l,NvU32 s,NvU32 d,NvU32 h,
 NVHDMIPKT_TYPE t,NVHDMIPKT_TC c,NvU32 n,const NvU8*p){(void)l;(void)s;(void)d;(void)h;(void)t;(void)c;(void)n;(void)p;abort();}
NVHDMIPKT_RESULT NvHdmiPkt_PacketCtrl(NvHdmiPkt_Handle l,NvU32 s,NvU32 d,NvU32 h,
 NVHDMIPKT_TYPE t,NVHDMIPKT_TC c){(void)l;(void)s;(void)d;(void)h;(void)t;(void)c;abort();}
@@NATIVE@@
int main(void){
 NVDevEvoRec *dev=calloc(1,sizeof(*dev));NVDispEvoRec*disp=calloc(1,sizeof(*disp));
 NVHDMIPKT_CLASS*lib=calloc(1,sizeof(*lib));NvU32*regs=calloc(16384,sizeof(*regs));
 assert(dev&&disp&&lib&&regs);disp->pDevEvo=dev;disp->headState[0].activeRmId=7;
 lib->memMap[0].pMemBase=regs;lib->callback.acquireMutex=lock;lib->callback.releaseMutex=lock;
 lib->callback.setTimeout=setTimer;lib->callback.checkTimeout=expired;lib->callback.print=print;
 lib->programAdvancedInfoframe=programAdvancedInfoframeC871;dev->hdmiLib.handle=lib;
 struct {NVT_INFOFRAME_HEADER header;NvU8 payload[13];}avi={.header={NVT_INFOFRAME_TYPE_VIDEO,1,13}};
 NvEvoInfoFrameTransmitControl ctrl={.newEnabled=NV_TRUE,.frequency=NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_EVERY_FRAME};
 NvU8 packet[31]={0x81,1,27,0,0x8b,0x84,0x90};packet[30]=0x40;
 unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=packet[i];packet[3]=-sum;
 struct NvKmsCb1HdrRoute route={.shared=1};NvU32 slot=nvCb1HdrSlot(&route);
 for(unsigned fid=1;fid<=8;fid++){
  ctrl.newFid=fid;
  nvEvoSendHdmiInfoFrameC8(disp,0,&ctrl,&avi.header,sizeof(avi),NV_TRUE);
  UpdateInfoFrameFlipStatePost(&ctrl);
  if(fid>1){assert((payload[8][0]&255)==0x81);
   assert(FLD_TEST_DRF(C871,_SF_GENERIC_INFOFRAME_CTRL,_ENABLE,_YES,regs[NVC871_SF_GENERIC_INFOFRAME_CTRL(0,8)/4]));}
  assert(nvCb1HdrWrite(disp,0,slot,7,packet));
  assert((payload[8][0]&255)==0x81);
  assert((payload[(fid-1)%2][0]&255)==0x82);
  assert(FLD_TEST_DRF(C871,_SF_GENERIC_INFOFRAME_CTRL,_ENABLE,_YES,
   regs[NVC871_SF_GENERIC_INFOFRAME_CTRL(0,(fid-1)%2)/4]));
 }
 NvU32 before[2][9];memcpy(before,payload,sizeof(before));
 NvU32 c0=regs[NVC871_SF_GENERIC_INFOFRAME_CTRL(0,0)/4],c1=regs[NVC871_SF_GENERIC_INFOFRAME_CTRL(0,1)/4];
 assert(nvCb1HdrWrite(disp,0,slot,7,NULL));
 assert(!memcmp(before,payload,sizeof(before))&&regs[NVC871_SF_GENERIC_INFOFRAME_CTRL(0,0)/4]==c0&&
  regs[NVC871_SF_GENERIC_INFOFRAME_CTRL(0,1)/4]==c1);
 assert(FLD_TEST_DRF(C871,_SF_GENERIC_INFOFRAME_CTRL,_ENABLE,_NO,regs[NVC871_SF_GENERIC_INFOFRAME_CTRL(0,8)/4]));
 free(regs);free(lib);free(disp);free(dev);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);src=folder/'check.c';src.write_text(program.replace('@@NATIVE@@','\n'.join(blocks)))
            mk=folder/'host.mk';mk.write_text('include Makefile\n.PHONY: cb1-check\ncb1-check:\n\tcc $(filter-out -mindirect-branch% -mfunction-return% -fcf-protection%,$(CFLAGS)) -ffunction-sections -fdata-sections -no-pie -std=gnu11 -Werror -Wno-unused-parameter -Wno-unused-function -Wno-missing-braces $(TEST_SOURCE) -Wl,--gc-sections -o $(TEST_BINARY)\n\t$(TEST_BINARY)\n')
            run=subprocess.run(['make','-s','-C',str(root/'src/nvidia-modeset'),'-f',str(mk),
                'cb1-check','TARGET_ARCH=x86_64','TEST_SOURCE='+str(src),'TEST_BINARY='+str(folder/'check')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_postcommit_timeout_marks_fault_without_manufacturing_completion(self):
        root=Path(os.environ['CB1_NVIDIA_SOURCE'])
        native=function((root/'kernel-open/nvidia-drm/nvidia-drm-modeset.c').read_text(),'nv_drm_cb1_timeout')
        program=r'''
#include <assert.h>
#include <stdbool.h>
#include "nvkms-cb1-hdr.h"
struct NvKmsKapiHeadModeSetConfig {struct NvKmsCb1Hdr cb1Hdr;unsigned numDisplays,displays[1];};
struct nv_drm_crtc_state {bool cb1_commit_fault;struct {struct NvKmsKapiHeadModeSetConfig modeSetConfig;}req_config;};
#define drm_crtc_state nv_drm_crtc_state
struct drm_crtc {struct nv_drm_crtc_state*state;int flip_list;unsigned head;};
struct nv_drm_device {void*pDevice;};struct drm_device {struct nv_drm_device nv;};
typedef struct {struct nv_drm_crtc_state*old;} nv_drm_atomic_state_base_t;
#define to_nv_device(d) (&(d)->nv)
#define to_nv_crtc(x) (x)
#define to_nv_crtc_state(x) (x)
#define list_empty(x) (*(x)==0)
static struct drm_crtc_state*drm_atomic_get_old_crtc_state(nv_drm_atomic_state_base_t*s,struct drm_crtc*c){(void)c;return s->old;}
static unsigned events,faults;
static void __nv_drm_handle_flip_event(struct drm_crtc*c){events++;c->flip_list=0;}
static bool mark(void*d,unsigned display,unsigned head){(void)d;assert(display==7&&head==1);faults++;return true;}
static struct {bool(*markHdr10PlusFault)(void*,unsigned,unsigned);}api={mark},*nvKms=&api;
@@NATIVE@@
int main(void){
 struct drm_device dev={0};struct nv_drm_crtc_state old={0},fresh={0};struct drm_crtc c={&fresh,1,1};
 nv_drm_atomic_state_base_t state={&old};
 fresh.req_config.modeSetConfig.numDisplays=1;fresh.req_config.modeSetConfig.displays[0]=7;
 fresh.req_config.modeSetConfig.cb1Hdr.enabled=1;
 nv_drm_cb1_timeout(&dev,&state,&c);assert(fresh.cb1_commit_fault&&faults==1&&c.flip_list==1&&!events);
 fresh.cb1_commit_fault=false;fresh.req_config.modeSetConfig.cb1Hdr.enabled=0;old.req_config.modeSetConfig.cb1Hdr.enabled=1;
 nv_drm_cb1_timeout(&dev,&state,&c);assert(fresh.cb1_commit_fault&&faults==2&&c.flip_list==1&&!events);
 old.req_config.modeSetConfig.cb1Hdr.enabled=0;
 nv_drm_cb1_timeout(&dev,&state,&c);assert(c.flip_list==1&&!events);
 fresh.cb1_commit_fault=false;nv_drm_cb1_timeout(&dev,&state,&c);assert(!c.flip_list&&events==1);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src,binary=Path(tmp)/'check.c',Path(tmp)/'check'
            src.write_text(program.replace('@@NATIVE@@',native))
            build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-I'+str(root/'src/common/inc'),'-I'+str(root/'src/common/sdk/nvidia/inc'),str(src),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_real_implicit_fence_import_precedes_preflight_and_unwinds_once(self):
        root=Path(os.environ['CB1_NVIDIA_SOURCE'])
        source=(root/'kernel-open/nvidia-drm/nvidia-drm-modeset.c').read_text()
        native='\n'.join(function(source,n) for n in ['nv_drm_cb1_preflight','nv_drm_cb1_unprepare','nv_drm_cb1_prepare'])
        kernel=Path(os.environ.get('CB1_KERNEL_SOURCE',root.parent/'kernel'))
        helpers=function((kernel/'drivers/gpu/drm/drm_gem_atomic_helper.c').read_text(),'drm_gem_plane_helper_prepare_fb')
        helpers+='\n'+function((kernel/'drivers/gpu/drm/drm_atomic_helper.c').read_text(),'drm_atomic_helper_prepare_planes')
        helpers+='\n'+function((kernel/'drivers/gpu/drm/drm_atomic_helper.c').read_text(),'drm_atomic_helper_unprepare_planes')
        program=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include <stdlib.h>
#include "nvkms-cb1-hdr.h"
#define HZ 100
struct dma_fence {bool ready;};struct dma_fence_chain {struct dma_fence base;};
enum dma_resv_usage {DMA_RESV_USAGE_KERNEL,DMA_RESV_USAGE_WRITE};
struct drm_gem_object {struct dma_fence*resv;};
struct drm_framebuffer {struct {size_t num_planes;}*format;struct drm_gem_object*obj;};
struct drm_crtc_state {struct {struct {struct NvKmsCb1Hdr cb1Hdr;}modeSetConfig;}req_config;};
struct drm_crtc {struct drm_crtc_state*state;int flip_list;};
struct drm_plane_state {struct drm_framebuffer*fb;struct dma_fence*fence;struct drm_crtc*crtc;};
struct drm_plane;
struct drm_plane_helper_funcs {int(*prepare_fb)(struct drm_plane*,struct drm_plane_state*);
 void(*cleanup_fb)(struct drm_plane*,struct drm_plane_state*);
 int(*begin_fb_access)(struct drm_plane*,struct drm_plane_state*);
 void(*end_fb_access)(struct drm_plane*,struct drm_plane_state*);};
struct drm_plane {struct drm_plane_helper_funcs*helper_private;};
struct drm_connector_state {void*writeback_job;};struct drm_connector {int unused;};
struct nv_drm_device {int flip_event_wq;};struct drm_device {struct nv_drm_device nv;};
typedef struct drm_atomic_commit {bool cb1_planes_prepared;struct drm_crtc*xcrtc;
 struct drm_crtc_state*xstate;struct drm_plane*xplane;struct drm_plane_state*xps;} nv_drm_atomic_state_base_t;
#define to_nv_atomic_state(x) (x)
#define to_nv_crtc_state(x) (x)
#define to_nv_crtc(x) (x)
#define to_nv_device(x) (&(x)->nv)
#define for_each_new_crtc_in_state(a,b,c,i) for(i=0,b=(a)->xcrtc,c=(a)->xstate;i<1;i++)
#define for_each_new_plane_in_state(a,b,c,i) for(i=0,b=(a)->xplane,c=(a)->xps;i<1;i++)
#define for_each_new_connector_in_state(a,b,c,i) for(i=0,b=NULL,c=NULL;i<0;i++)
#define list_empty(x) (*(x)==0)
#define wait_event_timeout(wq,condition,t) ((void)(wq),(void)(t),(condition)?1:0)
#define WARN_ON_ONCE(x) ((void)(x))
#define DRIVER_GEM 1
static unsigned imports,cleanups,begins,ends;static int resvError;
static bool drm_core_check_feature(struct drm_device*d,int f){(void)d;(void)f;return true;}
static int drm_writeback_prepare_job(void*p){(void)p;return 0;}
static struct dma_fence*dma_fence_get(struct dma_fence*f){return f;}
static void dma_fence_put(struct dma_fence*f){(void)f;}
static struct drm_gem_object*drm_gem_fb_get_obj(struct drm_framebuffer*f,size_t i){assert(!i);return f->obj;}
static int dma_resv_get_singleton(struct dma_fence*r,enum dma_resv_usage usage,struct dma_fence**out){
 assert(usage==DMA_RESV_USAGE_WRITE);imports++;*out=r;return resvError;}
static struct dma_fence_chain*dma_fence_chain_alloc(void){abort();}
static void dma_fence_chain_init(struct dma_fence_chain*c,struct dma_fence*a,struct dma_fence*b,int i){(void)c;(void)a;(void)b;(void)i;abort();}
static bool dma_fence_is_signaled(struct dma_fence*f){return f->ready;}
static int dma_fence_wait_timeout(struct dma_fence*f,bool intr,int t){assert(intr&&t==3*HZ);return f->ready?1:0;}
static int dma_fence_get_status(struct dma_fence*f){return f->ready?1:0;}
@@HELPERS@@
static void cleanup(struct drm_plane*p,struct drm_plane_state*s){(void)p;(void)s;cleanups++;}
static int begin(struct drm_plane*p,struct drm_plane_state*s){(void)p;(void)s;begins++;return 0;}
static void end(struct drm_plane*p,struct drm_plane_state*s){(void)p;(void)s;ends++;}
@@NATIVE@@
int main(void){
 struct drm_device dev={0};struct drm_crtc_state old={0},fresh={0};struct drm_crtc crtc={&old,0};
 struct dma_fence implicit={false};struct drm_gem_object obj={&implicit};
 typeof(*((struct drm_framebuffer*)0)->format) format={1};struct drm_framebuffer fb={&format,&obj};
 struct drm_plane_state ps={&fb,NULL,&crtc};
 struct drm_plane_helper_funcs ops={drm_gem_plane_helper_prepare_fb,cleanup,begin,end};struct drm_plane p={&ops};
 nv_drm_atomic_state_base_t s={.xcrtc=&crtc,.xstate=&fresh,.xplane=&p,.xps=&ps};
 fresh.req_config.modeSetConfig.cb1Hdr.enabled=1;
 assert(nv_drm_cb1_prepare(&dev,&s,true)==-EBUSY);
 assert(ps.fence==&implicit&&imports==1&&cleanups==1&&ends==1&&!s.cb1_planes_prepared);
 nv_drm_cb1_unprepare(&dev,&s);assert(cleanups==1);
 ps.fence=NULL;implicit.ready=true;imports=cleanups=begins=ends=0;
 assert(nv_drm_cb1_prepare(&dev,&s,false)==0&&s.cb1_planes_prepared&&imports==1);
 assert(nv_drm_cb1_prepare(&dev,&s,false)==0&&imports==1);
 nv_drm_cb1_unprepare(&dev,&s);assert(cleanups==1&&begins==1&&ends==1&&!s.cb1_planes_prepared);
 nv_drm_cb1_unprepare(&dev,&s);assert(cleanups==1);
 ps.fence=NULL;resvError=-ENOMEM;imports=cleanups=0;
 assert(nv_drm_cb1_prepare(&dev,&s,false)==-ENOMEM&&!s.cb1_planes_prepared&&imports==1&&!cleanups);
 fresh.req_config.modeSetConfig.cb1Hdr.enabled=0;resvError=0;ps.fence=NULL;imports=0;
 assert(nv_drm_cb1_prepare(&dev,&s,true)==0&&!s.cb1_planes_prepared&&!imports&&!ps.fence);
 ops=(struct drm_plane_helper_funcs){0}; /* Exact NVIDIA path: no prepare/cleanup callbacks. */
 fresh.req_config.modeSetConfig.cb1Hdr.enabled=1;implicit.ready=false;
 assert(nv_drm_cb1_prepare(&dev,&s,true)==-EBUSY&&ps.fence==&implicit&&imports==1&&!s.cb1_planes_prepared);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src,binary=Path(tmp)/'check.c',Path(tmp)/'check'
            src.write_text(program.replace('@@HELPERS@@',helpers).replace('@@NATIVE@@',native))
            build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-Wno-unused-parameter','-Wno-unused-but-set-variable',
                '-I'+str(root/'src/common/inc'),'-I'+str(root/'src/common/sdk/nvidia/inc'),str(src),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_strict_depth_retries_native_ten_only_after_rejected_twelve(self):
        root=Path(os.environ['CB1_NVIDIA_SOURCE'])
        native=function((root/'src/nvidia-modeset/kapi/src/nvkms-kapi.c').read_text(),'nvCb1HdrSetMode')
        program=r'''
#include <assert.h>
#include <stddef.h>
#include "nvkms-cb1-hdr.h"
#define NVKMS_MAX_SUBDEVICES 1
#define NVKMS_MAX_HEADS_PER_DISP 1
#define NVKMS_IOCTL_KAPI_CB1_HDR 0x10000
#define NVKMS_SET_MODE_STATUS_SUCCESS 0
struct NvKmsKapiDevice {void*pKmsOpen;};
struct NvKmsCb1KapiParams {struct {struct {struct {int commit;struct {struct {int colorBpc;}head[1];}disp[1];}request;
 struct {int status;}reply;}mode;}u;struct NvKmsCb1Hdr hdr[1][1];};
static unsigned calls,writes;static int maxDepth=10;
static int nvkms_ioctl_from_kapi_try_pmlock(void*o,unsigned cmd,struct NvKmsCb1KapiParams*p,size_t size){
 assert(o==(void*)1&&cmd==0x10000&&size==sizeof(*p));calls++;
 assert(p->hdr[0][0].packet[0]==0x81);
 int depth=p->u.mode.request.disp[0].head[0].colorBpc;
 p->u.mode.reply.status=depth>maxDepth?1:0;
 if(!p->u.mode.reply.status&&p->u.mode.request.commit)writes++;
 return !p->u.mode.reply.status;
}
@@NATIVE@@
int main(void){
 struct NvKmsKapiDevice dev={(void*)1};struct NvKmsCb1KapiParams p={0};
 p.hdr[0][0].enabled=1;p.hdr[0][0].packet[0]=0x81;p.u.mode.request.disp[0].head[0].colorBpc=12;
 assert(nvCb1HdrSetMode(&dev,&p)&&calls==2&&!writes&&p.u.mode.request.disp[0].head[0].colorBpc==10);
 calls=0;p.u.mode.request.commit=1;p.u.mode.request.disp[0].head[0].colorBpc=12;
 assert(nvCb1HdrSetMode(&dev,&p)&&calls==2&&writes==1);
 calls=writes=0;maxDepth=8;p.u.mode.request.disp[0].head[0].colorBpc=12;
 assert(!nvCb1HdrSetMode(&dev,&p)&&calls==2&&!writes);
 calls=0;p.hdr[0][0].enabled=0;p.u.mode.request.disp[0].head[0].colorBpc=12;
 assert(!nvCb1HdrSetMode(&dev,&p)&&calls==1&&!writes);
 calls=0;p.hdr[0][0].deepColor=1;maxDepth=12;
 assert(nvCb1HdrSetMode(&dev,&p)&&calls==1&&writes==1);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source,binary=Path(tmp)/'check.c',Path(tmp)/'check'
            source.write_text(program.replace('@@NATIVE@@',native))
            build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-I'+str(root/'src/common/inc'),'-I'+str(root/'src/common/sdk/nvidia/inc'),
                str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_late_atomic_failure_is_sticky_until_observed_successful_clear(self):
        root=Path(os.environ['CB1_NVIDIA_SOURCE'])
        native=function((root/'kernel-open/nvidia-drm/nvidia-drm-modeset.c').read_text(),'nv_drm_cb1_complete')
        program=r'''
#include <assert.h>
#include <stdbool.h>
#include "nvkms-cb1-hdr.h"
struct NvKmsKapiHeadModeSetConfig {struct NvKmsCb1Hdr cb1Hdr;unsigned numDisplays,displays[1];};
struct drm_crtc_state {bool cb1_commit_fault;struct {
 struct NvKmsKapiHeadModeSetConfig modeSetConfig;}req_config;};
#define nv_drm_crtc_state drm_crtc_state
struct drm_crtc {struct drm_crtc_state*state;unsigned head;};
struct nv_drm_device {void*pDevice;};struct drm_device {struct nv_drm_device nv;};
typedef struct {struct drm_crtc*xcrtc;struct drm_crtc_state*xstate;} nv_drm_atomic_state_base_t;
static struct drm_crtc_state *drm_atomic_get_old_crtc_state(nv_drm_atomic_state_base_t*s,struct drm_crtc*c){(void)c;return s->xstate;}
#define to_nv_device(d) (&(d)->nv)
#define to_nv_crtc(x) (x)
#define to_nv_crtc_state(x) (x)
#define for_each_new_crtc_in_state(a,b,c,i) for(i=0,b=(a)->xcrtc,c=(a)->xstate;i<1;i++)
static unsigned faults,status=2;
static bool mark(void*d,unsigned display,unsigned head){(void)d;assert(display==7&&head==1);faults++;return true;}
static bool query(void*d,unsigned display,unsigned head,unsigned*out){(void)d;assert(display==7&&head==1);*out=status;return true;}
static struct {bool(*markHdr10PlusFault)(void*,unsigned,unsigned);bool(*getHdr10PlusState)(void*,unsigned,unsigned,unsigned*);} api={mark,query},*nvKms=&api;
@@NATIVE@@
int main(void){
 struct drm_device dev={0};struct drm_crtc_state s={0};struct drm_crtc c={&s,1};
 nv_drm_atomic_state_base_t a={&c,&s};s.req_config.modeSetConfig.numDisplays=1;s.req_config.modeSetConfig.displays[0]=7;
 s.req_config.modeSetConfig.cb1Hdr.enabled=1;
 nv_drm_cb1_complete(&dev,&a,false);assert(s.cb1_commit_fault&&faults==1);
 nv_drm_cb1_complete(&dev,&a,true);assert(s.cb1_commit_fault);
 s.req_config.modeSetConfig.cb1Hdr.enabled=0;
 nv_drm_cb1_complete(&dev,&a,true);assert(s.cb1_commit_fault);
 status=0;nv_drm_cb1_complete(&dev,&a,true);assert(!s.cb1_commit_fault);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source,binary=Path(tmp)/'check.c',Path(tmp)/'check'
            source.write_text(program.replace('@@NATIVE@@',native))
            build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-I'+str(root/'src/common/inc'),'-I'+str(root/'src/common/sdk/nvidia/inc'),
                str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_live_transport_query_fails_closed_on_allocation_or_native_error(self):
        root=Path(os.environ['CB1_NVIDIA_SOURCE'])
        native=function((root/'src/nvidia-modeset/kapi/src/nvkms-kapi.c').read_text(),'GetHdr10PlusState')
        program=r'''
#include <assert.h>
#include <stddef.h>
#include <stdlib.h>
typedef unsigned NvU32;typedef int NvBool;typedef unsigned NvKmsKapiDisplay;
#define NV_FALSE 0
#define NV_CB1_QUERY 2
#define NVKMS_IOCTL_KAPI_CB1_HDR 0x10000
#define nvNvU32ToDpyId(x) (x)
struct NvKmsKapiDevice {unsigned hKmsDevice,hKmsDisp;void*pKmsOpen;};
struct NvKmsCb1KapiParams {unsigned operation;struct {unsigned device,disp,dpy,head,status,potential;}query;};
static int noMemory,noNative;
static __attribute__((unused)) void*nvKmsKapiCalloc(size_t n,size_t s){return noMemory?NULL:calloc(n,s);}
static __attribute__((unused)) void nvKmsKapiFree(void*p){free(p);}
static int nvkms_ioctl_from_kapi(void*open,unsigned cmd,struct NvKmsCb1KapiParams*p,size_t s){
 assert(open==(void*)1&&cmd==0x10000&&s==sizeof(*p)&&p->operation==2);
 assert(p->query.device==3&&p->query.disp==4&&p->query.dpy==5&&p->query.head==6);
 if(noNative)return 0;p->query.status=1;p->query.potential=1;return 1;
}
@@NATIVE@@
int main(void){
 NvU32 state=0;struct NvKmsKapiDevice dev={3,4,(void*)1};
 assert(!GetHdr10PlusState(NULL,5,6,&state)&&state==2);
 noMemory=1;assert(!GetHdr10PlusState(&dev,5,6,&state)&&state==2);noMemory=0;
 noNative=1;assert(!GetHdr10PlusState(&dev,5,6,&state)&&state==2);noNative=0;
 assert(GetHdr10PlusState(&dev,5,6,&state)&&state==1);
 assert(GetHdr10PlusState(&dev,5,6,NULL));
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source,binary=Path(tmp)/'check.c',Path(tmp)/'check'
            source.write_text(program.replace('@@NATIVE@@',native))
            build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_native_route_uses_final_depth_and_real_static_hdr_owners(self):
        root=Path(os.environ['CB1_NVIDIA_SOURCE'])
        native=function((root/'src/nvidia-modeset/src/nvkms-hdmi.c').read_text(),'nvCb1HdrValidate')
        program=r'''
#include <assert.h>
#include <stddef.h>
#include "nvkms-cb1-hdr.h"
enum {NVKMS_MAIN_LAYER=0,NVKMS_INFOFRAME_EOTF_ST2084=2,NVKMS_INFOFRAME_EOTF_HLG=3,
 NVKMS_OUTPUT_COLORIMETRY_BT2100=2,NVKMS_DPY_VRR_TYPE_NONE=0};
typedef struct {struct {int supportsGenericSharedInfoFrames;}caps;int ada,swAcr;} NVDevEvoRec;
typedef struct {NVDevEvoRec*pDevEvo;} NVDispEvoRec;
typedef struct {NVDispEvoRec*pDispEvo;int hdmi;struct {int valid;struct {
 struct {struct {int hdr10Plus;}valid;}ext861;
 struct {int static_metadata_type;struct {int smpte_st_2084_eotf;}supported_eotf;}hdr_static_metadata_info;
 struct {unsigned application_version;}hdr10PlusInfo;}info;}parsedEdid;} NVDpyEvoRec;
typedef struct {unsigned bpc;int colorimetry;} NVDpyAttributeColor;
typedef struct {int hdmi3D;struct {int type;}vrr;} NVHwModeTimingsEvo;
typedef struct {struct {int Enable;}vendorSpecificCtrl;struct {int EnableVRR;}empCtrl;} NVDispHeadInfoFrameStateEvoRec;
typedef struct {struct {int enabled,eotf;}hdrInfoFrame;struct {void*pSurfaceEvo[1];int tearing;}layer[1];
 struct {unsigned payloadSize;}hdmiVsifMetadata;} NVFlipEvoHwState;
static int nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
/* Hardware capability-query boundary; all native route assembly remains real. */
static void nvCb1HdrCaps(const NVDevEvoRec*d,struct NvKmsCb1HdrRoute*r){
 r->shared=d->caps.supportsGenericSharedInfoFrames;r->ada=d->ada;r->swAcr=d->swAcr;}
@@NATIVE@@
int main(void){
 NVDevEvoRec dev={0};NVDispEvoRec disp={&dev};NVDpyEvoRec d={.pDispEvo=&disp,.hdmi=1};
 d.parsedEdid.valid=1;d.parsedEdid.info.ext861.valid.hdr10Plus=1;
 d.parsedEdid.info.hdr_static_metadata_info.static_metadata_type=1;
 d.parsedEdid.info.hdr_static_metadata_info.supported_eotf.smpte_st_2084_eotf=1;
 NVDpyAttributeColor color={12,2};NVHwModeTimingsEvo timing={0};
 NVDispHeadInfoFrameStateEvoRec info={0};NVFlipEvoHwState flip={.hdrInfoFrame={1,2},.layer={{.pSurfaceEvo={(void*)1}}}};
 struct NvKmsCb1Hdr c={.specified=1,.enabled=1,.deepColor=1};NvU32 slot;
 c.packet[0]=0x81;c.packet[1]=1;c.packet[2]=27;c.packet[4]=0x8b;c.packet[5]=0x84;c.packet[6]=0x90;c.packet[30]=0x40;
 unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=c.packet[i];c.packet[3]=-sum;
 assert(nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,1,&slot)&&slot==1);
 color.bpc=8;assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,1,&slot));color.bpc=12;
 assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,0,&slot));
 info.vendorSpecificCtrl.Enable=1;assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,1,&slot));
 dev.caps.supportsGenericSharedInfoFrames=1;assert(nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,1,&slot)&&slot==3);
 dev.caps.supportsGenericSharedInfoFrames=0;info.vendorSpecificCtrl.Enable=0;dev.ada=1;info.empCtrl.EnableVRR=1;
 assert(nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,1,&slot)&&slot==2);
 dev.ada=0;assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,1,&slot));info.empCtrl.EnableVRR=0;
 flip.hdmiVsifMetadata.payloadSize=27;assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,1,&slot));
 flip.hdmiVsifMetadata.payloadSize=0;flip.hdrInfoFrame.eotf=3;
 assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,1,&slot));
 c.enabled=0;assert(nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,0,&slot)&&slot==0);
 info.vendorSpecificCtrl.Enable=1;
 assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,0,&slot));
 dev.caps.supportsGenericSharedInfoFrames=1;
 assert(nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,0,&slot));
 dev.caps.supportsGenericSharedInfoFrames=0;info.vendorSpecificCtrl.Enable=0;
 timing.hdmi3D=1;assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,0,&slot));timing.hdmi3D=0;
 flip.hdrInfoFrame.enabled=0;assert(!nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,0,&slot));
 c.deepColor=0;assert(nvCb1HdrValidate(&d,&color,&timing,&info,&flip,&c,0,&slot));
 assert(nvCb1HdrValidate(NULL,NULL,NULL,NULL,NULL,&c,0,&slot)&&slot==0);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source,binary=Path(tmp)/'check.c',Path(tmp)/'check'
            source.write_text(program.replace('@@NATIVE@@',native))
            build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-I'+str(root/'src/common/inc'),'-I'+str(root/'src/common/sdk/nvidia/inc'),
                str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_metadata_requires_caller_submitted_primary_before_helper_expansion(self):
        root = Path(os.environ['CB1_NVIDIA_SOURCE'])
        native = function((root/'kernel-open/nvidia-drm/nvidia-drm-modeset.c').read_text(),
                          'nv_drm_cb1_check_frame')
        program = r'''
#include <assert.h>
#include <errno.h>
#include <stddef.h>
struct drm_crtc {void*primary;};
struct drm_connector_state {void*hdr10plus_metadata;struct drm_crtc*crtc;};
struct drm_plane_state {void*fb;struct drm_crtc*crtc;};
typedef struct {struct drm_plane_state*primary;} nv_drm_atomic_state_base_t;
static struct drm_plane_state*drm_atomic_get_new_plane_state(nv_drm_atomic_state_base_t*s,void*p){
 (void)p;return s->primary;}
@@NATIVE@@
int main(void){
 struct drm_crtc crtc={0},foreign={0};struct drm_connector_state c={(void*)1,&crtc};
 nv_drm_atomic_state_base_t state={0};
 assert(nv_drm_cb1_check_frame(&state,&c)==-EINVAL);
 struct drm_plane_state p={(void*)1,&crtc};state.primary=&p;
 assert(nv_drm_cb1_check_frame(&state,&c)==0);
 p.fb=NULL;assert(nv_drm_cb1_check_frame(&state,&c)==-EINVAL);p.fb=(void*)1;
 p.crtc=&foreign;assert(nv_drm_cb1_check_frame(&state,&c)==-EINVAL);p.crtc=&crtc;
 c.crtc=NULL;assert(nv_drm_cb1_check_frame(&state,&c)==-EINVAL);
 c.hdr10plus_metadata=NULL;assert(nv_drm_cb1_check_frame(&state,&c)==0);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source,binary=Path(tmp)/'check.c',Path(tmp)/'check'
            source.write_text(program.replace('@@NATIVE@@',native))
            build=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_preflight_rejects_pending_and_waits_before_any_commit(self):
        root = Path(os.environ['CB1_NVIDIA_SOURCE'])
        native = function((root/'kernel-open/nvidia-drm/nvidia-drm-modeset.c').read_text(),
                          'nv_drm_cb1_preflight')
        program = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include "nvkms-cb1-hdr.h"
#define HZ 100
struct dma_fence {bool ready;int error;};
struct drm_crtc;
struct drm_plane {int type;};
struct drm_plane_state {struct drm_crtc*crtc;struct dma_fence*fence;};
struct drm_crtc_state {struct {struct {struct NvKmsCb1Hdr cb1Hdr;}modeSetConfig;}req_config;};
struct drm_crtc {struct drm_crtc_state*state;int flip_list;};
struct nv_drm_device {int flip_event_wq;};
struct drm_device {struct nv_drm_device nv;};
typedef struct {struct drm_crtc*xcrtc;struct drm_crtc_state*xstate;struct drm_plane*xplane;struct drm_plane_state*xps;} nv_drm_atomic_state_base_t;
#define to_nv_device(x) (&(x)->nv)
#define to_nv_crtc(x) (x)
#define to_nv_crtc_state(x) (x)
#define for_each_new_crtc_in_state(a,b,c,i) for(i=0,b=(a)->xcrtc,c=(a)->xstate;i<1;i++)
#define for_each_new_plane_in_state(a,b,c,i) for(i=0,b=(a)->xplane,c=(a)->xps;i<1;i++)
#define list_empty(x) (*(x)==0)
static unsigned waits,reads;static int completion,fenceCompletion=1;
#define wait_event_timeout(wq,condition,t) ((void)(wq),(void)(t),waits++,completion)
static __attribute__((unused)) int dma_fence_wait(struct dma_fence*f,bool interruptible){
 assert(interruptible);reads++;return f->error?f->error:0;}
static __attribute__((unused)) int dma_fence_wait_timeout(struct dma_fence*f,bool interruptible,int timeout){
 assert(interruptible&&timeout==3*HZ);reads++;return f->error?f->error:fenceCompletion;}
static bool dma_fence_is_signaled(struct dma_fence*f){reads++;return f->ready;}
static __attribute__((unused)) int dma_fence_get_status(struct dma_fence*f){return f->error;}
@@NATIVE@@
int main(void){
 struct drm_device dev={0};struct drm_crtc_state old={0},fresh={0};
 struct drm_crtc c={&old,1};struct drm_plane p={0};struct dma_fence fence={false,0};
 struct drm_plane_state plane={&c,&fence};nv_drm_atomic_state_base_t state={&c,&fresh,&p,&plane};
 assert(nv_drm_cb1_preflight(&dev,&state,true)==0 && !reads&&!waits);
 fresh.req_config.modeSetConfig.cb1Hdr.enabled=1;
 assert(nv_drm_cb1_preflight(&dev,&state,true)==-EBUSY && !reads&&!waits);
 assert(nv_drm_cb1_preflight(&dev,&state,false)==-EBUSY && waits==1&&!reads);
 c.flip_list=0;assert(nv_drm_cb1_preflight(&dev,&state,true)==-EBUSY && reads==1);
 fence.ready=true;assert(nv_drm_cb1_preflight(&dev,&state,true)==0);
 fence.error=-EINTR;assert(nv_drm_cb1_preflight(&dev,&state,true)==-EINTR);
 assert(nv_drm_cb1_preflight(&dev,&state,false)==-EINTR);
 fence.error=0;assert(nv_drm_cb1_preflight(&dev,&state,false)==0);
 fenceCompletion=0;assert(nv_drm_cb1_preflight(&dev,&state,false)==-ETIMEDOUT);fenceCompletion=1;
 fresh.req_config.modeSetConfig.cb1Hdr.enabled=0;old.req_config.modeSetConfig.cb1Hdr.enabled=1;
 c.flip_list=1;assert(nv_drm_cb1_preflight(&dev,&state,true)==-EBUSY);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp)/'check.c', Path(tmp)/'check'
            source.write_text(program.replace('@@NATIVE@@', native))
            build = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-but-set-variable',
                '-I'+str(root/'src/common/inc'), '-I'+str(root/'src/common/sdk/nvidia/inc'),
                str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_native_writer_is_exact_and_failed_disable_retains_owner(self):
        root = Path(os.environ['CB1_NVIDIA_SOURCE'])
        native = (root/'src/nvidia-modeset/src/nvkms-hdmi.c').read_text()
        writers = '\n'.join(function(native, name) for name in ['nvCb1HdrWrite', 'nvCb1HdrApply'])
        program = r'''
#include <assert.h>
#include <string.h>
#include "nvkms-cb1-hdr.h"
#define nvkms_memcpy memcpy
#define DRF_DEF(a,b,c,d) 8
enum {NVHDMIPKT_SUCCESS=0,NVHDMIPKT_TYPE_GENERIC=1,NVHDMIPKT_TYPE_SHARED_GENERIC2=7,
 NVHDMIPKT_TYPE_SHARED_GENERIC9=14,
 NVHDMIPKT_TRANSMIT_CONTROL_DISABLE=0,NVHDMIPKT_TRANSMIT_CONTROL_ENABLE_EVERY_FRAME=9,
 INFOFRAME_CTRL_LOC_VSYNC=1,INFOFRAME_CTRL_RUN_MODE_ALWAYS=1};
typedef unsigned NVHDMIPKT_TYPE;typedef unsigned NVHDMIPKT_RESULT;
typedef struct {unsigned location,runMode,packetLen;NvU8*pPacket;} ADVANCED_INFOFRAME;
typedef struct {NvBool enable;} ADVANCED_INFOFRAME_CTRL;
typedef struct {struct {void*handle;}hdmiLib;} NVDevEvoRec;
typedef struct {NVDevEvoRec*pDevEvo;unsigned displayOwner;struct {
 unsigned activeRmId;struct NvKmsCb1HdrLedger cb1HdrLedger;}headState[1];} NVDispEvoRec;
static unsigned writes,disables,failure,slot,size;static NvU8 observed[36];
static unsigned NvHdmiPkt_PacketWrite(void*h,unsigned sd,unsigned owner,unsigned head,
 unsigned type,unsigned tc,unsigned n,const NvU8*p){
 (void)h;assert(sd==0&&owner==7&&head==0&&tc==1);writes++;slot=type;size=n;
 memcpy(observed,p,n);return failure;
}
static unsigned NvHdmiPkt_PacketCtrl(void*h,unsigned sd,unsigned owner,unsigned head,
 unsigned type,unsigned tc){(void)h;(void)type;assert(!sd&&owner==7&&!head&&!tc);disables++;return failure;}
static unsigned NvHdmiPkt_SetupAdvancedInfoframe(void*h,unsigned sd,unsigned head,
 unsigned type,ADVANCED_INFOFRAME*p){
 (void)h;assert(!sd&&!head&&type==14&&p->location==1&&p->runMode==1);
 writes++;slot=type;size=p->packetLen;memcpy(observed,p->pPacket,size);return failure;
}
static unsigned NvHdmiPkt_AdvancedPacketCtrl(void*h,unsigned sd,unsigned head,
 unsigned type,ADVANCED_INFOFRAME_CTRL*p){
 (void)h;assert(!sd&&!head&&type==14&&!p->enable);disables++;return failure;
}
@@WRITERS@@
int main(void){
 NVDevEvoRec dev={0};NVDispEvoRec disp={.pDevEvo=&dev};disp.headState[0].activeRmId=7;
 struct NvKmsCb1Hdr c={.specified=1,.enabled=1};
 c.packet[0]=0x81;c.packet[1]=1;c.packet[2]=27;c.packet[4]=0x8b;
 c.packet[5]=0x84;c.packet[6]=0x90;c.packet[30]=0x40;
 unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=c.packet[i];c.packet[3]=-sum;
 for(unsigned s=1;s<=3;s++){
  nvCb1HdrApply(&disp,0,&c,s);
  assert(disp.headState[0].cb1HdrLedger.status==1&&disp.headState[0].cb1HdrLedger.slot==s);
  if(s==1){assert(size==31&&slot==1&&!memcmp(observed,c.packet,31));}
  else{assert(size==(s==2?32u:36u)&&slot==(s==2?7u:14u)&&!memcmp(observed,c.packet,3)&&!observed[3]);
   assert(!memcmp(observed+4,c.packet+3,28));}
  struct NvKmsCb1Hdr clear={.specified=1};failure=1;
  nvCb1HdrApply(&disp,0,&clear,0);
  assert(disp.headState[0].cb1HdrLedger.status==2&&disp.headState[0].cb1HdrLedger.slot==s);
  failure=0;nvCb1HdrApply(&disp,0,&clear,0);
  assert(!disp.headState[0].cb1HdrLedger.status&&!disp.headState[0].cb1HdrLedger.slot);
 }
 struct NvKmsCb1Hdr clear={.specified=1};failure=1;nvCb1HdrApply(&disp,0,&c,1);
 assert(disp.headState[0].cb1HdrLedger.status==2&&!disp.headState[0].cb1HdrLedger.slot);
 failure=0;unsigned before=disables;nvCb1HdrApply(&disp,0,&clear,0);
 assert(disables==before+1&&!disp.headState[0].cb1HdrLedger.status);
 before=writes;c.specified=0;nvCb1HdrApply(&disp,0,&c,1);assert(writes==before);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp)/'check.c', Path(tmp)/'check'
            source.write_text(program.replace('@@WRITERS@@', writers))
            build = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-I'+str(root/'src/common/inc'), '-I'+str(root/'src/common/sdk/nvidia/inc'),
                str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_typed_packet_slot_depth_and_failure_contract(self):
        root = Path(os.environ['CB1_NVIDIA_SOURCE'])
        header = root/'src/common/inc/nvkms-cb1-hdr.h'
        self.assertTrue(header.is_file(), 'native typed HDR10+ contract is absent')
        program = r'''
#include <assert.h>
#include <string.h>
#include "nvkms-cb1-hdr.h"
static void checksum(NvU8*p){p[3]=0;unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=p[i];p[3]=-sum;}
int main(void){
 NvU8 p[31]={0x81,1,27,0,0x8b,0x84,0x90};p[11]=255;p[30]=0x40;checksum(p);
 assert(nvCb1HdrPacketValid(p));
 p[7]=0x40;checksum(p);assert(nvCb1HdrPacketValid(p));
 for(unsigned i=0;i<31;i++){p[i]^=1;assert(!nvCb1HdrPacketValid(p));p[i]^=1;}
 p[7]=0x80;checksum(p);assert(!nvCb1HdrPacketValid(p));p[7]=0;
 p[18]=0xa0;checksum(p);assert(!nvCb1HdrPacketValid(p));p[18]=0;
 p[29]=1;checksum(p);assert(!nvCb1HdrPacketValid(p));p[29]=0;checksum(p);
 struct NvKmsCb1HdrRoute r={.hdmi=1,.pq=1,.bt2020=1,.bpc=12,
  .primary=1,.receiver=1};
 assert(nvCb1HdrRouteValid(&r,p));
 for(unsigned bpc=0;bpc<=16;bpc++){r.bpc=bpc;assert(nvCb1HdrRouteValid(&r,p)==(bpc>=10));}r.bpc=12;
 r.hdmi=0;assert(!nvCb1HdrRouteValid(&r,p));r.hdmi=1;
 r.pq=0;assert(!nvCb1HdrRouteValid(&r,p));r.pq=1;
 r.bt2020=0;assert(!nvCb1HdrRouteValid(&r,p));r.bt2020=1;
 r.primary=0;assert(!nvCb1HdrRouteValid(&r,p));r.primary=1;
 r.async=1;assert(!nvCb1HdrRouteValid(&r,p));r.async=0;
 r.threeD=1;assert(!nvCb1HdrRouteValid(&r,p));r.threeD=0;
 r.customVsif=1;assert(!nvCb1HdrRouteValid(&r,p));r.customVsif=0;
 r.vendor=1;assert(!nvCb1HdrRouteValid(&r,p));r.shared=1;assert(nvCb1HdrRouteValid(&r,p));r.vendor=0;
 p[7]=0x40;checksum(p);r.version=0;assert(!nvCb1HdrRouteValid(&r,p));r.version=1;
 assert(nvCb1HdrRouteValid(&r,p));
 r.shared=0;assert(nvCb1HdrSlot(&r)==NV_CB1_HDR_SLOT_GENERIC);
 r.vrr=1;assert(nvCb1HdrSlot(&r)==0);r.vrr=0;
 r.swAcr=1;assert(nvCb1HdrSlot(&r)==0);
 r.ada=1;r.vrr=1;assert(nvCb1HdrSlot(&r)==NV_CB1_HDR_SLOT_SHARED2);
 r.shared=1;assert(nvCb1HdrSlot(&r)==NV_CB1_HDR_SLOT_ADVANCED9);
 struct NvKmsCb1HdrLedger l={0};
 nvCb1HdrResult(&l,1,7,1);assert(l.status==1 && l.slot==1 && l.owner==7);
 nvCb1HdrResult(&l,0,0,0);assert(l.status==2 && l.slot==1 && l.owner==7);
 nvCb1HdrResult(&l,1,8,1);assert(l.status==2 && l.slot==1 && l.owner==7);
 nvCb1HdrResult(&l,0,0,1);assert(l.status==0 && l.slot==0 && l.owner==0);
 nvCb1HdrResult(&l,2,8,0);assert(l.status==2 && l.slot==0);
 nvCb1HdrResult(&l,0,0,1);assert(l.status==0);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp)/'check.c', Path(tmp)/'check'
            source.write_text(program)
            build = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-I'+str(root/'src/common/inc'), '-I'+str(root/'src/common/sdk/nvidia/inc'),
                str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
