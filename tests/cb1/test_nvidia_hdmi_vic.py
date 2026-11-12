"""Run native HDMI emitters with their matched timing-library constructors."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_hdr10_transport import function
import test_nvidia_native_hdr as native_hdr


class NvidiaHdmiVic(unittest.TestCase):
    sources = native_hdr.NvidiaNativeHdr.sources

    def test_advertised_cta_identity_preserves_hdr_and_sdr_clear(self):
        for root in self.sources():
            source = (root/'src/nvidia-modeset/src/nvkms-hdmi.c').read_text()
            timing = (root/'src/common/modeset/timing/nvt_edidext_861.c').read_text()
            private = (root/'src/common/modeset/timing/nvtiming_pvt.h').read_text()
            native = '\n'.join(function(source, name) for name in (
                'SendVideoInfoFrame', 'SendVendorSpecificInfoFrame',
                'SendHDRInfoFrame', 'nvUpdateHdmiInfoFrames'))
            modern = 'currentTransmitCtrl' in native
            helpers = ''
            for name in ('nvHdmiCtaVic', 'nvHdmiUseCtaVic'):
                if re.search(r'\b'+name+r'\s*\(', source):
                    helpers += function(source, name)+'\n'
            if modern:
                helpers += '\n'.join(function(source, name) for name in (
                    'UpdateInfoFrameFlipStatePre', 'UpdateInfoFrameFlipStatePost'))
            sdk = '\n'.join(line for line in private.splitlines()
                            if line.startswith(('#define nvt_nvu8_set_bits', '#define nvt_get_bits')))
            sdk += '\n'+re.search(r'static const NVT_VIDEO_INFOFRAME DEFAULT_VIDEO_INFOFRAME[^;]+;', timing)[0]
            sdk += '\n'+'\n'.join(function(timing, name) for name in (
                'NvTiming_ConstructVideoInfoframe', 'NvTiming_ConstructVendorSpecificInfoframe'))
            program = r'''
#include <assert.h>
#include <stddef.h>
#include <string.h>
#include "timing/nvtiming.h"
#include "nvkms-dv-vsif.h"
#define TRUE NV_TRUE
#define FALSE NV_FALSE
#define NVMISC_MEMCPY memcpy
#define nvkms_memcpy memcpy
#define nvkms_memset memset
#define ct_assert(x) _Static_assert(x,#x)
#define nvAssert assert
#define nvEvoLogDispDebug(...) ((void)0)
#define NVKMS_MAX_FID_SLOTS 4
enum {NVKMS_HDR_INFOFRAME_STATE_TRANSITIONING=0,
 NVKMS_HDR_INFOFRAME_STATE_ENABLED=1,NVKMS_HDR_INFOFRAME_STATE_DISABLED=2};
enum {NVKMS_INFOFRAME_EOTF_SDR_GAMMA=0,NVKMS_INFOFRAME_EOTF_HDR_GAMMA=1,
 NVKMS_INFOFRAME_EOTF_ST2084=2,NVKMS_INFOFRAME_EOTF_HLG=3};
enum {NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_INIT,
 NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_SINGLE_FRAME,
 NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_EVERY_FRAME};
#define NV_EVO_INFOFRAME_TRANSMIT_CONTROL_INIT 0
#define NV_EVO_INFOFRAME_TRANSMIT_CONTROL_SINGLE_FRAME 1
#define NV_EVO_INFOFRAME_TRANSMIT_CONTROL_EVERY_FRAME 2
typedef int NvEvoInfoFrameTransmitFrequency;
@@CONTROL@@
typedef struct {NvEvoInfoFrameTransmitControl videoInfoframeTransmitCtrl,
 vendorSpecificInfoframeTransmitCtrl,hdrStaticMetadataTransmitCtrl;} NvEvoInfoframeFlipState;
typedef struct {NVT_VIDEO_INFOFRAME_CTRL ctrl; NVT_VENDOR_SPECIFIC_INFOFRAME_CTRL vendorSpecificCtrl;
 NvBool hdTimings;} NVDispHeadInfoFrameStateEvoRec;
typedef struct {int unused;} NVDpyAttributeColor;
struct NvKmsCb1Vsif {NvU8 payload[27];NvU32 payloadSize;};
struct NvKmsHDRStaticMetadata {NvU16 data[12];};
typedef struct {struct NvKmsCb1Vsif hdmiVsifMetadata;
 struct {int state,eotf;struct NvKmsHDRStaticMetadata staticMetadata;}hdrInfoFrame;} NVDispHeadStateEvoRec;
typedef struct NVDispEvoRec NVDispEvoRec;
typedef struct {struct {
 void(*SendHdmiInfoFrame)(const NVDispEvoRec*,NvU32,@@CTRLTYPE@@,const NVT_INFOFRAME_HEADER*,NvU32,NvBool);
 void(*DisableHdmiInfoFrame)(const NVDispEvoRec*,NvU32,@@DISABLECTRL@@ int);
 }*hal;
 struct {NvBool supportsGenericSharedInfoFrames;}caps;} NVDevEvoRec;
struct NVDispEvoRec {NVDevEvoRec*pDevEvo; NVDispHeadStateEvoRec headState[1];};
typedef struct {struct {NvBool valid;NVT_EDID_INFO info;}parsedEdid;NvBool hdmi;} NVDpyEvoRec;
static NvU8 avi[32],hdr[32],vendor[32];static unsigned hdr_count,vendor_count,disabled;
static int hdr_frequency;
static void send(const NVDispEvoRec*d,NvU32 head,@@CTRLTYPE@@ control,
 const NVT_INFOFRAME_HEADER*p,NvU32 size,NvBool checksum){
 (void)d;assert(head==0 && checksum && size<=32);
 switch(p->type){
 case NVT_INFOFRAME_TYPE_VIDEO:memcpy(avi,p,size);break;
 case NVT_INFOFRAME_TYPE_VENDOR_SPECIFIC:memcpy(vendor,p,size);vendor_count++;break;
 case NVT_INFOFRAME_TYPE_DYNAMIC_RANGE_MASTERING:
  memcpy(hdr,p,size);hdr_count++;hdr_frequency=@@FREQ@@;break;
 default:assert(0);
 }
}
static void disable(const NVDispEvoRec*d,NvU32 head,@@DISABLECTRL@@ int type){
 (void)d;(void)head;@@IGNORECTRL@@ assert(type==NVT_INFOFRAME_TYPE_VENDOR_SPECIFIC);disabled++;
}
static NvBool nvDpyIsHdmiEvo(const NVDpyEvoRec*d){return d->hdmi;}
static NvBool nvCb1VsifValid(const struct NvKmsCb1Vsif*v){return v->payloadSize<=27;}
static void CalculateVideoInfoFrameColorFormat(const NVDpyAttributeColor*c,NvU32 h,
 const NVT_EDID_INFO*e,NVT_VIDEO_INFOFRAME_CTRL*v){(void)c;(void)h;(void)e;(void)v;}
static void nvDpyAssignSDRInfoFramePayload(NVT_HDR_INFOFRAME_PAYLOAD*p){memset(p,0,sizeof(*p));}
@@SDK@@
@@HELPERS@@
@@NATIVE@@
static void run(NVDispEvoRec*d,NVDpyEvoRec*display,NVDispHeadInfoFrameStateEvoRec*i){
 NvEvoInfoframeFlipState fs={0};NvEvoInfoFrameTransmitControl ctrl={0};NVDpyAttributeColor color={0};
 (void)fs;(void)ctrl;hdr_count=vendor_count=disabled=0;memset(avi,0,sizeof(avi));
 NVDispHeadInfoFrameStateEvoRec original=*i;
 nvUpdateHdmiInfoFrames(d,0,&color,i,@@UPDATEARGS@@display);
 assert(memcmp(i,&original,sizeof(*i))==0);
}
int main(void){
 typeof(*((NVDevEvoRec*)0)->hal) hal={send,disable};NVDevEvoRec dev={.hal=&hal};
 NVDispEvoRec disp={.pDevEvo=&dev};NVDpyEvoRec display={.hdmi=NV_TRUE};
 NVT_EDID_INFO*edid=&display.parsedEdid.info;display.parsedEdid.valid=NV_TRUE;
 edid->ext861.revision=NVT_CEA861_REV_F;
 edid->hdr_static_metadata_info.static_metadata_type=1;
 edid->hdr_static_metadata_info.supported_eotf.smpte_st_2084_eotf=1;
 edid->hdr_static_metadata_info.supported_eotf.future_eotf=1;
 disp.headState[0].hdrInfoFrame.eotf=NVKMS_INFOFRAME_EOTF_ST2084;
 NVDispHeadInfoFrameStateEvoRec info={0};info.vendorSpecificCtrl.Enable=1;
 info.vendorSpecificCtrl.VSIFVersion=NVT_VSIF_VERSION_H14B_VSIF;
 info.vendorSpecificCtrl.HDMIFormat=NVT_HDMI_VS_BYTE4_HDMI_VID_FMT_EXT;
 const NvU8 vic[]={0,95,94,93,98};
 for(unsigned h=1;h<=4;h++)for(unsigned ext=0;ext<2;ext++){
  NVT_EDID_CEA861_INFO*cea=ext?&edid->ext861_2:&edid->ext861;
  edid->ext861.total_svd=edid->ext861_2.total_svd=0;
  cea->total_svd=1;cea->video[0]=vic[h];
  info.vendorSpecificCtrl.HDMI_VIC=h;info.ctrl.video_format_id=0;
  info.ctrl.pic_aspect_ratio=NVT_VIDEO_INFOFRAME_BYTE2_M1M0_16X9;
  for(unsigned state=0;state<=2;state++){
   disp.headState[0].hdrInfoFrame.state=state;run(&disp,&display,&info);
   assert(hdr_count==1 && "advertised CTA mode must not suppress HDR or its SDR clear");
   assert(vendor_count==0 && disabled==1 && avi[6]==vic[h]);
   assert(((avi[4]>>4)&3)==(h==4?0:2));
   assert(hdr[3]==(state==1?2:0));
   assert(hdr_frequency==(state==2?NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_SINGLE_FRAME:
                                  NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_EVERY_FRAME));
  }
 }
 /* No matching ordinary SVD, including CTA221 (not native-bit CTA93). */
 info.vendorSpecificCtrl.HDMI_VIC=3;edid->ext861_2.total_svd=0;
 for(unsigned missing=0;missing<2;missing++){
  edid->ext861.total_svd=missing;edid->ext861.video[0]=221;
  run(&disp,&display,&info);assert(hdr_count==0 && vendor_count==1 && avi[6]==0);
 }
 edid->ext861.total_svd=1;edid->ext861.video[0]=93;
 run(&disp,&display,&info);assert(hdr_count==1 && vendor_count==0 && avi[6]==93);
 edid->ext861.total_svd=0;edid->ext861_2.total_svd=1;edid->ext861_2.video[0]=93;
 edid->ext861.revision=NVT_CEA861_REV_A;
 run(&disp,&display,&info);assert(hdr_count==0 && vendor_count==1 && avi[6]==0);
 edid->ext861.revision=NVT_CEA861_REV_F;
 edid->ext861_2.total_svd=0;edid->ext861.total_svd=255;
 memset(edid->ext861.video,0,sizeof(edid->ext861.video));
 run(&disp,&display,&info);assert(hdr_count==0 && vendor_count==1 && avi[6]==0);
 edid->ext861.total_svd=1;edid->ext861.video[0]=93;
 /* Custom DV, HDMI3D and HDMI Forum VSIF remain native owners. */
 disp.headState[0].hdmiVsifMetadata.payloadSize=24;
 run(&disp,&display,&info);assert(hdr_count==0 && vendor_count==1 && avi[6]==0);
 disp.headState[0].hdmiVsifMetadata.payloadSize=0;edid->HDMI3DSupported=1;
 info.vendorSpecificCtrl.HDMIFormat=NVT_HDMI_VS_BYTE4_HDMI_VID_FMT_3D;
 run(&disp,&display,&info);assert(hdr_count==0 && vendor_count==1 && avi[6]==0);
 info.vendorSpecificCtrl.HDMIFormat=NVT_HDMI_VS_BYTE4_HDMI_VID_FMT_NONE;
 info.vendorSpecificCtrl.VSIFVersion=NVT_VSIF_VERSION_HF_VSIF;
 run(&disp,&display,&info);assert(hdr_count==0 && vendor_count==1 && avi[6]==0);
 info.vendorSpecificCtrl.HDMIFormat=NVT_HDMI_VS_BYTE4_HDMI_VID_FMT_EXT;
 info.vendorSpecificCtrl.VSIFVersion=NVT_VSIF_VERSION_H14B_VSIF;
 edid->hdr_static_metadata_info.supported_eotf.smpte_st_2084_eotf=0;
 edid->hdr_static_metadata_info.supported_eotf.future_eotf=0;
 run(&disp,&display,&info);assert(vendor_count==1 && avi[6]==0);
 /* Player-led overrides only AVI color fields and retains the selected CTA VIC. */
 info.ctrl.video_format_id=93;info.vendorSpecificCtrl.HDMI_VIC=0;
 disp.headState[0].hdmiVsifMetadata.payloadSize=sizeof(nvDoviLowLatencyPayload);
 memcpy(disp.headState[0].hdmiVsifMetadata.payload,nvDoviLowLatencyPayload,
        sizeof(nvDoviLowLatencyPayload));
 run(&disp,&display,&info);
 assert(avi[6]==93 && ((avi[3]>>5)&3)==1 && ((avi[4]>>6)&3)==3);
 assert(((avi[5]>>4)&7)==6 && ((avi[5]>>2)&3)==0 && ((avi[7]>>6)&3)==0);
 assert(vendor_count==1 && vendor[0]==NVT_INFOFRAME_TYPE_VENDOR_SPECIFIC && vendor[1]==1 && vendor[2]==27);
 assert(!memcmp(vendor+3,nvDoviLowLatencyPayload,sizeof(nvDoviLowLatencyPayload)));
 display.parsedEdid.valid=0;run(&disp,&display,&info);assert(!hdr_count && !vendor_count && !disabled);
}
'''
            program = program.replace('@@SDK@@', sdk).replace('@@HELPERS@@', helpers).replace('@@NATIVE@@', native)
            replacements = {
                '@@CONTROL@@': ('typedef struct {int frequency,newEnabled,newFid,newFlipSynchronized,curFid,activeSlot,curEnabled,curFlipSynchronized;} NvEvoInfoFrameTransmitControl;' if modern else 'typedef int NvEvoInfoFrameTransmitControl;'),
                '@@CTRLTYPE@@': ('const NvEvoInfoFrameTransmitControl*' if modern else 'NvEvoInfoFrameTransmitControl'),
                '@@DISABLECTRL@@': ('const NvEvoInfoFrameTransmitControl*control,' if modern else ''),
                '@@IGNORECTRL@@': ('(void)control;' if modern else ''),
                '@@FREQ@@': ('control->frequency' if modern else 'control'),
                '@@UPDATEARGS@@': ('&fs,&ctrl,' if modern else ''),
            }
            for marker, value in replacements.items():
                program = program.replace(marker, value)
            with self.subTest(stack=str(root)), tempfile.TemporaryDirectory() as tmp:
                src, exe = Path(tmp)/'check.c', Path(tmp)/'check'
                src.write_text(program)
                args = ['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-function', '-Wno-unused-variable',
                        '-I'+str(root/'src/common/modeset'), '-I'+str(root/'src/common/inc'),
                        '-I'+str(root/'src/common/sdk/nvidia/inc'), str(src), '-o', str(exe)]
                built = subprocess.run(args, capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stderr)
                run = subprocess.run([str(exe)], capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__': unittest.main()
