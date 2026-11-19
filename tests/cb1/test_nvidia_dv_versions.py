"""Execute both native AVI writers and their strict legacy-DV timing helper."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


class NvidiaVersions(unittest.TestCase):
    def test_legacy_avi_matches_selected_timing_on_both_stacks(self):
        locations=[os.environ.get("CB1_PASCAL_SOURCE"),os.environ.get("CB1_NVIDIA_SOURCE")]
        if not all(locations): self.skipTest("matched patched R580 and R615 sources required")
        headers=[]
        for location in locations:
            root=Path(location)
            header=(root/"src/common/inc/nvkms-dv-vsif.h").read_text()
            headers.append(header)
            native=function((root/"src/nvidia-modeset/src/nvkms-hdmi.c").read_text(),"SendVideoInfoFrame")
            code=r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include "nvkms-dv-vsif.h"
#define TRUE NV_TRUE
typedef int NvEvoInfoFrameTransmitControl;
typedef struct {int unused;} NVDpyAttributeColor;
typedef struct {int unused;} NVT_EDID_INFO;
typedef struct {unsigned video_format_id,color_space,colorimetry,extended_colorimetry,rgb_quantization_range;} NVT_VIDEO_INFOFRAME_CTRL;
typedef struct {unsigned length; NvU8 byte5;} NVT_VIDEO_INFOFRAME;
typedef struct {int unused;} NVT_INFOFRAME_HEADER;
typedef int NVT_STATUS;
typedef struct {NvBool hdTimings; NVT_VIDEO_INFOFRAME_CTRL ctrl;
 struct{unsigned HDMI_VIC;}vendorSpecificCtrl;} NVDispHeadInfoFrameStateEvoRec;
typedef struct NVDispEvoRec NVDispEvoRec;
typedef void (*Sender)(const NVDispEvoRec *,NvU32,@@TRANSMIT@@,NVT_INFOFRAME_HEADER *,size_t,NvBool);
typedef struct {struct{Sender SendHdmiInfoFrame;}*hal;} NVDevEvoRec;
struct NVDispEvoRec {NVDevEvoRec*pDevEvo;struct{
 struct{NvU8 payload[27];NvU32 payloadSize;}hdmiVsifMetadata;}headState[1];};
enum{NVT_STATUS_SUCCESS,NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_EVERY_FRAME,
 NV_EVO_INFOFRAME_TRANSMIT_CONTROL_EVERY_FRAME};
#define nvEvoLogDispDebug(...) ((void)0)
#define NVT_VIDEO_INFOFRAME_BYTE1_Y1Y0_YCbCr422 1
#define NVT_VIDEO_INFOFRAME_BYTE2_C1C0_EXT_COLORIMETRY 3
#define NVT_VIDEO_INFOFRAME_BYTE3_EC_BT2020RGBYCC 6
#define NVT_VIDEO_INFOFRAME_BYTE3_Q1Q0_DEFAULT 0
#define NVT_VIDEO_INFOFRAME_BYTE5_YQ1YQ0_MASK 0xc0
static unsigned observed;
static NVT_VIDEO_INFOFRAME_CTRL observed_ctrl;
static NvU8 observed_byte5;
static void CalculateVideoInfoFrameColorFormat(const NVDpyAttributeColor*c,NvBool h,
 NVT_EDID_INFO*e,NVT_VIDEO_INFOFRAME_CTRL*v){(void)c;(void)h;(void)e;(void)v;}
static NVT_STATUS NvTiming_ConstructVideoInfoframe(NVT_EDID_INFO*e,
 NVT_VIDEO_INFOFRAME_CTRL*v,void*u,NVT_VIDEO_INFOFRAME*f){
 (void)e;(void)u;observed=v->video_format_id;observed_ctrl=*v;f->length=13;f->byte5=0xd0;return 0;}
static void UpdateInfoFrameFlipStatePre(NvEvoInfoFrameTransmitControl*a,
 NvEvoInfoFrameTransmitControl*b,int c,NvBool d){(void)a;(void)b;(void)c;(void)d;}
static void UpdateInfoFrameFlipStatePost(NvEvoInfoFrameTransmitControl*a){(void)a;}
static void send(const NVDispEvoRec *disp, NvU32 head,
 @@TRANSMIT@@, NVT_INFOFRAME_HEADER *header, size_t length, NvBool checksum){
 (void)disp;(void)head;(void)length;(void)checksum;@@USE_TRANSMIT@@
 observed_byte5=((NVT_VIDEO_INFOFRAME*)header)->byte5;
}
@@NATIVE@@
int main(void){
 typeof(*((NVDevEvoRec*)0)->hal) hal={send};NVDevEvoRec dev={&hal};
 NVDispEvoRec disp={.pDevEvo=&dev};NVDpyAttributeColor color={0};
 NVDispHeadInfoFrameStateEvoRec info={0};NVT_EDID_INFO edid={0};
 NvEvoInfoFrameTransmitControl a=0,b=0;
 NvU8 *p=disp.headState[0].hdmiVsifMetadata.payload;
 for(unsigned size=0;size<=27;size++){
  disp.headState[0].hdmiVsifMetadata.payloadSize=size;
  p[0]=3;p[1]=12;
  for(unsigned vic=16;vic<=97;vic++){
   info.ctrl.video_format_id=vic;
   @@CALL@@
   assert(observed==(size==24 && vic>=93 && vic<=95?0:vic));
  }
 }
 disp.headState[0].hdmiVsifMetadata.payloadSize=24;
 info.ctrl.video_format_id=95;
 p[10]=1;@@CALL@@ assert(observed==95);p[10]=0;
 p[3]=32;p[4]=0;assert(!nvDoviLegacy(p,24));p[4]=1;assert(nvDoviLegacy(p,24));
 p[0]=0x46;p[1]=0xd0;p[3]=2;p[4]=0;
 disp.headState[0].hdmiVsifMetadata.payloadSize=27;
 @@CALL@@ assert(observed==95); /* Modern V1/V2 are untouched. */
 assert(observed_ctrl.color_space==0 && observed_byte5==0xd0);
 for(unsigned vic=93;vic<=95;vic++){
  info.ctrl.video_format_id=vic;
  p[3]=3;
  assert(nvDoviLowLatency(p,27) && !nvDoviLowLatency(p,26));
  @@CALL@@
  assert(observed==vic && observed_ctrl.color_space==1 && observed_ctrl.colorimetry==3);
  assert(observed_ctrl.extended_colorimetry==6 && observed_ctrl.rgb_quantization_range==0);
  assert(observed_byte5==0x10);
  p[26]=1;
  assert(!nvDoviLowLatency(p,27));
  @@CALL@@
  assert(observed_ctrl.color_space==0 && observed_byte5==0xd0);
  p[26]=0;
 }
}
'''
            call="SendVideoInfoFrame(&disp,0,&color,&info,"+("&a,&b," if "currentTransmitCtrl" in native else "")+"&edid);"
            control_type = "NvEvoInfoFrameTransmitControl *" if "currentTransmitCtrl" in native else "int "
            code=code.replace("@@NATIVE@@",native).replace("@@CALL@@",call)
            code=code.replace("@@TRANSMIT@@",control_type+"control").replace("@@USE_TRANSMIT@@","(void)control;")
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/"test.c";binary=Path(tmp)/"test";path.write_text(code)
                result=subprocess.run(["cc","-std=gnu11","-Wall","-Wextra","-Werror",
                    "-Wno-unused-function","-Wno-unused-variable",
                    "-I"+str(root/"src/common/inc"),"-I"+str(root/"src/common/sdk/nvidia/inc"),
                    str(path),"-o",str(binary)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                result=subprocess.run([str(binary)],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(headers[0],headers[1])
