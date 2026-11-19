"""Execute the matched Intel SPD owner and real HDMI packet packer."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelSpdSdi(unittest.TestCase):
    def test_source_type_changes_only_spd_sdi_and_checksum(self):
        kernel = Path(os.environ['CB1_KERNEL_SOURCE'])
        intel = (kernel / 'drivers/gpu/drm/i915/display/intel_hdmi.c').read_text()
        hdmi = (kernel / 'drivers/video/hdmi.c').read_text()
        header = (kernel / 'include/linux/hdmi.h').read_text()
        parameter = re.search(r'static int hdmi_spd_sdi\s*=\s*([^;]+);', intel)
        initial = parameter.group(1) if parameter else 'HDMI_SPD_SDI_PC'
        packers = '\n'.join(function(hdmi, name) for name in (
            'hdmi_infoframe_checksum', 'hdmi_infoframe_set_checksum',
            'hdmi_spd_infoframe_init', 'hdmi_spd_infoframe_check_only',
            'hdmi_spd_infoframe_check', 'hdmi_spd_infoframe_pack_only',
            'hdmi_spd_infoframe_pack'))
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
#include <linux/types.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint64_t u64;
struct device;
#include "hdmi-test.h"
#define min(a,b) ((a)<(b)?(a):(b))
#define READ_ONCE(a) (a)
static int hdmi_spd_sdi=@@INITIAL@@;
struct intel_display {struct {bool dgfx;} platform;};
static struct intel_display display_fixture;
#define to_intel_display(p) ((void)(p),&display_fixture)
struct intel_encoder {struct {void *dev;} base;};
struct drm_connector_state {};
struct intel_crtc_state {bool has_infoframe;
 struct {unsigned enable;union hdmi_infoframe avi,spd,drm,hdmi;} infoframes;};
static unsigned intel_hdmi_infoframe_enable(unsigned type) {return type==HDMI_INFOFRAME_TYPE_SPD?4:0;}
#define drm_WARN_ON(device, condition) ((void)(device),!!(condition))
@@PACKERS@@
@@OWNER@@
int main(void) {
 struct intel_encoder encoder={0};struct drm_connector_state connector={};
 struct intel_crtc_state base;memset(&base,0x5a,sizeof(base));base.has_infoframe=true;
 struct intel_crtc_state initial=base;
 assert(intel_hdmi_compute_spd_infoframe(&encoder,&initial,&connector));
 assert(initial.infoframes.spd.spd.sdi==1);
 const int inputs[]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,-1,14,2147483647,(-2147483647-1)};
 const int expected[]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,9,9,9,9};
 for(unsigned dgfx=0;dgfx<2;dgfx++) {
  display_fixture.platform.dgfx=dgfx;hdmi_spd_sdi=9;
  struct intel_crtc_state reference=base;
  assert(intel_hdmi_compute_spd_infoframe(&encoder,&reference,&connector));
  unsigned char pc[29];assert(hdmi_spd_infoframe_pack(&reference.infoframes.spd.spd,pc,sizeof(pc))==29);
  assert(pc[0]==0x83 && pc[1]==1 && pc[2]==25 && pc[28]==9);
  assert(!memcmp(pc+4,"Intel\0\0\0",8));
  assert(!memcmp(pc+12,dgfx?"Discrete gfx\0\0\0\0":"Integrated gfx\0\0",16));
  for(unsigned i=0;i<sizeof(inputs)/sizeof(*inputs);i++) {
   hdmi_spd_sdi=inputs[i];struct intel_crtc_state state=base;
   assert(intel_hdmi_compute_spd_infoframe(&encoder,&state,&connector));
   assert(state.infoframes.enable==(base.infoframes.enable|4));
   assert(!memcmp(&state.infoframes.avi,&base.infoframes.avi,sizeof(base.infoframes.avi)));
   assert(!memcmp(&state.infoframes.drm,&base.infoframes.drm,sizeof(base.infoframes.drm)));
   assert(!memcmp(&state.infoframes.hdmi,&base.infoframes.hdmi,sizeof(base.infoframes.hdmi)));
   unsigned char packet[29];assert(hdmi_spd_infoframe_pack(&state.infoframes.spd.spd,packet,sizeof(packet))==29);
   assert(packet[28]==expected[i]);unsigned sum=0;
   for(unsigned j=0;j<sizeof(packet);j++) {sum+=packet[j];if(j!=3 && j!=28)assert(packet[j]==pc[j]);}
   assert((sum&255)==0);
   unsigned char short_packet[28];memset(short_packet,0xa5,sizeof(short_packet));
   assert(hdmi_spd_infoframe_pack(&state.infoframes.spd.spd,short_packet,sizeof(short_packet))==-ENOSPC);
   for(unsigned j=0;j<sizeof(short_packet);j++)assert(short_packet[j]==0xa5);
   state.infoframes.spd.spd.version=2;
   assert(hdmi_spd_infoframe_pack(&state.infoframes.spd.spd,packet,sizeof(packet))==-EINVAL);
  }
 }
 base.has_infoframe=false;struct intel_crtc_state absent=base;hdmi_spd_sdi=1;
 assert(intel_hdmi_compute_spd_infoframe(&encoder,&absent,&connector));
 assert(!memcmp(&absent,&base,sizeof(base)));
}
'''.replace('@@INITIAL@@', initial).replace('@@PACKERS@@', packers).replace(
            '@@OWNER@@', function(intel, 'intel_hdmi_compute_spd_infoframe'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'hdmi-test.h').write_text(re.sub(r'^#include .*$', '', header, flags=re.M))
            (root / 'spd.c').write_text(code)
            compiled = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra',
                                       '-Werror', '-Wno-unused-parameter',
                                       str(root / 'spd.c'), '-o', str(root / 'spd')],
                                      text=True, capture_output=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            tested = subprocess.run([str(root / 'spd')], text=True, capture_output=True)
            self.assertEqual(tested.returncode, 0, tested.stderr)


if __name__ == '__main__':
    unittest.main()
