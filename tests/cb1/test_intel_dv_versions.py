"""Execute Intel's existing V1/V2 VSIF owner with native HDMI packers."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get("CB1_KERNEL_SOURCE"),"matched kernel required")
class IntelVersions(unittest.TestCase):
    def test_existing_v1_and_v2_packet_selection(self):
        kernel=Path(os.environ["CB1_KERNEL_SOURCE"])
        intel=(kernel/"drivers/gpu/drm/i915/display/intel_hdmi.c").read_text()
        hdmi=(kernel/"drivers/video/hdmi.c").read_text()
        names=("hdmi_infoframe_checksum","hdmi_infoframe_set_checksum",
            "hdmi_vendor_infoframe_init","hdmi_vendor_infoframe_length",
            "hdmi_vendor_infoframe_check_only","hdmi_vendor_infoframe_check",
            "hdmi_vendor_infoframe_pack_only","hdmi_vendor_infoframe_pack",
            "hdmi_dolby_vendor_infoframe_init","hdmi_dolby_vendor_infoframe_check",
            "hdmi_dolby_vendor_infoframe_pack")
        program=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <string.h>
#include <sys/types.h>
#include <linux/types.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;
struct device;
#include "hdmi-test.h"
#include "drm_dvbridge.h"
@@PACKERS@@
struct drm_display_mode{unsigned vic,flags;};
struct drm_property_blob{void *data;size_t length;};
struct drm_display_info{bool has_hdmi_infoframe;};
struct drm_connector{struct drm_display_info display_info;struct drm_property_blob*edid_blob_ptr;};
struct drm_connector_state{struct drm_connector*connector;
 struct drm_property_blob*hdr10plus_metadata;bool dv_lab_standard;};
#define to_intel_digital_connector_state(p) (p)
#define intel_dv_lab_avi_vic drm_dvbridge_avi_vic
#define DRM_MODE_FLAG_3D_MASK 8
#define drm_WARN_ON(dev,ret) ((void)(dev),(ret))
struct intel_encoder{struct{void*dev;}base;};
struct intel_crtc_state{bool has_infoframe;struct{
 unsigned enable;union hdmi_infoframe hdmi;}infoframes;
 struct{struct drm_display_mode adjusted_mode;}hw;};
static unsigned drm_match_cea_mode(const struct drm_display_mode*m){return m->vic;}
static unsigned intel_hdmi_infoframe_enable(int t){(void)t;return 1;}
int hdmi_infoframe_unpack(union hdmi_infoframe*f,const void*d,size_t n){
 (void)f;(void)d;(void)n;return -EINVAL;}
static int drm_hdmi_vendor_infoframe_from_display_mode(struct hdmi_vendor_infoframe*f,
 struct drm_connector*c,const struct drm_display_mode*m){
 (void)c;(void)m;return hdmi_vendor_infoframe_init(f);}
@@OWNER@@
static void checksum(u8*b){u8 sum=0;b[127]=0;for(int i=0;i<127;i++)sum+=b[i];b[127]=-sum;}
int main(void){
 u8 raw[256],wire[31],golden[31]={0x81,1,27,0x4b,0x46,0xd0,0,2};
 struct drm_property_blob blob={raw,sizeof(raw)};
 struct drm_connector con={{true},&blob};
 struct drm_connector_state state={.connector=&con,.dv_lab_standard=true};
 struct intel_crtc_state crtc={.has_infoframe=true};
 struct intel_encoder encoder={0};
 for(unsigned version=1;version<=2;version++)for(unsigned length=11;length<=14;length+=3)
 for(unsigned ll=0;ll<2;ll++){
  if(version==2 && length!=11)continue;
  memset(raw,0,sizeof(raw));const u8 magic[]={0,255,255,255,255,255,255,0};
  memcpy(raw,magic,8);raw[126]=1;u8*b=raw+128;
  b[0]=2;b[1]=3;b[2]=5+length;b[4]=0xe0|length;
  b[5]=1;b[6]=0x46;b[7]=0xd0;b[9]=(version<<5)|2;b[11]=2;b[12]=ll;
  checksum(raw);checksum(b);
  for(unsigned vic=93;vic<=97;vic++){
   crtc.hw.adjusted_mode.vic=vic;
   assert(intel_hdmi_compute_hdmi_infoframe(&encoder,&crtc,&state));
   bool legacy=version==1 && (length==14 || !ll);
   if(legacy){
    struct hdmi_vendor_infoframe*f=&crtc.infoframes.hdmi.vendor.hdmi;
    assert(f->dolby_vision && f->vic==(vic<=95?96-vic:0));
    assert(hdmi_vendor_infoframe_pack(f,wire,sizeof(wire))==28);
    assert(wire[4]==3 && wire[5]==12 && wire[7]==(vic<=95?32:0));
   }else{
    assert(hdmi_dolby_vendor_infoframe_pack(&crtc.infoframes.hdmi.vendor.dolby,
      wire,sizeof(wire))==31);
    assert(!memcmp(wire,golden,sizeof(wire)));
   }
  }
 }
 crtc.hw.adjusted_mode.flags=DRM_MODE_FLAG_3D_MASK;
 assert(!intel_hdmi_compute_hdmi_infoframe(&encoder,&crtc,&state));
}
'''.replace("@@PACKERS@@","\n".join(function(hdmi,n) for n in names))
        program=program.replace("@@OWNER@@",function(intel,"intel_hdmi_compute_hdmi_infoframe"))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"test.c";binary=root/"test"
            (root/"hdmi-test.h").write_text(re.sub(r"^#include .*$","",
                (kernel/"include/linux/hdmi.h").read_text(),flags=re.M))
            path.write_text(program)
            result=subprocess.run(["cc","-std=gnu11","-Wall","-Wextra","-Werror",
                "-Wno-unused-function","-I"+str(root),"-I"+str(kernel/"include/drm"),
                str(path),"-o",str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            subprocess.run([str(binary)],check=True)
