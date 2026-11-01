"""HDR10+ must not replace HDMI-VIC with a CTA VIC the sink cannot accept."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelHdr10plusCta(unittest.TestCase):
    def test_native_avi_policy_with_competing_vendor_timing(self):
        kernel=Path(os.environ['CB1_KERNEL_SOURCE'])
        hdmi=(kernel/'drivers/gpu/drm/i915/display/intel_hdmi.c').read_text()
        edid=(kernel/'drivers/gpu/drm/drm_edid.c').read_text()
        name=('drm_hdmi_avi_infoframe_vic' if 'u8 drm_hdmi_avi_infoframe_vic(' in edid
              else 'vic_for_avi_infoframe')
        policy='\n'.join(function(edid,n) for n in ('cta_vdb_has_vic','is_hdmi2_sink',name,
            'drm_mode_hdmi_vic','drm_hdmi_vendor_infoframe_from_display_mode'))
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;
#include "drm_dvbridge_edid.h"
#define BIT(n) (1U<<(n))
enum{DRM_OUTPUT_COLOR_FORMAT_YCBCR420=3,INTEL_OUTPUT_FORMAT_RGB,
 INTEL_OUTPUT_FORMAT_YCBCR420,INTEL_OUTPUT_FORMAT_YCBCR444,HDMI_INFOFRAME_TYPE_AVI,
 HDMI_COLORSPACE_RGB,HDMI_COLORSPACE_YUV420,HDMI_COLORSPACE_YUV444,
 HDMI_QUANTIZATION_RANGE_LIMITED,HDMI_QUANTIZATION_RANGE_FULL,
 HDMI_QUANTIZATION_RANGE_DEFAULT,HDMI_YCC_QUANTIZATION_RANGE_LIMITED,HDMI_COLORIMETRY_NONE};
struct hdmi_avi_infoframe{unsigned video_code,colorspace,colorimetry,extended_colorimetry,
 quantization_range,ycc_quantization_range;};
struct drm_display_mode{u8 vic,hdmi_vic;unsigned flags;};
struct hdmi_vendor_infoframe{u8 vic;int s3d_struct;};
#define DRM_MODE_FLAG_3D_MASK 0xf00
struct drm_display_info{struct{struct{bool supported;}scdc;}hdmi;
 unsigned color_formats;u8*vics;int vics_len;bool has_hdmi_infoframe;};
struct drm_connector{struct drm_display_info display_info;};
struct intel_connector{struct drm_connector base;struct dvbridge_sink_caps dv_sink_caps;};
struct drm_connector_state{struct drm_connector*connector;void*hdr10plus_metadata;bool dv_lab_standard;};
struct intel_crtc_state{bool has_infoframe,limited_color_range;int output_format;
 struct{struct drm_display_mode adjusted_mode;}hw;
 struct{unsigned enable;struct{struct hdmi_avi_infoframe avi;}avi;}infoframes;};
struct intel_encoder{struct{void*dev;}base;};
#define to_intel_connector(p) ((struct intel_connector*)(p))
#define to_intel_digital_connector_state(p) (p)
static bool warning(void*d,bool r){(void)d;return r;}
#define drm_WARN_ON(d,r) warning(d,r)
#define intel_dv_lab_avi_vic(v) (v)
static unsigned intel_hdmi_infoframe_enable(unsigned t){(void)t;return 1;}
static unsigned drm_match_cea_mode(const struct drm_display_mode*m){return m->vic;}
static unsigned drm_match_hdmi_mode(const struct drm_display_mode*m){return m->hdmi_vic;}
static int hdmi_vendor_infoframe_init(struct hdmi_vendor_infoframe*f){memset(f,0,sizeof(*f));return 0;}
static int s3d_structure_from_display_mode(const struct drm_display_mode*m){(void)m;return 0;}
@@POLICY@@
/* Native constructor is an API boundary here; its unchanged legacy choice is zero. */
static int drm_hdmi_avi_infoframe_from_display_mode(struct hdmi_avi_infoframe*f,
 const struct drm_connector*c,const struct drm_display_mode*m)
{(void)c;memset(f,0,sizeof(*f));f->video_code=m->hdmi_vic?0:m->vic;return 0;}
static void drm_hdmi_avi_infoframe_colorimetry(struct hdmi_avi_infoframe*f,struct drm_connector_state*s)
{(void)f;(void)s;}
static void drm_hdmi_avi_infoframe_quant_range(struct hdmi_avi_infoframe*f,struct drm_connector*c,
 const struct drm_display_mode*m,unsigned q){(void)c;(void)m;f->quantization_range=q;}
static void drm_hdmi_avi_infoframe_content_type(struct hdmi_avi_infoframe*f,struct drm_connector_state*s)
{(void)f;(void)s;}
static int hdmi_avi_infoframe_check(struct hdmi_avi_infoframe*f){(void)f;return 0;}
@@OWNER@@
int main(void){
 struct intel_connector c={0};struct drm_connector_state s={.connector=&c.base,.hdr10plus_metadata=&c};
 struct intel_crtc_state crtc={.has_infoframe=true,.output_format=INTEL_OUTPUT_FORMAT_RGB};
 struct intel_encoder e={0};
 for(unsigned vic=93;vic<=95;vic++)for(unsigned sink=0;sink<4;sink++){
  c.base.display_info=(struct drm_display_info){.has_hdmi_infoframe=true};u8 advertised=vic;
  if(sink==1){c.base.display_info.vics=&advertised;c.base.display_info.vics_len=1;}
  if(sink==2)c.base.display_info.hdmi.scdc.supported=true;
  if(sink==3)c.base.display_info.color_formats=BIT(DRM_OUTPUT_COLOR_FORMAT_YCBCR420);
  crtc.hw.adjusted_mode=(struct drm_display_mode){.vic=vic,.hdmi_vic=96-vic};
  bool ok=intel_hdmi_compute_avi_infoframe(&e,&crtc,&s);
  assert(ok==(sink!=0));if(ok)assert(crtc.infoframes.avi.avi.video_code==vic);
 }
 c.base.display_info=(struct drm_display_info){0};
 crtc.hw.adjusted_mode=(struct drm_display_mode){.vic=16};
 assert(intel_hdmi_compute_avi_infoframe(&e,&crtc,&s) && crtc.infoframes.avi.avi.video_code==16);
 crtc.hw.adjusted_mode=(struct drm_display_mode){0};
 assert(intel_hdmi_compute_avi_infoframe(&e,&crtc,&s) && !crtc.infoframes.avi.avi.video_code);
 s.hdr10plus_metadata=NULL;crtc.hw.adjusted_mode=(struct drm_display_mode){.vic=95,.hdmi_vic=1};
 assert(intel_hdmi_compute_avi_infoframe(&e,&crtc,&s) && !crtc.infoframes.avi.avi.video_code);
}
'''.replace('@@POLICY@@',policy).replace('@@OWNER@@',function(hdmi,'intel_hdmi_compute_avi_infoframe'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.c';binary=Path(tmp)/'test';path.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function',
                '-I'+str(kernel/'include/drm'),str(path),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
