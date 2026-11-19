"""Execute the native DIP writer/readback against a bounded MMIO register file."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelGmpHdr(unittest.TestCase):
    def test_drm_bank_bytes_logical_readback_and_dp_bounds(self):
        kernel=Path(os.environ['CB1_KERNEL_SOURCE'])
        source=(kernel/'drivers/gpu/drm/i915/display/intel_hdmi.c').read_text()
        registers=(kernel/'drivers/gpu/drm/i915/display/intel_display_regs.h').read_text()
        packers=(kernel/'drivers/video/hdmi.c').read_text()
        names=('hdmi_infoframe_checksum','hdmi_infoframe_set_checksum',
               'hdmi_drm_infoframe_init','hdmi_drm_infoframe_check_only',
               'hdmi_drm_infoframe_check','hdmi_drm_infoframe_pack_only')
        functions='\n'.join(function(packers,n) for n in names)
        helpers='\n'.join(function(source,n) for n in (
            'intel_hdmi_has_gmp_hdr','intel_hdmi_uses_gmp_hdr','intel_hdmi_dip_type') if n+'(' in source)
        array=re.search(r'static const u8 infoframe_type_to_idx\[\] = \{.*?\n\};',source,re.S).group()
        owners='\n'.join(function(source,n) for n in (
            'hsw_infoframe_enable','hsw_dip_data_reg','hsw_dip_data_size',
            'hsw_write_infoframe','hsw_read_infoframe','hsw_infoframes_enabled',
            'intel_hdmi_infoframe_enable','intel_hdmi_infoframes_enabled','intel_write_infoframe',
            'intel_hdmi_compute_drm_infoframe','intel_hdmi_fastset_infoframes','hsw_set_infoframes'))
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include <linux/types.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef unsigned intel_reg_t;
struct device;
#include "hdmi-test.h"
#define REG_BIT(n) (1U<<(n))
#define BIT(n) REG_BIT(n)
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define min(a,b) ((a)<(b)?(a):(b))
#define min_t(t,a,b) ((t)min((t)(a),(t)(b)))
#define MISSING_CASE(x) assert(!"unexpected DIP type")
#define INVALID_MMIO_REG 0
#define _MMIO_TRANS2(d,t,r) ((void)(d),(r)+(t)*0x1000)
#include "display-regs.h"
enum transcoder {TRANSCODER_A,TRANSCODER_B,TRANSCODER_C,TRANSCODER_EDP};
enum {DP_SDP_VSC=7,DP_SDP_ADAPTIVE_SYNC=0x22,DP_SDP_PPS=0x10};
struct intel_display{int version;void*drm;struct{bool skylake,kabylake;}platform;};
static struct intel_display display_fixture={9,NULL,{false,true}};
#define to_intel_display(p) ((void)(p),&display_fixture)
#define DISPLAY_VER(d) ((d)->version)
#define IS_DISPLAY_VER(d,a,b) ((d)->version>=(a)&&(d)->version<=(b))
#define HAS_AS_SDP(d) ((d)->version>=13)
#define HAS_DDI(d) ((void)(d),true)
struct intel_encoder{struct{void*dev;}base;};
struct drm_connector_state{void*hdr_output_metadata;};
struct intel_crtc_state{enum transcoder cpu_transcoder;bool has_hdmi_sink,has_psr,has_panel_replay,has_infoframe;
 struct{unsigned enable;union hdmi_infoframe drm,avi,spd,hdmi;}infoframes;};
struct intel_digital_port{u32(*infoframes_enabled)(struct intel_encoder*,const struct intel_crtc_state*);
 void(*write_infoframe)(struct intel_encoder*,const struct intel_crtc_state*,unsigned,const void*,ssize_t);};
static struct intel_digital_port port_fixture;
#define enc_to_dig_port(p) ((void)(p),&port_fixture)
static bool warning(void*d,bool r){(void)d;return r;}
#define drm_WARN_ON(d,r) warning(d,r)
#define drm_dbg_kms(...) ((void)0)
static u32 registers[0x70000/4];static unsigned read_count,write_count;
static u32 intel_de_read(struct intel_display*d,intel_reg_t r)
{(void)d;assert(r<0x70000&&!(r&3));read_count++;return registers[r/4];}
static void intel_de_write(struct intel_display*d,intel_reg_t r,u32 v)
{(void)d;assert(r<0x70000&&!(r&3));registers[r/4]=v;write_count++;}
static void intel_de_posting_read(struct intel_display*d,intel_reg_t r){(void)intel_de_read(d,r);}
static u32 g4x_infoframe_enable(unsigned t){(void)t;return 0;}
static void assert_hdmi_transcoder_func_disabled(struct intel_display*d,enum transcoder t){(void)d;(void)t;}
static bool intel_hdmi_set_gcp_infoframe(struct intel_encoder*e,const struct intel_crtc_state*s,
 const struct drm_connector_state*c){(void)e;(void)s;(void)c;return false;}
static void put_unaligned_le16(u16 v,void*p){u8*b=p;b[0]=v;b[1]=v>>8;}
@@PACKERS@@
static int drm_hdmi_infoframe_set_hdr_metadata(struct hdmi_drm_infoframe*f,struct drm_connector_state*c)
{(void)c;return hdmi_drm_infoframe_init(f);}
ssize_t hdmi_infoframe_pack_only(const union hdmi_infoframe*f,void*b,size_t n)
{assert(f->any.type==HDMI_INFOFRAME_TYPE_DRM);return hdmi_drm_infoframe_pack_only(&f->drm,b,n);}
@@HELPERS@@
@@ARRAY@@
@@OWNERS@@
int main(void){
 struct intel_encoder e={0};struct intel_crtc_state s={.has_hdmi_sink=true,.has_infoframe=true};
 struct drm_connector_state conn={.hdr_output_metadata=&s};
 port_fixture.write_infoframe=hsw_write_infoframe;port_fixture.infoframes_enabled=hsw_infoframes_enabled;
 union hdmi_infoframe f={0};assert(!hdmi_drm_infoframe_init(&f.drm));
 f.drm.eotf=HDMI_EOTF_SMPTE_ST2084;f.drm.max_fall=0x1234;f.drm.max_cll=0xabcd;
 for(int gen=9;gen<=12;gen+=3)for(int trans=0;trans<3;trans++){
  display_fixture.version=gen;s.cpu_transcoder=trans;
  f.drm.eotf=gen==9&&trans==2?HDMI_EOTF_BT_2100_HLG:HDMI_EOTF_SMPTE_ST2084;
  s.infoframes.enable=intel_hdmi_infoframe_enable(HDMI_INFOFRAME_TYPE_DRM);
  memset(registers,0,sizeof(registers));intel_write_infoframe(&e,&s,HDMI_INFOFRAME_TYPE_DRM,&f);
  unsigned base=(gen==9?0x602e0:0x60440)+trans*0x1000;
  unsigned ctl=0x60200+trans*0x1000;
  u32 want=gen==9?BIT(4):BIT(28);assert(registers[ctl/4]==want);
  u8 hardware[32];memcpy(hardware,&registers[base/4],32);
  assert(hardware[0]==0x87&&hardware[1]==1&&hardware[2]==26&&hardware[3]==0);
  assert(hardware[5]==f.drm.eotf);
  assert(hardware[27]==0xcd&&hardware[28]==0xab&&hardware[29]==0x34&&hardware[30]==0x12);
  assert(hardware[31]==0);
  unsigned sum=0;for(unsigned i=0;i<31;i++)sum+=hardware[i];assert(!(sum&255));
  u8 back[32];hsw_read_infoframe(&e,&s,HDMI_INFOFRAME_TYPE_DRM,back,sizeof(back));
  assert(!memcmp(back,hardware,sizeof(back)));
  assert(intel_hdmi_infoframes_enabled(&e,&s)==s.infoframes.enable);
  if(gen==9){
   s.infoframes.drm=f;write_count=0;
   intel_hdmi_fastset_infoframes(&e,&s,&conn);assert(!write_count);
   registers[base/4]=0x010a; // A foreign inherited GMP is not HDR10.
   assert(intel_hdmi_infoframes_enabled(&e,&s)==intel_hdmi_infoframe_enable(HDMI_PACKET_TYPE_GAMUT_METADATA));
  }
  hsw_set_infoframes(&e,false,&s,&conn);assert(!registers[ctl/4]);
 }
 /* Native DP/LSPCON still owns GMP; do not alias it to HDMI DRM. */
 display_fixture.version=9;s.has_hdmi_sink=false;s.cpu_transcoder=TRANSCODER_A;
 memset(registers,0,sizeof(registers));u8 payload[32];memset(payload,0x39,sizeof(payload));
 hsw_write_infoframe(&e,&s,HDMI_PACKET_TYPE_GAMUT_METADATA,payload,sizeof(payload));
 assert(intel_hdmi_infoframes_enabled(&e,&s)==intel_hdmi_infoframe_enable(HDMI_PACKET_TYPE_GAMUT_METADATA));
 u8 sdp[36];memset(sdp,0xcc,sizeof(sdp));read_count=0;
 hsw_read_infoframe(&e,&s,HDMI_PACKET_TYPE_GAMUT_METADATA,sdp,sizeof(sdp));
 assert(read_count==8&&!memcmp(sdp,payload,32));
 assert(!sdp[32]&&!sdp[33]&&!sdp[34]&&!sdp[35]);
 s.has_hdmi_sink=true;s.cpu_transcoder=TRANSCODER_A;
 for(int scenario=0;scenario<4;scenario++){
  s.infoframes.enable=0;display_fixture.platform.kabylake=scenario==0||scenario==3;
  display_fixture.platform.skylake=scenario==2;
  s.cpu_transcoder=scenario==3?TRANSCODER_EDP:TRANSCODER_A;
  bool ok=intel_hdmi_compute_drm_infoframe(&e,&s,&conn);
  if(scenario==1)assert(ok&&!s.infoframes.enable); // BXT/CFL/CML excluded.
  else if(scenario==3)assert(!ok&&!s.infoframes.enable);
  else assert(ok && s.infoframes.enable==intel_hdmi_infoframe_enable(HDMI_INFOFRAME_TYPE_DRM));
 }
}
'''
        code=code.replace('@@PACKERS@@',functions).replace('@@HELPERS@@',helpers)
        code=code.replace('@@ARRAY@@',array).replace('@@OWNERS@@',owners)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/'test.c';binary=root/'test';path.write_text(code)
            (root/'hdmi-test.h').write_text(re.sub(r'^#include .*$', '',
                (kernel/'include/linux/hdmi.h').read_text(),flags=re.M))
            (root/'display-regs.h').write_text(re.sub(r'^#include .*$', '',registers,flags=re.M))
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-Wno-sign-compare','-Wno-unused-function','-Wno-unused-parameter',
                '-ftrivial-auto-var-init=pattern',
                '-I'+str(root),str(path),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
