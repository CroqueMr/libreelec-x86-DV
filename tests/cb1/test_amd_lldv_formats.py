"""The native format property follows the current connector EDID, not a cached request."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class AMDNativeFormats(unittest.TestCase):
    def test_live_formats_keep_422_and_track_444_depth_hotplug_and_source_family(self):
        kernel = Path(os.environ['CB1_KERNEL_SOURCE'])
        source = (kernel/'drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm_dv.c').read_text()
        names = ('dv_rx550', 'dv_display_supported', 'dv_lldv_native_formats', 'dv_lldv_native_link',
                 'amdgpu_dm_lldv_native_formats')
        functions = '\n'.join(function(source, name) for name in names)
        families = sorted(set(re.findall(r'\b(?:DCN|DCE)_VERSION_\w+', functions)))
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include "drm_dvbridge_edid.h"
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1U<<(n))
enum dce_version {FAMILIES};
enum {AMDGPU_LLDV_RGB10_LAB=3,AMDGPU_LLDV_444_10=4,
      DRM_OUTPUT_COLOR_FORMAT_YCBCR422=2,DRM_OUTPUT_COLOR_FORMAT_YCBCR444=1,
      DRM_EDID_HDMI_DC_30=16,connector_status_connected=1,
      DRM_MODE_CONNECTOR_HDMIA=2,SIGNAL_TYPE_HDMI_TYPE_A=3};
struct dc_context {enum dce_version dce_version;struct{unsigned chip_id;}asic_id;};
struct dc {struct dc_context *ctx;};
struct amdgpu_device {struct{struct dc *dc;}dm;};
#define drm_to_adev(p) ((struct amdgpu_device *)(p))
struct drm_property_blob {size_t length;void *data;};
struct drm_display_info {bool is_hdmi,has_hdmi_infoframe;unsigned color_formats,edid_hdmi_ycbcr444_dc_modes;
 int max_tmds_clock;struct{struct{bool supported;struct{bool supported;}scrambling;}scdc;}hdmi;};
struct drm_connector {void *dev;int status,connector_type;struct drm_property_blob *edid_blob_ptr;
                      struct drm_display_info display_info;};
struct amdgpu_dm_connector {struct drm_connector base;struct{int connector_signal;}*dc_link;};
#define to_amdgpu_dm_connector(p) ((struct amdgpu_dm_connector *)(p))
FUNCTIONS
static void checksum(unsigned char *p)
{unsigned char sum=0;p[127]=0;for(unsigned i=0;i<127;i++)sum+=p[i];p[127]=-sum;}
int main(void)
{
 unsigned char bytes[256]={0},*b=bytes+128;
 const unsigned char magic[]={0,255,255,255,255,255,255,0};
 memcpy(bytes,magic,8);bytes[126]=1;b[0]=2;b[1]=3;b[2]=16;b[4]=0xeb;
 b[5]=1;b[6]=0x46;b[7]=0xd0;b[9]=2<<5;b[11]=3;b[13]=1;
 checksum(bytes);checksum(b);
 struct dc_context ctx={.dce_version=DCN_VERSION_1_0};struct dc dc={&ctx};
 struct amdgpu_device device={.dm={&dc}};
 struct drm_property_blob edid={sizeof(bytes),bytes};
 struct {int connector_signal;}link={SIGNAL_TYPE_HDMI_TYPE_A};
 struct amdgpu_dm_connector con={
  .base={&device,connector_status_connected,DRM_MODE_CONNECTOR_HDMIA,&edid,
   {true,true,BIT(DRM_OUTPUT_COLOR_FORMAT_YCBCR422)|BIT(DRM_OUTPUT_COLOR_FORMAT_YCBCR444),
    DRM_EDID_HDMI_DC_30,600000,{{true,{true}}}}},
  .dc_link=(void*)&link};
 const u32 both=BIT(AMDGPU_LLDV_RGB10_LAB)|BIT(AMDGPU_LLDV_444_10);
 assert(amdgpu_dm_lldv_native_formats(&con.base)==both);
 con.base.display_info.max_tmds_clock=300000;
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_RGB10_LAB));
 con.base.display_info.max_tmds_clock=296702;
 assert(!amdgpu_dm_lldv_native_formats(&con.base));
 con.base.display_info.max_tmds_clock=370878;
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_RGB10_LAB));
 con.base.display_info.max_tmds_clock=370879;
 assert(amdgpu_dm_lldv_native_formats(&con.base)==both);
 con.base.display_info.hdmi.scdc.supported=false;
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_RGB10_LAB));
 con.base.display_info.hdmi.scdc.supported=true;
 con.base.display_info.hdmi.scdc.scrambling.supported=false;
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_RGB10_LAB));
 con.base.display_info.hdmi.scdc.scrambling.supported=true;
 con.base.display_info.max_tmds_clock=600000;
 b[13]=0;checksum(b);
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_RGB10_LAB));
 b[12]=1;checksum(b); /* Twelve-bit Dolby support does not imply ten-bit 4:4:4. */
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_RGB10_LAB));
 b[12]=0;b[13]=1;checksum(b);
 con.base.display_info.edid_hdmi_ycbcr444_dc_modes=0;
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_RGB10_LAB));
 con.base.display_info.edid_hdmi_ycbcr444_dc_modes=DRM_EDID_HDMI_DC_30;
 con.base.display_info.color_formats=BIT(DRM_OUTPUT_COLOR_FORMAT_YCBCR444);
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_444_10));
 con.base.status=0;assert(!amdgpu_dm_lldv_native_formats(&con.base));
 con.base.status=connector_status_connected;
 edid.length=128;assert(!amdgpu_dm_lldv_native_formats(&con.base));edid.length=256;
 b[127]^=1;assert(!amdgpu_dm_lldv_native_formats(&con.base));b[127]^=1;
 link.connector_signal=0;assert(!amdgpu_dm_lldv_native_formats(&con.base));
 link.connector_signal=SIGNAL_TYPE_HDMI_TYPE_A;
 ctx.dce_version=DCE_VERSION_11_2;ctx.asic_id.chip_id=0x67df;
 assert(!amdgpu_dm_lldv_native_formats(&con.base));
 ctx.asic_id.chip_id=0x699f;
 assert(amdgpu_dm_lldv_native_formats(&con.base)==BIT(AMDGPU_LLDV_444_10));
 device.dm.dc=NULL;assert(!amdgpu_dm_lldv_native_formats(&con.base));
}
'''.replace('FAMILIES', ','.join(families)).replace('FUNCTIONS', functions)
        with tempfile.TemporaryDirectory() as directory:
            src, binary = Path(directory)/'test.c', Path(directory)/'test'
            src.write_text(code)
            built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                    '-fsanitize=address,undefined',
                                    '-I'+str(kernel/'include/drm'), str(src), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
